from __future__ import annotations

import json
import logging
import os
import sys
import types
from pathlib import Path

import pytest

from beeagent_module.cases.rop_operator import (
    _filter_event_for_module,
    run_rop_batch_case,
    run_rop_operator_case,
)
from beeagent_module.core.module_contract import (
    AuthorityLevel,
    ModuleContext,
    ModuleResult,
)
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.settings import load_settings

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN1_TOKEN", "test-admin1-token")
os.environ.setdefault("BEEAGENT_WEB_ADMIN2_TOKEN", "test-admin2-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_cases_rop_operator")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _demo_payload() -> dict[str, str]:
    return {
        "source": "email",
        "sender": "lead@example.com",
        "subject": "Need product details",
        "body": "Please share pricing and delivery terms.",
    }


def _attachment_settings() -> dict[str, object]:
    return {
        "enabled": True,
        "chars_max": 120,
        "size_max": 4096,
        "types": [
            "text/plain",
            "application/json",
        ],
    }


def _rop_registry_entry_from_settings() -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    entries = settings["modules"]["registry"]

    for item in entries:
        if item["id"] == "beeagent-rop":
            assert item["enabled"] is True
            return item

    raise AssertionError("modules.registry must contain enabled beeagent-rop")


def _make_fake_package(
    name: str,
    entry_attr: str,
    entry_value: object,
) -> types.ModuleType:
    pkg = types.ModuleType(name)
    setattr(pkg, entry_attr, entry_value)
    sys.modules[name] = pkg
    return pkg


def _remove_fake_package(name: str) -> None:
    sys.modules.pop(name, None)


def test_rop_operator_flow_success_with_installed_module(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_operator_case(
        settings=settings,
        storage_dir=tmp_path,
        logger=_null_logger(),
        registry=registry,
        payload=_demo_payload(),
        run_id="run-rop-operator-success",
        session_id="session-rop-operator-success",
    )

    assert result["run_id"] == "run-rop-operator-success"
    assert result["module_id"] == "beeagent-rop"
    assert result["case_type"] == "lead_classification"
    assert result["status"] == "ok"
    assert result["module_status"] == "ok"

    run_dir = tmp_path / "runs" / "run-rop-operator-success"
    operator_summary_path = run_dir / "operator_summary.json"
    module_result_path = run_dir / "module-beeagent-rop" / "module_result.json"

    assert operator_summary_path.exists()
    assert module_result_path.exists()

    operator_summary = json.loads(operator_summary_path.read_text(encoding="utf-8"))
    assert operator_summary["status"] == "ok"
    assert (
        "runs/run-rop-operator-success/module-beeagent-rop/module_result.json"
        in operator_summary["artifact_refs"]
    )
    assert (
        "runs/run-rop-operator-success/operator_summary.json"
        in operator_summary["artifact_refs"]
    )


def test_rop_operator_flow_degraded_when_module_missing(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    registry = ModuleRegistry(config=[], logger=_null_logger())

    result = run_rop_operator_case(
        settings=settings,
        storage_dir=tmp_path,
        logger=_null_logger(),
        registry=registry,
        payload=_demo_payload(),
        run_id="run-rop-operator-missing",
        session_id="session-rop-operator-missing",
    )

    assert result["run_id"] == "run-rop-operator-missing"
    assert result["status"] == "degraded"
    assert result["module_status"] == "error"
    assert "Module is not loaded or unknown" in result["summary"]

    operator_summary_path = (
        tmp_path / "runs" / "run-rop-operator-missing" / "operator_summary.json"
    )
    assert operator_summary_path.exists()


class _StubNonOkModule:
    @property
    def module_id(self) -> str:
        return "stub-non-ok"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.READ_ONLY

    def supported_case_types(self) -> list[str]:
        return ["lead_classification"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="not_implemented",
            summary="stub non-ok for degraded operator flow",
            data={},
        )


def test_rop_operator_flow_degraded_for_non_ok_module_status(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    pkg_name = "_test_stub_non_ok_pkg"
    entry_name = "StubNonOkModule"
    _make_fake_package(pkg_name, entry_name, _StubNonOkModule)

    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "stub-non-ok",
                    "package": pkg_name,
                    "entry": entry_name,
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_operator_case(
            settings=settings,
            storage_dir=tmp_path,
            logger=_null_logger(),
            registry=registry,
            module_id="stub-non-ok",
            payload=_demo_payload(),
            run_id="run-rop-operator-non-ok",
            session_id="session-rop-operator-non-ok",
        )

        assert result["status"] == "degraded"
        assert result["module_status"] == "not_implemented"

        module_result_path = (
            tmp_path
            / "runs"
            / "run-rop-operator-non-ok"
            / "module-stub-non-ok"
            / "module_result.json"
        )
        assert module_result_path.exists()
    finally:
        _remove_fake_package(pkg_name)


def test_rop_operator_raises_when_payload_is_none(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    registry = ModuleRegistry(config=[], logger=_null_logger())

    try:
        run_rop_operator_case(
            settings=settings,
            storage_dir=tmp_path,
            logger=_null_logger(),
            registry=registry,
            payload=None,
            run_id="run-rop-operator-no-payload",
            session_id="session-rop-operator-no-payload",
        )
        raise AssertionError("RuntimeError expected for missing payload")
    except RuntimeError as exc:
        assert str(exc) == "ROP operator payload is required"


def _make_batch_settings(batch_path: str, enabled: bool = True) -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": "test-batch",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Test Batch Source",
                "enabled": enabled,
                "authority": "read_only",
                "items_max": 50,
                "batch": {
                    "path": batch_path,
                    "period": "2026-05",
                },
            }
        ],
    }
    return settings


def _make_mailbox_settings(enabled: bool = True) -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": "hotline",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "client_id": "welding",
                "display_name": "Hotline mailbox",
                "enabled": enabled,
                "authority": "read_only",
                "items_max": 10,
                "mailbox": {
                    "host": "imap.example.com",
                    "port": 993,
                    "use_ssl": True,
                    "folder": "INBOX",
                    "username_env": "ROP_MAILBOX_USERNAME",
                    "password_env": "ROP_MAILBOX_PASSWORD",
                },
            }
        ],
    }
    return settings


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


def _write_sample_batch(directory: Path) -> Path:
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e1",
                "case_type": "new_lead",
                "priority": "high",
                "confidence": 0.9,
            },
            {
                "event_id": "e2",
                "case_type": "irrelevant",
                "priority": "low",
                "confidence": 0.8,
            },
        ],
    }
    path = directory / "test_batch.json"
    path.write_text(json.dumps(batch), encoding="utf-8")
    return path


def test_rop_batch_case_success_with_installed_module(tmp_path: Path) -> None:
    batch_path = _write_sample_batch(tmp_path)
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
    settings = _make_batch_settings(str(batch_path.relative_to(tmp_path)))

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-batch-success",
        session_id="session-rop-batch-success",
    )

    assert result["run_id"] == "run-rop-batch-success"
    assert result["module_id"] == "beeagent-rop"
    assert result["case_type"] == "rop_summary"
    assert result["status"] == "ok"
    assert result["module_status"] == "ok"

    run_dir = tmp_path / "runs" / "run-rop-batch-success"

    assert (run_dir / "intake_metadata.json").exists()
    assert (run_dir / "normalized_events.json").exists()
    assert (run_dir / "operator_summary.json").exists()

    intake = json.loads((run_dir / "intake_metadata.json").read_text(encoding="utf-8"))
    assert intake["source_id"] == "test-batch"
    assert intake["loaded_item_count"] == 2

    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    assert isinstance(normalized, list)
    assert len(normalized) == 2

    operator = json.loads(
        (run_dir / "operator_summary.json").read_text(encoding="utf-8")
    )
    assert operator["status"] == "ok"
    refs = operator["artifact_refs"]
    assert any("source_diagnostics.json" in r for r in refs)
    assert any("intake_metadata.json" in r for r in refs)
    assert any("normalized_events.json" in r for r in refs)
    assert any("operator_summary.json" in r for r in refs)

    source = operator["source"]
    assert source["source_id"] == "test-batch"
    assert source["source_type"] == "json_batch"
    assert source["source_role"] == "batch_sample"
    assert source["client_id"] == "welding"
    assert source["source_display_name"] == "Test Batch Source"
    assert source["loaded_item_count"] == 2
    assert source["fetched_count"] == 2
    assert source["loaded_count"] == 2
    assert source["malformed_count"] == 0
    assert source["items_max"] == 50


