from __future__ import annotations

import logging
from pathlib import Path

from beeagent_module.core.attachment_analysis import run_attachment_analysis
from beeagent_module.core.attachment_store import persist_run_attachments
from beeagent_module.core.document_extraction import DocumentExtractionResult


def _logger() -> logging.Logger:
    logger = logging.getLogger("test_attachment_analysis")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _attachment_settings(
    enabled: bool = True,
    types: list[str] | None = None,
    size_max: int = 4096,
) -> dict:
    return {
        "enabled": enabled,
        "chars_max": 500,
        "size_max": size_max,
        "types": types or ["text/plain"],
        "storage": {
            "enabled": True,
            "file_max": 1048576,
            "message_max": 2097152,
            "files_message_max": 10,
        },
        "extraction": {
            "engine": "docling",
            "chars_max": 2000,
            "pages_max": 20,
            "timeout_seconds": 30,
            "ocr_enabled": True,
        },
    }


def _persist_event(tmp_path: Path, run_id: str, attachments: list[dict]) -> None:
    event = {
        "event_id": "evt-1",
        "event_instance_id": "event-000001",
        "_raw_attachments": attachments,
    }
    persist_run_attachments(
        storage_dir=tmp_path,
        run_id=run_id,
        events=[event],
        attachment_settings=_attachment_settings(),
        logger=_logger(),
    )


def _text_attachment(
    filename: str, content: str, content_type: str = "text/plain"
) -> dict:
    payload = content.encode("utf-8")
    return {
        "filename": filename,
        "content_type": content_type,
        "size": len(payload),
        "payload": payload,
        "storage_status": "stored",
        "reason_code": None,
    }


def _ok_result(text: str) -> DocumentExtractionResult:
    return DocumentExtractionResult(
        attachment_id="evt-1-att-0",
        status="ok",
        reason_code="docling_extraction_completed",
        engine="docling",
        text=text,
        text_length=len(text),
        is_truncated=False,
        content_type="text/plain",
        ocr_used=False,
        page_count=None,
    )


def test_disabled_analysis_zero_extraction_calls(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: calls.append("call") or {},
    )
    _persist_event(tmp_path, "run-1", [_text_attachment("a.txt", "hello world")])

    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-1",
        attachment_settings=_attachment_settings(enabled=False),
        logger=_logger(),
    )

    assert calls == []
    assert results["evt-1-att-0"]["analysis_status"] == "disabled"
    assert results["evt-1-att-0"]["reason_code"] == "analysis_disabled"
    assert results["evt-1-att-0"]["preview_available"] is False


def test_unsupported_content_type_degrades_explicitly(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: calls.append("call") or {},
    )
    _persist_event(
        tmp_path,
        "run-1",
        [
            _text_attachment(
                "legacy.doc", "legacy doc", content_type="application/msword"
            )
        ],
    )

    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-1",
        attachment_settings=_attachment_settings(types=["text/plain"]),
        logger=_logger(),
    )

    assert calls == []
    assert results["evt-1-att-0"]["analysis_status"] == "unsupported"
    assert results["evt-1-att-0"]["reason_code"] == "unsupported_content_type"
    assert results["evt-1-att-0"]["preview_available"] is False


def test_oversized_attachment_degrades_explicitly(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: calls.append("call") or {},
    )
    _persist_event(
        tmp_path,
        "run-1",
        [_text_attachment("big.txt", "x" * 5000)],
    )

    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-1",
        attachment_settings=_attachment_settings(size_max=1024),
        logger=_logger(),
    )

    assert calls == []
    assert results["evt-1-att-0"]["analysis_status"] == "unsupported"
    assert results["evt-1-att-0"]["reason_code"] == "attachment_oversized"


def test_successful_extraction_feeds_bounded_preview(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: {"evt-1-att-0": _ok_result("RFQ welding wire ER70S-6")},
    )
    _persist_event(tmp_path, "run-1", [_text_attachment("quote.txt", "quote content")])

    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-1",
        attachment_settings=_attachment_settings(),
        logger=_logger(),
    )

    result = results["evt-1-att-0"]
    assert result["analysis_status"] == "ok"
    assert result["reason_code"] == "docling_extraction_completed"
    assert result["preview_available"] is True
    assert result["analysis_preview"] == "RFQ welding wire ER70S-6"
    assert result["engine"] == "docling"
    assert result["text_length"] == len("RFQ welding wire ER70S-6")


