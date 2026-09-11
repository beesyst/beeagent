from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import yaml

from beeagent_module.adapters.bitrix_client import BitrixConnectorError
from beeagent_module.cases.rop_recipient_routing import (
    ROP_RECIPIENT_ROUTING_ARTIFACT,
    build_recipient_routing_artifact,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_recipient_routing")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _settings(
    *,
    bitrix_enabled: bool = False,
    source_recipient: str = "",
    page_size: int = 50,
    pages_max: int = 3,
) -> dict:
    source = {
        "source_id": "hotline",
        "source_type": "mailbox_readonly",
        "source_role": "technical_aggregator",
        "client_id": "welding",
        "display_name": "Hotline",
        "enabled": True,
        "authority": "read_only",
        "items_max": 20,
        "mailbox": {
            "host": "imap.example.com",
            "port": 993,
            "use_ssl": True,
            "folder": "INBOX",
            "username_env": "ROP_MAILBOX_USERNAME",
            "password_env": "ROP_MAILBOX_PASSWORD",
        },
    }
    if source_recipient:
        source["routing"] = {"email_recipient": source_recipient}
    return {
        "rop": {"sources": [source]},
        "bitrix": {
            "enabled": bitrix_enabled,
            "page_size": page_size,
            "pages_max": pages_max,
        },
    }


def _write_run(storage_dir: Path, run_id: str, events: list[dict]) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "normalized_events.json").write_text(
        json.dumps(events, ensure_ascii=False),
        encoding="utf-8",
    )
    return run_dir


def _event(
    event_id: str = "evt-1",
    instance_id: str = "event-000001",
    source_id: str = "hotline",
    *,
    to: list | None = None,
    cc: list | None = None,
    original_recipient: str = "",
) -> dict:
    return {
        "event_id": event_id,
        "event_instance_id": instance_id,
        "source_id": source_id,
        "source_role": "technical_aggregator",
        "source_display_name": "Hotline",
        "client_id": "welding",
        "to": to if to is not None else [],
        "cc": cc if cc is not None else [],
        "original_recipient": original_recipient,
    }


class _FakeBitrixClient:
    def __init__(self, users: list[dict], pages: int = 1) -> None:
        self._users = users
        self._pages = pages
        self.calls: list[dict] = []

    def list_users(self, select=None, start=0, limit=None):
        self.calls.append({"select": select, "start": start, "limit": limit})
        page_size = limit if limit else len(self._users)
        begin = start if start else 0
        page = self._users[begin : begin + page_size]
        next_start = None
        if begin + len(page) < len(self._users):
            next_start = begin + len(page)
        return {"result": page, "next": next_start}


class _RaisingBitrixClient:
    def list_users(self, select=None, start=0, limit=None):
        raise BitrixConnectorError("connection refused")


def _load_artifact(storage_dir: Path, run_id: str) -> dict:
    path = storage_dir / "runs" / run_id / ROP_RECIPIENT_ROUTING_ARTIFACT
    return json.loads(path.read_text(encoding="utf-8"))


def _active_user(user_id: int, email: str, active: str = "Y") -> dict:
    return {
        "ID": user_id,
        "EMAIL": email,
        "ACTIVE": active,
        "NAME": "Ivan",
        "LAST_NAME": "Petrov",
        "WORK_POSITION": "Manager",
    }


