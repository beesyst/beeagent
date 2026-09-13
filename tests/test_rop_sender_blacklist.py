from pathlib import Path
import json

import pytest

from beeui_module.adapters.envelopes import AdapterErrorResult

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


def test_sender_blacklist_v2_preserves_metadata_and_legacy_state(tmp_path: Path) -> None:
    path = tmp_path / "interfaces" / "rop_sender_blacklist.json"
    path.parent.mkdir()
    path.write_text('{"emails":["Legacy <legacy@example.com>"]}', encoding="utf-8")
    assert load_sender_blacklist_entries(tmp_path) == [{"name": "", "title": "", "email": "legacy@example.com", "role": "User"}]
    entry, changed = add_sender_blacklist_entry(tmp_path, {"name": "<b>Alice</b>", "title": "Owner", "email": "alice@example.com", "role": "Admin"})
    assert changed and entry["email"] == "alice@example.com"
    updated, changed = update_sender_blacklist_entry(tmp_path, "alice@example.com", {"name": "Alice", "title": "Owner", "email": "alice@example.com", "role": "User"})
    assert changed and updated["role"] == "User"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["version"] == 2
    assert load_sender_blacklist(tmp_path) == ["alice@example.com", "legacy@example.com"]


def test_sender_blacklist_prefers_original_sender_and_preserves_base(tmp_path: Path) -> None:
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
    audit_text = (tmp_path / "interfaces" / "rop_sender_blacklist_audit.jsonl").read_text(encoding="utf-8")
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
    assert table["toolbar"]["hidden"] == {"tab": "blacklist", "page_size": "50", "lang": "ru"}
    assert [row["email"]["label"] for row in table["rows"]] == ["123@example.com"]
    assert table["pagination"]["pages"][0]["active"]
    actions = table["rows"][0]["actions"]
    assert actions[0]["icon"] == "edit"
    assert "pending_action_id" not in actions[0]
    assert actions[1]["icon"] == "trash"
