from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from beeui_module.adapters.envelopes import AdapterResult
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.beeui_console_support import (
    _build_scoped_auth_settings,
    _build_settings,
    _client,
    _logger,
    _make_storage,
    _scoped_auth_client,
    _seed_download_attachment,
    _write_rich_rop_run,
    _write_rop_web_projection,
    _write_run_artifacts,
)


def _write_non_rop_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        json.dumps({"run_id": run_id, "status": "ok", "summary": "non-rop run"}),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps({"not": "a list"}), encoding="utf-8"
    )
    return run_dir


def _build_auth_settings(enabled: bool = False) -> dict:
    settings = _build_settings()
    settings["web"]["auth"] = {
        "enabled": enabled,
        "mode": "beeui_session",
        "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
        "principals": [
            {
                "id": "admin",
                "username": "admin",
                "role": "admin",
                "scopes": ["*"],
                "token_env": "BEEAGENT_WEB_ADMIN_TOKEN",
            },
            {
                "id": "rop",
                "username": "rop",
                "role": "viewer",
                "scopes": ["rop"],
                "token_env": "BEEAGENT_WEB_ROP_TOKEN",
            },
            {
                "id": "operator",
                "username": "operator",
                "role": "operator",
                "scopes": ["dashboard", "rop", "runs", "modules"],
                "token_env": "BEEAGENT_WEB_OPERATOR_TOKEN",
            },
        ],
    }
    return settings


def _set_auth_env() -> tuple[dict[str, str], dict[str, str | None]]:
    env = {
        "BEEAGENT_WEB_SESSION_SECRET": "test-session-secret-not-for-prod",
        "BEEAGENT_WEB_ADMIN_TOKEN": "admin-test-token",
        "BEEAGENT_WEB_ROP_TOKEN": "rop-test-token",
        "BEEAGENT_WEB_OPERATOR_TOKEN": "operator-test-token",
    }
    previous = {key: os.environ.get(key) for key in env}
    for k, v in env.items():
        os.environ[k] = v
    return env, previous


def _clear_auth_env(
    env: dict[str, str],
    previous: dict[str, str | None],
) -> None:
    for key in env:
        old_value = previous.get(key)
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


def _auth_client(storage_dir: Path) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    settings = _build_auth_settings(enabled=True)
    _write_rop_web_projection(storage_dir, settings)
    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)


def _set_scoped_auth_env() -> tuple[dict[str, str], dict[str, str | None]]:
    env = {
        "BEEAGENT_WEB_SESSION_SECRET": "scoped-session-secret",
        "BEEAGENT_WEB_ADMIN1_TOKEN": "admin1-test-token",
        "BEEAGENT_WEB_ADMIN2_TOKEN": "admin2-test-token",
        "BEEAGENT_WEB_ROPVIEWER_TOKEN": "ropviewer-test-token",
        "BEEAGENT_WEB_ROP_TOKEN": "rop-test-token",
    }
    previous = {key: os.environ.get(key) for key in env}
    for k, v in env.items():
        os.environ[k] = v
    return env, previous


def _clear_scoped_auth_env(
    env: dict[str, str],
    previous: dict[str, str | None],
) -> None:
    for key in env:
        old_value = previous.get(key)
        if old_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_value


