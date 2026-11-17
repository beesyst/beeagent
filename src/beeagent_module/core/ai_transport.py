from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit

_SUPPORTED_PROVIDERS = frozenset({"openai_responses", "openai_compatible"})


def call_structured_ai(
    *,
    prompt: str,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
    timeout_seconds: int,
    max_output_tokens: int,
    temperature: float,
    responses_text_format: dict[str, object] | None,
    output_chars_max: int | None,
    logger: logging.Logger,
    urlopen: Callable[..., Any] | None = None,
    reasoning_enabled: bool | None = None,
    diagnostics: dict[str, object] | None = None,
) -> str | None:
    if diagnostics is not None:
        diagnostics.clear()
    if (
        provider not in _SUPPORTED_PROVIDERS
        or not api_key.strip()
        or not model.strip()
        or not base_url.strip()
        or max_output_tokens <= 0
    ):
        if diagnostics is not None:
            diagnostics["category"] = "configuration"
        return None
    if provider == "openai_responses":
        api_url = base_url.rstrip("/") + "/responses"
        payload: dict[str, object] = {
            "model": model,
            "input": prompt,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if responses_text_format is not None:
            payload["text"] = {"format": responses_text_format}
    else:
        api_url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
            "response_format": {"type": "json_object"},
        }
    if provider == "openai_compatible":
        if reasoning_enabled is not None:
            payload["reasoning"] = {"enabled": reasoning_enabled}
        if urlsplit(base_url).hostname == "openrouter.ai" and responses_text_format:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    key: responses_text_format[key]
                    for key in ("name", "strict", "schema")
                },
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
        opener = urlopen or request.urlopen
        with opener(req, timeout=timeout_seconds) as response:
            raw = response.read()
            if diagnostics is not None:
                diagnostics["http_status"] = (
                    response.status if hasattr(response, "status") else 200
                )
            data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        category = (
            "refused"
            if isinstance(exc, error.HTTPError)
            and exc.code in {400, 401, 402, 403, 404, 422}
            else "invalid_response"
            if isinstance(exc, (ValueError, UnicodeError))
            else "temporary"
        )
        if diagnostics is not None:
            diagnostics["category"] = category
            if isinstance(exc, error.HTTPError):
                diagnostics["http_status"] = exc.code
        logger.warning("AI provider request failed: category=%s", category)
        return None
    content = _response_content(provider, data)
    category = "invalid_response"
    if provider == "openai_compatible" and isinstance(data, dict):
        choices = data.get("choices")
        first = (
            choices[0]
            if isinstance(choices, list) and choices and isinstance(choices[0], dict)
            else {}
        )
        message = first.get("message")
        if isinstance(message, dict) and message.get("refusal"):
            category = "refused"
            content = None
        elif first.get("finish_reason") == "length":
            category = "output_limit"
            content = None
        if diagnostics is not None and first.get("finish_reason") in {
            "stop",
            "length",
            "content_filter",
            "error",
        }:
            diagnostics["finish_reason"] = first["finish_reason"]
    if not content or (
        output_chars_max is not None and len(content) > output_chars_max
    ):
        if content and output_chars_max is not None and len(content) > output_chars_max:
            category = "output_limit"
        if diagnostics is not None:
            diagnostics["category"] = category
        logger.warning("AI provider response refused: category=%s", category)
        return None
    if diagnostics is not None:
        diagnostics["category"] = "ok"
    return content


def _response_content(provider: str, data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    if provider == "openai_compatible":
        choices = data.get("choices")
        if (
            not isinstance(choices, list)
            or not choices
            or not isinstance(choices[0], dict)
        ):
            return None
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        return content if isinstance(content, str) else None
    output = data.get("output")
    if not isinstance(output, list):
        return None
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        parts.extend(
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
        )
    return "".join(parts)
