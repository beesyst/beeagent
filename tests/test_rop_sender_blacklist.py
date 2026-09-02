from pathlib import Path
import json

import pytest

from beeui_module.adapters.envelopes import AdapterErrorResult

from beeagent_module.core.rop_sender_blacklist import (
    SenderBlacklistError,
    add_sender_blacklist_email,
    apply_sender_blacklist_policy,
    load_sender_blacklist,
    remove_sender_blacklist_email,
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


def test_sender_blacklist_prefers_original_sender_and_preserves_base(tmp_path: Path) -> None:
    add_sender_blacklist_email(tmp_path, "george@example.com")
    events = [
        {
            "sender": "parsales@welding.kz",
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


def test_admin_can_manage_sender_blacklist_with_rop_scope(tmp_path: Path) -> None:
    adapter = BeeAgentUiAdapter(
        tmp_path,
        {"web": {"auth": {"principals": [{"id": "admin", "scopes": ["rop"]}]}}},
    )

    result = adapter.execute_action(
        "rop_sender_blacklist_add",
        {"email": "admin-allowed@example.com"},
        actor={"user_id": "admin", "role": "admin"},
    )

    assert not isinstance(result, AdapterErrorResult)
    assert load_sender_blacklist(tmp_path) == ["admin-allowed@example.com"]
