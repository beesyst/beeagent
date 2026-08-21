from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from beeagent_module.core.rop_reason_contract import (
    AI_EVIDENCE_CODES,
    AI_EVIDENCE_CODES_MAX,
    ATTENTION_REASON_CODES,
)

_FINAL_DECISION_EVENT_KEYS = frozenset(
    {
        "event_id",
        "event_instance_id",
        "source_id",
        "sender",
        "subject",
        "deterministic_case_type",
        "deterministic_case_subtype",
        "deterministic_queue",
        "deterministic_action",
        "deterministic_confidence",
        "deterministic_reason_code",
        "final_case_type",
        "final_case_subtype",
        "final_queue",
        "final_action",
        "final_decision_source",
        "final_confidence",
        "needs_attention",
        "attention_reason",
        "attention_reason_code",
        "attention_evidence_codes",
        "automation_allowed",
        "bitrix_write_allowed",
        "base_classification",
        "duplicate",
    }
)
_MAX_ATTENTION_REASON_CODE_LENGTH = 80
_MAX_ATTENTION_REASON_LENGTH = 600
_MAX_AI_EVIDENCE_CODE_LENGTH = 80
_MAX_EVENT_INSTANCE_ID_LENGTH = 80
_BASE_CLASSIFICATION_KEYS = frozenset(
    {
        "case_type",
        "priority",
        "reason_code",
        "confidence",
        "reasoning",
        "is_fallback",
        "case_subtype",
        "recommended_queue",
        "should_rop_see",
        "correct_action",
    }
)
_DUPLICATE_RESULT_KEYS = frozenset(
    {
        "is_duplicate",
        "confidence",
        "reason_code",
        "reason_path",
        "reasoning",
        "candidate",
        "candidates",
        "is_fallback",
    }
)
_DUPLICATE_RESULT_KEYS_WITH_STATUS = _DUPLICATE_RESULT_KEYS | frozenset(
    {"resolution_status"}
)
_DUPLICATE_MATCH_KEYS = frozenset(
    {
        "existing_lead_id",
        "event_id",
        "similarity_score",
        "matched_fields",
        "reason_code",
        "reason_path",
        "reasoning",
    }
)


def _attention_evidence_codes(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        code
        for code in value
        if isinstance(code, str)
        and len(code) <= _MAX_AI_EVIDENCE_CODE_LENGTH
        and code in AI_EVIDENCE_CODES
    ][:AI_EVIDENCE_CODES_MAX]


def _attention_reason_code(adj: dict[str, Any]) -> str:
    merge_reason = adj.get("merge_reason")
    if (
        isinstance(merge_reason, str)
        and len(merge_reason) <= _MAX_ATTENTION_REASON_CODE_LENGTH
        and merge_reason in ATTENTION_REASON_CODES
    ):
        return merge_reason
    return "ai_adjudicator_unexpected_status"