class TestRecipientAttribution:
    def test_original_recipient_precedes_to(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-orig",
            [
                _event(
                    original_recipient="Manager <boss@welding.kz>",
                    to=["hotline@welding.kz"],
                )
            ],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-orig", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient"] == "boss@welding.kz"
        assert item["recipient_evidence_source"] == "original_recipient"
        assert item["recipient_status"] == "resolved"

    def test_to_fallback_when_no_original_recipient(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-to",
            [_event(to=["Hotline <hotline@welding.kz>"])],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-to", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient"] == "hotline@welding.kz"
        assert item["recipient_evidence_source"] == "to"
        assert item["recipient_status"] == "resolved"

    def test_configured_source_recipient_fallback(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-fallback",
            [_event()],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-fallback",
            _settings(source_recipient="fallback@welding.kz"),
            _null_logger(),
        )
        item = artifact["items"][0]
        assert item["recipient"] == "fallback@welding.kz"
        assert item["recipient_evidence_source"] == "source_recipient"

    def test_canonical_source_recipient_fallback(self, tmp_path: Path) -> None:
        _write_run(tmp_path, "run-canonical-fallback", [_event()])
        source = _settings(source_recipient="fallback@welding.kz")["rop"]["sources"][0]
        registry = tmp_path / "config" / "rop"
        registry.mkdir(parents=True)
        (registry / "sources.yml").write_text(
            yaml.safe_dump({"version": 1, "sources": [source]}, sort_keys=False),
            encoding="utf-8",
        )
        settings = {
            "rop": {
                "sources_path": "config/rop/sources.yml",
                "mailbox_poll": {
                    "enabled": True,
                    "source_id": "hotline",
                    "sources_all": True,
                },
            },
            "bitrix": {"enabled": False},
        }
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-canonical-fallback",
            settings,
            _null_logger(),
            project_root=tmp_path,
        )
        assert artifact["items"][0]["recipient"] == "fallback@welding.kz"
        assert artifact["items"][0]["recipient_evidence_source"] == "source_recipient"
        assert artifact["items"][0]["recipient_status"] == "resolved"

    def test_unresolved_without_evidence(self, tmp_path: Path) -> None:
        _write_run(tmp_path, "run-none", [_event()])
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-none", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient_status"] == "unresolved"
        assert item["recipient"] == ""
        assert item["responsible"]["status"] == "not_attempted"

    def test_multiple_to_recipients_is_ambiguous(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-ambig",
            [
                _event(
                    to=["a@welding.kz", "b@welding.kz"],
                )
            ],
        )
        client = _FakeBitrixClient([])
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-ambig",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["recipient_status"] == "ambiguous"
        assert item["recipient"] == ""
        assert item["recipient_candidates"] == ["a@welding.kz", "b@welding.kz"]
        assert item["responsible"]["status"] == "not_attempted"
        assert item["responsible"]["reason"] == "recipient_ambiguous"

    def test_multiple_original_recipients_is_ambiguous(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-ambig-orig",
            [
                _event(
                    original_recipient="a@welding.kz, b@welding.kz",
                )
            ],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-ambig-orig", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient_status"] == "ambiguous"
        assert item["recipient_evidence_source"] == "original_recipient"

    def test_cc_never_assigns_responsible(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-cc",
            [
                _event(
                    to=[],
                    cc=["cc@welding.kz"],
                )
            ],
        )
        client = _FakeBitrixClient([_active_user(9, "cc@welding.kz")])
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-cc",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["recipient_status"] == "unresolved"
        assert item["recipient"] == ""
        assert item["cc"] == ["cc@welding.kz"]
        assert item["responsible"]["status"] == "not_attempted"
        assert item["responsible"]["reason"] == "recipient_unresolved"

    def test_cc_recorded_as_evidence_when_to_resolves(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-cc-ev",
            [
                _event(
                    to=["a@welding.kz"],
                    cc=["cc@welding.kz"],
                )
            ],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-cc-ev", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient"] == "a@welding.kz"
        assert item["cc"] == ["cc@welding.kz"]

    def test_malformed_recipient_degrades_to_unresolved(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-malformed",
            [
                _event(
                    to=["not-an-email"],
                    original_recipient="",
                )
            ],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-malformed", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient_status"] == "unresolved"

    def test_email_normalization_lowercases(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-norm",
            [
                _event(
                    to=["  User@Welding.KZ  "],
                )
            ],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-norm", _settings(), _null_logger()
        )
        item = artifact["items"][0]
        assert item["recipient"] == "user@welding.kz"


