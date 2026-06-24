from __future__ import annotations

import argparse
import webbrowser
from copy import deepcopy

import uvicorn
from fastapi.routing import APIRoute

from beeagent_module.core.paths import get_project_root, get_storage_dir
from beeagent_module.core.settings import load_settings


def create_web_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="beeagent web", description="BeeAgent web console"
    )
    parser.add_argument("--host", type=str, default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    parser.add_argument(
        "--no-open",
        action="store_true",
        default=False,
        help="Do not open browser automatically",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional run ID for direct navigation",
    )
    return parser


def resolve_web_config(
    cli_args: argparse.Namespace,
    settings: dict,
) -> dict:
    web_cfg = deepcopy(settings.get("web", {}))

    if cli_args.host is not None:
        web_cfg["host"] = cli_args.host
    if cli_args.port is not None:
        web_cfg["port"] = cli_args.port
    if cli_args.no_open:
        web_cfg["open_browser"] = False

    web_cfg.setdefault("host", "127.0.0.1")
    web_cfg.setdefault("port", 8000)
    web_cfg.setdefault("open_browser", True)

    return web_cfg


def run_web(argv: list[str] | None = None) -> int:
    project_root = get_project_root()
    settings_path = project_root / "config" / "settings.yml"
    settings = load_settings(settings_path)

    parser = create_web_parser()
    args = parser.parse_args(argv)

    web_cfg = resolve_web_config(args, settings)
    host = web_cfg["host"]
    port = web_cfg["port"]
    open_browser = web_cfg["open_browser"]

    import logging as _logging

    from beeagent_module.interfaces.ui.app import build_beeui_app

    logger = _logging.getLogger("web")
    storage_dir = get_storage_dir()

    app = build_beeui_app(
        settings=settings,
        logger=logger,
        storage_dir=storage_dir,
    )

    url = f"http://{host}:{port}/"
    print(f"[web] BeeAgent web console starting: {url}")
    logger.info("BeeAgent web console starting: url=%s", url)

    if open_browser:
        logger.info("opening browser: url=%s", url)
        webbrowser.open(url)

    try:
        uvicorn.run(app, host=host, port=port, access_log=False)
    except KeyboardInterrupt:
        logger.info("BeeAgent web console stopped")
    except Exception as exc:
        logger.error("web console error: %s", exc, exc_info=True)
        return 1

    return 0


def run_routes(argv: list[str] | None = None) -> int:
    project_root = get_project_root()
    settings_path = project_root / "config" / "settings.yml"
    settings = load_settings(settings_path)

    import logging as _logging

    from beeagent_module.interfaces.ui.app import build_beeui_app

    logger = _logging.getLogger("routes")
    storage_dir = get_storage_dir()

    app = build_beeui_app(
        settings=settings,
        logger=logger,
        storage_dir=storage_dir,
    )

    print("\n=== BeeAgent Route Listing ===\n")
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = ",".join(sorted(route.methods or []))
            path = route.path
            name = route.name
        else:
            methods = "ANY"
            path = getattr(route, "path", str(route))
            name = getattr(route, "name", "")

        routes.append((methods, path, name))

    routes.sort(key=lambda r: r[1])
    for methods, path, name in routes:
        print(f"  {methods:8s} {path:45s} {name}")

    print(f"\nTotal routes: {len(routes)}")
    return 0
