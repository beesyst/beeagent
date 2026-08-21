from __future__ import annotations

import csv
import json
import logging
import os
import sys
import types
from hashlib import sha256
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
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")
os.environ.setdefault("BEEAGENT_WEB_OPERATOR_TOKEN", "test-operator-token")


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


def _write_raw_events_batch(
    directory: Path,
    events: list[dict],
    period: str = "2026-05",
) -> Path:
    batch = {"period": period, "items": events}
    path = directory / "raw_events_batch.json"
    path.write_text(json.dumps(batch), encoding="utf-8")
    return path


def _make_raw_batch_settings(
    batch_path: str,
    client_id: str = "welding",
    source_id: str = "test-batch",
) -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": source_id,
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": client_id,
                "display_name": "Test Batch Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {"path": batch_path, "period": "2026-05"},
            }
        ],
    }
    return settings


def _classify_raw_batch(
    tmp_path: Path,
    events: list[dict],
    run_id: str,
) -> list[dict]:
    batch_path = _write_raw_events_batch(tmp_path, events)
    registry = ModuleRegistry(
        config=[_rop_registry_entry_from_settings()], logger=_null_logger()
    )
    result = run_rop_batch_case(
        settings=_make_raw_batch_settings(str(batch_path.relative_to(tmp_path))),
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id=run_id,
        session_id=f"session-{run_id}",
    )

    assert result["status"] == "ok"
    return json.loads(
        (tmp_path / "runs" / run_id / "classified_events.json").read_text(
            encoding="utf-8"
        )
    )


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

    from beeagent_module.core.rop_final_decision import (
        load_or_build_final_decisions,
    )

    final_decisions_path = run_dir / "rop_final_decisions.json"
    assert final_decisions_path.exists()
    artifact = json.loads(final_decisions_path.read_text(encoding="utf-8"))
    assert artifact["summary"]["total_events"] == 2
    for event in artifact["events"]:
        assert event["final_queue"] == "unresolved"
        assert event["final_action"] == "no_action"
        assert event["needs_attention"] is True
        assert event["automation_allowed"] is False
        assert event["bitrix_write_allowed"] is False

    loaded, source = load_or_build_final_decisions(run_dir)
    assert source == "artifact"
    assert loaded == artifact


