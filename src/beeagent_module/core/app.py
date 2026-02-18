import logging

from beeagent_module.ui.telegram_bot import start_telegram_mode


# Запуск приложения в выбранном режиме
def run_app(settings: dict, logger: logging.Logger) -> None:
    mode = settings["run"]["mode"]
    logger.info("BeeAgent started")
    logger.info("mode=%s", mode)

    if mode == "telegram":
        start_telegram_mode(settings=settings, logger=logger)
        return

    raise RuntimeError(f"Unsupported run mode: {mode}")
