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
from beeagent_module.core.input_source import effective_rop_sender_email

RECONCILIATION_ARTIFACT = "bitrix_reconciliation.json"
SKIPPED_CASE_TYPES: frozenset[str] = frozenset(
    {
        "spam",
        "newsletter",
        "auto_reply",
        "out_of_office",
    }
)


def _validate_bitrix_reconciliation_preconditions(settings: dict) -> None:
    bitrix_cfg = settings.get("bitrix", {})
    if not bitrix_cfg.get("enabled", False):
        raise RuntimeError(
            "Bitrix reconciliation is disabled in config: "
            "set bitrix.enabled: true to run reconcile-bitrix."
        )


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
        "identity_only_no_target_count": 0,
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

        items.append(_with_event_instance_id(item, evt))

        status = item.get("bitrix_match_status", "error")
        if status.startswith("matched_"):
            aggregate["matched_count"] += 1
            if item.get("safe_to_use_as_target") is True:
                aggregate["safe_matched_count"] += 1
        elif status == "weak_match":
            aggregate["weak_match_count"] += 1
        elif status == "not_found":
            aggregate["not_found_count"] += 1
        elif status == "duplicate_candidate":
            aggregate["duplicate_candidate_count"] += 1
        elif status == "ambiguous":
            aggregate["ambiguous_count"] += 1
        elif status == "identity_only_no_target":
            aggregate["identity_only_no_target_count"] += 1
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


