import json
import logging
from pathlib import Path

import pytest

from beeagent_module.adapters.mailbox import ImapReadonlyMailboxClient
from beeagent_module.cases.rop_mailbox_poll import (
    _load_checkpoint,
    _write_checkpoint,
    handle_mailbox_poll,
)


class _FakeImap:
    def __init__(
        self,
        *,
        uidvalidity_response_name: str = "UIDVALIDITY",
        uidvalidity: bytes = b"42",
        uid_search_payload: bytes | None = b"9 2 7",
    ) -> None:
        self.calls = []
        self.uidvalidity_response_name = uidvalidity_response_name
        self.uidvalidity = uidvalidity
        self.uid_search_payload = uid_search_payload

    def login(self, *_args):
        return "OK", []

    def select(self, *_args, **kwargs):
        self.calls.append(("select", kwargs))
        return "OK", []

    def response(self, name: str) -> tuple[str, list[bytes | None]]:
        assert name == "UIDVALIDITY"
        return self.uidvalidity_response_name, [self.uidvalidity]

    def uid(self, command, *args):
        self.calls.append(("uid", command, args))
        if command == "SEARCH":
            return "OK", [self.uid_search_payload]
        return "OK", [(b"1 (BODY[] {3}", b"raw")]

    def logout(self):
        pass


def test_uid_poll_uses_readonly_uid_and_body_peek(monkeypatch):
    fake = _FakeImap()
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *_args: fake)
    client = ImapReadonlyMailboxClient("mail.example", 993, True, "u", "p")
    assert client.uid_state("INBOX") == (42, [2, 7, 9])
    assert ("uid", "SEARCH", ("ALL",)) in fake.calls
    assert client.fetch_uids("INBOX", [7], expected_uidvalidity=42) == [b"raw"]
    assert all(call[1].get("readonly") for call in fake.calls if call[0] == "select")
    assert ("uid", "FETCH", ("7", "(BODY.PEEK[])")) in fake.calls


def test_checkpoint_atomic_writer_preserves_other_sources(tmp_path: Path):
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    data = {
        "version": 1,
        "sources": {
            "other": {"folder": "INBOX", "uidvalidity": 1, "last_processed_uid": 2},
            "hotline_mailbox": {
                "folder": "INBOX",
                "uidvalidity": 3,
                "last_processed_uid": 4,
            },
        },
    }
    _write_checkpoint(path, data)
    assert json.loads(path.read_text()) == data
    assert _load_checkpoint(path, "hotline_mailbox", "INBOX") == data


def test_corrupt_checkpoint_fails_closed(tmp_path: Path):
    path = tmp_path / "rop_mailbox_checkpoint.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="rebaseline"):
        _load_checkpoint(path, "hotline_mailbox", "INBOX")


def test_uid_state_rejects_non_positive_uidvalidity(monkeypatch):
    fake = _FakeImap(uidvalidity=b"0")
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *_args: fake)
    client = ImapReadonlyMailboxClient("mail.example", 993, True, "u", "p")
    with pytest.raises(RuntimeError, match="UIDVALIDITY invalid"):
        client.uid_state("INBOX")


def test_uid_fetch_fails_before_fetch_when_epoch_changes(monkeypatch):
    first = _FakeImap()
    second = _FakeImap(uidvalidity=b"43")
    clients = iter((first, second))
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *_args: next(clients))
    client = ImapReadonlyMailboxClient("mail.example", 993, True, "u", "p")
    assert client.uid_state("INBOX") == (42, [2, 7, 9])
    with pytest.raises(RuntimeError, match="changed during poll"):
        client.fetch_uids("INBOX", [7], expected_uidvalidity=42)
    assert not any(call[0] == "uid" and call[1] == "FETCH" for call in second.calls)


def test_uidvalidity_response_name_must_match_stdlib_contract(monkeypatch):
    fake = _FakeImap(uidvalidity_response_name="OK")
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *_args: fake)
    client = ImapReadonlyMailboxClient("mail.example", 993, True, "u", "p")
    with pytest.raises(RuntimeError, match="UIDVALIDITY unavailable"):
        client.uid_state("INBOX")


def test_uid_state_rejects_malformed_search_payload(monkeypatch):
    fake = _FakeImap(uid_search_payload=None)
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *_args: fake)
    client = ImapReadonlyMailboxClient("mail.example", 993, True, "u", "p")
    with pytest.raises(RuntimeError, match="invalid UID"):
        client.uid_state("INBOX")


