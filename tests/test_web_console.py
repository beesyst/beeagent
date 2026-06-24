from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from beeagent_module.web.app import create_web_app, start_web_mode


def _logger() -> logging.Logger:
    logger = logging.getLogger("test_web_console")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _make_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "storage"
    (storage_dir / "runs").mkdir(parents=True)
    (storage_dir / "interfaces").mkdir(parents=True)
    return storage_dir


def _write_modules_artifact(storage_dir: Path) -> None:
    modules_payload = {
        "registry": [
            {
                "id": "beeagent-rop",
                "package": "beeagent_rop",
                "entry": "RopModule",
                "state": "loaded",
                "error": "",
            }
        ]
    }
    (storage_dir / "interfaces" / "modules.json").write_text(
        json.dumps(modules_payload),
        encoding="utf-8",
    )


def _write_run_artifacts(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    module_dir = run_dir / "module-beeagent-rop"
    module_dir.mkdir(parents=True)

    operator_summary = {
        "run_id": run_id,
        "status": "ok",
        "summary": "batch completed",
        "source": {
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "client_id": "welding",
            "source_display_name": "Welding Hotline mailbox",
            "mailbox_folder": "welding",
            "loaded_item_count": 3,
            "fetched_count": 3,
            "loaded_count": 3,
            "malformed_count": 0,
            "period": "2026-05",
        },
        "classification": {
            "normalized_count": 3,
            "classified_count": 3,
            "classification_failed_count": 0,
        },
    }

    source_diagnostics = {
        "source_id": "hotline_mailbox",
        "source_type": "mailbox_readonly",
        "source_role": "technical_aggregator",
        "client_id": "welding",
        "source_display_name": "Welding Hotline mailbox",
        "mailbox_folder": "welding",
        "items_max": 20,
        "status": "ok",
        "fetched_count": 3,
        "loaded_count": 3,
        "processed_count": 3,
        "malformed_count": 0,
        "reason": None,
    }

    intake_metadata = {
        "source_id": "hotline_mailbox",
        "source_type": "mailbox_readonly",
        "source_role": "technical_aggregator",
        "client_id": "welding",
        "source_display_name": "Welding Hotline mailbox",
        "mailbox_folder": "welding",
        "loaded_item_count": 3,
        "fetched_count": 3,
        "loaded_count": 3,
        "malformed_count": 0,
        "items_max": 20,
    }

    normalized_events = [
        {
            "event_id": "evt-1",
            "sender": "first@example.com",
            "subject": "Need price",
            "body_preview": "Need welding consumables",
            "attachments": [
                {
                    "filename": "brief.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 1024,
                    "content": "ATTACHMENT_RAW_CONTENT_SHOULD_NOT_BE_RENDERED",
                },
                {
                    "filename": "original.eml",
                    "content_type": "message/rfc822",
                    "size_bytes": 2048,
                    "content": "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED",
                },
            ],
            "raw_eml": "RAW-EML-CONTENT-SHOULD-NOT-BE-RENDERED",
        },
        {
            "event_id": "evt-2",
            "sender": "second@example.com",
            "subject": "Need logistics",
            "body_preview": "Urgent logistics request",
            "attachments": [],
        },
        {
            "event_id": "evt-3",
            "sender": "third@example.com",
            "subject": "Finance details",
            "body_preview": "Finance follow-up",
            "attachments": [],
        },
    ]

    classified_events = [
        {
            "event_id": "evt-1",
            "original_event_id": "evt-1",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "reason_code": "new_contact",
            "reasoning": "sender is new",
            "is_fallback": False,
        },
        {
            "event_id": "evt-2",
            "original_event_id": "evt-2",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.81,
            "reason_code": "duplicate_sender",
            "reasoning": "duplicate by sender",
            "is_fallback": True,
        },
        {
            "event_id": "evt-3",
            "original_event_id": "evt-3",
            "case_type": "irrelevant",
            "priority": "low",
            "confidence": 0.7,
            "reason_code": "non_rop_topic",
            "reasoning": "non ROP",
            "is_fallback": False,
        },
    ]

    attachment_extraction = {
        "run_id": run_id,
        "status": "ok",
        "aggregate": {
            "event_count": 3,
            "attachment_count": 2,
            "preview_available_count": 1,
            "metadata_only_count": 0,
            "refused_count": 1,
            "unsupported_count": 0,
            "failed_count": 0,
        },
        "items": [
            {
                "event_id": "evt-1",
                "source_id": "hotline_mailbox",
                "attachment_id": "evt-1-att-0",
                "filename": "brief.txt",
                "content_type": "text/plain",
                "size_bytes": 200,
                "extraction_status": "preview",
                "preview_available": True,
                "text_preview": "safe text preview",
                "preview_chars": 17,
                "is_supported": True,
                "is_refused": False,
                "is_truncated": False,
                "reason_code": "text_preview_extracted",
                "refusal_reason": None,
                "content": "RAW-CONTENT-MUST-NOT-BE-RENDERED",
            },
            {
                "event_id": "evt-1",
                "source_id": "hotline_mailbox",
                "attachment_id": "evt-1-att-1",
                "filename": "mail.eml",
                "content_type": "message/rfc822",
                "size_bytes": 200,
                "extraction_status": "refused",
                "preview_available": False,
                "text_preview": "",
                "preview_chars": 0,
                "is_supported": False,
                "is_refused": True,
                "is_truncated": False,
                "reason_code": "blocked_email_attachment",
                "refusal_reason": "email attachments are blocked",
            },
        ],
    }

    (run_dir / "operator_summary.json").write_text(
        json.dumps(operator_summary),
        encoding="utf-8",
    )
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics),
        encoding="utf-8",
    )
    (run_dir / "intake_metadata.json").write_text(
        json.dumps(intake_metadata),
        encoding="utf-8",
    )
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized_events),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified_events),
        encoding="utf-8",
    )
    (run_dir / "attachment_extraction.json").write_text(
        json.dumps(attachment_extraction),
        encoding="utf-8",
    )
    (run_dir / "rop_review_table.tsv").write_text(
        "event_id\tbot_case_type\nevt-1\tnew_lead\n",
        encoding="utf-8",
    )
    (module_dir / "module_result.json").write_text("{}", encoding="utf-8")
    (module_dir / "rop_summary_result.json").write_text("{}", encoding="utf-8")
    return run_dir


