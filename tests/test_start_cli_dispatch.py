from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import pytest
from beesdk.modules import AuthorityLevel, ModuleResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config.start as start_module
from config.start import _with_run_mode


class TestStartCliModeOverrides:
    def test_with_run_mode_overrides_mode_without_mutating_original(self) -> None:
        settings = {
            "run": {"mode": "some_other_mode"},
            "telegram": {"enabled": False},
        }

        effective = _with_run_mode(settings=settings, mode="telegram")

        assert effective["run"]["mode"] == "telegram"
        assert settings["run"]["mode"] == "some_other_mode"

    def test_with_run_mode_supports_web(self) -> None:
        settings = {
            "run": {"mode": "telegram"},
        }

        effective = _with_run_mode(settings=settings, mode="web")

        assert effective["run"]["mode"] == "web"
        assert settings["run"]["mode"] == "telegram"


def _base_settings() -> dict[str, Any]:
    return {
        "run": {"mode": "telegram"},
        "logging": {"level": "INFO", "clear_logs": True, "utc": True},
    }


def test_main_dispatches_web_mode(monkeypatch) -> None:
    called: dict[str, Any] = {}

    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "load_settings", lambda *args, **kwargs: _base_settings()
    )
    monkeypatch.setattr(start_module, "ensure_dirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_module, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "get_app_log_path", lambda *args, **kwargs: Path("logs/app.log")
    )

    class _Logger:
        def info(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    monkeypatch.setattr(start_module, "get_logger", lambda *args, **kwargs: _Logger())

    def _fake_run_web(argv):
        called["web_called"] = True
        called["argv"] = argv
        return 0

    monkeypatch.setattr("beeagent_module.cli.web.run_web", _fake_run_web)
    monkeypatch.setattr(start_module, "_handle_rop_cli", lambda *args, **kwargs: None)

    monkeypatch.setattr(start_module.sys, "argv", ["start.py", "web"])

    try:
        start_module.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert called.get("web_called") is True


def test_main_unknown_command_exits_with_code_2(monkeypatch) -> None:
    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "load_settings", lambda *args, **kwargs: _base_settings()
    )
    monkeypatch.setattr(start_module, "ensure_dirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_module, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "get_app_log_path", lambda *args, **kwargs: Path("logs/app.log")
    )

    class _Logger:
        def info(self, *args, **kwargs):
            return None

        def error(self, *args, **kwargs):
            return None

    monkeypatch.setattr(start_module, "get_logger", lambda *args, **kwargs: _Logger())
    monkeypatch.setattr(start_module.sys, "argv", ["start.py", "unknown"])

    try:
        start_module.main()
        assert False, "SystemExit expected"
    except SystemExit as exc:
        assert exc.code == 2


@pytest.mark.parametrize(
    ("result", "expected_exit"),
    [
        (
            ModuleResult(
                "beedrill",
                "reference_target_containment_replay",
                AuthorityLevel.READ_ONLY,
                "ok",
                "completed",
                {"security_verdict": "pass"},
            ),
            0,
        ),
        (
            ModuleResult(
                "beedrill",
                "reference_target_containment_replay",
                AuthorityLevel.READ_ONLY,
                "ok",
                "completed",
                {"security_verdict": "fail"},
            ),
            1,
        ),
        (
            ModuleResult(
                "beedrill",
                "reference_target_containment_replay",
                AuthorityLevel.READ_ONLY,
                "timeout",
                "timed out",
            ),
            3,
        ),
        (
            ModuleResult(
                "beedrill",
                "reference_target_containment_replay",
                AuthorityLevel.READ_ONLY,
                "refused",
                "refused",
            ),
            3,
        ),
        (
            ModuleResult(
                "beedrill",
                "reference_target_containment_replay",
                AuthorityLevel.READ_ONLY,
                "error",
                "failed",
            ),
            3,
        ),
        (
            ModuleResult(
                "beedrill",
                "reference_target_containment_replay",
                AuthorityLevel.READ_ONLY,
                "incomplete",
                "incomplete",
            ),
            3,
        ),
    ],
)
def test_beedrill_cli_copies_module_verdict_to_summary(
    monkeypatch, capsys, result: ModuleResult, expected_exit: int
) -> None:
    monkeypatch.setattr(start_module, "generate_run_id", lambda: "run-1")
    monkeypatch.setattr(start_module, "generate_session_id", lambda: "session-1")
    monkeypatch.setattr(start_module, "build_registry", lambda *_: object())
    monkeypatch.setattr(start_module, "get_storage_dir", lambda: Path("storage"))
    monkeypatch.setattr(start_module, "execute_module_case", lambda **_: result)

    exit_code = start_module._handle_beedrill_cli(
        ["run", "--scenario", "reference_target_containment_replay"],
        {"modules": {"registry": []}},
        logging.getLogger("test"),
    )

    summary = json.loads(capsys.readouterr().out)
    assert exit_code == expected_exit
    assert summary["execution_status"] == result.status
    assert summary["security_verdict"] == result.data.get("security_verdict")
    assert summary["artifact_refs"] == [
        "runs/run-1/module-beedrill/module_result.json",
        "runs/run-1/module-beedrill/reference_target_containment_replay.json",
    ]


