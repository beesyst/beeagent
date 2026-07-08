from __future__ import annotations

import asyncio
import json
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from beeagent_module.core.i18n import load_translations
from beeagent_module.ui.telegram_bot import (
    BUTTON_RUN_PROMO,
    _build_application,
    _scheduler_loop,
    _start_scheduler_if_enabled,
    handle_menu_button,
    handle_run_promo,
    handle_run_rop,
    handle_start,
    handle_unknown_command,
)


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None) -> None:
        _ = reply_markup
        self.replies.append(text)


class FakeCallbackQuery:
    def __init__(self, data: str, message: FakeMessage) -> None:
        self.data = data
        self.message = message
        self.answered = False

    async def answer(self) -> None:
        self.answered = True


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text})


class FakeApp:
    def __init__(self, bot_data: dict[str, Any]) -> None:
        self.bot_data = bot_data
        self.bot = FakeBot()


def run_async_handler(handler: Any, update: Any, context: Any) -> None:
    asyncio.run(handler(update, context))


def make_context(
    tmp_path: Path,
    chat_id: int = 1,
    telemetry_enabled: bool = False,
) -> SimpleNamespace:
    translations = load_translations("config/i18n/ru.yml")

    return SimpleNamespace(
        bot_data={
            "chat_id": chat_id,
            "telemetry_enabled": telemetry_enabled,
            "telemetry_path": tmp_path / "telemetry" / "telegram_updates.jsonl",
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
                "promo": {
                    "stock_min": 10,
                    "units_max": 2,
                },
                "quiz": {
                    "enabled": True,
                    "path": "config/quiz/pharmacy_quiz.json",
                },
                "i18n": {
                    "lang": "ru",
                    "path": "config/i18n/ru.yml",
                },
            },
            "storage_dir": tmp_path,
            "translations": translations,
        }
    )


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


def test_start_denies_non_admin(tmp_path: Path) -> None:
    update = make_message_update(chat_id=2, text="/start")
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_async_handler(handle_start, update, context)

    assert update.effective_message.replies[-1] == "Доступ запрещен: только admin chat."


def test_unknown_command_does_not_crash(tmp_path: Path) -> None:
    update = make_message_update(chat_id=1, text="/abc", update_id=20)
    context = make_context(tmp_path=tmp_path, chat_id=1)

    run_async_handler(handle_unknown_command, update, context)

    assert (
        update.effective_message.replies[-1]
        == "Неизвестная команда. Используйте /help."
    )


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


