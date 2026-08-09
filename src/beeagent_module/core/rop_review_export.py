from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

REVIEW_BODY_SHORT_MAX_CHARS = 500


class RopReviewExportError(RuntimeError):
    pass


def export_review_tsv_for_run(
    storage_dir: Path,
    run_id: str,
    logger: logging.Logger,
) -> str:
    normalized_path = storage_dir / "runs" / run_id / "normalized_events.json"
    classified_path = storage_dir / "runs" / run_id / "classified_events.json"
    tsv_output_path = storage_dir / "runs" / run_id / "rop_review_table.tsv"

    if not normalized_path.exists():
        raise RopReviewExportError(
            f"normalized_events.json not found for run_id={run_id}"
        )
    if not classified_path.exists():
        raise RopReviewExportError(
            f"classified_events.json not found for run_id={run_id}"
        )

    try:
        with normalized_path.open("r", encoding="utf-8") as f:
            normalized_events = json.load(f)
        with classified_path.open("r", encoding="utf-8") as f:
            classified_events = json.load(f)
    except json.JSONDecodeError as exc:
        raise RopReviewExportError(f"Failed to parse JSON artifacts: {exc}") from exc

    reconciliation_path = storage_dir / "runs" / run_id / "bitrix_reconciliation.json"
    reconciliation_data = None
    if reconciliation_path.exists():
        try:
            reconciliation_data = json.loads(
                reconciliation_path.read_text(encoding="utf-8")
            )
            logger.debug(
                "ROP CLI: bitrix reconciliation artifact found for TSV enrichment: %s",
                reconciliation_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "ROP CLI: failed to read bitrix reconciliation artifact: %s", exc
            )

    action_drafts_path = storage_dir / "runs" / run_id / "rop_action_drafts.json"
    action_drafts_data = None
    if action_drafts_path.exists():
        try:
            action_drafts_data = json.loads(
                action_drafts_path.read_text(encoding="utf-8")
            )
            logger.debug(
                "ROP CLI: action drafts artifact found for TSV enrichment: %s",
                action_drafts_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("ROP CLI: failed to read action drafts artifact: %s", exc)

    adjudicator_results_path = (
        storage_dir / "runs" / run_id / "rop_ai_adjudicator_results.json"
    )
    adjudicator_results_data = None
    if adjudicator_results_path.exists():
        try:
            adjudicator_results_data = json.loads(
                adjudicator_results_path.read_text(encoding="utf-8")
            )
            logger.debug(
                "ROP CLI: adjudicator results artifact found for TSV enrichment: %s",
                adjudicator_results_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "ROP CLI: failed to read adjudicator results artifact: %s", exc
            )

    tsv_rows = _build_review_tsv_rows(
        normalized_events,
        classified_events,
        reconciliation_data=reconciliation_data,
        action_drafts_data=action_drafts_data,
        adjudicator_results_data=adjudicator_results_data,
    )

    try:
        with tsv_output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=review_tsv_columns(),
                delimiter="\t",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(tsv_rows)
    except Exception as exc:
        raise RopReviewExportError(f"Failed to write TSV: {exc}") from exc

    print(f"\nReview TSV exported: {tsv_output_path}")
    logger.info(
        "ROP CLI: review TSV exported for run_id=%s path=%s rows=%d",
        run_id,
        tsv_output_path,
        len(tsv_rows),
    )
    return tsv_output_path.as_posix()


def _safe_tsv_value(value: Any) -> str:
    if value is None or value == "":
        return ""

    text = str(value)
    text = text.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    return text


def _build_body_short(normalized_evt: dict) -> str:
    preview = normalized_evt.get("body_preview")
    if preview and isinstance(preview, str) and preview.strip():
        return _safe_tsv_value(preview[:REVIEW_BODY_SHORT_MAX_CHARS])

    preview = normalized_evt.get("text_preview")
    if preview and isinstance(preview, str) and preview.strip():
        return _safe_tsv_value(preview[:REVIEW_BODY_SHORT_MAX_CHARS])

    body = normalized_evt.get("body")
    if body and isinstance(body, str) and body.strip():
        return _safe_tsv_value(body[:REVIEW_BODY_SHORT_MAX_CHARS])

    return ""


def _is_blocked_email_attachment(att: dict[str, Any]) -> bool:
    filename = str(att.get("filename") or "").strip().lower()
    content_type = str(att.get("content_type") or "").strip().lower()
    return filename.endswith(".eml") or content_type == "message/rfc822"


def _build_attachment_summary(attachments: Any) -> str:
    if not attachments or not isinstance(attachments, list):
        return ""

    summaries = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        if _is_blocked_email_attachment(att):
            continue

        filename = _safe_tsv_value(att.get("filename", ""))
        content_type = _safe_tsv_value(att.get("content_type", ""))
        size_bytes = att.get("size_bytes")

        if not filename:
            continue

        parts = [filename]
        meta = []

        if content_type:
            meta.append(content_type)

        if size_bytes is not None:
            try:
                size_int = int(size_bytes)
                meta.append(str(size_int))
            except ValueError, TypeError:
                pass

        summary = " ".join(parts)
        if meta:
            summary += f" ({', '.join(meta)})"
        summaries.append(_safe_tsv_value(summary))

    return _safe_tsv_value("; ".join(summaries))


def review_tsv_columns() -> list[str]:
    return [
        "event_id",
        "source_id",
        "source_type",
        "source_role",
        "source_display_name",
        "client_id",
        "sender",
        "subject",
        "clean_subject",
        "transport_labels",
        "spam_label_present",
        "reply_label_present",
        "forwarded_wrapper",
        "form_email",
        "original_sender",
        "original_sender_email",
        "original_recipient",
        "original_message_date",
        "date_source",
        "x_email_id",
        "body_short",
        "attachments",
        "bot_case_type",
        "bot_case_subtype",
        "bot_recommended_queue",
        "bot_should_rop_see",
        "bot_correct_action",
        "bot_reason_code",
        "bot_priority",
        "bot_confidence",
        "bot_is_fallback",
        "bot_reasoning",
        "bitrix_match_status",
        "bitrix_match_quality",
        "bitrix_confidence",
        "needs_manual_review",
        "safe_to_use_as_target",
        "recommended_action",
        "recommended_next_step",
        "action_queue",
        "action_draft_id",
        "human_case_type",
        "human_case_subtype",
        "human_recommended_queue",
        "human_should_rop_see",
        "human_correct_action",
        "bitrix_status",
        "notes",
        "bitrix_lead_id",
        "bitrix_deal_id",
        "bitrix_responsible",
        "is_duplicate",
        "duplicate_of",
        "ai_used",
        "ai_provider",
        "ai_model",
        "ai_status",
        "ai_confidence",
        "ai_reason",
        "ai_risk_flags",
        "ai_error",
        "deterministic_case_type",
        "deterministic_case_subtype",
        "deterministic_recommended_queue",
        "deterministic_correct_action",
        "deterministic_confidence",
        "deterministic_reason_code",
    ]


def _build_review_tsv_rows(
    normalized_events: list[dict],
    classified_events: list[dict],
    reconciliation_data: dict | None = None,
    action_drafts_data: dict | None = None,
    adjudicator_results_data: dict | None = None,
) -> list[dict[str, str]]:
    normalized_lookup = {evt.get("event_id"): evt for evt in normalized_events}

    bitrix_lookup: dict[str, dict] = {}
    if reconciliation_data and isinstance(reconciliation_data, dict):
        items = reconciliation_data.get("items", [])
        if isinstance(items, list):
            for item in items:
                eid = item.get("event_id", "")
                if eid:
                    bitrix_lookup[eid] = item

    action_drafts_lookup: dict[str, dict] = {}
    if action_drafts_data and isinstance(action_drafts_data, dict):
        items = action_drafts_data.get("items", [])
        if isinstance(items, list):
            for item in items:
                eid = item.get("event_id", "")
                if eid:
                    action_drafts_lookup[eid] = item

    adjudicator_results_lookup: dict[str, dict] = {}
    if adjudicator_results_data and isinstance(adjudicator_results_data, dict):
        items = adjudicator_results_data.get("results", [])
        if isinstance(items, list):
            for item in items:
                eid = item.get("event_id", "")
                if eid:
                    adjudicator_results_lookup[eid] = item

    rows: list[dict[str, str]] = []

    for classified_evt in classified_events:
        event_id = classified_evt.get("event_id", "")
        original_event_id = classified_evt.get("original_event_id", event_id)
        normalized_evt = normalized_lookup.get(original_event_id, {})

        body_short = _build_body_short(normalized_evt)
        attachments_summary = _build_attachment_summary(
            normalized_evt.get("attachments")
        )
        bot_priority = classified_evt.get("priority", "")
        bot_reasoning = classified_evt.get("reasoning", "")
        is_duplicate = classified_evt.get("is_duplicate")
        duplicate_of = classified_evt.get("duplicate_of", "")

        recon_item = bitrix_lookup.get(event_id, {})
        bitrix_entity_type = recon_item.get("bitrix_entity_type", "")

        bitrix_status = recon_item.get("bitrix_match_status", "")
        if not bitrix_status and bitrix_entity_type:
            bitrix_status = bitrix_entity_type

        bitrix_lead_id = ""
        bitrix_deal_id = ""
        bitrix_entity_id = recon_item.get("bitrix_entity_id")
        if bitrix_entity_id is not None:
            if bitrix_entity_type == "lead":
                bitrix_lead_id = str(bitrix_entity_id)
            elif bitrix_entity_type == "deal":
                bitrix_deal_id = str(bitrix_entity_id)

        bitrix_responsible = ""
        responsible_id = recon_item.get("bitrix_responsible_id")
        if responsible_id is not None:
            bitrix_responsible = str(responsible_id)

        bitrix_match_quality = recon_item.get("bitrix_match_quality", "")
        bitrix_confidence = recon_item.get("bitrix_confidence", "")
        needs_manual_review = recon_item.get("needs_manual_review", "")
        safe_to_use_as_target = recon_item.get("safe_to_use_as_target", "")

        action_draft_item = action_drafts_lookup.get(event_id, {})
        action_draft_id = action_draft_item.get("action_draft_id", "")
        recommended_action = action_draft_item.get("recommended_action", "")
        recommended_next_step = action_draft_item.get("recommended_next_step", "")
        action_queue = action_draft_item.get("queue", "")

        adj_result = adjudicator_results_lookup.get(event_id, {})

        bot_should_rop_see = classified_evt.get("should_rop_see")
        bot_should_rop_see_value = (
            str(bot_should_rop_see).lower() if bot_should_rop_see is not None else ""
        )

        row = {
            "event_id": _safe_tsv_value(event_id),
            "source_id": _safe_tsv_value(classified_evt.get("source_id", "")),
            "source_type": _safe_tsv_value(classified_evt.get("source_type", "")),
            "source_role": _safe_tsv_value(classified_evt.get("source_role", "")),
            "source_display_name": _safe_tsv_value(
                classified_evt.get("source_display_name", "")
            ),
            "client_id": _safe_tsv_value(classified_evt.get("client_id", "")),
            "sender": _safe_tsv_value(normalized_evt.get("sender", "")),
            "subject": _safe_tsv_value(normalized_evt.get("subject", "")),
            "clean_subject": _safe_tsv_value(normalized_evt.get("clean_subject", "")),
            "transport_labels": _safe_tsv_value(
                ",".join(normalized_evt.get("transport_labels", []))
            ),
            "spam_label_present": _safe_tsv_value(
                str(normalized_evt.get("spam_label_present", False)).lower()
            ),
            "reply_label_present": _safe_tsv_value(
                str(normalized_evt.get("reply_label_present", False)).lower()
            ),
            "forwarded_wrapper": _safe_tsv_value(
                str(normalized_evt.get("forwarded_wrapper", False)).lower()
            ),
            "form_email": _safe_tsv_value(normalized_evt.get("form_email", "")),
            "original_sender": _safe_tsv_value(
                normalized_evt.get("original_sender", "")
            ),
            "original_sender_email": _safe_tsv_value(
                normalized_evt.get("original_sender_email", "")
            ),
            "original_recipient": _safe_tsv_value(
                normalized_evt.get("original_recipient", "")
            ),
            "original_message_date": _safe_tsv_value(
                normalized_evt.get("original_message_date", "")
            ),
            "date_source": _safe_tsv_value(normalized_evt.get("date_source", "")),
            "x_email_id": _safe_tsv_value(normalized_evt.get("x_email_id", "")),
            "body_short": body_short,
            "attachments": _safe_tsv_value(attachments_summary),
            "bot_case_type": _safe_tsv_value(classified_evt.get("case_type", "")),
            "bot_case_subtype": _safe_tsv_value(classified_evt.get("case_subtype", "")),
            "bot_recommended_queue": _safe_tsv_value(
                classified_evt.get("recommended_queue", "")
            ),
            "bot_should_rop_see": _safe_tsv_value(bot_should_rop_see_value),
            "bot_correct_action": _safe_tsv_value(
                classified_evt.get("correct_action", "")
            ),
            "bot_reason_code": _safe_tsv_value(classified_evt.get("reason_code", "")),
            "bot_priority": _safe_tsv_value(bot_priority),
            "bot_confidence": _safe_tsv_value(classified_evt.get("confidence", "")),
            "bot_is_fallback": _safe_tsv_value(
                str(classified_evt.get("is_fallback", False)).lower()
            ),
            "bot_reasoning": _safe_tsv_value(bot_reasoning),
            "bitrix_match_status": _safe_tsv_value(bitrix_status),
            "bitrix_match_quality": _safe_tsv_value(bitrix_match_quality),
            "bitrix_confidence": _safe_tsv_value(bitrix_confidence),
            "needs_manual_review": _safe_tsv_value(str(needs_manual_review).lower()),
            "safe_to_use_as_target": _safe_tsv_value(
                str(safe_to_use_as_target).lower()
            ),
            "recommended_action": _safe_tsv_value(recommended_action),
            "recommended_next_step": _safe_tsv_value(recommended_next_step),
            "action_queue": _safe_tsv_value(action_queue),
            "action_draft_id": _safe_tsv_value(action_draft_id),
            "human_case_type": "",
            "human_case_subtype": "",
            "human_recommended_queue": "",
            "human_should_rop_see": "",
            "human_correct_action": "",
            "bitrix_status": "",
            "notes": "",
            "bitrix_lead_id": _safe_tsv_value(bitrix_lead_id),
            "bitrix_deal_id": _safe_tsv_value(bitrix_deal_id),
            "bitrix_responsible": _safe_tsv_value(bitrix_responsible),
            "is_duplicate": (
                _safe_tsv_value(str(is_duplicate).lower())
                if is_duplicate is not None
                else ""
            ),
            "duplicate_of": _safe_tsv_value(duplicate_of),
            "ai_used": _safe_tsv_value(
                str(adj_result.get("ai_used", False)).lower() if adj_result else ""
            ),
            "ai_provider": _safe_tsv_value(
                adj_result.get("ai_provider", "") if adj_result else ""
            ),
            "ai_model": _safe_tsv_value(
                adj_result.get("ai_model", "") if adj_result else ""
            ),
            "ai_status": _safe_tsv_value(
                adj_result.get("ai_status", "") if adj_result else ""
            ),
            "ai_confidence": _safe_tsv_value(
                str(adj_result.get("ai_confidence", "")) if adj_result else ""
            ),
            "ai_reason": _safe_tsv_value(
                adj_result.get("ai_reason", "") if adj_result else ""
            ),
            "ai_risk_flags": _safe_tsv_value(
                ",".join(adj_result.get("ai_risk_flags", [])) if adj_result else ""
            ),
            "ai_error": _safe_tsv_value(
                adj_result.get("ai_error", "") if adj_result else ""
            ),
            "deterministic_case_type": _safe_tsv_value(
                classified_evt.get(
                    "deterministic_case_type",
                    adj_result.get("deterministic_case_type", ""),
                )
            ),
            "deterministic_case_subtype": _safe_tsv_value(
                classified_evt.get(
                    "deterministic_case_subtype",
                    adj_result.get("deterministic_case_subtype", ""),
                )
            ),
            "deterministic_recommended_queue": _safe_tsv_value(
                classified_evt.get(
                    "deterministic_recommended_queue",
                    adj_result.get("deterministic_recommended_queue", ""),
                )
            ),
            "deterministic_correct_action": _safe_tsv_value(
                classified_evt.get(
                    "deterministic_correct_action",
                    adj_result.get("deterministic_correct_action", ""),
                )
            ),
            "deterministic_confidence": _safe_tsv_value(
                classified_evt.get(
                    "deterministic_confidence",
                    adj_result.get("deterministic_confidence", ""),
                )
            ),
            "deterministic_reason_code": _safe_tsv_value(
                classified_evt.get(
                    "deterministic_reason_code",
                    adj_result.get("deterministic_reason_code", ""),
                )
            ),
        }
        rows.append(row)

    return rows
