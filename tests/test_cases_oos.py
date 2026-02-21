import json
import logging
from pathlib import Path

from beeagent_module.cases.oos import (
    approve_last_run_case,
    get_last_report_case,
    run_oos_case,
)


# Тест кейса OOS: запуск, получение отчета и утверждение/отклонение задач
def _settings(dataset_id: str | None = None) -> dict:
    return {
        "mock": {
            "seed": 42,
            "weeks": 2,
            "stores": 2,
            "skus": 3,
            "category": "Vitamins",
        },
        "data": {
            "adapter": "mock",
            "mock": {
                "dataset_id": dataset_id,
            },
        },
        "scheduler": {
            "enabled": False,
            "interval": 60,
            "start_run": False,
        },
        "approval": {
            "reject_reason": "Rejected by operator",
        },
        "promo": {
            "stock_min": 10,
            "units_max": 2,
        },
        "recommendations": {
            "enabled": True,
            "items_max": 10,
        },
        "llm": {
            "enabled": False,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key_env": "OPENAI_API_KEY",
        },
    }


# Тест: кейс OOS создает артефакты и отчет
def test_run_oos_case_creates_artifacts_and_report(tmp_path: Path) -> None:
    result = run_oos_case(
        settings=_settings(),
        storage_dir=tmp_path,
        logger=logging.getLogger("test.cases"),
        trigger="manual",
    )

    assert result["run_id"].startswith("run-")
    assert "📊 OOS Detection Report" in result["report_text"]
    assert "Recommendations:" in result["report_text"]

    run_json = tmp_path / "runs" / result["run_id"] / "run.json"
    run_data = json.loads(run_json.read_text(encoding="utf-8"))

    assert run_data["agent"] == "oos"
    assert run_data["adapter"] == "mock"
    assert run_data["trigger"] == "manual"

    recommendations_json = tmp_path / "runs" / result["run_id"] / "recommendations.json"
    assert recommendations_json.exists()
    recommendations = json.loads(recommendations_json.read_text(encoding="utf-8"))
    assert isinstance(recommendations, list)


# Тест: получение последнего отчета OOS с добавлением статуса задач и причины отклонения
def test_last_report_case_contains_status_and_reject_reason(tmp_path: Path) -> None:
    result = run_oos_case(
        settings=_settings(),
        storage_dir=tmp_path,
        logger=logging.getLogger("test.cases"),
        trigger="manual",
    )

    approve_last_run_case(
        settings=_settings(),
        storage_dir=tmp_path,
        decision="rejected",
    )

    report_text = get_last_report_case(tmp_path)
    assert report_text is not None
    assert result["run_id"] in report_text
    assert "Tasks status:" in report_text
    assert "Reject reason: Rejected by operator" in report_text


# Тест: утверждение последнего запуска кейса OOS
def test_approve_last_run_case_approved(tmp_path: Path) -> None:
    run_oos_case(
        settings=_settings(),
        storage_dir=tmp_path,
        logger=logging.getLogger("test.cases"),
        trigger="manual",
    )

    response = approve_last_run_case(
        settings=_settings(),
        storage_dir=tmp_path,
        decision="approved",
    )

    assert response.startswith("Tasks approved for run")


# Тест: отклонение последнего запуска кейса OOS с указанием причины
def test_run_oos_case_scheduled_sets_trigger(tmp_path: Path) -> None:
    result = run_oos_case(
        settings=_settings(),
        storage_dir=tmp_path,
        logger=logging.getLogger("test.cases"),
        trigger="scheduled",
    )

    run_json = tmp_path / "runs" / result["run_id"] / "run.json"
    run_data = json.loads(run_json.read_text(encoding="utf-8"))

    assert run_data["trigger"] == "scheduled"


# Тест: проверка наличия steps.json в артефактах с временами выполнения узлов
def test_run_oos_case_creates_steps_artifact(tmp_path: Path) -> None:
    result = run_oos_case(
        settings=_settings(),
        storage_dir=tmp_path,
        logger=logging.getLogger("test.cases"),
        trigger="manual",
    )

    steps_json = tmp_path / "runs" / result["run_id"] / "steps.json"
    assert steps_json.exists()

    steps = json.loads(steps_json.read_text(encoding="utf-8"))
    assert isinstance(steps, list)
    assert len(steps) == 7

    expected_steps = [
        "collect_input",
        "load_data",
        "detect_oos",
        "draft_tasks",
        "build_recommendations",
        "render_report",
        "persist_run",
    ]

    for idx, step in enumerate(steps):
        assert step["step"] == expected_steps[idx]
        assert "duration_ms" in step
        assert isinstance(step["duration_ms"], int)
        assert step["duration_ms"] >= 0
