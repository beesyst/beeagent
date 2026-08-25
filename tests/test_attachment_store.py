from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from beeagent_module.core.attachment_store import (
    AttachmentStoreError,
    load_attachment_manifest,
    lookup_attachment,
    manifest_path,
    persist_run_attachments,
    read_attachment_blob,
    resolve_attachment_blob_path,
)


def _logger() -> logging.Logger:
    logger = logging.getLogger("test_attachment_store")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _storage_settings(
    enabled: bool = True,
    file_max: int = 1024,
    aggregate_max: int = 2048,
    files_max: int = 5,
) -> dict:
    return {
        "storage": {
            "enabled": enabled,
            "file_max": file_max,
            "message_max": aggregate_max,
            "files_message_max": files_max,
        }
    }


def _raw_event(
    event_id: str,
    attachments: list[dict],
    instance: str = "event-000001",
) -> dict:
    return {
        "event_id": event_id,
        "event_instance_id": instance,
        "_raw_attachments": attachments,
    }


def _raw_attachment(
    filename: str,
    content_type: str,
    content: bytes,
) -> dict:
    return {
        "filename": filename,
        "content_type": content_type,
        "size": len(content),
        "payload": content,
        "storage_status": "stored",
        "reason_code": None,
    }


def test_pdf_bytes_survive_as_opaque_blob(tmp_path: Path) -> None:
    import hashlib

    pdf = b"%PDF-1.4 fake pdf bytes"
    events = [_raw_event("evt-1", [_raw_attachment("brief.pdf", "application/pdf", pdf)])]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    assert manifest["status"] == "ok"
    item = manifest["items"][0]
    assert item["storage_status"] == "stored"
    assert item["filename"] == "brief.pdf"
    assert item["content_type"] == "application/pdf"
    assert item["size_bytes"] == len(pdf)
    assert item["sha256"] == hashlib.sha256(pdf).hexdigest()
    blob_id = item["blob_id"]
    assert blob_id.startswith("att-")

    blob_path = resolve_attachment_blob_path(tmp_path, "run-1", "evt-1-att-0")
    assert blob_path is not None
    assert blob_path.read_bytes() == pdf
    assert blob_path.name == f"{blob_id}.bin"


@pytest.mark.parametrize(
    "filename,content_type",
    [
        ("a.txt", "text/plain"),
        ("doc.pdf", "application/pdf"),
        ("doc.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("doc.doc", "application/msword"),
        ("img.jpeg", "image/jpeg"),
        ("img.png", "image/png"),
    ],
)
def test_common_formats_stored_opaque_regardless_of_analysis(
    tmp_path: Path, filename: str, content_type: str
) -> None:
    content = b"opaque-bytes-" + filename.encode("utf-8")
    events = [_raw_event("evt-f", [_raw_attachment(filename, content_type, content)])]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-f",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    item = manifest["items"][0]
    assert item["storage_status"] == "stored"
    assert item["sha256"] is not None
    assert item["content_type"] == content_type
    blob = read_attachment_blob(tmp_path, "run-f", "evt-f-att-0")
    assert blob is not None
    assert blob[0] == content


def test_filename_is_metadata_only_and_never_controls_path(tmp_path: Path) -> None:
    content = b"x" * 32
    events = [
        _raw_event(
            "evt-1",
            [
                _raw_attachment("../../etc/passwd", "text/plain", content),
                _raw_attachment("a\\b.txt", "text/plain", content),
            ],
        )
    ]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    for item in manifest["items"]:
        blob_path = resolve_attachment_blob_path(tmp_path, "run-1", item["attachment_id"])
        assert blob_path is not None
        assert blob_path.parent == tmp_path / "attachments" / "run-1"
    assert manifest["items"][0]["filename"] == "../../etc/passwd"


def test_same_content_different_filenames_share_blob_id(tmp_path: Path) -> None:
    content = b"same-content"
    events = [
        _raw_event(
            "evt-1",
            [
                _raw_attachment("one.txt", "text/plain", content),
                _raw_attachment("two.txt", "text/plain", content),
            ],
        )
    ]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    blob_ids = {item["blob_id"] for item in manifest["items"]}
    assert len(blob_ids) == 1
    assert manifest["items"][0]["attachment_id"] != manifest["items"][1]["attachment_id"]


def test_oversized_file_refused_before_storage(tmp_path: Path) -> None:
    content = b"y" * 2048
    events = [_raw_event("evt-1", [_raw_attachment("big.txt", "text/plain", content)])]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(file_max=1024),
        logger=_logger(),
    )

    item = manifest["items"][0]
    assert item["storage_status"] == "oversized"
    assert item["reason_code"] == "attachment_oversized"
    assert item["blob_id"] is None
    assert resolve_attachment_blob_path(tmp_path, "run-1", "evt-1-att-0") is None
    assert manifest["aggregate"]["stored_count"] == 0


def test_count_limit_enforced(tmp_path: Path) -> None:
    attachments = [
        _raw_attachment(f"f{i}.txt", "text/plain", b"x" * 8) for i in range(4)
    ]
    events = [_raw_event("evt-1", attachments)]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(files_max=2),
        logger=_logger(),
    )

    assert [i["storage_status"] for i in manifest["items"]] == [
        "stored",
        "stored",
        "count_exceeded",
        "count_exceeded",
    ]
    assert manifest["aggregate"]["stored_count"] == 2