def _build_valid_enabled_auth_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    settings = _build_full_settings()
    settings["web"]["auth"] = {
        "enabled": True,
        "mode": "beeui_session",
        "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
        "principals": [
            {
                "id": "admin",
                "username": "admin",
                "role": "admin",
                "scopes": ["*"],
                "token_env": "BEEAGENT_WEB_ADMIN_TOKEN",
            },
            {
                "id": "rop",
                "username": "rop",
                "role": "viewer",
                "scopes": ["rop"],
                "token_env": "BEEAGENT_WEB_ROP_TOKEN",
            },
            {
                "id": "operator",
                "username": "operator",
                "role": "operator",
                "scopes": ["dashboard", "rop", "runs", "modules"],
                "token_env": "BEEAGENT_WEB_OPERATOR_TOKEN",
            },
        ],
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    return settings


def _build_full_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "test"},
        "run": {"mode": "telegram"},
        "web": {
            "host": "127.0.0.1",
            "port": 8000,
            "open_browser": False,
            "auth": {
                "enabled": False,
                "mode": "beeui_session",
                "session_secret_env": "BEEAGENT_WEB_SESSION_SECRET",
                "principals": [],
            },
        },
        "telegram": {
            "enabled": False,
            "bot_token_env": "T",
            "chat_id_env": "T",
            "telemetry_enabled": False,
        },
        "logging": {"clear_logs": True, "utc": True, "level": "INFO"},
        "mock": {"seed": 1, "weeks": 1, "stores": 1, "skus": 1, "category": "X"},
        "data": {"adapter": "mock"},
        "scheduler": {"enabled": False, "interval": 100, "start_run": True},
        "approval": {"reject_reason": "R"},
        "promo": {"stock_min": 1, "units_max": 1},
        "i18n": {"lang": "ru", "path": "i18n.yml"},
        "quiz": {"enabled": False, "path": "q.json"},
        "modules": {"registry": []},
        "rop": {
            "email_preview": {
                "body_chars_max": 4000,
            },
            "ai_assist": {
                "enabled": False,
                "events_max": 20,
                "request_timeout": 30,
                "ai_confidence_min": 0.70,
                "dry_run": False,
                "adjudicator": {
                    "enabled": False,
                    "timeout": 20,
                    "input_chars_max": 8000,
                    "confidence_accept_min": 0.70,
                    "events_max": 20,
                    "attachment_chars_max": 2000,
                    "prompt_key": "rop.ai_adjudicator",
                },
            },
            "routing": {
                "queues": {
                    "sales": {"bitrix_category": "sales"},
                    "tender": {"bitrix_category": "tenders"},
                    "logistics": {"bitrix_category": "logistics"},
                    "finance": {"bitrix_category": "finance"},
                    "procurement": {"bitrix_category": "procurement"},
                    "manual_review": {"bitrix_category": "manual_review"},
                },
            },
            "attachments": {
                "enabled": False,
                "chars_max": 100,
                "size_max": 100,
                "types": ["text/plain"],
                "storage": {
                    "enabled": True,
                    "file_max": 1048576,
                    "message_max": 2097152,
                    "files_message_max": 10,
                },
                "extraction": {
                    "engine": "docling",
                    "chars_max": 2000,
                    "pages_max": 20,
                    "timeout_seconds": 30,
                    "ocr_enabled": True,
                },
            },
            "sources_path": "config/rop/sources.yml",
            "dashboard": {
                "default_period": "7d",
                "periods": ["today", "yesterday", "7d", "30d", "90d", "365d", "all"],
                "leaderboard": {"plan_lead": 20},
            },
        },
        "bitrix": {
            "enabled": False,
            "webhook_env": "BITRIX_WEBHOOK_URL",
            "timeout": 10,
            "page_size": 50,
            "pages_max": 3,
            "types_entity": [1, 2, 3, 4],
            "reconciliation": {
                "enabled": False,
                "candidate_limit": 20,
                "window_date": 180,
                "correlation": {
                    "enabled": True,
                    "window_days": 180,
                },
            },
            "widget": {
                "enabled": False,
                "token_env": "BITRIX_ROP_WIDGET_TOKEN",
                "default_period": "7d",
                "max_items": 50,
            },
            "embedded_app": {
                "enabled": False,
                "portal_origin": "",
                "default_role": "viewer",
                "request_timeout": 10,
            },
        },
        "ai": {
            "prompts": {"path": "p.yml", "store": False},
            "profiles": {
                "openai": {
                    "enabled": True,
                    "provider": "openai_responses",
                    "api_key_env": "K",
                    "base_url": "https://x",
                    "model": "gpt",
                },
                "deepseek": {
                    "enabled": False,
                    "provider": "openai_compatible",
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                },
                "lmstudio": {
                    "enabled": False,
                    "provider": "openai_compatible",
                    "api_key_env": "LMSTUDIO_API_KEY",
                    "base_url": "http://127.0.0.1:1234/v1",
                    "model": "local-model",
                },
                "custom": {
                    "enabled": False,
                    "provider": "openai_compatible",
                    "api_key_env": "CUSTOM_AI_API_KEY",
                    "base_url": "https://example.test/v1",
                    "model": "custom-model",
                },
            },
        },
    }


@pytest.mark.parametrize(
    ("env_name", "expected_secure"),
    [
        ("dev", False),
        ("test", False),
        ("local", False),
        ("prod", True),
    ],
)
def test_auth_cookie_secure_tracks_app_env(
    monkeypatch: pytest.MonkeyPatch,
    env_name: str,
    expected_secure: bool,
) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = _build_auth_settings(enabled=True)
    settings["app"]["env"] = env_name

    beeui_settings = build_beeui_settings(settings)

    assert beeui_settings["auth"]["cookie_secure"] is expected_secure


def test_auth_service_preserves_secure_cookie_in_prod(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = _build_auth_settings(enabled=True)
    settings["app"]["env"] = "prod"

    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=_make_storage(tmp_path),
    )
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        data={"user_id": "admin", "token": "admin-token"},
        follow_redirects=False,
    )

    assert response.status_code in (200, 302)
    assert "secure" in response.headers.get("set-cookie", "").lower()