def _merge_events(
    normalized: list[dict[str, Any]],
    classified: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_by_id: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    classified_by_id: dict[str, list[dict[str, Any]]] = {}
    for index, event in enumerate(normalized):
        event_id = event.get("event_id")
        if event_id:
            normalized_by_id.setdefault(event_id, []).append((index, event))
    for event in classified:
        event_id = event.get("event_id")
        if event_id:
            classified_by_id.setdefault(event_id, []).append(event)

    used_normalized: set[int] = set()
    merged: list[dict[str, Any]] = []
    for classified_event in classified:
        event_id = classified_event.get("event_id")
        if not event_id:
            continue
        candidates = [
            pair
            for pair in normalized_by_id.get(event_id, [])
            if pair[0] not in used_normalized
        ]
        instance_id = _event_instance_id(classified_event)
        exact = [
            pair
            for pair in candidates
            if instance_id is not None and _event_instance_id(pair[1]) == instance_id
        ]
        if len(exact) == 1:
            index, normalized_event = exact[0]
            used_normalized.add(index)
            merged.append({**normalized_event, **classified_event})
            continue
        if (
            len(candidates) == 1
            and len(classified_by_id.get(event_id, [])) == 1
        ):
            index, normalized_event = candidates[0]
            used_normalized.add(index)
            merged.append({**normalized_event, **classified_event})
            continue
        merged.append(dict(classified_event))

    for index, normalized_event in enumerate(normalized):
        if index not in used_normalized and normalized_event.get("event_id"):
            merged.append(dict(normalized_event))
    return merged


def _event_instance_id(event: dict[str, Any]) -> str | None:
    value = event.get("event_instance_id")
    return value if isinstance(value, str) and value else None


def _with_event_instance_id(
    item: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    instance_id = _event_instance_id(event)
    if instance_id is not None:
        item["event_instance_id"] = instance_id
    return item


def _reconcile_event(
    event: dict[str, Any],
    client: BitrixReadonlyClient,
    entity_types: list[int],
    candidate_limit: int,
    window_date: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    reconciliation_event = dict(event)
    sender = effective_rop_sender_email(event)
    reconciliation_event["sender"] = sender
    subject = event.get("subject", "")
    bot_case_type = event.get("case_type", event.get("bot_case_type", ""))
    phone = event.get("phone", "")

    if bot_case_type in SKIPPED_CASE_TYPES:
        return _make_skipped_item(reconciliation_event, "bot_case_type_not_actionable")

    all_candidates: list[dict[str, Any]] = []
    date_from = _make_date_from_filter(event, window_date)

    related_deal, identity_evidence = _resolve_related_deal(
        event=reconciliation_event,
        client=client,
        entity_types=entity_types,
        logger=logger,
    )
    if related_deal is not None:
        if (
            related_deal.get("bitrix_match_status") == "matched_deal"
            and 1 in entity_types
        ):
            exact_leads = _search_exact_communication_entity(
                client=client,
                entity_type_id=1,
                sender=sender,
                phone=phone,
                logger=logger,
                date_from=date_from,
            )
            if exact_leads:
                ambiguous_candidates = [
                    (1, lead)
                    for _entity_type_id, lead, _evidence in exact_leads
                ]
                ambiguous_candidates.append(
                    (
                        2,
                        {
                            "ID": related_deal.get("bitrix_entity_id"),
                            "TITLE": related_deal.get("bitrix_title", ""),
                        },
                    )
                )
                return _make_ambiguous_item(
                    reconciliation_event,
                    ambiguous_candidates,
                    "exact_lead_and_related_deal",
                    len(ambiguous_candidates),
                )
        return related_deal

    if identity_evidence is not None and 1 in entity_types:
        exact_leads = _search_exact_communication_entity(
            client=client,
            entity_type_id=1,
            sender=sender,
            phone=phone,
            logger=logger,
            date_from=date_from,
        )
        if len(exact_leads) == 1:
            _entity_type_id, lead, match_reason = exact_leads[0]
            return _make_matched_item(
                reconciliation_event,
                1,
                lead,
                match_reason,
                0.95,
                "strong",
            )
        if len(exact_leads) > 1:
            return _make_duplicate_item(
                reconciliation_event,
                [(1, lead) for _entity_type_id, lead, _reason in exact_leads],
                "multiple_exact_matches",
                len(exact_leads),
            )

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
        if identity_evidence is not None and 1 in entity_types:
            return _make_identity_only_no_target_item(
                reconciliation_event, identity_evidence
            )
        return _make_not_found_item(reconciliation_event, "no_candidate_found")

    classified = _classify_candidates(
        event=reconciliation_event,
        candidates=all_candidates,
        candidate_limit=candidate_limit,
    )
    if (
        identity_evidence is not None
        and 1 in entity_types
        and classified.get("bitrix_match_status")
        in {"matched_contact", "matched_company"}
        and classified.get("bitrix_match_quality") == "strong"
        and classified.get("candidate_count") == 1
    ):
        return _make_identity_only_no_target_item(
            reconciliation_event, identity_evidence
        )
    return classified


def _resolve_related_deal(
    event: dict[str, Any],
    client: BitrixReadonlyClient,
    entity_types: list[int],
    logger: logging.Logger,
) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any], str] | None]:
    if 2 not in entity_types:
        return None, None

    sender = event.get("sender", "")
    phone = event.get("phone", "")
    if not ((isinstance(sender, str) and "@" in sender) or phone):
        return None, None

    related_entities: list[tuple[int, dict[str, Any], str]] = []
    for entity_type_id in (3, 4):
        if entity_type_id not in entity_types:
            continue
        candidates = _search_exact_communication_entity(
            client=client,
            entity_type_id=entity_type_id,
            sender=sender,
            phone=phone,
            logger=logger,
        )
        related_entities.extend(candidates)

    if not related_entities:
        return None, None

    deals_by_id: dict[int, tuple[dict[str, Any], str]] = {}
    for entity_type_id, entity, evidence in related_entities:
        entity_id = _int_or_none(entity.get("ID"))
        if entity_id is None:
            raise BitrixConnectorError(
                "Bitrix returned related entity without valid ID"
            )
        for deal in client.search_related_deals(entity_type_id, entity_id):
            normalized_deal = _normalize_entity(deal)
            deal_id = _int_or_none(normalized_deal.get("ID"))
            if deal_id is None:
                raise BitrixConnectorError(
                    "Bitrix returned related deal without valid ID"
                )
            deals_by_id.setdefault(
                deal_id,
                (
                    normalized_deal,
                    f"related_{ENTITY_TYPE_NAMES[entity_type_id]}_{evidence}",
                ),
            )

    deals = list(deals_by_id.values())
    if not deals:
        if len(related_entities) == 1:
            return None, related_entities[0]
        return None, None
    if len(deals) == 1:
        deal, match_reason = deals[0]
        return (
            _make_matched_item(
                event,
                2,
                deal,
                match_reason,
                0.95,
                "strong",
            ),
            None,
        )
    return (
        _make_ambiguous_item(
            event,
            [(2, deal) for deal, _reason in deals],
            "multiple_related_deals",
        ),
        None,
    )