def test_rop_batch_indexes_newest_first_source_events_in_canonical_order(
    tmp_path: Path,
) -> None:
    from beeagent_rop.domain.thread_context import validate_thread_context

    from beeagent_module.core.rop_thread_context import build_public_thread_context

    run_id = "run-newest-first-thread"
    events = [
        {
            "event_id": "evt-reply",
            "message_id": "<reply@example.test>",
            "in_reply_to": "<original@example.test>",
            "sender": "reply@example.test",
            "subject": "Re: Synthetic quote request",
            "body": "Following up on the requested quote.",
            "date": "2026-05-02T10:00:00+00:00",
        },
        {
            "event_id": "evt-original",
            "message_id": "<original@example.test>",
            "sender": "buyer@example.test",
            "subject": "Synthetic quote request",
            "body": "Please send a quote for the specified equipment.",
            "date": "2026-05-01T10:00:00+00:00",
        },
    ]
    batch_path = _write_raw_events_batch(tmp_path, events)
    registry = ModuleRegistry(
        config=[_rop_registry_entry_from_settings()], logger=_null_logger()
    )

    result = run_rop_batch_case(
        settings=_make_raw_batch_settings(str(batch_path.relative_to(tmp_path))),
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id=run_id,
        session_id=f"session-{run_id}",
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / run_id
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    assert [event["event_id"] for event in normalized] == [
        "evt-reply",
        "evt-original",
    ]
    thread_index = json.loads(
        (run_dir / "mail_thread_index.json").read_text(encoding="utf-8")
    )
    assert len(thread_index["threads"]) == 1
    assert thread_index["threads"][0]["event_ids"] == [
        "evt-original",
        "evt-reply",
    ]
    thread_context = json.loads(
        (run_dir / "mail_thread_context.json").read_text(encoding="utf-8")
    )
    assert len(thread_context["contexts"]) == 1
    reply_context = thread_context["contexts"][0]
    assert reply_context["event_id"] == "evt-reply"
    assert reply_context["previous_event_ids"] == ["evt-original"]
    assert reply_context["participant_overlap"] is False
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified_by_id = {event["event_id"]: event for event in classified}
    assert (
        reply_context["previous_case_type"]
        == classified_by_id["evt-original"]["case_type"]
    )
    assert classified_by_id["evt-reply"]["in_reply_to"] == "<original@example.test>"
    normalized_by_id = {event["event_id"]: event for event in normalized}
    payload = build_public_thread_context(
        reply_context,
        normalized_by_id["evt-reply"],
    )
    validated, errors = validate_thread_context(payload)
    assert errors == []
    assert validated is not None


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


def test_rop_batch_attachment_items_carry_event_instance_id(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    batch_file = tmp_path / "batch_attachment_instance.json"
    batch = {
        "period": "2026-05",
        "items": [
            {
                "event_id": "evt-inst-001",
                "source": "email",
                "sender": "lead@example.com",
                "subject": "RFQ welding wire",
                "received_at": "2026-05-01T10:00:00Z",
                "attachments": [
                    {
                        "filename": "first.txt",
                        "content_type": "text/plain",
                        "size_bytes": 32,
                        "text_preview": "first safe preview",
                    }
                ],
            },
            {
                "event_id": "evt-inst-001",
                "source": "email",
                "sender": "lead@example.com",
                "subject": "RFQ welding wire",
                "received_at": "2026-05-02T10:00:00Z",
                "attachments": [
                    {
                        "filename": "second.txt",
                        "content_type": "text/plain",
                        "size_bytes": 32,
                        "text_preview": "second safe preview",
                    }
                ],
            },
        ],
    }
    batch_file.write_text(json.dumps(batch), encoding="utf-8")

    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": {
            "enabled": True,
            "chars_max": 120,
            "size_max": 4096,
            "types": ["text/plain"],
        },
        "sources": [
            {
                "source_id": "test-batch-attachment-instance",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Test Batch Attachment Instance",
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
        run_id="run-batch-attachment-instance",
        session_id="session-batch-attachment-instance",
    )

    run_dir = tmp_path / "runs" / "run-batch-attachment-instance"
    extraction = json.loads(
        (run_dir / "attachment_extraction.json").read_text(encoding="utf-8")
    )
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    items = extraction["items"]
    assert len(items) == 2
    assert {item["event_instance_id"] for item in items} == {
        "event-000001",
        "event-000002",
    }
    by_filename = {item["filename"]: item for item in items}
    normalized_by_instance = {event["event_instance_id"]: event for event in normalized}
    for item in items:
        normalized_event = normalized_by_instance[item["event_instance_id"]]
        assert item["filename"] in {
            attachment.get("filename")
            for attachment in normalized_event.get("attachments", [])
            if isinstance(attachment, dict)
        }
    assert (
        by_filename["first.txt"]["event_instance_id"]
        != by_filename["second.txt"]["event_instance_id"]
    )


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


def test_rop_batch_exact_duplicate_classified_with_evidence(tmp_path: Path) -> None:
    batch_path = _write_raw_events_batch(
        tmp_path,
        [
            {
                "event_id": "dup-a",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "Need a quote for welding wire",
                "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                "message_id": "<dup-a@example.com>",
                "thread_id": "th-dup",
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "dup-b",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "Need a quote for welding wire",
                "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                "message_id": "<dup-b@example.com>",
                "thread_id": "th-dup",
                "received_at": "2026-08-05T10:00:00Z",
            },
            {
                "event_id": "dup-c",
                "source": "email",
                "sender": "hr@example.com",
                "subject": "Weekly HR newsletter",
                "body": "Vacation schedule and onboarding updates.",
                "message_id": "<dup-c@example.com>",
                "received_at": "2026-08-02T10:00:00Z",
            },
        ],
    )
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
    settings = _make_raw_batch_settings(str(batch_path.relative_to(tmp_path)))

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-dup-exact",
        session_id="session-dup-exact",
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / "run-dup-exact"
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["dup-a"]["case_type"] == "new_lead"
    assert by_id["dup-b"]["case_type"] == "duplicate"
    assert by_id["dup-b"]["reason_code"] == "duplicate_candidate_confirmed"
    dup_block = by_id["dup-b"]["duplicate"]
    assert dup_block["is_duplicate"] is True
    assert dup_block["candidate"]["event_id"] == "dup-a"
    assert isinstance(dup_block["confidence"], (int, float))
    assert dup_block["confidence"] > 0
    assert by_id["dup-b"]["base_classification"]["case_type"] == "new_lead"
    assert by_id["dup-c"]["case_type"] != "duplicate"

    final = json.loads(
        (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
    )
    final_by_id = {event["event_id"]: event for event in final["events"]}
    assert final_by_id["dup-b"]["deterministic_case_type"] == "duplicate"
    assert final_by_id["dup-b"]["final_case_type"] == "duplicate"
    assert final_by_id["dup-b"]["final_decision_source"] == "deterministic"
    assert final_by_id["dup-b"]["duplicate"]["is_duplicate"] is True
    assert final_by_id["dup-b"]["base_classification"]["case_type"] == "new_lead"
    assert final_by_id["dup-a"]["deterministic_case_type"] == "new_lead"
    assert final_by_id["dup-a"]["final_case_type"] == "new_lead"
    assert final_by_id["dup-a"]["duplicate"] is None
    assert final_by_id["dup-a"]["base_classification"] is None

    operator = json.loads(
        (run_dir / "operator_summary.json").read_text(encoding="utf-8")
    )
    assert operator["classification"]["duplicate_count"] == 1
    assert operator["classification"]["classified_count"] == 3


def test_rop_batch_duplicates_do_not_become_canonical_source(tmp_path: Path) -> None:
    batch_path = _write_raw_events_batch(
        tmp_path,
        [
            {
                "event_id": "chain-1",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding electrodes",
                "body": "Please quote 200 kg of welding electrodes 3 mm.",
                "message_id": "<chain-1@example.com>",
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "chain-2",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding electrodes",
                "body": "Please quote 200 kg of welding electrodes 3 mm.",
                "message_id": "<chain-2@example.com>",
                "received_at": "2026-08-03T10:00:00Z",
            },
            {
                "event_id": "chain-3",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding electrodes",
                "body": "Please quote 200 kg of welding electrodes 3 mm.",
                "message_id": "<chain-3@example.com>",
                "received_at": "2026-08-05T10:00:00Z",
            },
        ],
    )
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
    settings = _make_raw_batch_settings(str(batch_path.relative_to(tmp_path)))

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-dup-chain",
        session_id="session-dup-chain",
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / "run-dup-chain"
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["chain-1"]["case_type"] == "new_lead"
    assert by_id["chain-2"]["case_type"] == "duplicate"
    assert by_id["chain-3"]["case_type"] == "duplicate"
    assert by_id["chain-2"]["duplicate"]["candidate"]["event_id"] == "chain-1"
    assert by_id["chain-3"]["duplicate"]["candidate"]["event_id"] == "chain-1"
    assert result["classification"]["duplicate_count"] == 2


def test_rop_batch_duplicate_message_id_items_are_not_self_matches(
    tmp_path: Path,
) -> None:
    transport_event_id = "<shared-message@example.test>"
    classified = _classify_raw_batch(
        tmp_path,
        [
            {
                "event_id": transport_event_id,
                "message_id": transport_event_id,
                "source": "email",
                "sender": "buyer@example.test",
                "subject": "Need a quote for welding wire",
                "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": transport_event_id,
                "message_id": transport_event_id,
                "source": "email",
                "sender": "buyer@example.test",
                "subject": "Need a quote for welding wire",
                "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                "received_at": "2026-08-02T10:00:00Z",
            },
        ],
        "run-duplicate-message-id-pair",
    )

    assert [event["case_type"] for event in classified] == ["new_lead", "duplicate"]
    assert classified[1]["duplicate"]["candidate"]["event_id"] == transport_event_id


def test_rop_batch_duplicate_message_id_does_not_form_duplicate_chain(
    tmp_path: Path,
) -> None:
    transport_event_id = "<shared-message-chain@example.test>"
    event = {
        "event_id": transport_event_id,
        "message_id": transport_event_id,
        "source": "email",
        "sender": "buyer@example.test",
        "subject": "RFQ welding electrodes",
        "body": "Please quote 200 kg of welding electrodes 3 mm.",
    }
    classified = _classify_raw_batch(
        tmp_path,
        [
            dict(event, received_at="2026-08-01T10:00:00Z"),
            dict(event, received_at="2026-08-02T10:00:00Z"),
            dict(event, received_at="2026-08-03T10:00:00Z"),
        ],
        "run-duplicate-message-id-chain",
    )

    assert [event["case_type"] for event in classified] == [
        "new_lead",
        "duplicate",
        "duplicate",
    ]
    assert len(classified[1]["duplicate"]["candidates"]) == 1
    assert len(classified[2]["duplicate"]["candidates"]) == 1
    assert classified[2]["duplicate"]["candidate"]["event_id"] == transport_event_id
    assert [event["event_instance_id"] for event in classified] == [
        "event-000003",
        "event-000002",
        "event-000001",
    ]

    run_dir = tmp_path / "runs" / "run-duplicate-message-id-chain"
    final_decisions = json.loads(
        (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
    )
    assert [event["event_instance_id"] for event in final_decisions["events"]] == [
        "event-000003",
        "event-000002",
        "event-000001",
    ]

    from beeagent_module.core.rop_review_export import export_review_tsv_for_run

    review_path = export_review_tsv_for_run(
        tmp_path,
        "run-duplicate-message-id-chain",
        _null_logger(),
    )
    with Path(review_path).open(encoding="utf-8", newline="") as review_file:
        review_rows = list(csv.DictReader(review_file, delimiter="\t"))
    assert [row["event_instance_id"] for row in review_rows] == [
        "event-000003",
        "event-000002",
        "event-000001",
    ]
    assert [row["bot_case_type"] for row in review_rows] == [
        "new_lead",
        "duplicate",
        "duplicate",
    ]


def test_duplicate_candidates_exclude_only_the_same_processing_item() -> None:
    from beeagent_module.cases.rop_operator import _build_duplicate_candidates

    event = {
        "event_id": "<same-message@example.test>",
        "client_id": "welding",
        "sender": "buyer@example.test",
    }
    canonical = [(4, event)]

    assert _build_duplicate_candidates(event, canonical, current_item_index=4) == []
    assert _build_duplicate_candidates(event, canonical, current_item_index=5) == [
        {
            "existing_lead_id": "<same-message@example.test>",
            "sender": "buyer@example.test",
            "subject": "",
            "body": "",
            "event_id": "<same-message@example.test>",
            "thread_id": None,
            "message_id": None,
            "raw_metadata": {},
        }
    ]


def test_rop_batch_same_message_id_isolated_by_client(tmp_path: Path) -> None:
    transport_event_id = "<shared-client-scope@example.test>"
    event = {
        "event_id": transport_event_id,
        "message_id": transport_event_id,
        "source": "email",
        "sender": "buyer@example.test",
        "subject": "Need a quote for welding wire",
        "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
        "received_at": "2026-08-01T10:00:00Z",
    }
    for source_id in ("client-a", "client-b"):
        (tmp_path / f"{source_id}.json").write_text(
            json.dumps({"period": "2026-05", "items": [event]}),
            encoding="utf-8",
        )
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": source_id,
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": client_id,
                "display_name": source_id,
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {"path": f"{source_id}.json", "period": "2026-05"},
            }
            for source_id, client_id in (("client-a", "a"), ("client-b", "b"))
        ],
    }
    registry = ModuleRegistry(
        config=[_rop_registry_entry_from_settings()], logger=_null_logger()
    )
    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-duplicate-message-id-client-scope",
        session_id="session-duplicate-message-id-client-scope",
        all_sources=True,
    )
    classified = json.loads(
        (
            tmp_path
            / "runs"
            / "run-duplicate-message-id-client-scope"
            / "classified_events.json"
        ).read_text(encoding="utf-8")
    )

    assert result["status"] == "ok"
    assert len(classified) == 2
    assert all(event["case_type"] == "new_lead" for event in classified)
    assert result["classification"]["duplicate_count"] == 0


def test_rop_batch_fallback_first_classification_is_canonical_for_duplicates(
    tmp_path: Path,
) -> None:
    batch_path = _write_raw_events_batch(
        tmp_path,
        [
            {
                "event_id": "fb-1",
                "source": "email",
                "sender": "neutral@example.com",
                "subject": "Status update",
                "body": "Nothing specific to report. Regards.",
                "message_id": "<fb-1@example.com>",
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "fb-2",
                "source": "email",
                "sender": "neutral@example.com",
                "subject": "Status update",
                "body": "Nothing specific to report. Regards.",
                "message_id": "<fb-2@example.com>",
                "received_at": "2026-08-02T10:00:00Z",
            },
            {
                "event_id": "fb-3",
                "source": "email",
                "sender": "neutral@example.com",
                "subject": "Status update",
                "body": "Nothing specific to report. Regards.",
                "message_id": "<fb-3@example.com>",
                "received_at": "2026-08-03T10:00:00Z",
            },
        ],
    )
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
    settings = _make_raw_batch_settings(str(batch_path.relative_to(tmp_path)))

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-fb-dup",
        session_id="session-fb-dup",
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / "run-fb-dup"
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["fb-1"]["case_type"] == "irrelevant"
    assert by_id["fb-1"]["is_fallback"] is True
    assert by_id["fb-2"]["case_type"] == "duplicate"
    assert by_id["fb-3"]["case_type"] == "duplicate"
    assert by_id["fb-2"]["duplicate"]["candidate"]["event_id"] == "fb-1"
    assert by_id["fb-3"]["duplicate"]["candidate"]["event_id"] == "fb-1"
    assert by_id["fb-2"]["base_classification"]["case_type"] == "irrelevant"
    assert result["classification"]["duplicate_count"] == 2