def test_beedrill_cli_refuses_unknown_scenario(capsys) -> None:
    exit_code = start_module._handle_beedrill_cli(
        ["run", "--scenario", "unknown"],
        {"modules": {"registry": []}},
        logging.getLogger("test"),
    )

    assert exit_code == 2
    assert "Usage:" in capsys.readouterr().err


@pytest.mark.parametrize("failure_stage", ["registry", "runtime"])
def test_beedrill_cli_emits_json_for_infrastructure_failure(
    monkeypatch, capsys, failure_stage: str
) -> None:
    monkeypatch.setattr(start_module, "generate_run_id", lambda: "run-1")
    if failure_stage == "registry":
        monkeypatch.setattr(
            start_module,
            "build_registry",
            lambda *_: (_ for _ in ()).throw(RuntimeError("registry unavailable")),
        )
    else:
        monkeypatch.setattr(start_module, "build_registry", lambda *_: object())
        monkeypatch.setattr(
            start_module,
            "execute_module_case",
            lambda **_: (_ for _ in ()).throw(RuntimeError("runtime unavailable")),
        )

    exit_code = start_module._handle_beedrill_cli(
        ["run", "--scenario", "reference_target_containment_replay"],
        {"modules": {"registry": []}},
        logging.getLogger("test"),
    )

    assert exit_code == 3
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": 1,
        "run_id": "run-1",
        "scenario_id": "reference_target_containment_replay",
        "execution_status": "error",
        "security_verdict": None,
        "artifact_refs": [],
    }


def test_main_auth_runs_bootstrap_before_cli_exit(monkeypatch) -> None:
    called: dict[str, Any] = {"bootstrap": 0, "auth": 0}

    monkeypatch.setattr(start_module, "sync_env_with_example", lambda *args: None)
    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)

    def _fake_bootstrap(*args, **kwargs):
        called["bootstrap"] += 1
        return {}

    def _fake_auth_cli(argv, project_root):
        called["auth"] += 1
        called["argv"] = argv
        assert called["bootstrap"] == 1
        return 0

    monkeypatch.setattr(start_module, "ensure_bootstrap_env", _fake_bootstrap)
    monkeypatch.setattr(start_module, "handle_auth_cli", _fake_auth_cli)
    monkeypatch.setattr(
        start_module.sys, "argv", ["start.py", "auth", "rotate", "admin1"]
    )

    try:
        start_module.main()
    except SystemExit as exc:
        assert exc.code == 0

    assert called["bootstrap"] == 1
    assert called["auth"] == 1
    assert called["argv"] == ["rotate", "admin1"]


def test_main_default_run_does_not_prepare_assets(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(start_module, "sync_env_with_example", lambda *args: None)
    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "ensure_bootstrap_env", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        start_module, "load_settings", lambda *args, **kwargs: _base_settings()
    )
    monkeypatch.setattr(start_module, "ensure_dirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_module, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "get_app_log_path", lambda *args, **kwargs: Path("logs/app.log")
    )

    class _Logger:
        def info(self, *args, **kwargs):
            return None

    monkeypatch.setattr(start_module, "get_logger", lambda *args, **kwargs: _Logger())
    monkeypatch.setattr(
        "beeagent_module.core.app.run_app",
        lambda *args, **kwargs: calls.append("run_app"),
    )
    monkeypatch.setattr(start_module.sys, "argv", ["start.py"])

    start_module.main()

    assert calls == ["run_app"]


def test_main_docling_assets_prepare_command_runs_once(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(start_module, "sync_env_with_example", lambda *args: None)
    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "ensure_bootstrap_env", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        start_module, "load_settings", lambda *args, **kwargs: _base_settings()
    )
    monkeypatch.setattr(start_module, "ensure_dirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(start_module, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "get_app_log_path", lambda *args, **kwargs: Path("logs/app.log")
    )

    class _Logger:
        def info(self, *args, **kwargs):
            return None

    monkeypatch.setattr(start_module, "get_logger", lambda *args, **kwargs: _Logger())
    monkeypatch.setattr(
        "beeagent_module.core.document_extraction.prepare_docling_assets",
        lambda: calls.append("prepare_assets"),
    )
    monkeypatch.setattr(
        start_module.sys, "argv", ["start.py", "docling-assets-prepare"]
    )

    start_module.main()

    assert calls == ["prepare_assets"]


