from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient

from beeui_module.adapters.envelopes import AdapterErrorResult
from tests.beeui_console_support import _build_settings, _logger, _make_storage

from beeagent_module.core.rop_sender_blacklist import (
    SenderBlacklistError,
    add_sender_blacklist_email,
    add_sender_blacklist_entry,
    apply_sender_blacklist_policy,
    load_sender_blacklist,
    load_sender_blacklist_entries,
    remove_sender_blacklist_email,
    update_sender_blacklist_entry,
    write_sender_blacklist_audit,
)
from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter


def test_sender_blacklist_add_remove_and_idempotency(tmp_path: Path) -> None:
    email, changed = add_sender_blacklist_email(tmp_path, "Alice <ALICE@example.com>")

    assert (email, changed) == ("alice@example.com", True)
    assert add_sender_blacklist_email(tmp_path, "alice@example.com") == (
        "alice@example.com",
        False,
    )
    assert load_sender_blacklist(tmp_path) == ["alice@example.com"]
    assert remove_sender_blacklist_email(tmp_path, "ALICE@example.com") == (
        "alice@example.com",
        True,
    )


def test_sender_blacklist_rejects_malformed_state(tmp_path: Path) -> None:
    path = tmp_path / "interfaces" / "rop_sender_blacklist.json"
    path.parent.mkdir()
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(SenderBlacklistError, match="malformed"):
        load_sender_blacklist(tmp_path)


def test_sender_blacklist_v2_preserves_metadata_and_legacy_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "interfaces" / "rop_sender_blacklist.json"
    path.parent.mkdir()
    path.write_text('{"emails":["Legacy <legacy@example.com>"]}', encoding="utf-8")
    assert load_sender_blacklist_entries(tmp_path) == [
        {"name": "", "title": "", "email": "legacy@example.com", "reason": ""}
    ]
    entry, changed = add_sender_blacklist_entry(
        tmp_path,
        {
            "name": "<b>Alice</b>",
            "title": "Owner",
            "email": "alice@example.com",
            "reason": "Customer request",
        },
    )
    assert changed and entry["email"] == "alice@example.com"
    updated, changed = update_sender_blacklist_entry(
        tmp_path,
        "alice@example.com",
        {
            "name": "Alice",
            "title": "Owner",
            "email": "alice@example.com",
            "reason": "Customer request",
        },
    )
    assert changed and updated["reason"] == "Customer request"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["version"] == 2
    assert load_sender_blacklist(tmp_path) == [
        "alice@example.com",
        "legacy@example.com",
    ]


def test_sender_blacklist_prefers_original_sender_and_preserves_base(
    tmp_path: Path,
) -> None:
    add_sender_blacklist_email(tmp_path, "george@example.com")
    events = [
        {
            "sender": "technical-forwarder@example.com",
            "original_sender_email": "George <george@example.com>",
            "case_type": "new_lead",
            "recommended_queue": "sales",
            "correct_action": "create_lead",
            "should_rop_see": True,
            "base_classification": {"case_type": "new_lead"},
        }
    ]

    assert apply_sender_blacklist_policy(events, tmp_path) == 1
    assert events[0]["case_type"] == "irrelevant"
    assert events[0]["policy_override_reason"] == "sender_blacklisted"
    assert events[0]["base_classification"] == {"case_type": "new_lead"}


def test_sender_blacklist_audit_excludes_raw_email(tmp_path: Path) -> None:
    write_sender_blacklist_audit(
        tmp_path,
        action_id="rop_sender_blacklist_add",
        actor_id="operator",
        outcome="changed",
        email="alice@example.com",
    )

    text = (tmp_path / "interfaces" / "rop_sender_blacklist_audit.jsonl").read_text(
        encoding="utf-8"
    )
    record = json.loads(text)
    assert "alice@example.com" not in text
    assert record["email_sha256"]


