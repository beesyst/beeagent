from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from beeagent_module.core.module_contract import ModuleContract


class ModuleState(str, Enum):
    LOADED = "loaded"
    DISABLED = "disabled"
    MISSING = "missing"
    INVALID = "invalid"


@dataclass
class ModuleEntry:
    id: str
    package: str
    entry: str
    enabled: bool
    state: ModuleState
    instance: Any | None = field(default=None, repr=False)
    error: str | None = None


class ModuleRegistry:
    def __init__(self, config: list[dict], logger: logging.Logger) -> None:
        self._logger = logger
        self._entries: list[ModuleEntry] = []
        self._load(config)

    def _load(self, config: list[dict]) -> None:
        for item in config:
            mod_id: str = item["id"]
            package: str = item["package"]
            entry: str = item["entry"]
            enabled: bool = item["enabled"]

            if not enabled:
                self._entries.append(
                    ModuleEntry(
                        id=mod_id,
                        package=package,
                        entry=entry,
                        enabled=False,
                        state=ModuleState.DISABLED,
                    )
                )
                self._logger.info("module disabled: id=%s package=%s", mod_id, package)
                continue

            try:
                pkg = importlib.import_module(package)
            except ImportError as exc:
                self._entries.append(
                    ModuleEntry(
                        id=mod_id,
                        package=package,
                        entry=entry,
                        enabled=True,
                        state=ModuleState.MISSING,
                        error=str(exc),
                    )
                )
                self._logger.warning(
                    "module missing: id=%s package=%s error=%s",
                    mod_id,
                    package,
                    exc,
                )
                continue

            try:
                attr = getattr(pkg, entry)
            except AttributeError as exc:
                error = f"package '{package}' does not expose entry '{entry}': {exc}"
                self._entries.append(
                    ModuleEntry(
                        id=mod_id,
                        package=package,
                        entry=entry,
                        enabled=True,
                        state=ModuleState.INVALID,
                        error=error,
                    )
                )
                self._logger.warning(
                    "module invalid: id=%s package=%s reason=%s",
                    mod_id,
                    package,
                    error,
                )
                continue

            try:
                instance = attr() if callable(attr) else attr
            except Exception as exc:  # noqa: BLE001
                error = f"failed to instantiate entry '{entry}' from '{package}': {exc}"
                self._entries.append(
                    ModuleEntry(
                        id=mod_id,
                        package=package,
                        entry=entry,
                        enabled=True,
                        state=ModuleState.INVALID,
                        error=error,
                    )
                )
                self._logger.warning(
                    "module invalid: id=%s package=%s reason=%s",
                    mod_id,
                    package,
                    error,
                )
                continue

            if not isinstance(instance, ModuleContract):
                error = (
                    f"module '{mod_id}' entry '{entry}' does not satisfy ModuleContract"
                    " (missing required properties or methods)"
                )
                self._entries.append(
                    ModuleEntry(
                        id=mod_id,
                        package=package,
                        entry=entry,
                        enabled=True,
                        state=ModuleState.INVALID,
                        instance=None,
                        error=error,
                    )
                )
                self._logger.warning(
                    "module invalid: id=%s package=%s reason=%s",
                    mod_id,
                    package,
                    error,
                )
                continue

            self._entries.append(
                ModuleEntry(
                    id=mod_id,
                    package=package,
                    entry=entry,
                    enabled=True,
                    state=ModuleState.LOADED,
                    instance=instance,
                )
            )
            self._logger.info(
                "module loaded: id=%s package=%s authority=%s case_types=%s",
                mod_id,
                package,
                instance.authority.value,
                instance.supported_case_types(),
            )

    def get(self, module_id: str) -> ModuleContract | None:
        for entry in self._entries:
            if entry.id == module_id and entry.state == ModuleState.LOADED:
                return entry.instance
        return None

    def loaded_ids(self) -> list[str]:
        return [e.id for e in self._entries if e.state == ModuleState.LOADED]

    def diagnostics(self) -> list[dict]:
        result = []
        for e in self._entries:
            item: dict = {
                "id": e.id,
                "package": e.package,
                "entry": e.entry,
                "state": e.state.value,
            }
            if e.error:
                item["error"] = e.error
            result.append(item)
        return result

    def write_diagnostics_artifact(self, storage_dir: Path) -> None:
        interfaces_dir = storage_dir / "interfaces"
        interfaces_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = interfaces_dir / "modules.json"
        artifact = {"registry": self.diagnostics()}
        with artifact_path.open("w", encoding="utf-8") as fh:
            json.dump(artifact, fh, indent=2, ensure_ascii=False)
        self._logger.info(
            "registry diagnostics artifact written: path=%s", artifact_path
        )


def build_registry(settings: dict, logger: logging.Logger) -> ModuleRegistry:
    from beeagent_module.core.paths import (
        get_storage_dir,
    )

    mod_cfg: dict = settings["modules"]
    registry_cfg: list[dict] = mod_cfg["registry"]

    registry = ModuleRegistry(config=registry_cfg, logger=logger)

    loaded = registry.loaded_ids()
    logger.info(
        "module registry initialized: loaded=%s total_declared=%d",
        loaded,
        len(registry_cfg),
    )

    registry.write_diagnostics_artifact(get_storage_dir())

    return registry
