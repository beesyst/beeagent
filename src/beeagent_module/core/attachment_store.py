from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

ATTACHMENT_STORE_DIRNAME = "attachments"
MANIFEST_FILENAME = "attachment_manifest.json"
MANIFEST_VERSION = 1
BLOB_SUFFIX = ".bin"
_BLOB_ID_PREFIX = "att-"
_BLOB_ID_DIGEST_LENGTH = 24
_FILENAME_MAX = 255
_IDENTITY_MAX = 255

_STORAGE_BLOCKED_REASON = "blocked_email_attachment"
_STORAGE_OVERSIZED_REASON = "attachment_oversized"
_STORAGE_COUNT_REASON = "attachment_count_exceeded"
_STORAGE_AGGREGATE_REASON = "message_aggregate_exceeded"
_STORAGE_FAILED_REASON = "attachment_storage_failed"


class AttachmentStoreError(RuntimeError):
    pass


def _bounded_text(value: Any, max_length: int = _FILENAME_MAX) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def attachment_storage_policy(attachment_settings: dict[str, Any]) -> dict[str, Any]:
    storage = attachment_settings.get("storage", {})
    if not isinstance(storage, dict):
        storage = {}
    return {
        "enabled": storage.get("enabled") is True,
        "file_max_bytes": int(storage.get("file_max_bytes") or 0),
        "message_aggregate_max_bytes": int(
            storage.get("message_aggregate_max_bytes") or 0
        ),
        "files_max_per_message": int(storage.get("files_max_per_message") or 0),
    }


def run_attachment_store_dir(storage_dir: Path, run_id: str) -> Path:
    root = storage_dir / ATTACHMENT_STORE_DIRNAME / run_id
    return root.resolve()


def _bounded_run_store_dir(storage_dir: Path, run_id: str) -> Path:
    store_root = (storage_dir / ATTACHMENT_STORE_DIRNAME).resolve()
    run_dir = (store_root / run_id).resolve()
    if not run_dir.is_relative_to(store_root):
        raise AttachmentStoreError(
            "Invalid run_id for attachment store: path traversal is not allowed."
        )
    return run_dir


def manifest_path(storage_dir: Path, run_id: str) -> Path:
    return _bounded_run_store_dir(storage_dir, run_id) / MANIFEST_FILENAME


