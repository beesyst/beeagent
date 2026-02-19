import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from beeagent_module.adapters.base import DataAdapter
from beeagent_module.agents.oos.rules import detect_rule_a
from beeagent_module.domain.models import Alert, RunMeta, Task
from beeagent_module.domain.serialization import model_to_dict


# Схема состояний для workflow (type hints)
class OOSState(TypedDict, total=False):
    storage_dir: Path
    logger: logging.Logger
    adapter: DataAdapter
    adapter_name: str
    trigger: str

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
    adapter = state.get("adapter")
    if adapter is None:
        raise ValueError("adapter is required")

    stores, skus = adapter.get_catalog()
    sales = adapter.get_sales()
    stock = adapter.get_stock()
    shelf_signals = adapter.get_shelf_signals()
    dataset_id = getattr(adapter, "dataset_id", "unknown")
    get_meta = getattr(adapter, "get_meta", None)

    state["stores"] = stores
    state["skus"] = skus
    state["sales"] = sales
    state["stock"] = stock
    state["shelf_signals"] = shelf_signals
    run_id = state.get("run_id", "unknown")

    if callable(get_meta):
        meta = cast(RunMeta, get_meta())

        state["run_meta"] = RunMeta(
            run_id=run_id,
            created_at=getattr(meta, "created_at", datetime.now(UTC).isoformat()),
            dataset_id=getattr(meta, "dataset_id", dataset_id),
            seed=getattr(meta, "seed", 0),
        )
    else:
        state["run_meta"] = RunMeta(
            run_id=run_id,
            created_at=datetime.now(UTC).isoformat(),
            dataset_id=dataset_id,
            seed=0,
        )

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


# Чек статуса задач по run_id
def _build_task_status_summary(tasks: list[Task]) -> tuple[str, str | None]:
    counts = {
        "draft": 0,
        "approved": 0,
        "rejected": 0,
    }

    for task in tasks:
        status = getattr(task, "status", "draft")
        if status in counts:
            counts[status] += 1

    summary = (
        "Tasks status: "
        f"draft={counts['draft']}, "
        f"approved={counts['approved']}, "
        f"rejected={counts['rejected']}"
    )
    return summary, None


# Чек формирования отчета в формате Markdown
def _build_report_md(report_text: str, summary: str, reject_reason: str | None) -> str:
    report_md = f"{report_text}\n\n{summary}"
    if reject_reason:
        report_md = f"{report_md}\nReject reason: {reject_reason}"
    return report_md


# Чек формирования отчета в формате HTML
def _build_report_html(report_md: str) -> str:
    return (
        "<!doctype html>\n"
        "<html>\n"
        "<head>\n"
        '  <meta charset="utf-8">\n'
        "  <title>OOS Report</title>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>OOS Report</h1>\n"
        "  <pre>\n"
        f"{report_md}\n"
        "  </pre>\n"
        "</body>\n"
        "</html>\n"
    )


# Чек записи последнего run_id
def _write_last_run_marker(storage_dir: Path, run_id: str) -> Path:
    reports_dir = storage_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    last_run_path = reports_dir / "last_run.json"
    payload = {
        "run_id": run_id,
        "ts": datetime.now(UTC).isoformat(),
    }
    last_run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return last_run_path


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
        "adapter": state.get("adapter_name"),
        "trigger": state.get("trigger", "manual"),
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

    report_text = state.get("report_text", "")
    summary_line, reject_reason = _build_task_status_summary(tasks)
    report_md = _build_report_md(report_text, summary_line, reject_reason)
    report_html = _build_report_html(report_md)

    artifacts_dir = storage_dir / "artifacts" / run_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "report.md").write_text(report_md, encoding="utf-8")
    (artifacts_dir / "report.html").write_text(report_html, encoding="utf-8")

    _write_last_run_marker(storage_dir, run_id)

    logger = state.get("logger")
    if logger:
        logger.info("Persisted run artifacts to %s", run_dir)
        logger.info("  - run.json: %s alerts, %s tasks", len(alerts), len(tasks))
        logger.info("  - report.md/report.html saved to %s", artifacts_dir)

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
    storage_dir: Path,
    adapter: DataAdapter,
    adapter_name: str,
    trigger: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    graph = build_oos_graph()

    initial_state: OOSState = {
        "storage_dir": storage_dir,
        "adapter": adapter,
        "adapter_name": adapter_name,
        "trigger": trigger,
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
