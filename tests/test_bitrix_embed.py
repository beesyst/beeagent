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
    (run_dir / "classified_events.json").write_text(json.dumps([]), encoding="utf-8")


def _set_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN_TOKEN", "admin-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-token")
    monkeypatch.setenv("BEEAGENT_WEB_OPERATOR_TOKEN", "operator-token")
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
    from beeagent_module.cases.rop_dashboard import (
        build_rop_web_projection,
        write_rop_web_projection,
    )
    from beeagent_module.interfaces.ui.app import build_beeui_app

    settings = _full_settings(monkeypatch)
    projection = build_rop_web_projection(
        storage_dir=storage_dir,
        periods=settings["rop"]["dashboard"]["periods"],
        logger=_logger(),
    )
    write_rop_web_projection(storage_dir, projection, _logger())
    return build_beeui_app(
        settings=settings,
        logger=_logger(),
        storage_dir=storage_dir,
    )


def _https_client(storage_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return TestClient(
        _build_app(storage_dir, monkeypatch), base_url="https://testserver"
    )


def _http_client(storage_dir: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    return TestClient(
        _build_app(storage_dir, monkeypatch), base_url="http://testserver"
    )


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def read(self, amt: int | None = None) -> bytes:
        if amt is None or amt < 0:
            return self._payload
        return self._payload[:amt]


def _mock_user_response(monkeypatch: pytest.MonkeyPatch, payload: Any) -> list[str]:
    from beeagent_module.interfaces.ui import bitrix_embed

    requested_urls: list[str] = []

    def _fake_urlopen(req: Any, timeout: int = 0) -> _FakeResponse:
        requested_urls.append(req.full_url)
        body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )
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


def _bind_state(
    storage_dir: Path,
    member_id: str = MEMBER_ID,
    portal_origin: str = PORTAL_ORIGIN,
    portal_domain: str = PORTAL_DOMAIN,
) -> None:
    state = bitrix_embed.InstallState(
        portal_origin=portal_origin,
        portal_domain=portal_domain,
        member_id=member_id,
        installed_at="2026-01-01T00:00:00+00:00",
        contract_version=bitrix_embed.CONTRACT_VERSION,
    )
    bitrix_embed.create_install_state(storage_dir, state)


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
            lambda s: s["bitrix"]["embedded_app"].update(
                {"enabled": False, "portal_origin": ""}
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
    def test_install_without_oauth_creates_no_artifact(
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

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"

        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

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

    def test_identical_reinstall_requires_oauth_and_redirects(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        first = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )
        second = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )

        assert first.status_code == 303
        assert second.status_code == 303
        assert second.headers["location"] == "/rop"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        state = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert state["member_id"] == MEMBER_ID

    def test_reinstall_without_oauth_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)
        client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )

        response = client.post("/bitrix/rop/install", data=_install_form())

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"

    def test_conflicting_member_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )
        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(member_id="member-other"),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflicting_installation"

    def test_conflicting_domain_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )
        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(DOMAIN="other.bitrix24.ru"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "portal_mismatch"

    def test_domain_mismatch_with_config_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(
            monkeypatch,
            _active_user_payload(user_id="42"),
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(DOMAIN="other.bitrix24.ru"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "portal_mismatch"
        assert requested == []
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

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
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data={**_install_full_form(), "EVIL": "x", "APP_SID": "sid"},
            follow_redirects=False,
        )

        assert response.status_code == 303
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
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(PROTOCOL="1"),
            follow_redirects=False,
        )

        assert response.status_code == 303

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

    def test_forwarded_proto_spoof_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(
            monkeypatch,
            _active_user_payload(user_id="42"),
        )
        client = _http_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            headers={"X-Forwarded-Proto": "https"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "https_required"
        assert requested == []

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

    def test_install_expired_token_creates_no_artifact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(AUTH_EXPIRES=str(int(time.time()) - 10)),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "invalid_launch"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

    @pytest.mark.parametrize(
        "payload",
        [
            _active_user_payload(user_id="42", active=False),
            {"error": "expired_token"},
        ],
    )
    def test_invalid_install_creates_no_artifact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        payload: Any,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, payload)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "bitrix_verification_failed"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

    def test_install_missing_auth_expires_creates_no_artifact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(AUTH_EXPIRES=""),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

    def test_install_stored_origin_mismatch_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(
            monkeypatch,
            _active_user_payload(user_id="42"),
        )
        _bind_state(
            storage_dir,
            portal_origin="https://other.bitrix24.ru",
            portal_domain="other.bitrix24.ru",
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "installation_portal_mismatch"
        assert requested == []

    def test_install_duplicate_sensitive_fields_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            content=f"member_id={MEMBER_ID}&AUTH_ID=first&AUTH_ID=second",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

    def test_install_invalid_content_type_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            content='{"member_id": "m"}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"

    def test_install_oversized_body_without_content_length_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        body = "member_id={0}&AUTH_ID=a&PLACEMENT={1}".format(
            MEMBER_ID,
            "x" * bitrix_embed.MAX_FORM_BODY_BYTES,
        )
        response = client.post(
            "/bitrix/rop/install",
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"

    def test_install_oversized_body_with_false_content_length_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        client = _https_client(storage_dir, monkeypatch)

        body = "member_id={0}&AUTH_ID=a&PLACEMENT={1}".format(
            MEMBER_ID,
            "x" * bitrix_embed.MAX_FORM_BODY_BYTES,
        )
        response = client.post(
            "/bitrix/rop/install",
            content=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Content-Length": "10",
            },
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_install"

    def test_atomic_conflicting_install_race(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        from beeagent_module.interfaces.ui import bitrix_embed as embed_mod

        conflicting = embed_mod.InstallState(
            portal_origin=PORTAL_ORIGIN,
            portal_domain=PORTAL_DOMAIN,
            member_id="member-other",
            installed_at="2026-01-01T00:00:00+00:00",
            contract_version=embed_mod.CONTRACT_VERSION,
        )
        calls = {"load": 0}

        def _race_load(storage):
            calls["load"] += 1
            if calls["load"] == 1:
                return None
            return conflicting

        def _race_create(storage, state):
            return False

        monkeypatch.setattr(embed_mod, "load_install_state", _race_load)
        monkeypatch.setattr(embed_mod, "create_install_state", _race_create)

        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflicting_installation"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

    def test_race_state_portal_mismatch_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        from beeagent_module.interfaces.ui import bitrix_embed as embed_mod

        raced = embed_mod.InstallState(
            portal_origin="https://other.bitrix24.ru",
            portal_domain="other.bitrix24.ru",
            member_id=MEMBER_ID,
            installed_at="2026-01-01T00:00:00+00:00",
            contract_version=embed_mod.CONTRACT_VERSION,
        )
        calls = {"load": 0}

        def _race_load(storage):
            calls["load"] += 1
            if calls["load"] == 1:
                return None
            return raced

        def _race_create(storage, state):
            return False

        monkeypatch.setattr(embed_mod, "load_install_state", _race_load)
        monkeypatch.setattr(embed_mod, "create_install_state", _race_create)

        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "installation_portal_mismatch"
        assert "set-cookie" not in response.headers

    @pytest.mark.parametrize(
        "race_content",
        [
            "{corrupted",
            "x" * (bitrix_embed.MAX_INSTALL_STATE_BYTES + 1),
        ],
    )
    def test_race_state_corrupted_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        race_content: str,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        from beeagent_module.interfaces.ui import bitrix_embed as embed_mod

        def _race_create(storage, state):
            (storage / "interfaces" / "bitrix_rop_app.json").write_text(
                race_content,
                encoding="utf-8",
            )
            return False

        monkeypatch.setattr(embed_mod, "create_install_state", _race_create)

        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "install_state_corrupted"
        assert "set-cookie" not in response.headers

    def test_race_state_identical_binding_accepted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(monkeypatch, _active_user_payload(user_id="42"))
        from beeagent_module.interfaces.ui import bitrix_embed as embed_mod

        raced = embed_mod.InstallState(
            portal_origin=PORTAL_ORIGIN,
            portal_domain=PORTAL_DOMAIN,
            member_id=MEMBER_ID,
            installed_at="2026-01-01T00:00:00+00:00",
            contract_version=embed_mod.CONTRACT_VERSION,
        )
        calls = {"load": 0}

        def _race_load(storage):
            calls["load"] += 1
            if calls["load"] == 1:
                return None
            return raced

        def _race_create(storage, state):
            return False

        monkeypatch.setattr(embed_mod, "load_install_state", _race_load)
        monkeypatch.setattr(embed_mod, "create_install_state", _race_create)

        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/rop"

    def test_install_oversized_response_creates_no_artifact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        oversized = {"result": {"ID": "42", "ACTIVE": True, "extra": "x" * 70000}}
        _mock_user_response(monkeypatch, oversized)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "response_too_large"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()

    def test_install_invalid_principal_creates_no_artifact(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _mock_user_response(
            monkeypatch,
            {"result": {"ID": True, "ACTIVE": True}},
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/install",
            data=_install_full_form(),
        )

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "malformed_response"
        artifact_path = storage_dir / "interfaces" / "bitrix_rop_app.json"
        assert not artifact_path.exists()


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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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

    def test_launch_get_returns_405(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _write_minimal_run(storage_dir)
        requested = _mock_user_response(monkeypatch, _active_user_payload(user_id="7"))
        _bind_state(storage_dir)
        client = _https_client(storage_dir, monkeypatch)

        response = client.get(
            "/bitrix/rop/launch",
            params=_launch_form(),
            follow_redirects=False,
        )

        assert response.status_code == 405
        assert requested == []

    def test_launch_get_without_params_returns_405(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        _bind_state(storage_dir)
        client = _https_client(storage_dir, monkeypatch)

        response = client.get("/bitrix/rop/launch", follow_redirects=False)

        assert response.status_code == 405
        assert requested == []

    def test_launch_accepts_ttl_expiry(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload(user_id="9"))
        client = _https_client(storage_dir, monkeypatch)
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)

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
        _bind_state(storage_dir)
        client = _http_client(storage_dir, monkeypatch)

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
        _bind_state(storage_dir)

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
        assert "Bitrix embedded app launch: user_id=" not in caplog.text

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

    def test_launch_oversized_response_rejects_without_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _bind_state(storage_dir)
        oversized = {"result": {"ID": "42", "ACTIVE": True, "extra": "x" * 70000}}
        _mock_user_response(monkeypatch, oversized)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(),
            follow_redirects=False,
        )

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "response_too_large"
        assert "set-cookie" not in response.headers

    def test_launch_invalid_principal_rejects_without_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        _bind_state(storage_dir)
        _mock_user_response(
            monkeypatch,
            {"result": {"ID": "not-numeric", "ACTIVE": True}},
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(),
            follow_redirects=False,
        )

        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "bitrix_verification_failed"
        assert error["reason"] == "malformed_response"
        assert "set-cookie" not in response.headers
        artifact_text = (storage_dir / "interfaces" / "bitrix_rop_app.json").read_text(
            encoding="utf-8"
        )
        assert "not-numeric" not in artifact_text

    def test_launch_domain_mismatch_no_outbound(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        _bind_state(storage_dir)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/launch",
            data=_launch_form(DOMAIN="other.bitrix24.ru"),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "portal_mismatch"
        assert requested == []

    def test_launch_stored_origin_mismatch_no_outbound(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        _bind_state(
            storage_dir,
            portal_origin="https://other.bitrix24.ru",
            portal_domain="other.bitrix24.ru",
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "installation_portal_mismatch"
        assert requested == []

    def test_launch_oversized_install_state_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        (storage_dir / "interfaces" / "bitrix_rop_app.json").write_text(
            "x" * (bitrix_embed.MAX_INSTALL_STATE_BYTES + 1),
            encoding="utf-8",
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "install_state_corrupted"
        assert requested == []

    def test_launch_overlong_state_field_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        _bind_state(
            storage_dir,
            member_id="m" * (bitrix_embed.MAX_INSTALL_STATE_FIELD_LENGTH + 1),
        )
        client = _https_client(storage_dir, monkeypatch)

        response = client.post("/bitrix/rop/launch", data=_launch_form())

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "install_state_corrupted"
        assert requested == []

    def test_launch_duplicate_sensitive_fields_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        _bind_state(storage_dir)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/launch",
            content=f"member_id={MEMBER_ID}&AUTH_ID=first&AUTH_ID=second",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_launch"
        assert requested == []

    def test_launch_invalid_content_type_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        storage_dir = _make_storage(tmp_path)
        requested = _mock_user_response(monkeypatch, _active_user_payload())
        _bind_state(storage_dir)
        client = _https_client(storage_dir, monkeypatch)

        response = client.post(
            "/bitrix/rop/launch",
            content='{"member_id": "m"}',
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_launch"
        assert requested == []


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
        assert (
            beeui["auth"]["session_age_max"]
            == bitrix_embed.EMBEDDED_SESSION_AGE_MAX_SECONDS
        )

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
            data={"user_id": "admin", "token": "admin-token"},
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
            bitrix_embed.parse_install_form({"AUTH_ID": "a", "PLACEMENT": "DEFAULT"})

    def test_parse_install_form_rejects_oversized_known_field(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.parse_install_form(
                {
                    "DOMAIN": "x",
                    "member_id": "m" * (bitrix_embed.MAX_FORM_VALUE_LENGTH + 1),
                }
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

    def test_create_install_state_is_exclusive(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        state = bitrix_embed.InstallState(
            portal_origin=PORTAL_ORIGIN,
            portal_domain=PORTAL_DOMAIN,
            member_id=MEMBER_ID,
            installed_at="2026-01-01T00:00:00+00:00",
            contract_version=bitrix_embed.CONTRACT_VERSION,
        )
        assert bitrix_embed.create_install_state(storage_dir, state) is True
        assert bitrix_embed.create_install_state(storage_dir, state) is False
        loaded = bitrix_embed.load_install_state(storage_dir)
        assert loaded is not None
        assert loaded.member_id == MEMBER_ID

    def test_load_install_state_raises_on_oversized(self, tmp_path: Path) -> None:
        storage_dir = _make_storage(tmp_path)
        (storage_dir / "interfaces" / "bitrix_rop_app.json").write_text(
            "x" * (bitrix_embed.MAX_INSTALL_STATE_BYTES + 1),
            encoding="utf-8",
        )
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.load_install_state(storage_dir)

    def test_install_state_from_dict_rejects_inconsistent_domain(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.InstallState.from_dict(
                {
                    "contract_version": 1,
                    "portal_origin": "https://company.bitrix24.ru",
                    "portal_domain": "other.bitrix24.ru",
                    "member_id": "m",
                    "installed_at": "2026-01-01T00:00:00+00:00",
                }
            )

    def test_install_state_from_dict_rejects_overlong_field(self) -> None:
        with pytest.raises(bitrix_embed.BitrixEmbedError):
            bitrix_embed.InstallState.from_dict(
                {
                    "contract_version": 1,
                    "portal_origin": "https://company.bitrix24.ru",
                    "portal_domain": "company.bitrix24.ru",
                    "member_id": "m"
                    * (bitrix_embed.MAX_INSTALL_STATE_FIELD_LENGTH + 1),
                    "installed_at": "2026-01-01T00:00:00+00:00",
                }
            )


class TestVerifyBitrixUserBounds:
    def _verify(
        self,
        monkeypatch: pytest.MonkeyPatch,
        payload: Any,
    ) -> dict[str, Any]:
        from beeagent_module.interfaces.ui import bitrix_embed

        body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )

        def _fake_urlopen(req: Any, timeout: int = 0) -> _FakeResponse:
            return _FakeResponse(body)

        monkeypatch.setattr(bitrix_embed, "urlopen", _fake_urlopen)
        return bitrix_embed.verify_bitrix_current_user(
            PORTAL_ORIGIN,
            "auth-id",
            5,
        )

    def test_response_exactly_at_byte_limit_accepted(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = b'{"result":'
        suffix = b'{"ID":"42","ACTIVE":true}}'
        pad = bitrix_embed.MAX_BITRIX_RESPONSE_BYTES - len(prefix) - len(suffix)
        payload = prefix + b" " * pad + suffix
        assert len(payload) == bitrix_embed.MAX_BITRIX_RESPONSE_BYTES

        user = self._verify(monkeypatch, payload)

        assert user["ID"] == "42"

    def test_response_above_byte_limit_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = b'{"result":'
        suffix = b'{"ID":"42","ACTIVE":true}}'
        pad = bitrix_embed.MAX_BITRIX_RESPONSE_BYTES + 1 - len(prefix) - len(suffix)
        payload = prefix + b" " * pad + suffix

        with pytest.raises(bitrix_embed.BitrixLaunchError) as exc:
            self._verify(monkeypatch, payload)

        assert exc.value.reason == "response_too_large"

    def test_oversized_valid_json_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {"result": {"ID": "42", "ACTIVE": True, "extra": "x" * 70000}}

        with pytest.raises(bitrix_embed.BitrixLaunchError) as exc:
            self._verify(monkeypatch, payload)

        assert exc.value.reason == "response_too_large"

    def test_overlong_user_id_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {
            "result": {
                "ID": "9" * (bitrix_embed.MAX_BITRIX_USER_ID_LENGTH + 1),
                "ACTIVE": True,
            }
        }

        with pytest.raises(bitrix_embed.BitrixLaunchError) as exc:
            self._verify(monkeypatch, payload)

        assert exc.value.reason == "malformed_response"

    def test_non_numeric_user_id_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {"result": {"ID": "user-42", "ACTIVE": True}}

        with pytest.raises(bitrix_embed.BitrixLaunchError) as exc:
            self._verify(monkeypatch, payload)

        assert exc.value.reason == "malformed_response"

    def test_boolean_user_id_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {"result": {"ID": True, "ACTIVE": True}}

        with pytest.raises(bitrix_embed.BitrixLaunchError) as exc:
            self._verify(monkeypatch, payload)

        assert exc.value.reason == "malformed_response"

    def test_valid_integer_user_id_accepted(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {"result": {"ID": 42, "ACTIVE": True}}

        user = self._verify(monkeypatch, payload)

        assert user["ID"] == "42"

    def test_valid_numeric_string_user_id_accepted(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {"result": {"ID": "42", "ACTIVE": True}}

        user = self._verify(monkeypatch, payload)

        assert user["ID"] == "42"

    def test_principal_user_id_accepts_only_normalized_string(self) -> None:
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            bitrix_embed.principal_user_id({"ID": 42})
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            bitrix_embed.principal_user_id({"ID": ""})
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            bitrix_embed.principal_user_id(
                {"ID": "9" * (bitrix_embed.MAX_BITRIX_USER_ID_LENGTH + 1)}
            )
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            bitrix_embed.principal_user_id({"ID": "abc"})
        assert (
            bitrix_embed.principal_user_id({"ID": "42"})
            == f"{bitrix_embed.BITRIX_PRINCIPAL_PREFIX}42"
        )

    def test_is_bitrix_principal_user_id(self) -> None:
        assert bitrix_embed.is_bitrix_principal_user_id("bitrix:42")
        assert bitrix_embed.is_bitrix_principal_user_id(
            f"bitrix:{'9' * bitrix_embed.MAX_BITRIX_USER_ID_LENGTH}"
        )
        assert not bitrix_embed.is_bitrix_principal_user_id("42")
        assert not bitrix_embed.is_bitrix_principal_user_id("bitrix:user-42")
        assert not bitrix_embed.is_bitrix_principal_user_id("bitrix:")
        assert not bitrix_embed.is_bitrix_principal_user_id("bitrix:42x")
        assert not bitrix_embed.is_bitrix_principal_user_id(
            f"bitrix:{'9' * (bitrix_embed.MAX_BITRIX_USER_ID_LENGTH + 1)}"
        )
        assert not bitrix_embed.is_bitrix_principal_user_id("")
        assert not bitrix_embed.is_bitrix_principal_user_id(None)

    @pytest.mark.parametrize(
        "payload",
        [
            b"not-json{{",
            "just a string",
            [1, 2, 3],
            42,
            {"result": "not-a-dict"},
            {"result": {"ACTIVE": True}},
            {"result": {"ID": "42"}},
            {"error": 123},
        ],
    )
    def test_malformed_response_fuzz_rejected(
        self,
        monkeypatch: pytest.MonkeyPatch,
        payload: Any,
    ) -> None:
        with pytest.raises(bitrix_embed.BitrixLaunchError):
            self._verify(monkeypatch, payload)
