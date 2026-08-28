from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from beeagent_module.core.document_extraction import _WORKER_OFFLINE_ENV
from beeagent_module.core.document_extractors import worker_converter


def _apply_offline_env() -> None:
    os.environ.update(_WORKER_OFFLINE_ENV)


def _load_request(request_path: str) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(request_path).read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError, TypeError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_response(response_path: str, payload: dict[str, Any]) -> None:
    Path(response_path).write_text(json.dumps(payload), encoding="utf-8")


def _run_items(extractor_id: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    convert_blob_item = worker_converter(extractor_id)
    results: list[dict[str, Any]] = []
    for item in items:
        index = int(item.get("index") or 0)
        result = convert_blob_item(item)
        result["index"] = index
        results.append(result)
    return results


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        return 2
    request_path, response_path = argv[0], argv[1]
    request = _load_request(request_path)
    if request is None:
        return 2
    _apply_offline_env()
    items = request.get("items")
    if not isinstance(items, list):
        return 2
    extractor_id = request.get("extractor_id")
    if not isinstance(extractor_id, str):
        return 2
    try:
        results = _run_items(extractor_id, items)
    except RuntimeError:
        return 2
    _write_response(response_path, {"results": results})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