def test_rop_batch_case_degraded_no_enabled_source(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [],
    }

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        run_id="run-rop-batch-no-source",
        session_id="session-rop-batch-no-source",
    )

    assert result["status"] == "degraded"
    assert (
        "no input source" in result["summary"].lower()
        or "empty" in result["summary"].lower()
    )
    assert (
        tmp_path / "runs" / "run-rop-batch-no-source" / "operator_summary.json"
    ).exists()


def test_rop_batch_case_source_selection_error_writes_diagnostics(
    tmp_path: Path,
) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [],
    }

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        run_id="run-rop-source-selection-error",
        session_id="session-rop-source-selection-error",
    )

    assert result["status"] == "degraded"

    diagnostics_path = (
        tmp_path / "runs" / "run-rop-source-selection-error" / "source_diagnostics.json"
    )
    assert diagnostics_path.exists()

    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert diagnostics["status"] == "degraded"
    assert diagnostics["reason"] == "source_selection_error"
    assert isinstance(diagnostics.get("aggregate"), dict)
    assert diagnostics.get("sources") == []


def test_rop_batch_case_degraded_missing_batch_file(tmp_path: Path) -> None:
    settings = _make_batch_settings("storage/mock/nonexistent.json")

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        run_id="run-rop-batch-missing-file",
        session_id="session-rop-batch-missing-file",
    )

    assert result["status"] == "degraded"
    assert "not found" in result["summary"].lower()
    diagnostics = json.loads(
        (
            tmp_path / "runs" / "run-rop-batch-missing-file" / "source_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostics["status"] == "degraded"
    assert diagnostics["reason"] == "batch_file_not_found"
    assert diagnostics["source_id"] == "test-batch"
    assert diagnostics["source_type"] == "json_batch"
    assert diagnostics["source_role"] == "batch_sample"
    assert diagnostics["client_id"] == "welding"
    assert diagnostics["source_display_name"] == "Test Batch Source"
    assert diagnostics["authority"] == "read_only"
    assert diagnostics["items_max"] == 50

    operator_summary = json.loads(
        (
            tmp_path / "runs" / "run-rop-batch-missing-file" / "operator_summary.json"
        ).read_text(encoding="utf-8")
    )
    source = operator_summary["source"]
    assert source["source_id"] == "test-batch"
    assert source["source_type"] == "json_batch"
    assert source["source_role"] == "batch_sample"
    assert source["client_id"] == "welding"
    assert source["source_display_name"] == "Test Batch Source"
    assert source["authority"] == "read_only"
    assert source["items_max"] == 50
    assert source["status"] == "degraded"
    assert source["reason"] == "batch_file_not_found"


def test_rop_batch_case_degraded_missing_module(tmp_path: Path) -> None:
    batch_path = _write_sample_batch(tmp_path)
    settings = _make_batch_settings(str(batch_path.relative_to(tmp_path)))
    registry = ModuleRegistry(config=[], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-batch-no-module",
        session_id="session-rop-batch-no-module",
    )

    assert result["status"] == "degraded"
    assert (
        tmp_path / "runs" / "run-rop-batch-no-module" / "operator_summary.json"
    ).exists()


def test_rop_batch_case_mailbox_missing_credentials_degraded(tmp_path: Path) -> None:
    settings = _make_mailbox_settings()

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        run_id="run-rop-mailbox-missing-creds",
        session_id="session-rop-mailbox-missing-creds",
        mailbox_client_factory=lambda _source: _FakeMailboxClient([]),
    )

    assert result["status"] == "degraded"
    diagnostics = json.loads(
        (
            tmp_path
            / "runs"
            / "run-rop-mailbox-missing-creds"
            / "source_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostics["reason"] == "missing_credentials"


def test_rop_batch_case_mailbox_auth_failure_degraded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from beeagent_module.adapters.mailbox import MailboxAuthError

    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
    settings = _make_mailbox_settings()

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=ModuleRegistry(config=[], logger=_null_logger()),
        run_id="run-rop-mailbox-auth-failed",
        session_id="session-rop-mailbox-auth-failed",
        mailbox_client_factory=lambda _source: _FakeMailboxClient(
            error=MailboxAuthError("mailbox authentication failed")
        ),
    )

    assert result["status"] == "degraded"
    diagnostics = json.loads(
        (
            tmp_path
            / "runs"
            / "run-rop-mailbox-auth-failed"
            / "source_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostics["reason"] == "auth_failure"


def test_rop_batch_case_mailbox_unavailable_degraded(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from beeagent_module.adapters.mailbox import MailboxUnavailableError

    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
    settings = _make_mailbox_settings()

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=ModuleRegistry(config=[], logger=_null_logger()),
        run_id="run-rop-mailbox-unavailable",
        session_id="session-rop-mailbox-unavailable",
        mailbox_client_factory=lambda _source: _FakeMailboxClient(
            error=MailboxUnavailableError("mailbox connection failed")
        ),
    )

    assert result["status"] == "degraded"
    diagnostics = json.loads(
        (
            tmp_path
            / "runs"
            / "run-rop-mailbox-unavailable"
            / "source_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostics["reason"] == "mailbox_unavailable"


def test_rop_batch_case_mailbox_empty_inbox_ok(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
    settings = _make_mailbox_settings()
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-mailbox-empty",
        session_id="session-rop-mailbox-empty",
        mailbox_client_factory=lambda _source: _FakeMailboxClient([]),
    )

    assert result["status"] == "ok"
    operator = json.loads(
        (
            tmp_path / "runs" / "run-rop-mailbox-empty" / "operator_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert operator["source"]["loaded_item_count"] == 0
    diagnostics = json.loads(
        (
            tmp_path / "runs" / "run-rop-mailbox-empty" / "source_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostics["reason"] == "empty_inbox"


def test_rop_batch_case_mailbox_malformed_message_skipped(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROP_MAILBOX_USERNAME", "operator@example.com")
    monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "secret")
    settings = _make_mailbox_settings()
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
    malformed = b"broken"
    valid = b"From: lead@example.com\nTo: hotline@example.com\nSubject: Hello\nMessage-ID: <mail-4@example.com>\nContent-Type: text/plain; charset=utf-8\n\nHello"

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-mailbox-malformed",
        session_id="session-rop-mailbox-malformed",
        mailbox_client_factory=lambda _source: _FakeMailboxClient([malformed, valid]),
    )

    assert result["status"] == "ok"
    diagnostics = json.loads(
        (
            tmp_path / "runs" / "run-rop-mailbox-malformed" / "source_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert diagnostics["malformed_count"] == 1
    normalized = json.loads(
        (
            tmp_path / "runs" / "run-rop-mailbox-malformed" / "normalized_events.json"
        ).read_text(encoding="utf-8")
    )
    assert len(normalized) == 1


def test_rop_batch_case_period_override_updates_artifacts(tmp_path: Path) -> None:
    batch_path = _write_sample_batch(tmp_path)
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
    settings = _make_batch_settings(str(batch_path.relative_to(tmp_path)))

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-batch-period-override",
        session_id="session-rop-batch-period-override",
        period_override="2026-06",
    )

    assert result["status"] == "ok"

    run_dir = tmp_path / "runs" / "run-rop-batch-period-override"

    intake = json.loads((run_dir / "intake_metadata.json").read_text(encoding="utf-8"))
    operator = json.loads(
        (run_dir / "operator_summary.json").read_text(encoding="utf-8")
    )

    assert intake["period"] == "2026-06"
    assert operator["source"]["period"] == "2026-06"


def test_rop_batch_case_all_sources_partial_degradation(tmp_path: Path) -> None:
    good_batch_path = _write_sample_batch(tmp_path)
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": "good-source",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Good Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 50,
                "batch": {
                    "path": str(good_batch_path.relative_to(tmp_path)),
                    "period": "2026-05",
                },
            },
            {
                "source_id": "broken-source",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Broken Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 50,
                "batch": {
                    "path": "storage/mock/missing.json",
                    "period": "2026-05",
                },
            },
        ],
    }

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-batch-all-sources",
        session_id="session-rop-batch-all-sources",
        all_sources=True,
    )

    assert result["status"] == "ok"

    run_dir = tmp_path / "runs" / "run-rop-batch-all-sources"
    source_diagnostics = json.loads(
        (run_dir / "source_diagnostics.json").read_text(encoding="utf-8")
    )
    intake = json.loads((run_dir / "intake_metadata.json").read_text(encoding="utf-8"))
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )

    assert source_diagnostics["selection_mode"] == "all_enabled"
    assert source_diagnostics["status"] == "ok"
    assert source_diagnostics["reason"] == "partial_degradation"
    assert source_diagnostics["aggregate"]["source_count"] == 2
    assert source_diagnostics["aggregate"]["loaded_source_count"] == 1
    assert source_diagnostics["aggregate"]["degraded_source_count"] == 1
    assert len(source_diagnostics["sources"]) == 2

    assert intake["selection_mode"] == "all_enabled"
    assert intake["source_count"] == 2
    assert intake["loaded_source_count"] == 1
    assert intake["degraded_source_count"] == 1
    assert len(intake["sources"]) == 2

    assert len(normalized) == 2
    assert all(item.get("source_id") == "good-source" for item in normalized)
    assert all(item.get("source_type") == "json_batch" for item in normalized)
    assert all(item.get("source_role") == "batch_sample" for item in normalized)
    assert all(item.get("source_display_name") == "Good Source" for item in normalized)
    assert all(item.get("client_id") == "welding" for item in normalized)


def test_rop_batch_case_explicit_source_id_runs_single_source(tmp_path: Path) -> None:
    primary_batch_path = _write_sample_batch(tmp_path)
    secondary_batch_path = tmp_path / "batch_second.json"
    secondary_batch_path.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "s2-e1",
                        "sender": "second@example.com",
                        "subject": "Second source",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": "first-source",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "First Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 50,
                "batch": {
                    "path": str(primary_batch_path.relative_to(tmp_path)),
                    "period": "2026-05",
                },
            },
            {
                "source_id": "second-source",
                "source_type": "json_batch",
                "source_role": "sales_mailbox",
                "client_id": "welding",
                "display_name": "Second Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 50,
                "batch": {
                    "path": str(secondary_batch_path.relative_to(tmp_path)),
                    "period": "2026-05",
                },
            },
        ],
    }

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-rop-batch-explicit-source",
        session_id="session-rop-batch-explicit-source",
        source_id="second-source",
    )

    assert result["status"] == "ok"

    run_dir = tmp_path / "runs" / "run-rop-batch-explicit-source"
    intake = json.loads((run_dir / "intake_metadata.json").read_text(encoding="utf-8"))
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )

    assert intake["selection_mode"] == "single_explicit"
    assert intake["source_id"] == "second-source"
    assert len(normalized) == 1
    assert normalized[0]["source_id"] == "second-source"
    assert normalized[0]["source_role"] == "sales_mailbox"


