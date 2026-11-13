import json
import logging
import os
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beeagent_module.integrations.beescan import web
from beeagent_module.interfaces.ui.app import build_beeui_app
from tests.settings_support import read_test_settings
from tests.test_beescan_investigation import (
    configure_approved,
    editable_dependency,  # noqa: F401 — pytest fixture
)


def web_settings(monkeypatch):
    settings = read_test_settings()
    settings["beescan"].pop("target_policy", None)
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


def test_metadata_atomic_interruption_and_symlink_refusal(tmp_path, monkeypatch):
    _, storage, app, case_id, _ = reviewed_dast_fixture(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    path = storage / "runs" / case_id / "module-beescan" / "web_metadata.json"
    original = {"value": {"case_id": case_id, "title": "Original", "archived": False}}
    service._publish_metadata(case_id, original)
    raw = path.read_bytes()
    with monkeypatch.context() as scoped:
        scoped.setattr(
            web.os,
            "replace",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("interrupted")),
        )
        with pytest.raises(OSError):
            service._publish_metadata(case_id, {"value": "changed"})
    assert path.read_bytes() == raw
    assert not list(path.parent.glob("web-metadata-*.pending"))
    path.unlink()
    destination = tmp_path / "protected"
    destination.write_text("original")
    path.symlink_to(destination)
    with pytest.raises(PermissionError):
        service._publish_metadata(case_id, original)
    assert destination.read_text() == "original"


def test_case_presentation_rename_archive_and_owner_refusal(tmp_path, monkeypatch):
    _, storage, app, case_id, _ = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    root = storage / "runs" / case_id / "module-beescan"
    original = {
        name: (root / name).read_bytes() for name in ("case.json", "web_receipt.json")
    }
    response = execute(
        client, headers, {"case_id": case_id, "title": "Renamed Case"}, "beescan_rename"
    )
    assert response.json()["ok"]
    assert "Renamed Case" in client.get("/beescan?tab=results").text
    other, other_headers = authenticated(app, "bob")
    assert not execute(
        other, other_headers, {"case_id": case_id, "title": "Foreign"}, "beescan_rename"
    ).json()["ok"]
    assert not execute(
        client, headers, {"case_id": case_id, "confirmation": "yes"}, "beescan_archive"
    ).json()["ok"]
    assert execute(
        client,
        headers,
        {"case_id": case_id, "confirmation": "ARCHIVE"},
        "beescan_archive",
    ).json()["ok"]
    assert "Renamed Case" not in client.get("/beescan?tab=results").text
    assert all((root / name).read_bytes() == raw for name, raw in original.items())
    assert app.state.beeagent_adapter.beescan.inspect(
        case_id, {"user_id": "alice", "role": "operator"}
    )["archived"]
    metadata_path = root / "web_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["value"]["title"] = "Tampered"
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(PermissionError):
        app.state.beeagent_adapter.beescan.inspect(
            case_id, {"user_id": "alice", "role": "operator"}
        )


def test_history_survives_mixed_runs_and_selected_filter(tmp_path, monkeypatch):
    _, storage, app, case_id, _ = reviewed_dast_fixture(tmp_path, monkeypatch)
    for index in range(520):
        (storage / "runs" / f"foreign-{index:04d}").mkdir(mode=0o700)
    (storage / "runs" / "web-symlink").symlink_to(
        storage / "runs" / case_id, target_is_directory=True
    )
    service = app.state.beeagent_adapter.beescan
    actor = {"user_id": "alice", "role": "operator"}
    assert [row["case_id"] for row in service.history(actor)] == [case_id]
    assert service.history({"user_id": "bob", "role": "operator"}) == []
    from beeagent_module.interfaces.ui.beescan import _workspace_context

    assert (
        _workspace_context(service, {"run_id": case_id, "q": "absent-search"}, actor)[
            "records"
        ]
        == []
    )
    assert (
        _workspace_context(service, {"run_id": case_id, "status": "ERROR"}, actor)[
            "records"
        ]
        == []
    )
    assert _workspace_context(service, {"page": "2"}, actor)["records"] == []


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
    assert data["presentation"]["complete"] is (
        status in {"REFUSED", "ERROR", "TIMEOUT"}
    )
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


