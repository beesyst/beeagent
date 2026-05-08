from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Загрузка и нормализация входных данных для ROP batch flow из configured источника
def find_active_rop_source(input_sources: list[dict]) -> dict:
    if not input_sources:
        raise RuntimeError(
            "rop.sources is empty: no input source declared in config"
        )

    enabled = [s for s in input_sources if s.get("enabled", False)]

    if not enabled:
        raise RuntimeError(
            "rop.sources: no enabled source found; "
            "set enabled: true for exactly one source"
        )

    if len(enabled) > 1:
        ids = ", ".join(str(s.get("source_id", "?")) for s in enabled)
        raise RuntimeError(
            f"rop.sources: multiple enabled sources found ({ids}); "
            "v0 supports exactly one enabled source"
        )

    return enabled[0]


# Безопасное разрешение batch path внутри project_root
def _resolve_project_file_path(project_root: Path, raw_path: str) -> Path:
    if not raw_path:
        raise RuntimeError("batch.path is empty")

    candidate = (project_root / raw_path).resolve()
    root = project_root.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"batch.path must stay inside project root: {raw_path}"
        ) from exc

    return candidate


# Загрузка batch-файла из источника типа json_batch, нормализация событий, возврат (events, metadata)
def load_json_batch(
    source: dict,
    project_root: Path,
    logger: logging.Logger,
) -> tuple[list[dict], dict[str, Any]]:
    source_id: str = source.get("source_id", "unknown")

    items_max = source.get("items_max")
    if not isinstance(items_max, int) or items_max <= 0:
        raise RuntimeError(
            f"rop.sources source_id={source_id}: items_max must be int > 0"
        )

    batch_cfg = source.get("batch")
    if not isinstance(batch_cfg, dict):
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch must be a mapping"
        )

    raw_path = batch_cfg.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch.path is empty"
        )

    period = batch_cfg.get("period")
    if not isinstance(period, str) or not period:
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch.period is empty"
        )

    batch_path = _resolve_project_file_path(project_root, raw_path)

    if not batch_path.exists():
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch file not found: {raw_path}"
        )

    try:
        raw = json.loads(batch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"rop.sources source_id={source_id}: "
            f"batch file is not valid JSON: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise RuntimeError(
            f"rop.sources source_id={source_id}: "
            "batch file must contain a top-level JSON object"
        )

    items = raw.get("items")
    if not isinstance(items, list):
        raise RuntimeError(
            f"rop.sources source_id={source_id}: "
            "batch file must contain 'items' as a list"
        )

    file_period = raw.get("period")
    effective_period = (
        file_period if isinstance(file_period, str) and file_period else period
    )

    events = _normalize_batch_items(
        items=items,
        source_id=source_id,
        items_max=items_max,
        logger=logger,
    )

    metadata: dict[str, Any] = {
        "source_id": source_id,
        "source_type": "json_batch",
        "authority": source.get("authority", "read_only"),
        "batch_path": raw_path,
        "period": effective_period,
        "raw_item_count": len(items),
        "loaded_item_count": len(events),
        "items_max": items_max,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "json_batch loaded: source_id=%s path=%s raw_items=%d loaded=%d period=%s",
        source_id,
        raw_path,
        len(items),
        len(events),
        effective_period,
    )

    return events, metadata


# Нормализация batch-элементов: отфильтровать не-dict, применить items_max
def _normalize_batch_items(
    items: list[Any],
    source_id: str,
    items_max: int,
    logger: logging.Logger,
) -> list[dict]:
    valid: list[dict] = []
    skipped = 0

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            logger.warning(
                "json_batch source_id=%s: item[%d] is not a dict, skipped",
                source_id,
                idx,
            )
            skipped += 1
            continue
        valid.append(item)

    if skipped:
        logger.warning(
            "json_batch source_id=%s: skipped %d non-dict items",
            source_id,
            skipped,
        )

    truncated = valid[:items_max]

    if len(valid) > items_max:
        logger.info(
            "json_batch source_id=%s: truncated to items_max=%d (total valid=%d)",
            source_id,
            items_max,
            len(valid),
        )

    return truncated
