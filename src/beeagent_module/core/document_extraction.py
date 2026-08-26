from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from beeagent_module.core.attachment_store import resolve_attachment_blob_path
from beeagent_module.core.paths import get_project_root

DOCLING_ENGINE = "docling"
_WORKER_MODULE = "beeagent_module.core.document_extraction_worker"
_LAYOUT_MODEL_REPO_ID = "docling-project/docling-layout-heron"
_LAYOUT_MODEL_REVISION = "main"

_STATUS_OK = "ok"
_STATUS_METADATA_ONLY = "metadata_only"
_STATUS_UNSUPPORTED = "unsupported"
_STATUS_REFUSED = "refused"
_STATUS_FAILED = "failed"

_REASON_BLOB_UNAVAILABLE = "attachment_blob_unavailable"
_REASON_WORKER_SPAWN_FAILED = "docling_worker_spawn_failed"
_REASON_WORKER_TIMEOUT = "docling_worker_timeout"
_REASON_WORKER_NO_RESULT = "docling_worker_no_result"
_REASON_UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"

_WORKER_ENV_KEYS = (
    "PATH",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUTF8",
    "SYSTEMROOT",
    "COMSPEC",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HUGGINGFACE_HUB_CACHE",
    "TRANSFORMERS_CACHE",
)
_WORKER_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
}


def _worker_environment() -> dict[str, str]:
    env: dict[str, str] = {}
    for key in _WORKER_ENV_KEYS:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.update(_WORKER_OFFLINE_ENV)
    return env


@dataclass(frozen=True)
class DocumentExtractionResult:
    attachment_id: str
    status: str
    reason_code: str
    engine: str
    text: str
    text_length: int
    is_truncated: bool
    content_type: str
    ocr_used: bool
    page_count: int | None


def _failed_result(
    attachment_id: str,
    content_type: str,
    reason_code: str,
) -> DocumentExtractionResult:
    return DocumentExtractionResult(
        attachment_id=attachment_id,
        status=_STATUS_FAILED,
        reason_code=reason_code,
        engine="none",
        text="",
        text_length=0,
        is_truncated=False,
        content_type=content_type,
        ocr_used=False,
        page_count=None,
    )


def _unsupported_result(
    attachment_id: str,
    content_type: str,
) -> DocumentExtractionResult:
    return DocumentExtractionResult(
        attachment_id=attachment_id,
        status=_STATUS_UNSUPPORTED,
        reason_code=_REASON_UNSUPPORTED_CONTENT_TYPE,
        engine="none",
        text="",
        text_length=0,
        is_truncated=False,
        content_type=content_type,
        ocr_used=False,
        page_count=None,
    )


def _parse_worker_result(
    attachment_id: str,
    raw: dict[str, Any],
) -> DocumentExtractionResult:
    status = str(raw.get("status") or _STATUS_FAILED)
    reason_code = str(raw.get("reason_code") or "docling_extraction_failed")
    text = raw.get("text")
    bounded_text = text if isinstance(text, str) else ""
    return DocumentExtractionResult(
        attachment_id=attachment_id,
        status=status,
        reason_code=reason_code,
        engine=str(raw.get("engine") or DOCLING_ENGINE),
        text=bounded_text,
        text_length=int(raw.get("text_length") or len(bounded_text)),
        is_truncated=bool(raw.get("is_truncated")),
        content_type=str(raw.get("content_type") or ""),
        ocr_used=bool(raw.get("ocr_used")),
        page_count=raw.get("page_count"),
    )