def test_bitrix_blacklist_trigger_rereads_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from beeagent_module.core.rop_bitrix_blacklist import (
        process_blacklist_stage_trigger,
    )

    class Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def item_list(self, *_args: object, **_kwargs: object) -> dict:
            return {
                "result": {
                    "items": [
                        {
                            "id": 42,
                            "stageId": "BLACKLIST",
                            "name": "Alice",
                            "lastName": "Example",
                            "post": "Buyer",
                            "email": [{"VALUE": "Alice <ALICE@example.com>"}],
                            "UF_REASON": "Spam sender",
                        }
                    ]
                }
            }

    monkeypatch.setenv("TRIGGER_SECRET", "test-secret")
    monkeypatch.setenv("BITRIX_WEBHOOK", "https://example.test/rest")
    monkeypatch.setattr(
        "beeagent_module.core.rop_bitrix_blacklist.BitrixReadonlyClient", Client
    )
    settings = {
        "bitrix": {
            "webhook_env": "BITRIX_WEBHOOK",
            "timeout": 1,
            "page_size": 1,
            "pages_max": 1,
            "blacklist_trigger": {
                "enabled": True,
                "secret_env": "TRIGGER_SECRET",
                "stage_id": "BLACKLIST",
                "classification_field": "UF_REASON",
            },
        }
    }
    assert process_blacklist_stage_trigger(tmp_path, settings, "42", "test-secret") == (
        "ok",
        True,
    )
    assert process_blacklist_stage_trigger(tmp_path, settings, "42", "test-secret") == (
        "ok",
        False,
    )
    assert load_sender_blacklist(tmp_path) == ["alice@example.com"]
    assert load_sender_blacklist_entries(tmp_path) == [
        {
            "name": "Example Alice",
            "title": "Buyer",
            "email": "alice@example.com",
            "reason": "Spam sender",
        }
    ]


@pytest.mark.parametrize("reason", [None, " ", 123, "x" * 129])
def test_bitrix_blacklist_trigger_rejects_invalid_classification_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reason: object
) -> None:
    from beeagent_module.core.rop_bitrix_blacklist import (
        process_blacklist_stage_trigger,
    )

    class Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def item_list(self, *_args: object, **_kwargs: object) -> dict:
            return {
                "result": {
                    "items": [
                        {
                            "id": 42,
                            "stageId": "BLACKLIST",
                            "name": "Alice",
                            "email": "alice@example.com",
                            "UF_REASON": reason,
                        }
                    ]
                }
            }

    monkeypatch.setenv("TRIGGER_SECRET", "test-secret")
    monkeypatch.setenv("BITRIX_WEBHOOK", "https://example.test/rest")
    monkeypatch.setattr(
        "beeagent_module.core.rop_bitrix_blacklist.BitrixReadonlyClient", Client
    )
    settings = {
        "bitrix": {
            "webhook_env": "BITRIX_WEBHOOK",
            "timeout": 1,
            "page_size": 1,
            "pages_max": 1,
            "blacklist_trigger": {
                "enabled": True,
                "secret_env": "TRIGGER_SECRET",
                "stage_id": "BLACKLIST",
                "classification_field": "UF_REASON",
            },
        }
    }
    assert process_blacklist_stage_trigger(tmp_path, settings, "42", "test-secret") == (
        "invalid_classification",
        False,
    )
    assert load_sender_blacklist_entries(tmp_path) == []


def test_bitrix_blacklist_trigger_rejects_bad_auth_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from beeagent_module.core.rop_bitrix_blacklist import (
        process_blacklist_stage_trigger,
    )

    monkeypatch.setenv("TRIGGER_SECRET", "test-secret")
    settings = {
        "bitrix": {
            "blacklist_trigger": {"enabled": True, "secret_env": "TRIGGER_SECRET"}
        }
    }
    assert process_blacklist_stage_trigger(tmp_path, settings, "42", "wrong") == (
        "unauthorized",
        False,
    )
    assert load_sender_blacklist(tmp_path) == []


def test_bitrix_lead_update_event_uses_application_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from beeagent_module.core.rop_bitrix_blacklist import (
        process_bitrix_lead_update_event,
    )

    class Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def item_list(self, *_args: object, **_kwargs: object) -> dict:
            return {
                "result": [
                    {
                        "id": 42,
                        "stageId": "BLACKLIST",
                        "email": "alice@example.com",
                        "UF_REASON": "Spam sender",
                    }
                ]
            }

    monkeypatch.setenv("EVENT_TOKEN", "event-token")
    monkeypatch.setenv("BITRIX_WEBHOOK", "https://example.test/rest")
    monkeypatch.setattr(
        "beeagent_module.core.rop_bitrix_blacklist.BitrixReadonlyClient", Client
    )
    settings = {
        "bitrix": {
            "webhook_env": "BITRIX_WEBHOOK",
            "embedded_app": {"portal_origin": "https://example.test"},
            "blacklist_trigger": {
                "enabled": True,
                "event_app_token_env": "EVENT_TOKEN",
                "stage_id": "BLACKLIST",
                "classification_field": "UF_REASON",
            },
        }
    }
    event = {
        "event": "ONCRMLEADUPDATE",
        "data": {"FIELDS": {"ID": "42"}},
        "auth": {"application_token": "event-token", "domain": "example.test"},
    }
    assert process_bitrix_lead_update_event(tmp_path, settings, event) == ("ok", True)
    event["auth"]["application_token"] = "wrong"
    assert process_bitrix_lead_update_event(tmp_path, settings, event) == (
        "unauthorized",
        False,
    )


