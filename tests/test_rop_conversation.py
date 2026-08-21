from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.rop_conversation import (
    build_conversation_relation,
    build_conversation_timeline,
    write_conversation_artifacts,
)
from beeagent_module.core.rop_outbound_correlation import (
    _activity_message_id,
    _activity_target,
    _is_outbound_activity,
    collect_outbound_correlation_evidence,
    resolve_outbound_bridge,
    write_outbound_correlation_artifact,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_conversation")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _event(
    event_id: str,
    *,
    client_id: str = "welding",
    source_id: str = "mailbox-a",
    message_id: str = "",
    in_reply_to: str = "",
    references: str = "",
    sender: str = "client@example.com",
    subject: str = "Subject",
    received_at: str = "2026-08-01T10:00:00Z",
) -> dict:
    return {
        "event_id": event_id,
        "event_instance_id": f"event-{event_id}",
        "client_id": client_id,
        "source_id": source_id,
        "sender": sender,
        "subject": subject,
        "received_at": received_at,
        "message_id": message_id,
        "in_reply_to": in_reply_to,
        "references": references,
    }


class TestBuildConversationRelation:
    def test_three_hop_chain_is_one_conversation(self) -> None:
        events = [
            _event("a", message_id="<a@test>", subject="Need quote"),
            _event(
                "b",
                message_id="<b@test>",
                in_reply_to="<a@test>",
                subject="Re: Need quote",
            ),
            _event(
                "c",
                message_id="<c@test>",
                references="<a@test> <b@test>",
                subject="Re: Need quote",
            ),
        ]
        thread_index = {
            "threads": [
                {
                    "thread_id": "thr_001",
                    "event_ids": ["a", "b", "c"],
                    "source_ids": ["mailbox-a"],
                    "message_ids": ["<a@test>", "<b@test>", "<c@test>"],
                }
            ]
        }
        relation = build_conversation_relation(events, thread_index, None)
        conversations = relation["conversations"]
        assert len(conversations) == 1
        conv = conversations[0]
        assert conv["conversation_id"] == "conv_001"
        roles = {item["event_id"]: item["role"] for item in conv["events"]}
        assert roles == {"a": "root", "b": "reply", "c": "reply"}

    def test_two_independent_threads_same_sender_stay_separate(self) -> None:
        events = [
            _event(
                "a",
                message_id="<a@test>",
                sender="same@example.com",
                subject="Thread one",
            ),
            _event(
                "b",
                message_id="<b@test>",
                in_reply_to="<a@test>",
                sender="same@example.com",
                subject="Re: Thread one",
            ),
            _event(
                "c",
                message_id="<c@test>",
                sender="same@example.com",
                subject="Thread two",
            ),
        ]
        thread_index = {
            "threads": [
                {
                    "thread_id": "thr_001",
                    "event_ids": ["a", "b"],
                    "source_ids": ["mailbox-a"],
                    "message_ids": ["<a@test>", "<b@test>"],
                },
                {
                    "thread_id": "thr_002",
                    "event_ids": ["c"],
                    "source_ids": ["mailbox-a"],
                    "message_ids": ["<c@test>"],
                },
            ]
        }
        relation = build_conversation_relation(events, thread_index, None)
        assert len(relation["conversations"]) == 2
        conv_ids = [conv["conversation_id"] for conv in relation["conversations"]]
        assert conv_ids == ["conv_001", "conv_002"]