def test_rop_batch_client_scope_isolation_for_duplicates(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": "source-a",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "client-a",
                "display_name": "Source A",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {
                    "path": "client_a_batch.json",
                    "period": "2026-05",
                },
            },
            {
                "source_id": "source-b",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "client-b",
                "display_name": "Source B",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {
                    "path": "client_b_batch.json",
                    "period": "2026-05",
                },
            },
        ],
    }

    def _client_batch(suffix: str) -> dict:
        return {
            "period": "2026-05",
            "items": [
                {
                    "event_id": f"{suffix}-first",
                    "source": "email",
                    "sender": "buyer@shared.example.com",
                    "subject": "Need a quote for welding wire",
                    "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                    "message_id": f"<{suffix}-first@example.com>",
                    "received_at": "2026-08-01T10:00:00Z",
                },
                {
                    "event_id": f"{suffix}-second",
                    "source": "email",
                    "sender": "buyer@shared.example.com",
                    "subject": "Need a quote for welding wire",
                    "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                    "message_id": f"<{suffix}-second@example.com>",
                    "received_at": "2026-08-02T10:00:00Z",
                },
            ],
        }

    (tmp_path / "client_a_batch.json").write_text(
        json.dumps(_client_batch("a")), encoding="utf-8"
    )
    (tmp_path / "client_b_batch.json").write_text(
        json.dumps(_client_batch("b")), encoding="utf-8"
    )

    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-dup-isolation",
        session_id="session-dup-isolation",
        all_sources=True,
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / "run-dup-isolation"
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["a-first"]["case_type"] == "new_lead"
    assert by_id["a-second"]["case_type"] == "duplicate"
    assert by_id["a-second"]["duplicate"]["candidate"]["event_id"] == "a-first"
    assert by_id["b-first"]["case_type"] == "new_lead"
    assert by_id["b-second"]["case_type"] == "duplicate"
    assert by_id["b-second"]["duplicate"]["candidate"]["event_id"] == "b-first"
    assert result["classification"]["duplicate_count"] == 2


def test_rop_batch_near_duplicate_uses_module_evidence(tmp_path: Path) -> None:
    classified = _classify_raw_batch(
        tmp_path,
        [
            {
                "event_id": "near-first",
                "source": "email",
                "sender": "Buyer Team <buyer@example.com>",
                "subject": "Просим выслать коммерческое предложение на электроды",
                "body": (
                    "Просим выслать коммерческое предложение на сварочные "
                    "электроды АНО-21 3.0 мм с доставкой."
                ),
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "near-second",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "Просим выслать коммерческое предложение на электроды",
                "body": "Просим выслать коммерческое предложение на сварочные электроды АНО-21.",
                "received_at": "2026-08-02T10:00:00Z",
            },
        ],
        "run-dup-near",
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["near-first"]["case_type"] == "new_lead"
    assert by_id["near-second"]["case_type"] == "new_lead"
    assert by_id["near-second"]["duplicate"]["is_duplicate"] is False
    assert by_id["near-second"]["duplicate"]["resolution_status"] == "possible"
    assert by_id["near-second"]["duplicate"]["reason_code"] == (
        "near_duplicate_subject_body"
    )


def test_rop_batch_similar_unrelated_event_stays_non_duplicate(tmp_path: Path) -> None:
    classified = _classify_raw_batch(
        tmp_path,
        [
            {
                "event_id": "unrelated-first",
                "source": "email",
                "sender": "other@example.com",
                "subject": "Need a quote for welding wire",
                "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "unrelated-second",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "Request for welding electrodes quote",
                "body": "Please send a quote for welding electrodes АНО-21.",
                "received_at": "2026-08-02T10:00:00Z",
            },
        ],
        "run-dup-unrelated",
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["unrelated-second"]["case_type"] != "duplicate"
    assert by_id["unrelated-second"]["duplicate"]["is_duplicate"] is False
    assert by_id["unrelated-second"]["duplicate"]["reason_code"] == (
        "no_duplicate_candidate"
    )


def test_rop_batch_same_client_multi_source_duplicate(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"] = {
        "email_preview": {"body_chars_max": 4000},
        "attachments": _attachment_settings(),
        "sources": [
            {
                "source_id": "source-a",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "same-client",
                "display_name": "Source A",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {"path": "same_client_a.json", "period": "2026-05"},
            },
            {
                "source_id": "source-b",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "same-client",
                "display_name": "Source B",
                "enabled": True,
                "authority": "read_only",
                "items_max": 100,
                "batch": {"path": "same_client_b.json", "period": "2026-05"},
            },
        ],
    }
    first = {
        "event_id": "multi-source-first",
        "source": "email",
        "sender": "buyer@example.com",
        "subject": "Need a quote for welding wire",
        "body": "Please send quote for welding wire ER70S-6 1.2 mm.",
        "received_at": "2026-08-01T10:00:00Z",
    }
    second = dict(
        first, event_id="multi-source-second", received_at="2026-08-02T10:00:00Z"
    )
    (tmp_path / "same_client_a.json").write_text(
        json.dumps({"period": "2026-05", "items": [first]}), encoding="utf-8"
    )
    (tmp_path / "same_client_b.json").write_text(
        json.dumps({"period": "2026-05", "items": [second]}), encoding="utf-8"
    )
    registry = ModuleRegistry(
        config=[_rop_registry_entry_from_settings()], logger=_null_logger()
    )
    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-dup-same-client-multi-source",
        session_id="session-dup-same-client-multi-source",
        all_sources=True,
    )
    classified = json.loads(
        (
            tmp_path
            / "runs"
            / "run-dup-same-client-multi-source"
            / "classified_events.json"
        ).read_text(encoding="utf-8")
    )
    by_id = {event["event_id"]: event for event in classified}

    assert result["status"] == "ok"
    assert by_id["multi-source-first"]["case_type"] == "new_lead"
    assert by_id["multi-source-second"]["case_type"] == "duplicate"
    assert by_id["multi-source-second"]["duplicate"]["candidate"]["event_id"] == (
        "multi-source-first"
    )


def test_rop_batch_duplicate_candidates_use_bounded_preview_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_operator as rop_operator_module

    oversized_body = "Please send a quote for welding wire. " + "x" * 10000
    captured_payloads: list[dict] = []
    original_execute = rop_operator_module.execute_module_case

    def _capture_execute(**kwargs):
        if kwargs["case_type"] == "lead_classification":
            captured_payloads.append(kwargs["payload"])
        return original_execute(**kwargs)

    monkeypatch.setattr(rop_operator_module, "execute_module_case", _capture_execute)
    batch_path = _write_raw_events_batch(
        tmp_path,
        [
            {
                "event_id": "bounded-first",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "Need a quote for welding wire",
                "body": oversized_body,
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "bounded-second",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "Need a quote for welding wire",
                "body": oversized_body,
                "received_at": "2026-08-02T10:00:00Z",
            },
        ],
    )
    settings = _make_raw_batch_settings(str(batch_path.relative_to(tmp_path)))
    settings["rop"]["email_preview"]["body_chars_max"] = 64
    registry = ModuleRegistry(
        config=[_rop_registry_entry_from_settings()], logger=_null_logger()
    )

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-bounded-candidate",
        session_id="session-bounded-candidate",
    )

    candidate_body = captured_payloads[1]["duplicate_candidates"][0]["body"]
    assert result["status"] == "ok"
    assert candidate_body != oversized_body
    assert len(candidate_body) <= 64


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (
            {
                "event_id": "reviewed-0001",
                "source": "mailbox_readonly",
                "sender": "hr-platform@example.test",
                "subject": "Вакансия инженера по закупкам",
                "body": "Требуется инженер по закупкам сварочных материалов. Отклик кандидата и резюме во вложении.",
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "irrelevant",
                "priority": "low",
                "reason_codes": {"irrelevant_service_notification"},
                "is_fallback": False,
                "min_confidence": 0.7,
            },
        ),
        (
            {
                "event_id": "reviewed-0002",
                "source": "mailbox_readonly",
                "sender": "no-reply@crm.example.test",
                "subject": "CRM: напоминание о задаче по сделке",
                "body": "Автоматическое уведомление CRM. Задача по сделке DEAL-123 просрочена. Обратите внимание.",
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "irrelevant",
                "priority": "low",
                "reason_codes": {"irrelevant_service_notification"},
                "is_fallback": False,
                "min_confidence": 0.7,
            },
        ),
        (
            {
                "event_id": "reviewed-0003",
                "source": "mailbox_readonly",
                "sender": "supplier-electrode@example.test",
                "subject": "Коммерческое предложение на сварочные электроды",
                "body": "Добрый день! Мы производитель сварочных электродов. Направляем коммерческое предложение на нашу продукцию и каталог. Предлагаем сотрудничество.",
                "attachments": [
                    {
                        "attachment_id": "att-reviewed-0003-a",
                        "filename": "kommercheskoe_predlozhenie.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 90000,
                        "is_inline": False,
                    }
                ],
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "irrelevant",
                "priority": "low",
                "reason_codes": {"irrelevant_supplier_or_bulk_signal"},
                "is_fallback": False,
                "min_confidence": 0.75,
            },
        ),
        (
            {
                "event_id": "reviewed-0004",
                "source": "mailbox_readonly",
                "sender": "service-promo@example.test",
                "subject": "Продвижение сайта для вашей компании",
                "body": "Мы предлагаем услуги по продвижению сайта, рекламе и SEO. Коммерческое предложение прилагаем.",
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "irrelevant",
                "priority": "low",
                "reason_codes": {"irrelevant_supplier_or_bulk_signal"},
                "is_fallback": False,
                "min_confidence": 0.75,
            },
        ),
        (
            {
                "event_id": "reviewed-0005",
                "source": "mailbox_readonly",
                "sender": "expo-events@example.test",
                "subject": "Приглашение на выставку Weldex",
                "body": "Приглашаем вас посетить наш стенд на международной выставке сварочного оборудования. Демонстрация новой продукции.",
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "irrelevant",
                "priority": "low",
                "reason_codes": {
                    "irrelevant_bulk_signal",
                    "irrelevant_supplier_or_bulk_signal",
                },
                "is_fallback": False,
                "min_confidence": 0.75,
            },
        ),
        (
            {
                "event_id": "reviewed-0006",
                "source": "mailbox_readonly",
                "sender": "buyer-welding@example.test",
                "subject": "Запрос коммерческого предложения на электроды",
                "body": "Добрый день! Просим предоставить коммерческое предложение на сварочные электроды АНО-21 для нашей закупки. Нужна цена и сроки поставки.",
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "new_lead",
                "priority": "high",
                "reason_codes": {"new_lead_request_signal"},
                "case_subtype": "new_lead_rfq",
                "is_fallback": False,
                "min_confidence": 0.7,
            },
        ),
        (
            {
                "event_id": "reviewed-0007",
                "source": "mailbox_readonly",
                "sender": "procurement-buyer@example.test",
                "subject": "02-1130",
                "body": "Добрый день! Прошу ознакомиться и отправить коммерческое на sales@example.test. При отправке не менять тему сообщения.",
                "attachments": [
                    {
                        "attachment_id": "att-reviewed-0007-a",
                        "filename": "document.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 45000,
                        "is_inline": False,
                    }
                ],
                "raw_metadata": {"client_profile": "welding"},
            },
            {
                "case_type": "new_lead",
                "priority": "high",
                "reason_codes": {"new_lead_request_signal"},
                "case_subtype": "new_lead_rfq",
                "is_fallback": False,
                "min_confidence": 0.8,
            },
        ),
    ],
    ids=(
        "hr_vacancy",
        "bitrix_reminder",
        "supplier_outreach",
        "service_promo",
        "event_invitation",
        "buyer_electrode_request",
        "buyer_commercial_offer_request",
    ),
)
def test_rop_batch_preserves_reviewed_it20_classification_outcomes(
    tmp_path: Path,
    event: dict,
    expected: dict,
) -> None:
    classified = _classify_raw_batch(
        tmp_path,
        [dict(event, received_at="2026-08-01T10:00:00Z")],
        f"run-reviewed-{event['event_id']}",
    )

    result = classified[0]
    assert result["case_type"] == expected["case_type"]
    assert result["priority"] == expected["priority"]
    assert result["reason_code"] in expected["reason_codes"]
    assert result["is_fallback"] is expected["is_fallback"]
    assert result["confidence"] >= expected["min_confidence"]
    if "case_subtype" in expected:
        assert result["case_subtype"] == expected["case_subtype"]


