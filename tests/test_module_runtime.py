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
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.module_runtime import execute_module_case


class _StubArtifactModule:
    @property
    def module_id(self) -> str:
        return "stub-artifact"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.DRAFT_ONLY

    def supported_case_types(self) -> list[str]:
        return ["lead_classification"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        if context.artifact_api is None:
            raise RuntimeError("artifact_api is required in module context")

        context.artifact_api.write_json(
            "module_output.json",
            {
                "received_run_id": context.run_id,
                "received_session_id": context.session_id,
                "received_case_type": context.case_type,
                "received_module_id": context.module_id,
                "received_authority": context.authority.value
                if context.authority
                else None,
                "input": context.payload,
            },
        )

        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="ok",
            summary="module handled with artifact api",
            data={"handled": True},
        )


class _StubBadResultModule:
    @property
    def module_id(self) -> str:
        return "stub-bad"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.READ_ONLY

    def supported_case_types(self) -> list[str]:
        return ["demo"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(
            module_id="wrong-id",
            case_type=context.case_type,
            authority=self.authority,
            status="ok",
            summary="invalid",
        )


def _make_fake_package(
    name: str,
    entry_attr: str,
    entry_value: object,
) -> types.ModuleType:
    pkg = types.ModuleType(name)
    setattr(pkg, entry_attr, entry_value)
    sys.modules[name] = pkg
    return pkg


def _remove_fake_package(name: str) -> None:
    sys.modules.pop(name, None)


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_module_runtime_null")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def test_execute_module_case_propagates_runtime_context_and_artifacts(
    tmp_path: Path,
) -> None:
    pkg_name = "_test_stub_artifact_module_pkg"
    entry_name = "StubArtifactModule"
    _make_fake_package(pkg_name, entry_name, _StubArtifactModule)

    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "stub-artifact",
                    "package": pkg_name,
                    "entry": entry_name,
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = execute_module_case(
            registry=registry,
            module_id="stub-artifact",
            case_type="lead_classification",
            payload={"lead_id": "L-1"},
            storage_dir=tmp_path,
            logger=_null_logger(),
            run_id="run-test123",
            session_id="session-test123",
        )

        assert result.status == "ok"
        assert result.module_id == "stub-artifact"
        assert result.case_type == "lead_classification"

        module_output_path = (
            tmp_path
            / "runs"
            / "run-test123"
            / "module-stub-artifact"
            / "module_output.json"
        )
        assert module_output_path.exists()

        module_result_path = (
            tmp_path
            / "runs"
            / "run-test123"
            / "module-stub-artifact"
            / "module_result.json"
        )
        assert module_result_path.exists()
    finally:
        _remove_fake_package(pkg_name)


def test_execute_module_case_rejects_unsupported_case_type(tmp_path: Path) -> None:
    pkg_name = "_test_stub_case_mismatch_pkg"
    entry_name = "StubArtifactModule"
    _make_fake_package(pkg_name, entry_name, _StubArtifactModule)

    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "stub-artifact",
                    "package": pkg_name,
                    "entry": entry_name,
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        try:
            execute_module_case(
                registry=registry,
                module_id="stub-artifact",
                case_type="unsupported_case",
                payload={},
                storage_dir=tmp_path,
                logger=_null_logger(),
            )
            assert False, "Expected RuntimeError for unsupported case type"
        except RuntimeError as exc:
            assert "Unsupported case_type" in str(exc)
    finally:
        _remove_fake_package(pkg_name)


def test_execute_module_case_rejects_inconsistent_module_result(tmp_path: Path) -> None:
    pkg_name = "_test_stub_bad_result_pkg"
    entry_name = "StubBadResultModule"
    _make_fake_package(pkg_name, entry_name, _StubBadResultModule)

    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "stub-bad",
                    "package": pkg_name,
                    "entry": entry_name,
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        try:
            execute_module_case(
                registry=registry,
                module_id="stub-bad",
                case_type="demo",
                payload={},
                storage_dir=tmp_path,
                logger=_null_logger(),
            )
            assert False, "Expected RuntimeError for inconsistent module result"
        except RuntimeError as exc:
            assert "inconsistent module_id" in str(exc)
    finally:
        _remove_fake_package(pkg_name)