def test_rop_batch_case_sanitizes_json_batch_in_normalized_events(
    tmp_path: Path,
) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_sanitize.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "san-001",
                "case_type": "new_lead",
                "confidence": 0.91,
                "raw_eml": "unsafe",
                "raw_message": "unsafe",
                "attachment_content": "unsafe",
                "content_bytes": "unsafe",
                "attachments": [
                    {
                        "filename": "original.eml",
                        "content_type": "message/rfc822",
                        "content": "unsafe",
                    },
                    {
                        "filename": "by_content_type.bin",
                        "content_type": "message/rfc822",
                        "content": "unsafe",
                    },
                    {
                        "filename": "brief.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 1234,
                        "content": "unsafe",
                    },
                ],
            }
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "sanitize-source",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Sanitize Source",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-batch-sanitize-normalized",
        session_id="session-batch-sanitize-normalized",
    )

    assert result["status"] == "ok"

    normalized = json.loads(
        (
            tmp_path
            / "runs"
            / "run-batch-sanitize-normalized"
            / "normalized_events.json"
        ).read_text(encoding="utf-8")
    )

    assert len(normalized) == 1
    item = normalized[0]

    assert "raw_eml" not in item
    assert "raw_message" not in item
    assert "attachment_content" not in item
    assert "content_bytes" not in item

    attachments = item.get("attachments", [])
    assert len(attachments) == 1
    assert attachments[0].get("filename") == "brief.pdf"
    assert attachments[0].get("content_type") == "application/pdf"
    assert "content" not in attachments[0]


def test_rop_batch_case_attachment_extraction_artifact_v0(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_attachment_extraction.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "evt-att-001",
                "source": "email",
                "sender": "lead@example.com",
                "subject": "Attachments",
                "attachments": [
                    {
                        "filename": "request.txt",
                        "content_type": "text/plain",
                        "size_bytes": 64,
                        "text_preview": "safe preview text for extraction",
                    },
                    {
                        "filename": "forwarded.eml",
                        "content_type": "message/rfc822",
                        "size_bytes": 128,
                    },
                    {
                        "filename": "scan.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 8192,
                    },
                ],
            }
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": {
            "enabled": True,
            "chars_max": 12,
            "size_max": 1024,
            "types": ["text/plain"],
        },
        "sources": [
            {
                "source_id": "test-batch-attachment-extraction",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Test Batch Attachment Extraction",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {
                    "path": str(batch_file.relative_to(tmp_path)),
                    "period": "2026-05",
                },
            }
        ],
    }

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-batch-attachment-extraction",
        session_id="session-batch-attachment-extraction",
    )

    assert result["status"] == "ok"

    run_dir = tmp_path / "runs" / "run-batch-attachment-extraction"
    extraction = json.loads(
        (run_dir / "attachment_extraction.json").read_text(encoding="utf-8")
    )
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )

    assert extraction["aggregate"]["attachment_count"] == 3
    assert extraction["aggregate"]["preview_available_count"] == 1
    assert extraction["aggregate"]["refused_count"] == 2

    statuses = {
        item["filename"]: item["extraction_status"] for item in extraction["items"]
    }
    assert statuses["request.txt"] == "preview"
    assert statuses["forwarded.eml"] == "refused"
    assert statuses["scan.pdf"] == "refused"

    reasons = {item["filename"]: item["reason_code"] for item in extraction["items"]}
    assert reasons["forwarded.eml"] == "blocked_email_attachment"
    assert reasons["scan.pdf"] == "attachment_oversized"

    assert len(normalized) == 1
    event = normalized[0]
    assert event["attachment_extraction_status"] == "refused"
    assert event["attachment_preview_available"] is True
    assert event["attachment_text_preview"] == "safe preview"
    assert len(event["attachment_extraction_refs"]) == 3