def extract_attachment_documents(
    storage_dir: Path,
    run_id: str,
    attachment_items: list[dict[str, Any]],
    extraction_settings: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, DocumentExtractionResult]:
    results: dict[str, DocumentExtractionResult] = {}
    if not attachment_items:
        return results

    request_items: list[dict[str, Any]] = []
    for item in attachment_items:
        attachment_id = str(item.get("attachment_id") or "")
        content_type = str(item.get("content_type") or "").strip().lower()
        if not attachment_id or not content_type:
            continue
        blob_path = resolve_attachment_blob_path(storage_dir, run_id, attachment_id)
        if blob_path is None:
            results[attachment_id] = _failed_result(
                attachment_id, content_type, _REASON_BLOB_UNAVAILABLE
            )
            continue
        request_items.append(
            {
                "index": len(request_items),
                "attachment_id": attachment_id,
                "blob_path": str(blob_path),
                "content_type": content_type,
            }
        )

    if not request_items:
        return results

    worker_results = _run_worker_batch(
        request_items=request_items,
        extraction_settings=extraction_settings,
        logger=logger,
    )
    for attachment_id, raw in worker_results.items():
        results[attachment_id] = _parse_worker_result(attachment_id, raw)
    return results


def _run_worker_batch(
    request_items: list[dict[str, Any]],
    extraction_settings: dict[str, Any],
    logger: logging.Logger,
) -> dict[str, dict[str, Any]]:
    per_item_timeout = int(extraction_settings.get("timeout_seconds") or 60)
    request = {
        "items": [
            {
                **item,
                "chars_max": int(extraction_settings.get("chars_max") or 0),
                "pages_max": int(extraction_settings.get("pages_max") or 0),
                "ocr_enabled": bool(extraction_settings.get("ocr_enabled")),
            }
            for item in request_items
        ]
    }
    total_timeout = max(per_item_timeout, per_item_timeout * len(request_items))

    fd, request_path = tempfile.mkstemp(prefix="dl_req_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(request, handle)
    except Exception:
        os.close(fd)
        raise
    response_path = request_path + ".result.json"

    try:
        try:
            completed = subprocess.run(
                [sys.executable, "-m", _WORKER_MODULE, request_path, response_path],
                capture_output=True,
                text=True,
                timeout=total_timeout,
                cwd=str(get_project_root()),
                env=_worker_environment(),
            )
        except subprocess.TimeoutExpired:
            logger.error(
                "document extraction worker timed out: run_items=%d timeout=%ds",
                len(request_items),
                total_timeout,
            )
            return {
                str(item.get("attachment_id") or ""): {
                    "status": _STATUS_FAILED,
                    "reason_code": _REASON_WORKER_TIMEOUT,
                }
                for item in request_items
            }
        except OSError as exc:
            logger.error("document extraction worker spawn failed: %s", exc)
            return {
                str(item.get("attachment_id") or ""): {
                    "status": _STATUS_FAILED,
                    "reason_code": _REASON_WORKER_SPAWN_FAILED,
                }
                for item in request_items
            }

        if completed.returncode != 0:
            logger.error(
                "document extraction worker failed: returncode=%d",
                completed.returncode,
            )
            return {
                str(item.get("attachment_id") or ""): {
                    "status": _STATUS_FAILED,
                    "reason_code": _REASON_WORKER_NO_RESULT,
                }
                for item in request_items
            }

        response = _read_response(response_path)
        if response is None:
            return {
                str(item.get("attachment_id") or ""): {
                    "status": _STATUS_FAILED,
                    "reason_code": _REASON_WORKER_NO_RESULT,
                }
                for item in request_items
            }

        results: dict[str, dict[str, Any]] = {}
        for raw in response.get("results", []):
            if not isinstance(raw, dict):
                continue
            index = raw.get("index")
            if not isinstance(index, int) or index < 0 or index >= len(request_items):
                continue
            results[str(request_items[index].get("attachment_id") or "")] = raw
        return results
    finally:
        _unlink_path(request_path)
        _unlink_path(response_path)


def _read_response(response_path: str) -> dict[str, Any] | None:
    path = Path(response_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError, TypeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _unlink_path(path: str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def prepare_docling_assets() -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=_LAYOUT_MODEL_REPO_ID,
        revision=_LAYOUT_MODEL_REVISION,
    )
    from beeagent_module.core.docling_reader import prepare_rapidocr_assets

    prepare_rapidocr_assets()
