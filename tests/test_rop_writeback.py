from __future__ import annotations

import json
import logging
import os
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from beeagent_module.adapters.bitrix_client import (
    ALLOWED_METHODS,
    BitrixMethodNotAllowed,
    BitrixReadonlyClient,
)
from beeagent_module.adapters.bitrix_write_client import (
    WRITE_ALLOWED_METHODS,
    BitrixWriteClient,
    build_bitrix_write_client,
)
from beeagent_module.cases.rop_bitrix_reconciliation import run_reconciliation
from beeagent_module.cases.rop_writeback import (
    WRITEBACK_STATE_FILENAME,
    WRITEBACK_SUMMARY_FILENAME,
    _load_state,
    _origin_id,
    _stable_identity,
    _stable_remote_id,
    build_writeback_plan,
    execute_writeback_pending,
    refresh_recoverable_writeback_prerequisites,
)
from beeagent_module.core.cli import create_rop_parser
from beeagent_module.core.settings import load_settings, validate_settings

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")
os.environ.setdefault("BEEAGENT_WEB_OPERATOR_TOKEN", "test-operator-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_writeback")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _writeback_settings(
    enabled: bool = True,
    stages: dict[str, str] | None = None,
    dry_run: bool = False,
    attempts_retry_max: int = 3,
    webhook_env: str = "BITRIX_WRITEBACK_WEBHOOK_URL",
    email_attach: bool = False,
    email_completed: bool = True,
    source_id: str = "",
    user_id_fallback: int | None = None,
) -> dict:
    writeback: dict[str, Any] = {
        "enabled": enabled,
        "webhook_env": webhook_env,
        "timeout": 10,
        "attempts_retry_max": attempts_retry_max,
        "dry_run": dry_run,
        "email_attach": email_attach,
        "email_completed": email_completed,
        "source_id": source_id,
        "stages": stages or {"new_lead": "NEW", "irrelevant": "NEW"},
    }
    if user_id_fallback is not None:
        writeback["user_id_fallback"] = user_id_fallback
    return {
        "bitrix": {
            "enabled": True,
            "webhook_env": "BITRIX_WEBHOOK_URL",
            "timeout": 10,
            "page_size": 50,
            "pages_max": 3,
            "types_entity": [1, 2, 3, 4],
            "reconciliation": {
                "enabled": True,
                "candidate_limit": 20,
                "window_date": 180,
                "correlation": {
                    "enabled": True,
                    "window_days": 180,
                },
            },
            "writeback": writeback,
        },
        "rop": {"sources": [], "routing": {"queues": {}}},
    }


@pytest.fixture
def writeback_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BITRIX_WEBHOOK_URL", "https://portal.test/rest/1/readonlytoken/"
    )
    monkeypatch.setenv(
        "BITRIX_WRITEBACK_WEBHOOK_URL", "https://portal.test/rest/1/writetoken/"
    )


def _classified_event(
    event_id: str,
    case_type: str,
    *,
    instance: str = "inst-1",
    client_id: str = "welding",
    source_id: str = "hotline_mailbox",
    should_rop_see: bool = True,
    message_id: str | None = None,
    x_email_id: str | None = None,
    in_reply_to: str = "",
    references: str = "",
    subject: str = "Test subject",
    sender: str = "",
    from_name: str = "",
    body_preview: str = "",
    forwarded_wrapper: bool = False,
    original_sender: str = "",
    original_sender_email: str = "",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_instance_id": instance,
        "client_id": client_id,
        "source_id": source_id,
        "case_type": case_type,
        "should_rop_see": should_rop_see,
        "message_id": message_id,
        "x_email_id": x_email_id,
        "in_reply_to": in_reply_to,
        "references": references,
        "subject": subject,
        "sender": sender,
        "from_name": from_name,
        "body_preview": body_preview,
        "forwarded_wrapper": forwarded_wrapper,
        "original_sender": original_sender,
        "original_sender_email": original_sender_email,
    }


def _decision(
    event_id: str,
    final_case_type: str,
    instance: str = "inst-1",
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_instance_id": instance,
        "final_case_type": final_case_type,
    }


def _recon_item(
    event_id: str,
    status: str,
    *,
    instance: str = "inst-1",
    safe: bool = False,
    entity_type: str = "",
    entity_id: int | None = None,
    responsible_id: int | None = 42,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_instance_id": instance,
        "bitrix_match_status": status,
        "bitrix_match_quality": status,
        "safe_to_use_as_target": safe,
        "bitrix_entity_type": entity_type,
        "bitrix_entity_type_id": {"lead": 1, "deal": 2}.get(entity_type),
        "bitrix_entity_id": entity_id,
        "bitrix_responsible_id": responsible_id,
        "needs_manual_review": not safe,
    }


def _routing_item(
    event_id: str,
    responsible_status: str = "matched",
    *,
    instance: str = "inst-1",
    user_id: int | None = 42,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_instance_id": instance,
        "responsible": {
            "status": responsible_status,
            "user_id": user_id,
            "reason": None,
        },
    }


def _write_artifacts(
    run_dir: Path,
    classified: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
    routing: list[dict[str, Any]] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps({"summary": {"total_events": len(decisions)}, "events": decisions}),
        encoding="utf-8",
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps({"items": reconciliation}, ensure_ascii=False), encoding="utf-8"
    )
    if routing is not None:
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps({"items": routing}, ensure_ascii=False), encoding="utf-8"
        )


def _seed_state(storage_dir: Path, records: list[dict[str, Any]]) -> None:
    path = storage_dir / "interfaces" / WRITEBACK_STATE_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "version": 1,
        "policy_snapshot": {},
        "events": {record["identity"]: record for record in records},
        "runs": {},
        "updated_at_utc": "2026-08-19T00:00:00Z",
    }
    path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _created_lead_record(
    message_id: str,
    *,
    client_id: str = "welding",
    source_id: str = "hotline_mailbox",
    remote_entity_id: int = 1001,
    responsible: int = 42,
) -> dict[str, Any]:
    identity = _stable_identity(client_id, source_id, message_id)
    return {
        "identity": identity,
        "client_id": client_id,
        "source_id": source_id,
        "remote_id": message_id,
        "message_id": message_id,
        "event_id": f"evt-{message_id}",
        "outcome": "create_lead",
        "status": "created",
        "remote_entity_type_id": 1,
        "remote_entity_id": remote_entity_id,
        "responsible_user_id": responsible,
        "target_provenance": "beeagent_created",
        "origin_id": _origin_id(identity),
        "originator_id": "beeagent-rop",
    }


