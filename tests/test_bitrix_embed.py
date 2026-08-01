from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from beeagent_module.interfaces.ui import bitrix_embed

PORTAL_ORIGIN = "https://company.bitrix24.ru"
PORTAL_DOMAIN = "company.bitrix24.ru"
MEMBER_ID = "member-001"


def _logger() -> logging.Logger:
    logger = logging.getLogger("test_bitrix_embed")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _make_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "storage"
    (storage_dir / "runs").mkdir(parents=True)
    (storage_dir / "interfaces").mkdir(parents=True)
    return storage_dir


def _write_minimal_run(storage_dir: Path) -> None:
    run_dir = storage_dir / "runs" / "run-embed"
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        json.dumps(
            {"run_id": "run-embed", "status": "ok", "summary": "batch completed"}
        ),
        encoding="utf-8",
    )


def _set_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-token")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")


def _full_settings(monkeypatch: pytest.MonkeyPatch) -> dict:
    from beeagent_module.core.paths import get_project_root
    from beeagent_module.core.settings import load_settings

    _set_auth_env(monkeypatch)
    settings = load_settings(get_project_root() / "config" / "settings.yml")
    settings["bitrix"]["embedded_app"]["enabled"] = True
    settings["bitrix"]["embedded_app"]["portal_origin"] = PORTAL_ORIGIN
    settings["bitrix"]["embedded_app"]["default_role"] = "viewer"
    settings["bitrix"]["embedded_app"]["request_timeout"] = 5
    return settings


def _build_app(storage_dir: Path, monkeypatch: pytest.MonkeyPatch):
    from beeagent_module.interfaces.ui.app import build_beeui_app

    return build_beeui_app(
        settings=_full_settings(monkeypatch),
        logger=_logger(),
        storage_dir=storage_dir,
    )