def test_rop_batch_case_attachment_extraction_does_not_store_raw_content(
    tmp_path: Path,
) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_attachment_safety.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "evt-att-safe-001",
                "source": "email",
                "sender": "lead@example.com",
                "subject": "Safe extraction",
                "attachments": [
                    {
                        "filename": "request.txt",
                        "content_type": "text/plain",
                        "size_bytes": 32,
                        "text": "line one\nline two",
                        "content": "RAW-SHOULD-NOT-PERSIST",
                        "content_bytes": "RAW-BYTES-SHOULD-NOT-PERSIST",
                    }
                ],
                "raw_eml": "RAW-EML-SHOULD-NOT-PERSIST",
            }
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": {
            "enabled": True,
            "chars_max": 200,
            "size_max": 1024,
            "types": ["text/plain"],
        },
        "sources": [
            {
                "source_id": "test-batch-attachment-safety",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Test Batch Attachment Safety",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {
                    "path": str(batch_file.relative_to(tmp_path)),
                    "period": "2026-05",
                },
            }
        ],
    }

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-batch-attachment-safety",
        session_id="session-batch-attachment-safety",
    )

    run_dir = tmp_path / "runs" / "run-batch-attachment-safety"
    extraction = json.loads(
        (run_dir / "attachment_extraction.json").read_text(encoding="utf-8")
    )
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )

    assert extraction["items"][0]["text_preview"] == "line one line two"
    assert "content" not in extraction["items"][0]
    assert "content_bytes" not in extraction["items"][0]

    serialized = json.dumps({"extraction": extraction, "normalized": normalized})
    assert "RAW-SHOULD-NOT-PERSIST" not in serialized
    assert "RAW-BYTES-SHOULD-NOT-PERSIST" not in serialized
    assert "RAW-EML-SHOULD-NOT-PERSIST" not in serialized


def test_rop_batch_classification_handoff_success(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-001",
                "source": "email",
                "sender": "lead1@example.com",
                "subject": "Inquiry 1",
            },
            {
                "event_id": "e-002",
                "source": "email",
                "sender": "lead2@example.com",
                "subject": "Inquiry 2",
            },
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-batch",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Batch Source",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-batch-classification-success",
        session_id="session-batch-classification-success",
    )

    assert result["status"] == "ok"
    assert result["module_status"] == "ok"

    run_dir = tmp_path / "runs" / "run-batch-classification-success"

    classified_path = run_dir / "classified_events.json"
    assert classified_path.exists()

    classified_events = json.loads(classified_path.read_text(encoding="utf-8"))
    assert len(classified_events) == 2
    assert all("case_type" in e for e in classified_events)

    operator_summary_path = run_dir / "operator_summary.json"
    operator_summary = json.loads(operator_summary_path.read_text(encoding="utf-8"))
    assert "classification" in operator_summary
    assert operator_summary["classification"]["normalized_count"] == 2
    assert operator_summary["classification"]["classified_count"] == 2
    assert operator_summary["classification"]["classification_failed_count"] == 0
    assert (
        "runs/run-batch-classification-success/classified_events.json"
        in operator_summary["artifact_refs"]
    )


def test_filter_event_for_module_normalizes_empty_received_at_to_none() -> None:
    filtered = _filter_event_for_module({"event_id": "e1", "received_at": ""})

    assert "received_at" in filtered
    assert filtered["received_at"] is None


def test_filter_event_for_module_preserves_context_fields() -> None:
    event = {
        "event_id": "e-preserve",
        "received_at": "2026-05-08T10:30:00+00:00",
        "original_message_date": "2026-06-09T04:55:46+00:00",
        "date_source": "original_forwarded_date",
        "clean_subject": "OEM submerged-arc welding machine supplied",
        "transport_labels": ["auto_fwd", "fwd", "spam"],
        "forwarded_wrapper": True,
        "original_sender": "gina.shi@morrowwelding.com",
        "original_recipient": "online@welding.kz",
        "x_email_id": "bounded-id-12345",
        "subject": "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied",
        "sender": "wrapper@example.com",
    }

    filtered = _filter_event_for_module(event)

    assert filtered["received_at"] == "2026-05-08T10:30:00+00:00"
    assert filtered["original_message_date"] == "2026-06-09T04:55:46+00:00"
    assert filtered["date_source"] == "original_forwarded_date"
    assert filtered["clean_subject"] == "OEM submerged-arc welding machine supplied"
    assert filtered["transport_labels"] == ["auto_fwd", "fwd", "spam"]
    assert filtered["forwarded_wrapper"] is True
    assert filtered["original_sender"] == "gina.shi@morrowwelding.com"
    assert filtered["original_recipient"] == "online@welding.kz"
    assert filtered["x_email_id"] == "bounded-id-12345"


def test_rop_batch_preclassified_events_get_trace_fields(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "preclassified_batch.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-pre-001",
                "case_type": "new_lead",
                "priority": "high",
                "confidence": 0.91,
            },
            {
                "event_id": "e-pre-002",
                "case_type": "existing_lead",
                "priority": "medium",
                "confidence": 0.84,
            },
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-batch-preclassified",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Batch Preclassified",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-batch-preclassified",
        session_id="session-batch-preclassified",
    )

    assert result["status"] == "ok"

    classified_path = (
        tmp_path / "runs" / "run-batch-preclassified" / "classified_events.json"
    )
    classified_events = json.loads(classified_path.read_text(encoding="utf-8"))

    assert len(classified_events) == 2
    for event in classified_events:
        assert event["source_id"] == "test-batch-preclassified"
        assert event["original_event_id"] == event["event_id"]
        assert event["is_fallback"] is False
        assert event["reason_code"] == "preclassified_input"

    operator_summary = json.loads(
        (
            tmp_path / "runs" / "run-batch-preclassified" / "operator_summary.json"
        ).read_text(encoding="utf-8")
    )
    assert operator_summary["classification"]["normalized_count"] == 2
    assert operator_summary["classification"]["classified_count"] == 2
    assert operator_summary["classification"]["classification_failed_count"] == 0


def test_rop_batch_event_preview_maps_to_body(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "preview_batch.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-preview-001",
                "source": "email",
                "sender": "preview@example.com",
                "subject": "[AUTO-FWD] FWD: *** SPAM *** Preview only",
                "attachments": [
                    {
                        "filename": "spec.pdf",
                        "content_type": "application/pdf",
                    }
                ],
                "body_preview": (
                    "--- Original Message ---\n"
                    "Email: gina.shi@morrowwelding.com\n"
                    "Оригинальный адрес получения: online@welding.kz\n"
                    "Дата: Tue, 9 Jun 2026 11:54:27 +0800\n"
                    "X-Email-ID: bounded-id-12345\n"
                    "\nSafe preview text for classification"
                ),
            }
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-batch-preview",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Batch Preview",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _PreviewBodyStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "lead_classification":
                assert "Safe preview text for classification" in context.payload["body"]
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="lead_classification",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Classified from preview text",
                    data={
                        "event_id": context.payload.get("event_id"),
                        "case_type": "new_lead",
                        "priority": "high",
                        "reason_code": "preview_text_classified",
                        "confidence": 0.95,
                        "is_fallback": False,
                    },
                )

            return ModuleResult(
                module_id="beeagent-rop",
                case_type="rop_summary",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Summary received preview-classified events",
                data={"counts": {"new_lead": 1}},
            )

    _pkg = _make_fake_package("test_stub_preview", "RopModule", _PreviewBodyStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_preview",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-batch-preview-body",
            session_id="session-batch-preview-body",
        )

        assert result["status"] == "ok"
        classified_events = json.loads(
            (
                tmp_path / "runs" / "run-batch-preview-body" / "classified_events.json"
            ).read_text(encoding="utf-8")
        )
        assert len(classified_events) == 1
        assert classified_events[0]["reason_code"] == "preview_text_classified"
        assert classified_events[0]["clean_subject"] == "Preview only"
        assert classified_events[0]["transport_labels"] == ["auto_fwd", "fwd", "spam"]
        assert classified_events[0]["spam_label_present"] is True
        assert classified_events[0]["reply_label_present"] is False
        assert classified_events[0]["forwarded_wrapper"] is True
        assert classified_events[0]["sender"] == "preview@example.com"
        assert (
            classified_events[0]["subject"]
            == "[AUTO-FWD] FWD: *** SPAM *** Preview only"
        )
        assert (
            "Safe preview text for classification"
            in classified_events[0]["body_preview"]
        )
        assert classified_events[0]["attachments"] == [
            {
                "filename": "spec.pdf",
                "content_type": "application/pdf",
            }
        ]
        assert classified_events[0]["original_sender"] == "gina.shi@morrowwelding.com"
        assert classified_events[0]["original_sender_email"] == (
            "gina.shi@morrowwelding.com"
        )
        assert classified_events[0]["original_recipient"] == "online@welding.kz"
        assert (
            classified_events[0]["original_message_date"] == "2026-06-09T03:54:27+00:00"
        )
        assert classified_events[0]["date_source"] == "original_forwarded_date"
        assert classified_events[0]["x_email_id"] == "bounded-id-12345"
    finally:
        _remove_fake_package("test_stub_preview")


