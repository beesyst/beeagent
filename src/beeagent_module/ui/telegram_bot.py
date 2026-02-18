from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from beeagent_module.core.paths import get_storage_dir
from beeagent_module.core.secrets import load_secrets

BUTTON_RUN_OOS = "run_oos"
BUTTON_SHOW_REPORT = "show_report"


# Запуск Telegram-режим и стартует polling
def start_telegram_mode(settings: dict, logger: logging.Logger) -> None:
    telegram_cfg = settings["telegram"]
    telegram_enabled = telegram_cfg["enabled"]
    logger.info("telegram mode started")
    logger.info("telegram.enabled=%s", telegram_enabled)

    if not telegram_enabled:
        logger.info("telegram mode skipped because it is disabled")
        return

    secrets = load_secrets(settings)

    token = str(secrets["telegram_bot_token"])
    chat_id = secrets["telegram_chat_id"]

    if not isinstance(chat_id, int):
        raise RuntimeError("telegram_chat_id must be int (loaded from env)")

    application = _build_application(
        token=token,
        chat_id=chat_id,
        telemetry_enabled=telegram_cfg["telemetry_enabled"],
        logger=logger,
        settings=settings,
    )
    logger.info("telegram bot polling started")
    application.run_polling(drop_pending_updates=True)


# Создание и настройка приложения Telegram
def _build_application(
    token: str,
    chat_id: int,
    telemetry_enabled: bool,
    logger: logging.Logger,
    settings: dict,
):
    from telegram.ext import (
        ApplicationBuilder,
        CallbackQueryHandler,
        CommandHandler,
        MessageHandler,
        filters,
    )

    application = ApplicationBuilder().token(token).build()
    storage_dir = get_storage_dir()

    application.bot_data["chat_id"] = chat_id
    application.bot_data["telemetry_enabled"] = telemetry_enabled
    application.bot_data["settings"] = settings
    application.bot_data["telemetry_path"] = (
        storage_dir / "telemetry" / "telegram_updates.jsonl"
    )
    application.bot_data["last_report_path"] = (
        storage_dir / "reports" / "last_oos_report.md"
    )
    application.bot_data["logger"] = logger

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("run_oos", handle_run_oos))
    application.add_handler(CommandHandler("last", handle_last))
    application.add_handler(CallbackQueryHandler(handle_menu_button))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))

    return application


# Обработка команды /start и показывает меню
async def handle_start(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="start")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "BeeAgent bot is ready. Use commands or buttons below.",
        reply_markup=_build_main_menu(),
    )


# Обработка команды /help и показывает доступные команды
async def handle_help(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="help")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    await message.reply_text(
        "Available commands:\n"
        "/start - show menu\n"
        "/help - show help\n"
        "/run_oos - run mock OOS scan\n"
        "/last - show last report"
    )


# Обработка команды /run_oos и формирование mock-отчета
async def handle_run_oos(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="run_oos")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    await _run_oos_and_reply(message, context)


# Обработка команды /last и возвращает последний отчет
async def handle_last(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="last")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    report_path = _get_last_report_path(context)
    if not report_path.exists():
        reply = getattr(message, "reply_text", None)
        if reply is None:
            return

        await reply("No reports yet. Run /run_oos first.")
        return

    report_text = report_path.read_text(encoding="utf-8")
    await message.reply_text(report_text)


# Обработка нажатий inline-кнопок
async def handle_menu_button(
    update: Any,
    context: Any,
) -> None:
    await _track_update_event(update, context, event_type="button")

    query = update.callback_query
    if query is None:
        return

    await query.answer()

    if not await _ensure_allowlist(update, context):
        return

    message = query.message
    if message is None:
        return

    reply = getattr(message, "reply_text", None)
    if reply is None:
        return

    if query.data == BUTTON_RUN_OOS:
        await _run_oos_and_reply(message, context)
        return

    if query.data == BUTTON_SHOW_REPORT:
        report_path = _get_last_report_path(context)
        if not report_path.exists():
            await reply("No reports yet. Run /run_oos first.")
            return

        report_text = report_path.read_text(encoding="utf-8")
        await reply(report_text)
        return

    await reply("Unknown action.")


# Обработка неизвестных команд без падения
async def handle_unknown_command(
    update: Any,
    context: Any,
) -> None:
    await _track_update_event(update, context, event_type="unknown_command")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    await message.reply_text("Unknown command. Use /help.")


# Сбор главного inline-меню
def _build_main_menu():
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ModuleNotFoundError:
        return None

    keyboard = [
        [InlineKeyboardButton("Run OOS Scan", callback_data=BUTTON_RUN_OOS)],
        [InlineKeyboardButton("Show Report", callback_data=BUTTON_SHOW_REPORT)],
    ]
    return InlineKeyboardMarkup(keyboard)


# Выполнение сценария OOS и сохранение отчета
async def _run_oos_and_reply(message: Any, context: Any) -> None:
    report_text = _build_mock_report()

    settings = context.bot_data["settings"]
    _persist_mock_dataset(settings)

    report_path = _get_last_report_path(context)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_text, encoding="utf-8")
    await message.reply_text(report_text)


# Билд текста mock-отчета
def _build_mock_report() -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    return (
        "Last OOS report\n"
        f"created_at: {created_at}\n"
        "alerts_total: 2\n"
        "- STORE-001 | SKU-1001 | shelf_signal=false\n"
        "- STORE-002 | SKU-1012 | shelf_signal=false"
    )


# Принудительное сохранение мокового набора данных при каждом запуске OOS для тестов и демонстрации
def _persist_mock_dataset(settings: dict) -> None:
    from beeagent_module.core.paths import get_storage_dir
    from beeagent_module.mock.dataset import generate_mock_dataset, save_mock_dataset

    mock_cfg = settings["mock"]
    storage_dir = get_storage_dir()

    dataset = generate_mock_dataset(
        seed=mock_cfg["seed"],
        weeks=mock_cfg["weeks"],
        stores=mock_cfg["stores"],
        skus=mock_cfg["skus"],
        category=mock_cfg["category"],
    )
    save_mock_dataset(dataset=dataset, storage_dir=storage_dir)


# Возврат пути к последнему отчету
def _get_last_report_path(context: Any) -> Path:
    return context.bot_data["last_report_path"]


# Чек allowlist по chat_id и отклонение чухих чатов
async def _ensure_allowlist(
    update: Any,
    context: Any,
) -> bool:
    allowed_chat_id = context.bot_data["chat_id"]
    chat = update.effective_chat
    logger: logging.Logger = context.bot_data["logger"]

    if chat is not None and chat.id == allowed_chat_id:
        return True

    denied_chat_id = chat.id if chat is not None else None
    logger.warning("allowlist denied chat_id=%s", denied_chat_id)

    message = update.effective_message
    if message is not None:
        await message.reply_text("Access denied: admin chat only.")

    return False


# Запись телеметрии Telegram-событий в jsonl
async def _track_update_event(
    update: Any,
    context: Any,
    event_type: str,
) -> None:
    telemetry_enabled = context.bot_data.get("telemetry_enabled", False)
    if not telemetry_enabled:
        return

    telemetry_path = context.bot_data["telemetry_path"]
    telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    user = update.effective_user
    chat = update.effective_chat
    query_data = update.callback_query.data if update.callback_query else None

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        "update_id": update.update_id,
        "chat_id": chat.id if chat else None,
        "user_id": user.id if user else None,
        "command": update.effective_message.text if update.effective_message else None,
        "callback_data": query_data,
    }

    with telemetry_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
