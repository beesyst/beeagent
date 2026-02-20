from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from beeagent_module.cases.oos import (
    approve_last_run_case,
    get_last_report_case,
    run_oos_case,
)
from beeagent_module.cases.promo import run_promo_case
from beeagent_module.core.paths import get_storage_dir
from beeagent_module.core.secrets import load_secrets

BUTTON_RUN_OOS = "run_oos"
BUTTON_RUN_PROMO = "run_promo"
BUTTON_SHOW_REPORT = "show_report"
BUTTON_APPROVE_TASKS = "approve_tasks"
BUTTON_REJECT_TASKS = "reject_tasks"


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

    application = (
        ApplicationBuilder()
        .token(token)
        .post_init(_on_application_start)
        .post_shutdown(_on_application_shutdown)
        .build()
    )
    storage_dir = get_storage_dir()

    application.bot_data["chat_id"] = chat_id
    application.bot_data["telemetry_enabled"] = telemetry_enabled
    application.bot_data["settings"] = settings
    application.bot_data["storage_dir"] = storage_dir
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
    application.add_handler(CommandHandler("run_promo", handle_run_promo))
    application.add_handler(CommandHandler("last", handle_last))
    application.add_handler(CallbackQueryHandler(handle_menu_button))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))

    return application


# Запуск scheduled-run режима: бесконечный цикл с интервалом из настроек и выполнением сценария OOS
async def _on_application_start(application: Any) -> None:
    await _start_scheduler_if_enabled(application)


# Корректная остановка при завершении приложения: остановка цикла scheduled-run
async def _on_application_shutdown(application: Any) -> None:
    await _stop_scheduler(application)


# Цикл для scheduled-run: выполнение сценария OOS и отправка отчета в Telegram по интервалу из настроек
async def _start_scheduler_if_enabled(application: Any) -> None:
    settings = application.bot_data["settings"]
    logger: logging.Logger = application.bot_data["logger"]
    scheduler_cfg = settings["scheduler"]

    if not scheduler_cfg["enabled"]:
        logger.info("scheduler disabled")
        return

    if application.bot_data.get("scheduler_task") is not None:
        return

    stop_event = asyncio.Event()
    scheduler_task = asyncio.create_task(_scheduler_loop(application, stop_event))
    application.bot_data["scheduler_stop_event"] = stop_event
    application.bot_data["scheduler_task"] = scheduler_task

    logger.info(
        "scheduler started interval=%s start_run=%s",
        scheduler_cfg["interval"],
        scheduler_cfg["start_run"],
    )


# Корректная остановка цикла scheduled-run при завершении приложения
async def _stop_scheduler(application: Any) -> None:
    logger: logging.Logger = application.bot_data["logger"]
    scheduler_task = application.bot_data.get("scheduler_task")
    stop_event = application.bot_data.get("scheduler_stop_event")

    if stop_event is not None:
        stop_event.set()

    if scheduler_task is not None:
        try:
            await asyncio.wait_for(scheduler_task, timeout=5)
        except TimeoutError:
            scheduler_task.cancel()
            logger.warning("scheduler shutdown timeout, task cancelled")


# Цикл для scheduled-run: выполнение сценария OOS и отправка отчета в Telegram по интервалу из настроек
async def _scheduler_loop(application: Any, stop_event: asyncio.Event) -> None:
    settings = application.bot_data["settings"]
    scheduler_cfg = settings["scheduler"]
    interval = scheduler_cfg["interval"]

    if scheduler_cfg["start_run"]:
        await _run_scheduled_oos_tick(application)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass

        if stop_event.is_set():
            break

        await _run_scheduled_oos_tick(application)


# Выполнение сценария OOS для scheduled-run и отправка отчета в Telegram, с логированием ошибок
async def _run_scheduled_oos_tick(application: Any) -> None:
    settings = application.bot_data["settings"]
    logger: logging.Logger = application.bot_data["logger"]
    storage_dir = application.bot_data["storage_dir"]
    chat_id = application.bot_data["chat_id"]

    try:
        result = run_oos_case(
            settings=settings,
            storage_dir=storage_dir,
            logger=logger,
            trigger="scheduled",
        )
    except Exception:
        logger.exception("scheduled run failed")
        return

    text = (
        "New run ready → Approve/Reject\n"
        f"Run ID: {result['run_id']}\n"
        f"Alerts: {result['alerts_count']}, Tasks: {result['tasks_count']}"
    )

    try:
        await application.bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        logger.exception("failed to send scheduled notification")


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
        "/run_promo - run promo scan\n"
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


# Обработка команды /run_promo и формирование promo-отчета
async def handle_run_promo(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="run_promo")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    await _run_promo_and_reply(message, context)


# Обработка команды /last и возвращает последний отчет
async def handle_last(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="last")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    storage_dir = context.bot_data["storage_dir"]
    report_text = get_last_report_case(storage_dir)
    if report_text is None:
        await message.reply_text("No reports yet. Run /run_oos first.")
        return

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

    if query.data == BUTTON_RUN_PROMO:
        await _run_promo_and_reply(message, context)
        return

    if query.data == BUTTON_SHOW_REPORT:
        storage_dir = context.bot_data["storage_dir"]
        report_text = get_last_report_case(storage_dir)
        if report_text is None:
            await reply("No reports yet. Run /run_oos first.")
            return

        await reply(report_text)
        return

    if query.data == BUTTON_APPROVE_TASKS:
        await _approve_or_reject_tasks(message, context, decision="approved")
        return

    if query.data == BUTTON_REJECT_TASKS:
        await _approve_or_reject_tasks(message, context, decision="rejected")
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
        [InlineKeyboardButton("Run Promo Scan", callback_data=BUTTON_RUN_PROMO)],
        [InlineKeyboardButton("Show Report", callback_data=BUTTON_SHOW_REPORT)],
        [InlineKeyboardButton("Approve Tasks", callback_data=BUTTON_APPROVE_TASKS)],
        [InlineKeyboardButton("Reject Tasks", callback_data=BUTTON_REJECT_TASKS)],
    ]
    return InlineKeyboardMarkup(keyboard)


# Выполнение сценария OOS через LangGraph и сохранение отчета
async def _run_oos_and_reply(message: Any, context: Any) -> None:
    settings = context.bot_data["settings"]
    logger: logging.Logger = context.bot_data["logger"]
    storage_dir = context.bot_data["storage_dir"]

    result = run_oos_case(
        settings=settings,
        storage_dir=storage_dir,
        logger=logger,
        trigger="manual",
    )

    report_text = result["report_text"]

    await message.reply_text(report_text)


# Выполнение сценария promo через LangGraph и отправка отчета
async def _run_promo_and_reply(message: Any, context: Any) -> None:
    settings = context.bot_data["settings"]
    logger: logging.Logger = context.bot_data["logger"]
    storage_dir = context.bot_data["storage_dir"]

    result = run_promo_case(
        settings=settings,
        storage_dir=storage_dir,
        logger=logger,
        trigger="manual",
    )

    report_text = result["report_text"]

    await message.reply_text(report_text)


# Обработка одобрения или отклонения задач и сохранение результата
async def _approve_or_reject_tasks(
    message: Any,
    context: Any,
    decision: str,
) -> None:
    settings = context.bot_data["settings"]
    storage_dir = context.bot_data["storage_dir"]
    result_text = approve_last_run_case(settings, storage_dir, decision)
    await message.reply_text(result_text)


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


# Чек включена ли телеметрия и запись события
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
