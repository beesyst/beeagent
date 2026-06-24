from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from beeagent_module.adapters.bitrix_client import (
    ALLOWED_METHODS,
    ENTITY_TYPE_NAMES,
    BitrixConnectorError,
    BitrixReadonlyClient,
    build_bitrix_client,
)

RECONCILIATION_ARTIFACT = "bitrix_reconciliation.json"
SKIPPED_CASE_TYPES: frozenset[str] = frozenset(
    {
        "spam",
        "newsletter",
        "auto_reply",
        "out_of_office",
        "irrelevant",
    }
)


# Чек, что Bitrix reconciliation preconditions выполнены: bitrix.enabled must be true
def _validate_bitrix_reconciliation_preconditions(settings: dict) -> None:
    bitrix_cfg = settings.get("bitrix", {})
    if not bitrix_cfg.get("enabled", False):
        raise RuntimeError(
            "Bitrix reconciliation is disabled in config: "
            "set bitrix.enabled: true to run reconcile-bitrix."
        )


# Запуск Bitrix reconciliation для существующего ROP run
def run_reconciliation(
    storage_dir: Path,
    run_id: str,
    settings: dict,
    logger: logging.Logger,
) -> dict[str, Any]:
    runs_root = (storage_dir / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()

    if not run_dir.is_relative_to(runs_root):
        raise RuntimeError(
            "Invalid run_id for Bitrix reconciliation: path traversal is not allowed."
        )

    if not run_dir.exists():
        raise RuntimeError(f"Run directory not found: {run_dir}")

    normalized_events = _read_required_artifact(run_dir, "normalized_events.json")
    classified_events = _read_required_artifact(run_dir, "classified_events.json")
    _validate_bitrix_reconciliation_preconditions(settings)

    events_to_reconcile = _merge_events(normalized_events, classified_events)

    bitrix_cfg = settings.get("bitrix", {})
    recon_cfg = bitrix_cfg.get("reconciliation", {})
    candidate_limit = recon_cfg.get("candidate_limit", 20)
    window_date = recon_cfg.get("window_date", 180)
    entity_types = bitrix_cfg.get("types_entity", [1, 2, 3, 4])

    client = build_bitrix_client(settings, logger=logger)
    portal_url = client.get_portal_url()

    items: list[dict[str, Any]] = []
    aggregate = {
        "event_count": len(events_to_reconcile),
        "safe_matched_count": 0,
        "matched_count": 0,
        "weak_match_count": 0,
        "not_found_count": 0,
        "duplicate_candidate_count": 0,
        "ambiguous_count": 0,
        "skipped_count": 0,
        "connector_degraded_count": 0,
        "error_count": 0,
        "manual_review_count": 0,
    }
    warnings: list[str] = []

    for evt in events_to_reconcile:
        try:
            item = _reconcile_event(
                event=evt,
                client=client,
                entity_types=entity_types,
                candidate_limit=candidate_limit,
                window_date=window_date,
                logger=logger,
            )
        except BitrixConnectorError as exc:
            logger.warning(
                "bitrix reconciliation connector error for event_id=%s: %s",
                evt.get("event_id", "?"),
                exc,
            )
            item = _make_connector_error_item(evt, str(exc))
        except Exception as exc:
            logger.error(
                "bitrix reconciliation unexpected error for event_id=%s: %s",
                evt.get("event_id", "?"),
                exc,
                exc_info=True,
            )
            item = _make_error_item(evt, exc.__class__.__name__)

        items.append(item)

        status = item.get("bitrix_match_status", "error")
        if status.startswith("matched_"):
            aggregate["matched_count"] += 1
            if item.get("bitrix_match_quality") == "strong":
                aggregate["safe_matched_count"] += 1
        elif status == "weak_match":
            aggregate["weak_match_count"] += 1
        elif status == "not_found":
            aggregate["not_found_count"] += 1
        elif status == "duplicate_candidate":
            aggregate["duplicate_candidate_count"] += 1
        elif status == "ambiguous":
            aggregate["ambiguous_count"] += 1
        elif status == "skipped":
            aggregate["skipped_count"] += 1
        elif status == "connector_degraded":
            aggregate["connector_degraded_count"] += 1
        elif status == "error":
            aggregate["error_count"] += 1

        if item.get("needs_manual_review"):
            aggregate["manual_review_count"] += 1

    artifact = {
        "run_id": run_id,
        "status": "ok"
        if aggregate["connector_degraded_count"] == 0 and aggregate["error_count"] == 0
        else "degraded",
        "read_only": True,
        "connector": {
            "system": "bitrix",
            "portal_url": portal_url,
            "auth_source": (
                f"env:{bitrix_cfg.get('webhook_env', 'BITRIX_WEBHOOK_URL')}"
            ),
            "allowed_methods": sorted(ALLOWED_METHODS),
        },
        "aggregate": aggregate,
        "items": items,
        "warnings": warnings,
    }

    artifact_path = run_dir / RECONCILIATION_ARTIFACT
    artifact_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "bitrix reconciliation artifact written: run_id=%s path=%s "
        "event_count=%d matched=%d weak=%d not_found=%d errors=%d",
        run_id,
        artifact_path.relative_to(storage_dir),
        aggregate["event_count"],
        aggregate["matched_count"],
        aggregate["weak_match_count"],
        aggregate["not_found_count"],
        aggregate["connector_degraded_count"] + aggregate["error_count"],
    )

    return artifact


