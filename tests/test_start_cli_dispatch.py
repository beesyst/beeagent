from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

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


def test_main_prepares_assets_before_default_run(monkeypatch) -> None:
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
        "beeagent_module.core.app.run_app",
        lambda *args, **kwargs: calls.append("run_app"),
    )
    monkeypatch.setattr(start_module.sys, "argv", ["start.py"])

    start_module.main()

    assert calls == ["prepare_assets", "run_app"]


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
