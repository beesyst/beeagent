import json
import logging
from pathlib import Path

import pytest

from beeagent_module.adapters.mailbox import ImapReadonlyMailboxClient
from beeagent_module.cases.rop_mailbox_poll import (
    _load_checkpoint,
    _select_poll_sources,
    _write_checkpoint,
    handle_mailbox_poll,
)


class _MultiPollMailbox:
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


def _multi_poll_settings() -> dict:
    return {
        "rop": {
            "mailbox_poll": {
                "enabled": True,
                "source_id": "source_a",
                "sources_all": True,
            },
            "sources": [
                {
                    "source_id": "source_a",
                    "source_type": "mailbox_readonly",
                    "authority": "read_only",
                    "enabled": True,
                    "items_max": 20,
                    "mailbox": {
                        "host": "imap.example",
                        "folder": "INBOX",
                        "username_env": "TEST_USER_A",
                        "password_env": "TEST_PASSWORD_A",
                        "port": 993,
                        "use_ssl": True,
                    },
                },
                {
                    "source_id": "source_b",
                    "source_type": "mailbox_readonly",
                    "authority": "read_only",
                    "enabled": True,
                    "items_max": 20,
                    "mailbox": {
                        "host": "imap.example",
                        "folder": "INBOX",
                        "username_env": "TEST_USER_B",
                        "password_env": "TEST_PASSWORD_B",
                        "port": 993,
                        "use_ssl": True,
                    },
                },
            ],
            "dashboard": {
                "default_period": "7d",
                "leaderboard": {"plan_lead": 20},
            },
        },
        "bitrix": {"enabled": True, "reconciliation": {"enabled": True}},
    }


def _multi_poll_env(monkeypatch) -> None:
    monkeypatch.setenv("TEST_USER_A", "user_a")
    monkeypatch.setenv("TEST_PASSWORD_A", "pass_a")
    monkeypatch.setenv("TEST_USER_B", "user_b")
    monkeypatch.setenv("TEST_PASSWORD_B", "pass_b")


def _patch_multi_mailboxes(
    monkeypatch, mailboxes: dict[str, _MultiPollMailbox]
) -> None:
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.ImapReadonlyMailboxClient",
        lambda _host, _port, _ssl, username, _password: mailboxes[username],
    )


def _patch_multi_postprocessing(monkeypatch) -> None:
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: {
            "status": "ok",
            "module_status": "ok",
            "source": {},
            "run_id": "run-" + str(_kwargs["source_id"]),
        },
    )
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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


def test_check_access_only_logs_in_and_selects_readonly_folder(monkeypatch):
    fake = _FakeImap()
    timeout: dict[str, object] = {}

    def client_factory(*_args, **kwargs):
        timeout.update(kwargs)
        return fake

    monkeypatch.setattr("imaplib.IMAP4_SSL", client_factory)
    ImapReadonlyMailboxClient("mail.example", 993, True, "u", "p").check_access(
        "INBOX", timeout_seconds=10.0
    )
    assert timeout == {"timeout": 10.0}
    assert fake.calls == [("select", {"readonly": True})]


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
            "dashboard": {
                "default_period": "7d",
                "leaderboard": {"plan_lead": 20},
            },
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
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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
        "build_recipient_routing_artifact",
        "export_review_tsv_for_run",
        "run_reconciliation",
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
        "build_recipient_routing_artifact": lambda *args, **kwargs: {},
        "export_review_tsv_for_run": lambda *args, **kwargs: "x",
        "run_reconciliation": lambda *args, **kwargs: {"status": "ok"},
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