@pytest.mark.parametrize(
    "published", ["QUEUED", "RUNNING", "ERROR", "REFUSED", "TIMEOUT"]
)
def test_worker_failure_preserves_status_and_private_diagnostics(
    tmp_path, monkeypatch, caplog, published
):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    task = web.validate_task(
        {"target": "http://127.0.0.1:18080", "task": "Inspect"},
        settings["beescan"]["investigation"],
    )
    invocation = web._WebInvocation(
        service,
        {"user_id": "alice", "role": "operator"},
        task,
        "quick",
        "web-failure",
        "web-failure",
        web._SEAL,
    )
    from beeagent_module.integrations.beescan.dast import _api

    api = _api(storage, invocation.run_id, logging.getLogger("test"))
    invocation.bind(api, invocation.run_id)
    marker = {
        "run_id": invocation.run_id,
        "case_id": invocation.case_id,
        "status": published,
        "reason": "original_reason",
        "complete": False,
        "request_count": 2,
        "request_count_exact": True,
    }
    web._persist(api, "investigation_status.json", marker)
    before = (api.artifact_dir() / "investigation_status.json").read_bytes()

    def fail(**kwargs):
        raise ValueError("PRIVATE-response-body Authorization: PRIVATE-token")

    monkeypatch.setattr(web, "execute_investigation", fail)
    service._execute(invocation, None, os.open(storage, os.O_RDONLY | os.O_DIRECTORY))
    result = json.loads((api.artifact_dir() / "investigation_status.json").read_text())
    assert result["request_count"] == 2
    if published in {"ERROR", "REFUSED", "TIMEOUT"}:
        assert (api.artifact_dir() / "investigation_status.json").read_bytes() == before
    else:
        assert result["status"] == "ERROR"
        assert result["reason"] == "web_execution_incomplete"
        assert result["request_count_exact"] is False
    log = api.artifact_dir() / "web_failure.log"
    assert log.stat().st_mode & 0o777 == 0o600
    assert log.parent.stat().st_mode & 0o777 == 0o700
    content = log.read_text()
    assert "category=validation phase=execution" in content
    assert "run_id=web-failure" in content
    assert "web.py:" in content and " in fail" in content
    assert "PRIVATE" not in content + caplog.text
    client, _ = authenticated(app)
    assert "PRIVATE" not in client.get("/api/beescan/status?run_id=web-failure").text
    for route in ("/runs/", "/api/runs/"):
        response = client.get(route + invocation.run_id + "/artifacts/web_failure.log")
        assert response.status_code == 403
        assert "Traceback" not in response.text