def test_rop_batch_per_event_classification_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_fail.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-good",
                "source": "email",
                "sender": "good@example.com",
                "subject": "Good",
            },
            {
                "event_id": "e-bad",
                "source": "email",
                "sender": "bad@example.com",
                "subject": "[AUTO-FWD] FWD: *** SPAM *** Bad",
                "body_preview": (
                    "--- Original Message ---\n"
                    "Email: bad-origin@example.com\n"
                    "Оригинальный адрес получения: online@welding.kz\n"
                    "Дата: Tue, 9 Jun 2026 11:54:27 +0800\n"
                    "X-Email-ID: bounded-id-bad\n"
                ),
            },
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-batch-fail",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Batch Failure",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _ClassificationFailureStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                events = context.payload.get("events", [])
                assert len(events) == 2
                assert all("case_type" in event for event in events)
                assert any(event.get("is_fallback") is True for event in events)

                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary received classified events",
                    data={
                        "counts": {
                            "new_lead": 1,
                            "unknown": 1,
                        }
                    },
                )

            event = context.payload
            if event.get("event_id") == "e-bad":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="lead_classification",
                    authority=AuthorityLevel.READ_ONLY,
                    status="error",
                    summary="Classification failed for this event",
                    data={},
                )

            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": event.get("event_id"),
                    "case_type": "new_lead",
                    "priority": "high",
                    "reason_code": "test_new_lead",
                    "confidence": 0.9,
                    "is_fallback": False,
                },
            )

    _pkg = _make_fake_package("test_stub_rop", "RopModule", _ClassificationFailureStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_rop",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-batch-partial-fail",
            session_id="session-batch-partial-fail",
        )

        assert result["status"] == "ok" or result["status"] == "degraded"

        run_dir = tmp_path / "runs" / "run-batch-partial-fail"

        classified_path = run_dir / "classified_events.json"
        assert classified_path.exists()

        classified_events = json.loads(classified_path.read_text(encoding="utf-8"))
        assert len(classified_events) == 2

        fallback_items = [e for e in classified_events if e.get("is_fallback") is True]
        assert len(fallback_items) == 1

        fallback = fallback_items[0]
        assert fallback["case_type"] == "unknown"
        assert fallback["priority"] == "medium"
        assert fallback["reason_code"] == "classification_error"
        assert fallback["confidence"] == 0.0
        assert fallback["is_fallback"] is True
        assert fallback["source_id"] == "test-batch-fail"
        assert fallback["reasoning"] == (
            "Per-event classification failed; event was converted to controlled fallback item."
        )
        assert fallback["clean_subject"] == "Bad"
        assert fallback["transport_labels"] == ["auto_fwd", "fwd", "spam"]
        assert fallback["spam_label_present"] is True
        assert fallback["reply_label_present"] is False
        assert fallback["forwarded_wrapper"] is True
        assert fallback["sender"] == "bad@example.com"
        assert fallback["subject"] == "[AUTO-FWD] FWD: *** SPAM *** Bad"
        assert fallback["body_preview"]
        assert fallback["original_sender"] == "bad-origin@example.com"
        assert fallback["original_recipient"] == "online@welding.kz"
        assert fallback["original_message_date"] == "2026-06-09T03:54:27+00:00"
        assert fallback["date_source"] == "original_forwarded_date"
        assert fallback["x_email_id"] == "bounded-id-bad"

        operator_summary_path = run_dir / "operator_summary.json"
        operator_summary = json.loads(operator_summary_path.read_text(encoding="utf-8"))
        assert operator_summary["classification"]["normalized_count"] == 2
        assert operator_summary["classification"]["classified_count"] == 1
        assert operator_summary["classification"]["classification_failed_count"] == 1

    finally:
        _remove_fake_package("test_stub_rop")


def test_rop_batch_classification_payload_does_not_send_empty_received_at(
    tmp_path: Path,
) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_received_at_empty.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-empty-received-at",
                "source": "email",
                "sender": "wrapper@example.com",
                "subject": "[AUTO-FWD] FWD: *** SPAM *** OEM submerged-arc welding machine supplied",
                "clean_subject": "OEM submerged-arc welding machine supplied",
                "transport_labels": ["auto_fwd", "fwd", "spam"],
                "forwarded_wrapper": True,
                "original_sender": "gina.shi@morrowwelding.com",
                "original_recipient": "online@welding.kz",
                "original_message_date": "2026-06-09T04:55:46+00:00",
                "date_source": "original_forwarded_date",
                "received_at": "",
                "x_email_id": "bounded-id-empty-received-at",
                "body_preview": "Safe preview for empty received_at boundary test",
            }
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-empty-received-at",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Empty received_at",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _ReceivedAtBoundaryStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "lead_classification":
                assert context.payload["received_at"] is None
                assert context.payload["original_message_date"] == (
                    "2026-06-09T04:55:46+00:00"
                )
                assert context.payload["date_source"] == "original_forwarded_date"
                assert context.payload["clean_subject"] == (
                    "OEM submerged-arc welding machine supplied"
                )
                assert context.payload["transport_labels"] == [
                    "auto_fwd",
                    "fwd",
                    "spam",
                ]
                assert context.payload["forwarded_wrapper"] is True
                assert context.payload["original_sender"] == (
                    "gina.shi@morrowwelding.com"
                )
                assert context.payload["original_recipient"] == "online@welding.kz"
                assert context.payload["x_email_id"] == "bounded-id-empty-received-at"
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="lead_classification",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Classified with normalized received_at",
                    data={
                        "event_id": context.payload.get("event_id"),
                        "case_type": "new_lead",
                        "priority": "high",
                        "reason_code": "normalized_received_at",
                        "confidence": 0.9,
                        "is_fallback": False,
                    },
                )

            return ModuleResult(
                module_id="beeagent-rop",
                case_type="rop_summary",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Summary ok",
                data={"counts": {"new_lead": 1}},
            )

    _make_fake_package(
        "test_stub_received_at_boundary",
        "RopModule",
        _ReceivedAtBoundaryStub,
    )
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_received_at_boundary",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-empty-received-at-boundary",
            session_id="session-empty-received-at-boundary",
        )

        assert result["status"] == "ok"
        operator_summary = json.loads(
            (
                tmp_path
                / "runs"
                / "run-empty-received-at-boundary"
                / "operator_summary.json"
            ).read_text(encoding="utf-8")
        )
        assert operator_summary["classification"]["normalized_count"] == 1
        assert operator_summary["classification"]["classified_count"] == 1
        assert operator_summary["classification"]["classification_failed_count"] == 0
    finally:
        _remove_fake_package("test_stub_received_at_boundary")


