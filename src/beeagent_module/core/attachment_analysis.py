from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.attachment_store import load_attachment_manifest
from beeagent_module.core.document_extraction import (
    DocumentExtractionResult,
    extract_attachment_documents,
)

_ANALYSIS_STATUS_OK = "ok"
_ANALYSIS_STATUS_DISABLED = "disabled"
_ANALYSIS_STATUS_UNSUPPORTED = "unsupported"
_ANALYSIS_STATUS_FAILED = "failed"


def _analysis_policy(attachment_settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": attachment_settings.get("enabled") is True,
        "types": {
            str(item).strip().lower()
            for item in attachment_settings.get("types", [])
            if isinstance(item, str) and item.strip()
        },
        "size_max": int(attachment_settings.get("size_max") or 0),
    }


def _extraction_settings(attachment_settings: dict[str, Any]) -> dict[str, Any]:
    extraction = attachment_settings.get("extraction", {})
    if not isinstance(extraction, dict):
        extraction = {}
    return {
        "engine": str(extraction.get("engine") or "").strip(),
        "chars_max": int(extraction.get("chars_max") or 0),
        "pages_max": int(extraction.get("pages_max") or 0),
        "timeout_seconds": int(extraction.get("timeout_seconds") or 60),
        "ocr_enabled": bool(extraction.get("ocr_enabled")),
    }


def _manifest_items(manifest: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        return []
    items = manifest.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _disabled_result(attachment_id: str) -> dict[str, Any]:
    return {
        "analysis_status": _ANALYSIS_STATUS_DISABLED,
        "reason_code": "analysis_disabled",
        "analysis_preview": "",
        "preview_available": False,
    }


def _unsupported_result(attachment_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "analysis_status": _ANALYSIS_STATUS_UNSUPPORTED,
        "reason_code": reason_code,
        "analysis_preview": "",
        "preview_available": False,
    }


def _failed_result(attachment_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "analysis_status": _ANALYSIS_STATUS_FAILED,
        "reason_code": reason_code,
        "analysis_preview": "",
        "preview_available": False,
    }


def _map_extraction_result(result: DocumentExtractionResult) -> dict[str, Any]:
    if result.status == "unsupported":
        return _unsupported_result(result.attachment_id, result.reason_code)
    if result.status != "ok":
        return _failed_result(result.attachment_id, result.reason_code)
    return {
        "analysis_status": _ANALYSIS_STATUS_OK,
        "reason_code": result.reason_code,
        "analysis_preview": result.text,
        "preview_available": bool(result.text),
        "engine": result.engine,
        "text_length": result.text_length,
        "is_truncated": result.is_truncated,
        "ocr_used": result.ocr_used,
        "page_count": result.page_count,
    }


def run_attachment_analysis(
    storage_dir: Path,
    run_id: str,
    attachment_settings: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, dict[str, Any]]:
    policy = _analysis_policy(attachment_settings)
    results: dict[str, dict[str, Any]] = {}

    manifest = load_attachment_manifest(storage_dir, run_id)
    stored_items = [
        item
        for item in _manifest_items(manifest)
        if item.get("storage_status") == "stored"
    ]
    if not stored_items:
        return results

    if not policy["enabled"]:
        for item in stored_items:
            attachment_id = str(item.get("attachment_id") or "")
            results[attachment_id] = _disabled_result(attachment_id)
        return results

    eligible: list[dict[str, Any]] = []
    for item in stored_items:
        attachment_id = str(item.get("attachment_id") or "")
        content_type = str(item.get("content_type") or "").lower()
        size = item.get("size_bytes")
        if content_type not in policy["types"]:
            results[attachment_id] = _unsupported_result(
                attachment_id, "unsupported_content_type"
            )
            continue
        if (
            isinstance(size, int)
            and policy["size_max"] > 0
            and size > policy["size_max"]
        ):
            results[attachment_id] = _unsupported_result(
                attachment_id, "attachment_oversized"
            )
            continue
        eligible.append(
            {
                "attachment_id": attachment_id,
                "content_type": content_type,
            }
        )

    if not eligible:
        return results

    extraction_results = extract_attachment_documents(
        storage_dir=storage_dir,
        run_id=run_id,
        attachment_items=eligible,
        extraction_settings=_extraction_settings(attachment_settings),
        logger=logger,
    )

    for attachment_id, result in extraction_results.items():
        results[attachment_id] = _map_extraction_result(result)
        logger.info(
            "attachment extraction completed: run_id=%s attachment_id=%s status=%s chars=%d",
            run_id,
            attachment_id,
            result.status,
            result.text_length,
        )

    return results
