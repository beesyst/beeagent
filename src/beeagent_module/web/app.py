from __future__ import annotations

import logging
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from beeagent_module.core.paths import get_storage_dir
from beeagent_module.web.routes import handle_request


# Запуск веб-интерфейса для операторов, предоставляющего доступ к данным и артефактам выполнения
class _WebHandler(BaseHTTPRequestHandler):
    storage_dir: ClassVar[Path | None] = None
    logger: ClassVar[logging.Logger | None] = None

    def do_GET(self) -> None:  # noqa: N802
        assert self.storage_dir is not None
        assert self.logger is not None

        response = handle_request(
            method="GET",
            raw_path=self.path,
            storage_dir=self.storage_dir,
            logger=self.logger,
        )

        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Cache-Control", "no-store")
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response.body)

    def log_message(self, format: str, *args: object) -> None:
        assert self.logger is not None
        self.logger.info("web http: " + format, *args)


# Запуск веб-интерфейса для операторов, предоставляющего доступ к данным и артефактам выполнения
def start_web_mode(settings: dict, logger: logging.Logger) -> None:
    web_settings = settings["web"]
    host = web_settings["host"]
    port = web_settings["port"]
    open_browser = web_settings["open_browser"]

    _WebHandler.storage_dir = get_storage_dir()
    _WebHandler.logger = logger

    try:
        server = ThreadingHTTPServer((host, port), _WebHandler)
    except OSError as exc:
        raise RuntimeError(
            f"Failed to bind operator web shell on {host}:{port}: {exc}"
        ) from exc

    url = f"http://{host}:{port}/"
    logger.info("operator web shell started: url=%s", url)

    if open_browser:
        logger.info("operator web shell opening browser: url=%s", url)
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("operator web shell stopped")
    finally:
        server.server_close()
