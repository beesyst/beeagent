import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib import request

import yaml

from beeagent_module.core.paths import get_project_root

OOS_SUMMARY_PROMPT_KEY = "oos.llm_summary"


# Функция для получения объяснения рекомендаций с помощью LLM (например, OpenAI)
class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


# Резолв относительного пути к конфигу от корня проекта.
def _resolve_config_path(path: str) -> Path:
    path_value = Path(path)
    if path_value.is_absolute():
        return path_value
    return get_project_root() / path_value


# Получение вложенного значения по пути ключей.
def _get_nested_value(payload: dict[str, Any], key_path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in key_path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


# Загрузка промптов из YAML и проверка структуры.
def _load_prompts(path: str) -> dict[str, Any]:
    file_path = _resolve_config_path(path)
    if not file_path.exists():
        raise RuntimeError(f"Prompts file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)

    if not isinstance(content, dict):
        raise RuntimeError("Prompts file must contain a top-level mapping")

    return content


# Подготовка system/user промптов по ключу и шаблону.
def _build_prompt_messages(
    llm_cfg: dict[str, Any], recommendations: list[dict[str, Any]]
) -> tuple[str, str]:
    prompts_path = llm_cfg.get("prompts_path")
    if not isinstance(prompts_path, str) or not prompts_path:
        raise RuntimeError("Invalid llm.prompts_path, expected non-empty string")

    prompt_key = OOS_SUMMARY_PROMPT_KEY

    prompts = _load_prompts(prompts_path)
    prompt_payload = _get_nested_value(prompts, tuple(prompt_key.split(".")))
    if not isinstance(prompt_payload, dict):
        raise RuntimeError(f"Prompt key not found in prompts file: {prompt_key}")

    system_template = prompt_payload.get("system")
    user_template = prompt_payload.get("user")
    if not isinstance(system_template, str) or not system_template:
        raise RuntimeError(f"Prompt '{prompt_key}.system' must be a non-empty string")
    if not isinstance(user_template, str) or not user_template:
        raise RuntimeError(f"Prompt '{prompt_key}.user' must be a non-empty string")

    recommendations_json = json.dumps(recommendations, ensure_ascii=False)

    # Render template safely. Unknown placeholders are preserved.
    user_prompt = user_template.format_map(
        _SafeDict(recommendations_json=recommendations_json)
    )

    # If template still contains placeholders, fallback to a minimal prompt.
    if "{" in user_prompt and "}" in user_prompt:
        user_prompt = (
            "Summarize the recommendations below into 5-10 lines. "
            "Use plain operational language without ML terms. Do not change any numbers.\n\n"
            f"Recommendations JSON: {recommendations_json}"
        )

    return system_template, user_prompt


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
    throttling = llm_cfg.get("throttling")
    if not isinstance(api_url, str) or not api_url:
        if logger:
            logger.warning("llm api_url missing, fallback to rules-only summary")
        return None
    if not isinstance(throttling, dict):
        if logger:
            logger.warning("llm throttling missing, fallback to rules-only summary")
        return None

    timeout = throttling.get("timeout")
    retries = throttling.get("retries")
    if not isinstance(timeout, int) or timeout <= 0:
        if logger:
            logger.warning("llm throttling.timeout invalid, fallback to rules-only")
        return None
    if not isinstance(retries, int) or retries < 0:
        if logger:
            logger.warning("llm throttling.retries invalid, fallback to rules-only")
        return None

    if provider != "openai":
        if logger:
            logger.warning(
                "unsupported llm provider=%s, fallback to rules-only", provider
            )
        return None

    system_prompt, user_prompt = _build_prompt_messages(llm_cfg, recommendations)

    payload = {
        "model": model,
        "input": [
            {
                "type": "message",
                "role": "developer",
                "content": system_prompt,
            },
            {
                "type": "message",
                "role": "user",
                "content": user_prompt,
            },
        ],
    }

    # Выполнение запроса с retry только для timeout ошибок.
    for attempt in range(retries + 1):
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
            with request.urlopen(req, timeout=timeout) as response:
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
                        alt_text = c.get("output_text")
                        if isinstance(alt_text, str) and alt_text.strip():
                            chunks.append(alt_text.strip())
                            continue

                        text = c.get("text")
                        if isinstance(text, str) and text.strip():
                            chunks.append(text.strip())
                if chunks:
                    return "\n".join(chunks)

            if logger:
                logger.warning(
                    "llm response has no output_text, fallback to rules-only"
                )
            return None
        except TimeoutError:
            if attempt < retries:
                if logger:
                    logger.warning("llm timeout, retry %s/%s", attempt + 1, retries)
                continue
            if logger:
                logger.warning("llm timeout after retries, fallback to rules-only")
            return None
        except request.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = "<unable to read error body>"
            if logger:
                logger.error(
                    "llm http error status=%s body=%s, fallback to rules-only",
                    exc.code,
                    body,
                )
            return None
        except Exception:
            if logger:
                logger.exception("llm request failed, fallback to rules-only")
            return None

    return None
