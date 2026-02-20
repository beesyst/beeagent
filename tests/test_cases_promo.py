import json
import logging
from pathlib import Path

from beeagent_module.cases.promo import run_promo_case


# Тестовые настройки для promo кейса
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
    }


# Тест: promo кейс создает артефакты и отчет
def test_run_promo_case_creates_artifacts_and_report(tmp_path: Path) -> None:
    result = run_promo_case(
        settings=_settings(),
        storage_dir=tmp_path,
        logger=logging.getLogger("test.cases"),
        trigger="manual",
    )

    assert result["run_id"].startswith("run-")
    assert "Promo Scan Report" in result["report_text"]

    run_dir = tmp_path / "runs" / result["run_id"]
    run_json = run_dir / "run.json"
    run_data = json.loads(run_json.read_text(encoding="utf-8"))

    assert run_data["agent"] == "promo"
    assert run_data["adapter"] == "mock"
    assert run_data["trigger"] == "manual"

    assert (run_dir / "alerts.json").exists()
    assert (run_dir / "tasks_draft.json").exists()
    assert (run_dir / "steps.json").exists()

    artifacts_dir = tmp_path / "artifacts" / result["run_id"]
    assert (artifacts_dir / "report.md").exists()
    assert (artifacts_dir / "report.html").exists()
