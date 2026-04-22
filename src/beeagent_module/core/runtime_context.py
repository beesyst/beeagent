from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from beeagent_module.core.module_contract import AuthorityLevel


# Содержит определение RuntimeContext, который является минимальным контекстом исполнения, передаваемым от ядра BeeAgent в модули
@dataclass(frozen=True)
class RuntimeContext:
    run_id: str
    session_id: str
    case_type: str
    module_id: str
    authority: AuthorityLevel
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be a non-empty string")
        if not isinstance(self.case_type, str) or not self.case_type:
            raise ValueError("case_type must be a non-empty string")
        if not isinstance(self.module_id, str) or not self.module_id:
            raise ValueError("module_id must be a non-empty string")
        if not isinstance(self.authority, AuthorityLevel):
            raise ValueError("authority must be an AuthorityLevel enum value")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")


# Генерация уникальных идентификаторов run_id и session_id с опциональными префиксами для лучшей читаемости и организации артефактов
def generate_run_id(prefix: str = "run") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


# Генерация уникальных идентификаторов run_id и session_id с опциональными префиксами для лучшей читаемости и организации артефактов
def generate_session_id(prefix: str = "session") -> str:
    return f"{prefix}-{uuid4().hex[:12]}"
