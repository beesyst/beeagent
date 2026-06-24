from __future__ import annotations

import logging
import sys
import types
from pathlib import Path

from beeagent_module.core.module_contract import (
    AuthorityLevel,
    ModuleContext,
    ModuleResult,
)
from beeagent_module.core.module_registry import ModuleRegistry, ModuleState


class _StubValidModule:
    @property
    def module_id(self) -> str:
        return "stub-valid"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.READ_ONLY

    def supported_case_types(self) -> list[str]:
        return ["stub_case"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="ok",
            summary="stub result",
        )


class _StubInvalidModule:
    @property
    def module_id(self) -> str:
        return "stub-invalid"

    def supported_case_types(self) -> list[str]:
        return []

    def handle(self, context: ModuleContext) -> ModuleResult:  # type: ignore[return]
        pass


def _make_fake_package(
    name: str, entry_attr: str, entry_value: object
) -> types.ModuleType:
    pkg = types.ModuleType(name)
    setattr(pkg, entry_attr, entry_value)
    sys.modules[name] = pkg
    return pkg


def _remove_fake_package(name: str) -> None:
    sys.modules.pop(name, None)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_registry_null")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_registry_registered_module() -> None:
    pkg_name = "_test_stub_valid_pkg"
    entry_name = "ValidModule"
    _make_fake_package(pkg_name, entry_name, _StubValidModule)

    try:
        config = [
            {
                "id": "stub-valid",
                "package": pkg_name,
                "entry": entry_name,
                "enabled": True,
            }
        ]
        registry = ModuleRegistry(config=config, logger=_null_logger())

        assert registry.loaded_ids() == ["stub-valid"]

        diag = registry.diagnostics()
        assert len(diag) == 1
        assert diag[0]["state"] == ModuleState.LOADED.value
        assert "error" not in diag[0]

        module = registry.get("stub-valid")
        assert module is not None
        assert module.module_id == "stub-valid"
        assert module.supported_case_types() == ["stub_case"]
    finally:
        _remove_fake_package(pkg_name)


def test_registry_missing_module() -> None:
    config = [
        {
            "id": "nonexistent-module",
            "package": "_nonexistent_pkg_xyz",
            "entry": "SomeClass",
            "enabled": True,
        }
    ]
    registry = ModuleRegistry(config=config, logger=_null_logger())

    assert registry.loaded_ids() == []
    assert registry.get("nonexistent-module") is None

    diag = registry.diagnostics()
    assert len(diag) == 1
    assert diag[0]["state"] == ModuleState.MISSING.value
    assert "error" in diag[0]


def test_registry_disabled_module() -> None:
    config = [
        {
            "id": "stub-disabled",
            "package": "_nonexistent_disabled_pkg",
            "entry": "SomeClass",
            "enabled": False,
        }
    ]
    registry = ModuleRegistry(config=config, logger=_null_logger())

    assert registry.loaded_ids() == []
    assert registry.get("stub-disabled") is None

    diag = registry.diagnostics()
    assert len(diag) == 1
    assert diag[0]["state"] == ModuleState.DISABLED.value
    assert "error" not in diag[0]


def test_registry_invalid_contract() -> None:
    pkg_name = "_test_stub_invalid_pkg"
    entry_name = "InvalidModule"
    _make_fake_package(pkg_name, entry_name, _StubInvalidModule)

    try:
        config = [
            {
                "id": "stub-invalid",
                "package": pkg_name,
                "entry": entry_name,
                "enabled": True,
            }
        ]
        registry = ModuleRegistry(config=config, logger=_null_logger())

        assert registry.loaded_ids() == []
        assert registry.get("stub-invalid") is None

        diag = registry.diagnostics()
        assert len(diag) == 1
        assert diag[0]["state"] == ModuleState.INVALID.value
        assert "error" in diag[0]
    finally:
        _remove_fake_package(pkg_name)


def test_registry_missing_entry_attribute() -> None:
    pkg_name = "_test_stub_no_entry_pkg"
    _make_fake_package(pkg_name, "other_attr", object())

    try:
        config = [
            {
                "id": "stub-no-entry",
                "package": pkg_name,
                "entry": "NonExistentEntry",
                "enabled": True,
            }
        ]
        registry = ModuleRegistry(config=config, logger=_null_logger())

        diag = registry.diagnostics()
        assert diag[0]["state"] == ModuleState.INVALID.value
        assert "error" in diag[0]
    finally:
        _remove_fake_package(pkg_name)


def test_registry_diagnostics_artifact(tmp_path: Path) -> None:
    pkg_name = "_test_stub_artifact_pkg"
    _make_fake_package(pkg_name, "ValidModule", _StubValidModule)

    try:
        config = [
            {
                "id": "stub-valid",
                "package": pkg_name,
                "entry": "ValidModule",
                "enabled": True,
            },
            {
                "id": "stub-disabled",
                "package": "_nonexistent_disabled",
                "entry": "X",
                "enabled": False,
            },
        ]
        registry = ModuleRegistry(config=config, logger=_null_logger())
        registry.write_diagnostics_artifact(tmp_path)

        artifact_path = tmp_path / "interfaces" / "modules.json"
        assert artifact_path.exists()

        import json

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert "registry" in data
        assert len(data["registry"]) == 2

        states = {item["id"]: item["state"] for item in data["registry"]}
        assert states["stub-valid"] == "loaded"
        assert states["stub-disabled"] == "disabled"
    finally:
        _remove_fake_package(pkg_name)


def test_registry_mixed_states() -> None:
    pkg_name = "_test_stub_mixed_valid"
    _make_fake_package(pkg_name, "ValidModule", _StubValidModule)

    try:
        config = [
            {
                "id": "m-loaded",
                "package": pkg_name,
                "entry": "ValidModule",
                "enabled": True,
            },
            {
                "id": "m-disabled",
                "package": "_nonexistent_x",
                "entry": "X",
                "enabled": False,
            },
            {
                "id": "m-missing",
                "package": "_nonexistent_y",
                "entry": "Y",
                "enabled": True,
            },
        ]
        registry = ModuleRegistry(config=config, logger=_null_logger())

        assert registry.loaded_ids() == ["m-loaded"]
        assert registry.get("m-loaded") is not None
        assert registry.get("m-disabled") is None
        assert registry.get("m-missing") is None

        diag_by_id = {d["id"]: d["state"] for d in registry.diagnostics()}
        assert diag_by_id["m-loaded"] == "loaded"
        assert diag_by_id["m-disabled"] == "disabled"
        assert diag_by_id["m-missing"] == "missing"
    finally:
        _remove_fake_package(pkg_name)
