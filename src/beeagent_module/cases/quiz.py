from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beeagent_module.agents.quiz.graph import run_quiz_workflow
from beeagent_module.core.paths import get_project_root


def _load_quiz_spec(quiz_spec_path: str) -> dict[str, Any]:
    project_root = get_project_root()
    full_path = project_root / quiz_spec_path

    if not full_path.exists():
        raise RuntimeError(f"Quiz spec not found: {full_path}")

    with full_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RuntimeError("Quiz spec must be a JSON object at top-level")

    return data


def _runs_dir(storage_dir: Path) -> Path:
    return storage_dir / "runs"


def _sessions_dir(storage_dir: Path) -> Path:
    return storage_dir / "sessions"


def _artifacts_dir(storage_dir: Path) -> Path:
    return storage_dir / "artifacts"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_chat_id_by_run_id(storage_dir: Path, run_id: str) -> int | None:
    ref_path = _runs_dir(storage_dir) / run_id / "session_ref.json"
    if not ref_path.exists():
        return None

    ref = _read_json(ref_path)
    chat_id = ref.get("chat_id")
    if isinstance(chat_id, int):
        return chat_id
    return None


def _load_quiz_session(storage_dir: Path, run_id: str) -> dict[str, Any] | None:
    chat_id = _load_chat_id_by_run_id(storage_dir, run_id)
    if chat_id is None:
        return None

    session_path = _sessions_dir(storage_dir) / f"{chat_id}.json"
    if not session_path.exists():
        return None

    session = _read_json(session_path)

    if session.get("run_id") != run_id:
        return None

    return session


def _save_quiz_session(storage_dir: Path, run_id: str, session: dict[str, Any]) -> None:
    chat_id = _load_chat_id_by_run_id(storage_dir, run_id)
    if chat_id is None:
        raise RuntimeError(f"Session ref not found for run_id={run_id}")

    session_path = _sessions_dir(storage_dir) / f"{chat_id}.json"
    _write_json(session_path, session)