def _attached_thread_record(
    message_id: str,
    *,
    client_id: str = "welding",
    source_id: str = "hotline_mailbox",
    target_entity_type: str = "lead",
    target_entity_type_id: int = 1,
    target_entity_id: int = 1001,
    responsible: int = 42,
    target_provenance: str = "thread_resolved",
) -> dict[str, Any]:
    identity = _stable_identity(client_id, source_id, message_id)
    return {
        "identity": identity,
        "client_id": client_id,
        "source_id": source_id,
        "remote_id": message_id,
        "message_id": message_id,
        "event_id": f"evt-{message_id}",
        "outcome": "attach_existing",
        "status": "attached",
        "target_entity_type": target_entity_type,
        "target_entity_type_id": target_entity_type_id,
        "target_entity_id": target_entity_id,
        "target_responsible_user_id": responsible,
        "target_provenance": target_provenance,
        "origin_id": _origin_id(identity),
        "originator_id": "beeagent-rop",
    }


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _HttpRecorder:
    def __init__(self, handler: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        self._handler = handler

    def __call__(self, request: Any, *args: Any, **kwargs: Any) -> _FakeResponse:
        url = str(request.full_url)
        method = url.rsplit("/", 1)[-1]
        raw = request.data if request.data else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError, UnicodeDecodeError:
            payload = None
        self.calls.append({"url": url, "method": method, "payload": payload})
        return _FakeResponse(self._handler(self.calls[-1]))


def _default_handler(call: dict[str, Any]) -> bytes:
    method = call["method"]
    if method == "crm.status.list":
        return json.dumps(
            {
                "result": [
                    {"ENTITY_ID": "STATUS", "STATUS_ID": "NEW"},
                    {"ENTITY_ID": "STATUS", "STATUS_ID": "IN_PROCESS"},
                ]
            }
        ).encode("utf-8")
    if method == "crm.item.list":
        return json.dumps({"result": {"items": []}}).encode("utf-8")
    if method == "crm.activity.list":
        return json.dumps({"result": []}).encode("utf-8")
    if method == "crm.item.add":
        return json.dumps({"result": {"item": {"id": 1001}}}).encode("utf-8")
    if method == "crm.activity.add":
        return json.dumps({"result": 9001}).encode("utf-8")
    raise AssertionError(f"unexpected method: {method}")


def _patch_http(recorder: _HttpRecorder) -> Any:
    return (
        patch("beeagent_module.adapters.bitrix_client.urlopen", recorder),
        patch("beeagent_module.adapters.bitrix_write_client.urlopen", recorder),
    )


class TestWritebackSettingsValidation:
    @pytest.fixture(autouse=True)
    def _writeback_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(
            "BITRIX_WEBHOOK_URL", "https://portal.test/rest/1/readonlytoken/"
        )
        monkeypatch.setenv(
            "BITRIX_WRITEBACK_WEBHOOK_URL",
            "https://portal.test/rest/1/writetoken/",
        )

    def _load(self) -> dict:
        return load_settings(_PROJECT_ROOT / "config" / "settings.yml")

    def test_writeback_disabled_by_default(self) -> None:
        settings = self._load()
        writeback = settings["bitrix"]["writeback"]
        assert writeback["enabled"] is False
        assert writeback["webhook_env"] == "BITRIX_WRITEBACK_WEBHOOK_URL"
        assert writeback["attempts_retry_max"] == 3
        assert writeback["email_attach"] is True
        validate_settings(settings)

    def test_env_example_declares_writeback_credential(self) -> None:
        assert "BITRIX_WRITEBACK_WEBHOOK_URL=\n" in (
            _PROJECT_ROOT / ".env.example"
        ).read_text(encoding="utf-8")

    @pytest.mark.parametrize("value", [True, "1563", 0, -1, 1.5])
    def test_user_id_fallback_invalid_rejected(self, value: Any) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["user_id_fallback"] = value
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "user_id_fallback" in str(exc_info.value)

    def test_user_id_fallback_valid_accepted(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["user_id_fallback"] = 1563
        validate_settings(settings)

    @pytest.mark.parametrize("value", ["X", "Y", "N", "yes", "true", 1, 0])
    def test_email_completed_invalid_rejected(self, value: Any) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["email_completed"] = value
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "email_completed" in str(exc_info.value)

    @pytest.mark.parametrize("value", [True, False])
    def test_email_completed_valid_accepted(self, value: bool) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["email_completed"] = value
        validate_settings(settings)

    def test_legacy_email_attach_completed_is_rejected(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["email_attach_completed"] = True
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "email_completed" in str(exc_info.value)

    def test_legacy_email_activity_completed_is_rejected(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["email_activity_completed"] = True
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "email_completed" in str(exc_info.value)

    def test_writeback_enabled_requires_bitrix_enabled(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True
        settings["bitrix"]["enabled"] = False
        settings["bitrix"]["reconciliation"]["enabled"] = False
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "bitrix.writeback.enabled requires" in str(exc_info.value)

    def test_writeback_enabled_requires_reconciliation_enabled(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True
        settings["bitrix"]["reconciliation"]["enabled"] = False
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "bitrix.reconciliation.enabled" in str(exc_info.value)

    def test_writeback_enabled_requires_stages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BITRIX_WRITEBACK_WEBHOOK_URL", "https://x.test/")
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True
        settings["bitrix"]["writeback"]["stages"] = {"new_lead": "NEW"}
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "irrelevant" in str(exc_info.value)

    def test_writeback_enabled_requires_empty_stage_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BITRIX_WRITEBACK_WEBHOOK_URL", "https://x.test/")
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True
        settings["bitrix"]["writeback"]["stages"] = {
            "new_lead": "",
            "irrelevant": "NEW",
        }
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "new_lead" in str(exc_info.value)

    def test_writeback_enabled_requires_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BITRIX_WRITEBACK_WEBHOOK_URL", raising=False)
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True
        settings["bitrix"]["writeback"]["stages"] = {
            "new_lead": "NEW",
            "irrelevant": "NEW",
        }
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "BITRIX_WRITEBACK_WEBHOOK_URL" in str(exc_info.value)

    def test_unsupported_stage_keys_rejected(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["stages"]["deal"] = "STAGE1"
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "deal" in str(exc_info.value)

    def test_email_attach_must_be_bool(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["email_attach"] = "yes"
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "email_attach" in str(exc_info.value)

    def test_retry_attempts_max_is_rejected(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["retry_attempts_max"] = 3
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "retry_attempts_max" in str(exc_info.value)

    def test_attach_email_is_rejected(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["attach_email"] = True
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "attach_email" in str(exc_info.value)

    def test_legacy_fallback_responsible_user_id_is_rejected(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["fallback_responsible_user_id"] = 1563
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "fallback_responsible_user_id" in str(exc_info.value)

    def test_source_id_must_be_string_or_null(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["source_id"] = 123
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "source_id" in str(exc_info.value)

    def test_writeback_rejects_same_read_and_write_env_name(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True
        settings["bitrix"]["writeback"]["webhook_env"] = "BITRIX_WEBHOOK_URL"

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)

        assert "must differ" in str(exc_info.value)
        assert "readonlytoken" not in str(exc_info.value)

    def test_writeback_rejects_same_credential_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "BITRIX_WRITEBACK_WEBHOOK_URL", "https://same.test/rest/1/x/"
        )
        monkeypatch.setenv("BITRIX_WEBHOOK_URL", "https://same.test/rest/1/x")
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)

        assert "credentials must be distinct" in str(exc_info.value)
        assert "https://" not in str(exc_info.value)

    def test_writeback_accepts_distinct_credential_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BITRIX_WEBHOOK_URL", "https://read.test/rest/1/x/")
        monkeypatch.setenv(
            "BITRIX_WRITEBACK_WEBHOOK_URL", "https://write.test/rest/1/y/"
        )
        settings = self._load()
        settings["bitrix"]["writeback"]["enabled"] = True

        validate_settings(settings)


class TestWriteClientBoundary:
    def test_write_allowed_methods_are_bounded(self) -> None:
        assert WRITE_ALLOWED_METHODS == frozenset({"crm.item.add", "crm.activity.add"})

    def test_readonly_client_rejects_write_methods(self) -> None:
        assert "crm.item.add" not in ALLOWED_METHODS
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        with pytest.raises(BitrixMethodNotAllowed):
            client.call("crm.item.add", {"entityTypeId": 1})

    def test_write_client_rejects_non_allowlisted_methods(self) -> None:
        client = BitrixWriteClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        for method in (
            "crm.lead.add",
            "crm.item.update",
            "crm.item.delete",
            "crm.item.list",
            "user.get",
        ):
            with pytest.raises(BitrixMethodNotAllowed) as exc_info:
                client.call(method, {})
            assert "not in allowed list" in str(exc_info.value)

    def test_write_client_rejects_insecure_url(self) -> None:
        with pytest.raises(Exception) as exc_info:
            BitrixWriteClient(webhook_url="http://insecure.url/", timeout=5)
        assert "HTTPS" in str(exc_info.value)

    def test_add_lead_posts_crm_item_add_entity_type_1(self) -> None:
        client = BitrixWriteClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps({"result": {"item": {"id": 777}}}).encode("utf-8")
        with patch(
            "beeagent_module.adapters.bitrix_write_client.urlopen",
            return_value=_FakeResponse(body),
        ) as mocked_urlopen:
            item_id = client.add_lead(
                {"TITLE": "Lead", "STAGE_ID": "NEW", "ASSIGNED_BY_ID": 5}
            )

        assert item_id == 777
        request = mocked_urlopen.call_args.args[0]
        assert request.full_url.endswith("/crm.item.add")
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["entityTypeId"] == 1
        assert payload["fields"]["STAGE_ID"] == "NEW"

    def test_add_lead_malformed_result_raises(self) -> None:
        from beeagent_module.adapters.bitrix_client import BitrixMalformedResponse

        client = BitrixWriteClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps({"result": {"item": {}}}).encode("utf-8")
        with (
            patch(
                "beeagent_module.adapters.bitrix_write_client.urlopen",
                return_value=_FakeResponse(body),
            ),
            pytest.raises(BitrixMalformedResponse),
        ):
            client.add_lead({"TITLE": "Lead"})

    def test_add_email_activity_posts_crm_activity_add(self) -> None:
        client = BitrixWriteClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps({"result": 9001}).encode("utf-8")
        with patch(
            "beeagent_module.adapters.bitrix_write_client.urlopen",
            return_value=_FakeResponse(body),
        ) as mocked_urlopen:
            activity_id = client.add_email_activity(
                owner_entity_type_id=1,
                owner_id=199263,
                responsible_id=42,
                origin_id="welding|hotline_mailbox|<msg-1@example.test>",
                subject="Subject",
                description="Body",
                sender_email="sender@example.com",
            )

        assert activity_id == 9001
        request = mocked_urlopen.call_args.args[0]
        assert request.full_url.endswith("/crm.activity.add")
        payload = json.loads(request.data.decode("utf-8"))
        fields = payload["fields"]
        assert fields["TYPE_ID"] == 4
        assert fields["OWNER_TYPE_ID"] == 1
        assert fields["OWNER_ID"] == 199263
        assert fields["RESPONSIBLE_ID"] == 42
        assert fields["PROVIDER_ID"] == "beeagent-rop"
        assert fields["PROVIDER_TYPE_ID"] == "welding|hotline_mailbox|<msg-1@example.test>"
        assert fields["COMPLETED"] == "Y"
        assert fields["COMMUNICATIONS"][0]["VALUE"] == "sender@example.com"
        assert fields["COMMUNICATIONS"][0]["TYPE"] == "EMAIL"

    def test_add_email_activity_posts_completed_n_when_requested(self) -> None:
        client = BitrixWriteClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps({"result": 9002}).encode("utf-8")
        with patch(
            "beeagent_module.adapters.bitrix_write_client.urlopen",
            return_value=_FakeResponse(body),
        ) as mocked_urlopen:
            client.add_email_activity(
                owner_entity_type_id=1,
                owner_id=199263,
                responsible_id=42,
                origin_id="welding|hotline_mailbox|<msg-1@example.test>",
                subject="Subject",
                description="Body",
                sender_email="sender@example.com",
                completed="N",
            )

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["fields"]["COMPLETED"] == "N"

    def test_build_write_client_uses_dedicated_env(self, writeback_env: None) -> None:
        client = build_bitrix_write_client(_writeback_settings())
        assert client._webhook_url.rstrip("/") == (
            "https://portal.test/rest/1/writetoken"
        )


class TestWritebackPlanner:
    def test_irrelevant_with_should_rop_see_false_enters_planning(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "irrelevant",
                    should_rop_see=False,
                    message_id="<msg-1@example.test>",
                )
            ],
            decisions=[_decision("evt-1", "irrelevant")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["case_type"] == "irrelevant"
        assert record["should_rop_see"] is False
        assert record["outcome"] == "create_lead"
        assert record["stage_id"] == "NEW"
        assert record["responsible_user_id"] == 42

    def test_new_lead_without_target_creates_lead(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1", "new_lead", message_id="<msg-1@example.test>", subject="Buy equipment"
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["stage_id"] == "NEW"
        assert record["responsible_user_id"] == 42
        assert record["originator_id"] == "beeagent-rop"
        assert record["origin_id"] == _origin_id(
            _stable_identity("welding", "hotline_mailbox", "<msg-1@example.test>")
        )

    def test_exact_reply_attaches_to_trusted_lead_no_new_lead(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_type"] == "lead"
        assert record["target_entity_id"] == 253

    def test_legacy_safe_reconciliation_cannot_authorize_deal_attach(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "existing_deal", message_id="<msg-1@example.test>")
            ],
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_deal",
                    safe=True,
                    entity_type="deal",
                    entity_id=88,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "unsafe_target"
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["writes_performed"] == 0
        assert not [
            call
            for call in recorder.calls
            if call["method"] in {"crm.item.add", "crm.activity.add"}
        ]

    def test_reconciled_related_deal_identity_defers_without_mutation(
        self,
        tmp_path: Path,
        writeback_env: None,
    ) -> None:
        run_id = "run-related-deal"
        run_dir = tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True)
        classified = [
            _classified_event(
                "evt-1",
                "existing_deal",
                message_id="<msg-1@example.test>",
                sender="client@example.com",
                instance="inst-old-contact",
            )
        ]
        classified[0]["received_at"] = "2026-08-19T12:00:00+00:00"
        (run_dir / "normalized_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        (run_dir / "rop_final_decisions.json").write_text(
            json.dumps({"events": [_decision("evt-1", "existing_deal")]}),
            encoding="utf-8",
        )
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps({"items": [_routing_item("evt-1", "matched", user_id=42)]}),
            encoding="utf-8",
        )

        class _RelatedDealClient:
            def __init__(self) -> None:
                self.searches: list[tuple[int, str, dict[str, Any]]] = []

            def get_portal_url(self) -> str:
                return "https://portal.test"

            def search_candidates(
                self, entity_type_id: int, query: str, **kwargs: Any
            ) -> list[dict[str, Any]]:
                self.searches.append((entity_type_id, query, kwargs))
                if entity_type_id == 3:
                    return [
                        {
                            "ID": "42",
                            "EMAIL": [{"VALUE": "client@example.com"}],
                            "DATE_CREATE": "2025-01-01T00:00:00+00:00",
                        }
                    ]
                return []

            def search_related_deals(
                self, entity_type_id: int, entity_id: int
            ) -> list[dict[str, Any]]:
                assert (entity_type_id, entity_id) == (3, 42)
                return [
                    {
                        "id": 88,
                        "title": "Existing deal",
                        "assignedById": 901,
                        "contactId": 42,
                    }
                ]

        import beeagent_module.cases.rop_bitrix_reconciliation as recon_mod

        settings = _writeback_settings(email_attach=True)
        related_client = _RelatedDealClient()
        with patch.object(
            recon_mod,
            "build_bitrix_client",
            return_value=related_client,
        ):
            reconciliation = run_reconciliation(
                tmp_path, run_id, settings, _null_logger()
            )
        assert reconciliation["items"][0]["bitrix_match_status"] == "matched_deal"
        assert reconciliation["items"][0]["safe_to_use_as_target"] is False
        relation_searches = [
            kwargs
            for entity_type_id, _query, kwargs in related_client.searches
            if entity_type_id in (3, 4)
        ]
        assert relation_searches
        assert all(kwargs.get("date_from") is None for kwargs in relation_searches)

        plan = build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        assert plan["events"][0]["outcome"] == "deferred"
        assert plan["events"][0]["reason_code"] == "unsafe_target"

        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            first = execute_writeback_pending(
                tmp_path, run_id, settings, _null_logger()
            )
            second = execute_writeback_pending(
                tmp_path, run_id, settings, _null_logger()
            )
        assert first["writes_performed"] == 0
        assert second["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        assert "crm.activity.add" not in methods

    @pytest.mark.parametrize(
        ("case_type", "identity_entity_type", "creates_lead"),
        [
            ("new_lead", 3, True),
            ("irrelevant", 4, True),
            ("existing_deal", 3, False),
            ("duplicate", 4, False),
        ],
    )
    def test_exact_identity_without_safe_target_only_creates_for_create_cases(
        self,
        tmp_path: Path,
        writeback_env: None,
        case_type: str,
        identity_entity_type: int,
        creates_lead: bool,
    ) -> None:
        run_id = f"run-identity-{case_type}-{identity_entity_type}"
        run_dir = tmp_path / "runs" / run_id
        event = _classified_event(
            "evt-1",
            case_type,
            message_id="<msg-1@example.test>",
            sender="client@example.com",
        )
        event["received_at"] = "2026-08-19T12:00:00+00:00"
        _write_artifacts(
            run_dir,
            classified=[event],
            decisions=[_decision("evt-1", case_type)],
            reconciliation=[],
            routing=[_routing_item("evt-1", "matched", user_id=42)],
        )
        (run_dir / "normalized_events.json").write_text(
            json.dumps([event]), encoding="utf-8"
        )

        class _IdentityClient:
            def get_portal_url(self) -> str:
                return "https://portal.test"

            def search_candidates(
                self, entity_type_id: int, _query: str, **_kwargs: Any
            ) -> list[dict[str, Any]]:
                if entity_type_id == identity_entity_type:
                    return [
                        {
                            "ID": "42",
                            "EMAIL": [{"VALUE": "client@example.com"}],
                        }
                    ]
                return []

            def search_related_deals(self, *_args: Any) -> list[dict[str, Any]]:
                return []

        import beeagent_module.cases.rop_bitrix_reconciliation as recon_mod

        settings = _writeback_settings(email_attach=True)
        with patch.object(
            recon_mod,
            "build_bitrix_client",
            return_value=_IdentityClient(),
        ):
            reconciliation = run_reconciliation(
                tmp_path, run_id, settings, _null_logger()
            )
        item = reconciliation["items"][0]
        assert item["bitrix_match_status"] == "identity_only_no_target"
        assert item["suitable_target_search"] == "completed_no_target"
        assert item["safe_to_use_as_target"] is False
        assert item["bitrix_entity_type"] == ""
        assert item["bitrix_entity_id"] is None

        plan = build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        record = plan["events"][0]
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            first = execute_writeback_pending(
                tmp_path, run_id, settings, _null_logger()
            )
            second = execute_writeback_pending(
                tmp_path, run_id, settings, _null_logger()
            )

        mutations = [
            call
            for call in recorder.calls
            if call["method"] in {"crm.item.add", "crm.activity.add"}
        ]
        if creates_lead:
            assert record["outcome"] == "create_lead"
            assert record["responsible_user_id"] == 42
            assert record["stage_id"] == "NEW"
            assert first["writes_performed"] == 2
            assert second["writes_performed"] == 0
            assert [call["method"] for call in mutations] == [
                "crm.item.add",
                "crm.activity.add",
            ]
            create = mutations[0]["payload"]["fields"]
            assert create["ASSIGNED_BY_ID"] == 42
            assert create["STAGE_ID"] == "NEW"
            assert create["fm"][0]["value"] == "client@example.com"
            activity = mutations[1]["payload"]["fields"]
            assert activity["OWNER_TYPE_ID"] == 1
            assert activity["OWNER_ID"] == 1001
        else:
            assert record["outcome"] == "deferred"
            assert record["reason_code"] == "case_type_not_create_eligible"
            assert first["writes_performed"] == 0
            assert second["writes_performed"] == 0
            assert mutations == []

    def test_competing_exact_lead_and_related_deal_new_lead_creates_independently(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_id = "run-competing-target"
        run_dir = tmp_path / "runs" / run_id
        event = _classified_event(
            "evt-1",
            "new_lead",
            message_id="<msg-1@example.test>",
            sender="client@example.com",
        )
        event["received_at"] = "2026-08-19T12:00:00+00:00"
        _write_artifacts(
            run_dir,
            classified=[event],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[],
            routing=[_routing_item("evt-1", "matched")],
        )
        (run_dir / "normalized_events.json").write_text(
            json.dumps([event]), encoding="utf-8"
        )

        class _CompetingTargetClient:
            def get_portal_url(self) -> str:
                return "https://portal.test"

            def search_candidates(
                self, entity_type_id: int, _query: str, **_kwargs: Any
            ) -> list[dict[str, Any]]:
                if entity_type_id == 1:
                    return [
                        {
                            "ID": "253",
                            "EMAIL": [{"VALUE": "client@example.com"}],
                        }
                    ]
                if entity_type_id == 3:
                    return [
                        {
                            "ID": "42",
                            "EMAIL": [{"VALUE": "client@example.com"}],
                        }
                    ]
                return []

            def search_related_deals(self, *_args: Any) -> list[dict[str, Any]]:
                return [{"id": 88, "title": "Existing deal"}]

        import beeagent_module.cases.rop_bitrix_reconciliation as recon_mod

        settings = _writeback_settings(email_attach=True)
        with patch.object(
            recon_mod,
            "build_bitrix_client",
            return_value=_CompetingTargetClient(),
        ):
            reconciliation = run_reconciliation(
                tmp_path, run_id, settings, _null_logger()
            )
        item = reconciliation["items"][0]
        assert item["bitrix_match_status"] == "ambiguous"
        assert item["safe_to_use_as_target"] is False

        plan = build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, run_id, settings, _null_logger())
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" in methods
        create = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert create["payload"]["entityTypeId"] == 1

    def test_forwarded_existing_target_attaches_original_sender_once(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-forwarded-target"
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-root@example.test>",
                    target_entity_type="deal",
                    target_entity_type_id=2,
                    target_entity_id=88,
                    responsible=901,
                )
            ],
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "existing_deal",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="forwarder@internal.example",
                    forwarded_wrapper=True,
                    original_sender_email="customer@example.com",
                )
            ],
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-forwarded-target", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-forwarded-target", settings, _null_logger()
            )
            execute_writeback_pending(
                tmp_path, "run-forwarded-target", settings, _null_logger()
            )

        assert not [call for call in recorder.calls if call["method"] == "crm.item.add"]
        activities = [
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        ]
        assert len(activities) == 1
        assert (
            activities[0]["payload"]["fields"]["COMMUNICATIONS"][0]["VALUE"]
            == "customer@example.com"
        )

    def test_old_contact_with_multiple_related_deals_defers_without_mutation(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_id = "run-old-contact-multiple"
        run_dir = tmp_path / "runs" / run_id
        classified = [
            _classified_event(
                "evt-1",
                "existing_deal",
                message_id="<msg-1@example.test>",
                sender="client@example.com",
            )
        ]
        classified[0]["received_at"] = "2026-08-19T12:00:00+00:00"
        _write_artifacts(
            run_dir,
            classified=classified,
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[],
            routing=[_routing_item("evt-1", "matched")],
        )
        (run_dir / "normalized_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        class _RelatedDealClient:
            def get_portal_url(self) -> str:
                return "https://portal.test"

            def search_candidates(
                self, entity_type_id: int, _query: str, **kwargs: Any
            ) -> list[dict[str, Any]]:
                assert kwargs.get("date_from") is None
                if entity_type_id == 3:
                    return [
                        {
                            "ID": "42",
                            "EMAIL": [{"VALUE": "client@example.com"}],
                            "DATE_CREATE": "2025-01-01T00:00:00+00:00",
                        }
                    ]
                return []

            def search_related_deals(self, *_args: Any) -> list[dict[str, Any]]:
                return [{"id": 88, "title": "First"}, {"id": 89, "title": "Second"}]

        import beeagent_module.cases.rop_bitrix_reconciliation as recon_mod

        settings = _writeback_settings(email_attach=True)
        with patch.object(
            recon_mod,
            "build_bitrix_client",
            return_value=_RelatedDealClient(),
        ):
            reconciliation = run_reconciliation(
                tmp_path, run_id, settings, _null_logger()
            )
        assert reconciliation["items"][0]["bitrix_match_status"] == "ambiguous"

        plan = build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        assert plan["events"][0]["outcome"] == "deferred"
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, run_id, settings, _null_logger())
        assert not [
            call
            for call in recorder.calls
            if call["method"] in {"crm.item.add", "crm.activity.add"}
        ]

    def test_forwarded_new_lead_uses_original_sender_identity(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-forwarded-lead"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="forwarder@internal.example",
                    from_name="Internal Forwarder",
                    forwarded_wrapper=True,
                    original_sender=("Усова Анна Николаевна <customer@example.com>"),
                    original_sender_email="customer@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-forwarded-lead", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-forwarded-lead", settings, _null_logger()
            )
            execute_writeback_pending(
                tmp_path, "run-forwarded-lead", settings, _null_logger()
            )

        creates = [call for call in recorder.calls if call["method"] == "crm.item.add"]
        assert len(creates) == 1
        fields = creates[0]["payload"]["fields"]
        assert fields["NAME"] == "Усова Анна Николаевна"
        assert fields["fm"][0]["value"] == "customer@example.com"
        activity = next(
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        )
        assert activity["payload"]["fields"]["COMMUNICATIONS"][0]["VALUE"] == (
            "customer@example.com"
        )

    def test_forwarded_new_lead_without_display_name_omits_name(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-forwarded-no-name"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="internal-forwarder@welding.kz",
                    from_name="Internal Forwarder",
                    forwarded_wrapper=True,
                    original_sender="customer@example.com",
                    original_sender_email="customer@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings()
        build_writeback_plan(
            tmp_path, "run-forwarded-no-name", settings, _null_logger()
        )
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-forwarded-no-name", settings, _null_logger()
            )

        fields = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )["payload"]["fields"]
        assert fields["fm"][0]["value"] == "customer@example.com"
        assert "NAME" not in fields

    def test_legacy_safe_target_without_thread_uses_normal_create_path(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_lead",
                    safe=True,
                    entity_type="lead",
                    entity_id=253,
                    responsible_id=None,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_new_lead_with_existing_crm_lead_creates_not_attaches(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_lead",
                    safe=False,
                    entity_type="lead",
                    entity_id=253,
                    responsible_id=None,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None
        assert record["reason_code"] is None

    def test_existing_deal_without_target_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "existing_deal", message_id="<msg-1@example.test>")
            ],
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "case_type_not_create_eligible"

    def test_duplicate_never_silently_creates(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "duplicate", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "duplicate")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "case_type_not_create_eligible"

    def test_ambiguous_crm_evidence_new_lead_creates(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "ambiguous")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert [
            call["method"]
            for call in recorder.calls
            if call["method"] == "crm.item.add"
        ]

    def test_duplicate_candidate_new_lead_creates(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "duplicate_candidate")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["reason_code"] is None
        assert record["target_entity_id"] is None

    def test_weak_match_new_lead_creates(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "weak_match")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_existing_deal_duplicate_candidate_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "existing_deal", message_id="<msg-1@example.test>")
            ],
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[_recon_item("evt-1", "duplicate_candidate")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "duplicate_target"

    def test_semantic_duplicate_duplicate_candidate_defers(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "duplicate", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "duplicate")],
            reconciliation=[_recon_item("evt-1", "duplicate_candidate")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "duplicate_target"

    def test_unsafe_target_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "existing_deal", message_id="<msg-1@example.test>")
            ],
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_lead",
                    safe=False,
                    entity_type="lead",
                    entity_id=253,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "unsafe_target"

    def test_identity_only_lead_match_creates_for_new_lead(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="client@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_lead",
                    safe=False,
                    entity_type="lead",
                    entity_id=253,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["stage_id"] == "NEW"
        assert record["responsible_user_id"] == 42
        assert record["target_provenance"] is None

    def test_fallback_responsible_assigned_when_routing_not_found(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(user_id_fallback=1563),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["stage_id"] == "NEW"
        assert record["responsible_user_id"] == 1563
        assert record["responsible_status"] == "fallback"
        assert record["responsible_reason"] == "fallback_responsible_user"

    def test_fallback_responsible_ignored_when_routing_matched(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched", user_id=42)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(user_id_fallback=1563),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["responsible_user_id"] == 42
        assert record["responsible_status"] == "matched"

    def test_fallback_responsible_ignored_for_connector_degraded(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "connector_degraded", user_id=None)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(user_id_fallback=1563),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "responsible_unresolved"

    @pytest.mark.parametrize("status", ["ambiguous", "unresolved", "not_attempted"])
    def test_fallback_responsible_is_not_used_for_non_not_found_status(
        self, tmp_path: Path, status: str
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", status, user_id=None)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(user_id_fallback=1563),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "responsible_unresolved"

    def test_fallback_responsible_requires_configured_stage(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(stages={"new_lead": ""}, user_id_fallback=1563),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "stage_not_configured"

    def test_exact_reply_attaches_to_created_thread_root(self, tmp_path: Path) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_type"] == "lead"
        assert record["target_entity_type_id"] == 1
        assert record["target_entity_id"] == 1001
        assert record["target_responsible_user_id"] == 42
        assert record["target_provenance"] == "thread_resolved"
        assert record["case_type"] == "existing_deal"
        assert record["semantic_case_type"] == "new_lead"

    def test_malformed_prior_message_id_no_thread_resolved(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                {
                    "identity": _stable_identity(
                        "welding", "hotline_mailbox", "not-a-message-id"
                    ),
                    "client_id": "welding",
                    "source_id": "hotline_mailbox",
                    "remote_id": "not-a-message-id",
                    "message_id": "not-a-message-id",
                    "event_id": "evt-root",
                    "outcome": "create_lead",
                    "status": "created",
                    "remote_entity_type_id": 1,
                    "remote_entity_id": 1001,
                    "responsible_user_id": 42,
                    "target_provenance": "beeagent_created",
                    "origin_id": "x",
                    "originator_id": "beeagent-rop",
                }
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb-malformed"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="not-a-message-id",
                    references="not-a-message-id",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-malformed", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["case_type"] == "new_lead"
        assert record["semantic_case_type"] == "new_lead"
        assert record["target_provenance"] is None

    def test_oversized_message_ids_do_not_collide(self, tmp_path: Path) -> None:
        oversized_a = "x@" + ("a" * 400)
        oversized_b = "x@" + ("b" * 400)
        _seed_state(
            tmp_path,
            [
                {
                    "identity": _stable_identity(
                        "welding", "hotline_mailbox", oversized_a
                    ),
                    "client_id": "welding",
                    "source_id": "hotline_mailbox",
                    "remote_id": oversized_a,
                    "message_id": oversized_a,
                    "event_id": "evt-root-a",
                    "outcome": "create_lead",
                    "status": "created",
                    "remote_entity_type_id": 1,
                    "remote_entity_id": 1001,
                    "responsible_user_id": 42,
                    "target_provenance": "beeagent_created",
                    "origin_id": "x",
                    "originator_id": "beeagent-rop",
                },
                {
                    "identity": _stable_identity(
                        "welding", "hotline_mailbox", oversized_b
                    ),
                    "client_id": "welding",
                    "source_id": "hotline_mailbox",
                    "remote_id": oversized_b,
                    "message_id": oversized_b,
                    "event_id": "evt-root-b",
                    "outcome": "create_lead",
                    "status": "created",
                    "remote_entity_type_id": 1,
                    "remote_entity_id": 2002,
                    "responsible_user_id": 42,
                    "target_provenance": "beeagent_created",
                    "origin_id": "x",
                    "originator_id": "beeagent-rop",
                },
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb-oversized"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to=oversized_a,
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-oversized", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["case_type"] == "new_lead"
        assert record["target_provenance"] is None

    def test_exact_reply_across_source_ids_same_client_attaches(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                _created_lead_record(
                    "<msg-a@example.test>",
                    source_id="mailbox-a",
                    remote_entity_id=1001,
                )
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb-cross-source"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    source_id="mailbox-b",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-cross-source", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 1001
        assert record["target_provenance"] == "thread_resolved"
        assert record["case_type"] == "existing_deal"
        assert record["semantic_case_type"] == "new_lead"

    def test_exact_outbound_bridge_without_trusted_target_is_deferred(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb-outbound"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="out-1@employee.test",
                    references="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-outbound",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": True,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 77,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-outbound", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "outbound_candidate_untrusted"
        assert record["target_entity_id"] is None

    def test_exact_outbound_bridge_matching_trusted_target_attaches(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_attached_thread_record("<msg-a@example.test>", target_entity_id=3001)])
        run_dir = tmp_path / "runs" / "run-wb-outbound-trusted"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="out-1@employee.test",
                    references="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-outbound-trusted",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": True,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 42,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-outbound-trusted", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 3001
        assert record["target_responsible_user_id"] == 42
        assert record["target_provenance"] == "bitrix_outbound_exact"
        assert record["case_type"] == "existing_deal"
        assert record["semantic_case_type"] == "new_lead"

    def test_exact_outbound_bridge_responsible_mismatch_attaches_canonical(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_attached_thread_record("<msg-a@example.test>", target_entity_id=3001)])
        run_dir = tmp_path / "runs" / "run-wb-outbound-responsible-mismatch"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="out-1@employee.test",
                    references="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-outbound-responsible-mismatch",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": True,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 77,
                            "outbound_activity_responsible_user_id": 77,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb-outbound-responsible-mismatch",
            _writeback_settings(),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 3001
        assert record["target_responsible_user_id"] == 42
        assert record["target_provenance"] == "bitrix_outbound_exact"

    def test_live_outbound_bridge_end_to_end_attaches_trusted_lead(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_id = "run-wb-live-outbound"
        run_dir = tmp_path / "runs" / run_id
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-root@example.test>",
                    target_entity_type="lead",
                    target_entity_type_id=1,
                    target_entity_id=199425,
                    responsible=1563,
                )
            ],
        )
        event = _classified_event(
            "evt-reply",
            "new_lead",
            message_id="<msg-reply@example.test>",
            sender="client@example.com",
            in_reply_to="<crm.activity.1617905-0R9TBN@my.welding.kz>",
            references="<crm.activity.1617905-0R9TBN@my.welding.kz>",
        )
        _write_artifacts(
            run_dir,
            classified=[event],
            decisions=[_decision("evt-reply", "new_lead")],
            reconciliation=[],
            routing=[_routing_item("evt-reply", "matched")],
        )
        (run_dir / "normalized_events.json").write_text(
            json.dumps([event]), encoding="utf-8"
        )

        class _OutboundClient:
            def get_portal_url(self) -> str:
                return "https://portal.test"

            def search_candidates(self, *_args: Any, **_kwargs: Any) -> list:
                return []

            def search_related_deals(self, *_args: Any) -> list:
                return []

            def activity_list(
                self,
                filter_params: dict,
                select: list[str],
                start: int = 0,
            ) -> dict:
                return {
                    "result": [
                        {
                            "ID": 1617905,
                            "TYPE_ID": 4,
                            "OWNER_TYPE_ID": 1,
                            "OWNER_ID": 199425,
                            "RESPONSIBLE_ID": 1610,
                            "DIRECTION": 2,
                            "COMPLETED": "Y",
                            "SETTINGS": {
                                "MESSAGE_HEADERS": {
                                    "Message-Id": (
                                        "<crm.activity.1617905-0R9TBN@my.welding.kz>"
                                    )
                                }
                            },
                        }
                    ]
                }

        import beeagent_module.cases.rop_bitrix_reconciliation as recon_mod

        settings = _writeback_settings(email_attach=True)
        with patch.object(
            recon_mod, "build_bitrix_client", return_value=_OutboundClient()
        ):
            reconciliation = run_reconciliation(
                tmp_path, run_id, settings, _null_logger()
            )
        correlation = json.loads(
            (run_dir / "bitrix_outbound_correlation.json").read_text(encoding="utf-8")
        )
        assert len(correlation["evidence"]) == 1
        assert correlation["evidence"][0]["bridge_exact"] is True
        assert correlation["evidence"][0]["target_entity_id"] == 199425
        assert correlation["evidence"][0]["outbound_activity_responsible_user_id"] == (
            1610
        )

        plan = build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 199425
        assert record["target_responsible_user_id"] == 1563
        assert record["target_provenance"] == "bitrix_outbound_exact"
        assert record["case_type"] == "existing_deal"
        assert record["semantic_case_type"] == "new_lead"
        assert plan["aggregate"]["outcome_counts"]["create_lead"] == 0

        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, run_id, settings, _null_logger())
        assert not [call for call in recorder.calls if call["method"] == "crm.item.add"]

    def test_outbound_bridge_cross_client_not_authorized(self, tmp_path: Path) -> None:
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-a@example.test>", target_entity_id=3001, client_id="client-x"
                )
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb-outbound-cross-client"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    client_id="welding",
                    in_reply_to="out-1@employee.test",
                    references="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-outbound-cross-client",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": True,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 77,
                            "outbound_activity_responsible_user_id": 77,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb-outbound-cross-client",
            _writeback_settings(),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "outbound_candidate_untrusted"
        assert record["target_entity_id"] is None

    def test_outbound_bridge_cross_source_same_client_attaches(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-a@example.test>",
                    target_entity_id=3001,
                    source_id="hotline_mailbox",
                )
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb-outbound-cross-source"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    source_id="sales_mailbox",
                    in_reply_to="out-1@employee.test",
                    references="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-outbound-cross-source",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": True,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 42,
                            "outbound_activity_responsible_user_id": 42,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb-outbound-cross-source",
            _writeback_settings(),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 3001
        assert record["target_responsible_user_id"] == 42
        assert record["target_provenance"] == "bitrix_outbound_exact"

    def test_proven_outbound_bridge_propagates_to_next_hop(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-b@example.test>",
                    target_entity_id=3001,
                    target_provenance="bitrix_outbound_exact",
                )
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb-next-hop"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-c",
                    "new_lead",
                    message_id="<msg-c@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-b@example.test>",
                    references="<msg-b@example.test>",
                )
            ],
            decisions=[_decision("evt-c", "new_lead")],
            reconciliation=[_recon_item("evt-c", "not_found")],
            routing=[_routing_item("evt-c", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-next-hop", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 3001
        assert record["target_responsible_user_id"] == 42
        assert record["target_provenance"] == "thread_resolved"
        assert record["case_type"] == "existing_deal"
        assert record["semantic_case_type"] == "new_lead"

    def test_irrelevant_semantic_trusted_attach_projects_existing_deal(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb-irrelevant-attach"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "irrelevant",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-b", "irrelevant")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb-irrelevant-attach",
            _writeback_settings(),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["case_type"] == "existing_deal"
        assert record["semantic_case_type"] == "irrelevant"

    def test_independent_request_keeps_semantic_case_type(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb-independent"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-independent", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["case_type"] == "new_lead"
        assert record["semantic_case_type"] == "new_lead"
        assert record["outcome"] == "create_lead"
        assert record["target_provenance"] is None

    def test_fake_crm_activity_hint_does_not_project_existing_deal(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb-fake-activity"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<crm.activity.999999-NOPE@my.welding.kz>",
                    references="<crm.activity.999999-NOPE@my.welding.kz>",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps({"run_id": "run-wb-fake-activity", "evidence": []}),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-fake-activity", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["case_type"] == "new_lead"
        assert record["semantic_case_type"] == "new_lead"
        assert record["outcome"] == "create_lead"

    def test_candidate_only_evidence_does_not_project_existing_deal(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb-candidate-only"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[
                _recon_item(
                    "evt-b",
                    "matched_lead",
                    safe=False,
                    entity_type="lead",
                    entity_id=5001,
                )
            ],
            routing=[_routing_item("evt-b", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-candidate-only", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["case_type"] == "new_lead"
        assert record["semantic_case_type"] == "new_lead"
        assert record["outcome"] == "create_lead"
        assert record["target_provenance"] is None

    def test_exact_outbound_bridge_conflicting_trusted_target_is_deferred(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_attached_thread_record("<msg-a@example.test>", target_entity_id=2002)])
        run_dir = tmp_path / "runs" / "run-wb-outbound-conflict"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="out-1@employee.test",
                    references="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-outbound-conflict",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": True,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 77,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-outbound-conflict", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "outbound_candidate_untrusted"
        assert record["target_entity_id"] is None

    def test_candidate_only_outbound_evidence_never_authorizes_attach(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb-candidate"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps(
                {
                    "run_id": "run-wb-candidate",
                    "evidence": [
                        {
                            "event_id": "evt-b",
                            "event_instance_id": "inst-1",
                            "bridge_exact": False,
                            "outbound_message_id": "out-1@employee.test",
                            "target_entity_type": "lead",
                            "target_entity_type_id": 1,
                            "target_entity_id": 3001,
                            "target_responsible_user_id": 77,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-candidate", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_no_exact_outbound_identifier_is_fail_closed(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb-no-id"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="out-1@employee.test",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        (run_dir / "bitrix_outbound_correlation.json").write_text(
            json.dumps({"run_id": "run-wb-no-id", "evidence": []}),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-no-id", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_thread_headers_merged_from_normalized_events(self, tmp_path: Path) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        run_dir.mkdir(parents=True, exist_ok=True)
        normalized = [
            {
                "event_id": "evt-b",
                "event_instance_id": "inst-1",
                "message_id": "<msg-b@example.test>",
                "in_reply_to": "<msg-a@example.test>",
                "references": "<msg-a@example.test>",
            }
        ]
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        classified = [_classified_event("evt-b", "new_lead", message_id="<msg-b@example.test>")]
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        (run_dir / "rop_final_decisions.json").write_text(
            json.dumps({"events": [_decision("evt-b", "new_lead")]}), encoding="utf-8"
        )
        (run_dir / "bitrix_reconciliation.json").write_text(
            json.dumps({"items": [_recon_item("evt-b", "not_found")]}),
            encoding="utf-8",
        )
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps({"items": [_routing_item("evt-b", "matched")]}),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 1001
        assert record["target_provenance"] == "thread_resolved"

    def test_normalized_event_without_event_id_never_authorizes_thread(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        run_dir.mkdir(parents=True, exist_ok=True)
        normalized = [
            {
                "message_id": "<msg-b@example.test>",
                "in_reply_to": "<msg-a@example.test>",
                "references": "<msg-a@example.test>",
            }
        ]
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        classified = [_classified_event("evt-b", "new_lead", message_id="<msg-b@example.test>")]
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        (run_dir / "rop_final_decisions.json").write_text(
            json.dumps({"events": [_decision("evt-b", "new_lead")]}), encoding="utf-8"
        )
        (run_dir / "bitrix_reconciliation.json").write_text(
            json.dumps({"items": [_recon_item("evt-b", "not_found")]}),
            encoding="utf-8",
        )
        (run_dir / "rop_recipient_routing.json").write_text(
            json.dumps({"items": [_routing_item("evt-b", "matched")]}),
            encoding="utf-8",
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_reply_chain_preserves_thread_root(self, tmp_path: Path) -> None:
        _seed_state(
            tmp_path,
            [
                _created_lead_record("<msg-a@example.test>", remote_entity_id=1001),
                _attached_thread_record("<msg-b@example.test>", target_entity_id=1001),
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-c",
                    "new_lead",
                    message_id="<msg-c@example.test>",
                    sender="client@example.com",
                    references="<msg-a@example.test> <msg-b@example.test>",
                )
            ],
            decisions=[_decision("evt-c", "new_lead")],
            reconciliation=[_recon_item("evt-c", "not_found")],
            routing=[_routing_item("evt-c", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 1001
        assert record["target_provenance"] == "thread_resolved"

    def test_two_independent_threads_resolve_to_distinct_leads(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                _created_lead_record("<msg-a@example.test>", remote_entity_id=1001),
                _created_lead_record("<msg-d@example.test>", remote_entity_id=1002),
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    in_reply_to="<msg-a@example.test>",
                ),
                _classified_event(
                    "evt-e",
                    "new_lead",
                    message_id="<msg-e@example.test>",
                    in_reply_to="<msg-d@example.test>",
                ),
            ],
            decisions=[
                _decision("evt-b", "new_lead"),
                _decision("evt-e", "new_lead"),
            ],
            reconciliation=[
                _recon_item("evt-b", "not_found"),
                _recon_item("evt-e", "not_found"),
            ],
            routing=[
                _routing_item("evt-b", "matched"),
                _routing_item("evt-e", "matched"),
            ],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        by_event = {record["event_id"]: record for record in plan["events"]}
        assert by_event["evt-b"]["outcome"] == "attach_existing"
        assert by_event["evt-b"]["target_entity_id"] == 1001
        assert by_event["evt-e"]["outcome"] == "attach_existing"
        assert by_event["evt-e"]["target_entity_id"] == 1002

    def test_conflicting_exact_references_defer_without_target(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                _created_lead_record("<msg-a@example.test>", remote_entity_id=1001),
                _created_lead_record("<msg-d@example.test>", remote_entity_id=1002),
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-x",
                    "new_lead",
                    message_id="<msg-x@example.test>",
                    references="<msg-a@example.test> <msg-d@example.test>",
                )
            ],
            decisions=[_decision("evt-x", "new_lead")],
            reconciliation=[_recon_item("evt-x", "not_found")],
            routing=[_routing_item("evt-x", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "ambiguous_thread_target"
        assert record["target_entity_id"] is None

    def test_same_entity_different_responsible_references_defer(
        self, tmp_path: Path
    ) -> None:
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-a@example.test>",
                    target_entity_id=1001,
                    responsible=42,
                ),
                _attached_thread_record(
                    "<msg-d@example.test>",
                    target_entity_id=1001,
                    responsible=1563,
                ),
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-x",
                    "new_lead",
                    message_id="<msg-x@example.test>",
                    references="<msg-a@example.test> <msg-d@example.test>",
                )
            ],
            decisions=[_decision("evt-x", "new_lead")],
            reconciliation=[_recon_item("evt-x", "not_found")],
            routing=[_routing_item("evt-x", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "ambiguous_thread_target"
        assert record["target_entity_id"] is None
        assert record["target_responsible_user_id"] is None

    def test_conflicting_entity_type_references_defer(self, tmp_path: Path) -> None:
        _seed_state(
            tmp_path,
            [
                _attached_thread_record("<msg-a@example.test>", target_entity_id=1001),
                _attached_thread_record(
                    "<msg-d@example.test>",
                    target_entity_type="deal",
                    target_entity_type_id=2,
                    target_entity_id=2001,
                    responsible=42,
                ),
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-x",
                    "new_lead",
                    message_id="<msg-x@example.test>",
                    references="<msg-a@example.test> <msg-d@example.test>",
                )
            ],
            decisions=[_decision("evt-x", "new_lead")],
            reconciliation=[_recon_item("evt-x", "not_found")],
            routing=[_routing_item("evt-x", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "ambiguous_thread_target"
        assert record["target_entity_id"] is None

    def test_consistent_full_identity_references_attach(self, tmp_path: Path) -> None:
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-a@example.test>",
                    target_entity_id=1001,
                    responsible=42,
                ),
                _attached_thread_record(
                    "<msg-d@example.test>",
                    target_entity_id=1001,
                    responsible=42,
                ),
            ],
        )
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-x",
                    "new_lead",
                    message_id="<msg-x@example.test>",
                    references="<msg-a@example.test> <msg-d@example.test>",
                )
            ],
            decisions=[_decision("evt-x", "new_lead")],
            reconciliation=[_recon_item("evt-x", "not_found")],
            routing=[_routing_item("evt-x", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_id"] == 1001
        assert record["target_responsible_user_id"] == 42
        assert record["target_provenance"] == "thread_resolved"

    def test_missing_thread_headers_never_authorize_targeting(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-y", "new_lead", message_id="<msg-y@example.test>", sender="client@example.com"
                )
            ],
            decisions=[_decision("evt-y", "new_lead")],
            reconciliation=[_recon_item("evt-y", "not_found")],
            routing=[_routing_item("evt-y", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_subject_similarity_alone_never_authorizes_attach(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb-subject"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-y",
                    "new_lead",
                    message_id="<msg-y@example.test>",
                    sender="client@example.com",
                    subject="Re: Need welding quote",
                )
            ],
            decisions=[_decision("evt-y", "new_lead")],
            reconciliation=[_recon_item("evt-y", "not_found")],
            routing=[_routing_item("evt-y", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb-subject", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_malformed_thread_headers_never_authorize_targeting(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-z",
                    "new_lead",
                    message_id="<msg-z@example.test>",
                    in_reply_to="<unrelated@example.com>",
                    references="unresolvable-ancestor",
                )
            ],
            decisions=[_decision("evt-z", "new_lead")],
            reconciliation=[_recon_item("evt-z", "not_found")],
            routing=[_routing_item("evt-z", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_legacy_attach_state_without_provenance_is_not_authority(
        self, tmp_path: Path
    ) -> None:
        legacy = _attached_thread_record("<msg-old@example.test>", target_entity_id=888)
        legacy["target_provenance"] = None
        legacy["event_id"] = "evt-legacy"
        _seed_state(tmp_path, [legacy])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-new",
                    "new_lead",
                    message_id="<msg-new@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-old@example.test>",
                )
            ],
            decisions=[_decision("evt-new", "new_lead")],
            reconciliation=[_recon_item("evt-new", "not_found")],
            routing=[_routing_item("evt-new", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_legacy_created_lead_without_provenance_is_not_authority(
        self, tmp_path: Path
    ) -> None:
        legacy = _created_lead_record("<msg-old@example.test>", remote_entity_id=777)
        legacy["target_provenance"] = None
        legacy["event_id"] = "evt-legacy"
        _seed_state(tmp_path, [legacy])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-new",
                    "new_lead",
                    message_id="<msg-new@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-old@example.test>",
                )
            ],
            decisions=[_decision("evt-new", "new_lead")],
            reconciliation=[_recon_item("evt-new", "not_found")],
            routing=[_routing_item("evt-new", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_independent_same_sender_new_lead_creates_new_lead(
        self, tmp_path: Path
    ) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-new",
                    "new_lead",
                    message_id="<msg-new@example.test>",
                    sender="client@example.com",
                )
            ],
            decisions=[_decision("evt-new", "new_lead")],
            reconciliation=[_recon_item("evt-new", "not_found")],
            routing=[_routing_item("evt-new", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["target_entity_id"] is None

    def test_same_run_reply_to_planned_create_defers_pending_thread_root(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-a", "new_lead", message_id="<msg-a@example.test>", sender="client@example.com"
                ),
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                ),
            ],
            decisions=[_decision("evt-a", "new_lead"), _decision("evt-b", "new_lead")],
            reconciliation=[
                _recon_item("evt-a", "not_found"),
                _recon_item("evt-b", "not_found"),
            ],
            routing=[
                _routing_item("evt-a", "matched"),
                _routing_item("evt-b", "matched"),
            ],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        by_event = {record["event_id"]: record for record in plan["events"]}
        assert by_event["evt-a"]["outcome"] == "create_lead"
        assert by_event["evt-b"]["outcome"] == "deferred"
        assert by_event["evt-b"]["reason_code"] == "pending_thread_root"
        assert by_event["evt-b"]["status"] == "pending"

    def test_skipped_case_type_is_not_attached_via_thread(self, tmp_path: Path) -> None:
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-spam",
                    "spam",
                    message_id="<msg-spam@example.test>",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-spam", "spam")],
            reconciliation=[_recon_item("evt-spam", "skipped")],
            routing=[_routing_item("evt-spam", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "event_skipped"

    def test_connector_degraded_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "connector_degraded")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "reconciliation_connector_degraded"
        assert record["status"] == "pending"

    def test_connector_degraded_plan_refreshes_without_reingestion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "connector_degraded")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings()
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def recovered_reconciliation(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
            reconciliation = {
                "status": "ok",
                "aggregate": {"event_count": 1},
                "items": [_recon_item("evt-1", "not_found")],
            }
            (run_dir / "bitrix_reconciliation.json").write_text(
                json.dumps(reconciliation), encoding="utf-8"
            )
            return reconciliation

        monkeypatch.setattr(
            "beeagent_module.cases.rop_bitrix_reconciliation.run_reconciliation",
            recovered_reconciliation,
        )
        assert refresh_recoverable_writeback_prerequisites(
            tmp_path, settings, _null_logger()
        ) == ["run-wb"]
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["outcome"] == "create_lead"
        assert record["status"] == "pending"

    @pytest.mark.parametrize(
        "responsible_status",
        ["not_found", "ambiguous", "connector_degraded", "unresolved"],
    )
    def test_unresolved_responsible_prevents_create(
        self, tmp_path: Path, responsible_status: str
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[
                _routing_item(
                    "evt-1",
                    responsible_status,
                    user_id=None if responsible_status != "matched" else 42,
                )
            ],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "responsible_unresolved"
        assert record["responsible_status"] == responsible_status

    def test_unresolved_responsible_defers_without_fallback(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "responsible_unresolved"

    def test_event_without_stable_identity_is_not_planned(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("", "new_lead")],
            decisions=[],
            reconciliation=[],
            routing=[],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        assert plan["events"] == []

    def test_stable_remote_id_prefers_message_id(self) -> None:
        assert (
            _stable_remote_id(
                {
                    "message_id": "m-1",
                    "x_email_id": "x-1",
                    "event_id": "e-1",
                }
            )
            == "m-1"
        )
        assert (
            _stable_remote_id(
                {
                    "message_id": "",
                    "x_email_id": "x-1",
                    "event_id": "e-1",
                }
            )
            == "x-1"
        )
        assert (
            _stable_remote_id(
                {
                    "message_id": "",
                    "x_email_id": "",
                    "event_id": "e-1",
                }
            )
            == "e-1"
        )

    def test_repeated_stable_identity_creates_single_plan_record(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>"),
                _classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>"),
            ],
            decisions=[
                _decision("evt-1", "new_lead"),
                _decision("evt-1", "new_lead"),
            ],
            reconciliation=[
                _recon_item("evt-1", "not_found"),
                _recon_item("evt-1", "not_found"),
            ],
            routing=[
                _routing_item("evt-1", "matched"),
                _routing_item("evt-1", "matched"),
            ],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        assert len(plan["events"]) == 1
        assert plan["events"][0]["identity"] == _stable_identity(
            "welding", "hotline_mailbox", "<msg-1@example.test>"
        )
        assert plan["events"][0]["outcome"] == "create_lead"

    def test_repeated_identity_prefers_non_duplicate_occurrence(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    instance="event-000001",
                    message_id="<msg-1@example.test>",
                ),
                _classified_event(
                    "evt-1",
                    "duplicate",
                    instance="event-000002",
                    message_id="<msg-1@example.test>",
                ),
            ],
            decisions=[
                _decision("evt-1", "new_lead", instance="event-000001"),
                _decision("evt-1", "duplicate", instance="event-000002"),
            ],
            reconciliation=[
                _recon_item("evt-1", "not_found", instance="event-000001"),
                _recon_item("evt-1", "not_found", instance="event-000002"),
            ],
            routing=[
                _routing_item("evt-1", "matched", instance="event-000001"),
                _routing_item("evt-1", "matched", instance="event-000002"),
            ],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        assert len(plan["events"]) == 1
        record = plan["events"][0]
        assert record["case_type"] == "new_lead"
        assert record["outcome"] == "create_lead"


class TestWritebackExecutor:
    def test_disabled_execute_zero_writes(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(enabled=False), _null_logger()
        )
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                _writeback_settings(enabled=False),
                _null_logger(),
            )
        assert result["status"] == "disabled"
        assert result["writes_performed"] == 0
        assert recorder.calls == []
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "deferred"
        assert record["reason_code"] == "writeback_disabled"

    def test_dry_run_execute_zero_writes(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                _writeback_settings(dry_run=True),
                _null_logger(),
            )
        assert result["status"] == "dry_run"
        assert result["writes_performed"] == 0
        assert recorder.calls == []

    def test_cli_dry_run_flag_zero_writes(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                _writeback_settings(),
                _null_logger(),
                dry_run_override=True,
            )
        assert result["status"] == "dry_run"
        assert result["writes_performed"] == 0
        assert recorder.calls == []

    def test_missing_credential_zero_writes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BITRIX_WRITEBACK_WEBHOOK_URL", raising=False)
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                _writeback_settings(),
                _null_logger(),
            )
        assert result["status"] == "credential_missing"
        assert result["writes_performed"] == 0
        assert recorder.calls == []
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["reason_code"] == "write_credential_missing"

    def test_invalid_stage_means_zero_mutations(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(stages={"new_lead": "NOPE", "irrelevant": "NEW"})
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        assert result["status"] == "stage_validation_failed"
        assert result["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "deferred"
        assert record["reason_code"] == "stage_validation_failed"

    def test_stage_validation_degraded_zero_writes(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def degraded_handler(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.status.list":
                raise URLError("connection refused")
            return _default_handler(call)

        recorder = _HttpRecorder(degraded_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["status"] == "stage_validation_degraded"
        assert result["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "pending"
        assert record["last_error_code"] == "stage_validation_degraded"

    def test_stage_validation_degraded_retries_after_recovery(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def degraded_handler(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.status.list":
                raise URLError("connection refused")
            return _default_handler(call)

        recorder = _HttpRecorder(degraded_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )

        recorder2 = _HttpRecorder(_default_handler)
        with _patch_http(recorder2)[0], _patch_http(recorder2)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["status"] == "executed"
        assert result["writes_performed"] == 1
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "created"
        assert record["remote_entity_id"] == 1001
        assert record["last_error_code"] is None

    def test_create_lead_posts_crm_item_add_entity_type_1(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1", "new_lead", message_id="<msg-1@example.test>", subject="Buy machine"
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched", user_id=42)],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["status"] == "executed"
        assert result["writes_performed"] == 1
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" in methods
        assert "crm.lead.add" not in methods
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["entityTypeId"] == 1
        fields = add_call["payload"]["fields"]
        assert fields["STAGE_ID"] == "NEW"
        assert fields["ASSIGNED_BY_ID"] == 42
        assert fields["ORIGINATOR_ID"] == "beeagent-rop"
        assert fields["ORIGIN_ID"] == _origin_id(
            _stable_identity("welding", "hotline_mailbox", "<msg-1@example.test>")
        )
        assert fields["TITLE"] == "Buy machine"
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "created"
        assert record["remote_entity_type_id"] == 1
        assert record["remote_entity_id"] == 1001

    def test_repeat_execute_does_not_create_duplicate_lead(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            first = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
            second = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert first["writes_performed"] == 1
        assert second["writes_performed"] == 0
        add_calls = [
            call for call in recorder.calls if call["method"] == "crm.item.add"
        ]
        assert len(add_calls) == 1

    def test_create_lead_attaches_email_activity_when_enabled(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    subject="Test subject",
                    sender="sender@example.com",
                    body_preview="Hello, this is the body.",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True, source_id="EMAIL")
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        assert result["writes_performed"] == 2
        methods = [call["method"] for call in recorder.calls]
        assert "crm.activity.add" in methods
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["SOURCE_ID"] == "EMAIL"
        assert add_call["payload"]["fields"]["fm"] == [
            {
                "typeId": "EMAIL",
                "value": "sender@example.com",
                "valueType": "WORK",
            }
        ]
        activity_call = next(
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        )
        fields = activity_call["payload"]["fields"]
        assert fields["OWNER_TYPE_ID"] == 1
        assert fields["OWNER_ID"] == 1001
        assert fields["TYPE_ID"] == 4
        assert fields["COMMUNICATIONS"][0]["VALUE"] == "sender@example.com"
        assert fields["SUBJECT"] == "Test subject"
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["email_activity_id"] == 9001
        assert record["email_attachment_required"] is True
        assert record["email_attachment_status"] == "attached"
        summary = json.loads(
            (run_dir / WRITEBACK_SUMMARY_FILENAME).read_text(encoding="utf-8")
        )
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert summary["aggregate"]["delivery_status_counts"] == {"completed": 1}
        assert draft["recommended_action"] == "delivery_completed"

    def test_create_lead_attach_no_duplicate_activity_on_repeat(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        activity_calls = [
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        ]
        assert len(activity_calls) == 1

    def test_create_lead_skips_email_attach_when_disabled(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["writes_performed"] == 1
        methods = [call["method"] for call in recorder.calls]
        assert "crm.activity.add" not in methods
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record.get("email_activity_id") is None

    def test_create_lead_does_not_retry_terminal_email_attach_failure(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        attach_failures = {"remaining": 2}

        def fail_activity_once(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                if attach_failures["remaining"] > 0:
                    attach_failures["remaining"] -= 1
                    return json.dumps(
                        {
                            "error": "INTERNAL_ERROR",
                            "error_description": "boom",
                        }
                    ).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(fail_activity_once)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "created"
        assert record["email_activity_id"] is None
        assert record["last_attach_error_code"] == "api_error"
        assert record["email_attachment_status"] == "failed"
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert draft["recommended_action"] == "review_delivery_failure"

        recorder2 = _HttpRecorder(_default_handler)
        with _patch_http(recorder2)[0], _patch_http(recorder2)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger(), retry_failed=True
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["email_activity_id"] is None
        assert record["last_attach_error_code"] == "api_error"
        item_adds = [
            call for call in recorder2.calls if call["method"] == "crm.item.add"
        ]
        assert item_adds == []
        activity_calls = [
            call for call in recorder2.calls if call["method"] == "crm.activity.add"
        ]
        assert activity_calls == []

    def test_created_lead_with_retryable_attachment_failure_is_not_completed(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def transport_failure(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.activity.add",
                    code=502,
                    msg="Bad Gateway",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(transport_failure)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        record = list(_load_state(tmp_path)["events"].values())[0]
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert record["remote_entity_id"] == 1001
        assert record["email_attachment_status"] == "pending"
        assert record["last_attach_error_code"] == "transport"
        assert draft["recommended_action"] == "complete_email_attachment"

    def test_created_lead_uncertain_attachment_requires_reconciliation(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        activity_adds = {"count": 0}

        def malformed_then_reconciled(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                activity_adds["count"] += 1
                return b"{broken"
            if call["method"] == "crm.activity.list" and activity_adds["count"]:
                return json.dumps({"result": [{"ID": 9001}]}).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(malformed_then_reconciled)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
            first_record = list(_load_state(tmp_path)["events"].values())[0]
            assert first_record["email_attachment_status"] == "uncertain"
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        record = list(_load_state(tmp_path)["events"].values())[0]
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert activity_adds["count"] == 1
        assert record["remote_entity_id"] == 1001
        assert record["email_activity_id"] == 9001
        assert record["email_attachment_status"] == "attached"
        assert draft["recommended_action"] == "delivery_completed"

    def test_created_lead_with_missing_sender_is_not_completed(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        record = list(_load_state(tmp_path)["events"].values())[0]
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert record["remote_entity_id"] == 1001
        assert record["email_attachment_status"] == "failed"
        assert record["last_attach_error_code"] == "email_sender_unavailable"
        assert draft["recommended_action"] == "review_delivery_failure"
        assert not [
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        ]

    def test_create_lead_does_not_retry_attach_when_disabled(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def fail_activity(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                return json.dumps(
                    {"error": "INTERNAL_ERROR", "error_description": "boom"}
                ).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(fail_activity)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["last_attach_error_code"] == "api_error"

        disabled_settings = _writeback_settings(email_attach=False)
        recorder2 = _HttpRecorder(_default_handler)
        with _patch_http(recorder2)[0], _patch_http(recorder2)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", disabled_settings, _null_logger()
            )
        activity_calls = [
            call for call in recorder2.calls if call["method"] == "crm.activity.add"
        ]
        assert activity_calls == []
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["email_activity_id"] is None
        assert record["last_attach_error_code"] == "api_error"

    def test_create_lead_sets_sender_email_field(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["fm"] == [
            {
                "typeId": "EMAIL",
                "value": "sender@example.com",
                "valueType": "WORK",
            }
        ]

    def test_create_lead_sets_sender_name_field(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                    from_name="Иван Петров",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["NAME"] == "Иван Петров"

    def test_create_lead_does_not_use_fallback_responsible(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        settings = _writeback_settings()
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        assert not [call for call in recorder.calls if call["method"] == "crm.item.add"]

    def test_create_lead_parses_sender_name_from_display_string(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="Иван Петров <sender@example.com>",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["NAME"] == "Иван Петров"

    def test_create_lead_without_sender_name_omits_name_field(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert "NAME" not in add_call["payload"]["fields"]

    def test_create_lead_without_sender_omits_email_field(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert "fm" not in add_call["payload"]["fields"]

    def test_uncertain_timeout_reconciles_before_repeat_post(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "planned"

        lookup_count = {"value": 0}

        def timeout_then_found(call: dict[str, Any]) -> bytes:
            method = call["method"]
            if method == "crm.item.add":
                raise URLError("timed out")
            if method == "crm.item.list":
                lookup_count["value"] += 1
                if lookup_count["value"] >= 2:
                    return json.dumps({"result": {"items": [{"id": 2002}]}}).encode(
                        "utf-8"
                    )
                return json.dumps({"result": {"items": []}}).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(timeout_then_found)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            first = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert first["writes_performed"] == 0
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "uncertain"
        assert record["last_error_code"] == "timeout"

        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            second = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert second["writes_performed"] == 0
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "recovered"
        assert record["remote_entity_id"] == 2002
        add_calls = [
            call for call in recorder.calls if call["method"] == "crm.item.add"
        ]
        assert len(add_calls) == 1

    def test_retryable_429_remains_pending_then_exhausts(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(attempts_retry_max=2)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def rate_limited(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.item.add",
                    code=429,
                    msg="Too Many Requests",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(rate_limited)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "pending"
        assert record["attempts"] == 1
        assert record["last_error_code"] == "transport"

        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "pending"
        assert record["attempts"] == 2

        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "retry_exhausted"
        assert result["writes_performed"] == 0
        add_calls = [
            call for call in recorder.calls if call["method"] == "crm.item.add"
        ]
        assert len(add_calls) == 2

    def test_retry_failed_rearms_exhausted_and_creates(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(attempts_retry_max=2)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def rate_limited(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.item.add",
                    code=429,
                    msg="Too Many Requests",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(rate_limited)
        for _ in range(3):
            with _patch_http(recorder)[0], _patch_http(recorder)[1]:
                execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "retry_exhausted"

        recorder2 = _HttpRecorder(_default_handler)
        with _patch_http(recorder2)[0], _patch_http(recorder2)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                settings,
                _null_logger(),
                retry_failed=True,
            )
        assert result["writes_performed"] == 1
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "created"
        assert record["remote_entity_id"] == 1001
        assert record["last_error_code"] is None

    def test_retry_failed_skips_terminal_failures(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def denied(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.item.add",
                    code=401,
                    msg="Unauthorized",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(denied)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "permission_denied"

        recorder2 = _HttpRecorder(_default_handler)
        with _patch_http(recorder2)[0], _patch_http(recorder2)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                _writeback_settings(),
                _null_logger(),
                retry_failed=True,
            )
        assert result["writes_performed"] == 0
        add_calls = [
            call for call in recorder2.calls if call["method"] == "crm.item.add"
        ]
        assert add_calls == []
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "permission_denied"

    def test_retry_failed_rearms_exhausted_existing_attach(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True, attempts_retry_max=1)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def unavailable_activity(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.activity.add",
                    code=502,
                    msg="Bad Gateway",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(unavailable_activity)
        for _ in range(2):
            with _patch_http(recorder)[0], _patch_http(recorder)[1]:
                execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-1"
        )
        assert record["status"] == "failed"
        assert record["reason_code"] == "retry_exhausted"
        assert record["target_entity_id"] == 253
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert draft["recommended_action"] == "review_delivery_failure"

        recovered = _HttpRecorder(_default_handler)
        with _patch_http(recovered)[0], _patch_http(recovered)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger(), retry_failed=True
            )
        assert result["writes_performed"] == 1
        assert not [
            call for call in recovered.calls if call["method"] == "crm.item.add"
        ]
        state = _load_state(tmp_path)
        record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-1"
        )
        assert record["status"] == "attached"
        assert record["email_activity_id"] == 9001
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert draft["recommended_action"] == "delivery_completed"

    def test_retry_failed_rearms_exhausted_created_lead_attachment(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1", "new_lead", message_id="<msg-1@example.test>", sender="sender@example.com"
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True, attempts_retry_max=1)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())

        def unavailable_activity(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.activity.add",
                    code=502,
                    msg="Bad Gateway",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(unavailable_activity)
        for _ in range(2):
            with _patch_http(recorder)[0], _patch_http(recorder)[1]:
                execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "created"
        assert record["remote_entity_id"] == 1001
        assert record["last_attach_error_code"] == "retry_exhausted"
        assert record["email_attachment_status"] == "failed"
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert draft["recommended_action"] == "review_delivery_failure"

        recovered = _HttpRecorder(_default_handler)
        with _patch_http(recovered)[0], _patch_http(recovered)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger(), retry_failed=True
            )
        assert result["writes_performed"] == 1
        assert not [
            call for call in recovered.calls if call["method"] == "crm.item.add"
        ]
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["remote_entity_id"] == 1001
        assert record["email_activity_id"] == 9001
        assert record["email_attachment_status"] == "attached"
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert draft["recommended_action"] == "delivery_completed"

    def test_terminal_401_fails_and_is_not_retried(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def denied(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.item.add",
                    code=401,
                    msg="Unauthorized",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(denied)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            first = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "permission_denied"

        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            second = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert second["writes_performed"] == 0
        add_calls = [
            call for call in recorder.calls if call["method"] == "crm.item.add"
        ]
        assert len(add_calls) == 1

    def test_terminal_400_fails_not_retried(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def bad_request(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.item.add",
                    code=400,
                    msg="Bad Request",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(bad_request)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "invalid_request"

    def test_server_error_5xx_is_retryable_pending(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def server_error(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                raise HTTPError(
                    url="https://portal.test/rest/1/writetoken/crm.item.add",
                    code=502,
                    msg="Bad Gateway",
                    hdrs=Message(),
                    fp=None,
                )
            return _default_handler(call)

        recorder = _HttpRecorder(server_error)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "pending"
        assert record["last_error_code"] == "transport"
        assert record["attempts"] == 1

    def test_api_error_fails_terminal(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def api_error(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                return json.dumps(
                    {
                        "error": "INVALID_FIELD",
                        "error_description": "bad field",
                    }
                ).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(api_error)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "failed"
        assert record["reason_code"] == "api_error"

    def test_malformed_response_is_uncertain(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def broken(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.add":
                return b"{broken"
            return _default_handler(call)

        recorder = _HttpRecorder(broken)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "uncertain"
        assert record["last_error_code"] == "malformed_response"

    def test_attach_existing_lead_creates_one_email_activity(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(email_attach=True),
            _null_logger(),
        )
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path,
                "run-wb",
                _writeback_settings(email_attach=True),
                _null_logger(),
            )
        assert result["writes_performed"] == 1
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        assert methods.count("crm.activity.add") == 1
        state = _load_state(tmp_path)
        record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-1"
        )
        assert record["outcome"] == "attach_existing"
        assert record["status"] == "attached"
        assert record["email_activity_id"] == 9001

    def test_email_attach_posts_completed_n_from_policy(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True, email_completed=False)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        activity = next(
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        )
        assert activity["payload"]["fields"]["COMPLETED"] == "N"

    def test_email_attach_defaults_to_completed_y(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        del settings["bitrix"]["writeback"]["email_completed"]
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        activity = next(
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        )
        assert activity["payload"]["fields"]["COMPLETED"] == "Y"

    def test_existing_lead_attach_replay_has_no_second_activity(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        first = _HttpRecorder(_default_handler)
        with _patch_http(first)[0], _patch_http(first)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        assert (
            len([call for call in first.calls if call["method"] == "crm.activity.add"])
            == 1
        )

        second = _HttpRecorder(_default_handler)
        with _patch_http(second)[0], _patch_http(second)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        assert not [
            call for call in second.calls if call["method"] == "crm.activity.add"
        ]
        state = _load_state(tmp_path)
        record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-1"
        )
        assert record["status"] == "attached"
        assert record["email_activity_id"] == 9001

    @pytest.mark.parametrize("failure", ["timeout", "malformed"])
    def test_uncertain_existing_attach_reconciles_before_retry(
        self, tmp_path: Path, writeback_env: None, failure: str
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path, [_attached_thread_record("<msg-root@example.test>", target_entity_id=253)]
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        activity_adds = {"count": 0}

        def uncertain_activity(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.activity.add":
                activity_adds["count"] += 1
                if failure == "timeout":
                    raise URLError("timed out")
                return b"{broken"
            if call["method"] == "crm.activity.list" and activity_adds["count"]:
                return json.dumps({"result": [{"ID": 9001}]}).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(uncertain_activity)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            first = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
            second = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        assert activity_adds["count"] == 1
        assert first["writes_performed"] == 0
        assert second["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert methods.count("crm.activity.list") == 2
        state = _load_state(tmp_path)
        record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-1"
        )
        assert record["status"] == "attached"
        assert record["email_activity_id"] == 9001

    def test_existing_deal_attach_uses_deal_owner_without_create(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _seed_state(
            tmp_path,
            [
                _attached_thread_record(
                    "<msg-root@example.test>",
                    target_entity_type="deal",
                    target_entity_type_id=2,
                    target_entity_id=88,
                )
            ],
        )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "existing_deal",
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "existing_deal")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=True)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        assert result["writes_performed"] == 1
        activity = next(
            call for call in recorder.calls if call["method"] == "crm.activity.add"
        )
        assert activity["payload"]["fields"]["OWNER_TYPE_ID"] == 2
        assert activity["payload"]["fields"]["OWNER_ID"] == 88
        assert not [call for call in recorder.calls if call["method"] == "crm.item.add"]

    def test_recovered_via_bitrix_lookup_no_post(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())

        def found_in_bitrix(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.list":
                return json.dumps({"result": {"items": [{"id": 555}]}}).encode("utf-8")
            return _default_handler(call)

        recorder = _HttpRecorder(found_in_bitrix)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "recovered"
        assert record["remote_entity_id"] == 555

    def test_state_and_summary_contain_no_credentials(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state_text = (tmp_path / "interfaces" / WRITEBACK_STATE_FILENAME).read_text(
            encoding="utf-8"
        )
        summary_text = (
            tmp_path / "runs" / "run-wb" / WRITEBACK_SUMMARY_FILENAME
        ).read_text(encoding="utf-8")
        for text in (state_text, summary_text):
            assert "readonlytoken" not in text
            assert "writetoken" not in text
            assert "portal.test" not in text

    def test_restart_survives_via_durable_state(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(tmp_path, "run-wb", _writeback_settings(), _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        state_path = tmp_path / "interfaces" / WRITEBACK_STATE_FILENAME
        assert state_path.exists()
        reloaded = _load_state(tmp_path)
        record = list(reloaded["events"].values())[0]
        assert record["status"] == "created"
        assert record["remote_entity_id"] == 1001

    @pytest.mark.parametrize(
        ("case_type", "match_status", "entity_type", "entity_id", "expected_status"),
        [
            ("new_lead", "not_found", "", None, "created"),
            ("new_lead", "matched_lead", "lead", 253, "attached"),
            ("existing_deal", "matched_deal", "deal", 88, "attached"),
        ],
    )
    def test_execution_refreshes_original_run_projections(
        self,
        tmp_path: Path,
        writeback_env: None,
        case_type: str,
        match_status: str,
        entity_type: str,
        entity_id: int | None,
        expected_status: str,
    ) -> None:
        run_id = "run-original"
        run_dir = tmp_path / "runs" / run_id
        if entity_type:
            _seed_state(
                tmp_path,
                [
                    _attached_thread_record(
                        "<msg-root@example.test>",
                        target_entity_type=entity_type,
                        target_entity_type_id=1 if entity_type == "lead" else 2,
                        target_entity_id=entity_id or 0,
                    )
                ],
            )
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    case_type,
                    message_id="<msg-1@example.test>",
                    in_reply_to="<msg-root@example.test>" if entity_type else "",
                    sender="sender@example.com" if entity_type else "",
                )
            ],
            decisions=[_decision("evt-1", case_type)],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    match_status,
                    safe=False,
                    entity_type=entity_type,
                    entity_id=entity_id,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(email_attach=bool(entity_type))
        build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(tmp_path, run_id, settings, _null_logger())

        summary = json.loads(
            (run_dir / WRITEBACK_SUMMARY_FILENAME).read_text(encoding="utf-8")
        )
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert summary["events"][0]["status"] == expected_status
        assert draft["delivery_status"] == expected_status
        assert draft["recommended_action"] == "delivery_completed"
        assert draft["recommended_next_step"] == "no_action_required"

    def test_manual_execution_refreshes_every_affected_original_run(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        settings = _writeback_settings()
        for run_id, event_id in (
            ("run-original-a", "evt-a"),
            ("run-original-b", "evt-b"),
        ):
            run_dir = tmp_path / "runs" / run_id
            _write_artifacts(
                run_dir,
                classified=[
                    _classified_event(event_id, "new_lead", message_id=event_id)
                ],
                decisions=[_decision(event_id, "new_lead")],
                reconciliation=[_recon_item(event_id, "not_found")],
                routing=[_routing_item(event_id, "matched")],
            )
            build_writeback_plan(tmp_path, run_id, settings, _null_logger())

        first = _HttpRecorder(_default_handler)
        with _patch_http(first)[0], _patch_http(first)[1]:
            execute_writeback_pending(
                tmp_path, "manual-execute", settings, _null_logger()
            )
        assert [call["method"] for call in first.calls].count("crm.item.add") == 2
        assert not (tmp_path / "runs" / "manual-execute").exists()

        for run_id in ("run-original-a", "run-original-b"):
            run_dir = tmp_path / "runs" / run_id
            summary = json.loads(
                (run_dir / WRITEBACK_SUMMARY_FILENAME).read_text(encoding="utf-8")
            )
            draft = json.loads(
                (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
            )["items"][0]
            assert summary["events"][0]["status"] == "created"
            assert draft["recommended_action"] == "delivery_completed"

        replay = _HttpRecorder(_default_handler)
        with _patch_http(replay)[0], _patch_http(replay)[1]:
            execute_writeback_pending(
                tmp_path, "manual-execute", settings, _null_logger()
            )
        assert not [call for call in replay.calls if call["method"] == "crm.item.add"]

    def test_poll_recovery_refreshes_original_run_without_recovery_run(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_id = "run-original"
        run_dir = tmp_path / "runs" / run_id
        _write_artifacts(
            run_dir,
            classified=[_classified_event("evt-1", "new_lead", message_id="<msg-1@example.test>")],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings()
        build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "poll-recovery", settings, _null_logger()
            )

        summary = json.loads(
            (run_dir / WRITEBACK_SUMMARY_FILENAME).read_text(encoding="utf-8")
        )
        draft = json.loads(
            (run_dir / "rop_action_drafts.json").read_text(encoding="utf-8")
        )["items"][0]
        assert summary["events"][0]["status"] == "created"
        assert draft["recommended_action"] == "delivery_completed"
        assert not (tmp_path / "runs" / "poll-recovery").exists()

    def test_cross_run_exact_reply_attaches_without_duplicate_lead(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        settings = _writeback_settings(email_attach=True)
        run_a = tmp_path / "runs" / "run-a"
        _write_artifacts(
            run_a,
            classified=[
                _classified_event(
                    "evt-a", "new_lead", message_id="<msg-a@example.test>", sender="client@example.com"
                )
            ],
            decisions=[_decision("evt-a", "new_lead")],
            reconciliation=[_recon_item("evt-a", "not_found")],
            routing=[_routing_item("evt-a", "matched")],
        )
        build_writeback_plan(tmp_path, "run-a", settings, _null_logger())
        first = _HttpRecorder(_default_handler)
        with _patch_http(first)[0], _patch_http(first)[1]:
            execute_writeback_pending(tmp_path, "run-a", settings, _null_logger())
        state = _load_state(tmp_path)
        a_record = list(state["events"].values())[0]
        assert a_record["outcome"] == "create_lead"
        assert a_record["status"] == "created"
        assert a_record["remote_entity_id"] == 1001
        assert a_record["target_provenance"] == "beeagent_created"

        run_b = tmp_path / "runs" / "run-b"
        _write_artifacts(
            run_b,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        build_writeback_plan(tmp_path, "run-b", settings, _null_logger())
        second = _HttpRecorder(_default_handler)
        with _patch_http(second)[0], _patch_http(second)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-b", settings, _null_logger()
            )
        assert result["writes_performed"] == 1
        methods = [call["method"] for call in second.calls]
        assert "crm.item.add" not in methods
        assert methods.count("crm.activity.add") == 1
        state = _load_state(tmp_path)
        by_event = {r["event_id"]: r for r in state["events"].values()}
        assert by_event["evt-b"]["outcome"] == "attach_existing"
        assert by_event["evt-b"]["status"] == "attached"
        assert by_event["evt-b"]["target_entity_id"] == 1001
        assert by_event["evt-b"]["target_responsible_user_id"] == 42
        assert by_event["evt-b"]["target_provenance"] == "thread_resolved"

    def test_fallback_responsible_creates_lead_with_assigned_user(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1", "new_lead", message_id="<msg-1@example.test>", sender="client@example.com"
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        settings = _writeback_settings(user_id_fallback=1563)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        assert result["writes_performed"] == 1
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["ASSIGNED_BY_ID"] == 1563
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["status"] == "created"
        assert record["responsible_user_id"] == 1563
        assert record["responsible_status"] == "fallback"

    def test_thread_reply_replay_creates_no_second_activity(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        settings = _writeback_settings(email_attach=True)
        _seed_state(tmp_path, [_created_lead_record("<msg-a@example.test>", remote_entity_id=1001)])
        run_b = tmp_path / "runs" / "run-b"
        _write_artifacts(
            run_b,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        build_writeback_plan(tmp_path, "run-b", settings, _null_logger())
        first = _HttpRecorder(_default_handler)
        with _patch_http(first)[0], _patch_http(first)[1]:
            execute_writeback_pending(tmp_path, "run-b", settings, _null_logger())
        assert (
            len([call for call in first.calls if call["method"] == "crm.activity.add"])
            == 1
        )

        replay = _HttpRecorder(_default_handler)
        with _patch_http(replay)[0], _patch_http(replay)[1]:
            execute_writeback_pending(tmp_path, "run-b", settings, _null_logger())
        assert not [
            call for call in replay.calls if call["method"] == "crm.activity.add"
        ]
        state = _load_state(tmp_path)
        b_record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-b"
        )
        assert b_record["status"] == "attached"
        assert b_record["email_activity_id"] == 9001

    def test_multi_hop_thread_chain_preserves_thread_root(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        settings = _writeback_settings(email_attach=True)
        run_a = tmp_path / "runs" / "run-a"
        _write_artifacts(
            run_a,
            classified=[
                _classified_event(
                    "evt-a", "new_lead", message_id="<msg-a@example.test>", sender="client@example.com"
                )
            ],
            decisions=[_decision("evt-a", "new_lead")],
            reconciliation=[_recon_item("evt-a", "not_found")],
            routing=[_routing_item("evt-a", "matched")],
        )
        build_writeback_plan(tmp_path, "run-a", settings, _null_logger())
        with (
            _patch_http(_HttpRecorder(_default_handler))[0],
            _patch_http(_HttpRecorder(_default_handler))[1],
        ):
            execute_writeback_pending(tmp_path, "run-a", settings, _null_logger())

        run_b = tmp_path / "runs" / "run-b"
        _write_artifacts(
            run_b,
            classified=[
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                )
            ],
            decisions=[_decision("evt-b", "new_lead")],
            reconciliation=[_recon_item("evt-b", "not_found")],
            routing=[_routing_item("evt-b", "matched")],
        )
        build_writeback_plan(tmp_path, "run-b", settings, _null_logger())
        with (
            _patch_http(_HttpRecorder(_default_handler))[0],
            _patch_http(_HttpRecorder(_default_handler))[1],
        ):
            execute_writeback_pending(tmp_path, "run-b", settings, _null_logger())

        run_c = tmp_path / "runs" / "run-c"
        _write_artifacts(
            run_c,
            classified=[
                _classified_event(
                    "evt-c",
                    "new_lead",
                    message_id="<msg-c@example.test>",
                    sender="client@example.com",
                    references="<msg-a@example.test> <msg-b@example.test>",
                )
            ],
            decisions=[_decision("evt-c", "new_lead")],
            reconciliation=[_recon_item("evt-c", "not_found")],
            routing=[_routing_item("evt-c", "matched")],
        )
        plan = build_writeback_plan(tmp_path, "run-c", settings, _null_logger())
        c_record = plan["events"][0]
        assert c_record["outcome"] == "attach_existing"
        assert c_record["target_entity_id"] == 1001
        state = _load_state(tmp_path)
        by_event = {r["event_id"]: r for r in state["events"].values()}
        assert by_event["evt-a"]["remote_entity_id"] == 1001
        assert by_event["evt-b"]["target_entity_id"] == 1001

    def test_same_run_reply_recovers_to_attach_after_root_confirmed(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        settings = _writeback_settings(email_attach=True)
        run_id = "run-ab"
        run_dir = tmp_path / "runs" / run_id
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-a", "new_lead", message_id="<msg-a@example.test>", sender="client@example.com"
                ),
                _classified_event(
                    "evt-b",
                    "new_lead",
                    message_id="<msg-b@example.test>",
                    sender="client@example.com",
                    in_reply_to="<msg-a@example.test>",
                ),
            ],
            decisions=[_decision("evt-a", "new_lead"), _decision("evt-b", "new_lead")],
            reconciliation=[
                _recon_item("evt-a", "not_found"),
                _recon_item("evt-b", "not_found"),
            ],
            routing=[
                _routing_item("evt-a", "matched"),
                _routing_item("evt-b", "matched"),
            ],
        )
        build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        first = _HttpRecorder(_default_handler)
        with _patch_http(first)[0], _patch_http(first)[1]:
            execute_writeback_pending(tmp_path, run_id, settings, _null_logger())
        state = _load_state(tmp_path)
        by_event = {r["event_id"]: r for r in state["events"].values()}
        assert by_event["evt-a"]["status"] == "created"
        assert by_event["evt-a"]["remote_entity_id"] == 1001
        assert by_event["evt-b"]["outcome"] == "deferred"
        assert by_event["evt-b"]["reason_code"] == "pending_thread_root"

        build_writeback_plan(tmp_path, run_id, settings, _null_logger())
        second = _HttpRecorder(_default_handler)
        with _patch_http(second)[0], _patch_http(second)[1]:
            result = execute_writeback_pending(
                tmp_path, run_id, settings, _null_logger()
            )
        assert result["writes_performed"] == 1
        state = _load_state(tmp_path)
        b_record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-b"
        )
        assert b_record["outcome"] == "attach_existing"
        assert b_record["status"] == "attached"
        assert b_record["target_entity_id"] == 1001
        assert b_record["target_provenance"] == "thread_resolved"

    def test_conflicting_thread_references_execute_zero_mutation(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        settings = _writeback_settings(email_attach=True)
        _seed_state(
            tmp_path,
            [
                _created_lead_record("<msg-a@example.test>", remote_entity_id=1001),
                _created_lead_record("<msg-d@example.test>", remote_entity_id=1002),
            ],
        )
        run_dir = tmp_path / "runs" / "run-x"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-x",
                    "new_lead",
                    message_id="<msg-x@example.test>",
                    sender="client@example.com",
                    references="<msg-a@example.test> <msg-d@example.test>",
                )
            ],
            decisions=[_decision("evt-x", "new_lead")],
            reconciliation=[_recon_item("evt-x", "not_found")],
            routing=[_routing_item("evt-x", "matched")],
        )
        build_writeback_plan(tmp_path, "run-x", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-x", settings, _null_logger()
            )
        assert result["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        assert "crm.activity.add" not in methods
        state = _load_state(tmp_path)
        x_record = next(
            r for r in state["events"].values() if r.get("event_id") == "evt-x"
        )
        assert x_record["outcome"] == "deferred"
        assert x_record["reason_code"] == "ambiguous_thread_target"


class TestWritebackCli:
    def test_parser_accepts_writeback_plan_and_execute(self) -> None:
        parser = create_rop_parser()
        plan_args = parser.parse_args(["writeback", "plan", "--run-id", "run-1"])
        assert plan_args.rop_command == "writeback"
        assert plan_args.writeback_command == "plan"
        assert plan_args.run_id == "run-1"

        execute_args = parser.parse_args(
            ["writeback", "execute", "--run-id", "run-1", "--dry-run"]
        )
        assert execute_args.writeback_command == "execute"
        assert execute_args.run_id == "run-1"
        assert execute_args.dry_run is True

        execute_default = parser.parse_args(["writeback", "execute"])
        assert execute_default.run_id == "manual-execute"
        assert execute_default.dry_run is False