def test_rop_batch_attachment_metadata_sanitation(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_att.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-attachment-size",
                "source": "email",
                "sender": "lead@example.com",
                "subject": "Spec attached",
                "body_preview": "Please see attached specification",
                "attachments": [
                    {
                        "filename": "spec.pdf",
                        "content_type": "application/pdf",
                        "size": 12345,
                        "unsupported_key": "must_be_removed",
                    }
                ],
            }
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-batch-att",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Batch Attachments",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _AttachmentSanitationStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "lead_classification":
                assert "attachments" in context.payload
                assert len(context.payload["attachments"]) == 1
                att = context.payload["attachments"][0]
                assert "size" not in att, (
                    f"Attachment should not contain 'size', got {att}"
                )
                assert "unsupported_key" not in att
                assert att.get("size_bytes") == 12345
                assert att.get("filename") == "spec.pdf"
                assert att.get("content_type") == "application/pdf"

                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="lead_classification",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Attachment metadata sanitized correctly",
                    data={
                        "event_id": context.payload.get("event_id"),
                        "case_type": "new_lead",
                        "priority": "high",
                        "confidence": 0.95,
                        "is_fallback": False,
                    },
                )

            return ModuleResult(
                module_id="beeagent-rop",
                case_type="rop_summary",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Summary received attachment-sanitized events",
                data={"counts": {"new_lead": 1}},
            )

    _pkg = _make_fake_package("test_stub_att", "RopModule", _AttachmentSanitationStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_att",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-batch-att-sanitation",
            session_id="session-batch-att-sanitation",
        )

        assert result["status"] == "ok"
    finally:
        _remove_fake_package("test_stub_att")


def test_rop_batch_value_error_does_not_crash_batch(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_valueerr.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "e-good-2",
                "source": "email",
                "sender": "good@example.com",
                "subject": "Good",
            },
            {
                "event_id": "e-bad-valueerr",
                "source": "email",
                "sender": "bad@example.com",
                "subject": "Bad",
                "attachments": [
                    {
                        "filename": "broken.pdf",
                        "size": "not_a_number",
                    }
                ],
            },
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"]["sources"] = [
        {
            "source_id": "test-batch-valueerr",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test Batch ValueError",
            "enabled": True,
            "authority": "read_only",
            "items_max": 100,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _ValueErrorStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                events = context.payload.get("events", [])
                assert len(events) == 2
                assert all("case_type" in event for event in events)
                assert any(event.get("is_fallback") is True for event in events)
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary received with fallback",
                    data={"counts": {"new_lead": 1, "unknown": 1}},
                )

            event_id = context.payload.get("event_id", "?")
            if event_id == "e-bad-valueerr":
                raise ValueError("Attachment metadata contains unsupported keys: size")

            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": event_id,
                    "case_type": "new_lead",
                    "priority": "high",
                    "confidence": 0.9,
                    "is_fallback": False,
                },
            )

    _pkg = _make_fake_package("test_stub_valueerr", "RopModule", _ValueErrorStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_valueerr",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-batch-valueerr",
            session_id="session-batch-valueerr",
        )

        assert result["status"] == "ok" or result["status"] == "degraded"

        run_dir = tmp_path / "runs" / "run-batch-valueerr"
        classified_path = run_dir / "classified_events.json"
        assert classified_path.exists()

        classified_events = json.loads(classified_path.read_text(encoding="utf-8"))
        assert len(classified_events) == 2

        fallback_items = [e for e in classified_events if e.get("is_fallback") is True]
        assert len(fallback_items) == 1

        fallback = fallback_items[0]
        assert fallback["case_type"] == "unknown"
        assert fallback["reason_code"] == "classification_error"
        assert fallback["is_fallback"] is True
        assert fallback["event_id"] == "e-bad-valueerr"

        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )
        assert operator_summary["classification"]["normalized_count"] == 2
        assert operator_summary["classification"]["classification_failed_count"] == 1
    finally:
        _remove_fake_package("test_stub_valueerr")


def test_json_batch_run_writes_mailbox_selection_envelope(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    batch_file = tmp_path / "batch_mailbox_selection.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "evt-001",
                        "source": "email",
                        "sender": "lead@example.com",
                        "subject": "Need price",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    settings["rop"]["sources"] = [
        {
            "source_id": "test-json-batch",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test JSON Batch",
            "enabled": True,
            "authority": "read_only",
            "items_max": 10,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _BatchSelectionStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "lead_classification":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="lead_classification",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Classified",
                    data={
                        "event_id": context.payload.get("event_id"),
                        "case_type": "new_lead",
                        "priority": "high",
                        "confidence": 0.9,
                        "reason_code": "classified",
                        "is_fallback": False,
                    },
                )
            return ModuleResult(
                module_id="beeagent-rop",
                case_type="rop_summary",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Summary",
                data={"counts": {"new_lead": 1}},
            )

    _pkg = _make_fake_package(
        "test_stub_mailbox_selection",
        "RopModule",
        _BatchSelectionStub,
    )
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_mailbox_selection",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-batch-mailbox-selection",
            session_id="session-batch-mailbox-selection",
        )

        mailbox_selection = json.loads(
            (
                tmp_path
                / "runs"
                / "run-batch-mailbox-selection"
                / "mailbox_selection.json"
            ).read_text(encoding="utf-8")
        )
        assert mailbox_selection["run_id"] == "run-batch-mailbox-selection"
        assert mailbox_selection["sources"] == []
        assert "raw_eml" not in json.dumps(mailbox_selection)
    finally:
        _remove_fake_package("test_stub_mailbox_selection")


def test_ai_assist_merge_contract_unavailable_preserves_deterministic_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_assist._call_ai_provider",
        lambda ai_cfg, prompt, logger: json.dumps(
            {
                "case_type": "existing_deal",
                "case_subtype": "follow_up",
                "recommended_queue": "review",
                "should_rop_see": True,
                "correct_action": "check_bitrix",
                "confidence": 0.9,
                "reason_code": "ai_assist",
                "risk_flags": [],
            }
        ),
    )

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"] = {
        "enabled": True,
        "events_max": 20,
        "request_timeout": 30,
        "ai_confidence_min": 0.40,
        "dry_run": True,
        "adjudicator": {
            **settings["rop"]["ai_assist"]["adjudicator"],
            "enabled": False,
        },
    }

    batch_file = tmp_path / "batch_ai_unavailable.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "evt-ai-001",
                        "source": "email",
                        "sender": "lead@example.com",
                        "subject": "Need update",
                        "case_type": "unknown",
                        "priority": "medium",
                        "confidence": 0.2,
                        "is_fallback": True,
                        "reason_code": "deterministic_fallback",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings["rop"]["sources"] = [
        {
            "source_id": "test-ai-batch",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test AI Batch",
            "enabled": True,
            "authority": "read_only",
            "items_max": 10,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _NoMergeStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary",
                    data={"counts": {"unknown": 1}},
                )
            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": context.payload.get("event_id"),
                    "case_type": "unknown",
                    "priority": "medium",
                    "confidence": 0.2,
                    "reason_code": "deterministic_fallback",
                    "is_fallback": True,
                },
            )

    _pkg = _make_fake_package("test_stub_no_merge", "RopModule", _NoMergeStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_no_merge",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-ai-contract-unavailable",
            session_id="session-ai-contract-unavailable",
        )

        run_dir = tmp_path / "runs" / "run-ai-contract-unavailable"
        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        assert classified_events[0]["case_type"] == "unknown"

        ai_results = json.loads(
            (run_dir / "rop_ai_assist_results.json").read_text(encoding="utf-8")
        )
        assert (
            ai_results["results"][0]["ai_assist_status"]
            == "module_contract_unavailable"
        )
        assert ai_results["results"][0]["ai_assist_used"] is False

        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )
        assert operator_summary["classification"]["ai_assist_degraded_count"] == 1
    finally:
        _remove_fake_package("test_stub_no_merge")