def test_receipt_failure_preserves_authenticated_case(tmp_path, monkeypatch):
    from beeagent_module.integrations.beescan.case_state import load_case

    settings, storage, app, case_id, _ = reviewed_dast_fixture(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    task = web.validate_task(
        {"target": "http://127.0.0.1:18080", "task": "Inspect"},
        settings["beescan"]["investigation"],
    )
    invocation = web._WebInvocation(
        service,
        {"user_id": "alice", "role": "operator"},
        task,
        "standard",
        case_id,
        case_id,
        web._SEAL,
    )
    root = storage / "runs" / case_id / "module-beescan"
    before = {
        name: (root / name).read_bytes()
        for name in ("case.json", "investigation_status.json", "web_receipt.json")
    }
    monkeypatch.setattr(
        web, "execute_investigation", lambda **kwargs: {"case_id": case_id}
    )
    original = web._persist

    def fail_receipt(api, name, data):
        if name == "web_receipt.json":
            raise OSError("PRIVATE-storage-payload")
        original(api, name, data)

    monkeypatch.setattr(web, "_persist", fail_receipt)
    service._execute(invocation, None, os.open(storage, os.O_RDONLY | os.O_DIRECTORY))
    assert {name: (root / name).read_bytes() for name in before} == before
    state, snapshot = load_case(storage, case_id)
    snapshot.verify()
    assert state["status"] == "CANDIDATE"
    assert (
        "category=storage phase=receipt_publication"
        in (root / "web_failure.log").read_text()
    )


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
    "boundary", ["valid", "not_lab", "seal", "policy", "revoked", "foreign_context"]
)
def test_editable_loader_web_authority(
    tmp_path, monkeypatch, editable_dependency, boundary
):
    from dataclasses import replace

    from beescan.domain import web_investigation

    from beeagent_module.integrations.beescan import investigation, local_cli

    settings, storage, app = setup_app(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    task = web.validate_task(
        {"target": "http://127.0.0.1:18080", "task": "Inspect"},
        settings["beescan"]["investigation"],
    )
    invocation = web._WebInvocation(
        service,
        {"user_id": "alice", "role": "operator"},
        task,
        "standard",
        "web-loader",
        "web-loader",
        web._SEAL,
    )
    policy = invocation.policy
    monkeypatch.setattr(
        local_cli._LocalRun,
        "verify",
        lambda *a, **kw: pytest.fail("Web acquired CLI authority"),
    )
    if boundary == "seal":
        invocation.seal = object()
    elif boundary == "policy":
        policy = replace(
            policy, transport=replace(policy.transport, scope_id="foreign-scope")
        )
    elif boundary == "revoked":
        settings["beescan"]["investigation"]["web"]["principal_ids"] = ["bob"]
    elif boundary == "foreign_context":
        invocation = object()
    if boundary == "valid":
        domain, revision = investigation._load_domain(
            local_lab=True, policy=policy, local_context=invocation
        )
        assert domain is web_investigation
        assert revision == "editable:/home/bee/Pro/beescan"
    else:
        with pytest.raises(PermissionError):
            investigation._load_domain(
                local_lab=boundary != "not_lab", policy=policy, local_context=invocation
            )
    assert list(storage.iterdir()) == []


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


def reviewed_dast_fixture(tmp_path, monkeypatch):
    import hashlib
    import os
    from dataclasses import asdict

    from beescan.capabilities.dast import (
        DastEvidence,
        DastExecution,
        DastIntent,
        ExecutionState,
        ScannerMatch,
        ScannerOutcome,
        build_dast_report,
        normalize_dast,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    from beeagent_module.integrations.beescan.case_state import load_case, save_case
    from beeagent_module.integrations.beescan.dast import _api, _plain

    settings, storage, app = setup_app(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    case_id, child = "web-review-case", "dast-review-child"
    now = datetime.now(UTC) - timedelta(seconds=30)
    intent = DastIntent(
        Project("p", "Laboratory fixture"),
        Target("t", "p", TargetKind.URL, "http://127.0.0.1:18080"),
        EngagementScope(
            "s",
            "p",
            ("t",),
            "fixture-authorization",
            valid_from=now,
            expires_at=now + timedelta(minutes=5),
            approved_methods=("active_dast",),
            max_requests=10,
            max_seconds=60,
        ),
        Mission("m", "p", "s", ("web.dast",)),
        case_id,
        child,
        "zap",
        "2.17.0",
        "rule6-v1",
        ("6",),
        ("check",),
        10,
        60,
        now,
    )
    evidence_record = {
        "schema_version": 1,
        "run_id": child,
        "intent_id": intent.identity,
        "requests": [
            {
                "request_sha256": "b" * 64,
                "response_sha256": "c" * 64,
                "status_code": 200,
            }
        ],
    }
    raw = json.dumps(evidence_record).encode()
    evidence = DastEvidence(
        "automated", hashlib.sha256(raw).hexdigest(), "b" * 64, "c" * 64
    )
    execution = DastExecution(
        intent.identity,
        child,
        "zap",
        "2.17.0",
        "rule6-v1",
        ("6",),
        ExecutionState.COMPLETE,
        ("check",),
        (evidence,),
        1,
        True,
        now + timedelta(seconds=1),
    )
    outcome = ScannerOutcome(
        intent.identity,
        child,
        "zap",
        "2.17.0",
        "rule6-v1",
        ("6",),
        (ScannerMatch("6", "check", evidence),),
    )
    finding_id = normalize_dast(intent, execution, outcome).findings[0].finding_id
    parent_api = _api(storage, case_id, logging.getLogger("fixture"))
    child_api = _api(storage, child, logging.getLogger("fixture"))
    report = build_dast_report(intent, execution, outcome)
    child_api.write_text("dast_evidence.json", raw.decode())
    for name, record in (
        (
            "dast_handoff.json",
            {
                "intent": _plain(intent),
                "execution": _plain(execution),
                "outcome": _plain(outcome),
            },
        ),
        ("egress_lifecycle.json", {"state": "closed", "cleanup_verified": True}),
        (
            "investigation_status.json",
            {
                "status": "CANDIDATE",
                "complete": True,
                "request_count": 1,
                "reason": "completed",
            },
        ),
        (
            "investigation_result.json",
            {
                "findings": [
                    asdict(normalize_dast(intent, execution, outcome).findings[0])
                ]
            },
        ),
    ):
        child_api.write_text(name, json.dumps(record))
    child_api.write_text("report.json", report.canonical_json)
    child_api.write_text("report.md", report.markdown)
    child_api.write_text("investigation_steps.json", "[]")
    parent_api.write_text(
        "investigation_status.json",
        json.dumps(
            {
                "status": "CANDIDATE",
                "complete": True,
                "request_count": 1,
                "reason": "completed",
            }
        ),
    )
    save_case(
        parent_api,
        {
            "schema_version": 3,
            "case_id": case_id,
            "origin": intent.target.locator,
            "operator_uid": os.getuid(),
            "segments": [child],
            "pending": False,
            "status": "CANDIDATE",
            "approval_identity": "a" * 64,
        },
    )
    actor = {"user_id": "alice", "role": "operator"}
    task = web.validate_task(
        {"target": intent.target.locator, "task": "Inspect"},
        settings["beescan"]["investigation"],
    )
    invocation = web._WebInvocation(
        service, actor, task, "standard", child, case_id, web._SEAL
    )
    invocation.bind(parent_api, case_id)
    invocation.bind(child_api, child)
    for path in storage.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    _, snapshot = load_case(storage, case_id)
    web._persist(parent_api, "web_receipt.json", service._receipt(snapshot, settings))
    return settings, storage, app, case_id, finding_id


def web_review_payload(case_id, finding_id):
    from beeagent_module.integrations.beescan.review import ATTESTATION

    return {
        "case_id": case_id,
        "finding_id": finding_id,
        "disposition": "verified",
        "decision_basis": "Independent synthetic fixture review",
        "evidence_text": "Independent reviewer fixture observation of a controlled response",
        "independence_attestation": ATTESTATION,
    }


def web_report_payload(case_id, finding_id, review_id, *, complete=False):
    return {
        "case_id": case_id,
        "finding_id": finding_id,
        "review_id": review_id,
        "prerequisites": ["Authorized laboratory"] if complete else [],
        "reproduction_steps": ["Use the independently recorded laboratory procedure"]
        if complete
        else [],
        "expected_behavior": "Refuse access" if complete else None,
        "observed_behavior": "Controlled file access" if complete else None,
        "impact": "Read controlled fixture data" if complete else None,
        "remediation": "Restrict path resolution",
        "program_requirements": "Laboratory rules checked" if complete else None,
        "reproduction_confirmed": complete,
        "impact_confirmed": complete,
        "program_confirmed": complete,
    }


def test_web_review_report_export_restart_and_immutable_source(tmp_path, monkeypatch):
    from beeagent_module.integrations.beescan.review import inspect_web_reports

    settings, storage, app, case_id, finding_id = reviewed_dast_fixture(
        tmp_path, monkeypatch
    )
    service = app.state.beeagent_adapter.beescan
    client, headers = authenticated(app)
    before = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    page = client.get("/beescan", params={"tab": "results", "run_id": case_id})
    assert '"action_id": "beescan_review"' in page.text
    data = web_review_payload(case_id, finding_id)
    result = execute(client, headers, data, "beescan_review")
    assert result.json()["ok"], result.text
    review_id = result.json()["data"]["review_id"]
    assert execute(client, headers, data, "beescan_review").json()["ok"] is False
    for complete in (False, True):
        prepared = execute(
            client,
            headers,
            web_report_payload(case_id, finding_id, review_id, complete=complete),
            "beescan_report_prepare",
        )
        assert prepared.json()["ok"], prepared.text
        assert prepared.json()["data"]["submission_eligible"] is complete
    actor = {"user_id": "alice", "role": "operator"}
    status = inspect_web_reports(service, case_id, finding_id, actor)
    assert len(status["reports"]) == 2
    report_run = status["reports"][-1]["report_run_id"]
    record = json.loads(
        (storage / "runs" / review_id / "module-beescan/review_record.json").read_text()
    )
    assert record["host_review"]["reviewer_id"] == "alice"
    before_get = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    query = {
        "case_id": case_id,
        "finding_id": finding_id,
        "report_run_id": report_run,
        "format": "json",
        "download": "true",
    }
    exported = client.get("/api/beescan/report", params=query)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-disposition"].startswith("attachment;")
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["x-content-type-options"] == "nosniff"
    assert (
        client.get(
            "/api/beescan/report", params=[*query.items(), ("format", "markdown")]
        ).status_code
        == 400
    )
    assert exported.json()["review"]["reviewer_id"] == "alice"
    assert data["evidence_text"] not in exported.text
    for output in ("markdown", "draft"):
        response = client.get("/api/beescan/report", params={**query, "format": output})
        assert response.status_code == 200
    preview = client.get("/api/beescan/report", params={**query, "download": "false"})
    assert (
        preview.status_code == 200
        and preview.json()["data"]["content"] == exported.text
    )
    page = client.get("/beescan", params={"tab": "results", "run_id": case_id})
    assert page.status_code == 200, page.text
    assert "beescan_report_prepare" in page.text
    assert data["evidence_text"] not in page.text
    restarted = build_beeui_app(settings, logging.getLogger("restart"), storage)
    restarted.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(
        settings
    )
    restored, _ = authenticated(restarted)
    assert restored.get("/api/beescan/report", params=query).content == exported.content
    assert before_get == {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    assert all(p.read_bytes() == value for p, value in before.items())
    bob, _ = authenticated(app, "bob")
    assert bob.get("/api/beescan/report", params=query).status_code == 403
    for change in (
        {"case_id": "foreign"},
        {"finding_id": "foreign"},
        {"report_run_id": "../secret"},
        {"format": "human_evidence.txt"},
        {"path": "/etc/passwd"},
    ):
        assert client.get(
            "/api/beescan/report", params={**query, **change}
        ).status_code in {400, 403}


@pytest.mark.parametrize("state", ["rejected", "inconclusive"])
def test_web_nonverified_without_evidence(tmp_path, monkeypatch, state):
    _, _, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    data = {
        **web_review_payload(case_id, finding_id),
        "disposition": state,
        "evidence_text": "",
        "independence_attestation": None,
    }
    reviewed = execute(client, headers, data, "beescan_review")
    assert reviewed.json()["ok"], reviewed.text
    result = execute(
        client,
        headers,
        web_report_payload(
            case_id, finding_id, reviewed.json()["data"]["review_id"], complete=True
        ),
        "beescan_report_prepare",
    )
    assert result.json()["ok"], result.text
    assert result.json()["data"]["submission_eligible"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"reviewer_id": "bob"},
        {"reviewer_authenticated": True},
        {"decided_at": "2020"},
        {"finding_id": "foreign"},
        {"case_id": "../private"},
        {"evidence_text": ""},
        {"evidence_text": "x" * 4097},
        {"evidence_text": "\x00"},
        {"evidence_text": "Authorization: Bearer PRIVATE"},
        {"independence_attestation": True},
        {"evidence_text": {"path": "/etc/passwd"}},
        {"disposition": "VERIFIED"},
    ],
)
def test_web_review_input_refusals(tmp_path, monkeypatch, change):
    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    before = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    result = execute(
        client,
        headers,
        {**web_review_payload(case_id, finding_id), **change},
        "beescan_review",
    )
    assert not result.json()["ok"], result.text
    assert before == {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}


@pytest.mark.parametrize("name", ["bob", "viewer", "limited", "outsider"])
def test_web_review_authority_and_csrf(tmp_path, monkeypatch, name):
    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app, name)
    result = execute(
        client, headers, web_review_payload(case_id, finding_id), "beescan_review"
    )
    assert result.status_code == 403 or not result.json()["ok"]
    owner, _ = authenticated(app)
    assert (
        execute(
            owner, {}, web_review_payload(case_id, finding_id), "beescan_review"
        ).status_code
        == 403
    )
    assert not list(storage.glob("runs/wr-*"))


@pytest.mark.parametrize("fault", ["source", "write", "rename", "receipt", "authority"])
def test_web_review_interrupted_publication(tmp_path, monkeypatch, fault):
    from beeagent_module.integrations.beescan import review

    settings, storage, app, case_id, finding_id = reviewed_dast_fixture(
        tmp_path, monkeypatch
    )
    client, headers = authenticated(app)
    original = review._write

    def write(api, fd, name, content):
        result = original(api, fd, name, content)
        if name == "receipt.pending.json":
            if fault == "source":
                (
                    storage / "runs/dast-review-child/module-beescan/dast_evidence.json"
                ).write_text("{}")
            elif fault == "write":
                raise OSError("interrupted")
            elif fault == "rename":
                monkeypatch.setattr(
                    review.os,
                    "replace",
                    lambda *a, **kw: (_ for _ in ()).throw(OSError("interrupted")),
                )
            elif fault == "receipt":
                (api.artifact_dir() / name).write_text("{}")
            else:
                settings["beescan"]["investigation"]["web"]["enabled"] = False
        return result

    monkeypatch.setattr(review, "_write", write)
    result = execute(
        client, headers, web_review_payload(case_id, finding_id), "beescan_review"
    )
    assert not result.json()["ok"], result.text
    assert not list(storage.glob("runs/wr-*/module-beescan/receipt.json"))


def test_candidate_report_and_offline_review_export(tmp_path, monkeypatch):
    import socket

    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.review import inspect_web_reports

    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)

    def denied(*args, **kwargs):
        raise AssertionError("target_network_or_scanner_invocation")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(dast_runner, "run_zap", denied)
    candidate = execute(
        client,
        headers,
        web_report_payload(case_id, finding_id, "", complete=True),
        "beescan_report_prepare",
    )
    assert candidate.json()["ok"], candidate.text
    assert candidate.json()["data"]["submission_eligible"] is False
    reviewed = execute(
        client, headers, web_review_payload(case_id, finding_id), "beescan_review"
    )
    assert reviewed.json()["ok"], reviewed.text
    result = execute(
        client,
        headers,
        web_report_payload(
            case_id, finding_id, reviewed.json()["data"]["review_id"], complete=True
        ),
        "beescan_report_prepare",
    )
    assert result.json()["ok"], result.text
    summaries = inspect_web_reports(
        app.state.beeagent_adapter.beescan,
        case_id,
        finding_id,
        {"user_id": "alice", "role": "operator"},
    )
    assert len(summaries["reports"]) == 2
    report_run = result.json()["data"]["report_run_id"]
    query = {
        "case_id": case_id,
        "finding_id": finding_id,
        "report_run_id": report_run,
        "format": "json",
        "download": "true",
    }
    assert client.get("/api/beescan/report", params=query).status_code == 200