@pytest.mark.parametrize(
    ("source_ref", "event", "expected_type"),
    [
        (
            "run-9cd9d1ae99e9",
            {
                "event_id": "reviewed-0008",
                "source": "mailbox_readonly",
                "sender": "supplier-ad@example.test",
                "subject": "Коммерческое предложение на электроды",
                "body": "Мы производим сварочные электроды АНО-21. Направляем коммерческое предложение на нашу продукцию. Предлагаем сотрудничество.",
                "raw_metadata": {"client_profile": "welding"},
            },
            "irrelevant",
        ),
        (
            "run-844530c057e6",
            {
                "event_id": "reviewed-0009",
                "source": "mailbox_readonly",
                "sender": "partner-program@example.test",
                "subject": "Коммерческое предложение по партнерской программе",
                "body": "Партнерская программа. Коммерческое предложение для партнеров на продукцию бренда. Приглашаем стать партнером.",
                "raw_metadata": {"client_profile": "welding"},
            },
            "irrelevant",
        ),
        (
            "run-ce974a9b8582",
            {
                "event_id": "reviewed-0010",
                "source": "mailbox_readonly",
                "sender": "service-center@example.test",
                "subject": "Сервисное обслуживание сварочных аппаратов",
                "body": "Предлагаем сервисное обслуживание и ремонт сварочных аппаратов. Коммерческое предложение прилагаем.",
                "raw_metadata": {"client_profile": "welding"},
            },
            "irrelevant",
        ),
        (
            "run-41d2bcf42389",
            {
                "event_id": "reviewed-0011",
                "source": "mailbox_readonly",
                "sender": "contractor-buyer@example.test",
                "subject": "Запрос коммерческого предложения",
                "body": "Просим направить коммерческое предложение на электроды. Мы производитель сварочных работ и хотим заказать материалы из вашего каталога.",
                "raw_metadata": {"client_profile": "welding"},
            },
            "new_lead",
        ),
        (
            "run-a7c20bc709ba",
            {
                "event_id": "reviewed-0012",
                "source": "mailbox_readonly",
                "sender": "supplier-offer@example.test",
                "subject": "Запрос на продукцию",
                "body": "Мы поставщик сварочного оборудования. Запрос на нашу продукцию во вложении.",
                "raw_metadata": {"client_profile": "welding"},
                "attachments": [
                    {
                        "attachment_id": "att-reviewed-0012-a",
                        "filename": "request.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 12000,
                        "is_inline": False,
                    }
                ],
            },
            "irrelevant",
        ),
        (
            "run-0036f2c6d9ee",
            {
                "event_id": "reviewed-0013",
                "source": "mailbox_readonly",
                "sender": "partner-ops@example.test",
                "subject": "Запрос по партнерской программе",
                "body": "Коллеги, во вложении запрос по партнерской программе. Просим заполнить.",
                "raw_metadata": {"client_profile": "welding"},
                "attachments": [
                    {
                        "attachment_id": "att-reviewed-0013-a",
                        "filename": "request.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 9000,
                        "is_inline": False,
                    }
                ],
            },
            "irrelevant",
        ),
        (
            "run-8bf12d19f51e",
            {
                "event_id": "reviewed-0014",
                "source": "mailbox_readonly",
                "sender": "manufacturer-promo@example.test",
                "subject": "Заявка на продукцию",
                "body": "Мы производим промышленные сварочные аппараты. Заявка на нашу продукцию во вложении.",
                "raw_metadata": {"client_profile": "welding"},
                "attachments": [
                    {
                        "attachment_id": "att-reviewed-0014-a",
                        "filename": "заявка_на_поставку.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 15000,
                        "is_inline": False,
                    }
                ],
            },
            "irrelevant",
        ),
        (
            "run-d96b18d8fc70",
            {
                "event_id": "reviewed-0015",
                "source": "mailbox_readonly",
                "sender": "procurement-buyer@example.test",
                "subject": "Запрос прайс-листа",
                "body": "Здравствуйте! Просим предоставить прайс-лист на сварочные материалы и уточнить условия поставки.",
                "raw_metadata": {"client_profile": "welding"},
            },
            "new_lead",
        ),
    ],
    ids=(
        "run-9cd9d1ae99e9_supplier_product_ad",
        "run-844530c057e6_partner_correspondence",
        "run-ce974a9b8582_service_promo",
        "run-41d2bcf42389_buyer_rfq_contractor",
        "run-a7c20bc709ba_supplier_ad_generic_attachment",
        "run-0036f2c6d9ee_partner_generic_attachment",
        "run-8bf12d19f51e_supplier_ad_strong_attachment",
        "run-d96b18d8fc70_buyer_price_list_request",
    ),
)
def test_rop_batch_final_classification_reviewed_it21_gate(
    tmp_path: Path,
    source_ref: str,
    event: dict,
    expected_type: str,
) -> None:
    run_id = f"run-it39-gate-{event['event_id']}"
    _classify_raw_batch(
        tmp_path,
        [dict(event, received_at="2026-08-01T10:00:00Z")],
        run_id,
    )
    final = json.loads(
        (tmp_path / "runs" / run_id / "rop_final_decisions.json").read_text(
            encoding="utf-8"
        )
    )
    decision = final["events"][0]
    assert decision["final_case_type"] == expected_type
    assert decision["final_decision_source"] in {
        "deterministic",
        "deterministic_preserved",
    }