def _blob_id(content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()[:_BLOB_ID_DIGEST_LENGTH]
    return f"{_BLOB_ID_PREFIX}{digest}"


def _raw_attachment_items(event: dict[str, Any]) -> list[dict[str, Any]]:
    raw = event.get("_raw_attachments")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def event_attachment_id(event_id: Any, index: int) -> str:
    bounded = _bounded_text(event_id, _IDENTITY_MAX)
    return f"{bounded or 'event'}-att-{index}"


def _event_attachment_id(event: dict[str, Any], index: int) -> str:
    return event_attachment_id(event.get("event_id"), index)


def _apply_retention_limits(
    attachments: list[dict[str, Any]],
    policy: dict[str, Any],
) -> None:
    if not policy.get("enabled"):
        for item in attachments:
            item["payload"] = None
            item["storage_status"] = "disabled"
            item["reason_code"] = "attachment_storage_disabled"
        return

    count_limit = int(policy.get("files_max_per_message") or 0)
    file_limit = int(policy.get("file_max_bytes") or 0)
    aggregate_limit = int(policy.get("message_aggregate_max_bytes") or 0)

    aggregate_total = 0
    for index, item in enumerate(attachments, start=1):
        if count_limit > 0 and index > count_limit:
            item["payload"] = None
            item["storage_status"] = "count_exceeded"
            item["reason_code"] = _STORAGE_COUNT_REASON
            continue
        size = item.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            item["payload"] = None
            item["storage_status"] = "malformed"
            item["reason_code"] = "malformed_attachment_metadata"
            continue
        if file_limit > 0 and size > file_limit:
            item["payload"] = None
            item["storage_status"] = "oversized"
            item["reason_code"] = _STORAGE_OVERSIZED_REASON
            continue
        if aggregate_limit > 0 and aggregate_total + size > aggregate_limit:
            item["payload"] = None
            item["storage_status"] = "aggregate_exceeded"
            item["reason_code"] = _STORAGE_AGGREGATE_REASON
            continue
        aggregate_total += size
        if item.get("payload") is None:
            item["storage_status"] = "unavailable"
            item["reason_code"] = "attachment_payload_unavailable"


def _is_blocked_email_attachment(filename: str, content_type: str) -> bool:
    normalized_filename = filename.strip().lower()
    normalized_content_type = content_type.strip().lower()
    return (
        normalized_filename.endswith(".eml")
        or normalized_content_type == "message/rfc822"
    )


def _write_blob_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".att_blob.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def persist_run_attachments(
    storage_dir: Path,
    run_id: str,
    events: list[dict[str, Any]],
    attachment_settings: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, Any]:
    policy = attachment_storage_policy(attachment_settings)
    items: list[dict[str, Any]] = []
    stored_count = 0
    refused_count = 0
    failed_count = 0
    total_bytes = 0

    for event in events:
        event_id = _bounded_text(event.get("event_id"), _IDENTITY_MAX)
        event_instance_id = _bounded_text(
            event.get("event_instance_id"), _IDENTITY_MAX
        )
        raw_attachments = _raw_attachment_items(event)
        _apply_retention_limits(raw_attachments, policy)

        for index, raw in enumerate(raw_attachments):
            filename = _bounded_text(raw.get("filename"))
            content_type = _bounded_text(raw.get("content_type"))
            size = raw.get("size")
            payload = raw.get("payload")
            attachment_id = _event_attachment_id(event, index)

            if _is_blocked_email_attachment(filename, content_type):
                refused_count += 1
                items.append(
                    {
                        "attachment_id": attachment_id,
                        "event_id": event_id,
                        "event_instance_id": event_instance_id,
                        "blob_id": None,
                        "filename": filename,
                        "content_type": content_type,
                        "size_bytes": size if isinstance(size, int) else None,
                        "sha256": None,
                        "storage_status": "blocked",
                        "reason_code": _STORAGE_BLOCKED_REASON,
                        "refusal_reason": "email attachments are blocked",
                    }
                )
                continue

            storage_status = str(raw.get("storage_status") or "stored")
            reason_code = raw.get("reason_code")

            if storage_status != "stored" or not isinstance(payload, bytes):
                if storage_status in ("oversized", "count_exceeded", "aggregate_exceeded"):
                    refused_count += 1
                items.append(
                    {
                        "attachment_id": attachment_id,
                        "event_id": event_id,
                        "event_instance_id": event_instance_id,
                        "blob_id": None,
                        "filename": filename,
                        "content_type": content_type,
                        "size_bytes": size if isinstance(size, int) else None,
                        "sha256": None,
                        "storage_status": storage_status,
                        "reason_code": reason_code,
                        "refusal_reason": _refusal_reason_for_status(storage_status),
                    }
                )
                continue

            try:
                blob_id = _blob_id(payload)
                blob_path = (
                    _bounded_run_store_dir(storage_dir, run_id) / f"{blob_id}{BLOB_SUFFIX}"
                )
                _write_blob_atomic(blob_path, payload)
            except OSError as exc:
                failed_count += 1
                logger.error(
                    "attachment storage failed: run_id=%s attachment_id=%s reason=%s",
                    run_id,
                    attachment_id,
                    exc,
                )
                items.append(
                    {
                        "attachment_id": attachment_id,
                        "event_id": event_id,
                        "event_instance_id": event_instance_id,
                        "blob_id": None,
                        "filename": filename,
                        "content_type": content_type,
                        "size_bytes": size if isinstance(size, int) else None,
                        "sha256": None,
                        "storage_status": "failed",
                        "reason_code": _STORAGE_FAILED_REASON,
                        "refusal_reason": "attachment storage failed",
                    }
                )
                continue

            stored_count += 1
            total_bytes += len(payload)
            items.append(
                {
                    "attachment_id": attachment_id,
                    "event_id": event_id,
                    "event_instance_id": event_instance_id,
                    "blob_id": blob_id,
                    "filename": filename,
                    "content_type": content_type,
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "storage_status": "stored",
                    "reason_code": None,
                    "refusal_reason": None,
                    "stored_path": f"{ATTACHMENT_STORE_DIRNAME}/{run_id}/{blob_id}{BLOB_SUFFIX}",
                }
            )

    if failed_count > 0:
        raise AttachmentStoreError(
            f"required attachment persistence failed: run_id={run_id} "
            f"failed_count={failed_count}"
        )

    manifest = {
        "run_id": run_id,
        "version": MANIFEST_VERSION,
        "status": "ok",
        "policy": {
            "enabled": policy["enabled"],
            "file_max_bytes": policy["file_max_bytes"],
            "message_aggregate_max_bytes": policy["message_aggregate_max_bytes"],
            "files_max_per_message": policy["files_max_per_message"],
        },
        "aggregate": {
            "attachment_count": len(items),
            "stored_count": stored_count,
            "refused_count": refused_count,
            "failed_count": failed_count,
            "total_bytes": total_bytes,
        },
        "items": items,
    }

    _write_manifest(storage_dir, run_id, manifest)
    logger.info(
        "attachment manifest persisted: run_id=%s attachments=%d stored=%d refused=%d",
        run_id,
        len(items),
        stored_count,
        refused_count,
    )
    return manifest