def _search_exact_communication_entity(
    client: BitrixReadonlyClient,
    entity_type_id: int,
    sender: str,
    phone: str,
    logger: logging.Logger,
    date_from: str | None = None,
) -> list[tuple[int, dict[str, Any], str]]:
    results: list[tuple[int, dict[str, Any], str]] = []
    seen_ids: set[int] = set()

    def add_exact(items: list[dict[str, Any]], evidence: str) -> None:
        for item in items:
            normalized = _normalize_entity(item)
            item_id = _int_or_none(normalized.get("ID"))
            if item_id is None or item_id in seen_ids:
                continue
            if evidence == "sender_email_exact":
                values = _extract_multifield_values(normalized, "EMAIL")
                if sender.lower() not in {value.lower() for value in values if value}:
                    continue
            else:
                values = _extract_multifield_values(normalized, "PHONE")
                if _normalize_phone(phone) not in {
                    _normalize_phone(value) for value in values if value
                }:
                    continue
            seen_ids.add(item_id)
            results.append((entity_type_id, normalized, evidence))

    if isinstance(sender, str) and "@" in sender:
        logger.debug(
            "bitrix exact communication search for entity_type=%s",
            entity_type_id,
        )
        add_exact(
            client.search_candidates(entity_type_id, sender, date_from=date_from),
            "sender_email_exact",
        )
    if phone and not results:
        logger.debug(
            "bitrix exact communication search for entity_type=%s",
            entity_type_id,
        )
        add_exact(
            client.search_candidates(entity_type_id, phone, date_from=date_from),
            "phone_exact",
        )
    return results


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

    def _add_candidates(results: list[dict[str, Any]]) -> None:
        for item in results:
            norm = _normalize_entity(item)
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


def _normalize_entity(item: dict[str, Any]) -> dict[str, Any]:
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
    needs_manual = True

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
        "safe_to_use_as_target": False,
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


def _make_identity_only_no_target_item(
    event: dict[str, Any],
    identity_evidence: tuple[int, dict[str, Any], str],
) -> dict[str, Any]:
    entity_type_id, entity, _match_reason = identity_evidence
    return {
        "event_id": event.get("event_id", ""),
        "source_id": event.get("source_id", ""),
        "sender": event.get("sender", ""),
        "subject": event.get("subject", ""),
        "bot_case_type": event.get("case_type", event.get("bot_case_type", "")),
        "bitrix_match_status": "identity_only_no_target",
        "bitrix_match_quality": "identity_only",
        "bitrix_entity_type": "",
        "bitrix_entity_type_id": None,
        "bitrix_entity_id": None,
        "bitrix_title": "",
        "bitrix_stage": "",
        "bitrix_responsible_id": None,
        "bitrix_contact_id": None,
        "bitrix_company_id": None,
        "identity_entity_type": ENTITY_TYPE_NAMES.get(entity_type_id, ""),
        "identity_entity_id": _int_or_none(entity.get("ID")),
        "bitrix_match_reason": "exact_identity_no_executable_target",
        "bitrix_confidence": 0.95,
        "needs_manual_review": False,
        "safe_to_use_as_target": False,
        "suitable_target_search": "completed_no_target",
        "candidate_count": 1,
        "candidate_summary": "Exact Contact/Company identity found; no executable Lead/Deal target.",
        "reconciliation_reason": (
            "Exact Contact/Company identity found; Lead and related Deal searches "
            "completed without an executable target."
        ),
    }


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


def _make_connector_error_item(
    event: dict[str, Any],
    error: str,
) -> dict[str, Any]:
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


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError, TypeError:
        return None
