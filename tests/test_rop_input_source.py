from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from beeagent_module.core.input_source import (
    _extract_clean_subject,
    _extract_forwarded_wrapper_fields,
    _extract_transport_labels,
    _sanitize_batch_item,
    find_active_rop_source,
    load_json_batch,
    load_mailbox_readonly,
    load_rop_source,
    select_rop_sources,
)

EMAIL_PREVIEW_BODY_CHARS_MAX = 4000


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_input_source_null")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_find_active_source_returns_single_enabled() -> None:
    sources = [
        {"source_id": "s1", "enabled": False},
        {"source_id": "s2", "enabled": True},
    ]
    result = find_active_rop_source(sources)
    assert result["source_id"] == "s2"


def test_find_active_source_raises_when_no_sources() -> None:
    with pytest.raises(RuntimeError, match="no input source declared"):
        find_active_rop_source([])


def test_find_active_source_raises_when_no_enabled_source() -> None:
    sources = [
        {"source_id": "s1", "enabled": False},
        {"source_id": "s2", "enabled": False},
    ]
    with pytest.raises(RuntimeError, match="no enabled source found"):
        find_active_rop_source(sources)


def test_find_active_source_raises_when_multiple_enabled() -> None:
    sources = [
        {"source_id": "s1", "enabled": True},
        {"source_id": "s2", "enabled": True},
    ]
    with pytest.raises(RuntimeError, match="multiple enabled sources"):
        find_active_rop_source(sources)


def test_select_rop_sources_all_enabled_returns_all_sources() -> None:
    sources = [
        {"source_id": "s1", "enabled": True},
        {"source_id": "s2", "enabled": False},
        {"source_id": "s3", "enabled": True},
    ]

    selected, mode = select_rop_sources(sources, all_sources=True)

    assert mode == "all_enabled"
    assert [item["source_id"] for item in selected] == ["s1", "s3"]


def test_select_rop_sources_explicit_source_id() -> None:
    sources = [
        {"source_id": "s1", "enabled": True},
        {"source_id": "s2", "enabled": True},
    ]

    selected, mode = select_rop_sources(sources, source_id="s2")

    assert mode == "single_explicit"
    assert len(selected) == 1
    assert selected[0]["source_id"] == "s2"


def test_select_rop_sources_explicit_disabled_raises() -> None:
    sources = [
        {"source_id": "s1", "enabled": False},
    ]

    with pytest.raises(RuntimeError, match="is disabled"):
        select_rop_sources(sources, source_id="s1")


def _make_source(path: str, period: str = "2026-05", items_max: int = 100) -> dict:
    return {
        "source_id": "test-source",
        "source_type": "json_batch",
        "source_role": "batch_sample",
        "client_id": "welding",
        "display_name": "Test Batch Source",
        "enabled": True,
        "authority": "read_only",
        "items_max": items_max,
        "batch": {
            "path": path,
            "period": period,
        },
    }


def test_load_json_batch_success(tmp_path: Path) -> None:
    batch = {
        "period": "2026-04",
        "items": [
            {"event_id": "e1", "case_type": "new_lead"},
            {"event_id": "e2", "case_type": "irrelevant"},
        ],
    }
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)), period="2026-05")
    events, metadata = load_json_batch(
        source=source,
        project_root=tmp_path,
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
    )

    assert len(events) == 2
    assert events[0]["event_id"] == "e1"
    assert metadata["period"] == "2026-04"
    assert metadata["source_id"] == "test-source"
    assert metadata["source_role"] == "batch_sample"
    assert metadata["client_id"] == "welding"
    assert metadata["source_display_name"] == "Test Batch Source"
    assert metadata["raw_item_count"] == 2
    assert metadata["loaded_item_count"] == 2


def test_load_json_batch_uses_config_period_when_file_has_none(tmp_path: Path) -> None:
    batch = {"items": [{"event_id": "e1", "case_type": "new_lead"}]}
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)), period="2026-05")
    _events, metadata = load_json_batch(
        source=source,
        project_root=tmp_path,
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
    )
    assert metadata["period"] == "2026-05"