@pytest.mark.parametrize(
    "fault",
    [
        "tamper",
        "missing",
        "symlink",
        "permissions",
        "hardlink",
        "oversize",
        "review_record",
        "source",
        "ownership",
    ],
)
def test_web_report_integrity_refusals(tmp_path, monkeypatch, fault):
    import os

    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    reviewed = execute(
        client, headers, web_review_payload(case_id, finding_id), "beescan_review"
    )
    assert reviewed.json()["ok"], reviewed.text
    review_id = reviewed.json()["data"]["review_id"]
    prepared = execute(
        client,
        headers,
        web_report_payload(case_id, finding_id, review_id),
        "beescan_report_prepare",
    )
    assert prepared.json()["ok"], prepared.text
    run_id = prepared.json()["data"]["report_run_id"]
    path = storage / "runs" / run_id / "module-beescan/vulnerability.json"
    if fault == "missing":
        path.unlink()
    elif fault == "symlink":
        saved = path.with_name("saved.json")
        path.rename(saved)
        path.symlink_to(saved.name)
    elif fault == "permissions":
        path.chmod(0o644)
    elif fault == "hardlink":
        os.link(path, path.with_name("linked.json"))
    elif fault == "oversize":
        path.write_text("x" * 131073)
    elif fault == "review_record":
        (storage / "runs" / review_id / "module-beescan/review_record.json").write_text(
            "{}"
        )
    elif fault == "source":
        (
            storage / "runs/dast-review-child/module-beescan/dast_handoff.json"
        ).write_text("{}")
    elif fault == "ownership":
        (storage / "runs" / case_id / "module-beescan/web_owner.json").write_text("{}")
    else:
        path.write_text("{}")
    query = {
        "case_id": case_id,
        "finding_id": finding_id,
        "report_run_id": run_id,
        "format": "json",
        "download": "true",
    }
    assert client.get("/api/beescan/report", params=query).status_code == 403
    if fault == "missing":
        from beeagent_module.integrations.beescan.review import inspect_web_reports

        with pytest.raises(ValueError):
            inspect_web_reports(
                app.state.beeagent_adapter.beescan,
                case_id,
                finding_id,
                {"user_id": "alice", "role": "operator"},
            )