def _write_multi_source_run_artifacts(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    module_dir = run_dir / "module-beeagent-rop"
    module_dir.mkdir(parents=True)

    operator_summary = {
        "run_id": run_id,
        "status": "ok",
        "summary": "batch completed with partial degradation",
        "source": {
            "mode": "all_enabled",
            "source_count": 2,
            "loaded_source_count": 1,
            "degraded_source_count": 1,
            "status": "ok",
            "reason": "partial_degradation",
            "fetched_count": 2,
            "loaded_count": 2,
            "malformed_count": 0,
        },
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Welding Hotline mailbox",
                "client_id": "welding",
                "status": "ok",
                "reason": None,
            },
            {
                "source_id": "sales_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "sales_mailbox",
                "source_display_name": "Welding Sales mailbox",
                "client_id": "welding",
                "status": "degraded",
                "reason": "source_load_error",
            },
        ],
        "classification": {
            "normalized_count": 2,
            "classified_count": 2,
            "classification_failed_count": 0,
        },
    }

    source_diagnostics = {
        "selection_mode": "all_enabled",
        "status": "ok",
        "reason": "partial_degradation",
        "aggregate": {
            "source_count": 2,
            "loaded_source_count": 1,
            "degraded_source_count": 1,
            "fetched_count": 2,
            "loaded_count": 2,
            "malformed_count": 0,
        },
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Welding Hotline mailbox",
                "client_id": "welding",
                "authority": "read_only",
                "mailbox_folder": "welding",
                "status": "ok",
                "reason": None,
                "items_max": 20,
                "fetched_count": 2,
                "loaded_count": 2,
                "malformed_count": 0,
            },
            {
                "source_id": "sales_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "sales_mailbox",
                "source_display_name": "Welding Sales mailbox",
                "client_id": "welding",
                "authority": "read_only",
                "mailbox_folder": "sales",
                "status": "degraded",
                "reason": "source_load_error",
                "items_max": 20,
                "fetched_count": 0,
                "loaded_count": 0,
                "malformed_count": 0,
            },
        ],
    }

    intake_metadata = {
        "selection_mode": "all_enabled",
        "period": "2026-05",
        "raw_item_count": 2,
        "loaded_item_count": 2,
        "fetched_count": 2,
        "loaded_count": 2,
        "malformed_count": 0,
        "source_count": 2,
        "loaded_source_count": 1,
        "degraded_source_count": 1,
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Welding Hotline mailbox",
                "client_id": "welding",
                "authority": "read_only",
                "mailbox_folder": "welding",
                "items_max": 20,
                "loaded_count": 2,
            },
            {
                "source_id": "sales_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "sales_mailbox",
                "source_display_name": "Welding Sales mailbox",
                "client_id": "welding",
                "authority": "read_only",
                "mailbox_folder": "sales",
                "items_max": 20,
                "loaded_count": 0,
            },
        ],
    }

    normalized_events = [
        {
            "event_id": "evt-ms-1",
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "Welding Hotline mailbox",
            "client_id": "welding",
            "sender": "first@example.com",
            "subject": "Need price",
            "body_preview": "Need welding consumables",
            "attachments": [],
        },
        {
            "event_id": "evt-ms-2",
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "Welding Hotline mailbox",
            "client_id": "welding",
            "sender": "second@example.com",
            "subject": "Need logistics",
            "body_preview": "Urgent logistics request",
            "attachments": [],
        },
    ]

    classified_events = [
        {
            "event_id": "evt-ms-1",
            "original_event_id": "evt-ms-1",
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "Welding Hotline mailbox",
            "client_id": "welding",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "reason_code": "new_contact",
            "reasoning": "sender is new",
            "is_fallback": False,
        },
        {
            "event_id": "evt-ms-2",
            "original_event_id": "evt-ms-2",
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "Welding Hotline mailbox",
            "client_id": "welding",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.81,
            "reason_code": "duplicate_sender",
            "reasoning": "duplicate by sender",
            "is_fallback": True,
        },
    ]

    (run_dir / "operator_summary.json").write_text(
        json.dumps(operator_summary),
        encoding="utf-8",
    )
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics),
        encoding="utf-8",
    )
    (run_dir / "intake_metadata.json").write_text(
        json.dumps(intake_metadata),
        encoding="utf-8",
    )
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized_events),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified_events),
        encoding="utf-8",
    )
    (run_dir / "rop_review_table.tsv").write_text(
        "event_id\tbot_case_type\nevt-ms-1\tnew_lead\n",
        encoding="utf-8",
    )
    (module_dir / "module_result.json").write_text("{}", encoding="utf-8")
    (module_dir / "rop_summary_result.json").write_text("{}", encoding="utf-8")
    return run_dir


