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
from beeagent_module.cases.quiz import (
    get_last_quiz_case,
    process_quiz_answer_case,
    start_quiz_case,
)
from beeagent_module.core.i18n import load_translations, t
from beeagent_module.core.paths import get_storage_dir
from beeagent_module.core.secrets import load_secrets

BUTTON_RUN_OOS = "run_oos"
BUTTON_RUN_PROMO = "run_promo"
BUTTON_SHOW_REPORT = "show_report"
BUTTON_APPROVE_TASKS = "approve_tasks"
BUTTON_REJECT_TASKS = "reject_tasks"
BUTTON_QUIZ_ANSWER_PREFIX = "qa_"


# Запуск Telegram-режим и стартует polling
def start_telegram_mode(settings: dict, logger: logging.Logger) -> None:
    telegram_cfg = settings["telegram"]
    telegram_enabled = telegram_cfg["enabled"]
    logger.info("telegram mode started")
    logger.info("telegram.enabled=%s", telegram_enabled)

    if not telegram_enabled:
        logger.info("telegram mode skipped because it is disabled")
        return

    i18n_cfg = settings["i18n"]
    translations = load_translations(i18n_cfg["path"])

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
        translations=translations,
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
    translations: dict[str, Any],
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
    application.bot_data["translations"] = translations

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("run_oos", handle_run_oos))
    application.add_handler(CommandHandler("run_promo", handle_run_promo))
    application.add_handler(CommandHandler("last", handle_last))
    application.add_handler(CommandHandler("quiz_pharmacy", handle_quiz_pharmacy))
    application.add_handler(CommandHandler("last_quiz", handle_last_quiz))
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

    text = t(
        application.bot_data["translations"],
        "telegram.scheduler.new_run",
        run_id=result["run_id"],
        alerts=result["alerts_count"],
        tasks=result["tasks_count"],
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
        _t(context, "telegram.start"),
        reply_markup=_build_main_menu(context.bot_data.get("translations")),
    )


# Обработка команды /help и показывает доступные команды
async def handle_help(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="help")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    await message.reply_text(_t(context, "telegram.help"))


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
        await message.reply_text(_t(context, "telegram.no_reports"))
        return

    await message.reply_text(report_text)


# Обработка команды /quiz_pharmacy и инициализация квиза
async def handle_quiz_pharmacy(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="quiz_pharmacy")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    settings = context.bot_data["settings"]
    logger: logging.Logger = context.bot_data["logger"]
    storage_dir = context.bot_data["storage_dir"]
    chat = update.effective_chat
    if chat is None:
        await message.reply_text(_t(context, "telegram.quiz.chat_not_found"))
        return

    result = start_quiz_case(
        settings=settings,
        storage_dir=storage_dir,
        chat_id=chat.id,
        logger=logger,
    )

    if "error" in result:
        await message.reply_text(
            _t(context, "telegram.quiz.start_error", error=result["error"])
        )
        return

    run_id = result["run_id"]
    question_text = result["report_text"]
    quiz_cfg = settings["quiz"]
    quiz_spec_path = quiz_cfg.get("path")

    if quiz_spec_path:
        from beeagent_module.cases.quiz import _load_quiz_spec

        quiz_spec = _load_quiz_spec(quiz_spec_path)
        questions = quiz_spec.get("questions", [])

        if questions:
            q = questions[0]
            options = q.get("options", [])
            keyboard = _build_answer_keyboard(run_id, options)

            await message.reply_text(question_text, reply_markup=keyboard)
            return

    await message.reply_text(question_text)


# Обработка команды /last_quiz и возврат последнего результата
async def handle_last_quiz(update: Any, context: Any) -> None:
    await _track_update_event(update, context, event_type="last_quiz")

    if not await _ensure_allowlist(update, context):
        return

    message = update.effective_message
    if message is None:
        return

    storage_dir = context.bot_data["storage_dir"]
    chat_id = context.bot_data["chat_id"]

    result = get_last_quiz_case(storage_dir, chat_id)
    if result is None:
        await message.reply_text(_t(context, "telegram.quiz.no_results"))
        return

    await message.reply_text(result["report_text"])


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
            await reply(_t(context, "telegram.no_reports"))
            return

        await reply(report_text)
        return

    if query.data == BUTTON_APPROVE_TASKS:
        await _approve_or_reject_tasks(message, context, decision="approved")
        return

    if query.data == BUTTON_REJECT_TASKS:
        await _approve_or_reject_tasks(message, context, decision="rejected")
        return

    if query.data and query.data.startswith(BUTTON_QUIZ_ANSWER_PREFIX):
        await _handle_quiz_answer(message, context, query.data)
        return

    await reply(_t(context, "telegram.unknown_action"))


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

    await message.reply_text(_t(context, "telegram.unknown"))


