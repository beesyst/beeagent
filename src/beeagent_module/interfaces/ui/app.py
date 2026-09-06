from __future__ import annotations

import csv
import io
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote

from beeui_module.adapters.envelopes import (
    AdapterErrorResult,
    AdapterResult,
)
from beeui_module.pages.config import load_beeui_config
from beeui_module.pages.detail import render_beeui_detail_page
from beeui_module.web.app import create_beeui_app
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from beeagent_module.cases.rop_dashboard import (
    rop_web_projection_v2_manifest,
)
from beeagent_module.core.attachment_store import (
    lookup_attachment,
    read_attachment_blob,
)
from beeagent_module.core.authorization import (
    EXTERNAL_PRINCIPAL_SCOPES,
    SCOPE_WILDCARD,
    home_path,
    is_resource_allowed,
)
from beeagent_module.core.rop_final_decision import (
    find_final_decision,
    load_or_build_final_decisions,
)
from beeagent_module.core.rop_sender_blacklist import (
    SenderBlacklistError,
    load_sender_blacklist_entries,
)
from beeagent_module.interfaces.ui.adapter import (
    BeeAgentUiAdapter,
    extract_rop_query_params,
)
from beeagent_module.interfaces.ui.bitrix_embed import (
    EMBEDDED_SESSION_AGE_MAX_SECONDS,
    is_valid_https_origin,
    is_bitrix_principal_user_id,
)
from beeagent_module.interfaces.ui.locale import (
    reset_current_locale,
    resolve_locale,
    set_current_locale,
    t,
)
from beeagent_module.interfaces.ui.read_model import (
    ALLOWED_EVIDENCE_IDS,
    normalize_rop_recommendation_hrefs,
)
from beeagent_module.interfaces.ui.rop_event_detail import (
    build_rop_event_detail_read_model,
)


def _result_data(
    result: AdapterResult | AdapterErrorResult,
    default: Any,
) -> Any:
    if isinstance(result, AdapterErrorResult):
        return default
    return result.data


def _csv_cell(value: str) -> str:
    return "'" + value if value[:1] in {"=", "+", "-", "@"} else value


def _result_warnings(
    result: AdapterResult | AdapterErrorResult,
) -> list[dict[str, Any]]:
    if isinstance(result, AdapterErrorResult):
        return []

    warnings = getattr(result, "warnings", []) or []
    serialized: list[dict[str, Any]] = []

    for warning in warnings:
        if isinstance(warning, dict):
            serialized.append(warning)
            continue

        code = getattr(warning, "code", "warning")
        message = getattr(warning, "message", str(warning))
        serialized.append({"code": code, "message": message})

    return serialized


def _ok_json(
    data: Any,
    warnings: list[Any] | None = None,
    meta: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "read_only": True,
            "data": data,
            "warnings": warnings or [],
            "meta": meta or {},
        },
        status_code=status_code,
    )


def _error_json(
    code: str,
    message: str | None = None,
    status_code: int = 400,
    error: dict[str, Any] | None = None,
) -> JSONResponse:
    payload_error = dict(error) if error is not None else {"code": code}
    if message:
        payload_error["message"] = message

    return JSONResponse(
        {
            "ok": False,
            "read_only": True,
            "error": payload_error,
            "warnings": [],
            "meta": {},
        },
        status_code=status_code,
    )


def _event_detail_error_status(code: str) -> int:
    if code in {
        "invalid_params",
        "invalid_run_id",
        "invalid_event_id",
        "invalid_query",
    }:
        return 400
    if code in {"not_found", "run_not_found", "event_not_found"}:
        return 404
    return 500


def build_beeui_settings(agent_settings: dict[str, Any]) -> dict[str, Any]:
    web_cfg = agent_settings.get("web", {})
    log_cfg = agent_settings.get("logging", {})
    web_auth = web_cfg.get("auth", {})
    auth_enabled = bool(web_auth.get("enabled", False))

    bitrix_cfg = agent_settings.get("bitrix", {})
    embedded_cfg = (
        bitrix_cfg.get("embedded_app", {}) if isinstance(bitrix_cfg, dict) else {}
    )
    embedded_enabled = bool(
        embedded_cfg.get("enabled", False) if isinstance(embedded_cfg, dict) else False
    )

    beeui_auth: dict[str, Any] = {"enabled": auth_enabled}

    if auth_enabled:
        session_env = web_auth["session_secret_env"]
        app_env = str(agent_settings.get("app", {}).get("env", "dev")).strip().lower()
        beeui_auth["session_secret"] = os.environ.get(session_env, "")
        beeui_auth["cookie_secure"] = app_env not in {"dev", "test", "local"}

        if embedded_enabled:
            beeui_auth["cookie_secure"] = True
            beeui_auth["cookie_samesite"] = "none"
            beeui_auth["session_age_max"] = EMBEDDED_SESSION_AGE_MAX_SECONDS

        principals = web_auth.get("principals", [])
        resolved_principals = []
        first_token = ""
        first_admin_token = ""
        first_operator_token = ""

        for principal in principals:
            role = str(principal.get("role", "")).strip()
            token = os.environ.get(principal["token_env"], "")
            if not first_token:
                first_token = token
            if role == "admin" and not first_admin_token:
                first_admin_token = token
            if role == "operator" and not first_operator_token:
                first_operator_token = token

            resolved_principals.append(
                {
                    "id": principal.get("id", ""),
                    "username": principal.get("username", ""),
                    "role": role,
                    "token": token,
                }
            )

        if first_token:
            beeui_auth["admin_token"] = first_admin_token or first_token
            beeui_auth["operator_token"] = first_operator_token or first_token
        beeui_auth["principals"] = resolved_principals

    return {
        "app": {
            "name": "beeui",
            "environment": agent_settings.get("app", {}).get("env", "dev"),
        },
        "web": {
            "host": web_cfg.get("host", "127.0.0.1"),
            "port": web_cfg.get("port", 8000),
            "open_browser": web_cfg.get("open_browser", False),
            "route_prefix": "",
            "cache_static": 3600,
        },
        "logging": {
            "clear_logs": log_cfg.get("clear_logs", True),
            "utc": log_cfg.get("utc", True),
            "level": log_cfg.get("level", "INFO"),
            "file": "logs/app.log",
        },
        "security": {
            "html_autoescape": True,
            "assets_ext": False,
            **(
                {"frame_ancestors": [str(embedded_cfg.get("portal_origin", ""))]}
                if embedded_enabled
                else {}
            ),
        },
        "auth": beeui_auth,
        "features": {
            "browser_artifact": True,
            "config_preview": False,
            "config_apply": False,
            "operator_actions": True,
            "api": False,
        },
        "product": {
            "id": "beeagent",
            "title": "BeeAgent",
        },
        "storage": {
            "enabled": True,
            "root": "storage",
        },
    }


