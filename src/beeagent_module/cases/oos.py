from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from beeagent_module.adapters.factory import get_adapter
from beeagent_module.agents.oos.graph import run_oos_workflow
from beeagent_module.mock.dataset import generate_mock_dataset, save_mock_dataset


# Кейс OOS: генерация mock-данных, запуск workflow, сохранение отчета и утверждение/отклонение задач
def run_oos_case(
    settings: dict,
    storage_dir: Path,
    logger: logging.Logger,
    trigger: str = "manual",
) -> dict[str, Any]:
    dataset_id = settings["data"]["mock"].get("dataset_id")

    if not dataset_id:
        mock_cfg = settings["mock"]
        dataset = generate_mock_dataset(
            seed=mock_cfg["seed"],
            weeks=mock_cfg["weeks"],
            stores=mock_cfg["stores"],
            skus=mock_cfg["skus"],
            category=mock_cfg["category"],
        )
        save_mock_dataset(dataset=dataset, storage_dir=storage_dir)
        dataset_id = dataset["meta"]["dataset_id"]

    adapter = get_adapter(
        settings=settings,
        storage_dir=storage_dir,
        dataset_id=dataset_id,
    )

    result = run_oos_workflow(
        storage_dir=storage_dir,
        adapter=adapter,
        adapter_name=settings["data"]["adapter"],
        trigger=trigger,
        llm_cfg=settings["llm"],
        recommendations_cfg=settings["recommendations"],
        i18n_cfg=settings["i18n"],
        logger=logger,
    )

    report_path = storage_dir / "reports" / "last_oos_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result["report_text"], encoding="utf-8")

    return result


# Кейс получения последнего отчета OOS с добавлением статуса задач и причины отклонения
def get_last_report_case(storage_dir: Path) -> str | None:
    report_path = storage_dir / "reports" / "last_oos_report.md"
    if not report_path.exists():
        return None

    report_text = report_path.read_text(encoding="utf-8")
    run_id = _load_last_run_id(storage_dir)
    if not run_id:
        return report_text

    summary_line, reject_reason = _load_tasks_status_summary(storage_dir, run_id)
    return _append_status_to_report(report_text, summary_line, reject_reason)


# Кейс утверждения/отклонения задач последнего запуска OOS с сохранением статуса и причины в артефактах
def approve_last_run_case(settings: dict, storage_dir: Path, decision: str) -> str:
    run_id = _load_last_run_id(storage_dir)
    if not run_id:
        return "No runs yet. Run /run_oos first."

    run_dir = storage_dir / "runs" / run_id
    draft_path = run_dir / "tasks_draft.json"
    if not draft_path.exists():
        return "No draft tasks found for last run."

    tasks = json.loads(draft_path.read_text(encoding="utf-8"))
    if decision == "approved":
        for task in tasks:
            task["status"] = "approved"
            task.pop("reason", None)
    elif decision == "rejected":
        reject_reason = settings["approval"]["reject_reason"]
        for task in tasks:
            task["status"] = "rejected"
            task["reason"] = reject_reason
    else:
        return "Unknown approval decision."

    approved_path = run_dir / "tasks_approved.json"
    approved_path.write_text(
        json.dumps(tasks, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return f"Tasks {decision} for run {run_id}."


# Вспомогательные функции для загрузки статуса задач и причины отклонения из артефактов последнего запуска
def _load_last_run_id(storage_dir: Path) -> str | None:
    last_run_path = storage_dir / "reports" / "last_run.json"
    if not last_run_path.exists():
        return None

    payload = json.loads(last_run_path.read_text(encoding="utf-8"))
    return payload.get("run_id")


# Чек: загрузка статуса задач и причины отклонения из артефактов последнего запуска OOS
def _load_tasks_status_summary(
    storage_dir: Path,
    run_id: str,
) -> tuple[str, str | None]:
    run_dir = storage_dir / "runs" / run_id
    approved_path = run_dir / "tasks_approved.json"
    draft_path = run_dir / "tasks_draft.json"

    if approved_path.exists():
        tasks = json.loads(approved_path.read_text(encoding="utf-8"))
    elif draft_path.exists():
        tasks = json.loads(draft_path.read_text(encoding="utf-8"))
    else:
        return "Tasks status: draft=0, approved=0, rejected=0", None

    counts = {"draft": 0, "approved": 0, "rejected": 0}
    reject_reason = None

    for task in tasks:
        status = task.get("status", "draft")
        if status in counts:
            counts[status] += 1
        if status == "rejected" and task.get("reason"):
            reject_reason = task.get("reason")

    summary_line = (
        "Tasks status: "
        f"draft={counts['draft']}, "
        f"approved={counts['approved']}, "
        f"rejected={counts['rejected']}"
    )
    return summary_line, reject_reason


# Чек: добавление статуса задач и причины отклонения в текст отчета последнего запуска OOS
def _append_status_to_report(
    report_text: str,
    summary_line: str,
    reject_reason: str | None,
) -> str:
    report = f"{report_text}\n\n{summary_line}"
    if reject_reason:
        report = f"{report}\nReject reason: {reject_reason}"
    return report
