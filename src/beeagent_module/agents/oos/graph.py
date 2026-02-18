import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from beeagent_module.agents.oos.rules import detect_rule_a
from beeagent_module.domain.models import Alert, RunMeta, Task
from beeagent_module.domain.serialization import model_to_dict
from beeagent_module.mock.dataset import load_mock_dataset


# Схема состояний для workflow (type hints)
class OOSState(TypedDict, total=False):
    dataset_id: str
    storage_dir: Path
    logger: logging.Logger

    stores: list[Any]
    skus: list[Any]
    sales: list[Any]
    stock: list[Any]
    shelf_signals: list[Any]

    run_meta: RunMeta
    alerts: list[Alert]
    tasks: list[Task]

    report_text: str
    run_id: str
    artifacts_dir: Path


# Node 1: сбор пользовательских данных и инициализация состояния рабочего процесса
def collect_input(state: OOSState, config: RunnableConfig | None = None) -> OOSState:
    _ = config
    state["run_id"] = f"run-{uuid4().hex[:12]}"
    return state


# Node 2: загрузка данных из storage и десериализация в объекты доменной модели
def load_data(state: OOSState, config: RunnableConfig | None = None) -> OOSState:
    _ = config
    dataset_id = state.get("dataset_id")
    storage_dir = state.get("storage_dir")
    if not dataset_id or not storage_dir:
        raise ValueError("dataset_id and storage_dir required")

    dataset_path = storage_dir / "mock" / dataset_id / "dataset.json"
    loaded = load_mock_dataset(dataset_path)

    state["stores"] = loaded.get("stores", [])
    state["skus"] = loaded.get("skus", [])
    state["sales"] = loaded.get("sales", [])
    state["stock"] = loaded.get("stock", [])
    state["shelf_signals"] = loaded.get("shelf_signals", [])
    state["run_meta"] = loaded["meta"]

    return state


# Node 3: применение правил OOS-детекции и генерация алертов
def detect_oos(state: OOSState, config: RunnableConfig | None = None) -> OOSState:
    _ = config
    stock_rows = state.get("stock", [])
    shelf_signals = state.get("shelf_signals", [])

    alerts: list[Alert] = []
    for stock_row in stock_rows:
        rule_a_alerts = detect_rule_a(
            stock_rows=stock_rows,
            shelf_signals=shelf_signals,
            sku_id=stock_row.sku_id,
            store_id=stock_row.store_id,
            date=stock_row.date,
        )
        alerts.extend(rule_a_alerts)

    state["alerts"] = alerts
    return state


# Node 4: генерация задач на основе алертов
def draft_tasks(state: OOSState, config: RunnableConfig | None = None) -> OOSState:
    _ = config
    alerts = state.get("alerts", [])
    tasks: list[Task] = []

    for idx, alert in enumerate(alerts):
        tasks.append(
            Task(
                task_id=f"task-{idx:04d}",
                store_id=alert.store_id,
                sku_id=alert.sku_id,
                action="restock_and_display",
                status="draft",
            )
        )

    state["tasks"] = tasks
    return state


# Node 5: форматирование алертов и задач в текст отчета для пользователя
def render_report(state: OOSState, config: RunnableConfig | None = None) -> OOSState:
    _ = config
    run_id = state.get("run_id", "unknown")
    run_meta = state.get("run_meta")
    alerts = state.get("alerts", [])
    tasks = state.get("tasks", [])

    dataset_id = run_meta.dataset_id if run_meta else "unknown"
    high_alerts = [a for a in alerts if a.severity == "high"]
    affected_stores = {a.store_id for a in alerts}
    affected_skus = {a.sku_id for a in alerts}

    report_lines = [
        "📊 OOS Detection Report",
        f"Run ID: {run_id}",
        f"Dataset: {dataset_id}",
        "",
        f"🚨 Alerts: {len(alerts)}",
        f"  - High severity: {len(high_alerts)}",
        f"  - Affected stores: {len(affected_stores)}",
        f"  - Affected SKUs: {len(affected_skus)}",
        "",
        f"✅ Tasks: {len(tasks)}",
    ]

    state["report_text"] = "\n".join(report_lines)
    return state


# Node 6: сохранение результатов выполнения в storage для последующего доступа и аудита
def persist_run(state: OOSState, config: RunnableConfig | None = None) -> OOSState:
    _ = config
    storage_dir = state.get("storage_dir")
    run_id = state.get("run_id")
    if not storage_dir or not run_id:
        raise ValueError("storage_dir and run_id required for persistence")

    run_meta = state.get("run_meta")
    alerts = state.get("alerts", [])
    tasks = state.get("tasks", [])

    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state["artifacts_dir"] = run_dir

    run_data = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "dataset_id": run_meta.dataset_id if run_meta else None,
        "seed": run_meta.seed if run_meta else None,
        "alerts_count": len(alerts),
        "tasks_count": len(tasks),
    }
    (run_dir / "run.json").write_text(json.dumps(run_data, indent=2), encoding="utf-8")

    (run_dir / "alerts.json").write_text(
        json.dumps(model_to_dict(alerts), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    (run_dir / "tasks_draft.json").write_text(
        json.dumps(model_to_dict(tasks), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger = state.get("logger")
    if logger:
        logger.info("Persisted run artifacts to %s", run_dir)
        logger.info("  - run.json: %s alerts, %s tasks", len(alerts), len(tasks))

    return state


# Построение графа рабочего процесса OOS-детекции с 6 узлами
def build_oos_graph():
    workflow = StateGraph(OOSState)
    workflow.add_node("collect_input", collect_input)
    workflow.add_node("load_data", load_data)
    workflow.add_node("detect_oos", detect_oos)
    workflow.add_node("draft_tasks", draft_tasks)
    workflow.add_node("render_report", render_report)
    workflow.add_node("persist_run", persist_run)

    workflow.add_edge("collect_input", "load_data")
    workflow.add_edge("load_data", "detect_oos")
    workflow.add_edge("detect_oos", "draft_tasks")
    workflow.add_edge("draft_tasks", "render_report")
    workflow.add_edge("render_report", "persist_run")
    workflow.add_edge("persist_run", END)

    workflow.set_entry_point("collect_input")
    return workflow.compile()


# Функция для запуска всего workflow OOS-детекции с заданным dataset_id и storage_dir
def run_oos_workflow(
    dataset_id: str,
    storage_dir: Path,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    graph = build_oos_graph()

    initial_state: OOSState = {
        "dataset_id": dataset_id,
        "storage_dir": storage_dir,
    }
    if logger is not None:
        initial_state["logger"] = logger

    result = graph.invoke(initial_state)
    final_state: dict[str, Any] = dict(result)

    alerts = final_state.get("alerts", [])
    tasks = final_state.get("tasks", [])

    return {
        "run_id": final_state.get("run_id", ""),
        "artifacts_dir": final_state.get("artifacts_dir"),
        "report_text": final_state.get("report_text", ""),
        "alerts_count": len(alerts),
        "tasks_count": len(tasks),
    }