def _rop_settings(monkeypatch) -> dict[str, Any]:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    from beeagent_module.core.settings import load_settings as real_load_settings

    root = Path(__file__).resolve().parents[1]
    return real_load_settings(root / "config" / "settings.yml")


def test_bootstrap_command_dispatches_runtime_bootstrap(monkeypatch) -> None:
    called: dict[str, Any] = {}

    def _fake_bootstrap():
        called["bootstrap"] = True

    monkeypatch.setattr(start_module, "bootstrap_runtime", _fake_bootstrap)
    monkeypatch.setattr(start_module.sys, "argv", ["start.py", "bootstrap"])

    start_module.main()

    assert called.get("bootstrap") is True


def test_resolve_profile_disabled_attachments_uses_base(monkeypatch) -> None:
    settings = _rop_settings(monkeypatch)
    settings["rop"]["attachments"]["enabled"] = False
    assert start_module._resolve_runtime_profile(settings) == "base"


def test_resolve_profile_docling_cpu(monkeypatch) -> None:
    settings = _rop_settings(monkeypatch)
    monkeypatch.setattr(start_module, "detect_accelerator", lambda: "cpu")
    assert start_module._resolve_runtime_profile(settings) == "docling-cpu"


def test_resolve_profile_docling_cuda(monkeypatch) -> None:
    settings = _rop_settings(monkeypatch)
    monkeypatch.setattr(start_module, "detect_accelerator", lambda: "cuda")
    assert start_module._resolve_runtime_profile(settings) == "docling-cuda"


def test_resolve_profile_unimplemented_engine_fails_fast(monkeypatch) -> None:
    settings = _rop_settings(monkeypatch)
    settings["rop"]["attachments"]["extraction"]["engine"] = "xberg"
    with pytest.raises(RuntimeError, match="not implemented"):
        start_module._resolve_runtime_profile(settings)


def test_sync_profile_rejects_arbitrary_extra(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="Invalid runtime dependency profile"):
        start_module._sync_runtime_profile("not-an-extra", Path("."))


def test_sync_profile_base_uses_frozen_sync(monkeypatch) -> None:
    calls: list[Any] = []

    class _Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        start_module.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv) or _Completed(),
    )
    start_module._sync_runtime_profile("base", Path("."))
    assert calls == [["uv", "sync", "--frozen"]]


def test_sync_profile_docling_cpu_uses_extra(monkeypatch) -> None:
    calls: list[Any] = []

    class _Completed:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(
        start_module.subprocess,
        "run",
        lambda argv, **kwargs: calls.append(argv) or _Completed(),
    )
    start_module._sync_runtime_profile("docling-cpu", Path("."))
    assert calls == [["uv", "sync", "--frozen", "--extra", "docling-cpu"]]


def test_sync_profile_failure_raises(monkeypatch) -> None:
    class _Completed:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(
        start_module.subprocess, "run", lambda argv, **kwargs: _Completed()
    )
    with pytest.raises(RuntimeError, match="Failed to sync"):
        start_module._sync_runtime_profile("base", Path("."))


def test_bootstrap_runtime_prepares_assets_for_active_docling(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(start_module, "sync_env_with_example", lambda *args: None)
    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "ensure_bootstrap_env", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        start_module,
        "load_settings",
        lambda *args, **kwargs: _rop_settings(monkeypatch),
    )
    monkeypatch.setattr(start_module, "detect_accelerator", lambda: "cpu")
    monkeypatch.setattr(
        start_module,
        "_sync_runtime_profile",
        lambda profile, root: calls.append(profile),
    )
    monkeypatch.setattr(
        "beeagent_module.core.document_extraction.prepare_docling_assets",
        lambda: calls.append("prepare_assets"),
    )

    start_module.bootstrap_runtime()

    assert calls == ["docling-cpu", "prepare_assets"]


def test_bootstrap_runtime_skips_assets_when_disabled(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(start_module, "sync_env_with_example", lambda *args: None)
    monkeypatch.setattr(start_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        start_module, "ensure_bootstrap_env", lambda *args, **kwargs: {}
    )

    def _disabled_settings(*args, **kwargs):
        settings = _rop_settings(monkeypatch)
        settings["rop"]["attachments"]["enabled"] = False
        return settings

    monkeypatch.setattr(start_module, "load_settings", _disabled_settings)
    monkeypatch.setattr(
        start_module,
        "_sync_runtime_profile",
        lambda *args, **kwargs: calls.append("sync"),
    )
    monkeypatch.setattr(
        "beeagent_module.core.document_extraction.prepare_docling_assets",
        lambda: calls.append("prepare_assets"),
    )

    start_module.bootstrap_runtime()

    assert calls == ["sync"]
