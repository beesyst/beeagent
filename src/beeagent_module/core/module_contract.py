from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable


# Модульный контракт для внешних доменных модулей, интегрирующихся с ядром BeeAgent
class AuthorityLevel(str, Enum):
    READ_ONLY = "read_only"
    DRAFT_ONLY = "draft_only"
    EXECUTION_CAPABLE = "execution_capable"


if TYPE_CHECKING:
    from beeagent_module.core.artifact_api import ArtifactAPI


# Контекст, передаваемый в метод handle() модуля, и результат, который он должен возвращать
@dataclass(frozen=True)
class ModuleContext:
    run_id: str
    case_type: str
    module_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    authority: AuthorityLevel | None = None
    artifact_api: "ArtifactAPI | None" = None


# Результат, возвращаемый методом handle() модуля, с ограниченными статусами и данными
@dataclass(frozen=True)
class ModuleResult:
    module_id: str
    case_type: str
    authority: AuthorityLevel
    status: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)


# Контракт, который должен реализовать любой внешний доменный модуль для интеграции с ядром BeeAgent
@runtime_checkable
class ModuleContract(Protocol):
    @property
    def module_id(self) -> str: ...

    @property
    def authority(self) -> AuthorityLevel: ...

    def supported_case_types(self) -> list[str]: ...

    def handle(self, context: ModuleContext) -> ModuleResult: ...