def test_web_automated_and_claimed_evidence_refusal(tmp_path, monkeypatch):
    import hashlib

    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    data = web_review_payload(case_id, finding_id)
    automated = (
        storage / "runs/dast-review-child/module-beescan/dast_evidence.json"
    ).read_text()
    assert not execute(
        client, headers, {**data, "evidence_text": automated}, "beescan_review"
    ).json()["ok"]
    claim = (
        storage
        / "runs"
        / ("he-" + hashlib.sha256(data["evidence_text"].encode()).hexdigest()[:48])
    )
    claim.mkdir(mode=0o700)
    assert not execute(client, headers, data, "beescan_review").json()["ok"]
    assert not list(storage.glob("runs/wr-*"))


def test_web_details_seeded_fuzz_and_expired_execution_authority(tmp_path, monkeypatch):
    import random

    from beeagent_module.integrations.beescan.review import _web_details

    settings, storage, app, case_id, finding_id = reviewed_dast_fixture(
        tmp_path, monkeypatch
    )
    generator = random.Random(365)
    valid = web_report_payload(case_id, finding_id, "")
    details = {
        key: value
        for key, value in valid.items()
        if key not in {"case_id", "finding_id", "review_id"}
    }
    for _ in range(250):
        key = generator.choice(tuple(details))
        value = generator.choice([{}, 1, [], "\x00", "я" * 16385])
        if key in {"prerequisites", "reproduction_steps"} and value == []:
            continue
        with pytest.raises((ValueError, TypeError)):
            _web_details({**details, key: value})
    settings["beescan"]["investigation"]["approval"]["transport"]["expires_at"] = (
        "2020-01-01T00:00:00+00:00"
    )
    client, headers = authenticated(app)
    response = execute(
        client, headers, web_review_payload(case_id, finding_id), "beescan_review"
    )
    assert response.json()["ok"], response.text


