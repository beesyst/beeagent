from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from beeagent_module.ui.telegram_bot import (
    BUTTON_RUN_OOS,
    BUTTON_SHOW_REPORT,
    handle_last,
    handle_menu_button,
    handle_run_oos,
    handle_start,
    handle_unknown_command,
)


# Эмуляция Telegram-сообщения с накоплением ответов
class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None) -> None:
        _ = reply_markup
        self.replies.append(text)


# Эмуляция callback query для inline-кнопок
class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage) -> None:
        self.data = data
        self.message = message
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


# Запууск async-обработчика в синхронном тесте
def run_async_handler(handler: Any, update: Any, context: Any) -> None:
    asyncio.run(handler(update, context))


# Создание контекста обработчика с bot_data
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
                }
            },
        }
    )


# Создание update для обычной команды
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


# Создание update для callback-кнопки
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


# Чек: неразрешенный chat получает отказ
def test_start_denies_non_admin(tmp_path: Path) -> None:
    update = make_message_update(chat_id=2, text="/start")
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_async_handler(handle_start, update, context)

    assert update.effective_message.replies[-1] == "Access denied: admin chat only."


# Чек: запись и чтение последнего отчета
def test_run_oos_then_last_report(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_update = make_message_update(chat_id=1, text="/run_oos", update_id=10)
    run_async_handler(handle_run_oos, run_update, context)

    last_update = make_message_update(chat_id=1, text="/last", update_id=11)
    run_async_handler(handle_last, last_update, context)

    assert "Last OOS report" in run_update.effective_message.replies[-1]
    assert "alerts_total" in last_update.effective_message.replies[-1]


# Чек: кнопки вызывают те же сценарии, что и команды
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
    assert "Last OOS report" in run_button_update.effective_message.replies[-1]
    assert "Last OOS report" in show_button_update.effective_message.replies[-1]


# Чек: ответ на неизвестную команду
def test_unknown_command_does_not_crash(tmp_path: Path) -> None:
    update = make_message_update(chat_id=1, text="/abc", update_id=20)
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_async_handler(handle_unknown_command, update, context)

    assert update.effective_message.replies[-1] == "Unknown command. Use /help."


# Чек: запись телеметрии в jsonl
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
