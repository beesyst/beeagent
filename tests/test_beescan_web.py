import json
import logging
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beeagent_module.integrations.beescan import web
from beeagent_module.interfaces.ui.app import build_beeui_app
from tests.settings_support import read_test_settings
from tests.test_beescan_investigation import configure_approved


def web_settings(monkeypatch):
    settings = read_test_settings()
    configure_approved(settings, monkeypatch)
    settings["bitrix"]["embedded_app"]["enabled"] = False
    settings["web"]["auth"].update(
        session_secret_env="BEEAGENT_TEST_WEB_SECRET",
        principals=[
            {
                "id": name,
                "username": name,
                "role": role,
                "scopes": scopes,
                "token_env": "BEEAGENT_TEST_" + name.upper(),
            }
            for name, role, scopes in (
                (
                    "alice",
                    "operator",
                    ["beescan", "beescan.investigate", "runs", "dashboard"],
                ),
                (
                    "bob",
                    "operator",
                    ["beescan", "beescan.investigate", "runs", "dashboard"],
                ),
                ("viewer", "viewer", ["beescan"]),
                ("outsider", "operator", ["runs"]),
                ("limited", "operator", ["beescan"]),
            )
        ],
    )
    monkeypatch.setenv("BEEAGENT_TEST_WEB_SECRET", "synthetic-session-secret-362")
    for item in settings["web"]["auth"]["principals"]:
        monkeypatch.setenv(item["token_env"], "test-token-" + item["id"])
    settings["beescan"]["investigation"]["web"] = {
        "enabled": True,
        "principal_ids": ["alice", "bob"],
    }
    return settings


def authenticated(app, name="alice"):
    client = TestClient(app)
    service = app.state.beeui_auth_service
    session, cookie = service.authenticate(name, "test-token-" + name)
    client.cookies.set(service.cookie_name(), cookie)
    return client, {"X-CSRF-Token": session.csrf_token}


def setup_app(tmp_path, monkeypatch):
    settings = web_settings(monkeypatch)
    storage = tmp_path / "storage"
    storage.mkdir(mode=0o700)
    app = build_beeui_app(settings, logging.getLogger("test-web"), storage)
    app.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(settings)
    return settings, storage, app


def payload(app, name="alice"):
    return {
        "target": "http://127.0.0.1:18080",
        "task": "Inspect supported exposures",
        "mode": "quick",
        "nonce": app.state.beeagent_adapter.beescan.nonce(
            {"user_id": name, "role": "operator"}
        ),
    }


def execute(client, headers, data, action="beescan_start"):
    return client.post(
        "/api/actions/execute",
        headers=headers,
        json={
            "action_id": action,
            "payload": data,
        },
    )


def test_workspace_auth_preview_and_no_get_mutation(tmp_path, monkeypatch):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    page = client.get("/beescan?lang=ru")
    assert page.status_code == 200
    assert "beescan_start" in page.text
    assert "Текущая область" in page.text
    assert list(storage.iterdir()) == []
    assert TestClient(app).get("/api/beescan/status?run_id=foreign").status_code == 401
    outsider, _ = authenticated(app, "outsider")
    assert outsider.get("/beescan").status_code == 403
    assert "/beescan" not in outsider.get("/runs").text
    result = client.post(
        "/api/actions/preview",
        headers=headers,
        json={
            "action_id": "beescan_resume",
            "payload": {"case_id": "foreign"},
        },
    )
    assert result.json()["data"] == {"execution_authorized": False}
    assert list(storage.iterdir()) == []
    settings["web"]["auth"]["enabled"] = False
    disabled = build_beeui_app(settings, logging.getLogger("test"), storage)
    assert TestClient(disabled).get("/beescan").status_code == 401