def test_poll_all_sources_processes_all_enabled(monkeypatch, tmp_path: Path):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                },
                "source_b": {
                    "folder": "INBOX",
                    "uidvalidity": 9,
                    "last_processed_uid": 200,
                },
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(7, [101, 102]),
        "user_b": _MultiPollMailbox(9, [201, 202]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    _patch_multi_postprocessing(monkeypatch)
    handle_mailbox_poll(
        _multi_poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
    )
    data = json.loads(path.read_text())
    assert data["sources"]["source_a"]["last_processed_uid"] == 102
    assert data["sources"]["source_b"]["last_processed_uid"] == 202
    assert mailboxes["user_a"].fetched == [101, 102]
    assert mailboxes["user_b"].fetched == [201, 202]


def test_default_multi_source_selection_uses_canonical_registry(
    tmp_path: Path,
) -> None:
    settings = _multi_poll_settings()
    sources = settings["rop"].pop("sources")
    for source in sources:
        source.update(
            {
                "source_role": "technical_aggregator",
                "client_id": "test_client",
                "display_name": source["source_id"],
                "routing": {"email_recipient": "ops@example.test"},
            }
        )
    settings["rop"]["sources_path"] = "config/rop/sources.yml"
    registry_path = tmp_path / "config" / "rop" / "sources.yml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps({"version": 1, "sources": sources}), encoding="utf-8"
    )

    selected = _select_poll_sources(settings, tmp_path, all_sources=True)

    assert [source["source_id"] for source in selected] == ["source_a", "source_b"]


def test_cli_all_sources_overrides_configured_single_source(
    monkeypatch, tmp_path: Path
):
    settings = _multi_poll_settings()
    settings["rop"]["mailbox_poll"]["sources_all"] = False
    selected: list[str] = []

    def _poll(*_args, **kwargs):
        selected.append(kwargs["source"]["source_id"])

    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._poll_single_source",
        _poll,
    )
    handle_mailbox_poll(
        settings,
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
        all_sources=True,
    )
    assert selected == ["source_a", "source_b"]


def test_disabled_configured_source_is_a_clean_noop(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _multi_poll_settings()
    settings["rop"]["mailbox_poll"]["sources_all"] = False
    settings["rop"]["sources"][0]["enabled"] = False
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._poll_single_source",
        lambda **_kwargs: pytest.fail("disabled source must not be polled"),
    )
    with caplog.at_level(logging.INFO):
        handle_mailbox_poll(settings, tmp_path, tmp_path, logging.getLogger("test"))
    assert "no enabled selected sources" in caplog.text
    assert not (tmp_path / "interfaces" / "rop_mailbox_checkpoint.json").exists()


def test_all_sources_with_no_enabled_mailboxes_is_a_clean_noop(
    monkeypatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = _multi_poll_settings()
    for source in settings["rop"]["sources"]:
        source["enabled"] = False
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._poll_single_source",
        lambda **_kwargs: pytest.fail("disabled sources must not be polled"),
    )
    with caplog.at_level(logging.INFO):
        handle_mailbox_poll(settings, tmp_path, tmp_path, logging.getLogger("test"))
    assert "no enabled selected sources" in caplog.text
    assert not (tmp_path / "interfaces" / "rop_mailbox_checkpoint.json").exists()


def test_poll_multi_source_no_new_messages_skips_pipeline(monkeypatch, tmp_path: Path):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 200,
                },
                "source_b": {
                    "folder": "INBOX",
                    "uidvalidity": 9,
                    "last_processed_uid": 300,
                },
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(7, [100, 200]),
        "user_b": _MultiPollMailbox(9, [250, 300]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: pytest.fail("pipeline"),
    )
    settings = _multi_poll_settings()
    settings["bitrix"]["writeback"] = {
        "enabled": True,
        "webhook_env": "BITRIX_WRITEBACK_WEBHOOK_URL",
        "timeout": 10,
        "attempts_retry_max": 3,
        "dry_run": False,
        "email_attach": True,
        "file_attach": False,
        "source_id": "EMAIL",
        "stages": {"new_lead": "NEW", "irrelevant": "NEW"},
    }
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.execute_writeback_pending",
        lambda **_kwargs: pytest.fail("writeback execution"),
    )
    before = path.read_text()
    handle_mailbox_poll(settings, tmp_path, tmp_path, logging.getLogger("test"))
    assert mailboxes["user_a"].fetched == []
    assert mailboxes["user_b"].fetched == []
    assert path.read_text() == before