def _client(storage_dir: Path) -> TestClient:
    app = create_web_app(
        settings={
            "web": {
                "host": "127.0.0.1",
                "port": 18080,
                "open_browser": False,
            }
        },
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)


def test_runs_route_with_empty_storage(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    response = client.get("/runs")

    assert response.status_code == 200
    assert "No runs found" in response.text


def test_html_routes_render_run_pages(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-001")
    client = _client(storage_dir)

    runs_response = client.get("/runs")
    overview_response = client.get("/runs/run-001")
    dashboard_response = client.get("/runs/run-001/rop")

    assert runs_response.status_code == 200
    assert "run-001" in runs_response.text
    assert overview_response.status_code == 200
    assert "Run overview: run-001" in overview_response.text
    assert dashboard_response.status_code == 200
    assert "ROP dashboard: run-001" in dashboard_response.text
    assert "Welding Hotline mailbox" in dashboard_response.text


def test_rop_dashboard_filter_case_type(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-002")
    client = _client(storage_dir)

    response = client.get("/runs/run-002/rop", params={"case_type": "duplicate"})

    assert response.status_code == 200
    assert "evt-2" in response.text
    assert "evt-1" not in response.text


def test_runs_api_returns_index(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-003")
    client = _client(storage_dir)

    response = client.get("/api/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_runs"] == 1
    assert payload["runs"][0]["run_id"] == "run-003"


def test_run_overview_api_returns_artifacts_and_counts(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-004")
    client = _client(storage_dir)

    response = client.get("/api/runs/run-004")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run-004"
    assert payload["counts"]["classified_count"] == 3
    assert any(
        item["name"] == "operator_summary.json"
        for item in payload["available_artifacts"]
    )


def test_rop_dashboard_api_is_sanitized_and_filterable(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-005")
    client = _client(storage_dir)

    response = client.get(
        "/api/rop/runs/run-005/dashboard",
        params={"fallback": "true"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["shown_rows"] == 1
    assert payload["rows"][0]["event_id"] == "evt-2"
    assert payload["rows"][0]["source_id"] == "hotline_mailbox"
    assert "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED" not in json.dumps(payload)
    assert "original.eml" not in json.dumps(payload)


def test_rop_dashboard_multisource_html_shows_source_rows(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_multi_source_run_artifacts(storage_dir=storage_dir, run_id="run-ms-001")
    client = _client(storage_dir)

    response = client.get("/runs/run-ms-001/rop")

    assert response.status_code == 200
    assert "source aggregate" in response.text
    assert "Welding Sales mailbox" in response.text
    assert "source_status" in response.text


def test_rop_dashboard_multisource_api_shape_and_source_filters(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_multi_source_run_artifacts(storage_dir=storage_dir, run_id="run-ms-002")
    client = _client(storage_dir)

    response = client.get("/api/rop/runs/run-ms-002/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_aggregate"]["source_count"] == 2
    assert payload["source_aggregate"]["degraded_source_count"] == 1
    assert len(payload["sources"]) == 2
    assert "source_id" in payload["filter_options"]
    assert "source_status" in payload["filter_options"]
    assert payload["rows"][0]["source_role"] == "technical_aggregator"

    filtered = client.get(
        "/api/rop/runs/run-ms-002/dashboard",
        params={"source_status": "degraded"},
    )
    filtered_payload = filtered.json()
    assert filtered.status_code == 200
    assert filtered_payload["metrics"]["shown_rows"] == 0


def test_rop_dashboard_multisource_html_source_status_filter(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_multi_source_run_artifacts(storage_dir=storage_dir, run_id="run-ms-003")
    client = _client(storage_dir)

    response = client.get(
        "/runs/run-ms-003/rop",
        params={"source_status": "ok"},
    )

    assert response.status_code == 200
    assert "evt-ms-1" in response.text
    assert "evt-ms-2" in response.text


def test_modules_html_and_api_read_existing_artifact(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)

    html_response = client.get("/modules")
    api_response = client.get("/api/modules")

    assert html_response.status_code == 200
    assert "beeagent-rop" in html_response.text
    assert api_response.status_code == 200
    assert api_response.json()["modules"][0]["id"] == "beeagent-rop"


def test_path_traversal_attempt_in_run_id_blocked_for_html_and_api(
    tmp_path: Path,
) -> None:
    client = _client(_make_storage(tmp_path))

    html_response = client.get("/runs/%2E%2E/etc/passwd/rop")
    api_response = client.get("/api/runs/%2E%2E/etc/passwd")

    assert html_response.status_code == 400
    assert api_response.status_code == 400


def test_no_raw_eml_or_attachment_content_in_rendered_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-006")
    client = _client(storage_dir)

    response = client.get("/runs/run-006/rop")

    assert response.status_code == 200
    assert "original.eml" not in response.text
    assert "message/rfc822" not in response.text
    assert "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED" not in response.text
    assert "RAW-EML-CONTENT-SHOULD-NOT-BE-RENDERED" not in response.text
    assert "ATTACHMENT_RAW_CONTENT_SHOULD_NOT_BE_RENDERED" not in response.text


def test_normalized_events_artifact_is_sanitized(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-007")
    client = _client(storage_dir)

    response = client.get("/runs/run-007/artifact/normalized_events.json")

    assert response.status_code == 200
    assert "brief.pdf" in response.text
    assert "application/pdf" in response.text
    assert "original.eml" not in response.text
    assert "message/rfc822" not in response.text
    assert "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED" not in response.text
    assert '"raw_eml"' not in response.text
    assert '"content"' not in response.text


def test_attachment_extraction_artifact_is_whitelisted_and_sanitized(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-009")
    client = _client(storage_dir)

    response = client.get("/runs/run-009/artifact/attachment_extraction.json")

    assert response.status_code == 200
    assert "safe text preview" in response.text
    assert "RAW-CONTENT-MUST-NOT-BE-RENDERED" not in response.text
    assert "mail.eml" not in response.text
    assert "message/rfc822" not in response.text


def test_get_routes_do_not_mutate_storage(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir=storage_dir, run_id="run-008")
    client = _client(storage_dir)

    before = {
        path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    client.get("/runs")
    client.get("/runs/run-008")
    client.get("/runs/run-008/rop")
    client.get("/api/runs")
    client.get("/api/runs/run-008")
    client.get("/api/rop/runs/run-008/dashboard")

    after = {
        path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert after == before


def test_start_web_mode_no_browser_open_and_uses_host_port(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app, host: str, port: int, access_log: bool) -> None:
        captured["title"] = app.title
        captured["host"] = host
        captured["port"] = port
        captured["access_log"] = access_log

    open_calls: list[str] = []

    def fake_open(url: str) -> bool:
        open_calls.append(url)
        return True

    monkeypatch.setattr("beeagent_module.web.app.uvicorn.run", fake_run)
    monkeypatch.setattr("beeagent_module.web.app.webbrowser.open", fake_open)

    start_web_mode(
        settings={"web": {"host": "127.0.0.1", "port": 19080, "open_browser": False}},
        logger=_logger(),
    )

    assert captured == {
        "title": "BeeAgent Web Console",
        "host": "127.0.0.1",
        "port": 19080,
        "access_log": False,
    }
    assert open_calls == []


def test_start_web_mode_opens_browser_when_enabled(monkeypatch) -> None:
    open_calls: list[str] = []

    def fake_run(app, host: str, port: int, access_log: bool) -> None:
        return None

    def fake_open(url: str) -> bool:
        open_calls.append(url)
        return True

    monkeypatch.setattr("beeagent_module.web.app.uvicorn.run", fake_run)
    monkeypatch.setattr("beeagent_module.web.app.webbrowser.open", fake_open)

    start_web_mode(
        settings={"web": {"host": "127.0.0.1", "port": 18081, "open_browser": True}},
        logger=_logger(),
    )

    assert open_calls == ["http://127.0.0.1:18081/"]