def build_beeui_app(
    settings: dict[str, Any],
    logger: logging.Logger,
    storage_dir: Path | None = None,
) -> FastAPI:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.paths import get_storage_dir as _get_storage_dir

    resolved_storage = storage_dir or _get_storage_dir()
    beeui_settings = build_beeui_settings(settings)

    adapter = BeeAgentUiAdapter(
        storage_dir=resolved_storage,
        settings=settings,
    )

    config_path = get_project_root() / "config" / "beeui.yml"
    from beeui_module.web import app as beeui_web_app

    resolved_ui_config = load_beeui_config(config_path)
    resolved_templates = Jinja2Templates(
        directory=str(Path(beeui_web_app.__file__).resolve().parent / "templates")
    )
    resolved_templates.env.autoescape = bool(
        beeui_settings["security"]["html_autoescape"]
    )

    app = create_beeui_app(
        settings=beeui_settings,
        ui_config=resolved_ui_config,
        product_id="beeagent",
        product_title="BeeAgent",
        adapter=adapter,
        navigation_visibility_resolver=_beeagent_navigation_visibility,
    )
    _register_rop_html_polish(app)

    app.state.beeagent_logger = logger
    app.state.beeagent_settings = settings
    app.state.beeagent_storage_dir = resolved_storage
    app.state.beeagent_adapter = adapter
    app.state.beeagent_beeui_templates = resolved_templates
    app.state.beeagent_beeui_ui_config = resolved_ui_config
    app.state.beeagent_beeui_route_prefix = beeui_settings["web"]["route_prefix"]

    _setup_beeagent_auth(app, beeui_settings, logger)
    _register_custom_routes(app, adapter, logger)

    return app


def _setup_beeagent_auth(
    app: FastAPI,
    beeui_settings: dict[str, Any],
    logger: logging.Logger,
) -> None:
    auth_cfg = beeui_settings.get("auth", {})
    enabled = bool(auth_cfg.get("enabled", False))

    if not enabled:
        logger.info("Auth is disabled (web.auth.enabled=false)")
        return

    from beeui_module.auth.models import UserRole
    from beeui_module.auth.service import AuthService

    principal_configs: list[dict[str, Any]] = auth_cfg.get("principals", [])
    original_service: AuthService | None = getattr(
        app.state, "beeui_auth_service", None
    )

    if original_service is None:
        raise RuntimeError("BeeUI auth service is required when web.auth.enabled=true")

    if not original_service.enabled:
        raise RuntimeError(
            "BeeUI auth service must be enabled when web.auth.enabled=true"
        )

    session_secret = str(auth_cfg.get("session_secret", ""))
    if not session_secret:
        raise RuntimeError(
            "Non-empty session secret is required when web.auth.enabled=true"
        )

    if not principal_configs:
        raise RuntimeError(
            "Non-empty principals are required when web.auth.enabled=true"
        )

    principal_records: list[dict[str, Any]] = []
    for principal in principal_configs:
        token = str(principal.get("token", ""))
        username = str(principal.get("username", ""))
        role_name = str(principal.get("role", "")).strip()
        if not token:
            raise RuntimeError(
                "Non-empty principal tokens are required when web.auth.enabled=true"
            )
        if not username:
            raise RuntimeError(
                "Non-empty principal usernames are required when web.auth.enabled=true"
            )

        try:
            role = getattr(UserRole, role_name)
        except AttributeError as exc:
            raise RuntimeError(f"Unsupported BeeUI auth role '{role_name}'") from exc

        principal_records.append(
            {
                "id": str(principal.get("id", "")),
                "username": username,
                "role": role,
                "token": token,
            }
        )

    class _BeeAgentAuthService(AuthService):
        def _find_principal(
            self,
            username: str,
            token: str,
        ) -> dict[str, Any] | None:
            import hmac

            for record in principal_records:
                if record["username"] != username:
                    continue
                if hmac.compare_digest(token, record["token"]):
                    return record
            return None

        def authenticate(
            self,
            user_id: str,
            token: str,
        ) -> tuple[Any, str | None]:
            from beeui_module.auth.models import SessionData
            from beeui_module.auth.sessions import (
                create_session_cookie,
                generate_csrf_token,
            )

            if not self.enabled:
                return None, None

            record = self._find_principal(user_id, token)
            if record is None:
                logger.warning("Authentication failed for user_id=%s", user_id)
                return None, None

            csrf_token = generate_csrf_token()
            session = SessionData(
                user_id=record["id"],
                role=record["role"],
                csrf_token=csrf_token,
            )
            cookie = create_session_cookie(session, self._session_secret or "")
            logger.info(
                "Session created for user_id=%s role=%s",
                record["id"],
                record["role"].value,
            )
            return session, cookie

    primary_token = principal_records[0]["token"]
    auth_settings = {
        "enabled": True,
        "session_secret": session_secret,
        "admin_token": auth_cfg.get("admin_token") or primary_token,
        "operator_token": auth_cfg.get("operator_token") or primary_token,
        "cookie_secure": bool(auth_cfg.get("cookie_secure", False)),
        "cookie_samesite": str(auth_cfg.get("cookie_samesite", "lax")).strip().lower(),
        "session_age_max": auth_cfg.get("session_age_max"),
    }
    app.state.beeui_auth_service = _BeeAgentAuthService(auth_settings)
    logger.info("Auth enabled with %d principal(s)", len(principal_records))

    _register_auth_middleware(app, logger)


_PUBLIC_PATHS: list[re.Pattern[str]] = [
    re.compile(r"^/health"),
    re.compile(r"^/static/"),
    re.compile(r"^/auth/"),
    re.compile(r"^/api/bitrix/rop/widget(?:/|$)"),
    re.compile(r"^/bitrix/rop/install$"),
    re.compile(r"^/bitrix/rop/launch$"),
]


