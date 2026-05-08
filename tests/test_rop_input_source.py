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
)


# Тесты для core.input_source: проверка логики выбора активного источника и загрузки batch-файла из json_batch источника
def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_input_source_null")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Тест: find_active_rop_source: проверка выбора единственного enabled источника, ошибки при отсутствии источников, отсутствии enabled, множестве enabled
def test_find_active_source_returns_single_enabled() -> None:
    sources = [
        {"source_id": "s1", "enabled": False},
        {"source_id": "s2", "enabled": True},
    ]
    result = find_active_rop_source(sources)
    assert result["source_id"] == "s2"


# Тест: find_active_rop_source: проверка ошибок при отсутствии источников, отсутствии enabled, множестве enabled
def test_find_active_source_raises_when_no_sources() -> None:
    with pytest.raises(RuntimeError, match="no input source declared"):
        find_active_rop_source([])


# Тест: find_active_rop_source: проверка ошибок при отсутствии enabled, множестве enabled
def test_find_active_source_raises_when_no_enabled_source() -> None:
    sources = [
        {"source_id": "s1", "enabled": False},
        {"source_id": "s2", "enabled": False},
    ]
    with pytest.raises(RuntimeError, match="no enabled source found"):
        find_active_rop_source(sources)


# Тест: find_active_rop_source: проверка ошибок при множестве enabled
def test_find_active_source_raises_when_multiple_enabled() -> None:
    sources = [
        {"source_id": "s1", "enabled": True},
        {"source_id": "s2", "enabled": True},
    ]
    with pytest.raises(RuntimeError, match="multiple enabled sources"):
        find_active_rop_source(sources)


# Тест: load_json_batch: проверка успешной загрузки, приоритета period из файла над config, ошибок при отсутствии файла, невалидном JSON, невалидной форме, применении max_items, фильтрации не-dict элементов
def _make_source(path: str, period: str = "2026-05", items_max: int = 100) -> dict:
    return {
        "source_id": "test-source",
        "source_type": "json_batch",
        "enabled": True,
        "authority": "read_only",
        "items_max": items_max,
        "batch": {
            "path": path,
            "period": period,
        },
    }


# Тест: load_json_batch: проверка успешной загрузки, приоритета period из файла над config
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
        source=source, project_root=tmp_path, logger=_null_logger()
    )

    assert len(events) == 2
    assert events[0]["event_id"] == "e1"
    assert metadata["period"] == "2026-04"
    assert metadata["source_id"] == "test-source"
    assert metadata["raw_item_count"] == 2
    assert metadata["loaded_item_count"] == 2


# Тест: load_json_batch: проверка приоритета period из файла над config
def test_load_json_batch_uses_config_period_when_file_has_none(tmp_path: Path) -> None:
    batch = {"items": [{"event_id": "e1", "case_type": "new_lead"}]}
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)), period="2026-05")
    _events, metadata = load_json_batch(
        source=source, project_root=tmp_path, logger=_null_logger()
    )
    assert metadata["period"] == "2026-05"


