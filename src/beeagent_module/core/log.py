import logging
import sys
import time
from pathlib import Path


# Настройка лога в stdout и файл
def setup_logging(log_path: Path, level: str, clear_logs: bool, utc: bool) -> None:

    log_level = getattr(logging, level.upper(), None)
    if log_level is None:
        raise ValueError(f"Unknown logging.level: {level}")

    logger = logging.getLogger()
    logger.setLevel(log_level)

    # убираем старые handlers при повторном запуске (pytest/перезапуск в одном процессе)
    logger.handlers.clear()

    fmt = "%(asctime)s [%(levelname)s] - [%(name)s] %(message)s"
    formatter = logging.Formatter(fmt)

    if utc:
        formatter.converter = time.gmtime

    stream_h = logging.StreamHandler(sys.stdout)
    stream_h.setLevel(log_level)
    stream_h.setFormatter(formatter)

    file_mode = "w" if clear_logs else "a"
    file_h = logging.FileHandler(log_path, mode=file_mode, encoding="utf-8")
    file_h.setLevel(log_level)
    file_h.setFormatter(formatter)

    logger.addHandler(stream_h)
    logger.addHandler(file_h)

    # глушим шумные логгеры, чтобы не утекали URL/токены и не засорять лог
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)


# Возврат именованного logger
def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
