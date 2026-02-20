from __future__ import annotations

from typing import Any


# Заглушка: точка входа для Slack UI (без интеграции)
def start_slack_mode(settings: dict, logger: Any) -> None:
    _ = settings
    _ = logger
    raise NotImplementedError("Slack UI is not implemented yet")


# Заглушка: обработчик входящего события Slack
def handle_slack_event(event: dict) -> None:
    _ = event
    raise NotImplementedError("Slack events are not implemented yet")
