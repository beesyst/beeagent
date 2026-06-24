import logging

from beeagent_module.core.module_registry import build_registry
from beeagent_module.ui.telegram_bot import start_telegram_mode
from beeagent_module.web.app import start_web_mode


def run_app(settings: dict, logger: logging.Logger) -> None:
    mode = settings["run"]["mode"]
    logger.info("BeeAgent started")
    logger.info("mode=%s", mode)

    build_registry(settings=settings, logger=logger)

    if mode == "telegram":
        start_telegram_mode(settings=settings, logger=logger)
        return

    if mode == "web":
        start_web_mode(settings=settings, logger=logger)
        return

    raise RuntimeError(f"Unsupported run mode: {mode}")
