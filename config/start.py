import logging
import sys
from copy import deepcopy

from dotenv import load_dotenv

from beeagent_module.core.cli import (
    RopCliError,
    create_rop_parser,
    handle_rop_export_review,
    handle_rop_reconcile_bitrix,
    handle_rop_run,
    handle_rop_summary,
)
from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.paths import ensure_dirs, get_app_log_path, get_project_root
from beeagent_module.core.settings import load_settings


# Главная точка входа: загрузка настроек, инициализация логов и директорий, запуск приложения
def main() -> None:
    project_root = get_project_root()

    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)

    settings_path = project_root / "config" / "settings.yml"
    settings = load_settings(settings_path)

    ensure_dirs()
    log_path = get_app_log_path()

    log_cfg = settings["logging"]
    setup_logging(
        log_path=log_path,
        level=log_cfg["level"],
        clear_logs=log_cfg["clear_logs"],
        utc=log_cfg["utc"],
    )

    logger = get_logger("app")

    args = sys.argv[1:]

    if not args:
        from beeagent_module.core.app import run_app

        logger.info("No CLI args provided, using run.mode from settings")
        run_app(settings=settings, logger=logger)
        return

    if args and args[0] == "telegram":
        from beeagent_module.core.app import run_app

        logger.info("Explicit telegram mode requested")
        telegram_settings = _with_run_mode(settings=settings, mode="telegram")
        run_app(settings=telegram_settings, logger=logger)
        return

    if args and args[0] == "web":
        from beeagent_module.cli.web import run_web

        exit_code = run_web(args[1:])
        sys.exit(exit_code)

    if args and args[0] == "routes":
        from beeagent_module.cli.web import run_routes

        exit_code = run_routes(args[1:])
        sys.exit(exit_code)

    if args and args[0] == "rop":
        _handle_rop_cli(args[1:], settings=settings, logger=logger)
        return

    logger.error("Unknown CLI command: %s", args[0])
    print(
        f"Error: Unknown CLI command: {args[0]}. Supported commands: telegram, web, routes, rop",
        file=sys.stderr,
    )
    sys.exit(2)


# Создание in-memory settings override для явного CLI runtime mode без изменения config/settings.yml
def _with_run_mode(settings: dict, mode: str) -> dict:
    effective_settings = deepcopy(settings)
    effective_settings["run"]["mode"] = mode
    return effective_settings


# Обработка ROP CLI команд: парсит аргументы, вызывает соответствующие обработчики и обрабатывает ошибки, логируя их и выводя сообщения в stderr
def _handle_rop_cli(
    cli_args: list[str],
    settings: dict,
    logger: logging.Logger,
) -> None:
    try:
        parser = create_rop_parser()
        args = parser.parse_args(cli_args)

        if args.rop_command == "run":
            handle_rop_run(args, settings=settings, logger=logger)
        elif args.rop_command == "summary":
            handle_rop_summary(args, logger=logger)
        elif args.rop_command == "export-review":
            handle_rop_export_review(args, logger=logger)
        elif args.rop_command == "reconcile-bitrix":
            handle_rop_reconcile_bitrix(args, settings=settings, logger=logger)
        else:
            logger.error("Unknown ROP CLI command: %s", args.rop_command)
            sys.exit(1)

    except RopCliError as exc:
        logger.error("ROP CLI error: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except SystemExit as exc:
        raise exc
    except Exception as exc:
        logger.error("ROP CLI unexpected error: %s", exc, exc_info=True)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