def _is_path_protected(path: str) -> bool:
    for pattern in _PUBLIC_PATHS:
        if pattern.match(path):
            return False
    return True


ROP_EVIDENCE_IDS = frozenset(ALLOWED_EVIDENCE_IDS)


def _principal_scopes(
    settings: dict[str, Any],
    principal_id: str,
) -> frozenset[str]:
    web_auth = settings.get("web", {}).get("auth", {})
    if not isinstance(web_auth, dict):
        return frozenset()
    principals = web_auth.get("principals", [])
    if not isinstance(principals, list):
        return frozenset()
    for principal in principals:
        if not isinstance(principal, dict):
            continue
        if principal.get("id") != principal_id:
            continue
        scopes = principal.get("scopes", [])
        if isinstance(scopes, list):
            return frozenset(str(scope) for scope in scopes)
        return frozenset()
    if is_bitrix_principal_user_id(principal_id):
        return EXTERNAL_PRINCIPAL_SCOPES
    return frozenset()


def _request_scopes(request: Request) -> frozenset[str] | None:
    settings = getattr(request.app.state, "beeagent_settings", None)
    if not isinstance(settings, dict):
        return frozenset()
    web_auth = settings.get("web", {}).get("auth", {})
    if not isinstance(web_auth, dict) or not web_auth.get("enabled"):
        return None
    service = getattr(request.app.state, "beeui_auth_service", None)
    if service is None or not getattr(service, "enabled", False):
        return frozenset()
    session = service.verify_session(request.cookies.get(service.cookie_name()))
    if session is None:
        return frozenset()
    return _principal_scopes(settings, session.user_id)


def _rop_projection_run_ids(storage_dir: Path | None) -> frozenset[str]:
    if storage_dir is None:
        return frozenset()
    manifest = rop_web_projection_v2_manifest(storage_dir)
    if manifest is None:
        return frozenset()
    return frozenset(manifest.get("run_ids", []))


def _rop_projection_entry_valid(storage_dir: Path | None, run_id: str) -> bool:
    if storage_dir is None:
        return False
    manifest = rop_web_projection_v2_manifest(storage_dir)
    return manifest is not None and run_id in manifest.get("run_ids", [])


def _artifact_path_run_id(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) >= 5 and parts[1] == "runs" and parts[3] == "artifacts":
        return parts[2]
    if (
        len(parts) >= 6
        and parts[1] == "api"
        and parts[2] == "runs"
        and parts[4] == "artifacts"
    ):
        return parts[3]
    return None


def _beeagent_navigation_visibility(
    request: Request,
    canonical_path: str,
) -> bool:
    scopes = _request_scopes(request)
    if scopes is None:
        return True
    if not scopes:
        return False
    return is_resource_allowed(
        scopes,
        canonical_path,
        rop_evidence_artifact_ids=ROP_EVIDENCE_IDS,
    )


def _unauthenticated_response(request: Request) -> Response:
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/auth/login", status_code=302)

    return JSONResponse(
        {
            "ok": False,
            "read_only": True,
            "error": {
                "code": "unauthenticated",
                "message": "Authentication required",
            },
            "warnings": [],
            "meta": {},
        },
        status_code=401,
    )


def _forbidden_response() -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "read_only": True,
            "error": {
                "code": "forbidden",
                "message": "Access denied",
            },
            "warnings": [],
            "meta": {},
        },
        status_code=403,
    )


def _register_auth_middleware(app: FastAPI, logger: logging.Logger) -> None:
    logger.info("Registering auth middleware for protected routes")

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if not _is_path_protected(str(request.url.path)):
            return await call_next(request)

        from beeui_module.auth.service import AuthService

        service: AuthService | None = getattr(
            request.app.state, "beeui_auth_service", None
        )
        if service is None or not service.enabled:
            logger.error("BeeUI auth service unavailable for protected route")
            return JSONResponse(
                {
                    "ok": False,
                    "read_only": True,
                    "error": {
                        "code": "auth_unavailable",
                        "message": "Authentication service unavailable",
                    },
                    "warnings": [],
                    "meta": {},
                },
                status_code=503,
            )

        cookie_name = service.cookie_name()
        cookie = request.cookies.get(cookie_name)
        session = service.verify_session(cookie)

        if session is None:
            return _unauthenticated_response(request)

        settings = getattr(request.app.state, "beeagent_settings", {}) or {}
        scopes = _principal_scopes(settings, session.user_id)
        path = str(request.url.path)
        if SCOPE_WILDCARD in scopes:
            allowed = is_resource_allowed(
                scopes,
                path,
                rop_evidence_artifact_ids=ROP_EVIDENCE_IDS,
            )
        else:
            storage_dir = getattr(request.app.state, "beeagent_storage_dir", None)
            requested_run_id = request.query_params.get("run_id")
            if requested_run_id is None:
                requested_run_id = _artifact_path_run_id(path)
            if requested_run_id is not None:
                try:
                    from beeui_module.adapters.ids import validate_run_id

                    validate_run_id(requested_run_id)
                except Exception:
                    requested_run_id = None
            if requested_run_id is not None:
                rop_run_ids = (
                    frozenset({requested_run_id})
                    if _rop_projection_entry_valid(storage_dir, requested_run_id)
                    else frozenset()
                )
            else:
                rop_run_ids = _rop_projection_run_ids(storage_dir)
            allowed = is_resource_allowed(
                scopes,
                path,
                rop_evidence_artifact_ids=ROP_EVIDENCE_IDS,
                rop_run_ids=rop_run_ids,
                requested_run_id=requested_run_id,
            )
        if allowed:
            return await call_next(request)

        accept = request.headers.get("accept", "")
        wants_html = "text/html" in accept
        if wants_html and path == "/":
            landing = home_path(scopes)
            if landing and landing != "/":
                from starlette.responses import RedirectResponse

                return RedirectResponse(url=landing, status_code=303)
        return _forbidden_response()


