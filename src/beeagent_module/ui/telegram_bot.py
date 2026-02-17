import logging


# Русский комментарий
def start_telegram_mode(settings: dict, logger: logging.Logger) -> None:
    telegram_enabled = settings["telegram"]["enabled"]
    logger.info("telegram mode started")
    logger.info("telegram.enabled=%s", telegram_enabled)
