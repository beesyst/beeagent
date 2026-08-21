from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeGuard

from beeagent_module.adapters.bitrix_client import (
    BitrixConnectorError,
    BitrixMalformedResponse,
)

OUTBOUND_CORRELATION_ARTIFACT = "bitrix_outbound_correlation.json"
_MAX_OUTBOUND_ACTIVITIES = 200
_MAX_EVIDENCE_ITEMS = 200
_ACTIVITY_EMAIL_TYPE_ID = 4
_ACTIVITY_DIRECTION_OUT = 2
_MAX_IDENTIFIER_LENGTH = 320
_MESSAGE_ID_SETTINGS_KEYS = ("MESSAGE_ID", "message_id", "EMAIL_MESSAGE_ID")
_CRM_ACTIVITY_REF_RE = re.compile(r"crm\.activity\.(\d+)")


def _bounded_text(value: Any, max_length: int = _MAX_IDENTIFIER_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:max_length]


def _normalize_message_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if len(value) > 2 and value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value[:_MAX_IDENTIFIER_LENGTH]


def _safe_list(value: Any) -> list:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _positive_int(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            parsed = int(normalized)
            return parsed if parsed > 0 else None
    return None


def _extract_reference_ids(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    tokens = re.findall(r"<([^<>]+)>", value)
    if not tokens:
        tokens = value.split()
    result: list[str] = []
    for token in tokens:
        token = _normalize_message_id(token)
        if token and token not in result:
            result.append(token)
    return result


def _event_reference_ids(event: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for header in ("in_reply_to", "references"):
        for ref_id in _extract_reference_ids(event.get(header)):
            if ref_id not in refs:
                refs.append(ref_id)
    return refs


def _crm_activity_reference_ids(event: dict[str, Any]) -> list[int]:
    activity_ids: list[int] = []
    for header in ("in_reply_to", "references"):
        for token in _extract_reference_ids(event.get(header)):
            match = _CRM_ACTIVITY_REF_RE.search(token)
            if match is None:
                continue
            activity_id = int(match.group(1))
            if activity_id > 0 and activity_id not in activity_ids:
                activity_ids.append(activity_id)
    return activity_ids


def _activity_message_id(activity: dict[str, Any]) -> str:
    settings = activity.get("SETTINGS")
    if isinstance(settings, dict):
        message_headers = settings.get("MESSAGE_HEADERS")
        if isinstance(message_headers, dict):
            for header_name, header_value in message_headers.items():
                if (
                    isinstance(header_name, str)
                    and header_name.lower() == "message-id"
                    and isinstance(header_value, str)
                    and header_value.strip()
                ):
                    return _normalize_message_id(header_value)
        for key in _MESSAGE_ID_SETTINGS_KEYS:
            value = settings.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_message_id(value)
    message_id = activity.get("MESSAGE_ID")
    if isinstance(message_id, str) and message_id.strip():
        return _normalize_message_id(message_id)
    return ""


def _activity_target(
    activity: dict[str, Any],
) -> tuple[str, int, int, int | None] | None:
    owner_type_id = _positive_int_or_none(activity.get("OWNER_TYPE_ID"))
    owner_id = _positive_int_or_none(activity.get("OWNER_ID"))
    responsible_id = _positive_int_or_none(activity.get("RESPONSIBLE_ID"))
    owner_type = "lead" if owner_type_id == 1 else "deal" if owner_type_id == 2 else ""
    if owner_type and owner_type_id is not None and owner_id is not None:
        return (
            owner_type,
            owner_type_id,
            owner_id,
            responsible_id,
        )
    return None


def _owner_identity(item: dict[str, Any]) -> tuple[str, int, int] | None:
    entity_type = item.get("target_entity_type")
    entity_type_id = item.get("target_entity_type_id")
    entity_id = item.get("target_entity_id")
    if (
        isinstance(entity_type, str)
        and _positive_int(entity_type_id)
        and _positive_int(entity_id)
    ):
        return (entity_type, int(entity_type_id), int(entity_id))
    return None


def _is_outbound_activity(activity: dict[str, Any]) -> bool:
    return _positive_int_or_none(activity.get("DIRECTION")) == _ACTIVITY_DIRECTION_OUT


def _index_outbound_activity(
    outbound_by_message_id: dict[str, dict[str, Any]],
    ambiguous_message_ids: set[str],
    activity: dict[str, Any],
    max_activities: int,
) -> bool:
    if not isinstance(activity, dict):
        return False
    if not _is_outbound_activity(activity):
        return False
    message_id = _activity_message_id(activity)
    target = _activity_target(activity)
    if not message_id or target is None:
        return False
    if len(outbound_by_message_id) >= max_activities:
        return True
    activity_responsible = target[3]
    item = {
        "outbound_message_id": message_id,
        "target_entity_type": target[0],
        "target_entity_type_id": target[1],
        "target_entity_id": target[2],
        "target_responsible_user_id": activity_responsible,
        "outbound_activity_responsible_user_id": activity_responsible,
    }
    existing = outbound_by_message_id.get(message_id)
    if existing is None:
        if message_id not in ambiguous_message_ids:
            outbound_by_message_id[message_id] = item
    elif _owner_identity(existing) != _owner_identity(item):
        ambiguous_message_ids.add(message_id)
        outbound_by_message_id.pop(message_id, None)
    return False


def collect_outbound_correlation_evidence(
    client: Any,
    events: list[dict[str, Any]],
    logger: logging.Logger,
    *,
    window_days: int = 180,
    max_activities: int = _MAX_OUTBOUND_ACTIVITIES,
    pages_max: int = 3,
) -> list[dict[str, Any]]:
    candidate_events = [
        event
        for event in events
        if isinstance(event, dict) and _event_reference_ids(event)
    ]
    if not candidate_events:
        return []

    window_start = datetime.now() - timedelta(days=window_days)
    window_start_iso = window_start.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    filter_params = {
        "TYPE_ID": _ACTIVITY_EMAIL_TYPE_ID,
        "COMPLETED": "Y",
        ">=DATE_CREATE": window_start_iso,
    }
    select = [
        "ID",
        "OWNER_TYPE_ID",
        "OWNER_ID",
        "RESPONSIBLE_ID",
        "SUBJECT",
        "DIRECTION",
        "SETTINGS",
    ]

    outbound_by_message_id: dict[str, dict[str, Any]] = {}
    ambiguous_message_ids: set[str] = set()

    activity_ids: list[int] = []
    for event in candidate_events:
        for activity_id in _crm_activity_reference_ids(event):
            if activity_id not in activity_ids:
                activity_ids.append(activity_id)
    for activity_id in activity_ids[:max_activities]:
        try:
            data = client.activity_list(
                filter_params={"ID": activity_id},
                select=select,
                start=0,
            )
        except BitrixConnectorError as exc:
            logger.warning(
                "rop outbound correlation id lookup failed: activity_id=%s reason=%s",
                activity_id,
                exc,
            )
            continue
        result = data.get("result")
        if not isinstance(result, list):
            logger.warning("rop outbound correlation malformed response")
            continue
        for activity in result:
            if _index_outbound_activity(
                outbound_by_message_id,
                ambiguous_message_ids,
                activity,
                max_activities,
            ):
                break

    start = 0
    try:
        for _ in range(pages_max):
            if len(outbound_by_message_id) >= max_activities:
                break
            data = client.activity_list(
                filter_params=filter_params,
                select=select,
                start=start,
            )
            result = data.get("result")
            if not isinstance(result, list):
                logger.warning("rop outbound correlation malformed response")
                return []

            for activity in result:
                if _index_outbound_activity(
                    outbound_by_message_id,
                    ambiguous_message_ids,
                    activity,
                    max_activities,
                ):
                    break

            if len(outbound_by_message_id) >= max_activities:
                break

            next_start = data.get("next")
            if next_start is None:
                break
            if not isinstance(next_start, int) or isinstance(next_start, bool):
                raise BitrixMalformedResponse(
                    "Bitrix returned malformed pagination cursor"
                )
            start = next_start
    except BitrixConnectorError as exc:
        logger.warning("rop outbound correlation connector error: %s", exc)
        return []

    if not outbound_by_message_id:
        return []

    evidence: list[dict[str, Any]] = []
    for event in candidate_events:
        refs = _event_reference_ids(event)
        matched: list[dict[str, Any]] = []
        for ref_id in refs:
            item = outbound_by_message_id.get(ref_id)
            if item is not None and item not in matched:
                matched.append(item)
        if not matched:
            continue
        if len(matched) > 1:
            continue
        bridge = dict(matched[0])
        bridge["event_id"] = _bounded_text(event.get("event_id"))
        bridge["event_instance_id"] = _bounded_text(event.get("event_instance_id"))
        bridge["bridge_exact"] = True
        evidence.append(bridge)
        if len(evidence) >= _MAX_EVIDENCE_ITEMS:
            break

    return evidence


def resolve_outbound_bridge(
    event: dict[str, Any],
    evidence_items: list[dict[str, Any]] | None,
    trusted_targets: set[tuple[str, int, int, int]] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(evidence_items, list):
        return None
    event_id = _bounded_text(event.get("event_id"))
    event_instance_id = _bounded_text(event.get("event_instance_id"))
    reference_ids = set(_event_reference_ids(event))
    candidate: dict[str, Any] | None = None
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        if item.get("event_id") != event_id:
            continue
        if event_instance_id and item.get("event_instance_id") != event_instance_id:
            continue
        if item.get("bridge_exact") is not True:
            continue
        outbound_message_id = _normalize_message_id(item.get("outbound_message_id"))
        if not outbound_message_id or outbound_message_id not in reference_ids:
            continue
        if not _positive_int(item.get("target_entity_id")):
            continue
        candidate = item
        break
    if candidate is None:
        return None

    entity_type = _bounded_text(candidate.get("target_entity_type"), 80)
    entity_type_id = candidate.get("target_entity_type_id")
    entity_id = candidate.get("target_entity_id")
    if not _positive_int(entity_type_id) or not _positive_int(entity_id):
        return {
            "authorized": False,
            "reason_code": "outbound_candidate_untrusted",
        }
    activity_responsible = candidate.get("target_responsible_user_id")
    if not isinstance(activity_responsible, int) or isinstance(
        activity_responsible, bool
    ):
        activity_responsible = None

    matched_responsibles: set[int] = set()
    if isinstance(trusted_targets, set):
        for (
            trusted_type,
            trusted_type_id,
            trusted_entity_id,
            trusted_responsible,
        ) in trusted_targets:
            if (
                trusted_type == entity_type
                and trusted_type_id == entity_type_id
                and trusted_entity_id == entity_id
                and isinstance(trusted_responsible, int)
                and not isinstance(trusted_responsible, bool)
            ):
                matched_responsibles.add(trusted_responsible)
    if len(matched_responsibles) != 1:
        return {
            "authorized": False,
            "reason_code": "outbound_candidate_untrusted",
        }
    canonical_responsible = next(iter(matched_responsibles))
    return {
        "authorized": True,
        "target": {
            "target_entity_type": entity_type,
            "target_entity_type_id": entity_type_id,
            "target_entity_id": entity_id,
            "target_responsible_user_id": canonical_responsible,
            "target_provenance": "bitrix_outbound_exact",
            "trusted_target_responsible_user_id": canonical_responsible,
            "outbound_activity_responsible_user_id": activity_responsible,
            "responsible_mismatch": (
                activity_responsible is not None
                and activity_responsible != canonical_responsible
            ),
        },
    }


def write_outbound_correlation_artifact(
    storage_dir: Path,
    run_id: str,
    items: list[dict[str, Any]],
    logger: logging.Logger,
) -> list[str]:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "run_id": run_id,
        "read_only": True,
        "evidence": items,
    }
    path = run_dir / OUTBOUND_CORRELATION_ARTIFACT
    path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "bitrix outbound correlation artifact written: run_id=%s evidence=%d",
        run_id,
        len(items),
    )
    return [str(path.relative_to(storage_dir))]