def _is_confidence(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.0 <= value <= 1.0
    )


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _sanitize_base_classification(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _BASE_CLASSIFICATION_KEYS:
        return None
    if not all(
        isinstance(value[key], str)
        for key in (
            "case_type",
            "priority",
            "reason_code",
            "reasoning",
            "case_subtype",
            "recommended_queue",
            "correct_action",
        )
    ):
        return None
    if not _is_confidence(value["confidence"]):
        return None
    if not isinstance(value["is_fallback"], bool):
        return None
    if not isinstance(value["should_rop_see"], bool):
        return None
    return {key: value[key] for key in _BASE_CLASSIFICATION_KEYS}


def _sanitize_duplicate_match(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _DUPLICATE_MATCH_KEYS:
        return None
    if not all(
        isinstance(value[key], str)
        for key in (
            "existing_lead_id",
            "event_id",
            "reason_code",
            "reasoning",
        )
    ):
        return None
    if not _is_confidence(value["similarity_score"]):
        return None
    if not _is_string_list(value["matched_fields"]):
        return None
    if not _is_string_list(value["reason_path"]):
        return None
    return {
        key: list(value[key])
        if key in {"matched_fields", "reason_path"}
        else value[key]
        for key in _DUPLICATE_MATCH_KEYS
    }


def _sanitize_duplicate(
    value: Any,
    candidates_max: int,
) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) not in {
        _DUPLICATE_RESULT_KEYS,
        _DUPLICATE_RESULT_KEYS_WITH_STATUS,
    }:
        return None
    if not isinstance(value["is_duplicate"], bool):
        return None
    if "resolution_status" in value and value["resolution_status"] not in {
        "confirmed",
        "possible",
        "not_duplicate",
    }:
        return None
    if not _is_confidence(value["confidence"]):
        return None
    if not isinstance(value["reason_code"], str):
        return None
    if not _is_string_list(value["reason_path"]):
        return None
    if not isinstance(value["reasoning"], str):
        return None
    if not isinstance(value["is_fallback"], bool):
        return None

    candidate = value["candidate"]
    if candidate is not None:
        candidate = _sanitize_duplicate_match(candidate)
        if candidate is None:
            return None

    candidates = value["candidates"]
    if not isinstance(candidates, list) or len(candidates) > candidates_max:
        return None
    sanitized_candidates: list[dict[str, Any]] = []
    for item in candidates:
        sanitized_item = _sanitize_duplicate_match(item)
        if sanitized_item is None:
            return None
        sanitized_candidates.append(sanitized_item)

    result = {
        "is_duplicate": value["is_duplicate"],
        "confidence": value["confidence"],
        "reason_code": value["reason_code"],
        "reason_path": list(value["reason_path"]),
        "reasoning": value["reasoning"],
        "candidate": candidate,
        "candidates": sanitized_candidates,
        "is_fallback": value["is_fallback"],
    }
    if "resolution_status" in value:
        result["resolution_status"] = value["resolution_status"]
    return result


def _deterministic_value(event: dict[str, Any], key: str, fallback: Any) -> Any:
    deterministic_key = f"deterministic_{key}"
    value = event.get(deterministic_key)

    if value is None or (isinstance(value, str) and not value.strip()):
        value = event.get(key)

    if value is None or (isinstance(value, str) and not value.strip()):
        return fallback

    return value


def _results_by_event_identity(
    adjudicator_results: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[tuple[str, str], dict[str, Any]]:
    if isinstance(adjudicator_results, dict):
        adjudicator_results = adjudicator_results.get("results")
    if not isinstance(adjudicator_results, list):
        return {}
    return {
        (
            str(result["event_id"]),
            str(result.get("event_instance_id") or ""),
        ): result
        for result in adjudicator_results
        if isinstance(result, dict) and result.get("event_id")
    }


def _normalize_terminal_routing(
    queue: str,
    action: str,
) -> tuple[str, str, bool]:
    if queue == "manual_review" or action == "manual_review":
        return "unresolved", "no_action", True
    return queue, action, False


def build_final_decisions(
    events: list[dict[str, Any]] | None,
    adjudicator_results: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, Any]:
    results_by_identity = _results_by_event_identity(adjudicator_results)
    decisions: list[dict[str, Any]] = []
    candidates_max = len(events or [])
    source_counts: dict[str, int] = {}
    attention_count = 0

    for event in events or []:
        if not isinstance(event, dict):
            continue

        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            continue
        event_id = event_id.strip()
        event_instance_id = event.get("event_instance_id")
        if not isinstance(event_instance_id, str):
            event_instance_id = ""
        adj = results_by_identity.get((event_id, event_instance_id))
        deterministic_case_type = _deterministic_value(event, "case_type", "unknown")
        deterministic_case_subtype = _deterministic_value(event, "case_subtype", None)
        deterministic_queue = _deterministic_value(
            event, "recommended_queue", "manual_review"
        )
        deterministic_action = _deterministic_value(
            event, "correct_action", "manual_review"
        )
        deterministic_confidence = _deterministic_value(event, "confidence", 0.0)
        deterministic_reason_code = _deterministic_value(event, "reason_code", "")

        if (
            not isinstance(deterministic_case_type, str)
            or not deterministic_case_type.strip()
        ):
            deterministic_case_type = "unknown"
        if not isinstance(deterministic_queue, str) or not deterministic_queue.strip():
            deterministic_queue = "manual_review"
        if (
            not isinstance(deterministic_action, str)
            or not deterministic_action.strip()
        ):
            deterministic_action = "manual_review"
        if not isinstance(deterministic_case_subtype, str):
            deterministic_case_subtype = None
        if not isinstance(deterministic_reason_code, str):
            deterministic_reason_code = ""
        if not isinstance(deterministic_confidence, (int, float)) or isinstance(
            deterministic_confidence, bool
        ):
            deterministic_confidence = 0.0

        final_case_type = deterministic_case_type
        final_case_subtype = deterministic_case_subtype
        final_queue = deterministic_queue
        final_action = deterministic_action
        final_confidence = deterministic_confidence
        final_decision_source = "deterministic"
        needs_attention = False
        attention_reason: str | None = None

        attention_reason_code: str | None = None
        attention_evidence_codes: list[str] | None = None
        duplicate_status = (
            event.get("duplicate", {}).get("resolution_status")
            if isinstance(event.get("duplicate"), dict)
            else None
        )

        if deterministic_case_type == "duplicate":
            adj = None

        if isinstance(adj, dict):
            ai_status = adj.get("ai_status")
            if ai_status == "ok":
                candidate_case_type = adj.get("final_case_type")
                candidate_subtype = adj.get(
                    "final_case_subtype", deterministic_case_subtype
                )
                candidate_queue = adj.get("final_recommended_queue")
                candidate_action = adj.get("final_correct_action")
                candidate_confidence = adj.get("ai_confidence")
                if isinstance(candidate_case_type, str) and candidate_case_type.strip():
                    final_case_type = candidate_case_type
                if candidate_subtype is None or isinstance(candidate_subtype, str):
                    final_case_subtype = candidate_subtype
                if isinstance(candidate_queue, str) and candidate_queue.strip():
                    final_queue = candidate_queue
                if isinstance(candidate_action, str) and candidate_action.strip():
                    final_action = candidate_action
                if isinstance(candidate_confidence, (int, float)) and not isinstance(
                    candidate_confidence, bool
                ):
                    final_confidence = candidate_confidence
                final_decision_source = "ai_adjudicator"
            elif ai_status in {
                "low_confidence_preserve",
                "deterministic_preserved",
                "duplicate_unresolved",
                "degraded",
                "invalid",
            }:
                needs_attention = True
                attention_reason_code = _attention_reason_code(adj)
                attention_reason = attention_reason_code
                attention_evidence_codes = _attention_evidence_codes(
                    adj.get("ai_evidence_codes")
                )
                final_decision_source = "deterministic_preserved"
            else:
                needs_attention = True
                attention_reason_code = _attention_reason_code(adj)
                attention_reason = attention_reason_code
                attention_evidence_codes = _attention_evidence_codes(
                    adj.get("ai_evidence_codes")
                )
                final_decision_source = "fallback_policy"

        if duplicate_status == "possible" and (
            not isinstance(adj, dict) or adj.get("ai_status") != "ok"
        ):
            base = event.get("base_classification")
            if isinstance(base, dict):
                final_case_type = base.get("case_type", final_case_type)
                final_case_subtype = base.get("case_subtype", final_case_subtype)
                final_queue = base.get("recommended_queue", final_queue)
                final_action = base.get("correct_action", final_action)
            needs_attention = True
            attention_reason_code = "possible_duplicate_unresolved_base_preserved"
            attention_reason = attention_reason_code
            final_decision_source = "deterministic_preserved"

        normalized_queue, normalized_action, normalized_attention = (
            _normalize_terminal_routing(final_queue, final_action)
        )
        if normalized_attention:
            final_queue = normalized_queue
            final_action = normalized_action
            needs_attention = True
            if attention_reason_code is None:
                attention_reason_code = "semantic_unresolved_no_operator_queue"
                attention_reason = attention_reason_code

        if needs_attention:
            attention_count += 1
        source_counts[final_decision_source] = (
            source_counts.get(final_decision_source, 0) + 1
        )
        decisions.append(
            {
                "event_id": event_id,
                "event_instance_id": event_instance_id,
                "source_id": event.get("source_id")
                if isinstance(event.get("source_id"), str)
                else "",
                "sender": event.get("sender")
                if isinstance(event.get("sender"), str)
                else "",
                "subject": event.get("subject")
                if isinstance(event.get("subject"), str)
                else "",
                "deterministic_case_type": deterministic_case_type,
                "deterministic_case_subtype": deterministic_case_subtype,
                "deterministic_queue": deterministic_queue,
                "deterministic_action": deterministic_action,
                "deterministic_confidence": deterministic_confidence,
                "deterministic_reason_code": deterministic_reason_code,
                "final_case_type": final_case_type,
                "final_case_subtype": final_case_subtype,
                "final_queue": final_queue,
                "final_action": final_action,
                "final_decision_source": final_decision_source,
                "final_confidence": final_confidence,
                "needs_attention": needs_attention,
                "attention_reason": attention_reason,
                "attention_reason_code": attention_reason_code,
                "attention_evidence_codes": attention_evidence_codes,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
                "base_classification": _sanitize_base_classification(
                    event.get("base_classification")
                ),
                "duplicate": _sanitize_duplicate(
                    event.get("duplicate"), candidates_max
                ),
            }
        )

    return {
        "summary": {
            "total_events": len(decisions),
            "decision_source_counts": source_counts,
            "attention_count": attention_count,
        },
        "events": decisions,
    }


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        with path.open("r", encoding="utf-8") as artifact:
            return json.load(artifact)
    except json.JSONDecodeError, OSError:
        return None


def _is_final_decisions_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if set(payload) != {"summary", "events"}:
        return False
    summary = payload.get("summary")
    events = payload.get("events")
    if not isinstance(summary, dict) or not isinstance(events, list):
        return False
    if set(summary) != {
        "total_events",
        "decision_source_counts",
        "attention_count",
    }:
        return False

    total_events = summary.get("total_events")
    attention_count = summary.get("attention_count")
    source_counts = summary.get("decision_source_counts")
    if (
        not isinstance(total_events, int)
        or isinstance(total_events, bool)
        or total_events < 0
        or not isinstance(attention_count, int)
        or isinstance(attention_count, bool)
        or attention_count < 0
        or not isinstance(source_counts, dict)
        or total_events != len(events)
    ):
        return False

    actual_source_counts: dict[str, int] = {}
    actual_attention_count = 0
    for event in events:
        if not isinstance(event, dict):
            return False
        if not set(event).issubset(_FINAL_DECISION_EVENT_KEYS):
            return False
        for key in (
            "event_id",
            "final_case_type",
            "final_queue",
            "final_action",
            "final_decision_source",
        ):
            if not isinstance(event.get(key), str) or not event[key].strip():
                return False
        if (
            "final_case_subtype" not in event
            or "final_confidence" not in event
            or "attention_reason" not in event
        ):
            return False
        if event.get("final_case_subtype") is not None and not isinstance(
            event.get("final_case_subtype"), str
        ):
            return False
        confidence = event.get("final_confidence")
        if confidence is not None and (
            not isinstance(confidence, (int, float)) or isinstance(confidence, bool)
        ):
            return False
        if not isinstance(event.get("needs_attention"), bool):
            return False
        if event["attention_reason"] is not None:
            attention_reason = event["attention_reason"]
            if (
                not isinstance(attention_reason, str)
                or len(attention_reason) > _MAX_ATTENTION_REASON_LENGTH
            ):
                return False
        if "attention_reason_code" in event:
            attention_reason_code = event["attention_reason_code"]
            if attention_reason_code is not None and (
                not isinstance(attention_reason_code, str)
                or not attention_reason_code.strip()
                or len(attention_reason_code) > _MAX_ATTENTION_REASON_CODE_LENGTH
            ):
                return False
        if "attention_evidence_codes" in event:
            evidence_codes = event["attention_evidence_codes"]
            if evidence_codes is not None and (
                not isinstance(evidence_codes, list)
                or len(evidence_codes) > AI_EVIDENCE_CODES_MAX
                or any(
                    not isinstance(code, str)
                    or len(code) > _MAX_AI_EVIDENCE_CODE_LENGTH
                    or code not in AI_EVIDENCE_CODES
                    for code in evidence_codes
                )
            ):
                return False
        if event["needs_attention"]:
            attention_reason_val = event.get("attention_reason")
            if (
                not isinstance(attention_reason_val, str)
                or not attention_reason_val.strip()
            ):
                return False
            actual_attention_count += 1
        if event.get("automation_allowed") is not False:
            return False
        if event.get("bitrix_write_allowed") is not False:
            return False
        if "base_classification" in event:
            base_classification = event["base_classification"]
            if (
                base_classification is not None
                and _sanitize_base_classification(base_classification) is None
            ):
                return False
        if "duplicate" in event:
            duplicate = event["duplicate"]
            if (
                duplicate is not None
                and _sanitize_duplicate(duplicate, len(events)) is None
            ):
                return False
        for key in (
            "source_id",
            "event_instance_id",
            "sender",
            "subject",
            "deterministic_case_type",
            "deterministic_case_subtype",
            "deterministic_queue",
            "deterministic_action",
            "deterministic_reason_code",
        ):
            if (
                key in event
                and event[key] is not None
                and not isinstance(event[key], str)
            ):
                return False
        if "event_instance_id" in event and (
            len(event["event_instance_id"]) > _MAX_EVENT_INSTANCE_ID_LENGTH
        ):
            return False
        if "deterministic_confidence" in event:
            deterministic_confidence = event["deterministic_confidence"]
            if deterministic_confidence is not None and (
                not isinstance(deterministic_confidence, (int, float))
                or isinstance(deterministic_confidence, bool)
            ):
                return False
        source = event["final_decision_source"]
        actual_source_counts[source] = actual_source_counts.get(source, 0) + 1

    if attention_count != actual_attention_count:
        return False
    if source_counts != actual_source_counts:
        return False
    return all(
        isinstance(source, str)
        and not isinstance(count, bool)
        and isinstance(count, int)
        and count >= 0
        for source, count in source_counts.items()
    )


def load_or_build_final_decisions(run_dir: Path) -> tuple[dict[str, Any], str]:
    artifact = _read_json(run_dir / "rop_final_decisions.json")
    if isinstance(artifact, dict) and _is_final_decisions_payload(artifact):
        return artifact, "artifact"

    events = _read_json(run_dir / "classified_events.json")
    adjudicator_results = _read_json(run_dir / "rop_ai_adjudicator_results.json")
    return build_final_decisions(
        events if isinstance(events, list) else [],
        adjudicator_results if isinstance(adjudicator_results, dict) else None,
    ), "computed"


def find_final_decision(
    payload: dict[str, Any] | None,
    event_id: str,
    event_instance_id: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    events = payload.get("events")
    if not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict) or event.get("event_id") != event_id:
            continue
        if (
            event_instance_id is None
            or event.get("event_instance_id") == event_instance_id
        ):
            return event
    return None