def test_web_review_concurrent_decisions_are_immutable(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from beeagent_module.integrations.beescan.review import execute_web_review

    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    barrier = threading.Barrier(2)

    def submit():
        barrier.wait(timeout=5)
        try:
            return execute_web_review(
                service,
                "beescan_review",
                web_review_payload(case_id, finding_id),
                {"user_id": "alice", "role": "operator"},
            )
        except OSError, ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert sum(value is not None for value in results) == 1
    assert len(list(storage.glob("runs/wr-*/module-beescan/receipt.json"))) == 1


def test_report_interruption_preserves_published_revision(tmp_path, monkeypatch):
    from beeagent_module.integrations.beescan import review

    _, storage, app, case_id, finding_id = reviewed_dast_fixture(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    reviewed = execute(
        client, headers, web_review_payload(case_id, finding_id), "beescan_review"
    )
    assert reviewed.json()["ok"]
    review_id = reviewed.json()["data"]["review_id"]
    initial = execute(
        client,
        headers,
        web_report_payload(case_id, finding_id, review_id),
        "beescan_report_prepare",
    )
    assert initial.json()["ok"]
    before = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    original = review.os.replace

    def fail_after_rename(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError("interrupted_after_publication")

    monkeypatch.setattr(review.os, "replace", fail_after_rename)
    incomplete = execute(
        client,
        headers,
        web_report_payload(case_id, finding_id, review_id, complete=True),
        "beescan_report_prepare",
    )
    assert not incomplete.json()["ok"]
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert len(list(storage.glob("runs/vr-*/module-beescan/receipt.json"))) == 1


@pytest.mark.parametrize(
    "excluded,target,address",
    [
        ("example.com", "https://EXAMPLE.com./", "93.184.216.34"),
        (".example.com", "https://child.example.com", "93.184.216.34"),
        ("*.example.com", "https://example.com", "93.184.216.34"),
        ("93.184.216.34", "https://public.test", "93.184.216.34"),
        ("93.184.216.0/24", "https://public.test", "93.184.216.34"),
        (
            "2606:4700:4700::1111",
            "https://[2606:4700:4700::1111]",
            "2606:4700:4700::1111",
        ),
        ("2606:4700::/32", "https://public.test", "2606:4700:4700::1111"),
    ],
)
def test_target_policy_exclusions_before_execution(
    monkeypatch, excluded, target, address
):
    from beeagent_module.integrations.beescan import http_runner
    from beeagent_module.integrations.beescan.policy import check_web_target

    settings = {"beescan": {"target_policy": {"excluded_targets": [excluded]}}}
    monkeypatch.setattr(http_runner, "resolve_addresses", lambda _: {address})
    with pytest.raises(PermissionError, match="target_excluded"):
        check_web_target(settings, target)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "100.100.100.200",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::1",
        "168.63.129.16",
        "192.0.2.1",
        "224.0.0.1",
        "0.0.0.0",
    ],
)
def test_target_policy_ssrf_and_rebinding(monkeypatch, address):
    from beeagent_module.integrations.beescan import http_runner
    from beeagent_module.integrations.beescan.policy import check_web_target

    settings = {"beescan": {"target_policy": {"excluded_targets": []}}}
    monkeypatch.setattr(
        http_runner, "resolve_addresses", lambda _: {"93.184.216.34", address}
    )
    with pytest.raises(PermissionError, match="internal_destination_denied"):
        check_web_target(settings, "https://public.test", connected_ip="93.184.216.34")


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"excluded_targets": None},
        {"excluded_targets": [1]},
        {"excluded_targets": ["https://example.com"]},
        {"excluded_targets": ["127.1"]},
        {"excluded_targets": ["10.1.2.3/8"]},
        {"excluded_targets": ["*"]},
        {"excluded_targets": [], "approved": True},
    ],
)
def test_target_policy_invalid_configuration(value):
    from beeagent_module.integrations.beescan.policy import target_exclusions

    with pytest.raises(RuntimeError, match="invalid_target_policy"):
        target_exclusions({"beescan": {"target_policy": value}})


