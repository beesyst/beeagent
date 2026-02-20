from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from beeagent_module.ui.telegram_bot import (
    BUTTON_APPROVE_TASKS,
    BUTTON_REJECT_TASKS,
    BUTTON_RUN_OOS,
    BUTTON_SHOW_REPORT,
    _run_scheduled_oos_tick,
    _scheduler_loop,
    _start_scheduler_if_enabled,
    handle_last,
    handle_menu_button,
    handle_run_oos,
    handle_run_promo,
    handle_start,
    handle_unknown_command,
)


# Фейк: объекты для имитации Telegram Update, Message, CallbackQuery и Bot в тестах
class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None) -> None:
        _ = reply_markup
        self.replies.append(text)


# Фейк: CallbackQuery для имитации нажатия кнопок в Telegram
class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage) -> None:
        self.data = data
        self.message = message
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


# Фейк: Bot для имитации отправки сообщений в Telegram
class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text})


# Фейк: App для хранения bot_data и имитации жизненного цикла приложения в тестах
class FakeApp:
    def __init__(self, bot_data: dict[str, Any]) -> None:
        self.bot_data = bot_data
        self.bot = FakeBot()


def run_async_handler(handler: Any, update: Any, context: Any) -> None:
    asyncio.run(handler(update, context))


# Вспомогательные функции для создания контекста и обновлений Telegram в тестах, а также тесты для проверки логики бота и сценария OOS
def make_context(
    tmp_path: Path,
    chat_id: int = 1,
    telemetry_enabled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        bot_data={
            "chat_id": chat_id,
            "telemetry_enabled": telemetry_enabled,
            "telemetry_path": tmp_path / "telemetry" / "telegram_updates.jsonl",
            "last_report_path": tmp_path / "reports" / "last_oos_report.md",
            "logger": logging.getLogger("test.telegram"),
            "settings": {
                "mock": {
                    "seed": 42,
                    "weeks": 4,
                    "stores": 2,
                    "skus": 3,
                    "category": "Vitamins",
                },
                "data": {
                    "adapter": "mock",
                    "mock": {
                        "dataset_id": None,
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
            },
            "storage_dir": tmp_path,
        }
    )


# Вспомогательные функции для создания обновлений Telegram с сообщениями и кнопками для тестов
def make_message_update(
    chat_id: int,
    text: str,
    update_id: int = 1,
) -> SimpleNamespace:
    message = FakeMessage(text=text)
    chat = SimpleNamespace(id=chat_id)
    user = SimpleNamespace(id=chat_id)
    return SimpleNamespace(
        update_id=update_id,
        message=message,
        callback_query=None,
        effective_message=message,
        effective_chat=chat,
        effective_user=user,
    )


# Вспомогательная функция для создания обновлений Telegram с данными кнопок для тестов
def make_callback_update(
    chat_id: int,
    callback_data: str,
    update_id: int = 1,
) -> SimpleNamespace:
    message = FakeMessage(text="button")
    query = FakeCallbackQuery(data=callback_data, message=message)
    chat = SimpleNamespace(id=chat_id)
    user = SimpleNamespace(id=chat_id)
    return SimpleNamespace(
        update_id=update_id,
        message=None,
        callback_query=query,
        effective_message=message,
        effective_chat=chat,
        effective_user=user,
    )


# Тест: доступ к боту разрешен только для админского чата, остальные получают отказ в доступе
def test_start_denies_non_admin(tmp_path: Path) -> None:
    update = make_message_update(chat_id=2, text="/start")
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_async_handler(handle_start, update, context)

    assert update.effective_message.replies[-1] == "Access denied: admin chat only."


# Тест: выполнение сценария OOS через команду и получение отчета, а также отображение статуса задач и причины отклонения в последнем отчете
def test_run_oos_then_last_report(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_update = make_message_update(chat_id=1, text="/run_oos", update_id=10)
    run_async_handler(handle_run_oos, run_update, context)

    last_update = make_message_update(chat_id=1, text="/last", update_id=11)
    run_async_handler(handle_last, last_update, context)

    assert "📊 OOS Detection Report" in run_update.effective_message.replies[-1]
    assert "🚨 Alerts:" in last_update.effective_message.replies[-1]
    assert "Tasks status:" in last_update.effective_message.replies[-1]


# Тест: нажатия кнопок "Run OOS" и "Show Report" вызывают одни и те же обработчики и возвращают отчет OOS
def test_buttons_call_same_handlers(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_button_update = make_callback_update(chat_id=1, callback_data=BUTTON_RUN_OOS)
    run_async_handler(handle_menu_button, run_button_update, context)

    show_button_update = make_callback_update(
        chat_id=1, callback_data=BUTTON_SHOW_REPORT
    )
    run_async_handler(handle_menu_button, show_button_update, context)

    assert run_button_update.callback_query.answered is True
    assert show_button_update.callback_query.answered is True
    assert "📊 OOS Detection Report" in run_button_update.effective_message.replies[-1]
    assert "📊 OOS Detection Report" in show_button_update.effective_message.replies[-1]


# Тест: нажатия кнопок "Approve Tasks" и "Reject Tasks" возвращают соответствующие ответы и сохраняют статус задач
def test_approve_tasks_button(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_update = make_message_update(chat_id=1, text="/run_oos", update_id=30)
    run_async_handler(handle_run_oos, run_update, context)

    approve_update = make_callback_update(
        chat_id=1,
        callback_data=BUTTON_APPROVE_TASKS,
        update_id=31,
    )
    run_async_handler(handle_menu_button, approve_update, context)

    assert "Tasks approved" in approve_update.effective_message.replies[-1]


# Тест: нажатия кнопки "Reject Tasks" возвращает соответствующий ответ и сохраняет статус задач с причиной отклонения
def test_reject_tasks_button(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_update = make_message_update(chat_id=1, text="/run_oos", update_id=40)
    run_async_handler(handle_run_oos, run_update, context)

    reject_update = make_callback_update(
        chat_id=1,
        callback_data=BUTTON_REJECT_TASKS,
        update_id=41,
    )
    run_async_handler(handle_menu_button, reject_update, context)

    assert "Tasks rejected" in reject_update.effective_message.replies[-1]


# Тест: последний отчет OOS содержит статус задач и причину отклонения после нажатия кнопки "Reject Tasks"
def test_last_report_includes_reject_reason(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_update = make_message_update(chat_id=1, text="/run_oos", update_id=50)
    run_async_handler(handle_run_oos, run_update, context)

    reject_update = make_callback_update(
        chat_id=1,
        callback_data=BUTTON_REJECT_TASKS,
        update_id=51,
    )
    run_async_handler(handle_menu_button, reject_update, context)

    last_update = make_message_update(chat_id=1, text="/last", update_id=52)
    run_async_handler(handle_last, last_update, context)

    assert (
        "Reject reason: Rejected by operator"
        in last_update.effective_message.replies[-1]
    )


# Тест: неизвестная команда не вызывает ошибок и возвращает сообщение об неизвестной команде
def test_unknown_command_does_not_crash(tmp_path: Path) -> None:
    update = make_message_update(chat_id=1, text="/abc", update_id=20)
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_async_handler(handle_unknown_command, update, context)

    assert update.effective_message.replies[-1] == "Unknown command. Use /help."


# Тест: при включенной телеметрии обновления Telegram записываются в JSONL файл с правильными полями
def test_telemetry_writes_jsonl(tmp_path: Path) -> None:
    update = make_message_update(chat_id=1, text="/start", update_id=77)
    context = make_context(tmp_path=tmp_path, chat_id=1, telemetry_enabled=True)

    run_async_handler(handle_start, update, context)

    telemetry_path = context.bot_data["telemetry_path"]
    assert telemetry_path.exists()

    line = telemetry_path.read_text(encoding="utf-8").strip().splitlines()[0]
    payload = json.loads(line)
    assert payload["event"] == "start"
    assert payload["chat_id"] == 1
    assert payload["update_id"] == 77


# Тест: при выключенной телеметрии файл не создается и обновления не записываются
def test_scheduler_not_started_when_disabled(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    app = FakeApp(bot_data=context.bot_data)

    asyncio.run(_start_scheduler_if_enabled(app))

    assert "scheduler_task" not in app.bot_data


# Тест: при включенной телеметрии обновления Telegram записываются в JSONL файл с правильными полями при нажатии кнопки "Run OOS"
def test_scheduler_tick_uses_scheduled_trigger(tmp_path: Path, monkeypatch) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    app = FakeApp(bot_data=context.bot_data)
    called: dict[str, Any] = {}

    def fake_run_oos_case(
        settings: dict,
        storage_dir: Path,
        logger: logging.Logger,
        trigger: str,
    ) -> dict[str, Any]:
        _ = settings, storage_dir, logger
        called["trigger"] = trigger
        return {
            "run_id": "run-test",
            "alerts_count": 2,
            "tasks_count": 2,
            "report_text": "ok",
        }

    monkeypatch.setattr(
        "beeagent_module.ui.telegram_bot.run_oos_case",
        fake_run_oos_case,
    )

    asyncio.run(_run_scheduled_oos_tick(app))

    assert called["trigger"] == "scheduled"
    assert app.bot.sent_messages[0]["chat_id"] == 1
    assert "New run ready → Approve/Reject" in app.bot.sent_messages[0]["text"]


# Тест: если сценарий OOS в scheduled-run выбрасывает ошибку, она логируется, и цикл продолжает работать
def test_scheduler_loop_continues_after_case_error(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    context.bot_data["settings"]["scheduler"] = {
        "enabled": True,
        "interval": 1,
        "start_run": True,
    }
    app = FakeApp(bot_data=context.bot_data)
    stop_event = asyncio.Event()
    call_count = {"value": 0}

    def fake_run_oos_case(
        settings: dict,
        storage_dir: Path,
        logger: logging.Logger,
        trigger: str,
    ) -> dict[str, Any]:
        _ = settings, storage_dir, logger, trigger
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise RuntimeError("boom")
        stop_event.set()
        return {
            "run_id": "run-ok",
            "alerts_count": 1,
            "tasks_count": 1,
            "report_text": "ok",
        }

    async def fast_wait_for(awaitable: Any, timeout: float) -> Any:
        _ = timeout
        task = asyncio.create_task(awaitable)
        await asyncio.sleep(0)
        if task.done():
            return task.result()
        task.cancel()
        raise TimeoutError()

    monkeypatch.setattr(
        "beeagent_module.ui.telegram_bot.run_oos_case",
        fake_run_oos_case,
    )
    monkeypatch.setattr(
        "beeagent_module.ui.telegram_bot.asyncio.wait_for",
        fast_wait_for,
    )

    with caplog.at_level(logging.ERROR):
        asyncio.run(_scheduler_loop(app, stop_event))

    assert call_count["value"] == 2
    assert "scheduled run failed" in caplog.text


# Тест: нажатия кнопки "Run Promo" вызывает сценарий promo и возвращает отчет promo
def test_run_promo_returns_report(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    promo_update = make_message_update(chat_id=1, text="/run_promo", update_id=60)
    run_async_handler(handle_run_promo, promo_update, context)

    assert "Promo Scan Report" in promo_update.effective_message.replies[-1]
