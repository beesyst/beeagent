from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from beeagent_module.core.capability_contract import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
)
from beeagent_module.core.module_contract import AuthorityLevel

CapabilityHandler = Callable[[CapabilityRequest], dict]


@dataclass(frozen=True)
class CapabilityEntry:
    name: str
    handler: CapabilityHandler
    required_authority: AuthorityLevel
    enabled: bool = True


class LocalCapabilityRuntime:
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._entries: dict[str, CapabilityEntry] = {}

    def register(
        self,
        name: str,
        handler: CapabilityHandler,
        required_authority: AuthorityLevel = AuthorityLevel.READ_ONLY,
        enabled: bool = True,
    ) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("Capability name must be a non-empty string")
        if not callable(handler):
            raise ValueError("Capability handler must be callable")
        if not isinstance(required_authority, AuthorityLevel):
            raise ValueError("required_authority must be an AuthorityLevel enum value")

        self._entries[name] = CapabilityEntry(
            name=name,
            handler=handler,
            required_authority=required_authority,
            enabled=enabled,
        )
        self._logger.info(
            "capability registered: name=%s enabled=%s required_authority=%s",
            name,
            enabled,
            required_authority.value,
        )

    def call(self, request: CapabilityRequest) -> CapabilityResult:
        entry = self._entries.get(request.capability_name)
        if entry is None:
            self._logger.warning(
                "capability refused: reason=unknown capability=%s module_id=%s run_id=%s",
                request.capability_name,
                request.module_id,
                request.run_id,
            )
            return CapabilityResult(
                capability_name=request.capability_name,
                status=CapabilityStatus.REFUSED,
                authority=request.authority,
                summary="Capability is not declared in runtime",
                diagnostics={"reason": "unknown_capability"},
            )

        if not entry.enabled:
            self._logger.warning(
                "capability refused: reason=disabled capability=%s module_id=%s run_id=%s",
                request.capability_name,
                request.module_id,
                request.run_id,
            )
            return CapabilityResult(
                capability_name=request.capability_name,
                status=CapabilityStatus.REFUSED,
                authority=request.authority,
                summary="Capability is disabled",
                diagnostics={"reason": "capability_disabled"},
            )

        if not _is_authority_sufficient(request.authority, entry.required_authority):
            self._logger.warning(
                "capability refused: reason=insufficient_authority capability=%s provided=%s required=%s module_id=%s run_id=%s",
                request.capability_name,
                request.authority.value,
                entry.required_authority.value,
                request.module_id,
                request.run_id,
            )
            return CapabilityResult(
                capability_name=request.capability_name,
                status=CapabilityStatus.REFUSED,
                authority=request.authority,
                summary="Capability authority is not sufficient",
                diagnostics={
                    "reason": "insufficient_authority",
                    "required_authority": entry.required_authority.value,
                },
            )

        self._logger.info(
            "capability call started: capability=%s module_id=%s run_id=%s authority=%s",
            request.capability_name,
            request.module_id,
            request.run_id,
            request.authority.value,
        )
        try:
            result_data = entry.handler(request)
            if not isinstance(result_data, dict):
                raise ValueError("Capability handler must return a dict")

            self._logger.info(
                "capability call finished: capability=%s module_id=%s run_id=%s status=%s",
                request.capability_name,
                request.module_id,
                request.run_id,
                CapabilityStatus.OK.value,
            )
            return CapabilityResult(
                capability_name=request.capability_name,
                status=CapabilityStatus.OK,
                authority=request.authority,
                summary="Capability call completed",
                data=result_data,
            )
        except TimeoutError:
            self._logger.warning(
                "capability call timeout: capability=%s module_id=%s run_id=%s",
                request.capability_name,
                request.module_id,
                request.run_id,
            )
            return CapabilityResult(
                capability_name=request.capability_name,
                status=CapabilityStatus.TIMEOUT,
                authority=request.authority,
                summary="Capability call timed out",
                diagnostics={"reason": "timeout"},
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception(
                "capability call error: capability=%s module_id=%s run_id=%s error_type=%s",
                request.capability_name,
                request.module_id,
                request.run_id,
                type(exc).__name__,
            )
            return CapabilityResult(
                capability_name=request.capability_name,
                status=CapabilityStatus.ERROR,
                authority=request.authority,
                summary="Capability call failed",
                diagnostics={
                    "reason": "exception",
                    "error_type": type(exc).__name__,
                },
            )

    def diagnostics(self) -> list[dict]:
        items = []
        for name, entry in sorted(self._entries.items()):
            items.append(
                {
                    "name": name,
                    "enabled": entry.enabled,
                    "required_authority": entry.required_authority.value,
                }
            )
        return items

    def write_diagnostics_artifact(self, storage_dir: Path) -> Path:
        interfaces_dir = storage_dir / "interfaces"
        interfaces_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = interfaces_dir / "capabilities.json"
        with artifact_path.open("w", encoding="utf-8") as fh:
            json.dump(
                {"capabilities": self.diagnostics()}, fh, indent=2, ensure_ascii=False
            )
        self._logger.info(
            "capability diagnostics artifact written: path=%s",
            artifact_path,
        )
        return artifact_path


_AUTHORITY_RANK = {
    AuthorityLevel.READ_ONLY: 1,
    AuthorityLevel.DRAFT_ONLY: 2,
    AuthorityLevel.EXECUTION_CAPABLE: 3,
}


def _is_authority_sufficient(
    provided: AuthorityLevel,
    required: AuthorityLevel,
) -> bool:
    return _AUTHORITY_RANK[provided] >= _AUTHORITY_RANK[required]