def test_auth_disabled_current_behavior(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-auth-off")
    client = _client(storage_dir)
    for path in ["/", "/health", "/rop", "/runs", "/modules"]:
        response = client.get(path)
        assert response.status_code == 200, f"GET {path} should be 200"
    for path in ["/api/dashboard", "/api/modules", "/api/rop/dashboard"]:
        response = client.get(path)
        assert response.status_code == 200, f"GET {path} should be 200"


def test_auth_disabled_no_env_vars_required(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    settings = _build_settings()
    storage_dir = _make_storage(tmp_path)
    app = build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )
    assert app is not None


def test_auth_enabled_fails_fast_without_beeui_auth_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from fastapi import FastAPI

    from beeagent_module.interfaces.ui import app as ui_app

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")

    settings = _build_auth_settings(enabled=True)

    def fake_create_beeui_app(**_: Any) -> FastAPI:
        return FastAPI()

    monkeypatch.setattr(ui_app, "create_beeui_app", fake_create_beeui_app)

    with pytest.raises(RuntimeError, match="BeeUI auth service is required"):
        ui_app.build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=_make_storage(tmp_path),
        )


def test_auth_disabled_non_loopback_host_rejected() -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_full_settings()
    settings["web"]["host"] = "0.0.0.0"
    settings["web"]["auth"]["enabled"] = False

    with pytest.raises(RuntimeError, match="web.auth.enabled=false"):
        validate_settings(settings)