def _https_client(storage_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return TestClient(_build_app(storage_dir, monkeypatch), base_url="https://testserver")


def _http_client(storage_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return TestClient(_build_app(storage_dir, monkeypatch), base_url="http://testserver")


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _mock_user_response(monkeypatch: pytest.MonkeyPatch, payload: Any) -> list[str]:
    from beeagent_module.interfaces.ui import bitrix_embed

    requested_urls: list[str] = []

    def _fake_urlopen(req: Any, timeout: int = 0) -> _FakeResponse:
        requested_urls.append(req.full_url)
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return _FakeResponse(body)

    monkeypatch.setattr(bitrix_embed, "urlopen", _fake_urlopen)
    return requested_urls


def _mock_user_error(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    from beeagent_module.interfaces.ui import bitrix_embed

    def _fake_urlopen(req: Any, timeout: int = 0) -> _FakeResponse:
        raise exc

    monkeypatch.setattr(bitrix_embed, "urlopen", _fake_urlopen)


def _install_form(**overrides: Any) -> dict[str, str]:
    values = {
        "member_id": MEMBER_ID,
        "PLACEMENT": "DEFAULT",
        "status": "L",
    }
    values.update(overrides)
    return values


def _install_full_form(**overrides: Any) -> dict[str, str]:
    values = {
        "AUTH_ID": "secret-auth-id-123",
        "AUTH_EXPIRES": str(int(time.time()) + 3600),
        "REFRESH_ID": "secret-refresh-456",
        "member_id": MEMBER_ID,
        "PLACEMENT": "DEFAULT",
        "status": "L",
    }
    values.update(overrides)
    return values


def _launch_form(**overrides: Any) -> dict[str, str]:
    values = {
        "AUTH_ID": "secret-auth-id-123",
        "AUTH_EXPIRES": str(int(time.time()) + 3600),
        "member_id": MEMBER_ID,
        "REFRESH_ID": "secret-refresh-456",
        "PLACEMENT": "DEFAULT",
        "status": "L",
    }
    values.update(overrides)
    return values


def _active_user_payload(user_id: str = "42", active: Any = True) -> dict[str, Any]:
    return {"result": {"ID": user_id, "ACTIVE": active, "NAME": "Test User"}}


class TestSettingsValidation:
    def _validate(self, monkeypatch: pytest.MonkeyPatch, mutate) -> None:
        from beeagent_module.core.settings import validate_settings

        _set_auth_env(monkeypatch)
        settings = _full_settings(monkeypatch)
        mutate(settings)
        validate_settings(settings)

    def test_disabled_embedded_app_with_empty_origin_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        self._validate(
            monkeypatch,
            lambda s: (
                s["bitrix"]["embedded_app"].update(
                    {"enabled": False, "portal_origin": ""}
                )
            ),
        )

    def test_enabled_requires_exact_https_origin(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(RuntimeError, match="portal_origin"):
            self._validate(
                monkeypatch,
                lambda s: s["bitrix"]["embedded_app"].update(
                    {"portal_origin": "http://company.bitrix24.ru"}
                ),
            )

    def test_enabled_rejects_trailing_slash_origin(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(RuntimeError, match="portal_origin"):
            self._validate(
                monkeypatch,
                lambda s: s["bitrix"]["embedded_app"].update(
                    {"portal_origin": "https://company.bitrix24.ru/"}
                ),
            )

    def test_enabled_requires_viewer_role(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(RuntimeError, match="viewer"):
            self._validate(
                monkeypatch,
                lambda s: s["bitrix"]["embedded_app"].update(
                    {"default_role": "operator"}
                ),
            )

    def test_invalid_default_role_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(RuntimeError, match="default_role"):
            self._validate(
                monkeypatch,
                lambda s: s["bitrix"]["embedded_app"].update(
                    {"default_role": "superuser"}
                ),
            )

    @pytest.mark.parametrize("timeout", [0, -1, 61])
    def test_request_timeout_bounds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        timeout: int,
    ) -> None:
        with pytest.raises(RuntimeError, match="request_timeout"):
            self._validate(
                monkeypatch,
                lambda s, t=timeout: s["bitrix"]["embedded_app"].update(
                    {"request_timeout": t}
                ),
            )

    def test_enabled_requires_web_auth(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        with pytest.raises(RuntimeError, match="web.auth.enabled"):
            self._validate(
                monkeypatch,
                lambda s: s["web"]["auth"].update({"enabled": False}),
            )


class TestInstall:
    def test_first_install_bind_returns_json_without_secrets(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(),
        )

        assert response.status_code == 200
        assert response.json() == {
            "ok": True,
            "data": {"status": "installed", "member_bound": True},
        }
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"

        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert artifact_path.exists()
        state = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert state["contract_version"] == bitrix_embed.CONTRACT_VERSION
        assert state["portal_origin"] == PORTAL_ORIGIN
        assert state["portal_domain"] == PORTAL_DOMAIN
        assert state["member_id"] == MEMBER_ID
        assert "installed_at" in state
        assert "AUTH_ID" not in json.dumps(state)
        assert "REFRESH_ID" not in json.dumps(state)
        assert "PLACEMENT" not in json.dumps(state)

    def test_install_full_context_redirects_and_binds(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        requested = _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/rop"
        set_cookie = response.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie
        assert "secure" in set_cookie
        assert "samesite=none" in set_cookie
        assert requested == [f"{PORTAL_ORIGIN}/rest/user.current"]
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert artifact_path.exists()
        state = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert state["member_id"] == MEMBER_ID
        assert "AUTH_ID" not in json.dumps(state)

    def test_identical_reinstall_is_safe(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        first = client.post("/bitrix/rop/install", data=_install_form())
        second = client.post("/bitrix/rop/install", data=_install_form())

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["data"]["status"] == "already_installed"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        state = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert state["member_id"] == MEMBER_ID

    def test_conflicting_member_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        client.post("/bitrix/rop/install", data=_install_form())
        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(member_id="member-other"),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflicting_installation"

    def test_conflicting_domain_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        client.post("/bitrix/rop/install", data=_install_form())
        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(DOMAIN="other.bitrix24.ru"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "portal_mismatch"

    def test_domain_mismatch_with_config_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(DOMAIN="other.bitrix24.ru"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "portal_mismatch"

    def test_missing_fields_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(member_id=""),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"

    def test_extra_bitrix_fields_tolerated(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data={**_install_form(), "EVIL": "x", "APP_SID": "sid"},
        )

        assert response.status_code == 200
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        artifact_text = artifact_path.read_text(encoding="utf-8")
        assert "EVIL" not in artifact_text
        assert "APP_SID" not in artifact_text
        assert "PLACEMENT" not in artifact_text

    def test_install_accepts_numeric_protocol(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(PROTOCOL="1"),
        )

        assert response.status_code == 200

    def test_install_error_reports_received_fields_without_values(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data={
                "PLACEMENT": "DEFAULT",
                "PLACEMENT_OPTIONS": "{}",
                "AUTH_ID": "super-secret-value",
            },
        )

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "invalid_install"
        assert "member_id" in error["message"]
        assert error["received_fields"] == ["AUTH_ID", "PLACEMENT", "PLACEMENT_OPTIONS"]
        assert "super-secret-value" not in response.text

    def test_non_https_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _http_client(storage_dir, monkeypatch)

        response = client.post("/bitrix/rop/install", data=_install_form())

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "https_required"

    def test_forwarded_proto_https_accepted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _http_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(),
            headers={"X-Forwarded-Proto": "https"},
        )

        assert response.status_code == 200

    def test_disabled_embedded_app_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)

        def _disable():
            settings = _full_settings(monkeypatch)
            settings["bitrix"]["embedded_app"]["enabled"] = False
            return settings

        from beeagent_module.interfaces.ui.app import build_beeui_app

        app = build_beeui_app(
            settings=_disable(),
            logger=_logger(),
            storage_dir=storage_dir,
        )
        client = TestClient(app, base_url="https://testserver")

        response = client.post("/bitrix/rop/install", data=_install_form())

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "embedded_app_disabled"

    def test_oversized_body_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_form(
                DOMAIN="company.bitrix24.ru",
                member_id="m" + "x" * (bitrix_embed.MAX_FORM_VALUE_LENGTH + 1),
            ),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"


class TestLaunch:
    def test_valid_launch_redirects_with_secure_iframe_cookie(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        requested = _mock_user_response(
            monkeypatch,
            _active_user_payload(user_id="42"),
        )
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(),
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/rop"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        set_cookie = response.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie
        assert "secure" in set_cookie
        assert "samesite=none" in set_cookie
        assert requested == [f"{PORTAL_ORIGIN}/rest/user.current"]

    def test_valid_launch_session_grants_rop_access(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        launch = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(),
            follow_redirects=False,
        )
        assert launch.status_code == 303

        rop = client.get("/rop", follow_redirects=False)
        assert rop.status_code == 200

    def test_unauthenticated_rop_stays_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        rop = client.get("/rop", follow_redirects=False)
        assert rop.status_code in (302, 401)

    def test_missing_fields_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(AUTH_ID=""),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_launch"

    def test_extra_bitrix_fields_tolerated(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data={**_launch_form(), "EVIL": "x"},
            follow_redirects=False,
        )

        assert response.status_code == 303

    def test_launch_error_reports_received_fields_without_values(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data={"AUTH_ID": "super-secret-value", "PLACEMENT": "DEFAULT"},
        )

        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == "invalid_launch"
        assert "AUTH_EXPIRES" in error["message"]
        assert "member_id" in error["message"]
        assert error["received_fields"] == ["AUTH_ID", "PLACEMENT"]
        assert "super-secret-value" not in response.text

    def test_launch_via_get_query_params(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        requested = _mock_user_response(monkeypatch, _active_user_payload(user_id="7"))
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.get(
            "/bitrix/rop/launch",
            params=_launch_form(),
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/rop"
        assert requested == [f"{PORTAL_ORIGIN}/rest/user.current"]

    def test_launch_get_without_params_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.get("/bitrix/rop/launch", follow_redirects=False)

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_launch"
        assert requested == []

    def test_launch_accepts_ttl_expiry(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload(user_id="9"))
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(AUTH_EXPIRES="3600"),
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert requested == [f"{PORTAL_ORIGIN}/rest/user.current"]

    def test_member_mismatch_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(member_id="member-other"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "member_mismatch"
        assert requested == []

    def test_not_installed_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_installed"
        assert requested == []

    def test_expired_token_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(AUTH_EXPIRES=str(int(time.time()) - 10)),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invalid_launch"
        assert requested == []

    def test_malformed_expiry_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(AUTH_EXPIRES="not-a-timestamp"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invalid_launch"

    def test_invalid_token_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, {"error": "expired_token"})
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "bitrix_error"
        assert error["bitrix_error"] == "expired_token"

    def test_inactive_user_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(
            monkeypatch,
            _active_user_payload(user_id="42", active=False),
        )
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "inactive_user"

    def test_timeout_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        from urllib.error import URLError

        _mock_user_error(monkeypatch, URLError("timed out"))
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "timeout"

    def test_http_401_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        import io
        from email.message import Message
        from urllib.error import HTTPError

        body = io.BytesIO(
            b'{"error":"invalid_token","error_description":"Unable to get application by token"}'
        )
        _mock_user_error(
            monkeypatch,
            HTTPError(
                f"{PORTAL_ORIGIN}/rest/user.current",
                401,
                "Unauthorized",
                Message(),
                body,
            ),
        )
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "token_rejected"
        assert error["bitrix_error"] == "invalid_token"
        assert "Unable to get application" not in response.text

    def test_malformed_rest_response_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, b"not-json{{")
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "malformed_response"

    def test_non_https_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        client = _http_client(storage_dir, monkeypatch)
        client.post(
            "/bitrix/rop/install",
            data=_install_form(),
            headers={"X-Forwarded-Proto": "https"},
        )

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "https_required"
        assert requested == []

    def test_tokens_absent_from_response_and_logs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)
        client.post("/bitrix/rop/install", data=_install_form())

        with caplog.at_level(logging.INFO):
            response = client.post(
                "/bitrix/rop/launch",
                data=_launch_form(),
                follow_redirects=False,
            )

        assert response.status_code == 303
        assert "secret-auth-id-123" not in response.text
        assert "secret-refresh-456" not in response.text
        assert "secret-auth-id-123" not in caplog.text
        assert "secret-refresh-456" not in caplog.text

    def test_corrupted_install_state_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        _mock_user_response(monkeypatch, _active_user_payload())
        client = _https_client(storage_dir, monkeypatch)
        (storage_dir / "interfaces" / "bitrix_rop_app.json").write_text(
            "{corrupted", encoding="utf-8"
        )

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "install_state_corrupted"


class TestEmbeddedSettingsComposition:
    def test_build_beeui_settings_embedded_policy(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_settings

        _set_auth_env(monkeypatch)
        settings = _full_settings(monkeypatch)

        beeui = build_beeui_settings(settings)

        assert beeui["security"]["frame_ancestors"] == [PORTAL_ORIGIN]
        assert beeui["auth"]["cookie_secure"] is True
        assert beeui["auth"]["cookie_samesite"] == "none"
        assert beeui["auth"]["session_age_max"] == bitrix_embed.EMBEDDED_SESSION_AGE_MAX_SECONDS

    def test_build_beeui_settings_without_embedded_unaffected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from beeagent_module.interfaces.ui.app import build_beeui_settings

        _set_auth_env(monkeypatch)
        settings = _full_settings(monkeypatch)
        settings["bitrix"]["embedded_app"]["enabled"] = False
        settings["bitrix"]["embedded_app"]["portal_origin"] = ""

        beeui = build_beeui_settings(settings)

        assert "frame_ancestors" not in beeui["security"]
        assert beeui["auth"].get("cookie_samesite") is None
        assert beeui["auth"].get("session_age_max") is None

    def test_local_login_works_with_embedded_policy(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        client = _https_client(storage_dir, monkeypatch)

        login = client.post(
            "/auth/login",
            data={"user_id": "admin1", "token": "admin1-token"},
            follow_redirects=False,
        )

        assert login.status_code == 302
        set_cookie = login.headers.get("set-cookie", "").lower()
        assert "httponly" in set_cookie
        assert "secure" in set_cookie
        assert "samesite=none" in set_cookie

        rop = client.get("/rop", follow_redirects=False)
        assert rop.status_code == 200


class TestEmbeddedModule:
    def test_parse_install_form_tolerates_unknown(self) -> None:
        values = bitrix_embed.parse_install_form(
            {"DOMAIN": "x", "member_id": "m", "EVIL": "1", "PLACEMENT": "DEFAULT"}
        )
        assert values["DOMAIN"] == "x"
        assert values["member_id"] == "m"

    def test_parse_install_form_requires_member_id(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.parse_install_form(
                {"AUTH_ID": "a", "PLACEMENT": "DEFAULT"}
            )

    def test_parse_install_form_rejects_oversized_known_field(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.parse_install_form(
                {"DOMAIN": "x", "member_id": "m" * (bitrix_embed.MAX_FORM_VALUE_LENGTH + 1)}
            )

    def test_parse_launch_form_requires_fields(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.parse_launch_form(
                {"AUTH_ID": "a", "AUTH_EXPIRES": "1", "DOMAIN": "x"}
            )

    def test_parse_launch_form_tolerates_unknown(self) -> None:
        values = bitrix_embed.parse_launch_form(
            {
                "AUTH_ID": "a",
                "AUTH_EXPIRES": "1",
                "DOMAIN": "x",
                "member_id": "m",
                "PLACEMENT": "DEFAULT",
                "EVIL": "1",
            }
        )
        assert values["AUTH_ID"] == "a"

    def test_build_portal_origin_rejects_http(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.build_portal_origin("http://company.bitrix24.ru")

    def test_build_portal_origin_normalizes(self) -> None:
        assert (
            bitrix_embed.build_portal_origin("Company.Bitrix24.Ru")
            == "https://company.bitrix24.ru"
        )

    def test_install_state_from_dict_rejects_malformed(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.InstallState.from_dict({"contract_version": 99})

    def test_load_install_state_raises_on_corrupted_json(
        self,
        tmp_path: Path,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        (storage_dir / "interfaces" / "bitrix_rop_app.json").write_text(
            "{broken", encoding="utf-8"
        )
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.load_install_state(storage_dir)

    def test_load_install_state_raises_on_invalid_origin(
        self,
        tmp_path: Path,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        (storage_dir / "interfaces" / "bitrix_rop_app.json").write_text(
            json.dumps(
                {
                    "contract_version": 1,
                    "portal_origin": "http://company.bitrix24.ru",
                    "portal_domain": "company.bitrix24.ru",
                    "member_id": "m",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.load_install_state(storage_dir)

    def test_validate_launch_auth_expires_accepts_ttl(self) -> None:
        bitrix_embed.validate_launch_auth_expires("3600")

    def test_validate_launch_auth_expires_rejects_zero_ttl(self) -> None:
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            bitrix_embed.validate_launch_auth_expires("0")

    def test_validate_launch_auth_expires_rejects_future_bomb(self) -> None:
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            bitrix_embed.validate_launch_auth_expires(
                str(int(time.time()) + 400 * 86400)
            )