# Тест: load_json_batch: проверка ошибок при отсутствии файла, невалидном JSON, невалидной форме, применении max_items, фильтрации не-dict элементов
def test_load_json_batch_missing_file(tmp_path: Path) -> None:
    source = _make_source("storage/mock/nonexistent.json")
    with pytest.raises(RuntimeError, match="batch file not found"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: проверка ошибок при невалидном JSON
def test_load_json_batch_invalid_json(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {{", encoding="utf-8")

    source = _make_source(str(bad_file.relative_to(tmp_path)))
    with pytest.raises(RuntimeError, match="not valid JSON"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: проверка ошибок при невалидной форме (не dict), отсутствии 'items' как списка
def test_load_json_batch_invalid_shape_not_dict(tmp_path: Path) -> None:
    list_file = tmp_path / "list.json"
    list_file.write_text(json.dumps([{"event_id": "e1"}]), encoding="utf-8")

    source = _make_source(str(list_file.relative_to(tmp_path)))
    with pytest.raises(RuntimeError, match="top-level JSON object"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: проверка ошибок при невалидной форме (отсутствие 'items' как списка)
def test_load_json_batch_missing_items_key(tmp_path: Path) -> None:
    batch_file = tmp_path / "no_items.json"
    batch_file.write_text(json.dumps({"period": "2026-05"}), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)))
    with pytest.raises(RuntimeError, match="'items' as a list"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: проверка применения max_items
def test_load_json_batch_respects_max_items(tmp_path: Path) -> None:
    batch = {
        "period": "2026-05",
        "items": [{"event_id": f"e{i}", "case_type": "new_lead"} for i in range(10)],
    }
    batch_file = tmp_path / "big.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)), items_max=3)
    events, metadata = load_json_batch(
        source=source, project_root=tmp_path, logger=_null_logger()
    )

    assert len(events) == 3
    assert metadata["loaded_item_count"] == 3
    assert metadata["raw_item_count"] == 10
    assert metadata["items_max"] == 3


# Тест: load_json_batch: проверка фильтрации не-dict элементов
def test_load_json_batch_skips_non_dict_items(tmp_path: Path) -> None:
    batch = {
        "period": "2026-05",
        "items": [{"event_id": "e1"}, "bad_item", None, {"event_id": "e2"}],
    }
    batch_file = tmp_path / "mixed.json"
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    source = _make_source(str(batch_file.relative_to(tmp_path)))
    events, metadata = load_json_batch(
        source=source, project_root=tmp_path, logger=_null_logger()
    )

    assert len(events) == 2
    assert metadata["loaded_item_count"] == 2


# Тест: load_json_batch с пустым batch.path — проверка ошибки при отсутствии пути
def test_load_json_batch_empty_path_raises(tmp_path: Path) -> None:
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
        "batch": {"path": "", "period": "2026-05"},
    }
    with pytest.raises(RuntimeError, match="batch.path is empty"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: ошибка при отсутствии items_max (required contract)
def test_load_json_batch_raises_when_items_max_missing(tmp_path: Path) -> None:
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "enabled": True,
        "authority": "read_only",
        "batch": {"path": "any.json", "period": "2026-05"},
    }
    with pytest.raises(RuntimeError, match="items_max must be int > 0"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: ошибка при отсутствии batch mapping (required contract)
def test_load_json_batch_raises_when_batch_missing(tmp_path: Path) -> None:
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
    }
    with pytest.raises(RuntimeError, match="batch must be a mapping"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Тест: load_json_batch: ошибка при пустом batch.period (required contract)
def test_load_json_batch_raises_when_batch_period_missing(tmp_path: Path) -> None:
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(
        '{"period": "2026-05", "items": [{"event_id": "e1"}]}', encoding="utf-8"
    )
    source = {
        "source_id": "test",
        "source_type": "json_batch",
        "enabled": True,
        "authority": "read_only",
        "items_max": 10,
        "batch": {"path": str(batch_file.relative_to(tmp_path)), "period": ""},
    }
    with pytest.raises(RuntimeError, match="batch.period is empty"):
        load_json_batch(source=source, project_root=tmp_path, logger=_null_logger())


# Чек: загрузка настроек с источником mailbox_readonly и проверкой наличия полей username_env и password_env
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


# Чек: загрузка настроек с источником mailbox_readonly и проверкой наличия полей username_env и password_env
def _mailbox_source(items_max: int = 10) -> dict:
    return {
        "source_id": "hotline",
        "source_type": "mailbox_readonly",
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


# Чек: загрузка настроек с источником mailbox_readonly и проверкой наличия полей username_env и password_env
def test_load_mailbox_readonly_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
    raw_message = b"From: Sender <lead@example.com>\nTo: hotline@example.com\nCc: cc@example.com\nSubject: Need welding help\nDate: Thu, 08 May 2026 10:30:00 +0000\nMessage-ID: <mail-1@example.com>\nContent-Type: multipart/mixed; boundary=sep\n\n--sep\nContent-Type: text/plain; charset=utf-8\n\nNeed hotline callback.\n--sep\nContent-Type: application/pdf\nContent-Disposition: attachment; filename=brief.pdf\n\nPDFDATA\n--sep--\n"

    events, metadata, diagnostics = load_mailbox_readonly(
        source=_mailbox_source(),
        logger=_null_logger(),
        mailbox_client_factory=lambda _source: _FakeMailboxClient([raw_message]),
    )

    assert len(events) == 1
    assert events[0]["message_id"] == "<mail-1@example.com>"
    assert events[0]["sender"] == "lead@example.com"
    assert events[0]["to"] == ["hotline@example.com"]
    assert events[0]["cc"] == ["cc@example.com"]
    assert events[0]["attachments"][0]["filename"] == "brief.pdf"
    assert metadata["source_type"] == "mailbox_readonly"
    assert metadata["loaded_item_count"] == 1
    assert metadata["period"] == "2026-05"
    assert diagnostics["status"] == "ok"
    assert diagnostics["processed_count"] == 1


# Чек: загрузка настроек с источником mailbox_readonly и отсутствием полей username_env и password_env должна вызывать RuntimeError
def test_load_mailbox_readonly_missing_credentials_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROP_MAILBOX_USERNAME", raising=False)
    monkeypatch.delenv("ROP_MAILBOX_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="credentials missing") as exc_info:
        load_mailbox_readonly(
            source=_mailbox_source(),
            logger=_null_logger(),
            mailbox_client_factory=lambda _source: _FakeMailboxClient([]),
        )

    exc = exc_info.value
    assert getattr(exc, "diagnostics")["reason"] == "missing_credentials"


# Чек: загрузка настроек с источником mailbox_readonly и отсутствием полей username_env и password_env должна вызывать RuntimeError
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
        mailbox_client_factory=lambda _source: _FakeMailboxClient([malformed, valid]),
    )

    assert len(events) == 1
    assert events[0]["message_id"] == "<mail-2@example.com>"
    assert diagnostics["malformed_count"] == 1
    assert diagnostics["skipped_count"] == 1


# Чек: загрузка настроек с источником mailbox_readonly и отсутствием полей username_env и password_env должна вызывать RuntimeError
def test_load_rop_source_dispatches_mailbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
    message = b"From: lead@example.com\nTo: hotline@example.com\nSubject: Hello\nMessage-ID: <mail-3@example.com>\nContent-Type: text/plain; charset=utf-8\n\nHello"

    events, metadata, diagnostics = load_rop_source(
        source=_mailbox_source(),
        project_root=Path.cwd(),
        logger=_null_logger(),
        mailbox_client_factory=lambda _source: _FakeMailboxClient([message]),
    )

    assert len(events) == 1
    assert metadata["source_type"] == "mailbox_readonly"
    assert diagnostics["source_type"] == "mailbox_readonly"