# Рид обязательного JSON artifact из run директории
def _read_required_artifact(
    run_dir: Path,
    filename: str,
) -> list[dict[str, Any]]:
    path = run_dir / filename
    if not path.exists():
        raise RuntimeError(
            f"Required artifact not found for Bitrix reconciliation: {filename}. "
            "Run ROP pipeline first (rop run)."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Required artifact is malformed JSON for Bitrix reconciliation: "
            f"{filename}: {exc}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Failed to read required Bitrix reconciliation artifact {filename}: {exc}"
        ) from exc
    if not isinstance(data, list):
        raise RuntimeError(
            f"Invalid artifact format for Bitrix reconciliation: {filename} "
            "must contain a JSON list."
        )
    return data


# Объединение normalized и classified events по event_id
def _merge_events(
    normalized: list[dict[str, Any]],
    classified: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    classified_lookup = {
        evt.get("event_id"): evt for evt in classified if evt.get("event_id")
    }
    normalized_lookup = {
        evt.get("event_id"): evt for evt in normalized if evt.get("event_id")
    }

    all_ids: list[str] = []
    seen: set[str] = set()

    for evt in classified:
        eid = evt.get("event_id")
        if eid and eid not in seen:
            all_ids.append(eid)
            seen.add(eid)

    for evt in normalized:
        eid = evt.get("event_id")
        if eid and eid not in seen:
            all_ids.append(eid)
            seen.add(eid)

    merged: list[dict[str, Any]] = []
    for eid in all_ids:
        cls = classified_lookup.get(eid, {})
        norm = normalized_lookup.get(eid, {})
        event = {**norm, **cls}
        event["event_id"] = eid
        merged.append(event)

    return merged


# Выполнение reconciliation для одного события
def _reconcile_event(
    event: dict[str, Any],
    client: BitrixReadonlyClient,
    entity_types: list[int],
    candidate_limit: int,
    window_date: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    sender = event.get("sender", "")
    subject = event.get("subject", "")
    bot_case_type = event.get("case_type", event.get("bot_case_type", ""))
    phone = event.get("phone", "")

    if bot_case_type in SKIPPED_CASE_TYPES:
        return _make_skipped_item(event, "bot_case_type_not_actionable")

    all_candidates: list[dict[str, Any]] = []
    date_from = _make_date_from_filter(event, window_date)

    for entity_type_id in entity_types:
        candidates = _search_entity(
            client=client,
            entity_type_id=entity_type_id,
            sender=sender,
            subject=subject,
            phone=phone,
            date_from=date_from,
            logger=logger,
        )
        all_candidates.extend(
            {"entity": c, "entity_type_id": entity_type_id} for c in candidates
        )

    if not all_candidates:
        return _make_not_found_item(event, "no_candidate_found")

    return _classify_candidates(
        event=event,
        candidates=all_candidates,
        candidate_limit=candidate_limit,
    )


# Поиск кандидатов по entity type
def _search_entity(
    client: BitrixReadonlyClient,
    entity_type_id: int,
    sender: str,
    subject: str,
    phone: str,
    date_from: str | None,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _normalize(item: dict[str, Any]) -> dict[str, Any]:
        mapping = {
            "id": "ID",
            "title": "TITLE",
            "stageId": "STAGE_ID",
            "statusId": "STATUS_ID",
            "assignedById": "ASSIGNED_BY_ID",
            "contactId": "CONTACT_ID",
            "companyId": "COMPANY_ID",
            "createdTime": "DATE_CREATE",
            "dateCreate": "DATE_CREATE",
        }
        normalized = dict(item)
        for camel, upper in mapping.items():
            if camel in item and upper not in item:
                normalized[upper] = item[camel]
                del normalized[camel]
        return normalized

    def _add_candidates(results: list[dict[str, Any]]) -> None:
        for item in results:
            norm = _normalize(item)
            item_id = str(norm.get("ID", ""))
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                candidates.append(norm)

    if sender and "@" in sender:
        logger.debug(
            "bitrix search by email for entity_type=%s",
            entity_type_id,
        )
        results = client.search_candidates(
            entity_type_id,
            sender,
            date_from=date_from,
        )
        _add_candidates(results)

    if phone and not candidates:
        logger.debug("bitrix search by phone for entity_type=%s", entity_type_id)
        results = client.search_candidates(
            entity_type_id,
            phone,
            date_from=date_from,
        )
        _add_candidates(results)

    # 3. Поиск по subject/title (если есть)
    if subject and not candidates:
        search_title = " ".join(subject.split()[:5])
        logger.debug("bitrix search by title for entity_type=%s", entity_type_id)
        results = client.search_candidates(
            entity_type_id,
            search_title,
            date_from=date_from,
        )
        _add_candidates(results)

    return candidates


def _make_date_from_filter(
    event: dict[str, Any],
    window_date: int,
) -> str | None:
    event_dt = _extract_event_datetime(event)
    if event_dt is None:
        return None
    return (event_dt - timedelta(days=window_date)).date().isoformat()


def _extract_event_datetime(event: dict[str, Any]) -> datetime | None:
    for key in ("event_date", "received_at", "timestamp", "created_at", "date"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def _extract_multifield_values(item: dict[str, Any], field_name: str) -> list[str]:
    field = item.get(field_name, [])
    if isinstance(field, list):
        return [
            entry.get("VALUE", "")
            for entry in field
            if isinstance(entry, dict) and isinstance(entry.get("VALUE"), str)
        ]
    if isinstance(field, str):
        return [field]
    return []


def _normalize_phone(value: str) -> str:
    return "".join(char for char in value if char.isdigit())


# Классификация кандидатов
def _classify_candidates(
    event: dict[str, Any],
    candidates: list[dict[str, Any]],
    candidate_limit: int,
) -> dict[str, Any]:
    sender = event.get("sender", "")
    phone = event.get("phone", "")
    subject = event.get("subject", "")
    normalized_phone = _normalize_phone(phone) if isinstance(phone, str) else ""

    by_type: dict[int, list[dict[str, Any]]] = {}
    for c in candidates[:candidate_limit]:
        et = c.get("entity_type_id", 0)
        if et not in by_type:
            by_type[et] = []
        by_type[et].append(c["entity"])

    exact_matches: list[tuple[int, dict[str, Any], str]] = []
    weak_matches: list[tuple[int, dict[str, Any]]] = []

    for et, items in by_type.items():
        for item in items:
            title = item.get("TITLE", "")

            if sender and "@" in sender:
                emails = _extract_multifield_values(item, "EMAIL")
                if sender.lower() in [e.lower() for e in emails if e]:
                    exact_matches.append((et, item, "sender_email_exact"))
                    continue

            if normalized_phone:
                phones = _extract_multifield_values(item, "PHONE")
                normalized_phones = [
                    _normalize_phone(value) for value in phones if value
                ]
                if normalized_phone in normalized_phones:
                    exact_matches.append((et, item, "phone_exact"))
                    continue

            if subject and title:
                if subject.lower() in title.lower() or title.lower() in subject.lower():
                    weak_matches.append((et, item))
                    continue

            weak_matches.append((et, item))

    candidate_count = len(exact_matches) + len(weak_matches)

    if exact_matches:
        if len(exact_matches) == 1:
            et, item, match_reason = exact_matches[0]
            return _make_matched_item(
                event,
                et,
                item,
                match_reason,
                0.95,
                "strong",
                candidate_count,
            )
        else:
            return _make_duplicate_item(
                event,
                [(et, item) for et, item, _reason in exact_matches],
                "multiple_exact_matches",
                candidate_count,
            )

    if weak_matches:
        if len(weak_matches) == 1:
            et, item = weak_matches[0]
            return _make_weak_match_item(
                event,
                et,
                item,
                "title_subject_only",
                candidate_count,
            )
        else:
            return _make_ambiguous_item(
                event,
                weak_matches,
                "multiple_weak_candidates",
                candidate_count,
            )

    return _make_not_found_item(event, "no_candidate_found", 0)


# Создание reconciliation item для статуса matched
def _make_matched_item(
    event: dict[str, Any],
    entity_type_id: int,
    entity: dict[str, Any],
    match_reason: str,
    confidence: float,
    match_quality: str = "strong",
    candidate_count: int = 1,
) -> dict[str, Any]:
    entity_type_name = ENTITY_TYPE_NAMES.get(entity_type_id, "")
    quality_is_strong = match_quality == "strong"
    needs_manual = not quality_is_strong or confidence < 0.8

    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": f"matched_{entity_type_name}",
        "bitrix_match_quality": match_quality,
        "bitrix_entity_type": entity_type_name,
        "bitrix_entity_type_id": entity_type_id,
        "bitrix_entity_id": _int_or_none(entity.get("ID")),
        "bitrix_title": entity.get("TITLE", ""),
        "bitrix_stage": entity.get("STAGE_ID", ""),
        "bitrix_responsible_id": _int_or_none(entity.get("ASSIGNED_BY_ID")),
        "bitrix_contact_id": _int_or_none(entity.get("CONTACT_ID")),
        "bitrix_company_id": _int_or_none(entity.get("COMPANY_ID")),
        "bitrix_match_reason": match_reason,
        "bitrix_confidence": confidence,
        "needs_manual_review": needs_manual,
        "safe_to_use_as_target": quality_is_strong,
        "candidate_count": candidate_count,
        "candidate_summary": (
            f"{candidate_count} candidate(s), quality={match_quality}, "
            f"best={entity.get('TITLE', '')} (ID={entity.get('ID', '?')})"
        ),
        "reconciliation_reason": (
            f"Bitrix {entity_type_name} found: "
            f"{entity.get('TITLE', '')} (ID={entity.get('ID', '?')})"
        ),
    }


# Создание reconciliation item для статуса not_found
def _make_not_found_item(
    event: dict[str, Any],
    reason: str,
    candidate_count: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "not_found",
        "bitrix_match_quality": "not_found",
        "bitrix_entity_type": "",
        "bitrix_entity_type_id": None,
        "bitrix_entity_id": None,
        "bitrix_title": "",
        "bitrix_stage": "",
        "bitrix_responsible_id": None,
        "bitrix_contact_id": None,
        "bitrix_company_id": None,
        "bitrix_match_reason": reason,
        "bitrix_confidence": 0.0,
        "needs_manual_review": True,
        "safe_to_use_as_target": False,
        "candidate_count": candidate_count,
        "candidate_summary": "No Bitrix candidate found; connector healthy.",
        "reconciliation_reason": (
            "No Bitrix candidate was found for this classified event."
        ),
    }


# Создание reconciliation item для статуса skipped
def _make_skipped_item(
    event: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "skipped",
        "bitrix_match_quality": "skipped",
        "bitrix_entity_type": "",
        "bitrix_entity_type_id": None,
        "bitrix_entity_id": None,
        "bitrix_title": "",
        "bitrix_stage": "",
        "bitrix_responsible_id": None,
        "bitrix_contact_id": None,
        "bitrix_company_id": None,
        "bitrix_match_reason": reason,
        "bitrix_confidence": 0.0,
        "needs_manual_review": False,
        "safe_to_use_as_target": False,
        "candidate_count": 0,
        "candidate_summary": "Event skipped; no reconciliation attempted.",
        "reconciliation_reason": f"Event skipped: {reason}.",
    }


# Создание reconciliation item для статуса duplicate_candidate
def _make_duplicate_item(
    event: dict[str, Any],
    candidates: list[tuple[int, dict[str, Any]]],
    reason: str,
    candidate_count: int = 0,
) -> dict[str, Any]:
    best = candidates[0]
    et, entity = best
    entity_type_name = ENTITY_TYPE_NAMES.get(et, "")

    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "duplicate_candidate",
        "bitrix_match_quality": "duplicate",
        "bitrix_entity_type": entity_type_name,
        "bitrix_entity_type_id": et,
        "bitrix_entity_id": _int_or_none(entity.get("ID")),
        "bitrix_title": entity.get("TITLE", ""),
        "bitrix_stage": entity.get("STAGE_ID", ""),
        "bitrix_responsible_id": _int_or_none(entity.get("ASSIGNED_BY_ID")),
        "bitrix_contact_id": _int_or_none(entity.get("CONTACT_ID")),
        "bitrix_company_id": _int_or_none(entity.get("COMPANY_ID")),
        "bitrix_match_reason": reason,
        "bitrix_confidence": 0.5,
        "needs_manual_review": True,
        "safe_to_use_as_target": False,
        "candidate_count": candidate_count or len(candidates),
        "candidate_summary": (
            f"{len(candidates)} candidate(s), duplicate, "
            f"best={entity.get('TITLE', '')} (ID={entity.get('ID', '?')})"
        ),
        "reconciliation_reason": (
            f"Multiple Bitrix candidates found ({len(candidates)}). "
            f"Best: {entity.get('TITLE', '')} (ID={entity.get('ID', '?')})."
        ),
    }


# Создание reconciliation item для статуса ambiguous
def _make_ambiguous_item(
    event: dict[str, Any],
    candidates: list[tuple[int, dict[str, Any]]],
    reason: str,
    candidate_count: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "ambiguous",
        "bitrix_match_quality": "ambiguous",
        "bitrix_entity_type": "",
        "bitrix_entity_type_id": None,
        "bitrix_entity_id": None,
        "bitrix_title": "",
        "bitrix_stage": "",
        "bitrix_responsible_id": None,
        "bitrix_contact_id": None,
        "bitrix_company_id": None,
        "bitrix_match_reason": reason,
        "bitrix_confidence": 0.0,
        "needs_manual_review": True,
        "safe_to_use_as_target": False,
        "candidate_count": candidate_count or len(candidates),
        "candidate_summary": (
            f"{len(candidates)} candidate(s), ambiguous, manual review required"
        ),
        "reconciliation_reason": (
            f"Too many ambiguous Bitrix candidates ({len(candidates)}). "
            "Manual review required."
        ),
    }


# Создание reconciliation item для статуса weak_match
def _make_weak_match_item(
    event: dict[str, Any],
    entity_type_id: int,
    entity: dict[str, Any],
    match_reason: str,
    candidate_count: int = 1,
) -> dict[str, Any]:
    entity_type_name = ENTITY_TYPE_NAMES.get(entity_type_id, "")
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "weak_match",
        "bitrix_match_quality": "weak",
        "bitrix_entity_type": entity_type_name,
        "bitrix_entity_type_id": entity_type_id,
        "bitrix_entity_id": _int_or_none(entity.get("ID")),
        "bitrix_title": entity.get("TITLE", ""),
        "bitrix_stage": entity.get("STAGE_ID", ""),
        "bitrix_responsible_id": _int_or_none(entity.get("ASSIGNED_BY_ID")),
        "bitrix_contact_id": _int_or_none(entity.get("CONTACT_ID")),
        "bitrix_company_id": _int_or_none(entity.get("COMPANY_ID")),
        "bitrix_match_reason": match_reason,
        "bitrix_confidence": 0.3,
        "needs_manual_review": True,
        "safe_to_use_as_target": False,
        "candidate_count": candidate_count,
        "candidate_summary": (
            f"{candidate_count} candidate(s), weak match (title/subject only), "
            f"best={entity.get('TITLE', '')} (ID={entity.get('ID', '?')})"
        ),
        "reconciliation_reason": (
            f"Weak Bitrix match: {entity_type_name} "
            f"{entity.get('TITLE', '')} (ID={entity.get('ID', '?')}) "
            "based on title/subject only. Manual verification required."
        ),
    }


# Создание reconciliation item для статуса connector_degraded
def _make_connector_error_item(
    event: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    """Создать reconciliation item со статусом connector_degraded."""
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "connector_degraded",
        "bitrix_match_quality": "connector_degraded",
        "bitrix_entity_type": "",
        "bitrix_entity_type_id": None,
        "bitrix_entity_id": None,
        "bitrix_title": "",
        "bitrix_stage": "",
        "bitrix_responsible_id": None,
        "bitrix_contact_id": None,
        "bitrix_company_id": None,
        "bitrix_match_reason": "connector_error",
        "bitrix_confidence": 0.0,
        "needs_manual_review": True,
        "safe_to_use_as_target": False,
        "candidate_count": 0,
        "candidate_summary": "Connector degraded; reconciliation not attempted.",
        "reconciliation_reason": f"Bitrix connector error: {error}",
    }


# Создание reconciliation item для неожиданной ошибки application layer
def _make_error_item(
    event: dict[str, Any],
    error_type: str,
) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "error",
        "bitrix_match_quality": "error",
        "bitrix_entity_type": "",
        "bitrix_entity_type_id": None,
        "bitrix_entity_id": None,
        "bitrix_title": "",
        "bitrix_stage": "",
        "bitrix_responsible_id": None,
        "bitrix_contact_id": None,
        "bitrix_company_id": None,
        "bitrix_match_reason": "reconciliation_error",
        "bitrix_confidence": 0.0,
        "needs_manual_review": True,
        "safe_to_use_as_target": False,
        "candidate_count": 0,
        "candidate_summary": "Reconciliation error; no match data available.",
        "reconciliation_reason": (
            f"Unexpected reconciliation error: {error_type}. Manual review required."
        ),
    }


# Безопасное приведение к int или None
def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError, TypeError:
        return None