def _refusal_reason_for_status(status: str) -> str | None:
    return {
        "oversized": "attachment exceeds storage size limit",
        "count_exceeded": "attachment count limit exceeded",
        "aggregate_exceeded": "message attachment aggregate size limit exceeded",
        "blocked": "email attachments are blocked",
        "failed": "attachment storage failed",
        "disabled": "attachment storage disabled",
        "malformed": "attachment metadata is invalid",
        "unavailable": "attachment payload unavailable",
    }.get(status)


def _write_manifest(storage_dir: Path, run_id: str, manifest: dict[str, Any]) -> Path:
    path = manifest_path(storage_dir, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".att_manifest.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def load_attachment_manifest(storage_dir: Path, run_id: str) -> dict[str, Any] | None:
    path = manifest_path(storage_dir, run_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("version") != MANIFEST_VERSION:
        return None
    return data


def _manifest_items(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    items = manifest.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def lookup_attachment(
    storage_dir: Path,
    run_id: str,
    attachment_id: str,
) -> dict[str, Any] | None:
    manifest = load_attachment_manifest(storage_dir, run_id)
    if manifest is None:
        return None
    for item in _manifest_items(manifest):
        if str(item.get("attachment_id") or "") == attachment_id:
            return item
    return None


def resolve_attachment_blob_path(
    storage_dir: Path,
    run_id: str,
    attachment_id: str,
) -> Path | None:
    item = lookup_attachment(storage_dir, run_id, attachment_id)
    if item is None:
        return None
    blob_id = item.get("blob_id")
    if not isinstance(blob_id, str) or not blob_id:
        return None
    if item.get("storage_status") != "stored":
        return None
    store_root = (storage_dir / ATTACHMENT_STORE_DIRNAME).resolve()
    blob_path = (store_root / run_id / f"{blob_id}{BLOB_SUFFIX}").resolve()
    if not blob_path.is_relative_to(store_root):
        return None
    return blob_path


def read_attachment_blob(
    storage_dir: Path,
    run_id: str,
    attachment_id: str,
) -> tuple[bytes, dict[str, Any]] | None:
    path = resolve_attachment_blob_path(storage_dir, run_id, attachment_id)
    item = lookup_attachment(storage_dir, run_id, attachment_id)
    if path is None or item is None:
        return None
    try:
        content = path.read_bytes()
    except OSError:
        return None
    return content, item


def attachment_download_url(run_id: str, attachment_id: str) -> str:
    return (
        f"/rop/attachments/{quote(str(attachment_id), safe='')}/download"
        f"?run_id={quote(run_id, safe='')}"
    )
