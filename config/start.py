import json
import logging
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv

from beeagent_module.cli.auth import ensure_auth_env, handle_auth_cli
from beeagent_module.core.accelerator import detect_accelerator
from beeagent_module.core.cli import (
    RopCliError,
    create_rop_parser,
    handle_rop_current,
    handle_rop_dashboard,
    handle_rop_evaluate_review,
    handle_rop_export_review,
    handle_rop_mvp_pack,
    handle_rop_poll,
    handle_rop_reconcile_bitrix,
    handle_rop_run,
    handle_rop_summary,
    handle_rop_writeback,
)
from beeagent_module.core.document_extractors import (
    DOCLING_EXTRACTOR,
    validate_selected_extractor,
)
from beeagent_module.core.env_sync import ensure_bootstrap_env, sync_env_with_example
from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.module_registry import build_registry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.paths import (
    ensure_dirs,
    get_app_log_path,
    get_project_root,
    get_storage_dir,
)
from beeagent_module.core.runtime_context import generate_run_id, generate_session_id
from beeagent_module.core.settings import load_settings

_BASE_PROFILE = "base"
_DOCLING_PROFILES = {
    "cpu": "docling-cpu",
    "cuda": "docling-cuda",
}
_ALLOWED_PROFILES = frozenset({_BASE_PROFILE, "docling-cpu", "docling-cuda"})
_BEEDRILL_SCENARIOS = {
    "reference_target_containment_replay": {
        "target_profile": "surfpool_local",
        "target_id": "reference_vault",
    },
    "reference_oracle_manipulation_replay": {
        "target_profile": "surfpool_local",
        "target_id": "reference_oracle_market",
    },
}


def bootstrap_runtime() -> None:
    project_root = get_project_root()
    env_path = project_root / ".env"
    settings_path = project_root / "config" / "settings.yml"

    sync_env_with_example(project_root)
    load_dotenv(dotenv_path=env_path, override=False)
    ensure_bootstrap_env(
        project_root=project_root,
        settings_path=settings_path,
        env_path=env_path,
        quiet=True,
    )
    load_dotenv(dotenv_path=env_path, override=False)

    settings = load_settings(settings_path)
    profile = _resolve_runtime_profile(settings)
    _sync_runtime_profile(profile, project_root)
    if profile != _BASE_PROFILE:
        from beeagent_module.core.document_extraction import prepare_docling_assets

        prepare_docling_assets()


def _resolve_runtime_profile(settings: dict) -> str:
    attachments = settings["rop"]["attachments"]
    if attachments["enabled"] is not True:
        return _BASE_PROFILE
    extraction = attachments["extraction"]
    engine = str(extraction["engine"]).strip()
    validate_selected_extractor(engine)
    if engine == DOCLING_EXTRACTOR:
        return _DOCLING_PROFILES[detect_accelerator()]
    raise RuntimeError(
        f"No locked dependency profile for document extractor '{engine}'"
    )


def _sync_runtime_profile(profile: str, project_root: Path) -> None:
    if profile not in _ALLOWED_PROFILES:
        raise RuntimeError(f"Invalid runtime dependency profile '{profile}'")
    argv = ["uv", "sync", "--frozen"]
    if profile != _BASE_PROFILE:
        argv.extend(["--extra", profile])
    completed = subprocess.run(
        argv,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Failed to sync runtime dependency profile '{profile}': "
            f"{completed.stderr.strip()}"
        )


def main() -> None:
    project_root = get_project_root()
    args = sys.argv[1:]
    env_path = project_root / ".env"
    settings_path = project_root / "config" / "settings.yml"

    if args and args[0] == "auth-init":
        sync_env_with_example(project_root)
        load_dotenv(dotenv_path=env_path, override=False)
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

    if args and args[0] == "bootstrap":
        bootstrap_runtime()
        return

    sync_env_with_example(project_root)
    load_dotenv(dotenv_path=env_path, override=False)
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

    if args and args[0] == "beedrill":
        sys.exit(_handle_beedrill_cli(args[1:], settings=settings, logger=logger))

    if args and args[0] == "docling-assets-prepare":
        from beeagent_module.core.document_extraction import prepare_docling_assets

        logger.info("Preparing local Docling model assets...")
        prepare_docling_assets()
        logger.info("Local Docling model assets prepared")
        return

    logger.error("Unknown CLI command: %s", args[0])
    print(
        f"Error: Unknown CLI command: {args[0]}. Supported commands: telegram, web, routes, rop, beedrill, auth, auth-init, docling-assets-prepare",
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
        elif args.rop_command == "evaluate-review":
            handle_rop_evaluate_review(args, logger=logger)
        elif args.rop_command == "writeback":
            handle_rop_writeback(args, settings=settings, logger=logger)
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


def _handle_beedrill_cli(
    cli_args: list[str],
    settings: dict,
    logger: logging.Logger,
) -> int:
    if (
        len(cli_args) != 3
        or cli_args[0] != "run"
        or cli_args[1] != "--scenario"
        or cli_args[2] not in _BEEDRILL_SCENARIOS
    ):
        print(
            "Usage: start.py beedrill run --scenario "
            "{reference_target_containment_replay|reference_oracle_manipulation_replay}",
            file=sys.stderr,
        )
        return 2
    scenario_id = cli_args[2]
    run_id = generate_run_id()
    try:
        registry = build_registry(settings, logger)
        result = execute_module_case(
            registry=registry,
            module_id="beedrill",
            case_type=scenario_id,
            payload=_BEEDRILL_SCENARIOS[scenario_id],
            storage_dir=get_storage_dir(),
            logger=logger,
            run_id=run_id,
            session_id=generate_session_id(),
        )
    except Exception as exc:
        logger.error("BeeDrill regression execution failed: %s", exc)
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "scenario_id": scenario_id,
                    "execution_status": "error",
                    "security_verdict": None,
                    "artifact_refs": [],
                },
                sort_keys=True,
            )
        )
        return 3
    execution_status = result.status
    security_verdict = (
        result.data.get("security_verdict") if execution_status == "ok" else None
    )
    artifact_dir = f"runs/{run_id}/module-beedrill"
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "execution_status": execution_status,
        "security_verdict": security_verdict,
        "artifact_refs": [
            f"{artifact_dir}/module_result.json",
            f"{artifact_dir}/{scenario_id}.json",
        ],
    }
    print(json.dumps(summary, sort_keys=True))
    if security_verdict == "pass":
        return 0
    if security_verdict == "fail":
        return 1
    return 3


if __name__ == "__main__":
    main()