@pytest.mark.parametrize(
    "key,value", [("uidvalidity", True), ("last_processed_uid", False)]
)
def test_checkpoint_boolean_uid_values_fail_closed(
    tmp_path: Path, key: str, value: bool
):
    path = tmp_path / "rop_mailbox_checkpoint.json"
    data = {
        "version": 1,
        "sources": {
            "source": {
                "folder": "INBOX",
                "uidvalidity": 4,
                "last_processed_uid": 3,
            }
        },
    }
    data["sources"]["source"][key] = value
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError, match="rebaseline"):
        _load_checkpoint(path, "source", "INBOX")
    assert json.loads(path.read_text()) == data


def test_missing_mailbox_env_fails_before_connecting(monkeypatch, tmp_path: Path):
    settings = {
        "rop": {
            "mailbox_poll": {"enabled": True, "source_id": "configured"},
            "sources": [
                {
                    "source_id": "configured",
                    "source_type": "mailbox_readonly",
                    "authority": "read_only",
                    "items_max": 20,
                    "mailbox": {
                        "host_env": "TEST_HOST",
                        "folder_env": "TEST_FOLDER",
                        "username_env": "TEST_USER",
                        "password_env": "TEST_PASSWORD",
                        "port": 993,
                        "use_ssl": True,
                    },
                }
            ],
        },
    }
    monkeypatch.delenv("TEST_HOST", raising=False)
    monkeypatch.delenv("TEST_FOLDER", raising=False)
    monkeypatch.setenv("TEST_USER", "user")
    monkeypatch.setenv("TEST_PASSWORD", "password")
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: pytest.fail("IMAP must not connect"),
    )
    with pytest.raises(RuntimeError, match="Missing required mailbox environment"):
        handle_mailbox_poll(
            settings, tmp_path, tmp_path, __import__("logging").getLogger("test")
        )
    assert not (tmp_path / "interfaces" / "rop_mailbox_checkpoint.json").exists()


class _PollMailbox:
    def __init__(self, uidvalidity: int, uids: list[int]) -> None:
        self.uidvalidity = uidvalidity
        self.uids = uids
        self.fetched: list[int] = []

    def uid_state(self, _folder: str):
        return self.uidvalidity, self.uids

    def fetch_uids(self, _folder: str, uids: list[int], *, expected_uidvalidity: int):
        assert expected_uidvalidity == self.uidvalidity
        self.fetched = uids
        return [b"raw"] * len(uids)


def _poll_settings() -> dict:
    return {
        "rop": {
            "mailbox_poll": {"enabled": True, "source_id": "source"},
            "sources": [
                {
                    "source_id": "source",
                    "source_type": "mailbox_readonly",
                    "authority": "read_only",
                    "items_max": 20,
                    "mailbox": {
                        "host": "imap.example",
                        "folder": "INBOX",
                        "username_env": "TEST_USER",
                        "password_env": "TEST_PASSWORD",
                        "port": 993,
                        "use_ssl": True,
                    },
                }
            ],
            "dashboard": {"default_period": "7d"},
        },
        "bitrix": {"enabled": True, "reconciliation": {"enabled": True}},
    }


def _poll_env(monkeypatch):
    monkeypatch.setenv("TEST_USER", "user")
    monkeypatch.setenv("TEST_PASSWORD", "password")


def test_poll_baseline_and_no_new_skip_pipeline(monkeypatch, tmp_path: Path):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [1, 2, 3])
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: mailbox,
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: pytest.fail("pipeline"),
    )
    handle_mailbox_poll(_poll_settings(), tmp_path, tmp_path, logging.getLogger("test"))
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    baseline = json.loads(path.read_text())
    assert baseline["sources"]["source"]["last_processed_uid"] == 3
    assert mailbox.fetched == []
    before = path.read_text()
    handle_mailbox_poll(_poll_settings(), tmp_path, tmp_path, logging.getLogger("test"))
    assert path.read_text() == before


