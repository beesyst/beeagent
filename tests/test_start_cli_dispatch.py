from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
