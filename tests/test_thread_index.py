from __future__ import annotations

import json
import logging
from pathlib import Path

from beeagent_module.core.rop_thread_context import build_public_thread_context
from beeagent_module.core.thread_index import (
    _has_reply_prefix,
    _normalize_subject,
    build_thread_context,
    build_thread_index,
    write_thread_artifacts,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_thread_index")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_thread_index_via_message_id() -> None:
    events = [
        {
            "event_id": "evt-001",
            "message_id": "<msg-001@host>",
            "subject": "Welding machine issue",
            "sender": "alice@example.com",
        },
        {
            "event_id": "evt-002",
            "message_id": "<msg-002@host>",
            "in_reply_to": "<msg-001@host>",
            "subject": "Re: Welding machine issue",
            "sender": "bob@example.com",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    threads = index["threads"]
    assert len(threads) == 1
    assert threads[0]["event_ids"] == ["evt-001", "evt-002"]
    assert (
        threads[0]["evidence"]["references_link"]
        or threads[0]["evidence"]["message_id_link"]
    )


def test_thread_index_via_subject_fallback() -> None:
    events = [
        {
            "event_id": "evt-001",
            "subject": "Project Alpha status",
            "sender": "alice@example.com",
        },
        {
            "event_id": "evt-002",
            "subject": "Re: Project Alpha status",
            "sender": "bob@example.com",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    threads = index["threads"]
    assert len(threads) == 1
    assert "evt-001" in threads[0]["event_ids"]
    assert "evt-002" in threads[0]["event_ids"]
    assert threads[0]["evidence"]["subject_fallback"] is True


def test_subject_fallback_does_not_merge_across_source_or_client() -> None:
    events = [
        {
            "event_id": "evt-001",
            "source_id": "source-a",
            "client_id": "client-a",
            "subject": "Project Alpha status",
            "sender": "alice@example.com",
        },
        {
            "event_id": "evt-002",
            "source_id": "source-b",
            "client_id": "client-a",
            "subject": "Re: Project Alpha status",
            "sender": "bob@example.com",
        },
        {
            "event_id": "evt-003",
            "source_id": "source-a",
            "client_id": "client-b",
            "subject": "Re: Project Alpha status",
            "sender": "carol@example.com",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    assert len(index["threads"]) == 3


def test_single_event_thread_fallback() -> None:
    events = [
        {
            "event_id": "evt-001",
            "subject": "Standalone message",
            "sender": "alice@example.com",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    threads = index["threads"]
    assert len(threads) == 1
    assert threads[0]["event_ids"] == ["evt-001"]
    assert threads[0]["evidence"]["subject_fallback"] is False


def test_mail_thread_index_shape() -> None:
    events = [
        {
            "event_id": "evt-001",
            "message_id": "<a@h>",
            "subject": "Test",
            "sender": "a@x.com",
        },
        {
            "event_id": "evt-002",
            "message_id": "<b@h>",
            "in_reply_to": "<a@h>",
            "subject": "Re: Test",
            "sender": "b@x.com",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    artifact_str = json.dumps(index)

    assert "raw_eml" not in artifact_str
    assert "attachment_content" not in artifact_str
    assert "content_bytes" not in artifact_str

    assert "threads" in index
    assert "warnings" in index
    for thread in index["threads"]:
        assert "thread_id" in thread
        assert "event_ids" in thread
        assert "message_ids" in thread
        assert "subject_normalized" in thread
        assert "participants" in thread
        assert "latest_event_id" in thread
        assert "evidence" in thread
        assert isinstance(thread["event_ids"], list)
        assert isinstance(thread["message_ids"], list)


def test_mail_thread_context_shape() -> None:
    events = [
        {
            "event_id": "evt-001",
            "message_id": "<a@h>",
            "subject": "Test",
            "sender": "a@x.com",
        },
        {
            "event_id": "evt-002",
            "message_id": "<b@h>",
            "in_reply_to": "<a@h>",
            "subject": "Re: Test",
            "sender": "b@x.com",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    context = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=None,
        logger=_null_logger(),
    )
    artifact_str = json.dumps(context)

    assert "raw_eml" not in artifact_str
    assert "attachment_content" not in artifact_str

    assert "contexts" in context
    for ctx in context["contexts"]:
        assert "event_id" in ctx
        assert "thread_id" in ctx
        assert "previous_event_ids" in ctx
        assert "thread_context_confidence" in ctx
        assert isinstance(ctx["thread_context_confidence"], float)


def test_write_thread_artifacts(tmp_path: Path) -> None:
    index = {
        "threads": [
            {
                "thread_id": "thr_001",
                "source_ids": ["test"],
                "event_ids": ["evt-001"],
                "message_ids": ["<a@h>"],
                "subject_normalized": "test",
                "participants": ["a@x.com"],
                "latest_event_id": "evt-001",
                "latest_at": "2026-06-01T10:00:00+00:00",
                "evidence": {
                    "message_id_link": False,
                    "references_link": False,
                    "subject_fallback": False,
                },
            }
        ],
        "warnings": [],
    }
    context = {
        "contexts": [
            {
                "event_id": "evt-001",
                "thread_id": "thr_001",
                "previous_event_ids": [],
                "thread_context_confidence": 0.5,
            }
        ],
        "warnings": [],
    }
    refs = write_thread_artifacts(
        storage_dir=tmp_path,
        run_id="test-thread-write",
        thread_index=index,
        thread_context=context,
        logger=_null_logger(),
    )
    assert len(refs) == 2

    index_path = tmp_path / "runs" / "test-thread-write" / "mail_thread_index.json"
    assert index_path.exists()
    index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    assert index_payload["run_id"] == "test-thread-write"
    context_path = tmp_path / "runs" / "test-thread-write" / "mail_thread_context.json"
    assert context_path.exists()
    context_payload = json.loads(context_path.read_text(encoding="utf-8"))
    assert context_payload["run_id"] == "test-thread-write"


def test_thread_context_malformed_degraded_path() -> None:
    events = [
        {"event_id": "evt-001", "subject": "Test", "sender": "a@x.com"},
    ]
    index = build_thread_index(events, logger=_null_logger())

    context = build_thread_context(
        events=events,
        thread_index={"threads": None},
        classified_events=None,
        logger=_null_logger(),
    )
    assert context["contexts"] == []

    context2 = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=[],
        logger=_null_logger(),
    )
    assert isinstance(context2["contexts"], list)


def test_thread_context_does_not_self_reference_repeated_message_id() -> None:
    events = [
        {
            "event_id": "<same@example.test>",
            "message_id": "<same@example.test>",
            "subject": "RE: 955551 / 0346 Invoice",
            "sender": "prior@example.test",
            "in_reply_to": "<prior@example.test>",
        },
        {
            "event_id": "<same@example.test>",
            "message_id": "<same@example.test>",
            "subject": "RE: 955551 / 0346 Invoice",
            "sender": "prior@example.test",
            "in_reply_to": "<prior@example.test>",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    context = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=[
            {
                "event_id": "<same@example.test>",
                "case_type": "existing_deal",
                "reasoning": "Bounded prior summary",
            },
            {
                "event_id": "<same@example.test>",
                "case_type": "duplicate",
                "reasoning": "exact duplicate matched by message_id",
            },
        ],
        logger=_null_logger(),
    )

    for entry in context["contexts"]:
        assert entry["event_id"] not in entry["previous_event_ids"]


def test_thread_context_uses_only_prior_classified_events_and_public_adapter() -> None:
    from beeagent_rop.domain.thread_context import validate_thread_context

    events = [
        {
            "event_id": "evt-early",
            "message_id": "<early@example.test>",
            "subject": "Delivery update",
            "sender": "buyer@example.test",
        },
        {
            "event_id": "evt-late",
            "message_id": "<late@example.test>",
            "in_reply_to": "<early@example.test>",
            "subject": "Re: Delivery update",
            "sender": "buyer@example.test",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    context = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=[
            {
                "event_id": "evt-early",
                "case_type": "existing_deal",
                "subject": "Delivery update",
                "reasoning": "Bounded prior summary",
            },
            {
                "event_id": "evt-late",
                "case_type": "new_lead",
            },
        ],
        logger=_null_logger(),
    )

    assert [item["event_id"] for item in context["contexts"]] == ["evt-late"]
    runtime_context = context["contexts"][0]
    assert runtime_context["previous_event_ids"] == ["evt-early"]
    assert runtime_context["previous_case_type"] == "existing_deal"
    payload = build_public_thread_context(runtime_context, events[1])
    validated, errors = validate_thread_context(payload)
    assert errors == []
    assert validated is not None
    assert set(payload) == {
        "thread_id",
        "previous_event_id",
        "reply_markers",
        "forward_markers",
        "previous_case_type",
        "participant_hints",
        "previous_subject",
        "previous_summary",
        "crm_deal_hint_summary",
        "thread_confidence",
        "reason_codes",
    }


def test_thread_context_does_not_use_current_participant_as_prior_overlap() -> None:
    events = [
        {
            "event_id": "evt-prior",
            "message_id": "<prior@example.test>",
            "subject": "Delivery update",
            "sender": "prior@example.test",
        },
        {
            "event_id": "evt-current",
            "message_id": "<current@example.test>",
            "in_reply_to": "<prior@example.test>",
            "subject": "Re: Delivery update",
            "sender": "current@example.test",
        },
    ]
    index = build_thread_index(events, logger=_null_logger())
    context = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=None,
        logger=_null_logger(),
    )

    assert context["contexts"][0]["participant_overlap"] is False


def test_thread_context_ignores_future_thread_evidence() -> None:
    initial_events = [
        {
            "event_id": "evt-prior",
            "message_id": "<prior@example.test>",
            "subject": "Delivery update",
            "sender": "prior@example.test",
        },
        {
            "event_id": "evt-current",
            "message_id": "<current@example.test>",
            "subject": "Re: Delivery update",
            "sender": "current@example.test",
        },
    ]
    future_event = {
        "event_id": "evt-future",
        "message_id": "<future@example.test>",
        "references": "<prior@example.test> <current@example.test>",
        "subject": "Re: Delivery update",
        "sender": "future@example.test",
    }

    initial_context = build_thread_context(
        events=initial_events,
        thread_index=build_thread_index(initial_events, logger=_null_logger()),
        classified_events=None,
        logger=_null_logger(),
    )
    full_events = [*initial_events, future_event]
    full_context = build_thread_context(
        events=full_events,
        thread_index=build_thread_index(full_events, logger=_null_logger()),
        classified_events=None,
        logger=_null_logger(),
    )

    initial_current = initial_context["contexts"][0]
    full_current = next(
        item for item in full_context["contexts"] if item["event_id"] == "evt-current"
    )
    assert full_current["reason_codes"] == initial_current["reason_codes"]
    assert (
        full_current["thread_context_confidence"]
        == initial_current["thread_context_confidence"]
    )


def test_public_thread_context_preserves_auto_forward_marker() -> None:
    payload = build_public_thread_context(
        {
            "thread_id": "thr-001",
            "previous_event_ids": ["evt-previous"],
            "thread_context_confidence": 0.5,
        },
        {
            "transport_labels": ["auto_fwd"],
            "forwarded_wrapper": False,
        },
    )

    assert payload["forward_markers"] is True
    assert "forward_only" in payload["reason_codes"]


def test_normalize_subject() -> None:
    assert _normalize_subject("Re: Hello") == "hello"
    assert _normalize_subject("FW: Hello") == "hello"
    assert _normalize_subject("Fwd: Hello") == "hello"
    assert _normalize_subject("Hello") == "hello"
    assert _normalize_subject("") == ""


def test_has_reply_prefix() -> None:
    assert _has_reply_prefix("Re: Hello") is True
    assert _has_reply_prefix("FW: Hello") is True
    assert _has_reply_prefix("Hello") is False
    assert _has_reply_prefix("") is False


def test_thread_context_cross_run_prior_message_reference() -> None:
    prior_events = [
        {
            "event_id": "<root@yandex.test>",
            "message_id": "<root@yandex.test>",
            "subject": "Запрос КП",
            "sender": "buyer@yandex.test",
        }
    ]
    prior_classified = [
        {
            "event_id": "<root@yandex.test>",
            "case_type": "new_lead",
        }
    ]
    events = [
        {
            "event_id": "<reply@yandex.test>",
            "message_id": "<reply@yandex.test>",
            "in_reply_to": "<root@yandex.test>",
            "references": "<root@yandex.test>",
            "subject": "Re: Запрос КП",
            "sender": "buyer@yandex.test",
        }
    ]
    index = build_thread_index(events, logger=_null_logger())
    context = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=[],
        logger=_null_logger(),
        prior_events=prior_events,
        prior_classified=prior_classified,
    )

    assert len(context["contexts"]) == 1
    entry = context["contexts"][0]
    assert entry["previous_case_type"] == "new_lead"
    assert "prior_run_reference" in entry["reason_codes"]


def test_thread_context_crm_activity_reference_is_existing_deal() -> None:
    events = [
        {
            "event_id": "<reply@yandex.test>",
            "message_id": "<reply@yandex.test>",
            "in_reply_to": "<crm.activity.1617969-ZP2J9I@my.welding.kz>",
            "references": "<crm.activity.1617969-ZP2J9I@my.welding.kz>",
            "subject": "Re: Запрос КП",
            "sender": "buyer@yandex.test",
        }
    ]
    index = build_thread_index(events, logger=_null_logger())
    context = build_thread_context(
        events=events,
        thread_index=index,
        classified_events=None,
        logger=_null_logger(),
    )

    assert len(context["contexts"]) == 1
    entry = context["contexts"][0]
    assert entry["previous_case_type"] == "existing_deal"
    assert "references_bitrix_activity" in entry["reason_codes"]