def test_scheduler_not_started_when_disabled(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    app = FakeApp(bot_data=context.bot_data)

    asyncio.run(_start_scheduler_if_enabled(app))

    assert "scheduler_task" not in app.bot_data


def test_scheduler_enabled_without_active_jobs_does_not_create_task(
    tmp_path: Path,
) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    context.bot_data["settings"]["scheduler"]["enabled"] = True
    app = FakeApp(bot_data=context.bot_data)

    asyncio.run(_start_scheduler_if_enabled(app))

    assert "scheduler_task" not in app.bot_data
    assert "scheduler_stop_event" not in app.bot_data


def test_scheduler_loop_stops_cleanly(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    app = FakeApp(bot_data=context.bot_data)
    stop_event = asyncio.Event()
    stop_event.set()

    asyncio.run(_scheduler_loop(app, stop_event))


def test_run_promo_returns_report(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)

    promo_update = make_message_update(chat_id=1, text="/run_promo", update_id=60)
    run_async_handler(handle_run_promo, promo_update, context)

    assert "Promo Scan Report" in promo_update.effective_message.replies[-1]


def test_run_promo_button_calls_handler(tmp_path: Path) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    update = make_callback_update(chat_id=1, callback_data=BUTTON_RUN_PROMO)

    run_async_handler(handle_menu_button, update, context)

    assert update.callback_query.answered is True
    assert "Promo Scan Report" in update.effective_message.replies[-1]


def test_run_rop_returns_operator_text(tmp_path: Path, monkeypatch) -> None:
    context = make_context(tmp_path=tmp_path, chat_id=1)
    update = make_message_update(chat_id=1, text="/run_rop", update_id=80)

    captured: dict[str, Any] = {}

    def fake_run_rop_operator_case(
        settings: dict,
        storage_dir: Path,
        logger: logging.Logger,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        captured["settings"] = settings
        captured["storage_dir"] = storage_dir
        captured["logger"] = logger
        captured["payload"] = payload
        return {"operator_text": "ROP operator run v0"}

    monkeypatch.setattr(
        "beeagent_module.ui.telegram_bot.run_rop_operator_case",
        fake_run_rop_operator_case,
    )

    run_async_handler(handle_run_rop, update, context)

    assert captured["settings"] == context.bot_data["settings"]
    assert captured["storage_dir"] == tmp_path
    assert captured["logger"] == context.bot_data["logger"]
    assert captured["payload"] == {
        "source": "email",
        "sender": "lead@example.com",
        "subject": "Need product details",
        "body": "Please share pricing and delivery terms.",
    }
    assert update.effective_message.replies[-1] == "ROP operator run v0"


def test_build_application_registers_run_rop_command(monkeypatch) -> None:
    class _Filter:
        def __and__(self, other: Any) -> "_Filter":
            _ = other
            return self

        def __invert__(self) -> "_Filter":
            return self

    class FakeCommandHandler:
        def __init__(self, command: str, callback: Any) -> None:
            self.command = command
            self.callback = callback

    class FakeCallbackQueryHandler:
        def __init__(self, callback: Any) -> None:
            self.callback = callback

    class FakeMessageHandler:
        def __init__(self, filt: Any, callback: Any) -> None:
            self.filters = filt
            self.callback = callback

    class FakeApplication:
        def __init__(self) -> None:
            self.bot_data: dict[str, Any] = {}
            self.handlers: list[Any] = []

        def add_handler(self, handler: Any) -> None:
            self.handlers.append(handler)

    class FakeApplicationBuilder:
        def __init__(self) -> None:
            self._app = FakeApplication()

        def token(self, token: str) -> "FakeApplicationBuilder":
            _ = token
            return self

        def post_init(self, callback: Any) -> "FakeApplicationBuilder":
            _ = callback
            return self

        def post_shutdown(self, callback: Any) -> "FakeApplicationBuilder":
            _ = callback
            return self

        def build(self) -> FakeApplication:
            return self._app

    fake_filters = types.SimpleNamespace(TEXT=_Filter(), COMMAND=_Filter())
    fake_telegram_ext = types.ModuleType("telegram.ext")
    setattr(fake_telegram_ext, "ApplicationBuilder", FakeApplicationBuilder)
    setattr(fake_telegram_ext, "CallbackQueryHandler", FakeCallbackQueryHandler)
    setattr(fake_telegram_ext, "CommandHandler", FakeCommandHandler)
    setattr(fake_telegram_ext, "MessageHandler", FakeMessageHandler)
    setattr(fake_telegram_ext, "filters", fake_filters)

    fake_telegram_pkg = types.ModuleType("telegram")
    setattr(fake_telegram_pkg, "ext", fake_telegram_ext)

    monkeypatch.setitem(sys.modules, "telegram", fake_telegram_pkg)
    monkeypatch.setitem(sys.modules, "telegram.ext", fake_telegram_ext)
    monkeypatch.setattr(
        "beeagent_module.ui.telegram_bot.get_storage_dir", lambda: Path("/tmp")
    )

    app = _build_application(
        token="token",
        chat_id=1,
        telemetry_enabled=False,
        logger=logging.getLogger("test.telegram"),
        settings={},
        translations={},
    )

    commands = [
        getattr(handler, "command")
        for handler in app.handlers
        if getattr(handler, "command", None) is not None
    ]
    assert "run_rop" in commands
    assert "last" not in commands
