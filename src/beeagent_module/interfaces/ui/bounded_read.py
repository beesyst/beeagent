from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MAX_JSON_BYTES = 512 * 1024  # 512 KB
MAX_JSONL_LINES = 1000
MAX_TSV_BYTES = 512 * 1024
MAX_TEXT_BYTES = 128 * 1024

SENSITIVE_KEY_PATTERNS = frozenset(
    {
        "password",
        "password_env",
        "secret",
        "token",
        "api_key",
        "api_secret",
        "auth_token",
        "session_secret",
        "private_key",
        "raw_eml",
        "content_bytes",
        "payload_bytes",
        "attachment_content",
    }
)
RAW_CONTENT_KEYS = frozenset({"content", "raw_eml", "content_bytes", "payload_bytes"})


# Чек, следует ли удалить ключ словаря
def _is_sensitive_key(key: str) -> bool:
    lower = key.lower().strip()
    return lower in SENSITIVE_KEY_PATTERNS or any(
        pattern in lower for pattern in SENSITIVE_KEY_PATTERNS
    )


# Рекурсивное удаление чувствительных данных из JSON-совместимых структур
def _redact_sensitive_values(data: Any, depth: int = 0) -> Any:
    if depth > 20:
        return str(data)[:200] if data is not None else None

    if isinstance(data, dict):
        result: dict[str, Any] = {}
        for key, value in data.items():
            if _is_sensitive_key(key) or key in RAW_CONTENT_KEYS:
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_sensitive_values(value, depth + 1)
        return result

    if isinstance(data, list):
        return [_redact_sensitive_values(item, depth + 1) for item in data]

    return data


# Чтение JSON-артефакта с ограничением размера, предупреждением о некорректности и редактированием
def read_bounded_json(path: Path) -> tuple[str | None, str | None, str | None]:
    if not path.exists():
        return None, None, "missing"

    stat = path.stat()
    if stat.st_size > MAX_JSON_BYTES:
        return (
            None,
            f"JSON artifact too large ({stat.st_size} bytes, max {MAX_JSON_BYTES})",
            None,
        )

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        redacted = _redact_sensitive_values(data)
        preview = json.dumps(redacted, indent=2, ensure_ascii=False)
        if len(preview) > MAX_JSON_BYTES:
            preview = preview[: MAX_JSON_BYTES - 1] + "\n…"
        return preview, None, None
    except json.JSONDecodeError as exc:
        return None, f"Malformed JSON: {exc}", None
    except OSError as exc:
        return None, None, f"Read error: {exc}"


# Чтение JSONL-артефакта с ограничением количества строк, предупреждением о некорректности и редактированием
def read_bounded_jsonl(path: Path) -> tuple[str | None, str | None, str | None]:
    if not path.exists():
        return None, None, "missing"

    lines: list[str] = []
    warning: str | None = None
    try:
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= MAX_JSONL_LINES:
                    warning = f"Truncated at {MAX_JSONL_LINES} lines"
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                    redacted = _redact_sensitive_values(obj)
                    lines.append(json.dumps(redacted, ensure_ascii=False))
                except json.JSONDecodeError:
                    lines.append(f"# malformed line {i}: {stripped[:200]}")
        result = "\n".join(lines)
        return result, warning, None
    except OSError as exc:
        return None, None, f"Read error: {exc}"


# Чтение TSV-артефакта с ограничением размера и предупреждением о некорректности
def read_bounded_tsv(path: Path) -> tuple[str | None, str | None, str | None]:
    if not path.exists():
        return None, None, "missing"

    stat = path.stat()
    if stat.st_size > MAX_TSV_BYTES:
        return (
            None,
            f"TSV artifact too large ({stat.st_size} bytes, max {MAX_TSV_BYTES})",
            None,
        )

    try:
        text = path.read_text(encoding="utf-8")
        return text, None, None
    except OSError as exc:
        return None, None, f"Read error: {exc}"


# Чтение текстового артефакта с ограничением размера
def read_bounded_text(path: Path) -> tuple[str | None, str | None, str | None]:
    if not path.exists():
        return None, None, "missing"

    stat = path.stat()
    if stat.st_size > MAX_TEXT_BYTES:
        return (
            None,
            f"Text artifact too large ({stat.st_size} bytes, max {MAX_TEXT_BYTES})",
            None,
        )

    try:
        return path.read_text(encoding="utf-8"), None, None
    except OSError as exc:
        return None, None, f"Read error: {exc}"


# Диспетчер для чтения артефактов с помощью соответствующего ограниченного ридера на основе ID/типа артефакта
def read_artifact_preview(artifact_id: str, artifact_path: Path):
    content_type = _infer_content_type(artifact_id)
    if content_type == "application/json":
        text, warning, error = read_bounded_json(artifact_path)
    elif content_type == "application/jsonl":
        text, warning, error = read_bounded_jsonl(artifact_path)
    elif content_type == "text/tab-separated-values":
        text, warning, error = read_bounded_tsv(artifact_path)
    else:
        text, warning, error = read_bounded_text(artifact_path)

    return text, warning, error


# Получение типа содержимого для разрешенного артефакта
def _infer_content_type(artifact_id: str) -> str:
    if artifact_id.endswith("_json") or artifact_id.endswith("_result_json"):
        return "application/json"
    if artifact_id.endswith("_tsv"):
        return "text/tab-separated-values"
    if artifact_id.endswith("_jsonl"):
        return "application/jsonl"
    return "text/plain"