def test_ai_adjudicator_accepted_result_updates_classified_events(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        lambda **kwargs: json.dumps(
            {
                "case_type": "new_lead",
                "case_subtype": "tender",
                "recommended_queue": "tender",
                "should_rop_see": True,
                "correct_action": "review_tender",
                "confidence": 0.91,
                "reason": "Clear RFQ content",
                "risk_flags": ["marketing_conflict"],
            }
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = True
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True

    batch_file = tmp_path / "batch_adjudicator_ok.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "evt-adj-001",
                        "source": "email",
                        "sender": "lead@example.com",
                        "subject": "Need tender quote",
                        "body": "Please send tender pricing",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings["rop"]["sources"] = [
        {
            "source_id": "test-adj-batch",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test adjudicator batch",
            "enabled": True,
            "authority": "read_only",
            "items_max": 10,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _AdjudicatorStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary",
                    data={"counts": {"unknown": 1}},
                )
            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": context.payload.get("event_id"),
                    "case_type": "unknown",
                    "case_subtype": None,
                    "recommended_queue": "manual_review",
                    "should_rop_see": True,
                    "correct_action": "manual_review",
                    "priority": "medium",
                    "confidence": 0.2,
                    "reason_code": "deterministic_fallback",
                    "is_fallback": True,
                },
            )

    _make_fake_package("test_stub_adj_ok", "RopModule", _AdjudicatorStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_ok",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-adjudicator-ok",
            session_id="session-adjudicator-ok",
        )

        run_dir = tmp_path / "runs" / "run-adjudicator-ok"
        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        event = classified_events[0]
        assert event["case_type"] == "new_lead"
        assert event["case_subtype"] == "tender"
        assert event["recommended_queue"] == "tender"
        assert event["correct_action"] == "review_tender"
        assert event["confidence"] == 0.91
        assert event["reason_code"] == "validated_ai_adjudicator_output"
        assert event["reasoning"] == "Clear RFQ content"
        assert event["deterministic_case_type"] == "unknown"
        assert event["deterministic_recommended_queue"] == "manual_review"
        assert event["ai_adjudicator_status"] == "ok"
        assert event["ai_adjudicator_reason"] == "Clear RFQ content"

        ai_results = json.loads(
            (run_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
        )
        result = ai_results["results"][0]
        assert result["ai_provider"] == "openai_responses"
        assert result["ai_model"] == settings["ai"]["profiles"]["openai"]["model"]
        assert result["ai_confidence"] == 0.91
        assert result["ai_reason"] == "Clear RFQ content"
        assert result["ai_risk_flags"] == ["marketing_conflict"]
        assert result["ai_error"] == ""
    finally:
        _remove_fake_package("test_stub_adj_ok")


def test_adjudicator_enabled_skips_legacy_ai_assist_provider_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_assist._call_ai_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy rop_ai_assist provider path must not run")
        ),
    )
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        lambda **kwargs: json.dumps(
            {
                "case_type": "new_lead",
                "case_subtype": "tender",
                "recommended_queue": "tender",
                "should_rop_see": True,
                "correct_action": "review_tender",
                "confidence": 0.91,
                "reason": "Clear RFQ content",
                "risk_flags": [],
            }
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = False
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True

    batch_file = tmp_path / "batch_adjudicator_no_legacy.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "evt-adj-legacy-001",
                        "source": "email",
                        "sender": "lead@example.com",
                        "subject": "Need tender quote",
                        "body": "Please send tender pricing",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings["rop"]["sources"] = [
        {
            "source_id": "test-adj-no-legacy",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test adjudicator legacy skip",
            "enabled": True,
            "authority": "read_only",
            "items_max": 10,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _NoLegacyStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary",
                    data={"counts": {"unknown": 1}},
                )
            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": context.payload.get("event_id"),
                    "case_type": "unknown",
                    "case_subtype": None,
                    "recommended_queue": "manual_review",
                    "should_rop_see": True,
                    "correct_action": "manual_review",
                    "priority": "medium",
                    "confidence": 0.2,
                    "reason_code": "deterministic_fallback",
                    "is_fallback": True,
                },
            )

    _make_fake_package("test_stub_adj_no_legacy", "RopModule", _NoLegacyStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_no_legacy",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-adjudicator-no-legacy",
            session_id="session-adjudicator-no-legacy",
        )

        run_dir = tmp_path / "runs" / "run-adjudicator-no-legacy"
        ai_results = json.loads(
            (run_dir / "rop_ai_assist_results.json").read_text(encoding="utf-8")
        )
        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )

        assert ai_results["results"] == []
        assert operator_summary["classification"]["ai_assist_enabled"] is False
        assert operator_summary["classification"]["ai_assist_requested_count"] == 0
    finally:
        _remove_fake_package("test_stub_adj_no_legacy")


def test_adjudicator_env_kill_switch_skips_all_ai_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_assist._call_ai_provider",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy rop_ai_assist provider path must not run")
        ),
    )
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("adjudicator provider path must not run")
        ),
    )
    monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = False
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True

    batch_file = tmp_path / "batch_adjudicator_env_disabled.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "evt-adj-env-off-001",
                        "source": "email",
                        "sender": "lead@example.com",
                        "subject": "Need tender quote",
                        "body": "Please send tender pricing",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings["rop"]["sources"] = [
        {
            "source_id": "test-adj-env-off",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test adjudicator env off",
            "enabled": True,
            "authority": "read_only",
            "items_max": 10,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _KillSwitchStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary",
                    data={"counts": {"unknown": 1}},
                )
            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": context.payload.get("event_id"),
                    "case_type": "unknown",
                    "case_subtype": None,
                    "recommended_queue": "manual_review",
                    "should_rop_see": True,
                    "correct_action": "manual_review",
                    "priority": "medium",
                    "confidence": 0.2,
                    "reason_code": "deterministic_fallback",
                    "is_fallback": True,
                },
            )

    _make_fake_package("test_stub_adj_env_off", "RopModule", _KillSwitchStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_env_off",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-adjudicator-env-off",
            session_id="session-adjudicator-env-off",
        )

        run_dir = tmp_path / "runs" / "run-adjudicator-env-off"
        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )
        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )

        assert operator_summary["classification"]["ai_assist_enabled"] is False
        assert operator_summary["classification"]["ai_assist_requested_count"] == 0
        assert operator_summary["classification"]["ai_assist_used_count"] == 0
        assert operator_summary["classification"]["ai_adjudicator_enabled"] is False
        assert operator_summary["classification"]["ai_adjudicator_used_count"] == 0
        assert classified_events[0].get("ai_adjudicator_used") is not True

        assert not (run_dir / "rop_ai_adjudicator_requests.json").exists()
        assert not (run_dir / "rop_ai_adjudicator_decisions.json").exists()
        assert not (run_dir / "rop_ai_adjudicator_results.json").exists()

        ai_results = json.loads(
            (run_dir / "rop_ai_assist_results.json").read_text(encoding="utf-8")
        )
        assert ai_results["results"] == []
    finally:
        _remove_fake_package("test_stub_adj_env_off")


