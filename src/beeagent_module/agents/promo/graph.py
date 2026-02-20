import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from beeagent_module.adapters.base import DataAdapter
from beeagent_module.domain.models import Alert, RunMeta, Task
from beeagent_module.domain.serialization import model_to_dict


# Схема состояний для workflow promo
class PromoState(TypedDict, total=False):
    storage_dir: Path
    logger: logging.Logger
    adapter: DataAdapter
    adapter_name: str
    trigger: str
    promo_cfg: dict[str, Any]

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
    steps: list[dict[str, Any]]


# Добавление шага observability в state и логирование
def _record_step(state: PromoState, step: str, duration_ms: int) -> None:
    steps: list[dict[str, Any]] = state.setdefault("steps", [])
    steps.append({"step": step, "duration_ms": duration_ms})

    logger = state.get("logger")
    if logger:
        logger.info("step=%s duration_ms=%d", step, duration_ms)


# Node 1: сбор пользовательских данных и инициализация состояния workflow
def collect_input(
    state: PromoState, config: RunnableConfig | None = None
) -> PromoState:
    _ = config
    start_time = time.perf_counter()

    state["run_id"] = f"run-{uuid4().hex[:12]}"
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "collect_input", duration_ms)

    return state


# Node 2: загрузка данных из adapter и инициализация метаданных запуска
def load_data(state: PromoState, config: RunnableConfig | None = None) -> PromoState:
    _ = config
    start_time = time.perf_counter()

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

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "load_data", duration_ms)

    return state


# Node 3: детекция promo-кандидатов по простым правилам
def detect_promo_rules(
    state: PromoState,
    config: RunnableConfig | None = None,
) -> PromoState:
    _ = config
    start_time = time.perf_counter()

    promo_cfg = state.get("promo_cfg", {})
    min_stock = int(promo_cfg.get("stock_min", 0))
    max_units = int(promo_cfg.get("units_max", 0))

    stock_rows = state.get("stock", [])
    sales_rows = state.get("sales", [])

    sales_totals: dict[tuple[str, str], int] = {}
    for sale in sales_rows:
        key = (sale.store_id, sale.sku_id)
        sales_totals[key] = sales_totals.get(key, 0) + sale.units

    alerts: list[Alert] = []
    seen: set[tuple[str, str]] = set()

    for stock_row in stock_rows:
        key = (stock_row.store_id, stock_row.sku_id)
        if key in seen:
            continue

        total_units = sales_totals.get(key, 0)
        if stock_row.stock_on_hand >= min_stock and total_units <= max_units:
            alerts.append(
                Alert(
                    store_id=stock_row.store_id,
                    sku_id=stock_row.sku_id,
                    rule_id="PROMO_LOW_SALES",
                    severity="medium",
                    details=(
                        "promo candidate: stock_on_hand="
                        f"{stock_row.stock_on_hand}, sales_units={total_units}"
                    ),
                )
            )
            seen.add(key)

    state["alerts"] = alerts

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "detect_promo_rules", duration_ms)

    return state


# Node 4: генерация задач promo на основе алертов
def draft_tasks(state: PromoState, config: RunnableConfig | None = None) -> PromoState:
    _ = config
    start_time = time.perf_counter()

    alerts = state.get("alerts", [])
    tasks: list[Task] = []

    for idx, alert in enumerate(alerts):
        tasks.append(
            Task(
                task_id=f"task-{idx:04d}",
                store_id=alert.store_id,
                sku_id=alert.sku_id,
                action="run_promo",
                status="draft",
            )
        )

    state["tasks"] = tasks

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "draft_tasks", duration_ms)

    return state


# Node 5: формирование promo-отчета для пользователя
def render_report(
    state: PromoState, config: RunnableConfig | None = None
) -> PromoState:
    _ = config
    start_time = time.perf_counter()

    run_id = state.get("run_id", "unknown")
    run_meta = state.get("run_meta")
    alerts = state.get("alerts", [])
    tasks = state.get("tasks", [])

    dataset_id = run_meta.dataset_id if run_meta else "unknown"
    report_lines = [
        "Promo Scan Report",
        f"Run ID: {run_id}",
        f"Dataset: {dataset_id}",
        "",
        f"Findings: {len(alerts)}",
        f"Tasks: {len(tasks)}",
    ]

    state["report_text"] = "\n".join(report_lines)

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "render_report", duration_ms)

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
        "  <title>Promo Report</title>\n"
        "</head>\n"
        "<body>\n"
        "  <h1>Promo Report</h1>\n"
        "  <pre>\n"
        f"{report_md}\n"
        "  </pre>\n"
        "</body>\n"
        "</html>\n"
    )


# Node 6: сохранение результатов promo run в storage
def persist_run(state: PromoState, config: RunnableConfig | None = None) -> PromoState:
    _ = config
    start_time = time.perf_counter()

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
        "agent": "promo",
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

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "persist_run", duration_ms)

    steps = state.get("steps", [])
    (run_dir / "steps.json").write_text(
        json.dumps(steps, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger = state.get("logger")
    if logger:
        logger.info("Persisted promo artifacts to %s", run_dir)
        logger.info("  - run.json: %s alerts, %s tasks", len(alerts), len(tasks))
        logger.info("  - report.md/report.html saved to %s", artifacts_dir)

    return state


# Построение графа promo workflow
def build_promo_graph():
    workflow = StateGraph(PromoState)
    workflow.add_node("collect_input", collect_input)
    workflow.add_node("load_data", load_data)
    workflow.add_node("detect_promo_rules", detect_promo_rules)
    workflow.add_node("draft_tasks", draft_tasks)
    workflow.add_node("render_report", render_report)
    workflow.add_node("persist_run", persist_run)
    workflow.add_edge("collect_input", "load_data")
    workflow.add_edge("load_data", "detect_promo_rules")
    workflow.add_edge("detect_promo_rules", "draft_tasks")
    workflow.add_edge("draft_tasks", "render_report")
    workflow.add_edge("render_report", "persist_run")
    workflow.add_edge("persist_run", END)
    workflow.set_entry_point("collect_input")
    return workflow.compile()


# Запуск promo workflow с заданными параметрами
def run_promo_workflow(
    storage_dir: Path,
    adapter: DataAdapter,
    adapter_name: str,
    promo_cfg: dict[str, Any],
    trigger: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    graph = build_promo_graph()

    initial_state: PromoState = {
        "storage_dir": storage_dir,
        "adapter": adapter,
        "adapter_name": adapter_name,
        "promo_cfg": promo_cfg,
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
