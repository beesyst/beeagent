from __future__ import annotations

import logging
import webbrowser
from pathlib import Path
from urllib.parse import unquote

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from beeagent_module.core.paths import get_storage_dir
from beeagent_module.web.routes import (
    get_modules_payload,
    get_rop_dashboard_payload,
    get_run_artifact_response,
    get_run_overview_payload,
    get_runs_payload,
    get_tsv_response,
    render_error_page,
    render_home_page,
    render_modules_page,
    render_rop_dashboard_page,
    render_run_overview_page,
    render_runs_page,
)


# Создание FastAPI приложения с маршрутами для отображения данных выполнения и артефактов, а также с защитой от path traversal атак
def create_web_app(
    settings: dict,
    logger: logging.Logger,
    storage_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(
        title="BeeAgent Web Console",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.logger = logger
    app.state.settings = settings
    app.state.storage_dir = storage_dir or get_storage_dir()

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def _block_path_traversal(request: Request, call_next):
        raw_path = request.scope.get("raw_path", b"")
        decoded_path = unquote(raw_path.decode("utf-8", errors="ignore"))
        if ".." in decoded_path:
            logger.warning("web path traversal blocked: path=%s", decoded_path)
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_path"},
                    headers={"Cache-Control": "no-store"},
                )

            return HTMLResponse(
                content=render_error_page(
                    title="Bad request",
                    heading="Invalid path",
                    message="Path traversal is not allowed.",
                ),
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )
        return await call_next(request)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> HTMLResponse | JSONResponse:
        logger.info(
            "web request failed: path=%s status=%s", request.url.path, exc.status_code
        )
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": str(exc.detail)},
                headers={"Cache-Control": "no-store"},
            )

        return HTMLResponse(
            content=render_error_page(
                title="Route error",
                heading="Route error",
                message=str(exc.detail),
            ),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/", response_class=HTMLResponse)
    async def home() -> HTMLResponse:
        return HTMLResponse(
            content=render_home_page(app.state.storage_dir),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs", response_class=HTMLResponse)
    async def runs() -> HTMLResponse:
        return HTMLResponse(
            content=render_runs_page(app.state.storage_dir),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_overview(run_id: str) -> HTMLResponse:
        status, html = render_run_overview_page(run_id, app.state.storage_dir)
        return HTMLResponse(
            content=html,
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}/rop", response_class=HTMLResponse)
    async def rop_dashboard(request: Request, run_id: str) -> HTMLResponse:
        status, html = render_rop_dashboard_page(
            run_id=run_id,
            storage_dir=app.state.storage_dir,
            query={
                key: request.query_params.getlist(key) for key in request.query_params
            },
        )
        return HTMLResponse(
            content=html,
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/modules", response_class=HTMLResponse)
    async def modules() -> HTMLResponse:
        return HTMLResponse(
            content=render_modules_page(app.state.storage_dir),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}/tsv", response_class=PlainTextResponse)
    async def run_tsv(run_id: str) -> PlainTextResponse:
        status, content, content_type = get_tsv_response(run_id, app.state.storage_dir)
        return PlainTextResponse(
            content=content,
            status_code=status,
            media_type=content_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}/artifact/{artifact_name}")
    async def run_artifact(run_id: str, artifact_name: str) -> PlainTextResponse:
        status, content, content_type = get_run_artifact_response(
            run_id=run_id,
            artifact_name=artifact_name,
            storage_dir=app.state.storage_dir,
            module_artifact=False,
        )
        return PlainTextResponse(
            content=content,
            status_code=status,
            media_type=content_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/runs/{run_id}/module-artifact/{artifact_name}")
    async def module_artifact(run_id: str, artifact_name: str) -> PlainTextResponse:
        status, content, content_type = get_run_artifact_response(
            run_id=run_id,
            artifact_name=artifact_name,
            storage_dir=app.state.storage_dir,
            module_artifact=True,
        )
        return PlainTextResponse(
            content=content,
            status_code=status,
            media_type=content_type,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/runs", response_class=JSONResponse)
    async def api_runs() -> JSONResponse:
        return JSONResponse(
            content=get_runs_payload(app.state.storage_dir),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/runs/{run_id}", response_class=JSONResponse)
    async def api_run_overview(run_id: str) -> JSONResponse:
        status, payload = get_run_overview_payload(run_id, app.state.storage_dir)
        return JSONResponse(
            content=payload,
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/rop/runs/{run_id}/dashboard", response_class=JSONResponse)
    async def api_rop_dashboard(request: Request, run_id: str) -> JSONResponse:
        status, payload = get_rop_dashboard_payload(
            run_id=run_id,
            storage_dir=app.state.storage_dir,
            query={
                key: request.query_params.getlist(key) for key in request.query_params
            },
        )
        return JSONResponse(
            content=payload,
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/modules", response_class=JSONResponse)
    async def api_modules() -> JSONResponse:
        return JSONResponse(
            content=get_modules_payload(app.state.storage_dir),
            headers={"Cache-Control": "no-store"},
        )

    return app


# Запуск веб-интерфейса для операторов, предоставляющего доступ к данным и артефактам выполнения
def start_web_mode(settings: dict, logger: logging.Logger) -> None:
    web_settings = settings["web"]
    host = web_settings["host"]
    port = web_settings["port"]
    open_browser = web_settings["open_browser"]
    app = create_web_app(settings=settings, logger=logger)

    url = f"http://{host}:{port}/"
    logger.info("operator web console started: url=%s", url)

    if open_browser:
        logger.info("operator web console opening browser: url=%s", url)
        webbrowser.open(url)

    try:
        uvicorn.run(app, host=host, port=port, access_log=False)
    except KeyboardInterrupt:
        logger.info("operator web console stopped")
