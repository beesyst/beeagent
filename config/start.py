import logging
import sys
from copy import deepcopy

from dotenv import load_dotenv

from beeagent_module.cli.auth import ensure_auth_env, handle_auth_cli
from beeagent_module.core.cli import (
    RopCliError,
    create_rop_parser,
    handle_rop_action_drafts,
    handle_rop_current,
    handle_rop_dashboard,
    handle_rop_evaluate_review,
    handle_rop_export_review,
    handle_rop_mvp_pack,
    handle_rop_recommendations,
    handle_rop_reconcile_bitrix,
    handle_rop_poll,
    handle_rop_run,
    handle_rop_summary,
)
from beeagent_module.core.env_sync import ensure_bootstrap_env, sync_env_with_example
from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.paths import ensure_dirs, get_app_log_path, get_project_root
from beeagent_module.core.settings import load_settings


def main() -> None:
    project_root = get_project_root()
    args = sys.argv[1:]
    env_path = project_root / ".env"
    settings_path = project_root / "config" / "settings.yml"

    sync_env_with_example(project_root)
    load_dotenv(dotenv_path=env_path, override=False)

    if args and args[0] == "auth-init":
        rotate = _parse_auth_init_args(args[1:])
        if rotate is None:
            ensure_bootstrap_env(
                project_root=project_root,
                settings_path=settings_path,
                env_path=env_path,
                quiet=False,
            )
        else:
            ensure_auth_env(
                project_root=project_root,
                settings_path=settings_path,
                env_path=env_path,
                rotate=rotate,
                quiet=False,
            )
        return

    ensure_bootstrap_env(
        project_root=project_root,
        settings_path=settings_path,
        env_path=env_path,
        quiet=True,
    )
    load_dotenv(dotenv_path=env_path, override=False)

    if args and args[0] == "auth":
        exit_code = handle_auth_cli(args[1:], project_root=project_root)
        sys.exit(exit_code)

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
        f"Error: Unknown CLI command: {args[0]}. Supported commands: telegram, web, routes, rop, auth, auth-init",
        file=sys.stderr,
    )
    sys.exit(2)


def _parse_auth_init_args(cli_args: list[str]) -> str | None:
    if not cli_args:
        return None
    if len(cli_args) == 2 and cli_args[0] == "--rotate":
        return cli_args[1]

    print(
        "Usage:\n"
        "  start.py auth-init\n"
        "  start.py auth-init --rotate <principal-id-or-username|session|all>",
        file=sys.stderr,
    )
    sys.exit(2)


def _with_run_mode(settings: dict, mode: str) -> dict:
    effective_settings = deepcopy(settings)
    effective_settings["run"]["mode"] = mode
    return effective_settings


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
        elif args.rop_command == "poll":
            handle_rop_poll(args, settings=settings, logger=logger)
        elif args.rop_command == "summary":
            handle_rop_summary(args, logger=logger)
        elif args.rop_command == "export-review":
            handle_rop_export_review(args, logger=logger)
        elif args.rop_command == "reconcile-bitrix":
            handle_rop_reconcile_bitrix(args, settings=settings, logger=logger)
        elif args.rop_command == "current":
            handle_rop_current(args, settings=settings, logger=logger)
        elif args.rop_command == "dashboard":
            handle_rop_dashboard(args, settings=settings, logger=logger)
        elif args.rop_command == "mvp-pack":
            handle_rop_mvp_pack(args, settings=settings, logger=logger)
        elif args.rop_command == "action-drafts":
            handle_rop_action_drafts(args, logger=logger)
        elif args.rop_command == "evaluate-review":
            handle_rop_evaluate_review(args, logger=logger)
        elif args.rop_command == "recommendations":
            handle_rop_recommendations(args, settings=settings, logger=logger)
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