def _register_rop_html_polish(app: FastAPI) -> None:
    @app.middleware("http")
    async def rop_html_polish(request: Request, call_next):
        locale = resolve_locale(
            request.query_params.get("lang"),
            cookie_param=request.cookies.get("beeui_lang"),
        )
        path = request.url.path
        # /rop is rendered through the BeeUI product adapter, which receives
        # only query params. Persist the cookie-derived locale into the request
        # query string so the adapter localizes content on first load even when
        # the URL carries no ?lang parameter.
        if path == "/rop" and "lang" not in request.query_params:
            from urllib.parse import quote

            qs = request.scope.get("query_string", b"").decode("latin-1")
            suffix = "lang=" + quote(locale, safe="")
            request.scope["query_string"] = (
                (qs + "&" + suffix) if qs else suffix
            ).encode("latin-1")

        token = set_current_locale(locale)
        try:
            response = await call_next(request)
        finally:
            reset_current_locale(token)

        content_type = response.headers.get("content-type", "")
        # /rop is rendered by BeeUI adapter — no localization pass needed
        if path == "/rop":
            return response

        needs_polish = locale == "ru" and path in {"/", "/runs"}
        if not needs_polish or "text/html" not in content_type:
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        html = body.decode("utf-8")
        html = _localize_product_console_html(html, path, locale)
        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=html,
            status_code=response.status_code,
            headers=headers,
            media_type="text/html",
        )


def _localize_product_console_html(
    html: str,
    path: str,
    locale: str,
) -> str:
    if locale != "ru":
        return html

    replacements: dict[str, list[tuple[str, str]]] = {
        "/": [
            ("<title>Dashboard · ", f"<title>{t('BeeAgent Dashboard', locale)} · "),
            (
                '<h2 class="page-title">Dashboard</h2>',
                f'<h2 class="page-title">{t("BeeAgent Dashboard", locale)}</h2>',
            ),
            (
                '<div class="text-secondary mt-1">Adapter-backed product overview</div>',
                (
                    '<div class="text-secondary mt-1">'
                    f"{t('Read-only operator dashboard', locale)}</div>"
                ),
            ),
            (
                '<h3 class="card-title">Latest run</h3>',
                f'<h3 class="card-title">{t("Latest run", locale)}</h3>',
            ),
            (
                '<h3 class="card-title">KPIs</h3>',
                f'<h3 class="card-title">{t("KPIs", locale)}</h3>',
            ),
            (
                '<h3 class="card-title">Summary</h3>',
                f'<h3 class="card-title">{t("Summary", locale)}</h3>',
            ),
            ("Open run", t("Open run", locale)),
            ("Technical details", t("Technical details", locale)),
        ],
        "/runs": [
            ("<title>Runs · ", f"<title>{t('Runs', locale)} · "),
            (
                '<h2 class="page-title">Runs</h2>',
                f'<h2 class="page-title">{t("Runs", locale)}</h2>',
            ),
            (
                '<div class="text-secondary mt-1">Adapter-backed run list</div>',
                f'<div class="text-secondary mt-1">{t("Run history", locale)}</div>',
            ),
            (
                '<h3 class="card-title">Run list</h3>',
                f'<h3 class="card-title">{t("Run list", locale)}</h3>',
            ),
            ("<th>Run ID</th>", f"<th>{t('Run ID', locale)}</th>"),
            ("<th>Status</th>", f"<th>{t('Status', locale)}</th>"),
            ("<th>Started</th>", f"<th>{t('Started', locale)}</th>"),
            ("<th>Completed</th>", f"<th>{t('Completed', locale)}</th>"),
            (">Open</a>", f">{t('Open', locale)}</a>"),
        ],
    }

    result = html
    for old, new in replacements.get(path, []):
        result = result.replace(old, new)
    return result


_PATH_TRAVERSAL_RE = re.compile(r"(?:^|/)\.\.(?:/|$)")


def _is_path_traversal(value: str) -> bool:
    return bool(_PATH_TRAVERSAL_RE.search(value))


def _safe_download_filename(filename: str) -> str:
    if not isinstance(filename, str):
        return "attachment"
    cleaned = "".join(
        char for char in filename if ord(char) >= 32 and char not in ('"', "\\")
    )
    cleaned = cleaned.replace("/", "_").replace("\x00", "")
    cleaned = cleaned.strip().strip(".")
    if not cleaned:
        return "attachment"
    return cleaned[:_MAX_DOWNLOAD_FILENAME]


def _content_disposition_header(filename: str) -> str:
    ascii_name = filename.encode("ascii", errors="ignore").decode("ascii")
    if not ascii_name:
        ascii_name = "attachment"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


_MAX_DOWNLOAD_FILENAME = 180