def test_poll_source_failure_isolated_and_checkpoint_preserved(
    monkeypatch, tmp_path: Path
):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                },
                "source_b": {
                    "folder": "INBOX",
                    "uidvalidity": 9,
                    "last_processed_uid": 200,
                },
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(7, [101, 102]),
        "user_b": _MultiPollMailbox(99, [201, 202]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    _patch_multi_postprocessing(monkeypatch)
    handle_mailbox_poll(
        _multi_poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
    )
    data = json.loads(path.read_text())
    assert data["sources"]["source_a"]["last_processed_uid"] == 102
    assert data["sources"]["source_b"]["last_processed_uid"] == 200


def test_poll_all_sources_fail_raises(monkeypatch, tmp_path: Path):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                },
                "source_b": {
                    "folder": "INBOX",
                    "uidvalidity": 9,
                    "last_processed_uid": 200,
                },
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(99, [101, 102]),
        "user_b": _MultiPollMailbox(98, [201, 202]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    _patch_multi_postprocessing(monkeypatch)
    with pytest.raises(RuntimeError, match="all selected sources"):
        handle_mailbox_poll(
            _multi_poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
        )
    data = json.loads(path.read_text())
    assert data["sources"]["source_a"]["last_processed_uid"] == 100
    assert data["sources"]["source_b"]["last_processed_uid"] == 200


def test_poll_new_source_baseline_preserves_existing_checkpoints(
    monkeypatch, tmp_path: Path
):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                }
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(7, [50, 100]),
        "user_b": _MultiPollMailbox(9, [10, 20, 30]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: pytest.fail("pipeline"),
    )
    handle_mailbox_poll(
        _multi_poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
    )
    data = json.loads(path.read_text())
    assert data["sources"]["source_a"] == {
        "folder": "INBOX",
        "uidvalidity": 7,
        "last_processed_uid": 100,
    }
    assert data["sources"]["source_b"]["folder"] == "INBOX"
    assert data["sources"]["source_b"]["uidvalidity"] == 9
    assert data["sources"]["source_b"]["last_processed_uid"] == 30
    assert mailboxes["user_a"].fetched == []
    assert mailboxes["user_b"].fetched == []


def test_poll_per_source_rebaseline_preserves_other_sources(
    monkeypatch, tmp_path: Path
):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                },
                "source_b": {
                    "folder": "INBOX",
                    "uidvalidity": 9,
                    "last_processed_uid": 200,
                },
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(7, [100]),
        "user_b": _MultiPollMailbox(9, [201, 202, 203]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case",
        lambda **_kwargs: pytest.fail("pipeline"),
    )
    handle_mailbox_poll(
        _multi_poll_settings(),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
        rebaseline=True,
        source_id="source_b",
    )
    data = json.loads(path.read_text())
    assert data["sources"]["source_a"]["last_processed_uid"] == 100
    assert data["sources"]["source_b"]["last_processed_uid"] == 203
    assert mailboxes["user_a"].fetched == []
    assert mailboxes["user_b"].fetched == []


def test_poll_source_id_override_polls_only_that_source(monkeypatch, tmp_path: Path):
    _multi_poll_env(monkeypatch)
    path = tmp_path / "interfaces" / "rop_mailbox_checkpoint.json"
    _write_checkpoint(
        path,
        {
            "version": 1,
            "sources": {
                "source_a": {
                    "folder": "INBOX",
                    "uidvalidity": 7,
                    "last_processed_uid": 100,
                },
                "source_b": {
                    "folder": "INBOX",
                    "uidvalidity": 9,
                    "last_processed_uid": 200,
                },
            },
        },
    )
    mailboxes = {
        "user_a": _MultiPollMailbox(7, [101, 102]),
        "user_b": _MultiPollMailbox(9, [201, 202]),
    }
    _patch_multi_mailboxes(monkeypatch, mailboxes)
    _patch_multi_postprocessing(monkeypatch)
    handle_mailbox_poll(
        _multi_poll_settings(),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
        source_id="source_a",
    )
    data = json.loads(path.read_text())
    assert data["sources"]["source_a"]["last_processed_uid"] == 102
    assert data["sources"]["source_b"]["last_processed_uid"] == 200
    assert mailboxes["user_a"].fetched == [101, 102]
    assert mailboxes["user_b"].fetched == []


def test_poll_source_id_and_all_sources_conflict(monkeypatch, tmp_path: Path):
    _multi_poll_env(monkeypatch)
    with pytest.raises(RuntimeError, match="cannot be used together"):
        handle_mailbox_poll(
            _multi_poll_settings(),
            tmp_path,
            tmp_path,
            logging.getLogger("test"),
            source_id="source_a",
            all_sources=True,
        )


