from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
import pytest

from tests.beeui_console_support import (
    _client,
    _make_storage,
    _seed_download_attachment,
)


def _seed_format_attachment(
    storage_dir: Path,
    run_id: str,
    attachment_id: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> None:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "classified_events.json").write_text(
        json.dumps([{"event_id": "evt-1"}]), encoding="utf-8"
    )
    store_dir = storage_dir / "attachments" / run_id
    store_dir.mkdir(parents=True, exist_ok=True)
    blob_id = "att-" + sha256(content).hexdigest()[:24]
    (store_dir / f"{blob_id}.bin").write_bytes(content)
    manifest_path = store_dir / "attachment_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {
            "run_id": run_id,
            "version": 1,
            "status": "ok",
            "policy": {},
            "aggregate": {"attachment_count": 0, "stored_count": 0},
            "items": [],
        }
    )
    manifest["items"].append(
        {
            "attachment_id": attachment_id,
            "event_id": "evt-1",
            "event_instance_id": "event-000001",
            "blob_id": blob_id,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(content),
            "sha256": sha256(content).hexdigest(),
            "storage_status": "stored",
        }
    )
    manifest["aggregate"]["attachment_count"] = len(manifest["items"])
    manifest["aggregate"]["stored_count"] = len(manifest["items"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def test_attachment_download_forced_headers_and_content(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl",
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert response.content == b"%PDF-1.4 download body bytes"
    disposition = response.headers.get("content-disposition", "")
    assert disposition.startswith("attachment")
    assert "brief.pdf" in disposition
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("content-type", "").startswith(
        "application/octet-stream"
    )


def test_attachment_download_invalid_run_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get("/rop/attachments/evt-1-att-0/download?run_id=../escape")
    assert response.status_code == 400
    response = client.get("/rop/attachments/evt-1-att-0/download?run_id=")
    assert response.status_code == 400


def test_attachment_download_unknown_and_traversal(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get("/rop/attachments/unknown-id/download?run_id=run-dl")
    assert response.status_code == 404
    response = client.get("/rop/attachments/..%2F..%2Fsecret/download?run_id=run-dl")
    assert response.status_code in (400, 404)
    response = client.get("/rop/attachments/evt-1-att-0/download?run_id=run-other")
    assert response.status_code == 404


def test_attachment_download_event_mismatch_fails_closed(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_download_attachment(storage_dir, "run-dl")
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl&event_id=other-event"
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "filename,content_type,payload",
    [
        ("rfq.txt", "text/plain", b"RFQ: 100 kg ER70S-6 welding wire"),
        ("prices.csv", "text/csv", b"sku,qty\\nER70S-6,100\\n"),
        ("rfq.pdf", "application/pdf", b"%PDF-1.4 download body bytes"),
        (
            "rfq.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\\x03\\x04 docx download",
        ),
        ("rfq.jpg", "image/jpeg", b"\\xff\\xd8\\xff\\xe0 download jpeg"),
        ("rfq.png", "image/png", b"\\x89PNG\\r\\n\\x1a\\n download png"),
    ],
)
def test_attachment_download_all_supported_formats(
    tmp_path: Path,
    filename: str,
    content_type: str,
    payload: bytes,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _seed_format_attachment(
        storage_dir, "run-dl-formats", "evt-1-att-0", filename, content_type, payload
    )
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl-formats&event_id=evt-1"
    )
    assert response.status_code == 200
    assert response.content == payload
    disposition = response.headers.get("content-disposition", "")
    assert disposition.startswith("attachment;")
    assert response.headers.get("content-type") == "application/octet-stream"
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("cache-control") == "no-store"


def test_attachment_download_blocked_eml_has_no_blob(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_id = "run-dl-eml"
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "classified_events.json").write_text(
        json.dumps([{"event_id": "evt-1"}]), encoding="utf-8"
    )
    store_dir = storage_dir / "attachments" / run_id
    store_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": run_id,
        "version": 1,
        "status": "ok",
        "policy": {},
        "aggregate": {"attachment_count": 1, "stored_count": 0},
        "items": [
            {
                "attachment_id": "evt-1-att-0",
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "blob_id": None,
                "filename": "nested.eml",
                "content_type": "message/rfc822",
                "size_bytes": 128,
                "sha256": None,
                "storage_status": "blocked",
                "reason_code": "blocked_email_attachment",
            }
        ],
    }
    (store_dir / "attachment_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    client = _client(storage_dir)
    response = client.get(
        "/rop/attachments/evt-1-att-0/download?run_id=run-dl-eml&event_id=evt-1"
    )
    assert response.status_code == 404
    assert not list(store_dir.glob("*.bin"))


def test_event_detail_attachment_lifecycle_metadata(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = storage_dir / "runs" / "run-detail-lifecycle"
    run_dir.mkdir(parents=True, exist_ok=True)
    event_id = "evt-lifecycle"
    normalized = [
        {
            "event_id": event_id,
            "event_instance_id": "event-000001",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": "Attachment lifecycle",
            "body_preview": "see attached",
            "received_at": "2026-08-03T10:00:00Z",
            "attachments": [
                {
                    "filename": "quote.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 128,
                }
            ],
        }
    ]
    classified = [
        {
            "event_id": event_id,
            "event_instance_id": "event-000001",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.9,
        }
    ]
    extraction = {
        "run_id": "run-detail-lifecycle",
        "status": "ok",
        "aggregate": {"attachment_count": 2},
        "items": [
            {
                "event_id": event_id,
                "event_instance_id": "event-000001",
                "attachment_id": "evt-lifecycle-att-0",
                "filename": "quote.pdf",
                "content_type": "application/pdf",
                "size_bytes": 128,
                "extraction_status": "metadata_only",
                "storage_status": "stored",
                "analysis_status": "ok",
                "sha256": "a" * 64,
                "download_url": "/rop/attachments/evt-lifecycle-att-0/download?run_id=run-detail-lifecycle",
                "preview_available": False,
            },
            {
                "event_id": event_id,
                "event_instance_id": "event-000001",
                "attachment_id": "evt-lifecycle-att-1",
                "filename": "forwarded.eml",
                "content_type": "message/rfc822",
                "size_bytes": None,
                "extraction_status": "refused",
                "storage_status": "blocked",
                "reason_code": "blocked_email_attachment",
                "analysis_status": "disabled",
                "preview_available": False,
            },
        ],
    }
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    (run_dir / "attachment_extraction.json").write_text(
        json.dumps(extraction), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-lifecycle", event_id
    )
    assert len(data["attachments"]) == 2
    att = data["attachments"][0]
    assert att["filename"] == "quote.pdf"
    assert att["storage_status"] == "stored"
    assert att["analysis_status"] == "ok"
    assert att["download_url"].startswith("/rop/attachments/")
    assert att["sha256"] == "a" * 64
    blocked = data["attachments"][1]
    assert blocked["filename"] == "forwarded.eml"
    assert blocked["storage_status"] == "blocked"
    assert blocked["reason_code"] == "blocked_email_attachment"

    client = _client(storage_dir)
    response = client.get(f"/api/rop/events/{event_id}?run_id=run-detail-lifecycle")
    assert response.status_code == 200
    api_att = response.json()["data"]["attachments"][0]
    assert api_att["storage_status"] == "stored"
    assert api_att["analysis_status"] == "ok"
    assert api_att["download_url"].startswith("/rop/attachments/")
    api_blocked = response.json()["data"]["attachments"][1]
    assert api_blocked["storage_status"] == "blocked"
    assert api_blocked["reason_code"] == "blocked_email_attachment"