def _register_custom_routes(
    app: FastAPI,
    adapter: BeeAgentUiAdapter,
    logger: logging.Logger,
) -> None:
    @app.get("/health", response_class=JSONResponse, include_in_schema=False)
    async def health() -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "app": "beeagent",
                "read_only": True,
            }
        )

    @app.get("/api/modules", include_in_schema=False)
    async def api_modules() -> JSONResponse:
        result = adapter.get_modules_dashboard()
        data = _result_data(result, {})
        return _ok_json(data)

    @app.get("/rop/blacklist.csv", include_in_schema=False)
    async def rop_blacklist_csv(request: Request) -> Response:
        try:
            query = request.query_params.get("q", "").strip().lower()
            if len(query) > 254:
                return _error_json(
                    "invalid_params", "Search query is invalid", status_code=400
                )
            entries = load_sender_blacklist_entries(app.state.beeagent_storage_dir)
        except SenderBlacklistError as exc:
            return _error_json("state_malformed", str(exc), status_code=400)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Name", "Title", "Email", "Role"])
        for entry in entries:
            if query and query not in entry["email"]:
                continue
            writer.writerow(
                [_csv_cell(entry[key]) for key in ("name", "title", "email", "role")]
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=rop-sender-blacklist.csv",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/rop/dashboard", include_in_schema=False)
    async def api_rop_dashboard(request: Request) -> JSONResponse:
        run_id = request.query_params.get("run_id")
        period = request.query_params.get("period")
        if request.query_params.get("tab") == "queue":
            period = "all"
        filter_params, pagination_params, param_errors = extract_rop_query_params(
            request.query_params
        )
        if param_errors:
            return _error_json(
                "invalid_params", "; ".join(param_errors), status_code=400
            )

        result = await run_in_threadpool(
            adapter.get_rop_dashboard,
            tab=request.query_params.get("tab", "api"),
            run_id=run_id,
            period=period,
            filter_params=filter_params,
            page=pagination_params["page"],
            page_size=pagination_params["page_size"],
            sort=pagination_params["sort"],
            order=pagination_params["order"],
        )
        if isinstance(result, AdapterErrorResult):
            code = result.error.get("code", "error")
            status = (
                404
                if code == "not_found"
                else 503
                if code == "web_projection_unavailable"
                else 400
            )
            return _error_json(code, status_code=status, error=result.error)

        data = _result_data(result, {})
        if isinstance(data, dict):
            data["rop_recommendations"] = normalize_rop_recommendation_hrefs(
                data.get("rop_recommendations", []),
                run_id=str(data.get("run_id", "")),
                period=data.get("period"),
                locale=resolve_locale(
                    request.query_params.get("lang"),
                    cookie_param=request.cookies.get("beeui_lang"),
                ),
            )
        return _ok_json(data)

    @app.get("/api/rop/events/{event_id}", include_in_schema=False)
    async def api_rop_event_detail(request: Request, event_id: str) -> JSONResponse:
        _, _, param_errors = extract_rop_query_params(request.query_params)
        if param_errors:
            return _error_json(
                "invalid_params", "; ".join(param_errors), status_code=400
            )
        run_id = request.query_params.get("run_id")
        if not run_id:
            return _error_json(
                "missing_run_id",
                "run_id query parameter is required",
                status_code=400,
            )
        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json(
                "invalid_run_id",
                "Invalid run_id",
                status_code=400,
            )

        if _is_path_traversal(event_id):
            return _error_json(
                "invalid_event_id",
                "Invalid event_id",
                status_code=400,
            )

        result = build_rop_event_detail_read_model(
            storage_dir=app.state.beeagent_storage_dir,
            run_id=run_id,
            event_id=event_id,
            event_instance_id=request.query_params.get("event_instance_id"),
            lang=resolve_locale(
                request.query_params.get("lang"),
                cookie_param=request.cookies.get("beeui_lang"),
            ),
        )
        if not result.get("ok", True) and result.get("error") == "not_found":
            return _error_json(
                "not_found",
                f"Event {event_id} not found in run {run_id}",
                status_code=404,
            )

        warnings_result = result.get("warnings", [])
        return _ok_json(result, warnings=warnings_result)

    @app.get("/rop/events/{event_id}", include_in_schema=False)
    async def rop_event_detail_html(request: Request, event_id: str) -> Response:
        run_id = request.query_params.get("run_id")
        if not run_id:
            return _error_json(
                "missing_run_id",
                "run_id query parameter is required",
                status_code=400,
            )
        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json(
                "invalid_run_id",
                "Invalid run_id",
                status_code=400,
            )

        if _is_path_traversal(event_id):
            return _error_json(
                "invalid_event_id",
                "Invalid event_id",
                status_code=400,
            )

        locale = resolve_locale(
            request.query_params.get("lang"),
            cookie_param=request.cookies.get("beeui_lang"),
        )
        token = set_current_locale(locale)
        try:
            query_params = dict(request.query_params)
            query_params["run_id"] = run_id
            query_params["event_id"] = event_id

            page_result = adapter.get_page("rop_event_detail", query_params)
            if isinstance(page_result, AdapterErrorResult):
                code = str(page_result.error.get("code", "page_error"))
                status_code = _event_detail_error_status(code)
                message = (
                    f"Event {event_id} not found in run {run_id}"
                    if status_code == 404
                    else str(
                        page_result.error.get(
                            "message", "Failed to build event detail page"
                        )
                    )
                )
                return _error_json(
                    code,
                    message,
                    status_code=status_code,
                    error=page_result.error,
                )

            return render_beeui_detail_page(
                request,
                page_result.data,
                templates=app.state.beeagent_beeui_templates,
                route_prefix=app.state.beeagent_beeui_route_prefix,
                ui_config=app.state.beeagent_beeui_ui_config,
                product_title=app.state.beeui_product["title"],
                product_id=app.state.beeui_product["id"],
            )
        finally:
            reset_current_locale(token)

    @app.get(
        "/rop/bitrix/{entity_type}/{entity_id}",
        include_in_schema=False,
    )
    async def rop_bitrix_entity_redirect(
        entity_type: str,
        entity_id: int,
    ) -> Response:
        entity_paths = {
            "lead": "lead",
            "deal": "deal",
        }
        entity_path = entity_paths.get(entity_type)
        if entity_path is None or entity_id <= 0:
            return _error_json(
                "not_found",
                "Bitrix entity not found",
                status_code=404,
            )

        settings = getattr(app.state, "beeagent_settings", {})
        bitrix_cfg = settings.get("bitrix", {}) if isinstance(settings, dict) else {}
        embedded_cfg = (
            bitrix_cfg.get("embedded_app", {})
            if isinstance(bitrix_cfg, dict)
            else {}
        )
        portal_origin = (
            embedded_cfg.get("portal_origin", "")
            if isinstance(embedded_cfg, dict)
            else ""
        )
        if not isinstance(portal_origin, str) or not is_valid_https_origin(
            portal_origin
        ):
            return _error_json(
                "unavailable",
                "Bitrix portal is unavailable",
                status_code=503,
            )
        return RedirectResponse(
            f"{portal_origin}/crm/{entity_path}/details/{entity_id}/"
        )

    @app.get("/rop/attachments/{attachment_id}/download", include_in_schema=False)
    async def rop_attachment_download(request: Request, attachment_id: str) -> Response:
        run_id = request.query_params.get("run_id")
        event_id = request.query_params.get("event_id")
        if not run_id:
            return _error_json(
                "missing_run_id",
                "run_id query parameter is required",
                status_code=400,
            )
        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json(
                "invalid_run_id",
                "Invalid run_id",
                status_code=400,
            )

        if _is_path_traversal(attachment_id):
            return _error_json(
                "invalid_attachment_id",
                "Invalid attachment_id",
                status_code=400,
            )
        if len(attachment_id) > 300:
            return _error_json(
                "invalid_attachment_id",
                "Invalid attachment_id",
                status_code=400,
            )

        storage_dir = getattr(app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_json("server_error", "Storage unavailable", status_code=503)

        item = lookup_attachment(storage_dir, run_id, attachment_id)
        if item is None:
            return _error_json(
                "not_found",
                "Attachment not found",
                status_code=404,
            )
        if event_id is not None and str(item.get("event_id") or "") != event_id:
            return _error_json(
                "not_found",
                "Attachment not found",
                status_code=404,
            )
        if item.get("storage_status") != "stored":
            return _error_json(
                "not_found",
                "Attachment not available",
                status_code=404,
            )

        blob = read_attachment_blob(storage_dir, run_id, attachment_id)
        if blob is None:
            return _error_json(
                "not_found",
                "Attachment not found",
                status_code=404,
            )
        content, meta = blob

        filename = str(meta.get("filename") or "attachment")
        safe_filename = _safe_download_filename(filename)
        disposition = _content_disposition_header(safe_filename)
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": disposition,
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    _register_bitrix_widget_routes(app, adapter, logger)
    _register_bitrix_embed_routes(app, logger)

    logger.info(
        "BeeAgent custom routes registered: "
        "/health, /api/modules, /api/rop/dashboard, "
        "/api/rop/events/{event_id}, /rop/events/{event_id}, "
        "/api/bitrix/rop/widget, /api/bitrix/rop/widget/events, "
        "/api/bitrix/rop/widget/events/{event_id}, "
        "/bitrix/rop/install, /bitrix/rop/launch"
    )


def _register_bitrix_widget_routes(
    app: FastAPI,
    adapter: BeeAgentUiAdapter,
    logger: logging.Logger,
) -> None:
    def serialize_final_decision(item: dict[str, Any]) -> dict[str, Any]:
        final_case_subtype = item.get("final_case_subtype")
        attention_reason = item.get("attention_reason")
        attention_reason_code = item.get("attention_reason_code")
        attention_evidence_codes = item.get("attention_evidence_codes")
        return {
            "event_id": str(item.get("event_id", "")),
            "final_case_type": str(item.get("final_case_type", "")),
            "final_case_subtype": (
                final_case_subtype if isinstance(final_case_subtype, str) else None
            ),
            "final_queue": str(item.get("final_queue", "")),
            "final_action": str(item.get("final_action", "")),
            "final_decision_source": str(item.get("final_decision_source", "")),
            "final_confidence": item.get("final_confidence"),
            "needs_attention": bool(item.get("needs_attention", False)),
            "attention_reason": (
                attention_reason if isinstance(attention_reason, str) else None
            ),
            "attention_reason_code": (
                attention_reason_code
                if isinstance(attention_reason_code, str)
                else None
            ),
            "attention_evidence_codes": (
                [str(c) for c in attention_evidence_codes if isinstance(c, str)]
                if isinstance(attention_evidence_codes, list)
                else None
            ),
            "automation_allowed": False,
            "bitrix_write_allowed": False,
        }

    def serialize_final_decisions_payload(
        payload: dict[str, Any],
        max_items: int,
    ) -> dict[str, Any]:
        events = payload.get("events", [])
        if not isinstance(events, list):
            events = []
        serialized_events = [
            serialize_final_decision(event)
            for event in events
            if isinstance(event, dict)
        ][:max_items]
        source_counts: dict[str, int] = {}
        attention_count = 0
        for event in serialized_events:
            source = event["final_decision_source"]
            source_counts[source] = source_counts.get(source, 0) + 1
            if event["needs_attention"]:
                attention_count += 1
        return {
            "summary": {
                "total_events": len(serialized_events),
                "decision_source_counts": source_counts,
                "attention_count": attention_count,
            },
            "events": serialized_events,
        }

    def empty_final_decisions() -> dict[str, Any]:
        return {
            "summary": {
                "total_events": 0,
                "decision_source_counts": {},
                "attention_count": 0,
            },
            "events": [],
        }

    @app.get("/api/bitrix/rop/widget", include_in_schema=False)
    async def bitrix_rop_widget(request: Request) -> JSONResponse:
        settings = getattr(app.state, "beeagent_settings", {})
        widget_cfg = settings.get("bitrix", {}).get("widget", {})
        widget_enabled = (
            widget_cfg.get("enabled", False) if isinstance(widget_cfg, dict) else False
        )

        if not widget_enabled:
            return _ok_json(
                {
                    "final_decisions": empty_final_decisions(),
                },
                meta={
                    "widget_disabled": True,
                    "message": "Bitrix widget API is disabled in config",
                },
            )

        token_env = widget_cfg.get("token_env", "BITRIX_ROP_WIDGET_TOKEN")
        expected_token = os.environ.get(token_env, "")
        if not expected_token:
            return _error_json(
                "widget_config_error",
                "Widget token env not configured",
                status_code=503,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error_json(
                "unauthorized",
                "Missing or invalid Authorization header",
                status_code=401,
            )

        import hmac

        provided_token = auth_header[7:]
        if not hmac.compare_digest(provided_token, expected_token):
            return _error_json(
                "unauthorized",
                "Invalid widget token",
                status_code=401,
            )

        storage_dir = getattr(app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_json("server_error", "Storage unavailable", status_code=503)

        run_id = request.query_params.get("run_id")
        if not run_id:
            runs_dir = storage_dir / "runs"
            if runs_dir.is_dir():
                run_dirs = sorted(
                    (d for d in runs_dir.iterdir() if d.is_dir()),
                    key=lambda d: d.stat().st_mtime,
                    reverse=True,
                )
                if run_dirs:
                    run_id = run_dirs[0].name

        if not run_id:
            return _ok_json(
                {
                    "final_decisions": empty_final_decisions(),
                },
                warnings=[{"code": "no_runs", "message": "No runs available"}],
            )

        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", "Invalid run_id", status_code=400)

        max_items = widget_cfg.get("max_items", 50)

        run_dir = storage_dir / "runs" / run_id
        if run_dir.is_dir():
            final_decisions, _ = load_or_build_final_decisions(run_dir)
            final_decisions_payload = serialize_final_decisions_payload(
                final_decisions,
                max_items,
            )
        else:
            final_decisions_payload = empty_final_decisions()

        return _ok_json(
            {"final_decisions": final_decisions_payload},
            meta={
                "run_id": run_id,
                "read_only": True,
            },
        )

    @app.get("/api/bitrix/rop/widget/events", include_in_schema=False)
    async def bitrix_rop_widget_events(request: Request) -> JSONResponse:
        return await bitrix_rop_widget(request)

    @app.get("/api/bitrix/rop/widget/events/{event_id}", include_in_schema=False)
    async def bitrix_rop_widget_event_detail(
        request: Request,
        event_id: str,
    ) -> JSONResponse:
        settings = getattr(app.state, "beeagent_settings", {})
        widget_cfg = settings.get("bitrix", {}).get("widget", {})
        widget_enabled = (
            widget_cfg.get("enabled", False) if isinstance(widget_cfg, dict) else False
        )

        if not widget_enabled:
            return _error_json(
                "widget_disabled",
                "Bitrix widget API is disabled in config",
                status_code=503,
            )

        token_env = widget_cfg.get("token_env", "BITRIX_ROP_WIDGET_TOKEN")
        expected_token = os.environ.get(token_env, "")
        if not expected_token:
            return _error_json(
                "widget_config_error",
                "Widget token env not configured",
                status_code=503,
            )

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return _error_json(
                "unauthorized",
                "Missing or invalid Authorization header",
                status_code=401,
            )

        import hmac

        provided_token = auth_header[7:]
        if not hmac.compare_digest(provided_token, expected_token):
            return _error_json(
                "unauthorized",
                "Invalid widget token",
                status_code=401,
            )

        storage_dir = getattr(app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_json("server_error", "Storage unavailable", status_code=503)

        run_id = request.query_params.get("run_id")
        if not run_id:
            runs_dir = storage_dir / "runs"
            if runs_dir.is_dir():
                run_dirs = sorted(
                    (d for d in runs_dir.iterdir() if d.is_dir()),
                    key=lambda d: d.stat().st_mtime,
                    reverse=True,
                )
                if run_dirs:
                    run_id = run_dirs[0].name

        if not run_id:
            return _error_json("missing_run_id", "run_id is required", status_code=400)

        try:
            from beeui_module.adapters.ids import validate_run_id

            validate_run_id(run_id)
        except Exception:
            return _error_json("invalid_run_id", "Invalid run_id", status_code=400)

        if _is_path_traversal(event_id):
            return _error_json("invalid_event_id", "Invalid event_id", status_code=400)

        final_decisions, _ = load_or_build_final_decisions(
            storage_dir / "runs" / run_id
        )
        final_decision = find_final_decision(final_decisions, event_id)

        if final_decision is None:
            return _error_json(
                "not_found",
                f"Event {event_id} not found in final decisions for run {run_id}",
                status_code=404,
            )

        return _ok_json(
            {"final_decision": serialize_final_decision(final_decision)},
            meta={"run_id": run_id, "read_only": True},
        )

    logger.info("Bitrix widget API routes registered")


def _register_bitrix_embed_routes(
    app: FastAPI,
    logger: logging.Logger,
) -> None:
    from beeagent_module.interfaces.ui.bitrix_embed import (
        CONTRACT_VERSION,
        MAX_FORM_BODY_BYTES,
        MAX_FORM_FIELDS,
        BitrixEmbedError,
        BitrixLaunchError,
        InstallState,
        build_portal_origin,
        create_install_state,
        load_install_state,
        parse_install_form,
        parse_launch_form,
        principal_user_id,
        validate_launch_auth_expires,
        verify_bitrix_current_user,
    )

    def _embed_config(settings: dict[str, Any]) -> dict[str, Any]:
        bitrix_cfg = settings.get("bitrix", {})
        if not isinstance(bitrix_cfg, dict):
            return {}
        emb_cfg = bitrix_cfg.get("embedded_app", {})
        if not isinstance(emb_cfg, dict):
            return {}
        return emb_cfg

    def _bounded_json(data: dict[str, Any], status_code: int = 200) -> JSONResponse:
        response = JSONResponse(data, status_code=status_code)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def _error_response(
        code: str,
        message: str,
        status_code: int = 400,
        extra: dict[str, Any] | None = None,
    ) -> JSONResponse:
        error_payload: dict[str, Any] = {"code": code, "message": message}
        if extra:
            error_payload.update(extra)
        return _bounded_json(
            {"ok": False, "error": error_payload},
            status_code=status_code,
        )

    def _received_fields(source: Any) -> list[str]:
        return sorted(str(key) for key in source.keys())

    def _is_https_request(request: Request) -> bool:
        return request.url.scheme.lower() == "https"

    async def _read_bounded_form(
        request: Request,
    ) -> dict[str, str] | None:
        media_type = (
            request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        )
        if media_type != "application/x-www-form-urlencoded":
            return None

        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_FORM_BODY_BYTES:
                return None

        try:
            pairs = parse_qsl(
                body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=MAX_FORM_FIELDS,
            )
        except UnicodeDecodeError, ValueError:
            return None

        values: dict[str, str] = {}
        for key, value in pairs:
            if key in values:
                return None
            values[key] = value
        return values

    def _verify_bitrix_user(
        values: dict[str, str],
        emb_cfg: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        try:
            validate_launch_auth_expires(values["AUTH_EXPIRES"])
        except BitrixLaunchError as exc:
            return None, _error_response("invalid_launch", str(exc), 403)

        configured_origin = str(emb_cfg.get("portal_origin", "")).strip()
        timeout = int(emb_cfg.get("request_timeout", 10))
        try:
            user = verify_bitrix_current_user(
                configured_origin,
                values["AUTH_ID"],
                timeout,
            )
        except BitrixLaunchError as exc:
            logger.info(
                "Bitrix user verification failed: reason=%s",
                exc.reason,
            )
            extra: dict[str, Any] = {"reason": exc.reason}
            if exc.bitrix_error:
                extra["bitrix_error"] = exc.bitrix_error
            return None, _error_response(
                "bitrix_verification_failed",
                "Bitrix user verification failed",
                403,
                extra=extra,
            )
        return user, None

    def _create_verified_redirect(
        request: Request,
        user: dict[str, Any],
        emb_cfg: dict[str, Any],
    ) -> Response:
        service = getattr(request.app.state, "beeui_auth_service", None)
        if service is None or not getattr(service, "enabled", False):
            return _error_response(
                "auth_unavailable",
                "Authentication service unavailable",
                503,
            )

        from beeui_module.auth.models import UserRole

        role_name = str(emb_cfg.get("default_role", "viewer"))
        role = getattr(UserRole, role_name, None)
        if role is None:
            return _error_response(
                "server_error",
                "Invalid embedded app role",
                500,
            )

        user_id = principal_user_id(user)
        _, cookie = service.create_principal_session(user_id, role)
        if cookie is None:
            return _error_response(
                "session_unavailable",
                "Failed to create session",
                503,
            )

        from starlette.responses import RedirectResponse

        redirect = RedirectResponse(url="/rop", status_code=303)
        service.attach_session_cookie(redirect, cookie)
        redirect.headers["Cache-Control"] = "no-store"
        redirect.headers["Pragma"] = "no-cache"
        redirect.headers["Referrer-Policy"] = "no-referrer"
        logger.info(
            "Bitrix embedded app launch: role=%s",
            role_name,
        )
        return redirect

    def _validate_portal_context(
        values: dict[str, str],
        emb_cfg: dict[str, Any],
        state: InstallState | None,
    ) -> JSONResponse | None:
        configured_origin = str(emb_cfg.get("portal_origin", "")).strip()
        configured_domain = configured_origin.removeprefix("https://")

        if state is not None and (
            state.portal_origin != configured_origin
            or state.portal_domain != configured_domain
        ):
            return _error_response(
                "installation_portal_mismatch",
                "Installed portal does not match the configured portal",
                409,
            )

        incoming_domain = values.get("DOMAIN", "")
        if incoming_domain:
            try:
                incoming_origin = build_portal_origin(incoming_domain)
            except BitrixEmbedError:
                return _error_response(
                    "invalid_domain",
                    "Invalid portal domain",
                    400,
                )
            if incoming_origin != configured_origin:
                return _error_response(
                    "portal_mismatch",
                    "Portal does not match the configured embedded app portal",
                    403,
                )

        return None

    @app.post("/bitrix/rop/install", include_in_schema=False)
    async def bitrix_rop_install(request: Request) -> Response:
        settings = getattr(request.app.state, "beeagent_settings", {})
        emb_cfg = _embed_config(settings)
        if not emb_cfg.get("enabled"):
            return _error_response(
                "embedded_app_disabled",
                "Embedded Bitrix app is disabled in config",
                403,
            )
        if not _is_https_request(request):
            return _error_response(
                "https_required",
                "HTTPS is required for the Bitrix embedded app endpoint",
                403,
            )

        form = await _read_bounded_form(request)
        if form is None:
            return _error_response(
                "invalid_install",
                "Malformed or oversized install request",
                400,
            )

        try:
            values = parse_install_form(form)
        except BitrixEmbedError as exc:
            return _error_response(
                "invalid_install",
                str(exc),
                400,
                extra={"received_fields": _received_fields(form)},
            )

        if not values.get("AUTH_ID") or not values.get("AUTH_EXPIRES"):
            return _error_response(
                "invalid_install",
                "AUTH_ID and AUTH_EXPIRES are required for installation",
                400,
            )

        storage_dir = getattr(request.app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_response("server_error", "Storage unavailable", 503)

        try:
            existing = load_install_state(storage_dir)
        except BitrixEmbedError as exc:
            return _error_response("install_state_corrupted", str(exc), 409)

        portal_error = _validate_portal_context(
            values,
            emb_cfg,
            existing,
        )
        if portal_error is not None:
            return portal_error

        member_id = values["member_id"]
        if existing is not None and existing.member_id != member_id:
            return _error_response(
                "conflicting_installation",
                "This deployment is already bound to another Bitrix portal",
                409,
            )

        user, verify_error = _verify_bitrix_user(values, emb_cfg)
        if verify_error is not None:
            return verify_error
        assert user is not None

        if existing is None:
            from datetime import UTC, datetime

            configured_origin = str(emb_cfg.get("portal_origin", "")).strip()
            state = InstallState(
                portal_origin=configured_origin,
                portal_domain=configured_origin.removeprefix("https://"),
                member_id=member_id,
                installed_at=datetime.now(UTC).isoformat(),
                contract_version=CONTRACT_VERSION,
            )
            if not create_install_state(storage_dir, state):
                try:
                    existing = load_install_state(storage_dir)
                except BitrixEmbedError as exc:
                    return _error_response(
                        "install_state_corrupted",
                        str(exc),
                        409,
                    )

                portal_error = _validate_portal_context(
                    values,
                    emb_cfg,
                    existing,
                )
                if portal_error is not None:
                    return portal_error

                if existing is None or existing.member_id != member_id:
                    return _error_response(
                        "conflicting_installation",
                        "This deployment is already bound to another Bitrix portal",
                        409,
                    )

        return _create_verified_redirect(request, user, emb_cfg)

    @app.post("/bitrix/rop/launch", include_in_schema=False)
    async def bitrix_rop_launch(request: Request) -> Response:
        settings = getattr(request.app.state, "beeagent_settings", {})
        emb_cfg = _embed_config(settings)
        if not emb_cfg.get("enabled"):
            return _error_response(
                "embedded_app_disabled",
                "Embedded Bitrix app is disabled in config",
                403,
            )
        if not _is_https_request(request):
            return _error_response(
                "https_required",
                "HTTPS is required for the Bitrix embedded app endpoint",
                403,
            )

        form = await _read_bounded_form(request)
        if form is None:
            return _error_response(
                "invalid_launch",
                "Malformed or oversized launch request",
                400,
            )

        try:
            values = parse_launch_form(form)
        except BitrixEmbedError as exc:
            return _error_response(
                "invalid_launch",
                str(exc),
                400,
                extra={"received_fields": _received_fields(form)},
            )

        storage_dir = getattr(request.app.state, "beeagent_storage_dir", None)
        if storage_dir is None:
            return _error_response("server_error", "Storage unavailable", 503)

        try:
            state = load_install_state(storage_dir)
        except BitrixEmbedError as exc:
            return _error_response("install_state_corrupted", str(exc), 409)
        if state is None:
            return _error_response(
                "not_installed",
                "Bitrix embedded app is not installed",
                403,
            )

        portal_error = _validate_portal_context(
            values,
            emb_cfg,
            state,
        )
        if portal_error is not None:
            return portal_error

        if state.member_id != values["member_id"]:
            return _error_response(
                "member_mismatch",
                "Launch member does not match the installed portal",
                403,
            )

        user, verify_error = _verify_bitrix_user(values, emb_cfg)
        if verify_error is not None:
            return verify_error
        assert user is not None

        return _create_verified_redirect(request, user, emb_cfg)

    logger.info(
        "Bitrix embedded app routes registered: /bitrix/rop/install, /bitrix/rop/launch"
    )