def start_quiz_case(
    settings: dict,
    storage_dir: Path,
    chat_id: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    quiz_cfg = settings.get("quiz", {})
    if not quiz_cfg.get("enabled"):
        return {"error": "Quiz is disabled"}

    quiz_spec_path = quiz_cfg.get("path")
    if not isinstance(quiz_spec_path, str) or not quiz_spec_path:
        return {"error": "quiz.path not configured"}

    quiz_spec = _load_quiz_spec(quiz_spec_path)

    result = run_quiz_workflow(
        storage_dir=storage_dir,
        quiz_spec=quiz_spec,
        chat_id=chat_id,
        logger=logger,
    )

    run_id = result["run_id"]
    quiz_id = result.get("quiz_id", "unknown")

    run_dir = _runs_dir(storage_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "run_id": run_id,
        "agent": "quiz",
        "quiz_id": quiz_id,
        "trigger": "manual",
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_json(run_dir / "run.json", run_meta)

    steps = result.get("steps", [])
    if not isinstance(steps, list):
        steps = []
    _write_json(run_dir / "steps.json", steps)

    _write_json(run_dir / "session_ref.json", {"chat_id": chat_id})

    questions = quiz_spec.get("questions", [])
    options: list[str] = []
    if isinstance(questions, list) and questions:
        first = questions[0]
        if isinstance(first, dict):
            raw_options = first.get("options", [])
            if isinstance(raw_options, list):
                options = [str(x) for x in raw_options]

    session_data = {
        "agent": "quiz",
        "run_id": run_id,
        "quiz_id": quiz_id,
        "chat_id": chat_id,
        "current_question_idx": 0,
        "answers": [],
        "is_finished": False,
    }
    _sessions_dir(storage_dir).mkdir(parents=True, exist_ok=True)
    _write_json(_sessions_dir(storage_dir) / f"{chat_id}.json", session_data)

    return {
        "run_id": run_id,
        "quiz_id": quiz_id,
        "report_text": result.get("report_text", ""),
        "options": options,
    }


def process_quiz_answer_case(
    settings: dict,
    storage_dir: Path,
    run_id: str,
    answer_idx: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    quiz_cfg = settings.get("quiz", {})
    quiz_spec_path = quiz_cfg.get("path")

    if not isinstance(quiz_spec_path, str) or not quiz_spec_path:
        return {"error": "quiz.path not configured"}

    quiz_spec = _load_quiz_spec(quiz_spec_path)
    questions = quiz_spec.get("questions", [])
    if not isinstance(questions, list) or not questions:
        return {"error": "Quiz has no questions"}

    session = _load_quiz_session(storage_dir, run_id)
    if session is None:
        return {"error": f"Session not found: {run_id}"}

    if session.get("is_finished") is True:
        return {"error": "Quiz already finished"}

    q_idx = session.get("current_question_idx", 0)
    if not isinstance(q_idx, int) or q_idx < 0:
        return {"error": "Invalid session state: current_question_idx"}

    if q_idx >= len(questions):
        return {"error": "Quiz already finished"}

    q = questions[q_idx]
    if not isinstance(q, dict):
        return {"error": "Invalid quiz spec: question must be an object"}

    q_id = str(q.get("q_id", f"q{q_idx}"))
    question_text = str(q.get("question", ""))

    options_raw = q.get("options", [])
    if not isinstance(options_raw, list) or not options_raw:
        return {"error": "Invalid quiz spec: options required"}

    options = [str(x) for x in options_raw]
    if not isinstance(answer_idx, int) or answer_idx < 0 or answer_idx >= len(options):
        return {"error": "Invalid answer index"}

    correct_idx = q.get("correct_answer_idx", 0)
    if (
        not isinstance(correct_idx, int)
        or correct_idx < 0
        or correct_idx >= len(options)
    ):
        correct_idx = 0

    start_time = time.perf_counter()

    is_correct = answer_idx == correct_idx
    answer_data = {
        "q_id": q_id,
        "question": question_text,
        "selected_answer_idx": answer_idx,
        "correct_answer_idx": correct_idx,
        "is_correct": is_correct,
    }

    answers = session.get("answers", [])
    if not isinstance(answers, list):
        answers = []
    answers.append(answer_data)
    session["answers"] = answers

    selected_opt = options[answer_idx]
    correct_opt = options[correct_idx]

    feedback = f"You answered: **{selected_opt}**\n"
    feedback += (
        "✅ Correct!"
        if is_correct
        else f"❌ Incorrect. Correct answer: **{correct_opt}**"
    )

    next_q_idx = q_idx + 1
    session["current_question_idx"] = next_q_idx

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    logger.info(
        "step=quiz_answer duration_ms=%d run_id=%s q_idx=%d", duration_ms, run_id, q_idx
    )

    if next_q_idx >= len(questions):
        session["is_finished"] = True
        _save_quiz_session(storage_dir, run_id, session)

        correct_count = sum(
            1 for a in answers if isinstance(a, dict) and a.get("is_correct")
        )
        total_count = len(answers)
        score_percent = (correct_count / total_count * 100) if total_count > 0 else 0.0

        result_data = {
            "run_id": run_id,
            "agent": "quiz",
            "quiz_id": session.get("quiz_id"),
            "chat_id": session.get("chat_id"),
            "total_questions": total_count,
            "correct_answers": correct_count,
            "score_percent": float(score_percent),
            "created_at": datetime.now(UTC).isoformat(),
        }

        run_dir = _runs_dir(storage_dir) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        _write_json(run_dir / "quiz_answers.json", answers)
        _write_json(run_dir / "quiz_result.json", result_data)

        artifacts_dir = _artifacts_dir(storage_dir) / run_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        report_text = (
            "**Quiz Results**\n"
            f"Score: {correct_count}/{total_count} ({score_percent:.1f}%)\n"
            f"Run ID: {run_id}\n"
        )

        (artifacts_dir / "report.md").write_text(report_text, encoding="utf-8")
        (artifacts_dir / "report.html").write_text(
            "<pre>" + report_text + "</pre>",
            encoding="utf-8",
        )

        logger.info("quiz_finished run_id=%s score=%.1f%%", run_id, score_percent)

        return {
            "is_finished": True,
            "feedback": feedback,
            "result": result_data,
            "report_text": report_text,
        }

    _save_quiz_session(storage_dir, run_id, session)

    next_q = questions[next_q_idx]
    if not isinstance(next_q, dict):
        return {"error": "Invalid quiz spec: next question must be an object"}

    next_question_text = str(next_q.get("question", ""))
    next_options_raw = next_q.get("options", [])
    next_options: list[str] = []
    if isinstance(next_options_raw, list):
        next_options = [str(x) for x in next_options_raw]

    next_msg = (
        f"**Question {next_q_idx + 1}/{len(questions)}**\n\n{next_question_text}\n"
    )
    for i, opt in enumerate(next_options):
        next_msg += f"\n{i}. {opt}"

    return {
        "is_finished": False,
        "feedback": feedback,
        "next_question": next_msg,
        "next_q_idx": next_q_idx,
        "options": next_options,
    }


def get_last_quiz_case(storage_dir: Path, chat_id: int) -> dict[str, Any] | None:
    runs_dir = _runs_dir(storage_dir)
    if not runs_dir.exists():
        return None

    last_result: dict[str, Any] | None = None
    last_ts: str | None = None

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue

        run_json = run_dir / "run.json"
        if run_json.exists():
            try:
                meta = _read_json(run_json)
            except Exception:
                continue
            if meta.get("agent") != "quiz":
                continue

        result_path = run_dir / "quiz_result.json"
        if not result_path.exists():
            continue

        try:
            result = _read_json(result_path)
        except Exception:
            continue

        if result.get("chat_id") != chat_id:
            continue

        ts = result.get("created_at", "")
        if not isinstance(ts, str):
            ts = ""

        if last_ts is None or ts > last_ts:
            last_ts = ts
            last_result = result

    if last_result is None:
        return None

    correct = int(last_result.get("correct_answers", 0) or 0)
    total = int(last_result.get("total_questions", 0) or 0)
    score = float(last_result.get("score_percent", 0.0) or 0.0)
    run_id = str(last_result.get("run_id", ""))

    report_text = (
        f"**Last Quiz Results (Run {run_id})**\n\n"
        f"Score: {correct}/{total} ({score:.1f}%)\n"
    )

    return {"run_id": run_id, "result": last_result, "report_text": report_text}
