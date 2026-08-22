from __future__ import annotations

import re
from typing import Any

_MAX_MESSAGE_ID_LENGTH = 320


def normalize_message_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.startswith("<") or stripped.endswith(">"):
        if not (stripped.startswith("<") and stripped.endswith(">")):
            return ""
        if "<" in stripped[1:-1] or ">" in stripped[1:-1]:
            return ""
        candidate = stripped[1:-1]
    else:
        if "<" in stripped or ">" in stripped:
            return ""
        candidate = stripped
    if not candidate:
        return ""
    if len(candidate) > _MAX_MESSAGE_ID_LENGTH:
        return ""
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in candidate):
        return ""
    if any(ch.isspace() for ch in candidate):
        return ""
    if candidate.count("@") != 1:
        return ""
    local, domain = candidate.split("@", 1)
    if not local or not domain:
        return ""
    return candidate


def extract_reference_ids(value: Any) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return []
    stripped = value.strip()
    if "<" in stripped or ">" in stripped:
        tokens = re.findall(r"<([^<>]+)>", stripped)
        if "".join(f"<{token}>" for token in tokens) != "".join(stripped.split()):
            return []
    else:
        tokens = stripped.split()
    result: list[str] = []
    for token in tokens:
        normalized = normalize_message_id(token)
        if normalized and normalized not in result:
            result.append(normalized)
    return result