def _writeback_poll_settings(writeback_enabled: bool) -> dict:
    settings = _poll_settings()
    settings["bitrix"]["writeback"] = {
        "enabled": writeback_enabled,
        "webhook_env": "BITRIX_WRITEBACK_WEBHOOK_URL",
        "timeout": 10,
        "attempts_retry_max": 3,
        "dry_run": False,
        "email_attach": True,
        "file_attach": False,
        "source_id": "EMAIL",
        "stages": {"new_lead": "NEW", "irrelevant": "NEW"},
    }
    return settings


def test_poll_persists_durable_writeback_intent_before_checkpoint_advance(
    monkeypatch, tmp_path: Path
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
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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
    order: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_writeback_plan",
        lambda **kwargs: order.append("plan"),
    )
    real_write_checkpoint = _write_checkpoint

    def recording_write_checkpoint(target_path: Path, data: dict) -> None:
        order.append("checkpoint")
        real_write_checkpoint(target_path, data)

    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._write_checkpoint",
        recording_write_checkpoint,
    )
    handle_mailbox_poll(
        _writeback_poll_settings(True),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
    )
    assert order == ["plan", "checkpoint"]
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 103
    )


def test_poll_writeback_enabled_failure_blocks_checkpoint_advance(
    monkeypatch, tmp_path: Path
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
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_writeback_plan",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("plan failed")),
    )
    with pytest.raises(RuntimeError, match="plan failed"):
        handle_mailbox_poll(
            _writeback_poll_settings(True),
            tmp_path,
            tmp_path,
            logging.getLogger("test"),
        )
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 100
    )


def test_poll_writeback_disabled_failure_does_not_block_checkpoint(
    monkeypatch, tmp_path: Path
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
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_writeback_plan",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("plan failed")),
    )
    handle_mailbox_poll(
        _writeback_poll_settings(False),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
    )
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 103
    )


def test_poll_writeback_enabled_executes_after_checkpoint(monkeypatch, tmp_path: Path):
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
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
    ):
        monkeypatch.setattr(
            "beeagent_module.cases.rop_mailbox_poll." + name,
            lambda *args, _result=result, **kwargs: _result,
        )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.export_review_tsv_for_run",
        lambda *_args, **_kwargs: "x",
    )
    order: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_rop_current_state",
        lambda *_args, **_kwargs: order.append("current_state") or {},
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.write_current_state",
        lambda *_args, **_kwargs: order.append("write_current_state"),
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_rop_dashboard",
        lambda *_args, **_kwargs: order.append("dashboard") or {},
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.write_rop_dashboard",
        lambda *_args, **_kwargs: order.append("write_dashboard"),
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.refresh_rop_web_projection",
        lambda **kwargs: order.append(f"projection:{kwargs['is_new_run']}"),
    )
    execute_kwargs: dict[str, object] = {}
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_writeback_plan",
        lambda **kwargs: order.append("plan"),
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.execute_writeback_pending",
        lambda **kwargs: (
            execute_kwargs.update(kwargs)
            or order.append("execute")
            or {"status": "executed", "writes_performed": 2}
        ),
    )
    real_write_checkpoint = _write_checkpoint

    def recording_write_checkpoint(target_path: Path, data: dict) -> None:
        order.append("checkpoint")
        real_write_checkpoint(target_path, data)

    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._write_checkpoint",
        recording_write_checkpoint,
    )
    handle_mailbox_poll(
        _writeback_poll_settings(True),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
    )
    assert order == [
        "plan",
        "current_state",
        "write_current_state",
        "dashboard",
        "write_dashboard",
        "projection:True",
        "checkpoint",
        "execute",
        "current_state",
        "write_current_state",
        "dashboard",
        "write_dashboard",
        "projection:False",
    ]
    assert execute_kwargs["scope_run_id"] == "run"
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 103
    )


def test_poll_writeback_disabled_does_not_execute(monkeypatch, tmp_path: Path):
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
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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
    order: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_writeback_plan",
        lambda **kwargs: order.append("plan"),
    )
    execute_called: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.execute_writeback_pending",
        lambda **kwargs: (
            execute_called.append("execute")
            or {"status": "executed", "writes_performed": 0}
        ),
    )
    real_write_checkpoint = _write_checkpoint

    def recording_write_checkpoint(target_path: Path, data: dict) -> None:
        order.append("checkpoint")
        real_write_checkpoint(target_path, data)

    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._write_checkpoint",
        recording_write_checkpoint,
    )
    handle_mailbox_poll(
        _writeback_poll_settings(False),
        tmp_path,
        tmp_path,
        logging.getLogger("test"),
    )
    assert order == ["plan", "checkpoint"]
    assert execute_called == []