def test_server_policy_successive_targets_without_static_approval(
    tmp_path, monkeypatch
):
    from beeagent_module.integrations.beescan import http_runner

    settings, storage, app = setup_app(tmp_path, monkeypatch)
    settings["beescan"]["target_policy"] = {
        "excluded_targets": ["hidden-denylist.test"]
    }
    settings["beescan"]["investigation"].update(
        approval=None, trusted_local_enabled=False
    )
    settings["beescan"]["dast"].update(enabled=True, approval=None)
    service = app.state.beeagent_adapter.beescan
    monkeypatch.setattr(http_runner, "resolve_addresses", lambda _: {"93.184.216.34"})
    seen = []

    def run(**kwargs):
        invocation = kwargs["web_invocation"]
        invocation.verify()
        assert kwargs.get("local_operator") is None
        active = kwargs["settings"]["beescan"]["dast"]["approval"]
        assert active["profile"] == "traversal-nonrecursive-v1"
        assert active["transport"]["origin"] == invocation.task.target
        seen.append(invocation.task.target)
        return {}

    monkeypatch.setattr(web, "execute_investigation", run)
    client, headers = authenticated(app)
    baseline = deepcopy(settings)
    for target in ("https://FIRST.example/", "https://second.example"):
        data = {
            **payload(app),
            "target": target,
            "task": "Assess Path Traversal",
            "mode": "standard",
        }
        result = execute(client, headers, data)
        assert result.json()["ok"], result.text
        service.executor.submit(lambda: None).result(timeout=5)
    assert seen == ["https://first.example", "https://second.example"]
    assert settings == baseline
    from beeagent_module.integrations.beescan.dast import _current
    from beeagent_module.integrations.beescan.policy import check_web_target

    context = web._WebInvocation(
        service,
        {"user_id": "alice", "role": "operator"},
        web.validate_task(
            {"target": "https://second.example", "task": "Inspect"},
            settings["beescan"]["investigation"],
        ),
        "standard",
        "web-trust-test",
        "web-trust-test",
        web._SEAL,
    )
    effective = context.effective_settings()
    with pytest.raises(PermissionError, match="active_dast_not_approved"):
        _current(effective)
    assert (
        _current(effective, web_invocation=context).profile
        == "traversal-nonrecursive-v1"
    )
    monkeypatch.setattr(http_runner, "resolve_addresses", lambda _: {"1.1.1.1"})
    with pytest.raises(PermissionError, match="dns_changed"):
        context.verify()
    monkeypatch.setattr(
        http_runner, "resolve_addresses", lambda _: {"93.184.216.34", "1.1.1.1"}
    )
    settings["beescan"]["target_policy"]["excluded_targets"].append("1.1.1.0/24")
    with pytest.raises(PermissionError, match="target_excluded"):
        check_web_target(
            settings, "https://second.example", connected_ip="93.184.216.34"
        )
    settings["beescan"]["target_policy"]["excluded_targets"].pop()
    monkeypatch.setattr(http_runner, "resolve_addresses", lambda _: {"93.184.216.34"})
    page = client.get("/beescan?lang=en")
    assert page.status_code == 200
    submit = page.text.split('id="beescan-submit"', 1)[1].split(">", 1)[0]
    assert "disabled" not in submit
    assert "Current approval" not in page.text
    assert "hidden-denylist.test" not in page.text
    blocked = execute(
        client, headers, {**payload(app), "target": "https://hidden-denylist.test"}
    )
    assert blocked.json()["ok"] and blocked.json()["data"]["status"] == "REFUSED"
    assert "hidden-denylist.test" not in blocked.text
    refused_id = blocked.json()["data"]["run_id"]
    refusal = client.get("/api/beescan/status", params={"run_id": refused_id})
    assert refusal.json()["data"]["reason"] == "target_excluded"
    assert refusal.json()["data"]["request_count"] == 0
    unsupported = execute(
        client,
        headers,
        {
            **payload(app),
            "target": "http://public.example",
            "task": "Assess Path Traversal",
            "mode": "standard",
        },
    )
    assert (
        unsupported.json()["ok"] and unsupported.json()["data"]["status"] == "REFUSED"
    )
    unsupported_view = client.get(
        "/api/beescan/status", params={"run_id": unsupported.json()["data"]["run_id"]}
    )
    assert unsupported_view.json()["data"]["reason"] == "web_dast_profile_unsupported"
    assert seen == ["https://first.example", "https://second.example"]
    assert not execute(
        client,
        headers,
        {
            **payload(app),
            "target": "https://hidden-denylist.test",
            "nonce": data["nonce"],
        },
    ).json()["ok"]
    before = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    viewer, viewer_headers = authenticated(app, "viewer")
    assert not execute(viewer, viewer_headers, payload(app)).json()["ok"]
    assert before == {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}


def test_target_policy_owner_file_protection(tmp_path):
    from beeagent_module.integrations.beescan.policy import validate_target_policy_file

    path = tmp_path / "settings.yml"
    path.write_text("beescan: {}")
    path.chmod(0o640)
    validate_target_policy_file(path)
    path.chmod(0o666)
    with pytest.raises(RuntimeError, match="insecure_target_policy_configuration"):
        validate_target_policy_file(path)
    path.chmod(0o640)
    link = tmp_path / "linked.yml"
    link.symlink_to(path)
    with pytest.raises(RuntimeError, match="insecure_target_policy_configuration"):
        validate_target_policy_file(link)


def test_target_policy_validation_does_not_require_domain_install(monkeypatch):
    import builtins

    from beeagent_module.integrations.beescan.policy import target_exclusions

    original = builtins.__import__

    def require_host_only(name, *args, **kwargs):
        if name.startswith("beescan"):
            pytest.fail("Bootstrap target policy requires uninstalled domain module")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", require_host_only)
    settings = {
        "beescan": {
            "target_policy": {
                "excluded_targets": ["EXAMPLE.com.", ".example.org", "10.0.0.0/8"]
            }
        }
    }
    assert len(target_exclusions(settings)) == 3