def test_ai_adjudicator_low_confidence_routes_to_manual_review_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.cases.rop_operator._is_event_eligible_for_ai_assist",
        lambda event, min_confidence: False,
    )
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        lambda **kwargs: json.dumps(
            {
                "case_type": "existing_deal",
                "case_subtype": None,
                "recommended_queue": "manual_review",
                "should_rop_see": True,
                "correct_action": "manual_review",
                "confidence": 0.35,
                "reason": "Uncertain",
                "risk_flags": ["low_signal"],
            }
        ),
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = True
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True

    batch_file = tmp_path / "batch_adjudicator_low.json"
    batch_file.write_text(
        json.dumps(
            {
                "period": "2026-05",
                "items": [
                    {
                        "event_id": "evt-adj-002",
                        "source": "email",
                        "sender": "lead@example.com",
                        "subject": "Need tender quote",
                        "body": "Please send tender pricing",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings["rop"]["sources"] = [
        {
            "source_id": "test-adj-low-batch",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "welding",
            "display_name": "Test adjudicator low batch",
            "enabled": True,
            "authority": "read_only",
            "items_max": 10,
            "batch": {
                "path": str(batch_file.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    class _AdjudicatorLowStub:
        @property
        def module_id(self) -> str:
            return "beeagent-rop"

        @property
        def authority(self) -> AuthorityLevel:
            return AuthorityLevel.READ_ONLY

        def supported_case_types(self) -> list[str]:
            return ["lead_classification", "rop_summary"]

        def handle(self, context: ModuleContext) -> ModuleResult:
            if context.case_type == "rop_summary":
                return ModuleResult(
                    module_id="beeagent-rop",
                    case_type="rop_summary",
                    authority=AuthorityLevel.READ_ONLY,
                    status="ok",
                    summary="Summary",
                    data={"counts": {"unknown": 1}},
                )
            return ModuleResult(
                module_id="beeagent-rop",
                case_type="lead_classification",
                authority=AuthorityLevel.READ_ONLY,
                status="ok",
                summary="Classified",
                data={
                    "event_id": context.payload.get("event_id"),
                    "case_type": "unknown",
                    "case_subtype": None,
                    "recommended_queue": "manual_review",
                    "should_rop_see": True,
                    "correct_action": "manual_review",
                    "priority": "medium",
                    "confidence": 0.2,
                    "reason_code": "deterministic_fallback",
                    "is_fallback": True,
                },
            )

    _make_fake_package("test_stub_adj_low", "RopModule", _AdjudicatorLowStub)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_low",
                    "entry": "RopModule",
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        run_rop_batch_case(
            settings=settings,
            storage_dir=tmp_path,
            project_root=tmp_path,
            logger=_null_logger(),
            registry=registry,
            run_id="run-adjudicator-low",
            session_id="session-adjudicator-low",
        )

        run_dir = tmp_path / "runs" / "run-adjudicator-low"
        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        event = classified_events[0]
        assert event["case_type"] == "unknown"
        assert event["recommended_queue"] == "manual_review"
        assert event["deterministic_case_type"] == "unknown"
        assert event["ai_adjudicator_status"] == "manual_review_degrade"
        assert event["reason_code"] == "ai_low_confidence_manual_review"

        ai_results = json.loads(
            (run_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
        )
        assert ai_results["results"][0]["ai_status"] == "manual_review_degrade"
    finally:
        _remove_fake_package("test_stub_adj_low")


def test_ai_adjudicator_ok_result_can_clear_optional_case_subtype() -> None:
    from beeagent_module.cases.rop_operator import _apply_ai_adjudicator_results

    events = [
        {
            "event_id": "evt-clear-subtype",
            "case_type": "existing_deal",
            "case_subtype": "follow_up",
            "recommended_queue": "sales",
            "correct_action": "check_bitrix",
            "should_rop_see": True,
            "confidence": 0.42,
            "reason_code": "deterministic_follow_up",
        }
    ]
    results = [
        {
            "event_id": "evt-clear-subtype",
            "ai_used": True,
            "ai_status": "ok",
            "ai_confidence": 0.91,
            "ai_reason": "AI accepted no subtype",
            "ai_risk_flags": [],
            "merge_reason": "validated_ai_adjudicator_output",
            "final_case_type": "new_lead",
            "final_case_subtype": None,
            "final_recommended_queue": "sales",
            "final_correct_action": "review_new_lead",
            "final_should_rop_see": True,
        }
    ]

    _apply_ai_adjudicator_results(events, results)

    assert events[0]["case_type"] == "new_lead"
    assert events[0]["case_subtype"] is None
    assert events[0]["recommended_queue"] == "sales"
    assert events[0]["correct_action"] == "review_new_lead"
    assert events[0]["should_rop_see"] is True
    assert events[0]["confidence"] == 0.91
    assert events[0]["reason_code"] == "validated_ai_adjudicator_output"
    assert events[0]["reasoning"] == "AI accepted no subtype"


def test_ai_adjudicator_manual_review_degrade_updates_classified_events() -> None:
    from beeagent_module.cases.rop_operator import _apply_ai_adjudicator_results

    events = [
        {
            "event_id": "evt-manual-review",
            "case_type": "existing_deal",
            "case_subtype": "existing_deal_procurement",
            "recommended_queue": "procurement",
            "correct_action": "check_bitrix",
            "should_rop_see": True,
            "confidence": 0.91,
            "reason_code": "existing_deal_reference_signal",
            "deterministic_case_type": "existing_deal",
            "deterministic_case_subtype": "existing_deal_procurement",
            "deterministic_recommended_queue": "procurement",
            "deterministic_correct_action": "check_bitrix",
            "deterministic_confidence": 0.91,
            "deterministic_reason_code": "existing_deal_reference_signal",
        }
    ]
    results = [
        {
            "event_id": "evt-manual-review",
            "ai_used": True,
            "ai_status": "manual_review_degrade",
            "ai_confidence": 0.35,
            "ai_reason": "Looks risky",
            "ai_risk_flags": ["low_signal"],
            "merge_reason": "ai_low_confidence_manual_review",
            "final_case_type": "existing_deal",
            "final_case_subtype": None,
            "final_recommended_queue": "manual_review",
            "final_correct_action": "manual_review",
            "final_should_rop_see": True,
        }
    ]

    _apply_ai_adjudicator_results(events, results)

    assert events[0]["case_type"] == "existing_deal"
    assert events[0]["case_subtype"] is None
    assert events[0]["recommended_queue"] == "manual_review"
    assert events[0]["correct_action"] == "manual_review"
    assert events[0]["should_rop_see"] is True
    assert events[0]["confidence"] == 0.35
    assert events[0]["ai_adjudicator_status"] == "manual_review_degrade"
    assert events[0]["reason_code"] == "ai_low_confidence_manual_review"
    assert events[0]["reasoning"] == "Looks risky"


def test_ai_adjudicator_low_confidence_preserve_keeps_deterministic_result() -> None:
    from beeagent_module.cases.rop_operator import _apply_ai_adjudicator_results

    events = [
        {
            "event_id": "evt-preserve-ignore",
            "case_type": "irrelevant",
            "case_subtype": "newsletter_bulk",
            "recommended_queue": "ignore",
            "correct_action": "ignore",
            "should_rop_see": False,
            "confidence": 0.93,
            "reason_code": "bulk_newsletter_ignore",
            "reasoning": "Deterministic ignore.",
        }
    ]
    results = [
        {
            "event_id": "evt-preserve-ignore",
            "ai_used": True,
            "ai_status": "low_confidence_preserve",
            "ai_confidence": 0.31,
            "ai_reason": "Low-confidence AI still sees non-actionable bulk content.",
            "ai_risk_flags": ["newsletter_bulk"],
            "merge_reason": "ai_low_confidence_safe_ignore_preserved",
            "final_case_type": "irrelevant",
            "final_case_subtype": "newsletter_bulk",
            "final_recommended_queue": "ignore",
            "final_correct_action": "ignore",
            "final_should_rop_see": False,
        }
    ]

    _apply_ai_adjudicator_results(events, results)

    assert events[0]["case_type"] == "irrelevant"
    assert events[0]["recommended_queue"] == "ignore"
    assert events[0]["correct_action"] == "ignore"
    assert events[0]["should_rop_see"] is False
    assert events[0]["confidence"] == 0.93
    assert events[0]["reason_code"] == "bulk_newsletter_ignore"
    assert events[0]["reasoning"] == "Deterministic ignore."
    assert events[0]["ai_adjudicator_status"] == "low_confidence_preserve"
    assert (
        events[0]["ai_adjudicator_merge_reason"]
        == "ai_low_confidence_safe_ignore_preserved"
    )


def test_no_direct_beeagent_rop_imports() -> None:
    import subprocess

    result = subprocess.run(
        [
            "grep",
            "-r",
            "-n",
            "from beeagent_rop\\|import beeagent_rop",
            str(_project_root() / "src" / "beeagent_module"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, (
        f"Found direct beeagent_rop imports:\n{result.stdout}"
    )
