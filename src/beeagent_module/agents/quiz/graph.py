import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

from beeagent_module.domain.models import QuizAnswer, QuizResult


# Тип состояния для квиза, хранящий все необходимые данные для работы и переходов между узлами
class QuizState(TypedDict, total=False):
    storage_dir: Path
    logger: logging.Logger
    quiz_spec: dict[str, Any]
    chat_id: int
    run_id: str
    quiz_id: str
    current_q_idx: int
    answer_idx: int
    answers: list[QuizAnswer]
    result: QuizResult
    report_text: str
    artifacts_dir: Path
    steps: list[dict[str, Any]]


# Вспомогательная функция для записи шагов и их длительности в состоянии
def _record_step(state: QuizState, step: str, duration_ms: int) -> None:
    steps: list[dict[str, Any]] = state.setdefault("steps", [])
    steps.append({"step": step, "duration_ms": duration_ms})

    logger = state.get("logger")
    if logger:
        logger.info("step=%s duration_ms=%d", step, duration_ms)


# Node 1: инициализация квиза, генерация run_id, загрузка спецификации и подготовка состояния
def quiz_init(state: QuizState, config: RunnableConfig | None = None) -> QuizState:
    _ = config
    start_time = time.perf_counter()

    state["run_id"] = f"quiz-run-{uuid4().hex[:12]}"
    state["current_q_idx"] = 0
    state["answers"] = []

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "quiz_init", duration_ms)

    return state


# Node 2: построение и отображение текущего вопроса для UI
def render_question(
    state: QuizState, config: RunnableConfig | None = None
) -> QuizState:
    _ = config
    start_time = time.perf_counter()

    quiz_spec = state.get("quiz_spec")
    if not quiz_spec:
        raise ValueError("quiz_spec is required")

    questions = quiz_spec.get("questions", [])
    q_idx = state.get("current_q_idx", 0)

    if q_idx >= len(questions):
        state["report_text"] = "Quiz finished"
    else:
        q = questions[q_idx]
        q_id = q.get("q_id", f"q{q_idx}")
        question_text = q.get("question", "")
        options = q.get("options", [])
        msg = f"**Question {q_idx + 1}/{len(questions)}**\n\n{question_text}\n"
        for i, opt in enumerate(options):
            msg += f"\n{i}. {opt}"

        state["report_text"] = msg

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "render_question", duration_ms)

    return state


# Node 3: обработка ответа (answer_idx кладём в state заранее)
def process_answer(state: QuizState, config: RunnableConfig | None = None) -> QuizState:
    _ = config
    start_time = time.perf_counter()

    quiz_spec = state.get("quiz_spec")
    if not quiz_spec:
        raise ValueError("quiz_spec is required")

    answer_idx = state.get("answer_idx")
    if not isinstance(answer_idx, int):
        raise ValueError("answer_idx is required in state")

    questions = quiz_spec.get("questions", [])
    q_idx = state.get("current_q_idx", 0)

    if q_idx < len(questions):
        q = questions[q_idx]
        q_id = q.get("q_id", f"q{q_idx}")
        question_text = q.get("question", "")
        correct_idx = q.get("correct_answer_idx", 0)
        is_correct = answer_idx == correct_idx

        answer = QuizAnswer(
            q_id=q_id,
            question=question_text,
            selected_answer_idx=answer_idx,
            correct_answer_idx=correct_idx,
            is_correct=is_correct,
        )

        answers: list[QuizAnswer] = state.get("answers", [])
        answers.append(answer)
        state["answers"] = answers
        state["current_q_idx"] = q_idx + 1

        options = q.get("options", [])
        selected_opt = options[answer_idx] if answer_idx < len(options) else "?"
        correct_opt = options[correct_idx] if correct_idx < len(options) else "?"

        feedback = f"You answered: **{selected_opt}**\n"
        feedback += (
            "✅ Correct!"
            if is_correct
            else f"❌ Incorrect. Correct answer: **{correct_opt}**"
        )
        state["report_text"] = feedback

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "process_answer", duration_ms)

    return state


# Node 4: завершение квиза и вычисление результата
def quiz_finalize(state: QuizState, config: RunnableConfig | None = None) -> QuizState:
    _ = config
    start_time = time.perf_counter()

    answers: list[QuizAnswer] = state.get("answers", [])
    correct_count = sum(1 for a in answers if a.is_correct)
    total_count = len(answers)
    score_percent = (correct_count / total_count * 100) if total_count > 0 else 0

    result = QuizResult(
        run_id=state.get("run_id", "unknown"),
        quiz_id=state.get("quiz_id", "unknown"),
        chat_id=state.get("chat_id", 0),
        total_questions=total_count,
        correct_answers=correct_count,
        score_percent=score_percent,
        created_at=datetime.now(UTC).isoformat(),
    )
    state["result"] = result
    report_lines = [
        "**Quiz Results**\n",
        f"Score: {correct_count}/{total_count} ({score_percent:.1f}%)\n",
        f"Run ID: {state.get('run_id')}\n",
    ]
    state["report_text"] = "".join(report_lines)

    duration_ms = int((time.perf_counter() - start_time) * 1000)
    _record_step(state, "quiz_finalize", duration_ms)

    return state


# Билд LangGraph workflow
def build_quiz_graph():
    graph = StateGraph(QuizState)
    graph.add_node("init", quiz_init)
    graph.add_node("render_q", render_question)
    graph.add_node("process_answer", process_answer)
    graph.add_node("finalize", quiz_finalize)
    graph.set_entry_point("init")
    graph.add_edge("init", "render_q")
    graph.add_edge("process_answer", "render_q")
    graph.add_edge("render_q", "finalize")
    graph.add_edge("finalize", END)

    return graph


# Хелпер: запуск всего workflow для квиза с заданными параметрами и возврат результатов
def run_quiz_workflow(
    storage_dir: Path,
    quiz_spec: dict[str, Any],
    chat_id: int,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Initialize quiz session and return first question."""

    run_id = f"quiz-run-{uuid4().hex[:12]}"
    artifact_dir = storage_dir / "runs" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    quiz_id = quiz_spec.get("quiz_id", "unknown")

    state: QuizState = {
        "storage_dir": storage_dir,
        "logger": logger,
        "quiz_spec": quiz_spec,
        "chat_id": chat_id,
        "run_id": run_id,
        "quiz_id": quiz_id,
        "current_q_idx": 0,
        "answers": [],
        "artifacts_dir": artifact_dir,
        "steps": [],
    }

    state = quiz_init(state)
    state = render_question(state)

    logger.info("quiz_init run_id=%s quiz_id=%s chat_id=%s", run_id, quiz_id, chat_id)

    return {
        "run_id": run_id,
        "quiz_id": quiz_id,
        "report_text": state.get("report_text", ""),
        "steps": state.get("steps", []),
    }