def test_poll_oldest_batch_advances_checkpoint_after_full_flow(
    monkeypatch, tmp_path: Path
):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, list(range(101, 151)))
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                }
            },
        },
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: mailbox,
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: {"status": "ok", "module_status": "ok", "run_id": "run"},
    )
    for name, result in (
        ("run_reconciliation", {"status": "ok"}),
        ("build_action_drafts", {}),
        ("build_context_enrichment", {}),
        ("write_context_enrichment_artifact", None),
        ("build_routing_map", {}),
        ("build_recommendations", {}),
        ("build_rop_current_state", {}),
        ("write_current_state", None),
        ("build_rop_dashboard", {}),
        ("write_rop_dashboard", None),
    ):
        monkeypatch.setattr(
            "beeagent_module.cases.rop_mailbox_poll." + name,
            lambda *args, _result=result, **kwargs: _result,
        )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.export_review_tsv_for_run",
        lambda *_args, **_kwargs: "x",
    )
    handle_mailbox_poll(_poll_settings(), tmp_path, tmp_path, logging.getLogger("test"))
    assert mailbox.fetched == list(range(101, 121))
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 120
    )


def test_poll_malformed_batch_does_not_advance_checkpoint(monkeypatch, tmp_path: Path):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [101, 102, 103])
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                }
            },
        },
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: mailbox,
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: {
            "status": "ok",
            "module_status": "ok",
            "source": {"malformed_count": 1},
            "run_id": "run",
        },
    )
    with pytest.raises(RuntimeError, match="malformed"):
        handle_mailbox_poll(
            _poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
        )
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 100
    )


def test_poll_rebaseline_recovers_from_non_dict_checkpoint(monkeypatch, tmp_path: Path):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [10, 20, 30])
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: mailbox,
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: pytest.fail("pipeline"),
    )
    handle_mailbox_poll(
        _poll_settings(),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
        rebaseline=True,
    )
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert data["sources"]["source"]["uidvalidity"] == 7
    assert data["sources"]["source"]["last_processed_uid"] == 30
    assert mailbox.fetched == []


def test_poll_rebaseline_preserves_other_sources_and_replaces_stale_source(
    monkeypatch, tmp_path: Path
):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [10, 20, 30])
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "other": {"folder": "INBOX", "uidvalidity": 3, "last_processed_uid": 5},
                "source": {
                    "folder": "OLD",
                    "uidvalidity": 1,
                    "last_processed_uid": 2,
                },
            },
        },
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: mailbox,
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: pytest.fail("pipeline"),
    )
    handle_mailbox_poll(
        _poll_settings(),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
        rebaseline=True,
    )
    data = json.loads(path.read_text())
    assert data["sources"]["other"] == {
        "folder": "INBOX",
        "uidvalidity": 3,
        "last_processed_uid": 5,
    }
    assert data["sources"]["source"]["folder"] == "INBOX"
    assert data["sources"]["source"]["uidvalidity"] == 7
    assert data["sources"]["source"]["last_processed_uid"] == 30
    assert mailbox.fetched == []


@pytest.mark.parametrize(
    "failing_stage",
    [
        "export_review_tsv_for_run",
        "run_reconciliation",
        "build_action_drafts",
        "build_recommendations",
        "write_current_state",
        "build_rop_dashboard",
        "write_rop_dashboard",
    ],
)
def test_poll_commit_gate_at_least_once_on_postprocessing_failure(
    monkeypatch, tmp_path: Path, failing_stage: str
):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [101, 102, 103])
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                }
            },
        },
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda *_args: mailbox,
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: {"status": "ok", "module_status": "ok", "run_id": "run"},
    )
    successful = {
        "export_review_tsv_for_run": lambda *args, **kwargs: "x",
        "run_reconciliation": lambda *args, **kwargs: {"status": "ok"},
        "build_action_drafts": lambda *args, **kwargs: {},
        "build_context_enrichment": lambda *args, **kwargs: {},
        "write_context_enrichment_artifact": lambda *args, **kwargs: None,
        "build_routing_map": lambda *args, **kwargs: {},
        "build_recommendations": lambda *args, **kwargs: {},
        "build_rop_current_state": lambda *args, **kwargs: {},
        "write_current_state": lambda *args, **kwargs: None,
        "build_rop_dashboard": lambda *args, **kwargs: {},
        "write_rop_dashboard": lambda *args, **kwargs: None,
    }
    for name, mock in successful.items():
        monkeypatch.setattr(
            "beeagent_module.cases.rop_mailbox_poll." + name,
            mock,
        )

    def _fail(*_args, **_kwargs):
        raise RuntimeError("stage failed")

    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll." + failing_stage,
        _fail,
    )
    with pytest.raises(RuntimeError, match="stage failed"):
        handle_mailbox_poll(
            _poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
        )
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 100
    )