def test_failed_extraction_degrades_explicitly(tmp_path: Path, monkeypatch) -> None:
    failed = DocumentExtractionResult(
        attachment_id="evt-1-att-0",
        status="failed",
        reason_code="docling_model_assets_missing",
        engine="docling",
        text="",
        text_length=0,
        is_truncated=False,
        content_type="text/plain",
        ocr_used=False,
        page_count=None,
    )
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: {"evt-1-att-0": failed},
    )
    _persist_event(tmp_path, "run-1", [_text_attachment("a.txt", "hello")])

    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-1",
        attachment_settings=_attachment_settings(),
        logger=_logger(),
    )

    result = results["evt-1-att-0"]
    assert result["analysis_status"] == "failed"
    assert result["reason_code"] == "docling_model_assets_missing"
    assert result["preview_available"] is False


def test_extraction_batch_receives_eligible_items_only(
    tmp_path: Path, monkeypatch
) -> None:
    captured: list[list[dict]] = []
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: captured.append(k["attachment_items"]) or {},
    )
    _persist_event(
        tmp_path,
        "run-1",
        [
            _text_attachment("ok.txt", "hello"),
            _text_attachment("big.txt", "x" * 5000),
            _text_attachment("legacy.doc", "legacy", content_type="application/msword"),
        ],
    )

    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-1",
        attachment_settings=_attachment_settings(size_max=1024),
        logger=_logger(),
    )

    assert len(captured) == 1
    eligible_ids = {item["attachment_id"] for item in captured[0]}
    assert eligible_ids == {"evt-1-att-0"}
    assert results["evt-1-att-1"]["reason_code"] == "attachment_oversized"
    assert results["evt-1-att-2"]["reason_code"] == "unsupported_content_type"


def test_no_manifest_returns_empty(tmp_path: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.core.attachment_analysis.extract_attachment_documents",
        lambda *a, **k: calls.append("call") or {},
    )
    results = run_attachment_analysis(
        storage_dir=tmp_path,
        run_id="run-missing",
        attachment_settings=_attachment_settings(),
        logger=_logger(),
    )
    assert results == {}
    assert calls == []


def test_no_provider_attachment_reading_path_remains() -> None:
    import beeagent_module.core.attachment_analysis as module

    for name in (
        "_call_text_provider",
        "_call_file_provider",
        "_upload_provider_file",
        "_delete_provider_file",
        "_post_json",
        "_post_responses_file",
        "_resolve_named_profile",
    ):
        assert not hasattr(module, name), f"provider path {name} must not exist"


def _failed_result(reason_code: str) -> DocumentExtractionResult:
    return DocumentExtractionResult(
        attachment_id="evt-1-att-0",
        status="failed",
        reason_code=reason_code,
        engine="docling",
        text="",
        text_length=0,
        is_truncated=False,
        content_type="text/plain",
        ocr_used=False,
        page_count=None,
    )


def _unsupported_result(reason_code: str) -> DocumentExtractionResult:
    return DocumentExtractionResult(
        attachment_id="evt-1-att-0",
        status="unsupported",
        reason_code=reason_code,
        engine="docling",
        text="",
        text_length=0,
        is_truncated=False,
        content_type="text/plain",
        ocr_used=False,
        page_count=None,
    )


def _build_extraction(
    tmp_path: Path,
    run_id: str,
    attachments: list[dict],
    analysis_results: dict,
    enabled: bool = True,
) -> tuple[dict, list[dict]]:
    from beeagent_module.core.attachment_extraction import build_attachment_extraction

    event = {
        "event_id": "evt-1",
        "event_instance_id": "event-000001",
        "source_id": "source-1",
        "source_type": "email",
        "source_role": "inbound",
        "source_display_name": "Source",
        "client_id": "welding",
        "sender": "buyer@example.com",
        "subject": "RFQ",
        "attachments": [
            {
                "filename": att["filename"],
                "content_type": att["content_type"],
                "size_bytes": att.get("size_bytes", 64),
            }
            for att in attachments
        ],
    }
    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id=run_id,
        events=[{**event, "_raw_attachments": attachments}],
        attachment_settings=_attachment_settings(enabled=enabled),
        logger=_logger(),
    )
    return build_attachment_extraction(
        run_id=run_id,
        events=[event],
        attachment_settings=_attachment_settings(enabled=enabled),
        attachment_manifest=manifest,
        analysis_results=analysis_results,
    )