# Сбор главного inline-меню
def _build_main_menu(translations: dict[str, Any] | None = None):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ModuleNotFoundError:
        return None

    if not isinstance(translations, dict):
        raise RuntimeError("translations not loaded for telegram menu")

    keyboard = [
        [
            InlineKeyboardButton(
                t(translations, "telegram.menu.run_oos"),
                callback_data=BUTTON_RUN_OOS,
            )
        ],
        [
            InlineKeyboardButton(
                t(translations, "telegram.menu.run_promo"),
                callback_data=BUTTON_RUN_PROMO,
            )
        ],
        [
            InlineKeyboardButton(
                t(translations, "telegram.menu.show_report"),
                callback_data=BUTTON_SHOW_REPORT,
            )
        ],
        [
            InlineKeyboardButton(
                t(translations, "telegram.menu.approve"),
                callback_data=BUTTON_APPROVE_TASKS,
            )
        ],
        [
            InlineKeyboardButton(
                t(translations, "telegram.menu.reject"),
                callback_data=BUTTON_REJECT_TASKS,
            )
        ],
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
        await message.reply_text(_t(context, "telegram.access_denied"))

    return False


# Получение перевода для Telegram контекста.
def _t(context: Any, key: str, **vars: Any) -> str:
    translations = context.bot_data.get("translations")
    if not isinstance(translations, dict):
        settings = context.bot_data.get("settings", {})
        i18n_cfg = settings.get("i18n", {})
        i18n_path = i18n_cfg.get("path")
        if not isinstance(i18n_path, str) or not i18n_path:
            raise RuntimeError("Invalid i18n.path for telegram translations")
        translations = load_translations(i18n_path)
        context.bot_data["translations"] = translations

    return t(translations, key, **vars)


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


# Билд клавиатуры с вариантами ответов для вопроса квиза
def _build_quiz_question_keyboard(run_id: str):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ModuleNotFoundError:
        return None

    return InlineKeyboardMarkup([])


# Билд клавиатуры с вариантами ответов для вопроса квиза
def _build_answer_keyboard(run_id: str, options: list[str]):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    except ModuleNotFoundError:
        return None

    keyboard = []
    for i, opt in enumerate(options):
        callback_data = f"{BUTTON_QUIZ_ANSWER_PREFIX}{run_id}_{i}"
        keyboard.append([InlineKeyboardButton(opt, callback_data=callback_data)])

    return InlineKeyboardMarkup(keyboard)


# Обработка нажатия кнопки ответа в квизе
async def _handle_quiz_answer(message: Any, context: Any, callback_data: str) -> None:
    settings = context.bot_data["settings"]
    logger: logging.Logger = context.bot_data["logger"]
    storage_dir = context.bot_data["storage_dir"]
    parts = callback_data.split("_")
    if len(parts) < 3:
        await message.reply_text(_t(context, "telegram.quiz.invalid_data"))
        return

    run_id = "_".join(parts[1:-1])
    try:
        answer_idx = int(parts[-1])
    except ValueError:
        await message.reply_text(_t(context, "telegram.quiz.invalid_answer_index"))
        return

    result = process_quiz_answer_case(
        settings=settings,
        storage_dir=storage_dir,
        run_id=run_id,
        answer_idx=answer_idx,
        logger=logger,
    )

    if "error" in result:
        await message.reply_text(
            _t(context, "telegram.quiz.answer_error", error=result["error"])
        )
        return

    # ответ на вопрос и показ следующего или результата
    feedback = result.get("feedback", "")
    await message.reply_text(feedback)

    if result.get("is_finished"):
        result_data = result.get("result", {})
        report_text = result.get("report_text", "")
        await message.reply_text(report_text)
        logger.info("quiz_finished run_id=%s", run_id)
    else:
        next_question_text = result.get("next_question", "")
        next_q_idx = result.get("next_q_idx", 0)
        quiz_cfg = settings.get("quiz", {})
        quiz_spec_path = quiz_cfg.get("path")

        if quiz_spec_path:
            from beeagent_module.cases.quiz import _load_quiz_spec

            quiz_spec = _load_quiz_spec(quiz_spec_path)
            questions = quiz_spec.get("questions", [])

            if next_q_idx < len(questions):
                q = questions[next_q_idx]
                options = q.get("options", [])
                keyboard = _build_answer_keyboard(run_id, options)

                await message.reply_text(next_question_text, reply_markup=keyboard)
                return

        await message.reply_text(next_question_text)