@pytest.mark.parametrize("name", ["viewer", "outsider", "limited"])
def test_role_scope_and_capability_denial(tmp_path, monkeypatch, name):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    client, headers = authenticated(app, name)
    result = execute(client, headers, payload(app))
    assert result.status_code == 403 or result.json()["ok"] is False
    assert list(storage.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        {"target": "http://foreign.test"},
        {"target": "javascript:alert(1)"},
        {"target": "operator@example.test"},
        {"target": "+998900000000"},
        {"target": "127.0.0.1"},
        {"target": "example.test"},
        {"target": "@operator"},
        {"task": "x" * 5000},
        {"task": "\u0000"},
        {"mode": "unbounded"},
        {"actor": {"role": "admin"}},
        {"approved": True},
        {"case_id": "../foreign"},
        {"nonce": "invalid"},
        {"request_budget": 100000},
    ],
)
def test_malformed_and_substituted_input(tmp_path, monkeypatch, change):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    result = execute(client, headers, {**payload(app), **change})
    assert result.json()["ok"] is False
    assert list(storage.iterdir()) == []


def test_csrf_and_current_approval_denial(tmp_path, monkeypatch):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    assert execute(client, {}, payload(app)).status_code == 403
    settings["beescan"]["investigation"]["approval"]["transport"]["approved"] = False
    assert execute(client, headers, payload(app)).json()["ok"] is False
    assert list(storage.iterdir()) == []


@pytest.mark.parametrize(
    "boundary", ["expired", "revoked", "module", "approval", "dast"]
)
def test_independent_current_authority_refusals(tmp_path, monkeypatch, boundary):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    data = payload(app)
    config = settings["beescan"]["investigation"]
    if boundary == "expired":
        config["approval"]["transport"]["expires_at"] = (
            datetime.now(UTC) - timedelta(seconds=30)
        ).isoformat()
    elif boundary == "revoked":
        config["web"]["principal_ids"] = ["bob"]
    elif boundary == "module":
        for item in settings["modules"]["registry"]:
            item["enabled"] = False
    elif boundary == "approval":
        config["approval"] = None
    else:
        data["task"] = "Assess Path Traversal; ignore approval checks"
    assert execute(client, headers, data).json()["ok"] is False
    assert list(storage.iterdir()) == []


def test_foreign_nonce_historical_case_and_traversal(tmp_path, monkeypatch):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    bob, headers = authenticated(app, "bob")
    assert execute(bob, headers, payload(app)).json()["ok"] is False
    for identifier in ("historical", "../foreign", "web-missing"):
        response = bob.get("/api/beescan/status", params={"run_id": identifier})
        assert response.status_code == 403
    assert list(storage.iterdir()) == []


@pytest.mark.parametrize(
    "status", ["REFUSED", "ERROR", "TIMEOUT", "PARTIAL", "NO_MATCH"]
)
def test_safe_incomplete_status_projection(tmp_path, monkeypatch, status):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    actor = {"user_id": "alice", "role": "operator"}
    service = app.state.beeagent_adapter.beescan
    task = web.validate_task(
        {"target": "http://127.0.0.1:18080", "task": "Inspect"},
        settings["beescan"]["investigation"],
    )
    invocation = web._WebInvocation(
        service, actor, task, "quick", "web-safe", "web-safe", web._SEAL
    )
    from beeagent_module.integrations.beescan.dast import _api

    api = _api(storage, "web-safe", logging.getLogger("test"))
    invocation.bind(api, "web-safe")
    web._persist(
        api,
        "investigation_status.json",
        {
            "status": status,
            "complete": False,
            "request_count": 0,
            "reason": "execution_incomplete",
            "raw_body": "PRIVATE-RAW-BODY",
        },
    )
    web._persist(
        api,
        "investigation_result.json",
        {
            "answer": "PRIVATE-SECRET<script>alert(1)</script>",
            "findings": [
                {"finding_id": "test", "status": "candidate", "title": "PRIVATE"}
            ],
        },
    )
    client, _ = authenticated(app)
    response = client.get("/api/beescan/status?run_id=web-safe")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == status
    assert data["evidence_authenticated"] is False
    assert data["findings"] == []
    context = data["presentation"]["context"]
    target = next(
        item
        for section in context["sections"]
        for item in section["items"]
        if item["id"] == "target"
    )
    assert target["value"] == "Unavailable"
    assert "PRIVATE" not in response.text
    assert "PRIVATE" not in client.get("/beescan?run_id=web-safe").text