def test_load_json_batch_missing_file(tmp_path: Path) -> None:
    source = _make_source("storage/mock/nonexistent.json")
    with pytest.raises(RuntimeError, match="batch file not found"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_invalid_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {{", encoding="utf-8")

    source = _make_source(str(bad_file.relative_to(tmp_path)))
    with pytest.raises(RuntimeError, match="not valid JSON"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_invalid_shape_not_dict(tmp_path: Path) -> None:
    list_file = tmp_path / "list.json"
    list_file.write_text(json.dumps([{"event_id": "e1"}]), encoding="utf-8")

    source = _make_source(str(list_file.relative_to(tmp_path)))
    with pytest.raises(RuntimeError, match="top-level JSON object"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_missing_items_key(tmp_path: Path) -> None:
    batch_file = tmp_path / "no_items.json"
    batch_file.write_text(json.dumps({"period": "2026-05"}), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)))
    with pytest.raises(RuntimeError, match="'items' as a list"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_respects_max_items(tmp_path: Path) -> None:
    batch = {
        "period": "2026-05",
        "items": [{"event_id": f"e{i}", "case_type": "new_lead"} for i in range(10)],
    }
    batch_file = tmp_path / "big.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)), items_max=3)
    events, metadata = load_json_batch(
        source=source,
        project_root=tmp_path,
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
    )

    assert len(events) == 3
    assert metadata["loaded_item_count"] == 3
    assert metadata["raw_item_count"] == 10
    assert metadata["items_max"] == 3


def test_load_json_batch_skips_non_dict_items(tmp_path: Path) -> None:
    batch = {
        "period": "2026-05",
        "items": [{"event_id": "e1"}, "bad_item", None, {"event_id": "e2"}],
    }
    batch_file = tmp_path / "mixed.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)))
    events, metadata = load_json_batch(
        source=source,
        project_root=tmp_path,
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
    )

    assert len(events) == 2
    assert metadata["loaded_item_count"] == 2


def test_load_json_batch_empty_path_raises(tmp_path: Path) -> None:
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "source_role": "batch_sample",
        "client_id": "welding",
        "display_name": "Test Batch Source",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
        "batch": {"path": "", "period": "2026-05"},
    }
    with pytest.raises(RuntimeError, match="batch.path is empty"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_raises_when_items_max_missing(tmp_path: Path) -> None:
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "source_role": "batch_sample",
        "client_id": "welding",
        "display_name": "Test Batch Source",
        "enabled": True,
        "authority": "read_only",
        "batch": {"path": "any.json", "period": "2026-05"},
    }
    with pytest.raises(RuntimeError, match="items_max must be int > 0"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_raises_when_batch_missing(tmp_path: Path) -> None:
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "source_role": "batch_sample",
        "client_id": "welding",
        "display_name": "Test Batch Source",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
    }
    with pytest.raises(RuntimeError, match="batch must be a mapping"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_raises_when_batch_period_missing(tmp_path: Path) -> None:
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(
        '{"period": "2026-05", "items": [{"event_id": "e1"}]}', encoding="utf-8"
    )
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "source_role": "batch_sample",
        "client_id": "welding",
        "display_name": "Test Batch Source",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
        "batch": {"path": str(batch_file.relative_to(tmp_path)), "period": ""},
    }
    with pytest.raises(RuntimeError, match="batch.period is empty"):
        load_json_batch(
            source=source,
            project_root=tmp_path,
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        )


def test_load_json_batch_body_preview_respects_configured_body_chars_max(
    tmp_path: Path,
) -> None:
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e1",
                "body": "A" * 80,
            }
        ],
    }
    batch_file = tmp_path / "preview.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    events, _metadata = load_json_batch(
        source=_make_source(str(batch_file.relative_to(tmp_path))),
        project_root=tmp_path,
        logger=_null_logger(),
        email_preview_body_chars_max=32,
    )

    assert events[0]["body_preview"] == "A" * 32
    assert events[0]["body_preview_chars"] == 32
    assert events[0]["body_preview_truncated"] is True


def test_load_json_batch_bounds_existing_body_preview(tmp_path: Path) -> None:
    batch_file = tmp_path / "batch_existing_preview.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "preview-only",
                        "sender": "lead@example.com",
                        "subject": "Preview only",
                        "body_preview": "<script>bad()</script>" + ("B" * 260),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    source = {
        "source_id": "test-preview-only",
        "source_type": "json_batch",
        "source_role": "batch_sample",
        "client_id": "welding",
        "display_name": "Preview Only",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
        "batch": {
            "path": str(batch_file.relative_to(tmp_path)),
            "period": "2026-05",
        },
    }

    events, _metadata = load_json_batch(
        source=source,
        project_root=tmp_path,
        logger=_null_logger(),
        email_preview_body_chars_max=50,
    )

    assert len(events) == 1
    assert events[0]["body_preview"] == "B" * 50
    assert events[0]["body_preview_chars"] == 50
    assert events[0]["body_preview_truncated"] is True
    assert events[0]["body_preview_source"] == "existing"
    assert "<script" not in events[0]["body_preview"]
    assert "bad()" not in events[0]["body_preview"]


class _FakeMailboxClient:
    def __init__(
        self, messages: list[bytes] | None = None, error: Exception | None = None
    ):
        self._messages = messages or []
        self._error = error

    def fetch_latest(self, folder: str, items_max: int) -> list[bytes]:
        assert folder == "INBOX"
        assert items_max > 0
        if self._error is not None:
            raise self._error
        return self._messages[:items_max]


