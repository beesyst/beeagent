from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from email.utils import getaddresses
from pathlib import Path
from typing import Any, Callable

from beeagent_module.adapters.bitrix_client import (
    BitrixConnectorError,
    BitrixMalformedResponse,
    build_bitrix_client,
)

ROP_RECIPIENT_ROUTING_ARTIFACT = "rop_recipient_routing.json"

_MAX_ADDRESS_LENGTH = 320
_MAX_ORIGINAL_RECIPIENT_LENGTH = 500
_DIRECTORY_SELECT_FIELDS = (
    "ID",
    "EMAIL",
    "ACTIVE",
    "NAME",
    "LAST_NAME",
    "WORK_POSITION",
)


def _bounded_email(value: str) -> str:
    return value.strip().lower()[: _MAX_ADDRESS_LENGTH]


def _extract_email_addresses(value: Any) -> list[str]:
    raw_values: list[str] = []
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = [item for item in value if isinstance(item, str)]
    if not raw_values:
        return []

    candidates: list[str] = []
    for raw in raw_values:
        if not raw or not raw.strip():
            continue
        if len(raw) > _MAX_ORIGINAL_RECIPIENT_LENGTH * 4:
            raw = raw[: _MAX_ORIGINAL_RECIPIENT_LENGTH * 4]
        try:
            pairs = getaddresses([raw])
        except (TypeError, ValueError, IndexError):
            continue
        for _name, addr in pairs:
            if not addr or "@" not in addr:
                continue
            normalized = _bounded_email(addr)
            if normalized and normalized not in candidates:
                candidates.append(normalized)
    return candidates