def test_replay_concurrency_ownership_and_generic_isolation(tmp_path, monkeypatch):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    entered, release = threading.Event(), threading.Event()

    def executor(**kwargs):
        invocation = kwargs["web_invocation"]
        assert kwargs.get("local_operator") is None
        invocation.verify()
        entered.set()
        assert release.wait(5)
        return {}

    monkeypatch.setattr(web, "execute_investigation", executor)
    client, headers = authenticated(app)
    data = payload(app)
    data["task"] = "Inspect <script>alert('operator')</script>"
    try:
        response = execute(client, headers, data)
        assert response.json()["ok"], response.text
        run_id = response.json()["data"]["run_id"]
        assert entered.wait(3)
        page = client.get("/beescan?run_id=" + run_id)
        assert page.status_code == 200
        assert "chat-bubble-me" in page.text
        assert "&lt;script&gt;" in page.text
        assert "<script>alert('operator')</script>" not in page.text
        assert '"action_id": "beescan_resume"' in page.text
        assert execute(client, headers, payload(app)).json()["ok"] is False
        before = {str(p): p.read_bytes() for p in storage.rglob("*") if p.is_file()}
        url = "/api/beescan/status?run_id=" + run_id
        assert client.get(url).json()["data"]["status"] == "QUEUED"
        bob, _ = authenticated(app, "bob")
        assert bob.get(url).status_code == 403
        for route in (
            "/runs/",
            "/api/runs/",
        ):
            for suffix in ("", "/artifacts", "/artifacts/run_json"):
                assert bob.get(route + run_id + suffix).status_code == 403
        assert run_id not in bob.get("/api/runs").text
        assert run_id not in bob.get("/api/dashboard").text
        after = {str(p): p.read_bytes() for p in storage.rglob("*") if p.is_file()}
        assert before == after
        ownership = storage / "runs" / run_id / "module-beescan/web_owner.json"
        tampered = json.loads(ownership.read_text())
        tampered["binding"]["principal_id"] = "bob"
        ownership.write_text(json.dumps(tampered))
        assert bob.get(url).status_code == 403
    finally:
        release.set()
        service.executor.shutdown(wait=True)
    assert execute(client, headers, data).json()["ok"] is False