def test_aggregate_limit_enforced(tmp_path: Path) -> None:
    events = [
        _raw_event(
            "evt-1",
            [
                _raw_attachment("a.txt", "text/plain", b"a" * 1000),
                _raw_attachment("b.txt", "text/plain", b"b" * 1000),
                _raw_attachment("c.txt", "text/plain", b"c" * 1000),
            ],
        )
    ]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(file_max=5000, aggregate_max=2048),
        logger=_logger(),
    )

    assert [i["storage_status"] for i in manifest["items"]] == [
        "stored",
        "stored",
        "aggregate_exceeded",
    ]


def test_blocked_email_attachment_explicit_status(tmp_path: Path) -> None:
    events = [
        _raw_event(
            "evt-1",
            [
                _raw_attachment("note.eml", "message/rfc822", b"raw eml"),
                _raw_attachment("ok.txt", "text/plain", b"ok"),
            ],
        )
    ]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    assert manifest["items"][0]["storage_status"] == "blocked"
    assert manifest["items"][0]["reason_code"] == "blocked_email_attachment"
    assert manifest["items"][1]["storage_status"] == "stored"


def test_storage_disabled_marks_items_disabled(tmp_path: Path) -> None:
    events = [
        _raw_event("evt-1", [_raw_attachment("a.txt", "text/plain", b"hello")])
    ]

    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(enabled=False),
        logger=_logger(),
    )

    assert manifest["items"][0]["storage_status"] == "disabled"
    assert manifest["aggregate"]["stored_count"] == 0
    assert resolve_attachment_blob_path(tmp_path, "run-1", "evt-1-att-0") is None


def test_manifest_contains_no_raw_bytes(tmp_path: Path) -> None:
    content = b"secret-bytes-should-not-leak"
    events = [_raw_event("evt-1", [_raw_attachment("a.txt", "text/plain", content)])]

    persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    manifest_path_ = manifest_path(tmp_path, "run-1")
    raw = manifest_path_.read_text(encoding="utf-8")
    assert "secret-bytes-should-not-leak" not in raw
    manifest = load_attachment_manifest(tmp_path, "run-1")
    assert manifest is not None
    assert "payload" not in json.dumps(manifest)


def test_storage_failure_raises_and_blocks(tmp_path: Path, monkeypatch) -> None:
    def _fail_write(path, content):
        raise OSError("disk full")

    monkeypatch.setattr(
        "beeagent_module.core.attachment_store._write_blob_atomic", _fail_write
    )
    events = [_raw_event("evt-1", [_raw_attachment("a.txt", "text/plain", b"x" * 16)])]

    with pytest.raises(AttachmentStoreError, match="required attachment persistence failed"):
        persist_run_attachments(
            storage_dir=tmp_path,
            run_id="run-1",
            events=events,
            attachment_settings=_storage_settings(),
            logger=_logger(),
        )

    assert load_attachment_manifest(tmp_path, "run-1") is None


def test_lookup_rejects_unknown_id_and_run(tmp_path: Path) -> None:
    events = [_raw_event("evt-1", [_raw_attachment("a.txt", "text/plain", b"x")])]
    persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    assert lookup_attachment(tmp_path, "run-1", "unknown") is None
    assert lookup_attachment(tmp_path, "run-other", "evt-1-att-0") is None
    assert resolve_attachment_blob_path(tmp_path, "run-1", "../etc/passwd") is None


def test_traversal_run_id_rejected(tmp_path: Path) -> None:
    with pytest.raises(AttachmentStoreError, match="path traversal"):
        manifest_path(tmp_path, "../escape")
    with pytest.raises(AttachmentStoreError, match="path traversal"):
        lookup_attachment(tmp_path, "../escape", "att-1")


def test_multiple_events_produce_stable_attachment_ids(tmp_path: Path) -> None:
    events = [
        _raw_event("evt-1", [_raw_attachment("a.txt", "text/plain", b"a")], "event-000001"),
        _raw_event("evt-2", [_raw_attachment("b.txt", "text/plain", b"b")], "event-000002"),
    ]
    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-1",
        events=events,
        attachment_settings=_storage_settings(),
        logger=_logger(),
    )

    assert [i["attachment_id"] for i in manifest["items"]] == [
        "evt-1-att-0",
        "evt-2-att-0",
    ]
    assert manifest["items"][0]["event_instance_id"] == "event-000001"


def test_long_event_id_attachment_id_truncated_consistently(
    tmp_path: Path,
) -> None:
    from beeagent_module.core.attachment_extraction import (
        build_attachment_extraction,
    )

    long_event_id = "x" * 300
    raw = _raw_attachment("note.pdf", "application/pdf", b"pdf-bytes")
    event = _raw_event(long_event_id, [raw])
    event["attachments"] = [
        {"filename": "note.pdf", "content_type": "application/pdf", "size": 9}
    ]
    attachment_settings = {
        "enabled": True,
        "chars_max": 500,
        "size_max": 1048576,
        "types": ["text/plain", "application/pdf"],
        "storage": {
            "enabled": True,
            "file_max": 1048576,
            "message_max": 2097152,
            "files_message_max": 10,
        },
    }
    manifest = persist_run_attachments(
        storage_dir=tmp_path,
        run_id="run-long-id",
        events=[event],
        attachment_settings=attachment_settings,
        logger=_logger(),
    )
    artifact, _enriched = build_attachment_extraction(
        run_id="run-long-id",
        events=[event],
        attachment_settings=attachment_settings,
        attachment_manifest=manifest,
    )
    expected_id = f"{long_event_id[:255]}-att-0"
    assert manifest["items"][0]["attachment_id"] == expected_id
    assert artifact["items"][0]["attachment_id"] == expected_id
    assert artifact["items"][0]["storage_status"] == "stored"
    assert artifact["items"][0]["download_url"].startswith("/rop/attachments/")