def _source_recipient_map(settings: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    input_sources = settings.get("rop", {}).get("sources", [])
    if not isinstance(input_sources, list):
        return result
    for source in input_sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            continue
        routing = source.get("routing")
        if not isinstance(routing, dict):
            continue
        email_recipient = routing.get("email_recipient")
        if isinstance(email_recipient, str) and email_recipient.strip():
            result[source_id] = email_recipient
    return result


def _resolve_event_recipient(
    event: dict[str, Any],
    source_recipient_email: str,
) -> dict[str, Any]:
    original_recipient = _extract_email_addresses(event.get("original_recipient"))
    if original_recipient:
        return _recipient_result(
            candidates=original_recipient,
            evidence_source="original_recipient",
        )

    to_candidates = _extract_email_addresses(event.get("to"))
    if to_candidates:
        return _recipient_result(
            candidates=to_candidates,
            evidence_source="to",
        )

    fallback_candidates = _extract_email_addresses(source_recipient_email)
    if fallback_candidates:
        return _recipient_result(
            candidates=fallback_candidates,
            evidence_source="source_recipient",
        )

    return {
        "recipient": "",
        "recipient_candidates": [],
        "recipient_evidence_source": "",
        "recipient_status": "unresolved",
        "recipient_reason": "no_recipient_evidence",
    }


def _recipient_result(
    candidates: list[str],
    evidence_source: str,
) -> dict[str, Any]:
    if len(candidates) == 1:
        return {
            "recipient": candidates[0],
            "recipient_candidates": candidates,
            "recipient_evidence_source": evidence_source,
            "recipient_status": "resolved",
            "recipient_reason": None,
        }
    return {
        "recipient": "",
        "recipient_candidates": candidates,
        "recipient_evidence_source": evidence_source,
        "recipient_status": "ambiguous",
        "recipient_reason": f"multiple_{evidence_source}_recipients",
    }


def _load_user_pages(
    client: Any,
    page_size: int,
    pages_max: int,
) -> list[dict[str, Any]]:
    users: list[dict[str, Any]] = []
    start = 0
    for _ in range(pages_max):
        data = client.list_users(
            select=list(_DIRECTORY_SELECT_FIELDS),
            start=start,
            limit=page_size,
        )
        if not isinstance(data, dict):
            raise BitrixMalformedResponse(
                "Bitrix returned malformed user.get result envelope"
            )
        page = data.get("result")
        if not isinstance(page, list):
            raise BitrixMalformedResponse("Bitrix returned malformed user.get result")
        users.extend(item for item in page if isinstance(item, dict))
        next_start = data.get("next")
        if next_start is None:
            break
        if not isinstance(next_start, int):
            raise BitrixMalformedResponse(
                "Bitrix returned malformed user.get pagination cursor"
            )
        start = next_start
    else:
        raise BitrixMalformedResponse(
            "Bitrix user directory pagination limit reached before completion"
        )
    return users


def _is_active_user(user: dict[str, Any]) -> bool:
    active = user.get("ACTIVE")
    if isinstance(active, bool):
        return active
    return str(active or "").upper() == "Y"


def _build_active_user_directory(
    users: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    directory: dict[str, list[dict[str, Any]]] = {}
    for user in users:
        if not isinstance(user, dict):
            continue
        if not _is_active_user(user):
            continue
        email = _bounded_email(str(user.get("EMAIL", "") or ""))
        if not email:
            continue
        directory.setdefault(email, []).append(user)
    return directory


def _resolve_responsible(
    recipient_email: str,
    directory: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    matches = directory.get(recipient_email, [])
    if not matches:
        return {
            "status": "not_found",
            "user_id": None,
            "name": "",
            "email": "",
            "reason": "no_active_user_for_email",
        }
    if len(matches) > 1:
        return {
            "status": "ambiguous",
            "user_id": None,
            "name": "",
            "email": "",
            "reason": "multiple_active_users_for_email",
        }
    user = matches[0]
    user_id = _int_or_none(user.get("ID"))
    if user_id is None:
        return _connector_degraded_responsible()
    name_parts = [
        str(user.get("NAME", "") or ""),
        str(user.get("LAST_NAME", "") or ""),
    ]
    return {
        "status": "matched",
        "user_id": user_id,
        "name": " ".join(part for part in name_parts if part),
        "email": recipient_email,
        "reason": None,
    }


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _not_attempted_responsible(reason: str) -> dict[str, Any]:
    return {
        "status": "not_attempted",
        "user_id": None,
        "name": "",
        "email": "",
        "reason": reason,
    }


def _connector_degraded_responsible() -> dict[str, Any]:
    return {
        "status": "connector_degraded",
        "user_id": None,
        "name": "",
        "email": "",
        "reason": "bitrix_user_directory_unavailable",
    }


def build_recipient_routing_artifact(
    storage_dir: Path,
    run_id: str,
    settings: dict[str, Any],
    logger: logging.Logger,
    bitrix_client_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()

    if not run_dir.is_relative_to(runs_root):
        raise ValueError("Invalid run_id: path traversal is not allowed.")

    if not run_dir.exists():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")

    normalized_path = run_dir / "normalized_events.json"
    if not normalized_path.exists():
        raise FileNotFoundError(
            "normalized_events.json not found; recipient routing requires it"
        )
    try:
        raw_events = json.loads(normalized_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("normalized_events.json is malformed") from exc
    if not isinstance(raw_events, list):
        raise ValueError("normalized_events.json must be a list")

    source_recipients = _source_recipient_map(settings)

    items: list[dict[str, Any]] = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id", ""))
        event_instance_id = str(event.get("event_instance_id", ""))
        source_id = str(event.get("source_id", ""))
        recipient = _resolve_event_recipient(
            event=event,
            source_recipient_email=source_recipients.get(source_id, ""),
        )
        items.append(
            {
                "event_id": event_id,
                "event_instance_id": event_instance_id,
                "source_id": source_id,
                "source_role": str(event.get("source_role", "")),
                "source_display_name": str(event.get("source_display_name", "")),
                "client_id": str(event.get("client_id", "")),
                "to": [
                    address[: _MAX_ADDRESS_LENGTH]
                    for address in _extract_email_addresses(event.get("to"))
                ],
                "cc": [
                    address[: _MAX_ADDRESS_LENGTH]
                    for address in _extract_email_addresses(event.get("cc"))
                ],
                "original_recipient": str(event.get("original_recipient", ""))[
                    : _MAX_ORIGINAL_RECIPIENT_LENGTH
                ],
                **recipient,
                "responsible": _not_attempted_responsible("bitrix_disabled"),
            }
        )

    bitrix_cfg = settings.get("bitrix", {})
    bitrix_enabled = bitrix_cfg.get("enabled") is True if isinstance(bitrix_cfg, dict) else False
    page_size = bitrix_cfg.get("page_size", 50) if isinstance(bitrix_cfg, dict) else 50
    pages_max = bitrix_cfg.get("pages_max", 3) if isinstance(bitrix_cfg, dict) else 3

    directory_status: dict[str, Any] = {
        "status": "not_attempted",
        "reason": "bitrix_disabled",
        "user_count": 0,
        "active_user_count": 0,
    }

    if bitrix_enabled:
        try:
            client = (
                bitrix_client_factory(settings)
                if bitrix_client_factory is not None
                else build_bitrix_client(settings, logger=logger)
            )
            users = _load_user_pages(
                client=client,
                page_size=int(page_size),
                pages_max=int(pages_max),
            )
            directory = _build_active_user_directory(users)
            directory_status = {
                "status": "loaded",
                "reason": None,
                "user_count": len(users),
                "active_user_count": len(directory),
            }
            for item in items:
                if item["recipient_status"] == "resolved":
                    item["responsible"] = _resolve_responsible(
                        recipient_email=item["recipient"],
                        directory=directory,
                    )
                elif item["recipient_status"] == "ambiguous":
                    item["responsible"] = _not_attempted_responsible(
                        "recipient_ambiguous"
                    )
                else:
                    item["responsible"] = _not_attempted_responsible(
                        "recipient_unresolved"
                    )
        except BitrixConnectorError as exc:
            directory_status = {
                "status": "connector_degraded",
                "reason": str(exc),
                "user_count": 0,
                "active_user_count": 0,
            }
            for item in items:
                item["responsible"] = _connector_degraded_responsible()
            logger.warning(
                "rop recipient routing: bitrix user directory degraded: run_id=%s reason=%s",
                run_id,
                exc,
            )

    aggregate = _build_routing_aggregate(items, directory_status)

    artifact: dict[str, Any] = {
        "run_id": run_id,
        "status": (
            "ok"
            if directory_status["status"] in ("loaded", "not_attempted")
            else "degraded"
        ),
        "read_only": True,
        "draft_only": True,
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "directory": directory_status,
        "aggregate": aggregate,
        "items": items,
    }

    artifact_path = run_dir / ROP_RECIPIENT_ROUTING_ARTIFACT
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "ROP recipient routing artifact written: run_id=%s path=%s items=%d directory=%s",
        run_id,
        str(artifact_path.relative_to(storage_dir)),
        len(items),
        directory_status["status"],
    )

    return artifact


def _build_routing_aggregate(
    items: list[dict[str, Any]],
    directory_status: dict[str, Any],
) -> dict[str, Any]:
    aggregate: dict[str, int] = {
        "event_count": len(items),
        "recipient_resolved_count": 0,
        "recipient_ambiguous_count": 0,
        "recipient_unresolved_count": 0,
        "responsible_matched_count": 0,
        "responsible_not_found_count": 0,
        "responsible_ambiguous_count": 0,
        "responsible_connector_degraded_count": 0,
        "responsible_not_attempted_count": 0,
    }
    for item in items:
        recipient_status = item.get("recipient_status", "")
        if recipient_status == "resolved":
            aggregate["recipient_resolved_count"] += 1
        elif recipient_status == "ambiguous":
            aggregate["recipient_ambiguous_count"] += 1
        else:
            aggregate["recipient_unresolved_count"] += 1
        responsible_status = item.get("responsible", {}).get("status", "")
        key = {
            "matched": "responsible_matched_count",
            "not_found": "responsible_not_found_count",
            "ambiguous": "responsible_ambiguous_count",
            "connector_degraded": "responsible_connector_degraded_count",
            "not_attempted": "responsible_not_attempted_count",
        }.get(responsible_status)
        if key:
            aggregate[key] += 1
    return aggregate