def _mailbox_source(items_max: int = 10) -> dict:
    return {
        "source_id": "hotline",
        "source_type": "mailbox_readonly",
        "source_role": "technical_aggregator",
        "client_id": "welding",
        "display_name": "Hotline mailbox",
        "enabled": True,
        "authority": "read_only",
        "items_max": items_max,
        "mailbox": {
            "host": "imap.example.com",
            "port": 993,
            "use_ssl": True,
            "folder": "INBOX",
            "username_env": "ROP_MAILBOX_USERNAME",
            "password_env": "ROP_MAIL_BOX_PASSWORD",
        },
    }


def test_load_mailbox_readonly_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
    raw_message = b"From: Sender <lead@example.com>\nTo: hotline@example.com\nCc: cc@example.com\nSubject: Need welding help\nDate: Thu, 08 May 2026 10:30:00 +0000\nMessage-ID: <mail-1@example.com>\nContent-Type: multipart/mixed; boundary=sep\n\n--sep\nContent-Type: text/plain; charset=utf-8\n\nNeed hotline callback.\n--sep\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=brief.pdf\n\nPDFDATA\n--sep--\n"

    events, metadata, diagnostics = load_mailbox_readonly(
        source=_mailbox_source(),
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
    )

    assert len(events) == 1
    assert events[0]["body_preview"] == "Need hotline callback."
    assert events[0]["body_preview_chars"] == len("Need hotline callback.")
    assert events[0]["body_preview_truncated"] is False
    assert events[0]["body_preview_source"] == "text_plain"
    assert events[0]["message_id"] == "<mail-1@example.com>"
    assert events[0]["sender"] == "lead@example.com"
    assert events[0]["to"] == ["hotline@example.com"]
    assert events[0]["cc"] == ["cc@example.com"]
    assert events[0]["attachments"][0]["filename"] == "brief.pdf"
    assert metadata["source_type"] == "mailbox_readonly"
    assert metadata["source_role"] == "technical_aggregator"
    assert metadata["client_id"] == "welding"
    assert metadata["source_display_name"] == "Hotline mailbox"
    assert metadata["loaded_item_count"] == 1
    assert metadata["period"] == "2026-05"
    assert diagnostics["status"] == "ok"
    assert diagnostics["processed_count"] == 1
    assert diagnostics["loaded_count"] == 1


def test_load_mailbox_readonly_missing_credentials_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROP_MAILBOX_USERNAME", raising=False)
    monkeypatch.delenv("ROP_MAIL_BOX_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="credentials missing") as exc_info:
        load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([]),
        )

    exc = exc_info.value
    assert getattr(exc, "diagnostics")["reason"] == "missing_credentials"


def test_load_mailbox_readonly_skips_malformed_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")

    malformed = b"bad-mail-without-headers"
    valid = b"From: lead@example.com\nTo: hotline@example.com\nSubject: Hello\nMessage-ID: <mail-2@example.com>\nContent-Type: text/plain; charset=utf-8\n\nHello"

    events, _metadata, diagnostics = load_mailbox_readonly(
        source=_mailbox_source(items_max=5),
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        mailbox_client_factory=lambda _source: _FakeMailboxClient([malformed, valid]),
    )

    assert len(events) == 1
    assert events[0]["message_id"] == "<mail-2@example.com>"
    assert diagnostics["malformed_count"] == 1
    assert diagnostics["skipped_count"] == 1


def test_load_mailbox_readonly_bounds_and_strips_html_body_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")

    long_html = (
        "<html><body><script>bad()</script><p>" + ("A" * 260) + "</p></body></html>"
    )
    raw_message = (
        "From: lead@example.com\n"
        "To: hotline@example.com\n"
        "Subject: HTML body\n"
        "Message-ID: <mail-html@example.com>\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        f"{long_html}"
    ).encode("utf-8")

    events, _metadata, _diagnostics = load_mailbox_readonly(
        source=_mailbox_source(),
        logger=_null_logger(),
        email_preview_body_chars_max=50,
        mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
    )

    assert len(events) == 1
    assert events[0]["body_preview"] == "A" * 50
    assert events[0]["body_preview_chars"] == 50
    assert events[0]["body_preview_truncated"] is True
    assert events[0]["body_preview_source"] == "html_text"
    assert "<script" not in events[0]["body_preview"]
    assert "bad()" not in events[0]["body_preview"]
    assert "<p>" not in events[0]["body_preview"]


def test_load_rop_source_dispatches_mailbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
    message = b"From: lead@example.com\nTo: hotline@example.com\nSubject: Hello\nMessage-ID: <mail-3@example.com>\nContent-Type: text/plain; charset=utf-8\n\nHello"

    events, metadata, diagnostics = load_rop_source(
        source=_mailbox_source(),
        project_root=Path.cwd(),
        logger=_null_logger(),
        email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
        mailbox_client_factory=lambda _source: _FakeMailboxClient([message]),
    )

    assert len(events) == 1
    assert metadata["source_type"] == "mailbox_readonly"
    assert diagnostics["source_type"] == "mailbox_readonly"