def test_rop_batch_reviewed_buyer_rfq_exercises_ai_adjudicator_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_calls: list[None] = []

    def _provider_response(**kwargs) -> str:
        provider_calls.append(None)
        return json.dumps(
            {
                "case_type": "irrelevant",
                "case_subtype": "bulk",
                "recommended_queue": "ignore",
                "should_rop_see": False,
                "correct_action": "ignore",
                "confidence": 0.93,
                "reason": "Promotional broadcast without a buyer request.",
                "risk_flags": [],
                "reason_code": "non_actionable_bulk_or_newsletter",
                "evidence_codes": ["low_signal"],
            }
        )

    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        _provider_response,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = _adjudicator_enabled_settings()
    settings["rop"]["sources"] = [
        _write_adjudicator_batch_source(
            tmp_path,
            "test-adj-buyer-rfq",
            "batch_buyer_rfq.json",
            [
                {
                    "event_id": "reviewed-ai-buyer",
                    "source": "mailbox_readonly",
                    "sender": "procurement-buyer@example.test",
                    "subject": "Запрос прайс-листа",
                    "body": (
                        "Здравствуйте! Просим предоставить прайс-лист на "
                        "сварочные материалы и уточнить условия поставки."
                    ),
                    "raw_metadata": {"client_profile": "welding"},
                }
            ],
        )
    ]

    stub_class = _make_deterministic_adjudicator_stub(
        case_type="new_lead",
        case_subtype="rfq",
        recommended_queue="sales",
        correct_action="review_new_lead",
        confidence=0.95,
        reason_code="customer_request_detected",
    )
    _make_fake_package("test_stub_adj_buyer_rfq", "RopModule", stub_class)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_buyer_rfq",
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
            run_id="run-adj-buyer-rfq",
            session_id="session-adj-buyer-rfq",
        )

        run_dir = tmp_path / "runs" / "run-adj-buyer-rfq"
        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )
        assert operator_summary["classification"]["ai_adjudicator_eligible_count"] == 1
        assert operator_summary["classification"]["ai_adjudicator_used_count"] == 1

        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        event = classified_events[0]
        assert event["deterministic_case_type"] == "new_lead"
        assert event["ai_adjudicator_status"] == "ok"
        assert event["case_type"] == "irrelevant"
        assert event["recommended_queue"] == "ignore"
        assert event["correct_action"] == "ignore"

        final_decisions = json.loads(
            (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
        )
        final_decision = final_decisions["events"][0]
        assert final_decision["final_decision_source"] == "ai_adjudicator"
        assert final_decision["final_case_type"] == "irrelevant"
        assert final_decision["final_queue"] == "ignore"
        assert final_decision["final_action"] == "ignore"
        assert provider_calls == [None]
    finally:
        _remove_fake_package("test_stub_adj_buyer_rfq")


def test_rop_batch_spam_labelled_rfq_exercises_ai_adjudicator_gate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_calls: list[None] = []

    def _provider_response(**kwargs) -> str:
        provider_calls.append(None)
        return json.dumps(
            {
                "case_type": "new_lead",
                "case_subtype": "rfq",
                "recommended_queue": "sales",
                "should_rop_see": True,
                "correct_action": "review_new_lead",
                "confidence": 0.93,
                "reason": "RFQ later in the message body.",
                "risk_flags": [],
                "reason_code": "customer_request_detected",
                "evidence_codes": ["low_signal"],
            }
        )

    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        _provider_response,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = _adjudicator_enabled_settings()
    body = (
        "Промо-рассылка. Отписаться. " * 30
        + "Нужен прайс-лист на сварочные материалы и условия поставки."
    )
    assert len(body) > 500
    settings["rop"]["sources"] = [
        _write_adjudicator_batch_source(
            tmp_path,
            "test-adj-spam-rfq",
            "batch_spam_rfq.json",
            [
                {
                    "event_id": "reviewed-ai-spam-rfq",
                    "source": "mailbox_readonly",
                    "sender": "updates@example.test",
                    "subject": "Ежемесячная рассылка",
                    "body": body,
                    "transport_labels": ["spam"],
                    "spam_label_present": True,
                    "raw_metadata": {"client_profile": "welding"},
                }
            ],
        )
    ]

    stub_class = _make_deterministic_adjudicator_stub(
        case_type="irrelevant",
        case_subtype="newsletter_bulk",
        recommended_queue="ignore",
        correct_action="ignore",
        confidence=0.95,
        reason_code="bulk_newsletter_ignore",
    )
    _make_fake_package("test_stub_adj_spam_rfq", "RopModule", stub_class)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_spam_rfq",
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
            run_id="run-adj-spam-rfq",
            session_id="session-adj-spam-rfq",
        )

        run_dir = tmp_path / "runs" / "run-adj-spam-rfq"
        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )
        assert operator_summary["classification"]["ai_adjudicator_eligible_count"] == 1
        assert operator_summary["classification"]["ai_adjudicator_used_count"] == 1

        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        event = classified_events[0]
        assert event["deterministic_case_type"] == "irrelevant"
        assert event["spam_label_present"] is True
        assert event["ai_adjudicator_status"] == "ok"
        assert event["case_type"] == "new_lead"
        assert event["recommended_queue"] == "sales"
        assert event["correct_action"] == "review_new_lead"

        final_decisions = json.loads(
            (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
        )
        final_decision = final_decisions["events"][0]
        assert final_decision["final_decision_source"] == "ai_adjudicator"
        assert final_decision["final_case_type"] == "new_lead"
        assert final_decision["final_queue"] == "sales"
        assert final_decision["final_action"] == "review_new_lead"
        assert provider_calls == [None]
    finally:
        _remove_fake_package("test_stub_adj_spam_rfq")


def test_build_duplicate_candidates_deterministic_order_and_self_exclusion() -> None:
    from beeagent_module.cases.rop_operator import _build_duplicate_candidates

    canonical = [
        (
            0,
            {
                "event_id": "b",
                "client_id": "c1",
                "sender": "b@example.com",
                "subject": "B",
                "received_at": "2026-08-02T00:00:00Z",
            },
        ),
        (
            1,
            {
                "event_id": "a",
                "client_id": "c1",
                "sender": "a@example.com",
                "subject": "A",
                "received_at": "2026-08-01T00:00:00Z",
            },
        ),
        (
            2,
            {
                "event_id": "x",
                "client_id": "c2",
                "sender": "x@example.com",
                "subject": "X",
                "received_at": "2026-08-03T00:00:00Z",
            },
        ),
    ]
    current = {"event_id": "b", "client_id": "c1"}

    candidates = _build_duplicate_candidates(current, canonical, current_item_index=0)

    assert [candidate["event_id"] for candidate in candidates] == ["a"]
    assert all(candidate["event_id"] != "b" for candidate in candidates)
    assert all(candidate["existing_lead_id"] == "a" for candidate in candidates)

    ordered_candidates = _build_duplicate_candidates(
        {"event_id": "new", "client_id": "c1"}, canonical, current_item_index=3
    )
    assert [candidate["event_id"] for candidate in ordered_candidates] == ["a", "b"]


def test_build_duplicate_candidates_tie_break_by_event_id() -> None:
    from beeagent_module.cases.rop_operator import _build_duplicate_candidates

    canonical = [
        (
            0,
            {
                "event_id": "z",
                "client_id": "c1",
                "sender": "z@example.com",
                "subject": "Z",
                "received_at": "2026-08-01T00:00:00Z",
            },
        ),
        (
            1,
            {
                "event_id": "a",
                "client_id": "c1",
                "sender": "a@example.com",
                "subject": "A",
                "received_at": "2026-08-01T00:00:00Z",
            },
        ),
    ]
    candidates = _build_duplicate_candidates(
        {"event_id": "new", "client_id": "c1"}, canonical, current_item_index=2
    )

    assert [candidate["event_id"] for candidate in candidates] == ["a", "z"]


def test_rop_batch_orders_offset_timestamps_in_utc(tmp_path: Path) -> None:
    classified = _classify_raw_batch(
        tmp_path,
        [
            {
                "event_id": "offset-later",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding wire",
                "body": "Please send quote for welding wire.",
                "received_at": "2026-07-31T22:30:00Z",
            },
            {
                "event_id": "offset-earlier",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding wire",
                "body": "Please send quote for welding wire.",
                "received_at": "2026-08-01T00:15:00+02:00",
            },
        ],
        "run-offset-order",
    )

    by_id = {event["event_id"]: event for event in classified}

    assert by_id["offset-earlier"]["case_type"] == "new_lead"
    assert by_id["offset-later"]["case_type"] == "duplicate"
    assert by_id["offset-later"]["duplicate"]["candidate"]["event_id"] == (
        "offset-earlier"
    )


def test_duplicate_candidates_order_offset_timestamps_in_utc() -> None:
    from beeagent_module.cases.rop_operator import _build_duplicate_candidates

    candidates = _build_duplicate_candidates(
        {"event_id": "current", "client_id": "welding"},
        [
            (
                0,
                {
                    "event_id": "offset-later",
                    "client_id": "welding",
                    "received_at": "2026-07-31T22:30:00Z",
                },
            ),
            (
                1,
                {
                    "event_id": "offset-earlier",
                    "client_id": "welding",
                    "received_at": "2026-08-01T00:15:00+02:00",
                },
            ),
        ],
        current_item_index=2,
    )

    assert [candidate["event_id"] for candidate in candidates] == [
        "offset-earlier",
        "offset-later",
    ]


def test_ai_paths_skip_deterministic_duplicate() -> None:
    from beeagent_module.cases.rop_operator import _is_event_eligible_for_ai_assist
    from beeagent_module.core.rop_ai_adjudicator import (
        _is_event_eligible_for_adjudicator,
    )

    duplicate_event = {
        "case_type": "duplicate",
        "confidence": 0.99,
        "is_fallback": False,
    }
    assert _is_event_eligible_for_adjudicator(duplicate_event) is False
    assert _is_event_eligible_for_ai_assist(duplicate_event, 0.70) is False


def test_ai_adjudicator_preserves_deterministic_duplicate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_calls: list[dict] = []

    def _provider_response(**kwargs) -> str:
        provider_calls.append(kwargs)
        return (
            "```json\n"
            + json.dumps(
                {
                    "case_type": "manual_review",
                    "case_subtype": "",
                    "recommended_queue": "manual_review",
                    "should_rop_see": True,
                    "correct_action": "manual_review",
                    "confidence": 0.9,
                    "reason": "unexpected adjudication",
                    "risk_flags": [],
                    "reason_code": "conflicting_business_signals",
                    "evidence_codes": [],
                }
            )
            + "\n```"
        )

    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        _provider_response,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = True
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True

    batch_path = _write_raw_events_batch(
        tmp_path,
        [
            {
                "event_id": "adj-dup-1",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding wire",
                "body": "Please send quote for welding wire.",
                "message_id": "<adj-dup-1@example.com>",
                "received_at": "2026-08-01T10:00:00Z",
            },
            {
                "event_id": "adj-dup-2",
                "source": "email",
                "sender": "buyer@example.com",
                "subject": "RFQ welding wire",
                "body": "Please send quote for welding wire.",
                "message_id": "<adj-dup-2@example.com>",
                "received_at": "2026-08-02T10:00:00Z",
            },
        ],
    )
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())
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
                "path": str(batch_path.relative_to(tmp_path)),
                "period": "2026-05",
            },
        }
    ]

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="run-dup-adj",
        session_id="session-dup-adj",
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / "run-dup-adj"
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    by_id = {event["event_id"]: event for event in classified}

    assert by_id["adj-dup-1"]["case_type"] == "new_lead"
    assert by_id["adj-dup-2"]["case_type"] == "duplicate"
    assert by_id["adj-dup-2"].get("ai_adjudicator_status") is None

    final = json.loads(
        (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
    )
    final_by_id = {event["event_id"]: event for event in final["events"]}
    assert final_by_id["adj-dup-2"]["final_case_type"] == "duplicate"
    assert final_by_id["adj-dup-2"]["final_decision_source"] == "deterministic"
    assert final_by_id["adj-dup-2"]["duplicate"]["is_duplicate"] is True
    assert not any(
        "adj-dup-2" in str(call.get("prompt", "")) for call in provider_calls
    )


def test_final_decision_preserves_deterministic_duplicate() -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    decisions = build_final_decisions(
        [
            {
                "event_id": "duplicate-final",
                "case_type": "duplicate",
                "recommended_queue": "manual_review",
                "correct_action": "review",
                "confidence": 0.99,
                "reason_code": "duplicate_candidate_confirmed",
                "is_fallback": False,
            }
        ],
        [
            {
                "event_id": "duplicate-final",
                "ai_status": "ok",
                "final_case_type": "manual_review",
                "final_recommended_queue": "manual_review",
                "final_correct_action": "manual_review",
                "ai_confidence": 0.9,
            }
        ],
    )

    event = decisions["events"][0]
    assert event["final_case_type"] == "duplicate"
    assert event["final_decision_source"] == "deterministic"


@pytest.mark.parametrize("ai_status", ["degraded", "invalid", "manual_review_degrade"])
def test_final_decision_routes_unavailable_possible_duplicate_to_base_preserved(
    ai_status: str,
) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    base = {
        "case_type": "new_lead",
        "priority": "medium",
        "reason_code": "customer_request_detected",
        "confidence": 0.8,
        "reasoning": "bounded base classification",
        "is_fallback": False,
        "case_subtype": "",
        "recommended_queue": "sales",
        "should_rop_see": True,
        "correct_action": "review_new_lead",
    }
    duplicate = {
        "is_duplicate": False,
        "resolution_status": "possible",
        "confidence": 0.86,
        "reason_code": "near_duplicate_subject_body",
        "reason_path": ["subject_similarity"],
        "reasoning": "bounded duplicate evidence",
        "candidate": None,
        "candidates": [],
        "is_fallback": False,
    }
    decisions = build_final_decisions(
        [
            {
                "event_id": "possible-final",
                **base,
                "base_classification": base,
                "duplicate": duplicate,
            }
        ],
        [
            {
                "event_id": "possible-final",
                "ai_status": ai_status,
                "merge_reason": "missing_api_key_deterministic_result_preserved",
            }
        ],
    )

    event = decisions["events"][0]
    assert event["final_case_type"] == "new_lead"
    assert event["final_queue"] == "sales"
    assert event["final_action"] == "review_new_lead"
    assert event["needs_attention"] is True
    assert (
        event["attention_reason_code"] == "possible_duplicate_unresolved_base_preserved"
    )
    assert event["duplicate"]["resolution_status"] == "possible"


def test_final_decision_possible_duplicate_missing_base_is_safe() -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    duplicate = {
        "is_duplicate": False,
        "resolution_status": "possible",
        "confidence": 0.8,
        "reason_code": "near_duplicate_subject_body",
        "reason_path": ["subject_similarity"],
        "reasoning": "bounded duplicate evidence",
        "candidate": None,
        "candidates": [],
        "is_fallback": False,
    }
    decisions = build_final_decisions(
        [
            {
                "event_id": "possible-final",
                "case_type": "new_lead",
                "recommended_queue": "sales",
                "correct_action": "review_new_lead",
                "confidence": 0.8,
                "duplicate": duplicate,
            }
        ],
        [
            {
                "event_id": "possible-final",
                "ai_status": "degraded",
                "merge_reason": "provider_call_failed_deterministic_result_preserved",
            }
        ],
    )

    event = decisions["events"][0]
    assert event["final_case_type"] == "new_lead"
    assert event["final_queue"] == "sales"
    assert event["needs_attention"] is True
    assert (
        event["attention_reason_code"] == "possible_duplicate_unresolved_base_preserved"
    )


def test_final_decisions_route_degraded_tender_to_deterministic_preserved() -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions

    event = {
        "event_id": "tender-final",
        "case_type": "new_lead",
        "case_subtype": "tender",
        "recommended_queue": "tender",
        "correct_action": "review_tender",
        "confidence": 0.95,
        "reason_code": "tender_or_rfq_detected",
    }
    for status in ("low_confidence", "manual_review_degrade", "degraded", "invalid"):
        decisions = build_final_decisions(
            [event],
            [
                {
                    "event_id": "tender-final",
                    "ai_status": status,
                    "merge_reason": "provider_call_failed_deterministic_result_preserved",
                    "ai_evidence_codes": [],
                }
            ],
        )
        decision = decisions["events"][0]
        assert decision["deterministic_queue"] == "tender"
        assert decision["deterministic_action"] == "review_tender"
        assert decision["final_queue"] == "tender"
        assert decision["final_action"] == "review_tender"
        assert decision["needs_attention"] is True

    for case_type, queue, action in (
        ("new_lead", "tender", "review_tender"),
        ("existing_deal", "tender", "review_tender"),
        ("irrelevant", "ignore", "ignore"),
    ):
        decisions = build_final_decisions(
            [event],
            [
                {
                    "event_id": "tender-final",
                    "ai_status": "ok",
                    "final_case_type": case_type,
                    "final_case_subtype": None,
                    "final_recommended_queue": queue,
                    "final_correct_action": action,
                    "ai_confidence": 0.91,
                }
            ],
        )
        decision = decisions["events"][0]
        assert decision["final_case_type"] == case_type
        assert decision["final_queue"] == queue
        assert decision["final_action"] == action
        assert decision["needs_attention"] is False


def test_entity_encoded_rfq_reaches_public_module_and_ai_qualification(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_calls: list[dict] = []

    def _provider_response(**kwargs) -> str:
        provider_calls.append(kwargs)
        assert "Запрос цен № T-0002338" in kwargs["prompt"]
        return json.dumps(
            {
                "case_type": "irrelevant",
                "case_subtype": "",
                "recommended_queue": "ignore",
                "should_rop_see": False,
                "correct_action": "ignore",
                "confidence": 0.40,
                "reason": "Insufficient evidence for an automated decision.",
                "risk_flags": ["low_signal"],
                "reason_code": "insufficient_business_signal",
                "evidence_codes": ["low_signal"],
            }
        )

    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        _provider_response,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _adjudicator_enabled_settings()
    batch_path = _write_raw_events_batch(
        tmp_path,
        [
            {
                "event_id": "synthetic-rfq-001",
                "sender": "notifications@example.test",
                "subject": "&#1053;&#1086;&#1074;&#1099;&#1077; &#1089;&#1086;&#1073;&#1099;&#1090;&#1080;&#1103; &#1087;&#1086; &#1074;&#1072;&#1096;&#1080;&#1084; &#1087;&#1086;&#1076;&#1087;&#1080;&#1089;&#1082;&#1072;&#1084;",
                "body": "&#1047;&#1072;&#1087;&#1088;&#1086;&#1089; &#1094;&#1077;&#1085; &#8470; T-0002338. &#x42d;&#x43b;&#x435;&#x43a;&#x442;&#x440;&#x43e;- &#x438; &#x440;&#x443;&#x447;&#x43d;&#x44b;&#x435; &#x438;&#x43d;&#x441;&#x442;&#x440;&#x443;&#x43c;&#x435;&#x43d;&#x442;&#x44b; &amp; &#x43e;&#x441;&#x43d;&#x430;&#x441;&#x442;&#x43a;&#x430;.",
                "received_at": "2026-08-10T10:00:00Z",
            }
        ],
    )
    settings["rop"]["sources"] = [
        {
            "source_id": "synthetic-rfq-source",
            "source_type": "json_batch",
            "source_role": "batch_sample",
            "client_id": "synthetic-client",
            "display_name": "Synthetic RFQ source",
            "enabled": True,
            "authority": "read_only",
            "items_max": 20,
            "batch": {
                "path": str(batch_path.relative_to(tmp_path)),
                "period": "2026-08",
            },
        }
    ]
    registry = ModuleRegistry(
        config=[_rop_registry_entry_from_settings()],
        logger=_null_logger(),
    )

    result = run_rop_batch_case(
        settings=settings,
        storage_dir=tmp_path,
        project_root=tmp_path,
        logger=_null_logger(),
        registry=registry,
        run_id="synthetic-entity-rfq",
        session_id="synthetic-entity-rfq-session",
    )

    assert result["status"] == "ok"
    run_dir = tmp_path / "runs" / "synthetic-entity-rfq"
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    assert "Запрос цен № T-0002338" in normalized[0]["body_preview"]
    ai_results = json.loads(
        (run_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
    )
    assert ai_results["results"][0]["ai_status"] == "low_confidence_preserve"
    assert provider_calls
    final = json.loads(
        (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
    )["events"][0]
    assert final["final_case_type"] == "unknown"
    assert final["final_queue"] == "unresolved"
    assert final["final_action"] == "no_action"
    assert final["needs_attention"] is True
    assert (
        final["attention_reason_code"]
        == "ai_confidence_below_threshold_deterministic_result_preserved"
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
    provider_calls: list[None] = []

    def _provider_response(**kwargs) -> str:
        provider_calls.append(None)
        return (
            "```json\n"
            + json.dumps(
                {
                    "case_type": "new_lead",
                    "case_subtype": "tender",
                    "recommended_queue": "tender",
                    "should_rop_see": True,
                    "correct_action": "review_tender",
                    "confidence": 0.91,
                    "reason": "Clear RFQ content",
                    "risk_flags": ["marketing_conflict"],
                    "reason_code": "customer_request_detected",
                    "evidence_codes": ["low_signal"],
                }
            )
            + "\n```"
        )

    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        _provider_response,
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
                    "reason_code": "fallback_low_signal",
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
        assert event["reason_code"] == "fallback_low_signal"
        assert event["reasoning"] == "Clear RFQ content"
        assert event["deterministic_case_type"] == "unknown"
        assert event["deterministic_recommended_queue"] == "manual_review"
        assert event["ai_adjudicator_status"] == "ok"
        assert event["ai_adjudicator_reason"] == "Clear RFQ content"
        assert event["ai_adjudicator_merge_reason"] == (
            "validated_ai_adjudicator_output"
        )

        ai_results = json.loads(
            (run_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
        )
        result = ai_results["results"][0]
        assert result["ai_provider"] == "openai_responses"
        assert result["ai_model"] == settings["ai"]["profiles"]["openai"]["model"]
        assert result["ai_confidence"] == 0.91
        assert result["ai_reason"] == "Clear RFQ content"
        assert result["ai_reason_code"] == "customer_request_detected"
        assert result["ai_risk_flags"] == ["marketing_conflict"]
        assert result["ai_error"] == ""
        assert provider_calls == [None]
        assert "```json" not in (
            run_dir / "rop_ai_adjudicator_requests.json"
        ).read_text(encoding="utf-8")
        assert "```json" not in (
            run_dir / "rop_ai_adjudicator_decisions.json"
        ).read_text(encoding="utf-8")
        assert "```json" not in (run_dir / "rop_ai_adjudicator_results.json").read_text(
            encoding="utf-8"
        )

        artifacts_before = {
            path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in run_dir.rglob("*")
            if path.is_file()
        }
        from beeagent_module.interfaces.ui.rop_event_detail import (
            build_rop_event_detail_page_model,
            build_rop_event_detail_read_model,
        )

        ru_api = build_rop_event_detail_read_model(
            tmp_path,
            "run-adjudicator-ok",
            "evt-adj-001",
            lang="ru",
        )
        en_api = build_rop_event_detail_read_model(
            tmp_path,
            "run-adjudicator-ok",
            "evt-adj-001",
            lang="en",
        )
        ru_html = build_rop_event_detail_page_model(
            tmp_path,
            "run-adjudicator-ok",
            "evt-adj-001",
            lang="ru",
        )
        en_html = build_rop_event_detail_page_model(
            tmp_path,
            "run-adjudicator-ok",
            "evt-adj-001",
            lang="en",
        )
        artifacts_after = {
            path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
            for path in run_dir.rglob("*")
            if path.is_file()
        }

        assert ru_api["classification"]["reason_code"] == ("fallback_low_signal")
        assert ru_api["classification"]["reason_display"] == (
            "Резерв: слабый сигнал, применена резервная классификация"
        )
        assert en_api["classification"]["reason_display"] == (
            "Fallback: low signal, fallback classification applied"
        )
        assert "Unknown reason code" not in str(en_html)
        assert "Неизвестный код причины" not in str(ru_html)
        assert (
            ru_api["ai_adjudicator"]["ai_adjudicator_reason_code"]
            == "customer_request_detected"
        )
        assert artifacts_after == artifacts_before

        final_decisions = json.loads(
            (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
        )
        assert final_decisions["summary"]["total_events"] == 1
        final_decision = final_decisions["events"][0]
        assert final_decision["event_id"] == "evt-adj-001"
        assert final_decision["final_decision_source"] == "ai_adjudicator"
        assert final_decision["final_case_type"] == "new_lead"
        assert final_decision["final_queue"] == "tender"
        assert final_decision["final_action"] == "review_tender"
        assert final_decision["automation_allowed"] is False
        assert final_decision["bitrix_write_allowed"] is False
    finally:
        _remove_fake_package("test_stub_adj_ok")


def _make_deterministic_adjudicator_stub(
    *,
    case_type: str,
    case_subtype: str | None,
    recommended_queue: str,
    correct_action: str,
    confidence: float,
    reason_code: str,
    is_fallback: bool = False,
) -> type:
    class _Stub:
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
                    "case_type": case_type,
                    "case_subtype": case_subtype,
                    "recommended_queue": recommended_queue,
                    "should_rop_see": True,
                    "correct_action": correct_action,
                    "priority": "medium",
                    "confidence": confidence,
                    "reason_code": reason_code,
                    "is_fallback": is_fallback,
                },
            )

    return _Stub


def _write_adjudicator_batch_source(
    tmp_path: Path,
    source_id: str,
    filename: str,
    items: list[dict],
) -> dict:
    batch_file = tmp_path / filename
    batch_file.write_text(
        json.dumps({"period": "2026-05", "items": items}),
        encoding="utf-8",
    )
    return {
        "source_id": source_id,
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


def _adjudicator_enabled_settings() -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    settings["rop"]["ai_assist"]["enabled"] = True
    settings["rop"]["ai_assist"]["dry_run"] = True
    settings["rop"]["ai_assist"]["adjudicator"]["enabled"] = True
    return settings


def test_ai_adjudicator_high_confidence_tender_candidate_ignores_non_actionable_digest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    provider_calls: list[None] = []

    def _provider_response(**kwargs) -> str:
        provider_calls.append(None)
        return json.dumps(
            {
                "case_type": "irrelevant",
                "case_subtype": "tender_digest",
                "recommended_queue": "ignore",
                "should_rop_see": False,
                "correct_action": "ignore",
                "confidence": 0.91,
                "reason": "Generic tender digest with no actionable opportunity.",
                "risk_flags": ["low_signal"],
                "reason_code": "non_actionable_bulk_or_newsletter",
                "evidence_codes": ["newsletter_bulk"],
            }
        )

    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        _provider_response,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = _adjudicator_enabled_settings()
    settings["rop"]["sources"] = [
        _write_adjudicator_batch_source(
            tmp_path,
            "test-adj-tender-digest",
            "batch_tender_digest.json",
            [
                {
                    "event_id": "evt-tender-digest",
                    "sender": "tenders@example.com",
                    "subject": "Tender digest for welding",
                    "body": "Weekly tender digest subscription. Unsubscribe to stop.",
                }
            ],
        )
    ]

    stub_class = _make_deterministic_adjudicator_stub(
        case_type="new_lead",
        case_subtype="tender",
        recommended_queue="tender",
        correct_action="review_tender",
        confidence=0.95,
        reason_code="tender_or_rfq_detected",
    )
    _make_fake_package("test_stub_adj_tender_digest", "RopModule", stub_class)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_tender_digest",
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
            run_id="run-adj-tender-digest",
            session_id="session-adj-tender-digest",
        )

        run_dir = tmp_path / "runs" / "run-adj-tender-digest"
        operator_summary = json.loads(
            (run_dir / "operator_summary.json").read_text(encoding="utf-8")
        )
        assert operator_summary["classification"]["ai_adjudicator_eligible_count"] == 1
        assert operator_summary["classification"]["ai_adjudicator_used_count"] == 1

        classified_events = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        event = classified_events[0]
        assert event["deterministic_case_type"] == "new_lead"
        assert event["deterministic_recommended_queue"] == "tender"
        assert event["ai_adjudicator_status"] == "ok"
        assert event["case_type"] == "irrelevant"
        assert event["recommended_queue"] == "ignore"
        assert event["correct_action"] == "ignore"

        final_decisions = json.loads(
            (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
        )
        final_decision = final_decisions["events"][0]
        assert final_decision["final_decision_source"] == "ai_adjudicator"
        assert final_decision["final_case_type"] == "irrelevant"
        assert final_decision["final_queue"] == "ignore"
        assert final_decision["final_action"] == "ignore"
        assert provider_calls == [None]
    finally:
        _remove_fake_package("test_stub_adj_tender_digest")


def test_tender_adjudicator_provider_failure_routes_projection_and_final(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.rop_ai_adjudicator.call_openai_responses_api",
        lambda **kwargs: None,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _adjudicator_enabled_settings()
    settings["rop"]["sources"] = [
        _write_adjudicator_batch_source(
            tmp_path,
            "test-adj-tender-failure",
            "batch_tender_failure.json",
            [
                {
                    "event_id": "evt-tender-failure",
                    "sender": "tenders@example.test",
                    "subject": "Tender invitation",
                    "body": "Tender invitation for review.",
                }
            ],
        )
    ]
    stub_class = _make_deterministic_adjudicator_stub(
        case_type="new_lead",
        case_subtype="tender",
        recommended_queue="tender",
        correct_action="review_tender",
        confidence=0.95,
        reason_code="tender_or_rfq_detected",
    )
    _make_fake_package("test_stub_adj_tender_failure", "RopModule", stub_class)
    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "beeagent-rop",
                    "package": "test_stub_adj_tender_failure",
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
            run_id="run-adj-tender-failure",
            session_id="session-adj-tender-failure",
        )

        run_dir = tmp_path / "runs" / "run-adj-tender-failure"
        result = json.loads(
            (run_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
        )["results"][0]
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )[0]
        final = json.loads(
            (run_dir / "rop_final_decisions.json").read_text(encoding="utf-8")
        )["events"][0]

        assert result["ai_status"] == "degraded"
        assert result["deterministic_recommended_queue"] == "tender"
        assert result["deterministic_correct_action"] == "review_tender"
        assert result["final_recommended_queue"] == "tender"
        assert result["final_correct_action"] == "review_tender"
        assert classified["deterministic_recommended_queue"] == "tender"
        assert classified["deterministic_correct_action"] == "review_tender"
        assert classified["recommended_queue"] == "tender"
        assert classified["correct_action"] == "review_tender"
        assert final["deterministic_queue"] == "tender"
        assert final["deterministic_action"] == "review_tender"
        assert final["final_queue"] == "tender"
        assert final["final_action"] == "review_tender"
        assert final["needs_attention"] is True
    finally:
        _remove_fake_package("test_stub_adj_tender_failure")


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


def test_ai_adjudicator_low_confidence_preserves_deterministic_result(
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
        assert event["ai_adjudicator_status"] == "deterministic_preserved"
        assert event["reason_code"] == "deterministic_fallback"
        assert (
            event["ai_adjudicator_merge_reason"]
            == "ai_output_invalid_deterministic_result_preserved"
        )

        ai_results = json.loads(
            (run_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
        )
        assert ai_results["results"][0]["ai_status"] == "deterministic_preserved"
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
            "reason_code": "existing_deal_reference_signal",
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
    assert events[0]["reason_code"] == "existing_deal_reference_signal"
    assert events[0]["ai_adjudicator_merge_reason"] == (
        "validated_ai_adjudicator_output"
    )
    assert events[0]["reasoning"] == "AI accepted no subtype"


def test_ai_adjudicator_deterministic_preserved_keeps_classified_events() -> None:
    from beeagent_module.cases.rop_operator import _apply_ai_adjudicator_results

    events = [
        {
            "event_id": "evt-deterministic-preserved",
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
            "event_id": "evt-deterministic-preserved",
            "ai_used": True,
            "ai_status": "deterministic_preserved",
            "ai_confidence": 0.35,
            "ai_reason": "Looks risky",
            "ai_risk_flags": ["low_signal"],
            "merge_reason": "ai_output_conflict_deterministic_result_preserved",
            "final_case_type": "existing_deal",
            "final_case_subtype": "existing_deal_procurement",
            "final_recommended_queue": "procurement",
            "final_correct_action": "check_bitrix",
            "final_should_rop_see": True,
        }
    ]

    _apply_ai_adjudicator_results(events, results)

    assert events[0]["case_type"] == "existing_deal"
    assert events[0]["case_subtype"] == "existing_deal_procurement"
    assert events[0]["recommended_queue"] == "procurement"
    assert events[0]["correct_action"] == "check_bitrix"
    assert events[0]["confidence"] == 0.91
    assert events[0]["reason_code"] == "existing_deal_reference_signal"
    assert events[0]["ai_adjudicator_status"] == "deterministic_preserved"
    assert events[0]["ai_adjudicator_merge_reason"] == (
        "ai_output_conflict_deterministic_result_preserved"
    )


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
    import ast

    allowed = {
        "src/beeagent_module/interfaces/ui/reason_catalog.py": {
            ("beeagent_rop.contracts", "ClassificationReasonCode"),
        },
    }
    violations = []
    source_root = _project_root() / "src" / "beeagent_module"
    for path in source_root.rglob("*.py"):
        relative_path = str(path.relative_to(_project_root()))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("beeagent_rop")
            ):
                for alias in node.names:
                    if (node.module, alias.name) not in allowed.get(
                        relative_path, set()
                    ):
                        violations.append(
                            f"{relative_path}: from {node.module} import {alias.name}"
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("beeagent_rop"):
                        violations.append(f"{relative_path}: import {alias.name}")

    assert not violations, (
        f"Found direct beeagent_rop imports:\n{'\n'.join(violations)}"
    )


def test_classification_reason_catalog_covers_public_contract() -> None:
    from beeagent_module.interfaces.ui.reason_catalog import (
        check_classification_coverage,
        check_reason_catalog_coverage,
    )

    assert check_classification_coverage() == []
    assert check_reason_catalog_coverage() == []


def test_reason_catalog_distinguishes_legacy_and_unknown_codes() -> None:
    from beeagent_module.interfaces.ui.reason_catalog import (
        get_ai_reason_display,
        get_attention_reason_display,
    )

    legacy_display, legacy_warning = get_ai_reason_display(
        None,
        "ru",
        merge_reason="ai_output_conflict_manual_review",
    )
    unknown_display, unknown_warning = get_attention_reason_display(
        "unavailable_code",
        "ru",
    )
    legacy_attention_display, legacy_attention_warning = get_attention_reason_display(
        None,
        "ru",
        merge_reason="ai_output_conflict_manual_review",
    )

    assert "ручн" in legacy_display.lower()
    assert legacy_warning == "legacy ai_reason_code missing"
    assert "Неизвестный" in unknown_display
    assert unknown_warning == (
        "Код причины внимания неизвестен. Показано безопасное совместимое объяснение."
    )
    assert "ручн" in legacy_attention_display.lower()
    assert legacy_attention_warning == (
        "Старый формат итогового решения: код причины внимания отсутствует. "
        "Показано совместимое объяснение; данные не изменялись."
    )


def test_reason_catalog_bounds_unknown_codes_and_uses_legacy_status() -> None:
    from beeagent_module.interfaces.ui.reason_catalog import (
        get_ai_reason_display,
        get_classification_reason_display,
    )

    oversized_code = "<script>unknown</script>" + "x" * 100
    display, warning = get_classification_reason_display(oversized_code, "en")
    legacy_display, legacy_warning = get_ai_reason_display(
        None,
        "en",
        ai_status="manual_review_degrade",
    )

    assert display == "Unknown reason code; localized explanation unavailable"
    assert warning == ("unknown classification reason_code: " + oversized_code[:80])
    assert legacy_display == "AI adjudicator routed the event to manual review"
    assert legacy_warning == "legacy ai_reason_code missing"