class TestConversationTimeline:
    def test_cross_source_exact_reply_same_client_bridged(self, tmp_path: Path) -> None:
        state = {
            "events": {
                "welding|mailbox-a|<a@test>|": {
                    "event_id": "a",
                    "event_instance_id": "event-a",
                    "client_id": "welding",
                    "source_id": "mailbox-a",
                    "message_id": "<a@test>",
                    "in_reply_to": "",
                    "references": "",
                    "sender_email": "client@example.com",
                    "subject": "Need quote",
                    "case_type": "new_lead",
                    "outcome": "create_lead",
                    "status": "created",
                    "target_entity_type": "lead",
                    "target_entity_id": 1001,
                    "target_provenance": "beeagent_created",
                    "last_run_id": "run-1",
                    "created_at_utc": "2026-08-01T10:00:00Z",
                },
                "welding|mailbox-b|<b@test>|": {
                    "event_id": "b",
                    "event_instance_id": "event-b",
                    "client_id": "welding",
                    "source_id": "mailbox-b",
                    "message_id": "<b@test>",
                    "in_reply_to": "<a@test>",
                    "references": "<a@test>",
                    "sender_email": "client@example.com",
                    "subject": "Re: Need quote",
                    "case_type": "existing_deal",
                    "outcome": "attach_existing",
                    "target_entity_id": 1001,
                    "target_provenance": "thread_resolved",
                    "last_run_id": "run-2",
                    "created_at_utc": "2026-08-02T10:00:00Z",
                },
            }
        }
        (tmp_path / "interfaces").mkdir(parents=True, exist_ok=True)
        (tmp_path / "interfaces" / "rop_writeback_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

        timeline = build_conversation_timeline(tmp_path, "run-2", "b", "event-b")
        assert timeline["available"] is True
        assert timeline["client_id"] == "welding"
        assert timeline["message_count"] == 2
        events = {item["event_id"]: item for item in timeline["events"]}
        assert events["a"]["source_id"] == "mailbox-a"
        assert events["b"]["source_id"] == "mailbox-b"
        assert events["b"]["role"] == "reply"

    def test_independent_conversation_not_included(self, tmp_path: Path) -> None:
        state = {
            "events": {
                "welding|mailbox-a|<a@test>|": {
                    "event_id": "a",
                    "client_id": "welding",
                    "source_id": "mailbox-a",
                    "message_id": "<a@test>",
                    "in_reply_to": "",
                    "references": "",
                    "last_run_id": "run-1",
                    "created_at_utc": "2026-08-01T10:00:00Z",
                },
                "welding|mailbox-a|<x@test>|": {
                    "event_id": "x",
                    "client_id": "welding",
                    "source_id": "mailbox-a",
                    "message_id": "<x@test>",
                    "in_reply_to": "",
                    "references": "",
                    "last_run_id": "run-1",
                    "created_at_utc": "2026-08-01T11:00:00Z",
                },
            }
        }
        (tmp_path / "interfaces").mkdir(parents=True, exist_ok=True)
        (tmp_path / "interfaces" / "rop_writeback_state.json").write_text(
            json.dumps(state), encoding="utf-8"
        )

        timeline = build_conversation_timeline(tmp_path, "run-1", "a")
        assert timeline["message_count"] == 1
        assert timeline["events"][0]["event_id"] == "a"

    def test_no_records_returns_unavailable(self, tmp_path: Path) -> None:
        timeline = build_conversation_timeline(tmp_path, "run-1", "a")
        assert timeline["available"] is False


class TestConversationArtifacts:
    def test_write_conversation_artifacts(self, tmp_path: Path) -> None:
        refs = write_conversation_artifacts(
            storage_dir=tmp_path,
            run_id="run-conv",
            relation={"conversations": [{"conversation_id": "conv_001"}]},
            logger=_null_logger(),
        )
        path = tmp_path / "runs" / "run-conv" / "rop_conversation.json"
        assert path.exists()
        assert refs == ["runs/run-conv/rop_conversation.json"]
        artifact = json.loads(path.read_text(encoding="utf-8"))
        assert artifact["conversations"][0]["conversation_id"] == "conv_001"


class _FakeBitrixClient:
    def __init__(
        self,
        result: list[dict] | None = None,
        error: Exception | None = None,
        responses: list[dict] | None = None,
    ):
        self._result = result or []
        self._error = error
        self._responses = responses
        self.calls: list[dict] = []

    def activity_list(
        self, filter_params: dict, select: list[str], start: int = 0
    ) -> dict:
        self.calls.append(
            {"filter_params": filter_params, "select": select, "start": start}
        )
        if self._error is not None:
            raise self._error
        if self._responses is not None:
            if start < len(self._responses):
                return self._responses[start]
            return {"result": []}
        return {"result": self._result}


class TestOutboundCorrelationCollect:
    def test_exact_outbound_message_id_bridge(self) -> None:
        client = _FakeBitrixClient(
            result=[
                {
                    "ID": 11,
                    "OWNER_TYPE_ID": 1,
                    "OWNER_ID": 1001,
                    "RESPONSIBLE_ID": 42,
                    "DIRECTION": 2,
                    "SUBJECT": "Re: Need quote",
                    "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                }
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-1@employee.test>",
                "references": "<out-1@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert len(evidence) == 1
        assert evidence[0]["event_id"] == "evt-b"
        assert evidence[0]["bridge_exact"] is True
        assert evidence[0]["target_entity_id"] == 1001
        assert evidence[0]["target_responsible_user_id"] == 42
        assert client.calls[0]["filter_params"]["TYPE_ID"] == 4

    def test_exact_bridge_via_message_headers_location(self) -> None:
        client = _FakeBitrixClient(
            result=[
                {
                    "ID": 1617905,
                    "OWNER_TYPE_ID": 1,
                    "OWNER_ID": 199425,
                    "RESPONSIBLE_ID": 1610,
                    "DIRECTION": 2,
                    "SETTINGS": {
                        "MESSAGE_HEADERS": {
                            "Message-Id": (
                                "<crm.activity.1617905-0R9TBN@my.welding.kz>"
                            )
                        }
                    },
                }
            ]
        )
        events = [
            {
                "event_id": "evt-reply",
                "event_instance_id": "event-reply",
                "references": "<crm.activity.1617905-0R9TBN@my.welding.kz>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert len(evidence) == 1
        assert evidence[0]["bridge_exact"] is True
        assert evidence[0]["outbound_message_id"] == (
            "crm.activity.1617905-0R9TBN@my.welding.kz"
        )
        assert evidence[0]["target_entity_id"] == 199425
        assert evidence[0]["outbound_activity_responsible_user_id"] == 1610

    def test_no_reply_headers_skips_check(self) -> None:
        client = _FakeBitrixClient()
        events = [{"event_id": "evt-a", "message_id": "<a@test>"}]
        assert (
            collect_outbound_correlation_evidence(client, events, _null_logger()) == []
        )
        assert client.calls == []

    def test_connector_error_degrades_to_empty(self) -> None:
        from beeagent_module.adapters.bitrix_client import BitrixConnectorError

        client = _FakeBitrixClient(error=BitrixConnectorError("boom"))
        events = [{"event_id": "evt-b", "in_reply_to": "<x@test>"}]
        assert (
            collect_outbound_correlation_evidence(client, events, _null_logger()) == []
        )

    def test_multiple_exact_matches_not_bridged(self) -> None:
        client = _FakeBitrixClient(
            result=[
                {
                    "ID": 11,
                    "OWNER_TYPE_ID": 1,
                    "OWNER_ID": 1001,
                    "RESPONSIBLE_ID": 42,
                    "DIRECTION": 2,
                    "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                },
                {
                    "ID": 12,
                    "OWNER_TYPE_ID": 2,
                    "OWNER_ID": 2001,
                    "RESPONSIBLE_ID": 43,
                    "DIRECTION": 2,
                    "SETTINGS": {"MESSAGE_ID": "<out-2@employee.test>"},
                },
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "in_reply_to": "<out-1@employee.test> <out-2@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert evidence == []


class TestActivityMessageId:
    def test_message_headers_message_id_camel(self) -> None:
        activity = {
            "SETTINGS": {
                "MESSAGE_HEADERS": {"Message-Id": "<crm.activity.1-ABC@welding.kz>"}
            }
        }
        assert _activity_message_id(activity) == "crm.activity.1-ABC@welding.kz"

    def test_message_headers_message_id_upper(self) -> None:
        activity = {
            "SETTINGS": {
                "MESSAGE_HEADERS": {"Message-ID": "<crm.activity.2-DEF@welding.kz>"}
            }
        }
        assert _activity_message_id(activity) == "crm.activity.2-DEF@welding.kz"

    def test_message_headers_message_id_lower(self) -> None:
        activity = {
            "SETTINGS": {
                "MESSAGE_HEADERS": {"message-id": "<crm.activity.3-GHI@welding.kz>"}
            }
        }
        assert _activity_message_id(activity) == "crm.activity.3-GHI@welding.kz"

    def test_message_headers_message_id_arbitrary_case(self) -> None:
        activity = {
            "SETTINGS": {
                "MESSAGE_HEADERS": {"mEsSaGe-iD": "<crm.activity.4-JKL@welding.kz>"}
            }
        }
        assert _activity_message_id(activity) == "crm.activity.4-JKL@welding.kz"

    def test_legacy_settings_message_id_still_supported(self) -> None:
        activity = {"SETTINGS": {"MESSAGE_ID": "<out-legacy-1@welding.kz>"}}
        assert _activity_message_id(activity) == "out-legacy-1@welding.kz"

    def test_legacy_settings_email_message_id_still_supported(self) -> None:
        activity = {"SETTINGS": {"EMAIL_MESSAGE_ID": "<out-legacy-2@welding.kz>"}}
        assert _activity_message_id(activity) == "out-legacy-2@welding.kz"

    def test_top_level_message_id_still_supported(self) -> None:
        activity = {"MESSAGE_ID": "<out-top-3@welding.kz>"}
        assert _activity_message_id(activity) == "out-top-3@welding.kz"

    def test_message_headers_malformed_no_crash(self) -> None:
        activity = {"SETTINGS": {"MESSAGE_HEADERS": ["not-a-mapping"]}}
        assert _activity_message_id(activity) == ""

    def test_message_headers_value_not_string_ignored(self) -> None:
        activity = {"SETTINGS": {"MESSAGE_HEADERS": {"Message-Id": 12345}}}
        assert _activity_message_id(activity) == ""

    def test_missing_message_id_returns_empty(self) -> None:
        assert _activity_message_id({"SETTINGS": {"OTHER": "x"}}) == ""
        assert _activity_message_id({}) == ""


class TestResolveOutboundBridge:
    def _event(self, refs: str = "<out-1@employee.test>") -> dict[str, Any]:
        return {
            "event_id": "evt-b",
            "event_instance_id": "event-b",
            "in_reply_to": refs,
            "references": refs,
        }

    def _evidence(
        self,
        *,
        target_entity_type: str = "lead",
        target_entity_type_id: int = 1,
        target_entity_id: int = 1001,
        target_responsible_user_id: int | None = 42,
        bridge_exact: bool = True,
        outbound_message_id: str = "out-1@employee.test",
    ) -> list[dict[str, Any]]:
        return [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "bridge_exact": bridge_exact,
                "outbound_message_id": outbound_message_id,
                "target_entity_type": target_entity_type,
                "target_entity_type_id": target_entity_type_id,
                "target_entity_id": target_entity_id,
                "target_responsible_user_id": target_responsible_user_id,
                "outbound_activity_responsible_user_id": target_responsible_user_id,
            }
        ]

    def test_exact_bridge_matching_trusted_target_is_authorized(self) -> None:
        trusted = {("lead", 1, 1001, 42)}
        bridge = resolve_outbound_bridge(self._event(), self._evidence(), trusted)
        assert bridge is not None
        assert bridge["authorized"] is True
        assert bridge["target"]["target_entity_id"] == 1001
        assert bridge["target"]["target_responsible_user_id"] == 42
        assert bridge["target"]["target_provenance"] == "bitrix_outbound_exact"

    def test_exact_bridge_without_trusted_target_is_candidate_only(self) -> None:
        bridge = resolve_outbound_bridge(self._event(), self._evidence(), set())
        assert bridge is not None
        assert bridge["authorized"] is False
        assert bridge["reason_code"] == "outbound_candidate_untrusted"

    def test_exact_bridge_conflicts_with_trusted_target_is_candidate_only(self) -> None:
        trusted = {("lead", 1, 2002, 42)}
        bridge = resolve_outbound_bridge(self._event(), self._evidence(), trusted)
        assert bridge is not None
        assert bridge["authorized"] is False
        assert bridge["reason_code"] == "outbound_candidate_untrusted"

    def test_responsible_mismatch_does_not_block_authorized_bridge(self) -> None:
        trusted = {("lead", 1, 1001, 42)}
        bridge = resolve_outbound_bridge(
            self._event(), self._evidence(target_responsible_user_id=77), trusted
        )
        assert bridge is not None
        assert bridge["authorized"] is True
        assert bridge["target"]["target_entity_id"] == 1001
        assert bridge["target"]["target_responsible_user_id"] == 42
        assert bridge["target"]["target_provenance"] == "bitrix_outbound_exact"
        assert bridge["target"]["outbound_activity_responsible_user_id"] == 77
        assert bridge["target"]["responsible_mismatch"] is True

    def test_activity_responsible_never_replaces_canonical(self) -> None:
        trusted = {("lead", 1, 1001, 1563)}
        bridge = resolve_outbound_bridge(
            self._event(), self._evidence(target_responsible_user_id=1610), trusted
        )
        assert bridge is not None
        assert bridge["authorized"] is True
        assert bridge["target"]["target_responsible_user_id"] == 1563
        assert bridge["target"]["trusted_target_responsible_user_id"] == 1563
        assert bridge["target"]["outbound_activity_responsible_user_id"] == 1610

    def test_activity_without_responsible_still_authorized(self) -> None:
        trusted = {("lead", 1, 1001, 42)}
        bridge = resolve_outbound_bridge(
            self._event(), self._evidence(target_responsible_user_id=None), trusted
        )
        assert bridge is not None
        assert bridge["authorized"] is True
        assert bridge["target"]["target_responsible_user_id"] == 42

    def test_trusted_responsible_ambiguous_fails_closed(self) -> None:
        trusted = {("lead", 1, 1001, 42), ("lead", 1, 1001, 77)}
        bridge = resolve_outbound_bridge(self._event(), self._evidence(), trusted)
        assert bridge is not None
        assert bridge["authorized"] is False
        assert bridge["reason_code"] == "outbound_candidate_untrusted"

    def test_owner_mismatch_not_authorized(self) -> None:
        trusted = {("lead", 1, 2002, 42)}
        bridge = resolve_outbound_bridge(self._event(), self._evidence(), trusted)
        assert bridge is not None
        assert bridge["authorized"] is False
        assert bridge["reason_code"] == "outbound_candidate_untrusted"

    def test_stale_bridge_without_current_rfc_ancestry_is_no_bridge(self) -> None:
        trusted = {("lead", 1, 1001, 42)}
        event = self._event(refs="<other-9@employee.test>")
        bridge = resolve_outbound_bridge(event, self._evidence(), trusted)
        assert bridge is None

    def test_no_exact_evidence_returns_none(self) -> None:
        event = self._event()
        assert resolve_outbound_bridge(event, []) is None
        assert resolve_outbound_bridge(event, None) is None

    def test_candidate_only_never_authorizes(self) -> None:
        event = self._event()
        evidence = self._evidence(bridge_exact=False)
        assert resolve_outbound_bridge(event, evidence) is None

    def test_missing_entity_id_fail_closed(self) -> None:
        event = self._event()
        evidence = self._evidence(target_entity_id=None)  # type: ignore[arg-type]
        assert resolve_outbound_bridge(event, evidence) is None

    def test_other_event_evidence_ignored(self) -> None:
        event = self._event()
        evidence = self._evidence()
        evidence[0]["event_id"] = "evt-other"
        assert resolve_outbound_bridge(event, evidence) is None


class TestOutboundActivityDirection:
    def test_direction_two_accepted(self) -> None:
        assert _is_outbound_activity({"DIRECTION": 2}) is True
        assert _is_outbound_activity({"DIRECTION": "2"}) is True

    def test_direction_one_rejected(self) -> None:
        assert _is_outbound_activity({"DIRECTION": 1}) is False
        assert _is_outbound_activity({"DIRECTION": "1"}) is False

    def test_missing_direction_rejected(self) -> None:
        assert _is_outbound_activity({}) is False

    def test_malformed_direction_rejected(self) -> None:
        assert _is_outbound_activity({"DIRECTION": "two"}) is False
        assert _is_outbound_activity({"DIRECTION": -2}) is False
        assert _is_outbound_activity({"DIRECTION": True}) is False

    def test_numeric_string_target_ids_accepted(self) -> None:
        assert _activity_target(
            {
                "OWNER_TYPE_ID": "1",
                "OWNER_ID": "1001",
                "RESPONSIBLE_ID": "42",
                "DIRECTION": "2",
            }
        ) == ("lead", 1, 1001, 42)
        assert _activity_target(
            {
                "OWNER_TYPE_ID": 2,
                "OWNER_ID": "2001",
                "RESPONSIBLE_ID": 7,
                "DIRECTION": "2",
            }
        ) == ("deal", 2, 2001, 7)

    def test_message_id_presence_is_not_outbound_proof(self) -> None:
        assert (
            _is_outbound_activity(
                {"DIRECTION": 1, "SETTINGS": {"MESSAGE_ID": "<out@x.test>"}}
            )
            is False
        )
        assert (
            _is_outbound_activity({"SETTINGS": {"MESSAGE_ID": "<out@x.test>"}}) is False
        )

    def test_owner_type_must_be_lead_or_deal(self) -> None:
        assert (
            _activity_target(
                {
                    "OWNER_TYPE_ID": 3,
                    "OWNER_ID": 1001,
                    "RESPONSIBLE_ID": 42,
                    "DIRECTION": 2,
                }
            )
            is None
        )

    def test_same_message_id_conflicting_targets_no_bridge(self) -> None:
        client = _FakeBitrixClient(
            result=[
                {
                    "ID": 11,
                    "OWNER_TYPE_ID": 1,
                    "OWNER_ID": 1001,
                    "RESPONSIBLE_ID": 42,
                    "DIRECTION": 2,
                    "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                },
                {
                    "ID": 12,
                    "OWNER_TYPE_ID": 2,
                    "OWNER_ID": 2001,
                    "RESPONSIBLE_ID": 43,
                    "DIRECTION": 2,
                    "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                },
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-1@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert evidence == []

    def test_same_message_id_same_target_is_bridged(self) -> None:
        client = _FakeBitrixClient(
            result=[
                {
                    "ID": 11,
                    "OWNER_TYPE_ID": 1,
                    "OWNER_ID": 1001,
                    "RESPONSIBLE_ID": 42,
                    "DIRECTION": 2,
                    "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                },
                {
                    "ID": 12,
                    "OWNER_TYPE_ID": 1,
                    "OWNER_ID": 1001,
                    "RESPONSIBLE_ID": 42,
                    "DIRECTION": 2,
                    "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                },
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-1@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert len(evidence) == 1
        assert evidence[0]["bridge_exact"] is True
        assert evidence[0]["target_entity_id"] == 1001
        assert evidence[0]["target_responsible_user_id"] == 42

    def test_malformed_result_fails_closed(self) -> None:
        client = _FakeBitrixClient(responses=[{"result": "malformed"}])
        events = [{"event_id": "evt-b", "in_reply_to": "<out-1@employee.test>"}]
        assert (
            collect_outbound_correlation_evidence(client, events, _null_logger()) == []
        )

    def test_exact_message_id_on_later_page_discovered(self) -> None:
        client = _FakeBitrixClient(
            responses=[
                {
                    "result": [
                        {
                            "ID": 11,
                            "OWNER_TYPE_ID": 1,
                            "OWNER_ID": 1001,
                            "RESPONSIBLE_ID": 42,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                        }
                    ],
                    "next": 1,
                },
                {
                    "result": [
                        {
                            "ID": 12,
                            "OWNER_TYPE_ID": 2,
                            "OWNER_ID": 2001,
                            "RESPONSIBLE_ID": 43,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-2@employee.test>"},
                        }
                    ]
                },
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-2@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert len(evidence) == 1
        assert evidence[0]["bridge_exact"] is True
        assert evidence[0]["target_entity_id"] == 2001
        assert evidence[0]["target_responsible_user_id"] == 43
        assert [call["start"] for call in client.calls] == [0, 1]

    def test_same_message_id_cross_page_targets_ambiguous(self) -> None:
        client = _FakeBitrixClient(
            responses=[
                {
                    "result": [
                        {
                            "ID": 11,
                            "OWNER_TYPE_ID": 1,
                            "OWNER_ID": 1001,
                            "RESPONSIBLE_ID": 42,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                        }
                    ],
                    "next": 1,
                },
                {
                    "result": [
                        {
                            "ID": 12,
                            "OWNER_TYPE_ID": 2,
                            "OWNER_ID": 2001,
                            "RESPONSIBLE_ID": 43,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                        }
                    ]
                },
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-1@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(client, events, _null_logger())
        assert evidence == []

    def test_malformed_next_cursor_fails_closed(self) -> None:
        client = _FakeBitrixClient(
            responses=[
                {
                    "result": [
                        {
                            "ID": 11,
                            "OWNER_TYPE_ID": 1,
                            "OWNER_ID": 1001,
                            "RESPONSIBLE_ID": 42,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                        }
                    ],
                    "next": "abc",
                }
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-1@employee.test>",
            }
        ]
        assert (
            collect_outbound_correlation_evidence(client, events, _null_logger()) == []
        )

    def test_pages_max_respected(self) -> None:
        client = _FakeBitrixClient(
            responses=[
                {
                    "result": [
                        {
                            "ID": 11,
                            "OWNER_TYPE_ID": 1,
                            "OWNER_ID": 1001,
                            "RESPONSIBLE_ID": 42,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-1@employee.test>"},
                        }
                    ],
                    "next": 1,
                },
                {
                    "result": [
                        {
                            "ID": 12,
                            "OWNER_TYPE_ID": 2,
                            "OWNER_ID": 2001,
                            "RESPONSIBLE_ID": 43,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-2@employee.test>"},
                        }
                    ],
                    "next": 2,
                },
                {
                    "result": [
                        {
                            "ID": 13,
                            "OWNER_TYPE_ID": 2,
                            "OWNER_ID": 3001,
                            "RESPONSIBLE_ID": 44,
                            "DIRECTION": 2,
                            "SETTINGS": {"MESSAGE_ID": "<out-3@employee.test>"},
                        }
                    ]
                },
            ]
        )
        events = [
            {
                "event_id": "evt-b",
                "event_instance_id": "event-b",
                "in_reply_to": "<out-2@employee.test>",
            }
        ]
        evidence = collect_outbound_correlation_evidence(
            client, events, _null_logger(), pages_max=2
        )
        assert [call["start"] for call in client.calls] == [0, 1]
        assert len(evidence) == 1
        assert evidence[0]["outbound_message_id"] == "out-2@employee.test"


class TestOutboundCorrelationArtifact:
    def test_write_artifact(self, tmp_path: Path) -> None:
        refs = write_outbound_correlation_artifact(
            storage_dir=tmp_path,
            run_id="run-oc",
            items=[{"event_id": "evt-b", "bridge_exact": True}],
            logger=_null_logger(),
        )
        path = tmp_path / "runs" / "run-oc" / "bitrix_outbound_correlation.json"
        assert path.exists()
        assert refs == ["runs/run-oc/bitrix_outbound_correlation.json"]
        artifact = json.loads(path.read_text(encoding="utf-8"))
        assert artifact["read_only"] is True
        assert artifact["evidence"][0]["bridge_exact"] is True