@pytest.mark.parametrize(
    ("response", "failure", "expected"),
    [
        (
            {
                "result": {
                    "items": [
                        {
                            "id": 42,
                            "stageId": "OTHER",
                            "email": "sender@example.com",
                            "UF_REASON": "Reason",
                        }
                    ]
                }
            },
            None,
            "wrong_stage",
        ),
        ({"result": {"items": []}}, None, "lead_unavailable"),
        (
            {
                "result": {
                    "items": [
                        {
                            "id": 42,
                            "stageId": "BLACKLIST",
                            "email": "invalid",
                            "UF_REASON": "Reason",
                        }
                    ]
                }
            },
            None,
            "connector_error",
        ),
        (
            {
                "result": {
                    "items": [
                        {
                            "id": 42,
                            "stageId": "BLACKLIST",
                            "email": [
                                {"VALUE": "one@example.com"},
                                {"VALUE": "two@example.com"},
                            ],
                            "UF_REASON": "Reason",
                        }
                    ]
                }
            },
            None,
            "invalid_sender",
        ),
        ({"result": {"items": "malformed"}}, None, "lead_unavailable"),
        (None, RuntimeError("auth failed"), "connector_error"),
        (None, TimeoutError("timeout"), "connector_error"),
    ],
)
def test_bitrix_blacklist_trigger_rejects_external_failures_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: object,
    failure: Exception | None,
    expected: str,
) -> None:
    from beeagent_module.core.rop_bitrix_blacklist import (
        process_blacklist_stage_trigger,
    )

    class Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def item_list(self, *_args: object, **_kwargs: object) -> object:
            if failure is not None:
                raise failure
            return response

    monkeypatch.setenv("TRIGGER_SECRET", "test-secret")
    monkeypatch.setenv("BITRIX_WEBHOOK", "https://example.test/rest")
    monkeypatch.setattr(
        "beeagent_module.core.rop_bitrix_blacklist.BitrixReadonlyClient", Client
    )
    settings = {
        "bitrix": {
            "webhook_env": "BITRIX_WEBHOOK",
            "timeout": 1,
            "page_size": 1,
            "pages_max": 1,
            "blacklist_trigger": {
                "enabled": True,
                "secret_env": "TRIGGER_SECRET",
                "stage_id": "BLACKLIST",
                "classification_field": "UF_REASON",
            },
        }
    }

    assert process_blacklist_stage_trigger(tmp_path, settings, "42", "test-secret") == (
        expected,
        False,
    )
    assert load_sender_blacklist(tmp_path) == []


def test_admin_can_manage_sender_blacklist_with_wildcard_scope(tmp_path: Path) -> None:
    adapter = BeeAgentUiAdapter(
        tmp_path,
        {"web": {"auth": {"principals": [{"id": "admin", "scopes": ["*"]}]}}},
    )

    result = adapter.execute_action(
        "rop_sender_blacklist_add",
        {"email": "admin-allowed@example.com"},
        actor={"user_id": "admin", "role": "admin"},
    )

    assert not isinstance(result, AdapterErrorResult)
    assert load_sender_blacklist(tmp_path) == ["admin-allowed@example.com"]


def test_blacklist_denials_are_audited_without_raw_email(tmp_path: Path) -> None:
    adapter = BeeAgentUiAdapter(
        tmp_path,
        {"web": {"auth": {"principals": [{"id": "operator", "scopes": []}]}}},
    )

    wrong_role = adapter.execute_action(
        "rop_sender_blacklist_remove",
        {"email": "denied@example.com"},
        actor={"user_id": "viewer", "role": "viewer"},
    )
    wrong_scope = adapter.execute_action(
        "rop_sender_blacklist_remove",
        {"email": "denied@example.com"},
        actor={"user_id": "operator", "role": "operator"},
    )

    assert isinstance(wrong_role, AdapterErrorResult)
    assert isinstance(wrong_scope, AdapterErrorResult)
    audit_text = (
        tmp_path / "interfaces" / "rop_sender_blacklist_audit.jsonl"
    ).read_text(encoding="utf-8")
    assert audit_text.count('"outcome":"permission_denied"') == 2
    assert "denied@example.com" not in audit_text


