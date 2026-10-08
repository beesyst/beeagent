import json
import logging
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from dotenv import load_dotenv

from beeagent_module.cli.auth import ensure_auth_env, handle_auth_cli
from beeagent_module.core.accelerator import detect_accelerator
from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.beedrill_ai_assist import run_beedrill_ai_assist
from beeagent_module.core.beedrill_toolchain import (
    NativeToolchainError,
    ensure_native_tools,
)
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
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.module_registry import ModuleRegistry, build_registry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.paths import (
    ensure_dirs,
    get_app_log_path,
    get_project_root,
    get_storage_dir,
)
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)
from beeagent_module.core.settings import _is_module_enabled, load_settings

_DOCLING_PROFILES = {
    "cpu": "docling-cpu",
    "cuda": "docling-cuda",
}
_EXTRA_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_BEEDRILL_SCENARIOS = {
    "reference_target_containment_replay": {
        "target_profile": "surfpool_local",
        "target_id": "reference_vault",
    },
    "reference_oracle_manipulation_replay": {
        "target_profile": "surfpool_local",
        "target_id": "reference_oracle_market",
    },
    "spl_token_freeze_containment_replay": {
        "target_profile": "surfpool_local",
        "target_id": "spl_token_freeze_containment",
    },
}
_BEEDRILL_DIAGNOSTIC_REASONS = {
    "missing_surfpool",
    "missing_solana_cli",
    "missing_cargo",
    "missing_sbf_builder",
    "incompatible_toolchain",
    "surfpool_startup_failed",
    "rpc_unavailable",
    "build_failed",
    "timeout",
    "cleanup_failed",
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
    extras = _resolve_runtime_extras(settings)
    _sync_runtime_extras(extras, project_root)
    if any(extra in _DOCLING_PROFILES.values() for extra in extras):
        from beeagent_module.core.document_extraction import prepare_docling_assets

        prepare_docling_assets()


def _resolve_runtime_extras(settings: dict) -> list[str]:
    extras = {
        item["install_extra"]
        for item in settings["modules"]["registry"]
        if item["enabled"] is True and "install_extra" in item
    }
    rop_enabled = any(
        item["id"] == "beeagent-rop" and item["enabled"] is True
        for item in settings["modules"]["registry"]
    )
    attachments = settings["rop"]["attachments"]
    if rop_enabled and attachments["enabled"] is True:
        extraction = attachments["extraction"]
        engine = str(extraction["engine"]).strip()
        validate_selected_extractor(engine)
        if engine != DOCLING_EXTRACTOR:
            raise RuntimeError(
                f"No locked dependency profile for document extractor '{engine}'"
            )
        extras.add(_DOCLING_PROFILES[detect_accelerator()])
    return sorted(extras)


def _sync_runtime_extras(extras: list[str], project_root: Path) -> None:
    if any(
        not isinstance(extra, str) or not _EXTRA_NAME_RE.fullmatch(extra)
        for extra in extras
    ):
        raise RuntimeError("Invalid runtime dependency extra")
    argv = ["uv", "sync", "--frozen", "--no-dev"]
    for extra in sorted(set(extras)):
        argv.extend(["--extra", extra])
    completed = subprocess.run(
        argv,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Failed to sync runtime dependency extras: "
            + ", ".join(sorted(set(extras)))
            + ": "
            + completed.stderr.strip()
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
        if not _is_module_enabled(settings, "beeagent-rop"):
            raise RopCliError("beeagent-rop module is disabled")

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


def _beedrill_error_record(run_id: str, scenario_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "scenario_id": scenario_id,
        "execution_status": "error",
        "security_verdict": None,
        "artifact_refs": [],
    }


def _execute_beedrill_scenario(
    registry: ModuleRegistry,
    scenario_id: str,
    logger: logging.Logger,
    run_id: str | None = None,
) -> dict[str, object]:
    scenario_run_id = run_id or generate_run_id()
    try:
        result = execute_module_case(
            registry=registry,
            module_id="beedrill",
            case_type=scenario_id,
            payload=_BEEDRILL_SCENARIOS[scenario_id],
            storage_dir=get_storage_dir(),
            logger=logger,
            run_id=scenario_run_id,
            session_id=generate_session_id(),
        )
    except Exception:
        logger.error("BeeDrill regression execution failed")
        return _beedrill_error_record(scenario_run_id, scenario_id)
    execution_status = result.status
    security_verdict = (
        result.data.get("security_verdict") if execution_status == "ok" else None
    )
    explanation_facts = (
        result.data.get("explanation_facts") if execution_status == "ok" else None
    )
    diagnostic_reason = (
        result.data.get("diagnostic_reason") if execution_status != "ok" else None
    )
    artifact_dir = f"runs/{scenario_run_id}/module-beedrill"
    record = {
        "schema_version": 1,
        "run_id": scenario_run_id,
        "scenario_id": scenario_id,
        "execution_status": execution_status,
        "security_verdict": security_verdict,
        "explanation_facts": explanation_facts,
        "artifact_refs": [
            f"{artifact_dir}/module_result.json",
            f"{artifact_dir}/{scenario_id}.json",
        ],
    }
    if (
        isinstance(diagnostic_reason, str)
        and diagnostic_reason in _BEEDRILL_DIAGNOSTIC_REASONS
    ):
        record["diagnostic_reason"] = diagnostic_reason
    return record


def _beedrill_suite_record(record: dict[str, object]) -> dict[str, object]:
    security_verdict = record["security_verdict"]
    if security_verdict != "pass" and security_verdict != "fail":
        security_verdict = None
    return {
        "scenario_id": record["scenario_id"],
        "run_id": record["run_id"],
        "execution_status": record["execution_status"],
        "security_verdict": security_verdict,
        "artifact_refs": record["artifact_refs"],
        "explanation_facts": record.get("explanation_facts"),
        **(
            {"diagnostic_reason": record["diagnostic_reason"]}
            if isinstance(record.get("diagnostic_reason"), str)
            else {}
        ),
    }


def _beedrill_suite_status(record: dict[str, object]) -> str:
    if record["execution_status"] == "ok" and record["security_verdict"] == "pass":
        return "passed"
    if record["execution_status"] == "ok" and record["security_verdict"] == "fail":
        return "failed"
    return "incomplete"


def _handle_beedrill_check(settings: dict, logger: logging.Logger) -> int:
    suite_run_id = generate_run_id("beedrill-suite")
    suite_session_id = generate_session_id("beedrill-suite")
    try:
        registry = build_registry(settings, logger)
        if _is_module_enabled(settings, "beedrill"):
            ensure_native_tools(needs_sbf=True)
    except NativeToolchainError as exc:
        print(f"INCOMPLETE: {exc.reason}. {exc}", file=sys.stderr)
        records = [
            _beedrill_suite_record(
                {
                    **_beedrill_error_record(generate_run_id(), scenario_id),
                    **(
                        {"diagnostic_reason": exc.reason}
                        if (
                            scenario_id != "spl_token_freeze_containment_replay"
                            or exc.reason
                            not in {
                                "missing_cargo",
                                "missing_sbf_builder",
                                "missing_solana_cli",
                            }
                        )
                        else {}
                    ),
                }
            )
            for scenario_id in _BEEDRILL_SCENARIOS
        ]
    except Exception:
        logger.error("BeeDrill regression suite setup failed")
        records = [
            _beedrill_suite_record(
                _beedrill_error_record(generate_run_id(), scenario_id)
            )
            for scenario_id in _BEEDRILL_SCENARIOS
        ]
    else:
        records = [
            _beedrill_suite_record(
                _execute_beedrill_scenario(registry, scenario_id, logger)
            )
            for scenario_id in _BEEDRILL_SCENARIOS
        ]

    statuses = [_beedrill_suite_status(record) for record in records]
    passed = statuses.count("passed")
    failed = statuses.count("failed")
    incomplete = statuses.count("incomplete")
    suite_status = "incomplete" if incomplete else "fail" if failed else "pass"
    summary = {
        "schema_version": 1,
        "suite_status": suite_status,
        "passed": passed,
        "failed": failed,
        "incomplete": incomplete,
        "scenarios": [
            {key: value for key, value in record.items() if key != "explanation_facts"}
            for record in records
        ],
    }
    artifact_status = suite_status
    artifact_api: ArtifactAPI | None = None
    try:
        artifact_api = ArtifactAPI(
            context=RuntimeContext(
                run_id=suite_run_id,
                session_id=suite_session_id,
                case_type="beedrill_check",
                module_id="beeagent",
                authority=AuthorityLevel.READ_ONLY,
            ),
            storage_dir=get_storage_dir(),
            logger=logger,
        )
        artifact_api.write_json("beedrill_security_regression.json", summary)
    except OSError as exc:
        logger.error("BeeDrill regression suite artifact persistence failed: %s", exc)
        artifact_status = "incomplete"

    ai_assist = settings.get("beedrill", {}).get("ai_assist", {})
    if (
        artifact_status != "incomplete"
        and artifact_api is not None
        and ai_assist.get("enabled") is True
    ):
        try:
            ai_artifact = run_beedrill_ai_assist(
                settings=settings,
                records=records,
                suite_run_id=suite_run_id,
                logger=logger,
            )
            artifact_api.write_json("beedrill_ai_assist.json", ai_artifact)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            logger.warning("BeeDrill AI assist artifact was not persisted: %s", exc)

    print("BeeDrill Security Regression")
    for record, status in zip(records, statuses, strict=True):
        print(f"{status.upper()}: {record['scenario_id']}")
        if status == "incomplete" and record.get("diagnostic_reason"):
            print(
                f"Reason: {record['diagnostic_reason']}. Check native readiness, local RPC availability and the scenario artifact; retry beedrill check."
            )
    print(f"Scenarios: passed={passed} failed={failed} incomplete={incomplete}")
    print(f"Suite status: {artifact_status.upper()}")
    return {"pass": 0, "fail": 1, "incomplete": 3}[artifact_status]


def _handle_beedrill_cli(
    cli_args: list[str],
    settings: dict,
    logger: logging.Logger,
) -> int:
    if cli_args and cli_args[0] == "check":
        if cli_args != ["check"]:
            print("Usage: start.py beedrill check", file=sys.stderr)
            return 2
        return _handle_beedrill_check(settings, logger)
    if (
        len(cli_args) != 3
        or cli_args[0] != "run"
        or cli_args[1] != "--scenario"
        or cli_args[2] not in _BEEDRILL_SCENARIOS
    ):
        print(
            "Usage: start.py beedrill run --scenario "
            "{reference_target_containment_replay|reference_oracle_manipulation_replay|spl_token_freeze_containment_replay}",
            file=sys.stderr,
        )
        return 2
    scenario_id = cli_args[2]
    run_id = generate_run_id()
    try:
        registry = build_registry(settings, logger)
        if _is_module_enabled(settings, "beedrill"):
            ensure_native_tools(
                needs_sbf=scenario_id != "spl_token_freeze_containment_replay"
            )
    except NativeToolchainError as exc:
        print(f"INCOMPLETE: {exc.reason}. {exc}", file=sys.stderr)
        summary = {
            **_beedrill_error_record(run_id, scenario_id),
            "diagnostic_reason": exc.reason,
        }
    except Exception:
        logger.error("BeeDrill regression execution failed")
        summary = _beedrill_error_record(run_id, scenario_id)
    else:
        summary = _execute_beedrill_scenario(registry, scenario_id, logger, run_id)
    print(json.dumps(summary, sort_keys=True))
    if summary["security_verdict"] == "pass":
        return 0
    if summary["security_verdict"] == "fail":
        return 1
    return 3


if __name__ == "__main__":
    main()
