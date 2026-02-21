import json
import logging
import os
from typing import Any
from urllib import request


# Функция для получения объяснения рекомендаций с помощью LLM (например, OpenAI)
def explain_recommendations(
    llm_cfg: dict[str, Any],
    recommendations: list[dict[str, Any]],
    logger: logging.Logger | None = None,
) -> str | None:
    if not llm_cfg.get("enabled"):
        return None

    api_key_env = llm_cfg.get("api_key_env", "")
    api_key = os.getenv(api_key_env, "")
    if not api_key:
        if logger:
            logger.warning("llm api key missing, fallback to rules-only summary")
        return None

    provider = llm_cfg.get("provider")
    model = llm_cfg.get("model")
    if provider != "openai":
        if logger:
            logger.warning(
                "unsupported llm provider=%s, fallback to rules-only", provider
            )
        return None

    prompt = (
        "You are an operations analyst. Summarize the recommendations below into 5-10 lines. "
        "Use plain operational language without ML terms. Do not change any numbers.\n\n"
        f"Recommendations JSON: {json.dumps(recommendations, ensure_ascii=False)}"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You summarize recommendations."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }

    try:
        req = request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        choices = data.get("choices", [])
        if not choices:
            if logger:
                logger.warning("llm response has no choices, fallback to rules-only")
            return None
        message = choices[0].get("message", {})
        content = message.get("content", "")
        return content.strip() if content else None
    except Exception:
        if logger:
            logger.exception("llm request failed, fallback to rules-only")
        return None