class TestResponsibleResolution:
    def test_exact_active_user_matches(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-match",
            [_event(to=["boss@welding.kz"])],
        )
        client = _FakeBitrixClient([_active_user(12, "boss@welding.kz")])
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-match",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        responsible = item["responsible"]
        assert responsible["status"] == "matched"
        assert responsible["user_id"] == 12
        assert responsible["email"] == "boss@welding.kz"
        assert artifact["directory"]["status"] == "loaded"

    def test_inactive_user_is_not_accepted(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-inactive",
            [_event(to=["boss@welding.kz"])],
        )
        client = _FakeBitrixClient([_active_user(12, "boss@welding.kz", active="N")])
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-inactive",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "not_found"

    def test_boolean_active_user_is_accepted(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-bool-active",
            [_event(to=["boss@welding.kz"])],
        )
        client = _FakeBitrixClient(
            [dict(_active_user(12, "boss@welding.kz"), ACTIVE=True)]
        )
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-bool-active",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "matched"
        assert item["responsible"]["user_id"] == 12
        assert artifact["directory"]["status"] == "loaded"

    def test_boolean_inactive_user_is_rejected(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-bool-inactive",
            [_event(to=["boss@welding.kz"])],
        )
        client = _FakeBitrixClient(
            [dict(_active_user(12, "boss@welding.kz"), ACTIVE=False)]
        )
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-bool-inactive",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "not_found"

    def test_no_user_produces_not_found(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-notfound",
            [_event(to=["missing@welding.kz"])],
        )
        client = _FakeBitrixClient([])
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-notfound",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "not_found"

    def test_multiple_exact_active_users_ambiguous(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-dup",
            [_event(to=["boss@welding.kz"])],
        )
        client = _FakeBitrixClient(
            [
                _active_user(1, "boss@welding.kz"),
                _active_user(2, "boss@welding.kz"),
            ]
        )
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-dup",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "ambiguous"
        assert item["responsible"]["user_id"] is None

    def test_connector_failure_produces_degraded(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-degraded",
            [_event(to=["boss@welding.kz"])],
        )
        client = _RaisingBitrixClient()
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-degraded",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "connector_degraded"
        assert artifact["directory"]["status"] == "connector_degraded"
        assert artifact["status"] == "degraded"

    def test_bitrix_disabled_not_attempted(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-disabled",
            [_event(to=["boss@welding.kz"])],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-disabled",
            _settings(bitrix_enabled=False),
            _null_logger(),
        )
        item = artifact["items"][0]
        assert item["responsible"]["status"] == "not_attempted"
        assert item["responsible"]["reason"] == "bitrix_disabled"
        assert artifact["directory"]["status"] == "not_attempted"
        assert artifact["status"] == "ok"

    def test_directory_loaded_once_not_per_email(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-once",
            [
                _event("evt-1", "event-000001", to=["a@welding.kz"]),
                _event("evt-2", "event-000002", to=["b@welding.kz"]),
                _event("evt-3", "event-000003", to=["c@welding.kz"]),
            ],
        )
        client = _FakeBitrixClient(
            [
                _active_user(1, "a@welding.kz"),
                _active_user(2, "b@welding.kz"),
                _active_user(3, "c@welding.kz"),
            ]
        )
        build_recipient_routing_artifact(
            tmp_path,
            "run-once",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        assert len(client.calls) == 1
        assert client.calls[0]["select"] == [
            "ID",
            "EMAIL",
            "ACTIVE",
            "NAME",
            "LAST_NAME",
            "WORK_POSITION",
        ]

    def test_directory_pagination_is_bounded(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-pages",
            [_event(to=["boss@welding.kz"])],
        )
        users = [_active_user(i, f"u{i}@welding.kz") for i in range(1, 6)]
        client = _FakeBitrixClient(users, pages=5)
        build_recipient_routing_artifact(
            tmp_path,
            "run-pages",
            _settings(bitrix_enabled=True, page_size=2, pages_max=3),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        assert len(client.calls) == 3

    def test_incomplete_directory_degrades_all_resolutions(
        self, tmp_path: Path
    ) -> None:
        _write_run(
            tmp_path,
            "run-incomplete-directory",
            [_event(to=["boss@welding.kz"])],
        )
        client = _FakeBitrixClient(
            [
                _active_user(12, "boss@welding.kz"),
                _active_user(13, "other@welding.kz"),
            ]
        )
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-incomplete-directory",
            _settings(bitrix_enabled=True, page_size=1, pages_max=1),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        assert len(client.calls) == 1
        assert artifact["directory"]["status"] == "connector_degraded"
        assert artifact["items"][0]["responsible"]["status"] == "connector_degraded"

    @pytest.mark.parametrize(
        "user_id",
        [None, True, 0, -1, "bad-id", "0", "-1"],
    )
    def test_malformed_exact_active_user_id_degrades(
        self, tmp_path: Path, user_id: object
    ) -> None:
        _write_run(
            tmp_path,
            "run-malformed-id",
            [_event(to=["boss@welding.kz"])],
        )
        user = _active_user(12, "boss@welding.kz")
        if user_id is None:
            user.pop("ID")
        else:
            user["ID"] = user_id
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-malformed-id",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: _FakeBitrixClient([user]),
        )
        responsible = artifact["items"][0]["responsible"]
        assert responsible["status"] == "connector_degraded"
        assert responsible["status"] != "not_found"


class TestArtifactContract:
    def test_artifact_contains_event_id_and_instance_id(self, tmp_path: Path) -> None:
        _write_run(
            tmp_path,
            "run-artifact",
            [
                _event("evt-7", "event-000007", to=["boss@welding.kz"]),
            ],
        )
        client = _FakeBitrixClient([_active_user(12, "boss@welding.kz")])
        artifact = build_recipient_routing_artifact(
            tmp_path,
            "run-artifact",
            _settings(bitrix_enabled=True),
            _null_logger(),
            bitrix_client_factory=lambda _settings: client,
        )
        assert artifact["run_id"] == "run-artifact"
        assert artifact["read_only"] is True
        assert artifact["draft_only"] is True
        item = artifact["items"][0]
        assert item["event_id"] == "evt-7"
        assert item["event_instance_id"] == "event-000007"
        assert item["source_id"] == "hotline"
        assert item["source_role"] == "technical_aggregator"
        assert item["client_id"] == "welding"
        assert item["responsible"]["status"] == "matched"
        assert artifact["aggregate"]["event_count"] == 1
        assert artifact["aggregate"]["recipient_resolved_count"] == 1
        assert artifact["aggregate"]["responsible_matched_count"] == 1

    def test_artifact_does_not_include_body_or_raw_content(
        self, tmp_path: Path
    ) -> None:
        _write_run(
            tmp_path,
            "run-noraw",
            [
                {
                    **_event(to=["boss@welding.kz"]),
                    "body_preview": "secret body text",
                    "attachments": [{"filename": "x.pdf"}],
                }
            ],
        )
        artifact = build_recipient_routing_artifact(
            tmp_path, "run-noraw", _settings(), _null_logger()
        )
        assert "body_preview" not in artifact["items"][0]
        assert "attachments" not in artifact["items"][0]
        raw = json.dumps(artifact)
        assert "secret body text" not in raw

    def test_missing_normalized_events_raises(self, tmp_path: Path) -> None:
        (tmp_path / "runs" / "run-empty").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="normalized_events"):
            build_recipient_routing_artifact(
                tmp_path, "run-empty", _settings(), _null_logger()
            )

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="path traversal"):
            build_recipient_routing_artifact(
                tmp_path, "../escape", _settings(), _null_logger()
            )

    def test_malformed_events_json_raises(self, tmp_path: Path) -> None:
        run_dir = _write_run(tmp_path, "run-bad", [_event()])
        (run_dir / "normalized_events.json").write_text("{", encoding="utf-8")
        with pytest.raises(ValueError, match="malformed"):
            build_recipient_routing_artifact(
                tmp_path, "run-bad", _settings(), _null_logger()
            )