def test_blacklist_search_preserves_tab_and_page_size(tmp_path: Path) -> None:
    add_sender_blacklist_email(tmp_path, "123@example.com")
    add_sender_blacklist_email(tmp_path, "other@example.com")
    adapter = BeeAgentUiAdapter(tmp_path, {})

    result = adapter.get_page(
        "rop",
        {"tab": "blacklist", "lang": "ru", "page": "3", "page_size": "50", "q": "123"},
    )

    assert not isinstance(result, AdapterErrorResult)
    table = result.data["layout"][0]
    assert table["id"] == "rop-blacklist"
    assert table["toolbar"]["hidden"] == {
        "tab": "blacklist",
        "page_size": "50",
        "lang": "ru",
    }
    assert [row["email"]["label"] for row in table["rows"]] == ["123@example.com"]
    assert table["pagination"]["pages"][0]["active"]
    actions = table["rows"][0]["actions"]
    assert actions[0]["icon"] == "edit"
    assert "pending_action_id" not in actions[0]
    assert actions[1]["icon"] == "trash"


def test_bitrix_external_operator_blacklist_authority_is_bounded(
    tmp_path: Path,
) -> None:
    adapter = BeeAgentUiAdapter(tmp_path, {"web": {"auth": {"principals": []}}})

    viewer = adapter.execute_action(
        "rop_sender_blacklist_add",
        {"email": "viewer-denied@example.com"},
        actor={"user_id": "bitrix:42", "role": "viewer"},
    )
    operator = adapter.execute_action(
        "rop_sender_blacklist_add",
        {"email": "operator-allowed@example.com"},
        actor={"user_id": "bitrix:42", "role": "operator"},
    )
    source_write = adapter.execute_action(
        "rop_source_remove",
        {"source_id": "mailbox"},
        actor={"user_id": "bitrix:42", "role": "operator"},
    )

    assert isinstance(viewer, AdapterErrorResult)
    assert not isinstance(operator, AdapterErrorResult)
    assert isinstance(source_write, AdapterErrorResult)
    assert load_sender_blacklist(tmp_path) == ["operator-allowed@example.com"]


def _bitrix_callback_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, Path]:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    class Client:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def item_list(self, *_args: object, **_kwargs: object) -> dict:
            return {
                "result": {
                    "items": [
                        {
                            "id": 42,
                            "stageId": "BLACKLIST",
                            "email": "callback@example.com",
                            "UF_REASON": "Customer request",
                        }
                    ]
                }
            }

    settings = _build_settings()
    settings["bitrix"] = {
        "webhook_env": "BITRIX_WEBHOOK",
        "timeout": 1,
        "page_size": 1,
        "pages_max": 1,
        "embedded_app": {"portal_origin": "https://example.test"},
        "blacklist_trigger": {
            "enabled": True,
            "secret_env": "TRIGGER_SECRET",
            "event_app_token_env": "EVENT_TOKEN",
            "stage_id": "BLACKLIST",
            "classification_field": "UF_REASON",
        },
    }
    storage_dir = _make_storage(tmp_path)
    monkeypatch.setenv("TRIGGER_SECRET", "path-secret")
    monkeypatch.setenv("EVENT_TOKEN", "event-token")
    monkeypatch.setenv("BITRIX_WEBHOOK", "https://example.test/rest")
    monkeypatch.setattr(
        "beeagent_module.core.rop_bitrix_blacklist.BitrixReadonlyClient", Client
    )
    app = build_beeui_app(settings=settings, logger=_logger(), storage_dir=storage_dir)
    return TestClient(app), storage_dir


def test_bitrix_event_callback_is_bounded_authenticated_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, storage_dir = _bitrix_callback_client(tmp_path, monkeypatch)
    event = {
        "event": "ONCRMLEADUPDATE",
        "data": {"FIELDS": {"ID": "42"}},
        "auth": {"application_token": "event-token", "domain": "example.test"},
    }

    assert client.get("/api/bitrix/rop/events/path-secret").status_code == 405
    assert (
        client.post("/api/bitrix/rop/events/wrong-secret", json=event).status_code
        == 401
    )
    robot_payload = {"event": "ONCRMLEADUPDATE", "data[FIELDS][ID]": "42"}
    first = client.post("/api/bitrix/rop/events/path-secret", data=robot_payload)
    second = client.post("/api/bitrix/rop/events/path-secret", data=robot_payload)
    token = client.post("/api/bitrix/rop/events", json=event)
    malformed = client.post("/api/bitrix/rop/events/path-secret", content=b"{")
    oversized = client.post(
        "/api/bitrix/rop/events/path-secret",
        content=b"x" * 8193,
        headers={"content-type": "application/json"},
    )

    assert first.status_code == 200 and first.json()["data"]["changed"] is True
    assert second.status_code == 200 and second.json()["data"]["changed"] is False
    assert token.status_code == 200 and token.json()["data"]["changed"] is False
    assert malformed.status_code == 400
    assert oversized.status_code == 400
    assert load_sender_blacklist(storage_dir) == ["callback@example.com"]
