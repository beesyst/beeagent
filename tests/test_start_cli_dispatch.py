from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import config.start as start_module
from config.start import _with_run_mode


# Тесты entrypoint helper: explicit CLI mode override не должен менять исходный settings.
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


# Тест: при передаче CLI аргумента вызывается run_app с правильным mode
def _base_settings() -> dict[str, Any]:
    return {
        "run": {"mode": "telegram"},
        "logging": {"level": "INFO", "clear_logs": True, "utc": True},
    }


# Тест: при передаче CLI аргумента вызывается run_app с правильным mode
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

    def _fake_run_app(*, settings, logger):
        called["mode"] = settings["run"]["mode"]

    monkeypatch.setattr(start_module, "run_app", _fake_run_app)
    monkeypatch.setattr(start_module, "_handle_rop_cli", lambda *args, **kwargs: None)

    monkeypatch.setattr(start_module.sys, "argv", ["start.py", "web"])

    start_module.main()

    assert called["mode"] == "web"


# Тест: при передаче неизвестного CLI аргумента происходит выход с кодом 2
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
