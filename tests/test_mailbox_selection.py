from __future__ import annotations

import json
import logging
from pathlib import Path

from beeagent_module.core.mailbox_selection import (
    build_mailbox_selection_artifact,
    sort_messages_by_date,
    write_mailbox_selection_artifact,
)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_mailbox_selection")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_latest_n_selects_newest_messages() -> None:
    messages = [
        {"source_message_id": "1", "internal_date": "2026-06-01T10:00:00+00:00"},
        {"source_message_id": "2", "internal_date": "2026-06-03T10:00:00+00:00"},
        {"source_message_id": "3", "internal_date": "2026-06-02T10:00:00+00:00"},
    ]
    sorted_msgs = sort_messages_by_date(messages)
    assert len(sorted_msgs) == 3
    assert sorted_msgs[0]["source_message_id"] == "2"
    assert sorted_msgs[1]["source_message_id"] == "3"
    assert sorted_msgs[2]["source_message_id"] == "1"


def test_latest_n_per_source() -> None:
    sources = [
        {
            "source_id": "mailbox_a",
            "items_max": 2,
            "total_available": 5,
            "messages": [
                {
                    "source_message_id": "1",
                    "internal_date": "2026-06-01T10:00:00+00:00",
                },
                {
                    "source_message_id": "2",
                    "internal_date": "2026-06-03T10:00:00+00:00",
                },
                {
                    "source_message_id": "3",
                    "internal_date": "2026-06-02T10:00:00+00:00",
                },
            ],
        },
        {
            "source_id": "mailbox_b",
            "items_max": 1,
            "total_available": 3,
            "messages": [
                {
                    "source_message_id": "4",
                    "internal_date": "2026-06-02T10:00:00+00:00",
                },
                {
                    "source_message_id": "5",
                    "internal_date": "2026-06-03T10:00:00+00:00",
                },
            ],
        },
    ]
    artifact = build_mailbox_selection_artifact(
        run_id="test-run",
        sources=sources,
        logger=_null_logger(),
    )
    assert artifact["run_id"] == "test-run"
    assert artifact["strategy"] == "latest_n_by_internaldate_desc"
    assert len(artifact["sources"]) == 2

    src_a = artifact["sources"][0]
    assert src_a["source_id"] == "mailbox_a"
    assert src_a["selected_count"] == 3

    src_b = artifact["sources"][1]
    assert src_b["source_id"] == "mailbox_b"
    assert src_b["selected_count"] == 2


def test_missing_date_fallback_warning() -> None:
    messages = [
        {"source_message_id": "1", "internal_date": "2026-06-01T10:00:00+00:00"},
        {"source_message_id": "2", "_date_fallback": True},
        {"source_message_id": "3", "internal_date": "2026-06-02T10:00:00+00:00"},
    ]
    sources = [
        {
            "source_id": "test_source",
            "items_max": 5,
            "total_available": 3,
            "messages": messages,
        }
    ]
    artifact = build_mailbox_selection_artifact(
        run_id="test-run",
        sources=sources,
        logger=_null_logger(),
    )
    assert len(artifact["warnings"]) > 0
    assert any(
        "date" in w.lower() and "fallback" in w.lower() for w in artifact["warnings"]
    )


def test_mailbox_selection_safe_shape() -> None:
    messages = [
        {
            "source_message_id": "1",
            "internal_date": "2026-06-01T10:00:00+00:00",
            "message_id": "<abc@host>",
        },
        {
            "source_message_id": "2",
            "internal_date": "2026-06-02T10:00:00+00:00",
            "message_id": "<def@host>",
        },
    ]
    sources = [
        {
            "source_id": "test_source",
            "items_max": 10,
            "total_available": 2,
            "messages": messages,
        }
    ]
    artifact = build_mailbox_selection_artifact(
        run_id="test-run",
        sources=sources,
        logger=_null_logger(),
    )
    artifact_str = json.dumps(artifact)

    assert "raw_eml" not in artifact_str
    assert "message/rfc822" not in artifact_str
    assert "attachment_content" not in artifact_str
    assert "content_bytes" not in artifact_str

    src = artifact["sources"][0]
    for msg in src["messages"]:
        assert "source_message_id" in msg
        assert "internal_date" in msg
        assert "message_id" in msg
        assert "subject" in msg
        assert "selected" in msg


def test_write_mailbox_selection_artifact(tmp_path: Path) -> None:
    artifact = {
        "run_id": "test-run-write",
        "strategy": "latest_n_by_internaldate_desc",
        "sources": [],
        "warnings": [],
    }
    path = write_mailbox_selection_artifact(
        storage_dir=tmp_path,
        run_id="test-run-write",
        artifact=artifact,
        logger=_null_logger(),
    )
    assert path.exists()
    assert path.name == "mailbox_selection.json"
    assert "runs" in str(path)
    assert "test-run-write" in str(path)

    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["run_id"] == "test-run-write"
    assert loaded["strategy"] == "latest_n_by_internaldate_desc"


def test_sort_messages_date_fallback_uid_order() -> None:
    messages = [
        {"source_message_id": "msg-003", "uid": "003"},
        {"source_message_id": "msg-001", "uid": "001"},
        {"source_message_id": "msg-002", "uid": "002"},
    ]
    sorted_msgs = sort_messages_by_date(messages)
    assert len(sorted_msgs) == 3
    assert sorted_msgs[0]["source_message_id"] == "msg-003"
    assert sorted_msgs[1]["source_message_id"] == "msg-002"
    assert sorted_msgs[2]["source_message_id"] == "msg-001"
