from pathlib import Path

from beeagent_module.cases.quiz import (
    get_last_quiz_case,
    process_quiz_answer_case,
    start_quiz_case,
)
from beeagent_module.core.log import get_logger, setup_logging


def test_quiz_case_workflow(tmp_path: Path) -> None:
    settings = {
        "quiz": {
            "enabled": True,
            "path": "config/quiz/pharmacy_quiz.json",
        },
    }

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "app.log"
    setup_logging(log_path=log_path, level="INFO", clear_logs=True, utc=True)
    logger = get_logger("test")
    result = start_quiz_case(
        settings=settings,
        storage_dir=storage_dir,
        chat_id=123,
        logger=logger,
    )

    assert "run_id" in result
    assert result["quiz_id"] == "pharmacy_v1"
    assert "Question 1" in result["report_text"]

    run_id = result["run_id"]
    session_path = storage_dir / "sessions" / "123.json"
    assert session_path.exists()

    result2 = process_quiz_answer_case(
        settings=settings,
        storage_dir=storage_dir,
        run_id=run_id,
        answer_idx=1,
        logger=logger,
    )

    assert result2.get("is_finished") is False
    assert "Question 2" in result2["next_question"]

    result3 = process_quiz_answer_case(
        settings=settings,
        storage_dir=storage_dir,
        run_id=run_id,
        answer_idx=2,
        logger=logger,
    )

    assert result3.get("is_finished") is False

    result4 = process_quiz_answer_case(
        settings=settings,
        storage_dir=storage_dir,
        run_id=run_id,
        answer_idx=1,
        logger=logger,
    )

    assert result4.get("is_finished") is False

    result5 = process_quiz_answer_case(
        settings=settings,
        storage_dir=storage_dir,
        run_id=run_id,
        answer_idx=0,
        logger=logger,
    )

    assert result5.get("is_finished") is True
    result_data = result5.get("result", {})
    assert result_data["correct_answers"] == 3
    assert result_data["total_questions"] == 4
    assert result_data["score_percent"] == 75.0

    answers_path = storage_dir / "runs" / run_id / "quiz_answers.json"
    result_path = storage_dir / "runs" / run_id / "quiz_result.json"
    report_path = storage_dir / "artifacts" / run_id / "report.md"
    assert answers_path.exists()
    assert result_path.exists()
    assert report_path.exists()

    last = get_last_quiz_case(storage_dir, chat_id=123)
    assert last is not None
    assert last["run_id"] == run_id
    assert "75.0%" in last["report_text"]
