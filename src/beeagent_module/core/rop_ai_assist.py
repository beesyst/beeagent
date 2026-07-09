from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib import request

_AI_ASSIST_PROVIDERS = frozenset({"openai_compatible", "openai_responses"})


def resolve_ai_profile(
    ai_cfg: dict[str, Any],
    ai_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_name = ai_cfg.get("profile", "")
    profiles = ai_cfg.get("profiles", {})
    if isinstance(profiles, dict) and isinstance(profile_name, str) and profile_name:
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            raise RuntimeError(f"Unknown rop.ai_assist.profile: {profile_name}")

        return {
            "provider": profile["provider"],
            "model": os.getenv(profile["model_env"], "").strip(),
            "api_key_env": profile["api_key_env"],
            "base_url": os.getenv(profile["base_url_env"], "").strip(),
            "request_timeout": ai_cfg.get("request_timeout", 30),
            "dry_run": ai_cfg.get("dry_run", False),
            "profile": profile_name,
        }

    active_profiles = (ai_settings or {}).get("profiles", {})
    if not isinstance(active_profiles, dict):
        raise RuntimeError("ai.profiles must be a mapping")

    enabled_profiles = [
        (name, profile)
        for name, profile in active_profiles.items()
        if isinstance(profile, dict) and profile.get("enabled") is True
    ]
    if len(enabled_profiles) != 1:
        raise RuntimeError("Exactly one ai.profiles.*.enabled must be true")

    active_name, active_profile = enabled_profiles[0]
    return {
        "provider": active_profile["provider"],
        "model": active_profile["model"],
        "api_key_env": active_profile["api_key_env"],
        "base_url": active_profile["base_url"],
        "request_timeout": ai_cfg.get("request_timeout", 30),
        "dry_run": ai_cfg.get("dry_run", False),
        "profile": active_name,
    }


def _build_assist_prompt(
    event: dict[str, Any],
    thread_context: dict[str, Any] | None,
) -> str:
    lines: list[str] = [
        "You are a ROP classification assistant. Analyze the following inbound event.",
        "Return a JSON object with these fields:",
        '  "case_type": string ("spam", "noise", "new_lead", "existing_deal", "follow_up", "irrelevant"),',
        '  "case_subtype": string or null,',
        '  "recommended_queue": string or null,',
        '  "should_rop_see": boolean,',
        '  "correct_action": string or null,',
        '  "confidence": float (0.0 to 1.0),',
        '  "reason_code": string,',
        '  "risk_flags": list of strings',
        "",
        "Rules:",
        "- Do not suggest CRM/Bitrix write-back actions.",
        "- Do not suggest mailbox mutations.",
        "- If unsure, set confidence low and flag risk.",
        "- Return ONLY valid JSON, no markdown, no explanation.",
        "",
        "Event:",
    ]

    subject = event.get("subject") or ""
    body = event.get("body") or event.get("body_preview") or ""
    sender = event.get("sender") or ""

    lines.append(f"  sender: {sender[:200]}")
    lines.append(f"  subject: {subject[:200]}")
    lines.append(f"  body_preview: {str(body)[:500]}")

    if thread_context:
        lines.append("")
        lines.append("Thread context:")
        lines.append(json.dumps(thread_context, ensure_ascii=False)[:500])

    return "\n".join(lines)


def _parse_ai_response(raw_text: str) -> dict[str, Any] | None:
    if not raw_text or not raw_text.strip():
        return None

    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        end = cleaned.find("```", 3)
        if end != -1:
            cleaned = cleaned[3:end].strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        try:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                data = json.loads(cleaned[start : end + 1])
            else:
                return None
        except json.JSONDecodeError:
            return None

    if not isinstance(data, dict):
        return None

    return data


def _validate_ai_output(data: dict[str, Any]) -> dict[str, Any]:
    valid_case_types = {
        "spam",
        "noise",
        "new_lead",
        "existing_deal",
        "follow_up",
        "irrelevant",
        "unknown",
    }
    validated: dict[str, Any] = {}
    warnings: list[str] = []

    case_type = data.get("case_type", "unknown")
    if isinstance(case_type, str) and case_type in valid_case_types:
        validated["case_type"] = case_type
    else:
        validated["case_type"] = "unknown"
        warnings.append(f"invalid case_type: {case_type}")

    subtype = data.get("case_subtype")
    validated["case_subtype"] = subtype if isinstance(subtype, str) else None

    queue = data.get("recommended_queue")
    validated["recommended_queue"] = queue if isinstance(queue, str) else None

    should_see = data.get("should_rop_see")
    validated["should_rop_see"] = (
        bool(should_see) if isinstance(should_see, bool) else False
    )

    correct_action = data.get("correct_action")
    validated["correct_action"] = (
        correct_action if isinstance(correct_action, str) else None
    )

    confidence = data.get("confidence", 0.0)
    if isinstance(confidence, (int, float)) and 0.0 <= confidence <= 1.0:
        validated["confidence"] = float(confidence)
    else:
        validated["confidence"] = 0.0
        warnings.append("invalid confidence value")

    reason_code = data.get("reason_code")
    validated["reason_code"] = (
        reason_code if isinstance(reason_code, str) else "ai_assist_fallback"
    )

    risk_flags = data.get("risk_flags", [])
    if isinstance(risk_flags, list):
        validated["risk_flags"] = [str(f) for f in risk_flags if isinstance(f, str)]
    else:
        validated["risk_flags"] = []

    blocked_actions = {"create", "update", "delete", "add", "write", "archive", "mark"}
    for flag in validated.get("risk_flags", []):
        if any(ba in str(flag).lower() for ba in blocked_actions):
            warnings.append(f"blocked write-back risk flag: {flag}")

    action = validated.get("correct_action") or ""
    if any(ba in action.lower() for ba in blocked_actions):
        validated["correct_action"] = None
        validated["risk_flags"] = [
            *validated.get("risk_flags", []),
            "blocked_write_back_action",
        ]
        warnings.append("correct_action contained write-back instruction, rejected")

    validated["warnings"] = warnings
    return validated


def _is_event_eligible_for_ai_assist(event: dict[str, Any]) -> bool:
    case_type = event.get("case_type", "")
    is_fallback = event.get("is_fallback", False)
    confidence = event.get("confidence", 1.0)

    eligible_case_types = {"unknown", "existing_deal"}
    if case_type in eligible_case_types or is_fallback:
        return True

    if isinstance(confidence, (int, float)) and confidence < 0.60:
        return True

    confident_types = {"spam", "noise", "new_lead"}
    if case_type in confident_types and not is_fallback:
        if isinstance(confidence, (int, float)) and confidence >= 0.70:
            return False

    return True


def _call_ai_provider(
    ai_cfg: dict[str, Any],
    prompt: str,
    logger: logging.Logger,
) -> str | None:
    provider = ai_cfg["provider"]
    if provider not in _AI_ASSIST_PROVIDERS:
        logger.warning(
            "ai_assist: unsupported provider=%s, expected one of %s",
            provider,
            sorted(_AI_ASSIST_PROVIDERS),
        )
        return None

    api_key_env = ai_cfg["api_key_env"]
    model = ai_cfg["model"]
    base_url = ai_cfg["base_url"]
    timeout = int(ai_cfg["request_timeout"])
    dry_run = ai_cfg.get("dry_run", False)

    if dry_run:
        logger.info("ai_assist: dry_run=True, skipping actual API call")
        return json.dumps(
            {
                "case_type": "existing_deal",
                "case_subtype": None,
                "recommended_queue": None,
                "should_rop_see": True,
                "correct_action": None,
                "confidence": 0.50,
                "reason_code": "dry_run_placeholder",
                "risk_flags": ["dry_run"],
            }
        )

    if not isinstance(model, str) or not model.strip():
        logger.warning("ai_assist: model is missing in active AI profile")
        return None
    if not isinstance(base_url, str) or not base_url.strip():
        logger.warning("ai_assist: base_url is missing in active AI profile")
        return None

    api_key = os.getenv(api_key_env, "").strip()
    if not api_key:
        logger.warning(
            "ai_assist: api key env %s is empty",
            api_key_env,
        )
        return None

    api_url = base_url.rstrip("/") + "/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    try:
        req = request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        response_data = json.loads(raw)

        choices = response_data.get("choices", [])
        if not choices:
            logger.warning("ai_assist: no choices in response")
            return None

        content = choices[0].get("message", {}).get("content", "")
        return content
    except Exception as exc:
        logger.warning("ai_assist: API call failed: %s", exc)
        return None


def _build_request_artifact(
    event: dict[str, Any],
    eligible: bool,
    ai_cfg: dict[str, Any],
    thread_context: dict[str, Any] | None,
) -> dict[str, Any]:
    provider = ai_cfg["provider"]
    model = ai_cfg.get("model", "")

    return {
        "event_id": event.get("event_id", ""),
        "eligible": eligible,
        "request_preview": {
            "subject": (event.get("subject") or "")[:200],
            "body_preview": (event.get("body") or event.get("body_preview") or "")[
                :300
            ],
            "attachment_preview": (event.get("attachment_text_preview") or "")[:200]
            if event.get("attachment_preview_available")
            else None,
            "thread_context_summary": (
                json.dumps(thread_context, ensure_ascii=False)[:300]
            )
            if thread_context
            else None,
        },
        "provider": provider,
        "model": model,
    }


def run_ai_assist_for_event(
    event: dict[str, Any],
    ai_cfg: dict[str, Any],
    thread_context: dict[str, Any] | None,
    min_ai_confidence: float,
    logger: logging.Logger,
) -> dict[str, Any]:
    eligible = _is_event_eligible_for_ai_assist(event)

    request_artifact = _build_request_artifact(
        event=event,
        eligible=eligible,
        ai_cfg=ai_cfg,
        thread_context=thread_context,
    )

    decision: dict[str, Any] = {
        "event_id": event.get("event_id", ""),
        "status": "skipped",
        "reason_code": "not_eligible",
    }

    result: dict[str, Any] = {
        "event_id": event.get("event_id", ""),
        "ai_assist_used": False,
        "ai_assist_status": "not_eligible",
        "final_case_type": event.get("case_type", "unknown"),
        "final_case_subtype": event.get("case_subtype"),
        "final_recommended_queue": event.get("recommended_queue"),
        "final_correct_action": event.get("correct_action"),
        "merge_reason": "deterministic_result_preserved",
        "warnings": [],
    }

    if not eligible:
        return {
            "request": request_artifact,
            "decision": decision,
            "result": result,
        }

    prompt = _build_assist_prompt(event, thread_context)

    raw_response = _call_ai_provider(
        ai_cfg=ai_cfg,
        prompt=prompt,
        logger=logger,
    )

    if raw_response is None:
        decision = {
            "event_id": event.get("event_id", ""),
            "status": "degraded",
            "reason_code": "provider_call_failed",
        }
        result = {
            "event_id": event.get("event_id", ""),
            "ai_assist_used": False,
            "ai_assist_status": "degraded",
            "final_case_type": event.get("case_type", "unknown"),
            "final_case_subtype": event.get("case_subtype"),
            "final_recommended_queue": event.get("recommended_queue"),
            "final_correct_action": event.get("correct_action"),
            "merge_reason": "provider_call_failed_deterministic_result_preserved",
            "warnings": ["AI provider call failed; deterministic result preserved"],
        }
        return {
            "request": request_artifact,
            "decision": decision,
            "result": result,
        }

    parsed = _parse_ai_response(raw_response)
    if parsed is None:
        decision = {
            "event_id": event.get("event_id", ""),
            "status": "invalid",
            "reason_code": "unparseable_response",
            "raw_response_preview": raw_response[:500],
        }
        result = {
            "event_id": event.get("event_id", ""),
            "ai_assist_used": True,
            "ai_assist_status": "invalid",
            "final_case_type": event.get("case_type", "unknown"),
            "final_case_subtype": event.get("case_subtype"),
            "final_recommended_queue": event.get("recommended_queue"),
            "final_correct_action": event.get("correct_action"),
            "merge_reason": "ai_output_invalid_deterministic_result_preserved",
            "warnings": ["AI output was unparseable; deterministic result preserved"],
        }
        return {
            "request": request_artifact,
            "decision": decision,
            "result": result,
        }

    validated = _validate_ai_output(parsed)
    ai_confidence = validated.get("confidence", 0.0)

    decision = {
        "event_id": event.get("event_id", ""),
        "status": "ok" if ai_confidence >= min_ai_confidence else "low_confidence",
        "validated_output": validated,
        "ai_case_type": validated.get("case_type"),
        "case_subtype": validated.get("case_subtype"),
        "recommended_queue": validated.get("recommended_queue"),
        "correct_action": validated.get("correct_action"),
        "should_rop_see": validated.get("should_rop_see"),
        "ai_confidence": ai_confidence,
        "risk_flags": validated.get("risk_flags", []),
    }

    if ai_confidence >= min_ai_confidence and not validated.get("risk_flags"):
        merge_reason = "validated_ai_assist_for_fallback_case"
        ai_assist_status = "ok"
        final_case_type = validated.get("case_type") or event.get(
            "case_type", "unknown"
        )
        final_subtype = validated.get("case_subtype") or event.get("case_subtype")
        final_queue = validated.get("recommended_queue") or event.get(
            "recommended_queue"
        )
        final_action = validated.get("correct_action") or event.get("correct_action")
    else:
        merge_reason = (
            "ai_confidence_below_threshold"
            if ai_confidence < min_ai_confidence
            else "ai_output_risk_flags_deterministic_result_preserved"
        )
        ai_assist_status = (
            "low_confidence" if ai_confidence < min_ai_confidence else "blocked"
        )
        final_case_type = event.get("case_type", "unknown")
        final_subtype = event.get("case_subtype")
        final_queue = event.get("recommended_queue")
        final_action = event.get("correct_action")

    result = {
        "event_id": event.get("event_id", ""),
        "ai_assist_used": ai_assist_status in ("ok", "low_confidence"),
        "ai_assist_status": ai_assist_status,
        "final_case_type": final_case_type,
        "final_case_subtype": final_subtype,
        "final_recommended_queue": final_queue,
        "final_correct_action": final_action,
        "merge_reason": merge_reason,
        "warnings": validated.get("warnings", []),
    }

    return {
        "request": request_artifact,
        "decision": decision,
        "result": result,
    }


def write_ai_assist_artifacts(
    storage_dir: Path,
    run_id: str,
    requests: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    results: list[dict[str, Any]],
    counters: dict[str, int],
    logger: logging.Logger,
) -> list[str]:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    refs: list[str] = []

    requests_path = run_dir / "rop_ai_assist_requests.json"
    requests_data = {
        "run_id": run_id,
        "counters": counters,
        "requests": requests,
    }
    requests_path.write_text(
        json.dumps(requests_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    refs.append(str(requests_path.relative_to(storage_dir)))
    logger.info(
        "rop_ai_assist_requests written: run_id=%s requests=%d",
        run_id,
        len(requests),
    )

    decisions_path = run_dir / "rop_ai_assist_decisions.json"
    decisions_data = {
        "run_id": run_id,
        "counters": counters,
        "decisions": decisions,
    }
    decisions_path.write_text(
        json.dumps(decisions_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    refs.append(str(decisions_path.relative_to(storage_dir)))

    results_path = run_dir / "rop_ai_assist_results.json"
    results_data = {
        "run_id": run_id,
        "counters": counters,
        "results": results,
    }
    results_path.write_text(
        json.dumps(results_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    refs.append(str(results_path.relative_to(storage_dir)))
    logger.info(
        "rop_ai_assist_results written: run_id=%s results=%d status_ok=%d degraded=%d invalid=%d",
        run_id,
        len(results),
        counters.get("ai_assist_used_count", 0),
        counters.get("ai_assist_degraded_count", 0),
        counters.get("ai_assist_invalid_count", 0),
    )

    return refs
