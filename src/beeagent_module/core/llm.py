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

    api_key_env = llm_cfg.get("api_key_env")
    if not isinstance(api_key_env, str) or not api_key_env:
        if logger:
            logger.warning("llm api_key_env missing, fallback to rules-only summary")
        return None

    api_key = os.getenv(api_key_env, "")
    if not api_key:
        if logger:
            logger.warning("llm api key missing, fallback to rules-only summary")
        return None

    provider = llm_cfg.get("provider")
    model = llm_cfg.get("model")
    api_url = llm_cfg.get("api_url")
    if not isinstance(api_url, str) or not api_url:
        if logger:
            logger.warning("llm api_url missing, fallback to rules-only summary")
        return None
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

    temperature = llm_cfg.get("temperature")
    if not isinstance(temperature, (int, float)):
        if logger:
            logger.warning(
                "llm temperature missing/invalid, fallback to rules-only summary"
            )
        return None

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": "You summarize recommendations."},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(temperature),
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
        with request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)

        # Responses API: приоритет - output_text
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        # фоллбек: пробуем собрать текст из output[*].content[*].text
        output = data.get("output", [])
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content", [])
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    text = c.get("text")
                    if isinstance(text, str) and text.strip():
                        chunks.append(text.strip())
            if chunks:
                return "\n".join(chunks)

        if logger:
            logger.warning("llm response has no output_text, fallback to rules-only")
        return None
    except Exception:
        if logger:
            logger.exception("llm request failed, fallback to rules-only")
        return None
