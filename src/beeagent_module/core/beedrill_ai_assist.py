from __future__ import annotations

import json
import os
from typing import Any

import yaml

from beeagent_module.core.ai_transport import call_structured_ai
from beeagent_module.core.paths import get_project_root


def run_beedrill_ai_assist(
    *,
    settings: dict[str, Any],
    records: list[dict[str, object]],
    suite_run_id: str,
    logger: Any,
) -> dict[str, object]:
    cfg = settings["beedrill"]["ai_assist"]
    facts = [record["explanation_facts"] for record in records]
    provenance = [
        {"scenario_id": record["scenario_id"], "run_id": record["run_id"]}
        for record in records
    ]
    artifact: dict[str, object] = {
        "schema_version": 1,
        "status": "degraded",
        "suite_run_id": suite_run_id,
        "source_scenarios": provenance,
        "provider": None,
        "model": None,
    }
    if any(not isinstance(item, dict) for item in facts):
        artifact["reason"] = "completed_suite_missing_explanation_facts"
        return artifact
    try:
        profile = _active_profile(settings)
        prompt = _prompt(settings, cfg["prompt_key"], facts, cfg["input_chars_max"])
        artifact["provider"] = profile["provider"]
        artifact["model"] = profile["model"]
        raw = call_structured_ai(
            prompt=prompt,
            provider=profile["provider"],
            model=profile["model"],
            api_key=os.getenv(profile["api_key_env"], ""),
            base_url=profile["base_url"],
            timeout_seconds=cfg["timeout"],
            max_output_tokens=max(1, cfg["output_chars_max"] // 4),
            temperature=0.0,
            responses_text_format=_response_format(),
            output_chars_max=cfg["output_chars_max"],
            logger=logger,
        )
        response = _response(raw, cfg["output_chars_max"])
    except (KeyError, OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        logger.warning("BeeDrill AI assist degraded: %s", exc)
        artifact["reason"] = "provider_or_response_unavailable"
        return artifact
    if response is None:
        artifact["reason"] = "provider_or_response_unavailable"
        return artifact
    artifact["status"] = "ok"
    artifact["response"] = response
    return artifact


def _active_profile(settings: dict[str, Any]) -> dict[str, str]:
    profiles = settings["ai"]["profiles"]
    enabled = [profile for profile in profiles.values() if profile["enabled"] is True]
    if len(enabled) != 1:
        raise RuntimeError("exactly one AI profile must be enabled")
    profile = enabled[0]
    return {
        key: profile[key] for key in ("provider", "model", "api_key_env", "base_url")
    }


def _prompt(
    settings: dict[str, Any], prompt_key: str, facts: list[object], limit: int
) -> str:
    path = get_project_root() / settings["ai"]["prompts"]["path"]
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    current: object = payload
    for key in prompt_key.split("."):
        if not isinstance(current, dict):
            raise RuntimeError("BeeDrill AI prompt is unavailable")
        current = current.get(key)
    if (
        not isinstance(current, dict)
        or not isinstance(current.get("system"), str)
        or not isinstance(current.get("user"), str)
    ):
        raise RuntimeError("BeeDrill AI prompt is invalid")
    facts_json = json.dumps(
        facts,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    user_prompt = current["user"].replace("{explanation_facts_json}", facts_json)
    prompt = f"System:\n{current['system']}\n\nUser:\n{user_prompt}"
    if len(prompt) > limit:
        raise RuntimeError("BeeDrill explanation facts exceed configured input limit")
    return prompt


def _response(raw: str | None, limit: int) -> dict[str, object] | None:
    if not isinstance(raw, str) or len(raw) > limit:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict) or set(value) != {
        "explanation",
        "remediation",
        "remediation_unverified",
    }:
        return None
    explanation = value["explanation"]
    remediation = value["remediation"]
    if (
        not isinstance(explanation, str)
        or len(explanation) > limit
        or not isinstance(remediation, list)
        or len(remediation) > 5
        or any(not isinstance(item, str) or len(item) > 300 for item in remediation)
        or value["remediation_unverified"] is not True
    ):
        return None
    return value


def _response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "name": "beedrill_ai_assist",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "explanation",
                "remediation",
                "remediation_unverified",
            ],
            "properties": {
                "explanation": {"type": "string"},
                "remediation": {
                    "type": "array",
                    "maxItems": 5,
                    "items": {"type": "string", "maxLength": 300},
                },
                "remediation_unverified": {"type": "boolean", "const": True},
            },
        },
    }