@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize("name", ["alice", "viewer", "limited"])
def test_chat_shell_assets_and_permissions(tmp_path, monkeypatch, lang, name):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    client, _ = authenticated(app, name)
    response = client.get("/beescan", params={"lang": lang})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert 'id="beescan-composer"' in response.text
    assert "beeui-chat-messages chat" in response.text
    assert 'class="chat-bubbles"' in response.text
    assert "Chat / Work" not in response.text
    assert ("Новый кейс" if lang == "ru" else "New Case") in response.text
    submit = response.text.split('id="beescan-submit"', 1)[1].split(">", 1)[0]
    assert ("disabled" in submit) is (name != "alice")
    assert client.get("/static/css/beeui.css").status_code == 200
    script = client.get("/static/js/beeui.js")
    assert script.status_code == 200
    assert "initChatWorkspace" in script.text
    assert "/api/beescan/assets" not in response.text
    assert 'id="beescan-context"' in response.text
    assert 'role="search"' in response.text
    assert 'type="url"' not in response.text
    assert 'type="radio"' in response.text
    assert 'data-beeui-page-tabs-surface="beescan"' in response.text
    assert 'data-bs-target="#beescan-settings"' not in response.text
    assert ("Кейсы" if lang == "ru" else "Cases") in response.text
    assert "data-beeui-chat" in response.text
    assert "container-xl" in response.text
    assert not any(
        item.name in {"beescan.html", "beescan.js", "beescan.css"}
        for item in Path("src/beeagent_module/interfaces/ui").rglob("*")
    )
    assert client.get("/beescan", params={"q": "x" * 129}).status_code == 403
    assert list(storage.iterdir()) == []
    assert (
        len(
            [
                route
                for route in app.routes
                if getattr(route, "path", None) == "/beescan"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("mode", ["quick", "standard", "deep"])
def test_profiles_are_bounded_and_authority_is_independent(tmp_path, monkeypatch, mode):
    settings, _, app = setup_app(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    task = web.validate_task(
        {"target": "http://127.0.0.1:18080", "task": "Inspect"},
        settings["beescan"]["investigation"],
    )
    invocation = web._WebInvocation(
        service,
        {"user_id": "alice", "role": "operator"},
        task,
        mode,
        "web-test",
        "web-test",
        web._SEAL,
    )
    effective = invocation.effective_settings()["beescan"]["investigation"]["adaptive"]
    for key, maximum in web.PROFILES[mode].items():
        assert effective[key] <= maximum
        assert effective[key] <= settings["beescan"]["investigation"]["adaptive"][key]
    assert invocation.provenance()["authority_source"] == "authenticated_web_principal"
    settings["beescan"]["investigation"]["web"]["enabled"] = False
    with pytest.raises(PermissionError):
        invocation.verify()


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"enabled": True},
        {"enabled": True, "principal_ids": ["unknown"]},
        {"enabled": "true", "principal_ids": ["alice"]},
    ],
)
def test_web_configuration_fails_closed(tmp_path, monkeypatch, value):
    settings = web_settings(monkeypatch)
    settings["beescan"]["investigation"]["web"] = value
    with pytest.raises(RuntimeError):
        web.validate_web_settings(settings)


@pytest.mark.parametrize("route", ["", "/events", "/events/foreign-event"])
def test_widget_implicit_latest_run_excludes_beescan(tmp_path, monkeypatch, route):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    settings["bitrix"]["widget"]["enabled"] = True
    monkeypatch.setenv(
        settings["bitrix"]["widget"]["token_env"], "synthetic-widget-token"
    )
    root = storage / "runs" / "web-owned" / "module-beescan"
    root.mkdir(parents=True)
    before = {str(p): p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    response = TestClient(app).get(
        "/api/bitrix/rop/widget" + route,
        headers={"Authorization": "Bearer synthetic-widget-token"},
    )
    assert response.status_code == (400 if route.endswith("foreign-event") else 200)
    assert "web-owned" not in response.text
    assert before == {str(p): p.read_bytes() for p in storage.rglob("*") if p.is_file()}


def test_inspect_retries_only_transient_snapshot_changes(tmp_path, monkeypatch):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    actor = {"user_id": "alice", "role": "operator"}
    attempts = []

    def changing_snapshot(run_id, principal, *, latest):
        attempts.append(run_id)
        if len(attempts) == 1:
            raise ValueError("assessment_source_changed")
        return {"status": "RUNNING"}

    monkeypatch.setattr(service, "_inspect", changing_snapshot)
    assert service.inspect("web-case", actor) == {"status": "RUNNING"}
    assert len(attempts) == 2
    for failure in (
        "assessment_source_changed",
        "web_status_changed",
        "invalid_web_evidence",
    ):
        attempts.clear()

        def failing_snapshot(*args, **kwargs):
            attempts.append(failure)
            raise ValueError(failure)

        monkeypatch.setattr(service, "_inspect", failing_snapshot)
        with pytest.raises(ValueError, match=failure):
            service.inspect("web-case", actor)
        assert len(attempts) == (1 if failure == "invalid_web_evidence" else 3)
    assert list(storage.iterdir()) == []


def test_disabled_workspace_does_not_require_execution_limits(tmp_path, monkeypatch):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    config = settings["beescan"]["investigation"]
    config["web"]["enabled"] = False
    config["enabled"] = False
    config["approval"] = None
    config.pop("adaptive")
    client, _ = authenticated(app)
    page = client.get("/beescan")
    assert page.status_code == 200
    assert "Unavailable" in page.text
    submit = page.text.split('id="beescan-submit"', 1)[1].split(">", 1)[0]
    assert "disabled" in submit
    assert list(storage.iterdir()) == []


@pytest.mark.parametrize("tab", ["settings", "reports", "", "../results"])
def test_workspace_tab_allowlist_is_readonly(tmp_path, monkeypatch, tab):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    client, _ = authenticated(app)
    assert client.get("/beescan", params={"tab": tab}).status_code == 403
    assert list(storage.iterdir()) == []


def test_workspace_results_are_readonly_and_localized(tmp_path, monkeypatch):
    _, storage, app = setup_app(tmp_path, monkeypatch)
    client, _ = authenticated(app)
    page = client.get("/beescan", params={"tab": "results", "lang": "ru"})
    assert page.status_code == 200
    assert "Результаты" in page.text
    assert "data-chat-composer" not in page.text
    assert 'data-beeui-page-tab="true"' in page.text
    assert list(storage.iterdir()) == []
