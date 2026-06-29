from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_mailbox_selection_artifact(
    run_id: str,
    sources: list[dict[str, Any]],
    logger: logging.Logger,
) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "run_id": run_id,
        "strategy": "latest_n_by_internaldate_desc",
        "sources": [],
        "warnings": [],
    }

    for source in sources:
        source_id = source.get("source_id", "unknown")
        items_max = source.get("items_max", 0)
        available_count = source.get("total_available", 0)
        messages = source.get("messages", [])
        source_warnings: list[str] = []

        date_fallback_count = sum(
            1 for m in messages if m.get("_date_fallback")
        )

        if date_fallback_count > 0:
            w = (
                f"source_id={source_id}: {date_fallback_count} message(s) "
                f"had no reliable date; used UID/order fallback"
            )
            source_warnings.append(w)
            logger.warning("mailbox selection: %s", w)

        source_entry: dict[str, Any] = {
            "source_id": source_id,
            "items_max": items_max,
            "selected_count": len(messages),
            "available_count": available_count,
            "messages": [
                {
                    "source_message_id": m.get("source_message_id", ""),
                    "internal_date": m.get("internal_date"),
                    "message_id": m.get("message_id", ""),
                    "subject": m.get("subject", ""),
                    "selected": True,
                }
                for m in messages
            ],
            "warnings": source_warnings,
        }
        artifact["sources"].append(source_entry)
        artifact["warnings"].extend(source_warnings)

    return artifact


def write_mailbox_selection_artifact(
    storage_dir: Path,
    run_id: str,
    artifact: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "mailbox_selection.json"
    path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "mailbox_selection artifact written: run_id=%s path=%s sources=%d",
        run_id,
        path.relative_to(storage_dir),
        len(artifact.get("sources", [])),
    )
    return path


def sort_messages_by_date(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    def _sort_key(m: dict[str, Any]) -> tuple[int, str]:
        raw = m.get("internal_date") or m.get("date") or ""
        if isinstance(raw, str) and raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return (0, dt.isoformat())
            except ValueError:
                return (1, "")
        uid = m.get("source_message_id") or m.get("uid") or ""
        return (1, uid)

    sorted_msgs = sorted(messages, key=_sort_key)
    sorted_msgs.reverse()

    return sorted_msgs
