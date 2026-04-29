from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from beeagent_module.core.module_contract import AuthorityLevel


# Контракты для описания запроса и результата при вызове capability
class CapabilityStatus(str, Enum):
    OK = "ok"
    REFUSED = "refused"
    TIMEOUT = "timeout"
    ERROR = "error"


# Контракты для описания запроса и результата при вызове capability
@dataclass(frozen=True)
class CapabilityRequest:
    capability_name: str
    authority: AuthorityLevel
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    session_id: str = ""
    module_id: str = ""
    case_type: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.capability_name, str) or not self.capability_name:
            raise ValueError("capability_name must be a non-empty string")
        if not isinstance(self.authority, AuthorityLevel):
            raise ValueError("authority must be an AuthorityLevel enum value")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dict")


# Контракты для описания запроса и результата при вызове capability
@dataclass(frozen=True)
class CapabilityResult:
    capability_name: str
    status: CapabilityStatus
    authority: AuthorityLevel
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