class TestCleanSubject:
    def test_strips_auto_fwd_prefix(self) -> None:
        result = _extract_clean_subject(
            "[AUTO-FWD] OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_fwd_prefix(self) -> None:
        result = _extract_clean_subject(
            "FWD: OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_fw_prefix(self) -> None:
        result = _extract_clean_subject(
            "FW: OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_re_prefix(self) -> None:
        result = _extract_clean_subject(
            "RE: OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_spam_prefix(self) -> None:
        result = _extract_clean_subject(
            "*** SPAM *** OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_all_prefixes_combined(self) -> None:
        result = _extract_clean_subject(
            "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_auto_fwd_colon_variant(self) -> None:
        result = _extract_clean_subject(
            "AUTO-FWD: OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_strips_repeated_prefixes(self) -> None:
        result = _extract_clean_subject(
            "FWD: FWD: RE: OEM submerged-arc welding machine supplied"
        )
        assert result == "OEM submerged-arc welding machine supplied"

    def test_preserves_original_subject_when_no_prefixes(self) -> None:
        result = _extract_clean_subject("OEM submerged-arc welding machine supplied")
        assert result == "OEM submerged-arc welding machine supplied"

    def test_empty_subject_returns_empty(self) -> None:
        assert _extract_clean_subject("") == ""
        assert _extract_clean_subject("   ") == ""

    def test_none_subject_returns_empty(self) -> None:
        assert _extract_clean_subject(None) == ""


class TestTransportLabels:
    def test_extracts_auto_fwd_label(self) -> None:
        labels = _extract_transport_labels(
            "[AUTO-FWD] OEM submerged-arc welding machine supplied"
        )
        assert "auto_fwd" in labels

    def test_extracts_multiple_labels(self) -> None:
        labels = _extract_transport_labels(
            "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied"
        )
        assert "auto_fwd" in labels
        assert "fwd" in labels
        assert "spam" in labels

    def test_extracts_re_label(self) -> None:
        labels = _extract_transport_labels(
            "RE: OEM submerged-arc welding machine supplied"
        )
        assert "re" in labels

    def test_empty_subject_returns_empty_labels(self) -> None:
        assert _extract_transport_labels("") == []
        assert _extract_transport_labels("   ") == []

    def test_no_transport_labels_for_clean_subject(self) -> None:
        labels = _extract_transport_labels("OEM submerged-arc welding machine supplied")
        assert labels == []

    def test_labels_are_deduplicated(self) -> None:
        labels = _extract_transport_labels("[AUTO-FWD] AUTO-FWD: test")
        assert labels.count("auto_fwd") == 1

    def test_does_not_extract_re_from_middle_of_business_subject(self) -> None:
        labels = _extract_transport_labels("Certification RE: ISO 9001 update")
        assert labels == []


class TestForwardedWrapperExtraction:
    def test_single_email_line_does_not_create_forwarded_wrapper(self) -> None:
        body = "Email: gina.shi@morrowwelding.com\nSome other text"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is False
        assert fields["form_email"] == ""
        assert fields["original_sender"] == ""

    def test_extracts_original_recipient(self) -> None:
        body = "\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u0434\u0440\u0435\u0441 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f: online@welding.kz\nmore"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is False
        assert fields["original_recipient"] == ""

    def test_single_date_line_does_not_create_forwarded_wrapper(self) -> None:
        body = "\u0414\u0430\u0442\u0430: Tue, 9 Jun 2026 11:54:27 +0800\nmore text"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is False
        assert fields["original_message_date"] == ""
        assert fields["date_source"] == ""

    def test_single_x_email_id_line_does_not_create_forwarded_wrapper(self) -> None:
        body = "X-Email-ID: bounded-id-12345\nmore"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is False
        assert fields["x_email_id"] == ""

    def test_extracts_all_fields_together(self) -> None:
        body = (
            "--- Original Message ---\n"
            "Email: gina.shi@morrowwelding.com\n"
            "\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u0434\u0440\u0435\u0441 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f: online@welding.kz\n"
            "\u0414\u0430\u0442\u0430: Tue, 9 Jun 2026 11:54:27 +0800\n"
            "X-Email-ID: bounded-id-12345\n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["form_email"] == "gina.shi@morrowwelding.com"
        assert fields["original_sender"] == "gina.shi@morrowwelding.com"
        assert fields["original_sender_email"] == "gina.shi@morrowwelding.com"
        assert fields["original_recipient"] == "online@welding.kz"
        assert fields["original_message_date"] == "2026-06-09T03:54:27+00:00"
        assert fields["date_source"] == "original_forwarded_date"
        assert fields["x_email_id"] == "bounded-id-12345"
        assert fields["forwarded_wrapper"] is True

    def test_empty_body_returns_defaults(self) -> None:
        fields = _extract_forwarded_wrapper_fields("")
        assert fields["forwarded_wrapper"] is False
        assert fields["form_email"] == ""
        assert fields["original_sender"] == ""
        assert fields["original_sender_email"] == ""
        assert fields["date_source"] == ""

    def test_malformed_date_degrades_gracefully(self) -> None:
        body = "Дата: not-a-real-date-at-all\nmore"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["original_message_date"] == ""
        assert fields["date_source"] == ""
        assert fields["forwarded_wrapper"] is False

    def test_no_forwarded_wrapper_for_plain_body(self) -> None:
        body = "Just a normal email body without any forwarded markers"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is False

    def test_forwarded_marker_detected(self) -> None:
        body = "--- Forwarded Message ---\nEmail: test@example.com"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is True
        assert fields["form_email"] == "test@example.com"
        assert fields["original_sender"] == "test@example.com"
        assert fields["original_sender_email"] == "test@example.com"

    def test_two_extracted_fields_create_forwarded_wrapper_without_marker(self) -> None:
        body = (
            "Email: gina.shi@morrowwelding.com\n"
            "\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u0434\u0440\u0435\u0441 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f: online@welding.kz\n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is True
        assert fields["form_email"] == "gina.shi@morrowwelding.com"
        assert fields["original_sender"] == "gina.shi@morrowwelding.com"
        assert fields["original_sender_email"] == "gina.shi@morrowwelding.com"
        assert fields["original_recipient"] == "online@welding.kz"


class TestSanitizeBatchItemNormalization:
    def test_computes_clean_subject_for_batch_item(self) -> None:
        item = {
            "event_id": "e1",
            "subject": "[AUTO-FWD] FWD: *** SPAM *** OEM welding machine",
            "sender": "test@example.com",
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["clean_subject"] == "OEM welding machine"
        assert result["transport_labels"] == ["auto_fwd", "fwd", "spam"]
        assert result["spam_label_present"] is True
        assert result["reply_label_present"] is False
        assert result["forwarded_wrapper"] is False

    def test_normalization_fields_default_for_batch_item_without_subject(self) -> None:
        item = {"event_id": "e1", "sender": "test@example.com"}
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["clean_subject"] == ""
        assert result["transport_labels"] == []
        assert result["spam_label_present"] is False
        assert result["reply_label_present"] is False

    def test_normalizes_invalid_transport_labels_from_input(self) -> None:
        item = {
            "event_id": "e1",
            "subject": "FWD: Test",
            "transport_labels": [123, "custom", "re"],
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["transport_labels"] == ["re"]

    def test_computes_transport_labels_from_subject_when_provided_labels_are_invalid(
        self,
    ) -> None:
        item = {
            "event_id": "e1",
            "subject": "FWD: Test",
            "transport_labels": ["custom", "unknown"],
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["transport_labels"] == ["fwd"]

    def test_preserves_existing_valid_transport_labels(self) -> None:
        item = {
            "event_id": "e1",
            "subject": "FWD: Test",
            "clean_subject": "Already cleaned",
            "transport_labels": ["fwd"],
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["clean_subject"] == "Already cleaned"
        assert result["transport_labels"] == ["fwd"]

    def test_computes_missing_transport_fields_when_clean_subject_exists(self) -> None:
        item = {
            "event_id": "e1",
            "subject": "FWD: RE: Test",
            "clean_subject": "Already cleaned",
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["clean_subject"] == "Already cleaned"
        assert result["transport_labels"] == ["fwd", "re"]
        assert result["spam_label_present"] is False
        assert result["reply_label_present"] is True

    def test_extracts_missing_forwarded_wrapper_fields_from_batch_body(self) -> None:
        item = {
            "event_id": "e1",
            "sender": "wrapper@example.com",
            "subject": "FWD: Test",
            "body": (
                "--- Original Message ---\n"
                "Email: gina.shi@morrowwelding.com\n"
                "Оригинальный адрес получения: online@welding.kz\n"
                "Дата: Tue, 9 Jun 2026 11:54:27 +0800\n"
                "X-Email-ID: bounded-id-12345\n"
            ),
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["forwarded_wrapper"] is True
        assert result["form_email"] == "gina.shi@morrowwelding.com"
        assert result["original_sender"] == "gina.shi@morrowwelding.com"
        assert result["original_sender_email"] == "gina.shi@morrowwelding.com"
        assert result["original_recipient"] == "online@welding.kz"
        assert result["original_message_date"] == "2026-06-09T03:54:27+00:00"
        assert result["date_source"] == "original_forwarded_date"
        assert result["x_email_id"] == "bounded-id-12345"

    def test_does_not_extract_forwarded_wrapper_fields_outside_bound(self) -> None:
        item = {
            "event_id": "e1",
            "sender": "wrapper@example.com",
            "subject": "FWD: Test",
            "body": (
                ("A" * 33) + "--- Original Message ---\n"
                "Email: gina.shi@morrowwelding.com\n"
                "Оригинальный адрес получения: online@welding.kz\n"
                "Дата: Tue, 9 Jun 2026 11:54:27 +0800\n"
                "X-Email-ID: bounded-id-12345\n"
            ),
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=32)
        assert result["forwarded_wrapper"] is False
        assert result["form_email"] == ""
        assert result["original_sender"] == ""
        assert result["original_sender_email"] == ""
        assert result["original_recipient"] == ""
        assert result["original_message_date"] == ""
        assert result["date_source"] == "fallback_order"
        assert result["date"] == ""
        assert result["received_at"] is None
        assert result["_date_fallback"] is True
        assert result["x_email_id"] == ""

    def test_extracts_forwarded_wrapper_fields_inside_bound(self) -> None:
        item = {
            "event_id": "e1",
            "sender": "wrapper@example.com",
            "subject": "FWD: Test",
            "body": (
                "--- Original Message ---\n"
                "Email: gina.shi@morrowwelding.com\n"
                "Оригинальный адрес получения: online@welding.kz\n"
                "Дата: Tue, 9 Jun 2026 11:54:27 +0800\n"
                "X-Email-ID: bounded-id-12345\n" + ("A" * 200)
            ),
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=200)
        assert result["forwarded_wrapper"] is True
        assert result["form_email"] == "gina.shi@morrowwelding.com"
        assert result["original_sender"] == "gina.shi@morrowwelding.com"
        assert result["original_sender_email"] == "gina.shi@morrowwelding.com"
        assert result["original_recipient"] == "online@welding.kz"
        assert result["original_message_date"] == "2026-06-09T03:54:27+00:00"
        assert result["date_source"] == "original_forwarded_date"
        assert result["date"] == result["original_message_date"]
        assert result["received_at"] is None
        assert result["_date_fallback"] is False
        assert result["x_email_id"] == "bounded-id-12345"

    def test_original_date_normalizes_empty_received_at_to_none(self) -> None:
        item = {
            "event_id": "e1",
            "subject": "FWD: Test",
            "original_message_date": "2026-06-09T04:55:46+00:00",
            "date_source": "original_forwarded_date",
            "received_at": "",
        }

        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)

        assert result["date"] == "2026-06-09T04:55:46+00:00"
        assert result["received_at"] is None
        assert result["date_source"] == "original_forwarded_date"
        assert result["_date_fallback"] is False


class TestNormalizedEventFields:
    def test_normalized_event_contains_new_fields(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: wrapper@example.com\n"
            "To: hotline@example.com\n"
            "Subject: [AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied\n"
            "Date: Thu, 08 May 2026 10:30:00 +0000\n"
            "Message-ID: <mail-spam@example.com>\n"
            "Content-Type: text/plain; charset=utf-8\n"
            "\n"
            "--- Original Message ---\n"
            "Email: gina.shi@morrowwelding.com\n"
            "\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u0434\u0440\u0435\u0441 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f: online@welding.kz\n"
            "\u0414\u0430\u0442\u0430: Tue, 9 Jun 2026 11:54:27 +0800\n"
            "X-Email-ID: bounded-id-12345\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        assert len(events) == 1
        evt = events[0]
        assert evt["subject"] == (
            "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied"
        )
        assert evt["clean_subject"] == "OEM submerged-arc welding machine supplied"
        assert evt["transport_labels"] == ["auto_fwd", "fwd", "spam"]
        assert evt["spam_label_present"] is True
        assert evt["reply_label_present"] is False
        assert evt["forwarded_wrapper"] is True
        assert evt["form_email"] == "gina.shi@morrowwelding.com"
        assert evt["original_sender"] == "gina.shi@morrowwelding.com"
        assert evt["original_sender_email"] == "gina.shi@morrowwelding.com"
        assert evt["original_recipient"] == "online@welding.kz"
        assert evt["original_message_date"] == "2026-06-09T03:54:27+00:00"
        assert evt["received_at"] == "2026-05-08T10:30:00+00:00"
        assert evt["date"] == evt["original_message_date"]
        assert evt["date_source"] == "original_forwarded_date"
        assert evt["_date_fallback"] is False
        assert evt["x_email_id"] == "bounded-id-12345"

    def test_normalized_event_uses_mailbox_header_date_without_forwarded_original(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: test@example.com\n"
            "To: hotline@example.com\n"
            "Subject: RE: Simple reply\n"
            "Date: Thu, 08 May 2026 10:30:00 +0000\n"
            "Message-ID: <reply@example.com>\n"
            "Content-Type: text/plain\n"
            "\n"
            "Just a reply\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        evt = events[0]
        assert evt["date"] == "2026-05-08T10:30:00+00:00"
        assert evt["received_at"] == "2026-05-08T10:30:00+00:00"
        assert evt["date_source"] == "mailbox_header"
        assert evt["_date_fallback"] is False

    def test_normalized_event_prefers_forwarded_date_and_keeps_missing_mailbox_date_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: wrapper@example.com\n"
            "To: hotline@example.com\n"
            "Subject: [AUTO-FWD] FWD: OEM submerged-arc welding machine supplied\n"
            "Date: invalid mailbox date\n"
            "Message-ID: <mail-invalid-date@example.com>\n"
            "Content-Type: text/plain; charset=utf-8\n"
            "\n"
            "--- Original Message ---\n"
            "Email: gina.shi@morrowwelding.com\n"
            "\u041e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u044c\u043d\u044b\u0439 \u0430\u0434\u0440\u0435\u0441 \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f: online@welding.kz\n"
            "\u0414\u0430\u0442\u0430: Tue, 9 Jun 2026 12:55:46 +0800\n"
            "X-Email-ID: bounded-id-invalid-date\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        assert len(events) == 1
        evt = events[0]
        assert evt["original_message_date"] == "2026-06-09T04:55:46+00:00"
        assert evt["date"] == evt["original_message_date"]
        assert evt["date_source"] == "original_forwarded_date"
        assert evt["received_at"] is None
        assert evt["_date_fallback"] is False
        assert evt["form_email"] == "gina.shi@morrowwelding.com"
        assert evt["original_sender"] == "gina.shi@morrowwelding.com"
        assert evt["original_sender_email"] == "gina.shi@morrowwelding.com"

    def test_normalized_event_date_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: test@example.com\n"
            "To: hotline@example.com\n"
            "Subject: No date header\n"
            "Message-ID: <no-date@example.com>\n"
            "Content-Type: text/plain\n"
            "\n"
            "Simple body\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        assert len(events) == 1
        evt = events[0]
        assert evt["date"] == ""
        assert evt["received_at"] is None
        assert evt["_date_fallback"] is True
        assert evt["date_source"] == "fallback_order"

    def test_normalized_event_clean_body_without_forwarded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: test@example.com\n"
            "To: hotline@example.com\n"
            "Subject: RE: Simple reply\n"
            "Date: Thu, 08 May 2026 10:30:00 +0000\n"
            "Message-ID: <reply@example.com>\n"
            "Content-Type: text/plain\n"
            "\n"
            "Just a reply\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        evt = events[0]
        assert evt["clean_subject"] == "Simple reply"
        assert evt["reply_label_present"] is True
        assert evt["spam_label_present"] is False
        assert evt["forwarded_wrapper"] is False
        assert evt["date"] == evt["received_at"]
        assert evt["date_source"] == "mailbox_header"


class TestNoRawEmlNoAttachmentNoSecrets:
    def test_blocked_keys_not_in_normalized_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: test@example.com\n"
            "To: hotline@example.com\n"
            "Subject: Test\n"
            "Date: Thu, 08 May 2026 10:30:00 +0000\n"
            "Message-ID: <test@example.com>\n"
            "Content-Type: multipart/mixed; boundary=sep\n"
            "\n"
            "--sep\n"
            "Content-Type: text/plain\n"
            "\n"
            "body\n"
            "--sep\n"
            "Content-Type: message/rfc822\n"
            "Content-Disposition: attachment; filename=nested.eml\n"
            "\n"
            "nested data\n"
            "--sep--\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        assert len(events) == 1
        evt = events[0]
        blocked_keys = {
            "raw_eml",
            "raw_message",
            "attachment_content",
            "content",
            "content_bytes",
            "payload_bytes",
        }
        for key in blocked_keys:
            assert key not in evt, f"blocked key {key} found in normalized event"

        attachments = evt.get("attachments", [])
        filenames = [att.get("filename", "") for att in attachments]
        content_types = [att.get("content_type", "") for att in attachments]
        assert "nested.eml" not in filenames
        assert "message/rfc822" not in content_types

    def test_no_secrets_in_normalized_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
        monkeypatch.setenv("ROP_MAIL_BOX_PASSWORD", "secret")
        raw_message = (
            "From: test@example.com\n"
            "To: hotline@example.com\n"
            "Subject: Test\n"
            "Date: Thu, 08 May 2026 10:30:00 +0000\n"
            "Message-ID: <test@example.com>\n"
            "Content-Type: text/plain\n"
            "\n"
            "normal body\n"
        ).encode("utf-8")

        events, _metadata, _diagnostics = load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            email_preview_body_chars_max=EMAIL_PREVIEW_BODY_CHARS_MAX,
            mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
        )

        evt = events[0]
        evt_json = json.dumps(evt)
        assert "secret" not in evt_json.lower()
        assert "BITRIX_WEBHOOK" not in evt_json


class TestIt33ForwardedWrapperSeparation:
    def test_email_does_not_override_original_sender(self) -> None:
        body = (
            "Email: galina.okruzhko@welding.kz\n"
            "Оригинальный отправитель: WARUITE <dawson_yude@163.com>\n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["form_email"] == "galina.okruzhko@welding.kz"
        assert fields["original_sender"] == "WARUITE <dawson_yude@163.com>"
        assert fields["original_sender_email"] == "dawson_yude@163.com"

    def test_dawson_like_forwarded_wrapper(self) -> None:
        body = (
            "--- Original Message ---\n"
            "Email: galina.okruzhko@welding.kz\n"
            "Оригинальный отправитель: WARUITE <dawson_yude@163.com>\n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["form_email"] == "galina.okruzhko@welding.kz"
        assert fields["original_sender"] == "WARUITE <dawson_yude@163.com>"
        assert fields["original_sender_email"] == "dawson_yude@163.com"
        assert fields["forwarded_wrapper"] is True

    def test_usova_like_forwarded_wrapper(self) -> None:
        body = (
            "--- Original Message ---\n"
            "Email: ekaterina.astanina@welding.kz\n"
            "Оригинальный отправитель: Усова Анна Николаевна <usova@mir-svarki.ru>\n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["form_email"] == "ekaterina.astanina@welding.kz"
        assert "Усова Анна Николаевна" in fields["original_sender"]
        assert fields["original_sender_email"] == "usova@mir-svarki.ru"
        assert fields["forwarded_wrapper"] is True

    def test_fallback_form_email_to_original_sender(self) -> None:
        body = (
            "--- Original Message ---\n"
            "Email: galina.okruzhko@welding.kz\n"
            "Оригинальный адрес получения: online@welding.kz\n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["form_email"] == "galina.okruzhko@welding.kz"
        assert fields["original_sender"] == "galina.okruzhko@welding.kz"
        assert fields["original_sender_email"] == "galina.okruzhko@welding.kz"
        assert fields["forwarded_wrapper"] is True

    def test_weak_evidence_single_email_only(self) -> None:
        body = "Email: galina.okruzhko@welding.kz\nSome other text"
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is False
        assert fields["form_email"] == ""
        assert fields["original_sender"] == ""
        assert fields["original_sender_email"] == ""

    def test_malformed_original_sender_no_crash(self) -> None:
        body = (
            "--- Original Message ---\n"
            "Email: test@example.com\n"
            "Оригинальный отправитель: \n"
        )
        fields = _extract_forwarded_wrapper_fields(body)
        assert fields["forwarded_wrapper"] is True
        assert fields["form_email"] == "test@example.com"
        assert fields["original_sender"] == "test@example.com"
        assert fields["original_sender_email"] == "test@example.com"

    def test_no_crash_on_invalid_email_in_sender(self) -> None:
        fields = _extract_forwarded_wrapper_fields(
            "--- Forwarded Message ---\n"
            "Email: x@y\n"
            "Оригинальный отправитель: just text without email\n"
        )
        assert fields["forwarded_wrapper"] is True
        assert fields["original_sender_email"] == ""


class TestIt33BatchSanitization:
    def test_fills_form_email_from_forwarded_body(self) -> None:
        item = {
            "event_id": "e1",
            "sender": "wrapper@example.com",
            "subject": "FWD: Test",
            "body": (
                "--- Original Message ---\n"
                "Email: galina.okruzhko@welding.kz\n"
                "Оригинальный отправитель: WARUITE <dawson_yude@163.com>\n"
            ),
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["form_email"] == "galina.okruzhko@welding.kz"
        assert result["original_sender"] == "WARUITE <dawson_yude@163.com>"
        assert result["original_sender_email"] == "dawson_yude@163.com"

    def test_preserves_valid_pre_normalized_values(self) -> None:
        item = {
            "event_id": "e1",
            "sender": "wrapper@example.com",
            "subject": "FWD: Test",
            "body": "Email: wrong@example.com\n",
            "form_email": "prefilled@example.com",
            "original_sender": "Prefilled <prefilled@example.com>",
            "original_sender_email": "prefilled@example.com",
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert result["form_email"] == "prefilled@example.com"
        assert result["original_sender"] == "Prefilled <prefilled@example.com>"
        assert result["original_sender_email"] == "prefilled@example.com"

    def test_no_blocked_keys_leak(self) -> None:
        item = {
            "event_id": "e1",
            "raw_eml": "should not be here",
            "attachment_content": "nope",
            "content_bytes": "no",
        }
        result = _sanitize_batch_item(item, email_preview_body_chars_max=4000)
        assert "raw_eml" not in result
        assert "attachment_content" not in result
        assert "content_bytes" not in result
