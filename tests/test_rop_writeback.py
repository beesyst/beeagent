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
from beeagent_module.cases.rop_writeback import (
    WRITEBACK_STATE_FILENAME,
    WRITEBACK_SUMMARY_FILENAME,
    _load_state,
    _origin_id,
    _stable_identity,
    _stable_remote_id,
    build_writeback_plan,
    execute_writeback_pending,
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
    retry_max: int = 3,
    webhook_env: str = "BITRIX_WRITEBACK_WEBHOOK_URL",
    attach_email: bool = False,
    source_id: str = "",
    fallback_responsible_user_id: int | None = None,
) -> dict:
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
            },
            "writeback": {
                "enabled": enabled,
                "webhook_env": webhook_env,
                "timeout": 10,
                "retry_attempts_max": retry_max,
                "dry_run": dry_run,
                "attach_email": attach_email,
                "source_id": source_id,
                "fallback_responsible_user_id": fallback_responsible_user_id,
                "stages": stages or {"new_lead": "NEW", "irrelevant": "NEW"},
            },
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
    subject: str = "Test subject",
    sender: str = "",
    from_name: str = "",
    body_preview: str = "",
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
        "subject": subject,
        "sender": sender,
        "from_name": from_name,
        "body_preview": body_preview,
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
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_instance_id": instance,
        "bitrix_match_status": status,
        "bitrix_match_quality": status,
        "safe_to_use_as_target": safe,
        "bitrix_entity_type": entity_type,
        "bitrix_entity_id": entity_id,
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
        except (json.JSONDecodeError, UnicodeDecodeError):
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
        validate_settings(settings)

    def test_fallback_responsible_user_id_accepts_positive_int(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["fallback_responsible_user_id"] = 1563
        validate_settings(settings)

    def test_fallback_responsible_user_id_rejects_non_positive(self) -> None:
        for bad_value in (0, -1, "1563", True, 3.5):
            settings = self._load()
            settings["bitrix"]["writeback"]["fallback_responsible_user_id"] = (
                bad_value
            )
            with pytest.raises(RuntimeError) as exc_info:
                validate_settings(settings)
            assert "fallback_responsible_user_id" in str(exc_info.value)

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

    def test_attach_email_must_be_bool(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["attach_email"] = "yes"
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "attach_email" in str(exc_info.value)

    def test_source_id_must_be_string_or_null(self) -> None:
        settings = self._load()
        settings["bitrix"]["writeback"]["source_id"] = 123
        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "source_id" in str(exc_info.value)


class TestWriteClientBoundary:
    def test_write_allowed_methods_are_bounded(self) -> None:
        assert WRITE_ALLOWED_METHODS == frozenset(
            {"crm.item.add", "crm.activity.add"}
        )

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
        assert fields["COMPLETED"] == "Y"
        assert fields["COMMUNICATIONS"][0]["VALUE"] == "sender@example.com"
        assert fields["COMMUNICATIONS"][0]["TYPE"] == "EMAIL"

    def test_build_write_client_uses_dedicated_env(
        self, writeback_env: None
    ) -> None:
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
                    message_id="msg-1",
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
                    "evt-1", "new_lead", message_id="msg-1", subject="Buy equipment"
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
            _stable_identity("welding", "hotline_mailbox", "msg-1")
        )

    def test_safe_existing_lead_attaches_no_new_lead(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_lead",
                    safe=True,
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
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_type"] == "lead"
        assert record["target_entity_id"] == 253

    def test_safe_existing_deal_attaches(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "existing_deal", message_id="msg-1")
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
        assert record["outcome"] == "attach_existing"
        assert record["target_entity_type"] == "deal"
        assert record["target_entity_id"] == 88

    def test_existing_deal_without_target_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "existing_deal", message_id="msg-1")
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
            classified=[
                _classified_event("evt-1", "duplicate", message_id="msg-1")
            ],
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

    def test_ambiguous_target_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "ambiguous")],
            routing=[_routing_item("evt-1", "matched")],
        )
        plan = build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        record = plan["events"][0]
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "ambiguous_target"

    def test_duplicate_candidate_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
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
                _classified_event("evt-1", "new_lead", message_id="msg-1")
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
        assert record["outcome"] == "deferred"
        assert record["reason_code"] == "unsafe_target"

    def test_connector_degraded_defers(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
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

    def test_fallback_responsible_used_when_routing_unresolved(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        plan = build_writeback_plan(
            tmp_path,
            "run-wb",
            _writeback_settings(fallback_responsible_user_id=1563),
            _null_logger(),
        )
        record = plan["events"][0]
        assert record["outcome"] == "create_lead"
        assert record["responsible_status"] == "fallback"
        assert record["responsible_user_id"] == 1563
        assert (
            record["responsible_reason"] == "fallback_responsible_configured"
        )

    def test_event_without_stable_identity_is_not_planned(
        self, tmp_path: Path
    ) -> None:
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
                _classified_event("evt-1", "new_lead", message_id="msg-1"),
                _classified_event("evt-1", "new_lead", message_id="msg-1"),
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
            "welding", "hotline_mailbox", "msg-1"
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
                    message_id="msg-1",
                ),
                _classified_event(
                    "evt-1",
                    "duplicate",
                    instance="event-000002",
                    message_id="msg-1",
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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
                    "evt-1", "new_lead", message_id="msg-1", subject="Buy machine"
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched", user_id=42)],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
        add_call = next(call for call in recorder.calls if call["method"] == "crm.item.add")
        assert add_call["payload"]["entityTypeId"] == 1
        fields = add_call["payload"]["fields"]
        assert fields["STAGE_ID"] == "NEW"
        assert fields["ASSIGNED_BY_ID"] == 42
        assert fields["ORIGINATOR_ID"] == "beeagent-rop"
        assert fields["ORIGIN_ID"] == _origin_id(
            _stable_identity("welding", "hotline_mailbox", "msg-1")
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
                    message_id="msg-1",
                    subject="Test subject",
                    sender="sender@example.com",
                    body_preview="Hello, this is the body.",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(attach_email=True, source_id="EMAIL")
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        assert result["writes_performed"] == 1
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
                    message_id="msg-1",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(attach_email=True)
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
                    message_id="msg-1",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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

    def test_create_lead_retries_email_attach_after_failure(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event(
                    "evt-1",
                    "new_lead",
                    message_id="msg-1",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(attach_email=True)
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

        recorder2 = _HttpRecorder(_default_handler)
        with _patch_http(recorder2)[0], _patch_http(recorder2)[1]:
            execute_writeback_pending(tmp_path, "run-wb", settings, _null_logger())
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["email_activity_id"] == 9001
        assert record["last_attach_error_code"] is None
        item_adds = [
            call for call in recorder2.calls if call["method"] == "crm.item.add"
        ]
        assert item_adds == []
        activity_calls = [
            call for call in recorder2.calls if call["method"] == "crm.activity.add"
        ]
        assert len(activity_calls) == 1

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
                    message_id="msg-1",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(attach_email=True)
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

        disabled_settings = _writeback_settings(attach_email=False)
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
                    message_id="msg-1",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
                    message_id="msg-1",
                    sender="sender@example.com",
                    from_name="Иван Петров",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["NAME"] == "Иван Петров"

    def test_create_lead_uses_fallback_responsible_when_routing_unresolved(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "not_found", user_id=None)],
        )
        settings = _writeback_settings(fallback_responsible_user_id=1563)
        build_writeback_plan(tmp_path, "run-wb", settings, _null_logger())
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            execute_writeback_pending(
                tmp_path, "run-wb", settings, _null_logger()
            )
        add_call = next(
            call for call in recorder.calls if call["method"] == "crm.item.add"
        )
        assert add_call["payload"]["fields"]["ASSIGNED_BY_ID"] == 1563

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
                    message_id="msg-1",
                    sender="Иван Петров <sender@example.com>",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
                    message_id="msg-1",
                    sender="sender@example.com",
                )
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
                    return json.dumps(
                        {"result": {"items": [{"id": 2002}]}}
                    ).encode("utf-8")
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(retry_max=2)
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        settings = _writeback_settings(retry_max=2)
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
                execute_writeback_pending(
                    tmp_path, "run-wb", settings, _null_logger()
                )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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

    def test_terminal_401_fails_and_is_not_retried(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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

    def test_terminal_400_fails_not_retried(self, tmp_path: Path, writeback_env: None) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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

    def test_api_error_fails_terminal(self, tmp_path: Path, writeback_env: None) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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

    def test_malformed_response_is_uncertain(self, tmp_path: Path, writeback_env: None) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

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

    def test_attach_existing_defers_pending_binding_contract(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[
                _recon_item(
                    "evt-1",
                    "matched_lead",
                    safe=True,
                    entity_type="lead",
                    entity_id=253,
                )
            ],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
        recorder = _HttpRecorder(_default_handler)
        with _patch_http(recorder)[0], _patch_http(recorder)[1]:
            result = execute_writeback_pending(
                tmp_path, "run-wb", _writeback_settings(), _null_logger()
            )
        assert result["writes_performed"] == 0
        methods = [call["method"] for call in recorder.calls]
        assert "crm.item.add" not in methods
        state = _load_state(tmp_path)
        record = list(state["events"].values())[0]
        assert record["outcome"] == "attach_existing"
        assert record["status"] == "deferred"
        assert record["reason_code"] == "email_binding_contract_unconfirmed"

    def test_recovered_via_bitrix_lookup_no_post(
        self, tmp_path: Path, writeback_env: None
    ) -> None:
        run_dir = tmp_path / "runs" / "run-wb"
        _write_artifacts(
            run_dir,
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )

        def found_in_bitrix(call: dict[str, Any]) -> bytes:
            if call["method"] == "crm.item.list":
                return json.dumps(
                    {"result": {"items": [{"id": 555}]}}
                ).encode("utf-8")
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
            classified=[
                _classified_event("evt-1", "new_lead", message_id="msg-1")
            ],
            decisions=[_decision("evt-1", "new_lead")],
            reconciliation=[_recon_item("evt-1", "not_found")],
            routing=[_routing_item("evt-1", "matched")],
        )
        build_writeback_plan(
            tmp_path, "run-wb", _writeback_settings(), _null_logger()
        )
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