def test_successful_docling_maps_to_canonical_preview(tmp_path: Path) -> None:
    artifact, enriched = _build_extraction(
        tmp_path=tmp_path,
        run_id="run-ok",
        attachments=[_text_attachment("quote.txt", "RFQ welding wire ER70S-6")],
        analysis_results={
            "evt-1-att-0": {
                "analysis_status": "ok",
                "reason_code": "docling_extraction_completed",
                "analysis_preview": "RFQ welding wire ER70S-6",
                "preview_available": True,
            }
        },
    )
    item = artifact["items"][0]
    assert item["extraction_status"] == "preview"
    assert item["preview_available"] is True
    assert item["text_preview"] == "RFQ welding wire ER70S-6"
    assert item["reason_code"] == "local_extraction_preview"
    event = enriched[0]
    assert event["attachment_extraction_status"] == "preview"
    assert event["attachment_preview_available"] is True
    assert "ER70S-6" in event["attachment_text_preview"]


def test_missing_assets_maps_to_canonical_failed(tmp_path: Path) -> None:
    artifact, enriched = _build_extraction(
        tmp_path=tmp_path,
        run_id="run-fail",
        attachments=[_text_attachment("quote.txt", "RFQ welding wire ER70S-6")],
        analysis_results={
            "evt-1-att-0": {
                "analysis_status": "failed",
                "reason_code": "docling_assets_missing",
                "analysis_preview": "",
                "preview_available": False,
            }
        },
    )
    item = artifact["items"][0]
    assert item["extraction_status"] == "failed"
    assert item["preview_available"] is False
    assert item["text_preview"] == ""
    assert item["reason_code"] == "docling_assets_missing"
    assert artifact["aggregate"]["failed_count"] == 1
    assert artifact["status"] == "degraded"
    event = enriched[0]
    assert event["attachment_extraction_status"] == "failed"
    assert event["attachment_preview_available"] is False


def test_unsupported_maps_to_canonical_unsupported(tmp_path: Path) -> None:
    artifact, enriched = _build_extraction(
        tmp_path=tmp_path,
        run_id="run-unsupported",
        attachments=[_text_attachment("legacy.doc", "legacy")],
        analysis_results={
            "evt-1-att-0": {
                "analysis_status": "unsupported",
                "reason_code": "unsupported_content_type",
                "analysis_preview": "",
                "preview_available": False,
            }
        },
    )
    item = artifact["items"][0]
    assert item["extraction_status"] == "unsupported"
    assert item["reason_code"] == "unsupported_content_type"
    event = enriched[0]
    assert event["attachment_extraction_status"] == "unsupported"


def test_refusal_precedence_not_overwritten_by_parser(tmp_path: Path) -> None:
    artifact, enriched = _build_extraction(
        tmp_path=tmp_path,
        run_id="run-refused",
        attachments=[
            {
                "filename": "forwarded.eml",
                "content_type": "message/rfc822",
                "size_bytes": 128,
            }
        ],
        analysis_results={
            "evt-1-att-0": {
                "analysis_status": "ok",
                "reason_code": "docling_extraction_completed",
                "analysis_preview": "should not override",
                "preview_available": True,
            }
        },
    )
    item = artifact["items"][0]
    assert item["extraction_status"] == "refused"
    assert item["is_refused"] is True
    assert item["reason_code"] == "blocked_email_attachment"
    event = enriched[0]
    assert event["attachment_extraction_status"] == "refused"


def test_historical_analysis_fields_remain_readable(tmp_path: Path) -> None:
    artifact, _enriched = _build_extraction(
        tmp_path=tmp_path,
        run_id="run-historical",
        attachments=[_text_attachment("quote.txt", "RFQ welding wire ER70S-6")],
        analysis_results={
            "evt-1-att-0": {
                "analysis_status": "ok",
                "reason_code": "docling_extraction_completed",
                "analysis_preview": "RFQ welding wire ER70S-6",
                "preview_available": True,
            }
        },
    )
    item = artifact["items"][0]
    assert item["analysis_status"] == "ok"
    assert item["analysis_reason_code"] == "docling_extraction_completed"
    assert item["analysis_preview"] == "RFQ welding wire ER70S-6"
