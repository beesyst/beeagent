from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.core.module_registry import ModuleRegistry, build_registry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.runtime_context import generate_run_id, generate_session_id


# Реализация ROP оператора для запуска модульных кейсов и сбора результатов в едином формате
def run_rop_operator_case(
    settings: dict,
    storage_dir: Path,
    logger: logging.Logger,
    module_id: str = "beeagent-rop",
    case_type: str = "lead_classification",
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    registry: ModuleRegistry | None = None,
) -> dict[str, Any]:
    effective_run_id = run_id or generate_run_id()
    effective_session_id = session_id or generate_session_id()

    if registry is None:
        registry = build_registry(settings=settings, logger=logger)

    if payload is None:
        raise RuntimeError("ROP operator payload is required")
    effective_payload = payload
    run_dir = storage_dir / "runs" / effective_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    module_status = "error"
    module_summary = "module execution failed"
    operator_status = "degraded"

    try:
        result = execute_module_case(
            registry=registry,
            module_id=module_id,
            case_type=case_type,
            payload=effective_payload,
            storage_dir=storage_dir,
            logger=logger,
            run_id=effective_run_id,
            session_id=effective_session_id,
        )
        module_status = result.status
        module_summary = result.summary
        operator_status = "ok" if result.status == "ok" else "degraded"
    except RuntimeError as exc:
        module_summary = str(exc)

    module_dir = run_dir / f"module-{module_id}"
    artifact_refs = _collect_artifact_refs(
        storage_dir=storage_dir,
        module_dir=module_dir,
        case_type=case_type,
    )

    operator_summary = {
        "run_id": effective_run_id,
        "session_id": effective_session_id,
        "module_id": module_id,
        "case_type": case_type,
        "status": operator_status,
        "module_status": module_status,
        "summary": module_summary,
        "artifact_refs": artifact_refs,
    }

    operator_summary_path = run_dir / "operator_summary.json"
    operator_ref = operator_summary_path.relative_to(storage_dir).as_posix()
    operator_summary["artifact_refs"] = [*artifact_refs, operator_ref]

    operator_summary_path.write_text(
        json.dumps(operator_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    operator_text = _build_operator_text(
        run_id=effective_run_id,
        module_id=module_id,
        case_type=case_type,
        status=operator_status,
        module_status=module_status,
        summary=module_summary,
        artifact_refs=operator_summary["artifact_refs"],
    )

    logger.info(
        "rop operator flow finished: run_id=%s module_id=%s case_type=%s status=%s module_status=%s",
        effective_run_id,
        module_id,
        case_type,
        operator_status,
        module_status,
    )

    return {
        **operator_summary,
        "operator_text": operator_text,
    }


# Вспомогательные функции для ROP оператора
def _collect_artifact_refs(
    storage_dir: Path,
    module_dir: Path,
    case_type: str,
) -> list[str]:
    refs: list[str] = []
    module_result_path = module_dir / "module_result.json"
    case_result_path = module_dir / f"{case_type}_result.json"

    for path in (module_result_path, case_result_path):
        if path.exists():
            refs.append(path.relative_to(storage_dir).as_posix())

    return refs


# Генерация текстового отчета для ROP оператора
def _build_operator_text(
    run_id: str,
    module_id: str,
    case_type: str,
    status: str,
    module_status: str,
    summary: str,
    artifact_refs: list[str],
) -> str:
    artifacts_text = "\n".join(f"- {item}" for item in artifact_refs) or "- none"
    return (
        "ROP operator run v0\n"
        f"run_id: {run_id}\n"
        f"module_id: {module_id}\n"
        f"case_type: {case_type}\n"
        f"status: {status}\n"
        f"module_status: {module_status}\n"
        f"summary: {summary}\n"
        f"artifacts:\n{artifacts_text}"
    )
