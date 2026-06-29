from __future__ import annotations

import json
import logging
from pathlib import Path

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