def test_poll_degraded_reconciliation_persists_before_checkpoint(
    monkeypatch, tmp_path: Path
):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [101])
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
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "degraded"}),
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
    order: list[str] = []
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.build_writeback_plan",
        lambda **_kwargs: order.append("plan"),
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.execute_writeback_pending",
        lambda **_kwargs: (
            order.append("execute") or {"status": "executed", "writes_performed": 0}
        ),
    )
    real_write_checkpoint = _write_checkpoint
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll._write_checkpoint",
        lambda target_path, data: (
            order.append("checkpoint") or real_write_checkpoint(target_path, data)
        ),
    )
    handle_mailbox_poll(
        _writeback_poll_settings(True), tmp_path, tmp_path, logging.getLogger("test")
    )
    assert order == ["plan", "checkpoint", "execute"]
    checkpoint = json.loads(path.read_text())
    assert checkpoint["sources"]["source"]["last_processed_uid"] == 101


def test_poll_no_new_messages_does_not_recover_historical_writeback(
    monkeypatch, tmp_path: Path
):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [100])
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
        lambda **_kwargs: pytest.fail("mailbox ingestion"),
    )
    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.execute_writeback_pending",
        lambda **_kwargs: pytest.fail("writeback execution"),
    )
    handle_mailbox_poll(
        _writeback_poll_settings(True), tmp_path, tmp_path, logging.getLogger("test")
    )
    assert mailbox.fetched == []


def test_poll_no_new_messages_disabled_does_not_recover_writeback(
    monkeypatch, tmp_path: Path
):
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [100])
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
        "beeagent_module.cases.rop_mailbox_poll.execute_writeback_pending",
        lambda **_kwargs: pytest.fail("writeback execution"),
    )
    handle_mailbox_poll(
        _writeback_poll_settings(False), tmp_path, tmp_path, logging.getLogger("test")
    )
    assert mailbox.fetched == []


def test_poll_attachment_storage_failure_blocks_checkpoint_advance(
    monkeypatch, tmp_path: Path
) -> None:
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
            "status": "degraded",
            "module_status": "error",
            "source": {"malformed_count": 0},
            "run_id": "run",
        },
    )
    with pytest.raises(RuntimeError, match="did not complete successfully"):
        handle_mailbox_poll(
            _poll_settings(), tmp_path, tmp_path, logging.getLogger("test")
        )
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 100
    )
    assert not (tmp_path / "attachments").exists()


def test_poll_attachment_blobs_persist_before_checkpoint_advance(
    monkeypatch, tmp_path: Path
) -> None:
    _poll_env(monkeypatch)
    mailbox = _PollMailbox(7, [101])
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
    captured: dict[str, str] = {}

    def _fake_batch(**kwargs):
        storage_dir = kwargs["storage_dir"]
        run_id = kwargs.get("run_id") or "run"
        assert isinstance(run_id, str)
        store_dir = storage_dir / "attachments" / run_id
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "att-blob.bin").write_bytes(b"blob-bytes")
        (store_dir / "attachment_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "version": 1,
                    "status": "ok",
                    "aggregate": {"stored_count": 1},
                    "items": [],
                }
            ),
            encoding="utf-8",
        )
        captured["run_id"] = run_id
        return {
            "status": "ok",
            "module_status": "ok",
            "source": {"malformed_count": 0},
            "run_id": run_id,
        }

    monkeypatch.setattr(
        "beeagent_module.cases.rop_mailbox_poll.run_rop_batch_case", _fake_batch
    )
    for name, result in (
        ("build_recipient_routing_artifact", {}),
        ("run_reconciliation", {"status": "ok"}),
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
        lambda *args, **kwargs: None,
    )
    handle_mailbox_poll(_poll_settings(), tmp_path, tmp_path, logging.getLogger("test"))
    run_id = captured["run_id"]
    assert (tmp_path / "attachments" / run_id / "attachment_manifest.json").exists()
    assert (
        json.loads(path.read_text())["sources"]["source"]["last_processed_uid"] == 101
    )
