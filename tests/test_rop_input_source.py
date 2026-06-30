from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from beeagent_module.core.input_source import (
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
            "password_env": "ROP_MAILBOX_PASSWORD",
        },
    }


def test_load_mailbox_readonly_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
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
    monkeypatch.delenv("ROP_MAILBOX_PASSWORD", raising=False)

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
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")

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
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")

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
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
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