class TestAuthEnabled:
    _env: dict[str, str] = {}
    _previous_env: dict[str, str | None] = {}

    @classmethod
    def setup_class(cls) -> None:
        cls._env, cls._previous_env = _set_auth_env()

    @classmethod
    def teardown_class(cls) -> None:
        _clear_auth_env(cls._env, cls._previous_env)

    def _login(self, client: TestClient, user_id: str, token: str) -> Any:
        return client.post("/auth/login", data={"user_id": user_id, "token": token})

    def test_unauthenticated_rop_protected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        response = client.get("/rop", follow_redirects=False)
        assert response.status_code in (302, 401)

    def test_unauthenticated_api_returns_401(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 401

    def test_health_remains_public(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_source_removal_returns_safe_http_result_and_persists_runtime_state(
        self, tmp_path: Path
    ) -> None:
        from beeagent_module.core.paths import get_project_root
        from beeagent_module.core.rop_sources import load_rop_sources
        from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-source-action")
        client = _auth_client(storage_dir)
        settings = _build_auth_settings(enabled=True)
        seed_path = get_project_root() / "config" / "rop" / "sources.yml"
        seed_before = seed_path.read_bytes()

        assert self._login(client, "admin", "admin-test-token").status_code == 200
        csrf_token = client.get("/auth/csrf").json()["data"]["csrf_token"]
        response = client.post(
            "/api/actions/execute",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "action_id": "rop_source_remove",
                "payload": {"source_id": "hotline_mailbox"},
            },
        )

        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert "adapter_error" not in response.text
        assert "Adapter error" not in response.text
        assert seed_path.read_bytes() == seed_before
        assert all(
            source["source_id"] != "hotline_mailbox"
            for source in load_rop_sources(get_project_root(), settings, storage_dir)
        )
        assert client.get("/rop?tab=sources").status_code == 200
        page = BeeAgentUiAdapter(storage_dir, settings).get_page(
            "rop", {"tab": "sources"}
        )
        assert isinstance(page, AdapterResult)
        assert page.data["layout"][0]["id"] == "rop-sources"
        assert all(
            row["status"]["args"]["source_id"] != "hotline_mailbox"
            for row in page.data["layout"][0]["rows"]
        )

    def test_source_registry_write_failure_has_safe_http_envelope(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from beeagent_module.core import rop_sources

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-source-write-failure")
        client = _auth_client(storage_dir)

        def fail_registry_write(_path: Path, _sources: list[dict[str, Any]]) -> None:
            raise OSError("denied")

        monkeypatch.setattr(rop_sources, "_write", fail_registry_write)
        assert self._login(client, "admin", "admin-test-token").status_code == 200
        csrf_token = client.get("/auth/csrf").json()["data"]["csrf_token"]
        response = client.post(
            "/api/actions/execute",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "action_id": "rop_source_remove",
                "payload": {"source_id": "hotline_mailbox"},
            },
        )

        assert response.status_code == 502
        assert response.json()["error"] == {
            "code": "source_registry_write_failed",
            "message": "Failed to update ROP source registry",
        }
        assert "adapter_error" not in response.text
        assert "Adapter error" not in response.text

    def test_static_remains_public(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        response = client.get("/static/")
        assert response.status_code in (200, 404)

    def test_admin_can_access_rop(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        login_resp = self._login(client, "admin", "admin-test-token")
        assert login_resp.status_code in (302, 200)
        response = client.get("/rop", follow_redirects=False)
        assert response.status_code == 200

    def test_rop_queue_uses_cookie_locale_on_first_load(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = _write_run_artifacts(storage_dir, "run-auth-cookie")
        (run_dir / "classified_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-1",
                        "source_id": "hotline_mailbox",
                        "case_type": "existing_deal",
                        "priority": "high",
                        "sender": "client@example.com",
                        "subject": "Follow-up on quote",
                    }
                ]
            ),
            encoding="utf-8",
        )
        client = _auth_client(storage_dir)
        self._login(client, "admin", "admin-test-token")
        client.cookies.set("beeui_lang", "ru")
        response = client.get("/rop?tab=queue")

        assert response.status_code == 200
        assert "Сделка" in response.text
        assert "Existing deal" not in response.text
        client.close()

    def test_rop_queue_lang_query_overrides_cookie(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        run_dir = _write_run_artifacts(storage_dir, "run-auth-cookie-en")
        (run_dir / "classified_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-1",
                        "source_id": "hotline_mailbox",
                        "case_type": "existing_deal",
                        "priority": "high",
                        "sender": "client@example.com",
                        "subject": "Follow-up on quote",
                    }
                ]
            ),
            encoding="utf-8",
        )
        client = _auth_client(storage_dir)
        self._login(client, "admin", "admin-test-token")
        client.cookies.set("beeui_lang", "ru")
        response = client.get("/rop?tab=queue&lang=en")

        assert response.status_code == 200
        assert "Deal" in response.text
        assert "Существующая сделка" not in response.text
        client.close()

    def test_admin_can_access_api(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        client = _auth_client(storage_dir)
        self._login(client, "admin", "admin-test-token")
        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200

    def test_operator_principal_keeps_operator_role(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
        monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-test-token")
        monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-test-token")
        monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-test-token")

        settings = _build_auth_settings(enabled=True)

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-operator-role")
        _write_rop_web_projection(storage_dir, settings)

        app = build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=storage_dir,
        )
        service = app.state.beeui_auth_service

        assert service._resolve_role("admin-test-token") == UserRole.admin
        assert service._resolve_role("operator-test-token") == UserRole.operator

        client = TestClient(app)
        login_resp = client.post(
            "/auth/login",
            data={"user_id": "operator", "token": "operator-test-token"},
        )
        assert login_resp.status_code in (302, 200)

        response = client.get("/api/rop/dashboard")
        assert response.status_code == 200

    def test_invalid_token_rejected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)
        login_resp = self._login(client, "admin", "wrong-token")
        assert login_resp.status_code == 401

    def test_protected_route_fails_closed_if_auth_service_removed(
        self,
        tmp_path: Path,
    ) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth-service-missing")

        app = build_beeui_app(
            settings=_build_auth_settings(enabled=True),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        app.state.beeui_auth_service = None

        client = TestClient(app)
        response = client.get("/api/rop/dashboard")

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "auth_unavailable"

    def test_unknown_api_path_requires_auth_before_404(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _auth_client(storage_dir)

        response = client.get("/api/not-existing")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"


class TestPrincipalScopedAuthorization:
    _env: dict[str, str] = {}
    _previous_env: dict[str, str | None] = {}

    @classmethod
    def setup_class(cls) -> None:
        cls._env, cls._previous_env = _set_scoped_auth_env()

    @classmethod
    def teardown_class(cls) -> None:
        _clear_scoped_auth_env(cls._env, cls._previous_env)

    def _client(self, tmp_path: Path) -> TestClient:
        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        return _scoped_auth_client(storage_dir)

    def _login(
        self,
        client: TestClient,
        user_id: str,
        token: str,
        follow_redirects: bool = True,
    ) -> Any:
        return client.post(
            "/auth/login",
            data={"user_id": user_id, "token": token},
            follow_redirects=follow_redirects,
        )

    def test_exact_username_token_success(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin1", "admin1-test-token")
        assert resp.status_code in (302, 200)
        assert client.get("/", follow_redirects=False).status_code == 200

    def test_rop_viewer_exact_username_token_success(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(
            client,
            "ropviewer",
            "ropviewer-test-token",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert client.get("/rop", follow_redirects=False).status_code == 200

    def test_wrong_username_valid_token_rejected(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "nobody", "admin1-test-token")
        assert resp.status_code == 401

    def test_another_principal_username_valid_token_rejected(
        self,
        tmp_path: Path,
    ) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin2", "admin1-test-token")
        assert resp.status_code == 401

    def test_correct_username_wrong_token_rejected(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin1", "wrong-token")
        assert resp.status_code == 401

    def test_failure_response_does_not_expose_credentials(
        self,
        tmp_path: Path,
    ) -> None:
        client = self._client(tmp_path)
        resp = self._login(client, "admin1", "wrong-token")
        assert "wrong-token" not in resp.text
        assert "admin1-test-token" not in resp.text

    def test_canonical_configured_session_identity(self, tmp_path: Path) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)
        self._login(client, "admin1", "admin1-test-token")

        service = app.state.beeui_auth_service
        cookie = client.cookies.get(service.cookie_name())
        session = service.verify_session(cookie)
        assert session is not None
        assert session.user_id == "admin_1"

    def test_admin_wildcard_full_html_access(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "admin1", "admin1-test-token")
        for path in ["/", "/rop", "/runs", "/runs/run-auth", "/modules"]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code in (200, 404), f"GET {path} should be allowed"

    def test_admin_wildcard_full_api_access(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "admin1", "admin1-test-token")
        for path in [
            "/api/dashboard",
            "/api/runs",
            "/api/modules",
            "/api/rop/dashboard",
        ]:
            response = client.get(path)
            assert response.status_code == 200, f"GET {path} should be allowed"

    def test_rop_viewer_allowed_html_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert client.get("/rop", follow_redirects=False).status_code == 200
        evt = client.get("/rop/events/evt-1?run_id=run-auth")
        assert evt.status_code != 403
        evidence = client.get(
            "/runs/run-auth/artifacts/operator_summary_json",
            follow_redirects=False,
        )
        assert evidence.status_code != 403

    def test_rop_viewer_allowed_api_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert client.get("/api/rop/dashboard").status_code == 200
        evt = client.get("/api/rop/events/evt-1?run_id=run-auth")
        assert evt.status_code != 403
        evidence = client.get("/api/runs/run-auth/artifacts/operator_summary_json")
        assert evidence.status_code != 403

    def test_rop_viewer_forbidden_html_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        for path in [
            "/runs",
            "/runs/run-auth",
            "/runs/run-auth/artifacts",
            "/modules",
            "/components",
        ]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 403, f"GET {path} should be denied"

    def test_rop_viewer_forbidden_api_matrix(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        for path in [
            "/api/dashboard",
            "/api/runs",
            "/api/runs/run-auth",
            "/api/runs/run-auth/artifacts",
            "/api/modules",
        ]:
            response = client.get(path)
            assert response.status_code == 403, f"GET {path} should be denied"

    def test_rop_viewer_denied_unrelated_artifact(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert (
            client.get(
                "/runs/run-auth/artifacts/run_json",
                follow_redirects=False,
            ).status_code
            == 403
        )
        assert client.get("/api/runs/run-auth/artifacts/run_json").status_code == 403

    def test_unknown_protected_surface_default_deny(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        assert client.get("/components", follow_redirects=False).status_code == 403
        assert client.get("/api/unknown-surface").status_code == 403

    def test_unauthenticated_differs_from_forbidden(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        unauthed = client.get("/api/runs")
        assert unauthed.status_code == 401
        assert unauthed.json()["error"]["code"] == "unauthenticated"

        self._login(client, "ropviewer", "ropviewer-test-token")
        forbidden = client.get("/api/runs")
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "forbidden"

    def test_rop_viewer_landing_redirects_to_rop(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        login_resp = self._login(
            client,
            "ropviewer",
            "ropviewer-test-token",
            follow_redirects=False,
        )
        assert login_resp.status_code == 302
        assert login_resp.headers["location"] == "/"

        landing = client.get(
            "/", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert landing.status_code == 303
        assert landing.headers["location"] == "/rop"

    def test_rop_viewer_direct_dashboard_url_denied(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        api = client.get("/api/dashboard")
        assert api.status_code == 403
        assert api.json()["error"]["code"] == "forbidden"

    def test_fresh_canonical_rop_session_has_scoped_operator_authority(
        self, tmp_path: Path
    ) -> None:
        from beeui_module.auth.models import UserRole

        client = self._client(tmp_path)
        login = self._login(client, "rop", "rop-test-token", follow_redirects=False)
        assert login.status_code == 302

        app = client.app
        assert isinstance(app, FastAPI)

        service = app.state.beeui_auth_service
        session = service.verify_session(client.cookies.get(service.cookie_name()))
        assert session is not None
        assert session.user_id == "rop"
        assert session.role == UserRole.operator
        assert client.get("/rop", follow_redirects=False).status_code == 200
        assert client.get("/rop?tab=sources", follow_redirects=False).status_code == 200
        assert (
            client.get("/rop?tab=blacklist", follow_redirects=False).status_code == 200
        )
        assert client.get("/rop/sources.csv", follow_redirects=False).status_code == 200
        csrf = client.get("/auth/csrf")
        assert csrf.status_code == 200
        csrf_token = csrf.json()["data"]["csrf_token"]
        add = client.post(
            "/api/actions/execute",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "action_id": "rop_sender_blacklist_add",
                "payload": {"email": "rop-authority-test@example.com"},
            },
        )
        assert add.status_code == 200
        assert add.json()["ok"] is True
        remove = client.post(
            "/api/actions/execute",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "action_id": "rop_sender_blacklist_remove",
                "payload": {"email": "rop-authority-test@example.com"},
            },
        )
        assert remove.status_code == 200
        assert remove.json()["ok"] is True
        assert client.get("/api/dashboard").status_code == 403
        assert client.get("/api/runs").status_code == 403
        assert client.get("/modules").status_code == 403
        assert client.get("/api/unknown-surface").status_code == 403

        viewer_client = self._client(tmp_path / "viewer")
        self._login(viewer_client, "ropviewer", "ropviewer-test-token")
        viewer_csrf = viewer_client.get("/auth/csrf")
        assert viewer_csrf.status_code == 200
        viewer_action = viewer_client.post(
            "/api/actions/execute",
            headers={"X-CSRF-Token": viewer_csrf.json()["data"]["csrf_token"]},
            json={
                "action_id": "rop_sender_blacklist_add",
                "payload": {"email": "rop-authority-test@example.com"},
            },
        )
        assert viewer_action.status_code == 403
        assert viewer_action.json()["error"]["code"] == "forbidden"

    def test_unmapped_future_scope_gets_403(self, tmp_path: Path) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        settings = _build_scoped_auth_settings()
        settings["web"]["auth"]["principals"][2]["scopes"] = ["beescan"]
        app = build_beeui_app(
            settings=settings,
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)
        self._login(client, "ropviewer", "ropviewer-test-token")

        assert client.get("/rop", follow_redirects=False).status_code == 403
        assert client.get("/api/rop/dashboard").status_code == 403
        assert client.get("/api/runs").status_code == 403

    def test_rop_viewer_navigation_hides_unrelated_items(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        html = client.get("/rop", headers={"accept": "text/html"}).text
        assert 'href="/rop"' in html
        assert 'href="/runs"' not in html
        assert 'href="/modules"' not in html
        assert 'nav-link-title">Dashboard</span>' not in html
        assert 'nav-link-title">Operator</span>' not in html

    def test_admin_navigation_shows_all_items(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "admin1", "admin1-test-token")
        html = client.get("/", headers={"accept": "text/html"}).text
        assert 'data-beeui-icon="dashboard"' in html
        assert 'data-beeui-icon="activity"' in html
        assert 'data-beeui-icon="apps"' in html
        assert 'href="/runs"' in html
        assert 'href="/modules"' in html
        assert 'href="/rop"' in html
        assert 'nav-link-title">Dashboard</span>' in html
        assert 'nav-link-title">ROP</span>' in html
        assert 'nav-link-title">Runs</span>' in html
        assert 'nav-link-title">Modules</span>' in html
        assert 'nav-link-title">Operator</span>' not in html

    def test_rop_viewer_navigation_hides_ru_locale(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        html = client.get("/rop?lang=ru", headers={"accept": "text/html"}).text
        assert 'href="/rop' in html
        assert 'href="/runs' not in html
        assert 'href="/modules' not in html
        assert 'nav-link-title">Оператор</span>' not in html

    def test_bitrix_external_session_bounded_rop(self, tmp_path: Path) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        _write_rop_web_projection(storage_dir, _build_scoped_auth_settings())
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)

        service = app.state.beeui_auth_service
        _, cookie = service.create_principal_session("bitrix:42", UserRole.viewer)
        client.cookies.set(service.cookie_name(), cookie)

        assert client.get("/rop", follow_redirects=False).status_code == 200
        assert client.get("/api/rop/dashboard").status_code == 200
        assert (
            client.get(
                "/", headers={"accept": "text/html"}, follow_redirects=False
            ).status_code
            == 303
        )
        assert client.get("/api/runs").status_code == 403
        assert client.get("/api/modules").status_code == 403
        assert (
            client.get(
                "/runs/run-auth/artifacts/run_json",
                follow_redirects=False,
            ).status_code
            == 403
        )

    def test_unknown_signed_principal_denied(self, tmp_path: Path) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)

        service = app.state.beeui_auth_service
        _, cookie = service.create_principal_session("unknown-user", UserRole.viewer)
        client.cookies.set(service.cookie_name(), cookie)

        assert client.get("/rop", follow_redirects=False).status_code == 403
        assert client.get("/api/rop/dashboard").status_code == 403
        assert client.get("/api/runs").status_code == 403

    def test_legacy_numeric_signed_principal_denied(self, tmp_path: Path) -> None:
        from beeui_module.auth.models import UserRole

        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)

        service = app.state.beeui_auth_service
        _, cookie = service.create_principal_session("42", UserRole.viewer)
        client.cookies.set(service.cookie_name(), cookie)

        assert client.get("/rop", follow_redirects=False).status_code == 403
        assert client.get("/api/rop/dashboard").status_code == 403

    def test_rop_viewer_non_rop_run_denied(self, tmp_path: Path) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_app

        storage_dir = _make_storage(tmp_path)
        _write_run_artifacts(storage_dir, "run-auth")
        _write_non_rop_run(storage_dir, "run-non-rop")
        _write_rop_web_projection(storage_dir, _build_scoped_auth_settings())
        app = build_beeui_app(
            settings=_build_scoped_auth_settings(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app)
        self._login(client, "ropviewer", "ropviewer-test-token")

        for path in [
            "/rop?run_id=run-non-rop",
            "/rop/events/evt-1?run_id=run-non-rop",
        ]:
            response = client.get(
                path, headers={"accept": "text/html"}, follow_redirects=False
            )
            assert response.status_code == 403, f"GET {path} should be denied"

        for path in [
            "/api/rop/dashboard?run_id=run-non-rop",
            "/api/rop/events/evt-1?run_id=run-non-rop",
        ]:
            response = client.get(path)
            assert response.status_code == 403, f"GET {path} should be denied"

        assert (
            client.get(
                "/runs/run-non-rop/artifacts/operator_summary_json",
                follow_redirects=False,
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/runs/run-non-rop/artifacts/classified_events_json",
                follow_redirects=False,
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/runs/run-non-rop/artifacts/operator_summary_json"
            ).status_code
            == 403
        )

        assert client.get("/rop?run_id=run-auth").status_code == 200
        assert (
            client.get(
                "/runs/run-auth/artifacts/operator_summary_json",
                follow_redirects=False,
            ).status_code
            != 403
        )

    def test_logout_invalidates_session(self, tmp_path: Path) -> None:
        client = self._client(tmp_path)
        self._login(client, "ropviewer", "ropviewer-test-token")
        client.post("/auth/logout")
        assert client.get("/rop", follow_redirects=False).status_code in (302, 401)


def test_auth_settings_fail_fast_missing_session_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.delenv("BEEAGENT_WEB_SESSION_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="BEEAGENT_WEB_SESSION_SECRET"):
        validate_settings(settings)


def test_auth_settings_fail_fast_missing_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.delenv("BEEAGENT_WEB_ADMIN_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BEEAGENT_WEB_ADMIN_TOKEN"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_principal_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["id"] = "admin"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals id"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["username"] = "admin"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals username"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_token_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["token_env"] = "BEEAGENT_WEB_ADMIN_TOKEN"

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals token_env"):
        validate_settings(settings)


def test_auth_settings_fail_fast_invalid_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["role"] = "superadmin"

    with pytest.raises(RuntimeError, match="Invalid web.auth.principals\\[1\\].role"):
        validate_settings(settings)


def test_auth_settings_fail_fast_missing_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1].pop("scopes")

    with pytest.raises(RuntimeError, match="scopes"):
        validate_settings(settings)


def test_auth_settings_fail_fast_empty_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = []

    with pytest.raises(RuntimeError, match="scopes"):
        validate_settings(settings)


def test_auth_settings_accepts_future_safe_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings, validate_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(get_project_root() / "config" / "settings.yml")
    settings["web"]["auth"]["principals"][1]["scopes"] = ["beescan"]
    validate_settings(settings)


@pytest.mark.parametrize(
    "bad_scope",
    [
        "Beescan",
        "ROP",
        "rop/",
        "/rop",
        "ro p",
        "rop ",
        " rop",
        "röp",
        "..",
        "-rop",
        "9rop",
        "ro-p/",
    ],
)
def test_auth_settings_fail_fast_malformed_scope(
    monkeypatch: pytest.MonkeyPatch,
    bad_scope: str,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = [bad_scope]

    with pytest.raises(RuntimeError, match="safe lowercase scope identifier"):
        validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = ["rop", "rop"]

    with pytest.raises(RuntimeError, match="Duplicate web.auth.principals"):
        validate_settings(settings)


def test_auth_settings_fail_fast_wildcard_with_other_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    settings["web"]["auth"]["principals"][1]["scopes"] = ["*", "rop"]

    with pytest.raises(RuntimeError, match="wildcard"):
        validate_settings(settings)


def test_auth_settings_accepts_wildcard_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings, validate_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(get_project_root() / "config" / "settings.yml")
    validate_settings(settings)


def test_auth_settings_accepts_multiple_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings, validate_settings

    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = load_settings(get_project_root() / "config" / "settings.yml")
    settings["web"]["auth"]["principals"][1]["scopes"] = ["rop", "runs"]
    validate_settings(settings)


def test_auth_settings_fail_fast_duplicate_resolved_token_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "admin-token")

    with pytest.raises(RuntimeError, match="Duplicate resolved token value"):
        validate_settings(settings)


def test_auth_settings_duplicate_resolved_token_error_does_not_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.core.settings import validate_settings

    settings = _build_valid_enabled_auth_settings(monkeypatch)
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "admin-token")

    with pytest.raises(RuntimeError, match="Duplicate resolved token value") as exc:
        validate_settings(settings)

    assert "admin-token" not in str(exc.value)


def test_widget_api_allows_bearer_without_beeui_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-widget-auth")

    settings = _build_auth_settings(enabled=True)
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 50,
        }
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")

    client = _client(storage_dir, settings=settings)
    response = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-widget-auth"},
        headers={"Authorization": "Bearer widget-token"},
    )

    assert response.status_code == 200
    assert isinstance(response.json()["data"]["final_decisions"], dict)


def test_widget_api_rejects_missing_or_invalid_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-widget-401")

    settings = _build_auth_settings(enabled=True)
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 50,
        }
    }
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")

    client = _client(storage_dir, settings=settings)
    missing = client.get("/api/bitrix/rop/widget", params={"run_id": "run-widget-401"})
    invalid = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-widget-401"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401


def test_widget_api_returns_final_decisions_block(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rich_rop_run(storage_dir, "run-widget-fd")
    final_decisions = {
        "summary": {
            "total_events": 2,
            "decision_source_counts": {"deterministic": 2},
            "attention_count": 0,
        },
        "events": [
            {
                "event_id": "evt-001",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "sales",
                "final_action": "review_new_lead",
                "final_decision_source": "deterministic",
                "final_confidence": 0.85,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            },
            {
                "event_id": "evt-002",
                "final_case_type": "existing_deal",
                "final_case_subtype": "follow_up",
                "final_queue": "logistics",
                "final_action": "attach_to_deal",
                "final_decision_source": "deterministic",
                "final_confidence": 0.7,
                "needs_attention": False,
                "attention_reason": None,
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            },
        ],
    }
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(final_decisions), encoding="utf-8"
    )
    settings = _build_settings()
    settings["bitrix"] = {
        "widget": {
            "enabled": True,
            "token_env": "BITRIX_ROP_WIDGET_TOKEN",
            "default_period": "7d",
            "max_items": 1,
        }
    }
    monkeypatch.setenv("BITRIX_ROP_WIDGET_TOKEN", "widget-token")
    client = _client(storage_dir, settings=settings)
    response = client.get(
        "/api/bitrix/rop/widget",
        params={"run_id": "run-widget-fd"},
        headers={"Authorization": "Bearer widget-token"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "final_decisions" in data
    fd = data["final_decisions"]
    assert fd["summary"]["total_events"] == 1
    assert fd["summary"]["decision_source_counts"] == {"deterministic": 1}
    assert fd["summary"]["attention_count"] == 0
    assert len(fd["events"]) == 1
    assert fd["events"][0]["event_id"] == "evt-001"
    assert fd["events"][0]["final_case_subtype"] is None
    assert fd["events"][0]["attention_reason"] is None
    assert fd["events"][0]["automation_allowed"] is False
    assert fd["events"][0]["bitrix_write_allowed"] is False


class TestAttachmentDownloadAuth:
    _env: dict[str, str] = {}
    _previous_env: dict[str, str | None] = {}

    @classmethod
    def setup_class(cls) -> None:
        cls._env, cls._previous_env = _set_auth_env()

    @classmethod
    def teardown_class(cls) -> None:
        _clear_auth_env(cls._env, cls._previous_env)

    def test_unauthenticated_download_rejected(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        response = client.get(
            "/rop/attachments/evt-1-att-0/download?run_id=run-dl",
            follow_redirects=False,
        )
        assert response.status_code in (302, 401)

    def test_authenticated_rop_principal_can_download(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        login = client.post(
            "/auth/login",
            data={"user_id": "rop", "token": "rop-test-token"},
            follow_redirects=False,
        )
        assert login.status_code in (200, 302)
        response = client.get("/rop/attachments/evt-1-att-0/download?run_id=run-dl")
        assert response.status_code == 200
        assert response.content == b"%PDF-1.4 download body bytes"
        assert response.headers.get("x-content-type-options") == "nosniff"

    def test_authenticated_admin_can_download(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        client.post(
            "/auth/login",
            data={"user_id": "admin", "token": "admin-test-token"},
            follow_redirects=False,
        )
        response = client.get("/rop/attachments/evt-1-att-0/download?run_id=run-dl")
        assert response.status_code == 200

    def test_authenticated_rop_unknown_attachment_404(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        _seed_download_attachment(storage_dir, "run-dl")
        client = _auth_client(storage_dir)
        client.post(
            "/auth/login",
            data={"user_id": "rop", "token": "rop-test-token"},
            follow_redirects=False,
        )
        response = client.get("/rop/attachments/not-there/download?run_id=run-dl")
        assert response.status_code == 404
