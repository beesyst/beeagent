from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import ModuleContext, ModuleResult
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)


# Явный core-path исполнения модуля: собирает RuntimeContext, прокидывает его в ModuleContext и связывает module outputs с run_id
def execute_module_case(
    registry: ModuleRegistry,
    module_id: str,
    case_type: str,
    payload: dict[str, Any],
    storage_dir: Path,
    logger: logging.Logger,
    run_id: str | None = None,
    session_id: str | None = None,
) -> ModuleResult:
    module = registry.get(module_id)
    if module is None:
        raise RuntimeError(f"Module is not loaded or unknown: {module_id}")

    if case_type not in module.supported_case_types():
        raise RuntimeError(
            f"Unsupported case_type '{case_type}' for module '{module_id}'"
        )

    effective_run_id = run_id or generate_run_id()
    effective_session_id = session_id or generate_session_id()

    runtime_context = RuntimeContext(
        run_id=effective_run_id,
        session_id=effective_session_id,
        case_type=case_type,
        module_id=module_id,
        authority=module.authority,
        payload=payload,
    )

    artifact_api = ArtifactAPI(
        context=runtime_context,
        storage_dir=storage_dir,
        logger=logger,
    )

    logger.info(
        "module execution started: module_id=%s case_type=%s run_id=%s session_id=%s authority=%s artifact_dir=%s",
        module_id,
        case_type,
        runtime_context.run_id,
        runtime_context.session_id,
        runtime_context.authority.value,
        artifact_api.artifact_dir().relative_to(storage_dir),
    )

    module_context = ModuleContext(
        run_id=runtime_context.run_id,
        case_type=runtime_context.case_type,
        module_id=runtime_context.module_id,
        payload=runtime_context.payload,
        session_id=runtime_context.session_id,
        authority=runtime_context.authority,
        artifact_api=artifact_api,
    )

    result = module.handle(module_context)

    if result.module_id != module_id:
        raise RuntimeError(
            "Module returned inconsistent module_id: "
            f"expected '{module_id}', got '{result.module_id}'"
        )

    if result.case_type != case_type:
        raise RuntimeError(
            "Module returned inconsistent case_type: "
            f"expected '{case_type}', got '{result.case_type}'"
        )

    if result.authority != module.authority:
        raise RuntimeError(
            "Module returned inconsistent authority: "
            f"expected '{module.authority.value}', got '{result.authority.value}'"
        )

    artifact_api.write_json(
        "module_result.json",
        {
            "run_id": runtime_context.run_id,
            "session_id": runtime_context.session_id,
            "module_id": result.module_id,
            "case_type": result.case_type,
            "authority": result.authority.value,
            "status": result.status,
            "summary": result.summary,
            "data": result.data,
        },
    )

    logger.info(
        "module execution finished: module_id=%s case_type=%s run_id=%s status=%s",
        result.module_id,
        result.case_type,
        runtime_context.run_id,
        result.status,
    )

    return result
