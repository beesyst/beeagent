import json
import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from beeagent_module.integrations.beescan import access_control as host
from beeagent_module.integrations.beescan import detection_runner, egress
from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.interfaces.ui.app import build_beeui_app
from tests.beescan_access_support import AccessApplication, make_test_profile
from tests.test_beescan_web import (
    authenticated,
    execute,
    payload,
    setup_app,
    web_report_payload,
    web_review_payload,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "/records/one?token=secret&session=private&key=value#fragment",
            "/records/one",
        ),
        ("/records/one", "/records/one"),
    ],
)
def test_discovery_diagnostic_url_excludes_query_values(value, expected):
    from beeagent_module.integrations.beescan.access_discovery import (
        diagnostic_relative_url,
    )

    assert diagnostic_relative_url(value) == expected


def prepare(
    tmp_path,
    monkeypatch,
    mode="vulnerable",
    relationship="horizontal",
    application=None,
):
    settings, storage, app = setup_app(tmp_path, monkeypatch)
    application = application or AccessApplication(mode, relationship)
    for name, value in zip(("A", "B"), application.tokens):
        monkeypatch.setenv("BEEAGENT_ACCESS_" + name, value)
    profile = make_test_profile(
        "http://127.0.0.1:18080", relationship, mode == "public"
    )
    settings["beescan"]["access_control"] = {"profiles": [profile]}
    settings["beescan"]["investigation"]["local_lab_enabled"] = True

    class ControlledEgress:
        def __init__(self, policy, *, artifacts, assessment_run_id, seconds):
            self.artifacts = artifacts
            self.run_id = assessment_run_id

        def start(self):
            pass

        def close(self):
            _persist(
                self.artifacts,
                "egress_lifecycle.json",
                {
                    "assessment_run_id": self.run_id,
                    "state": "closed",
                    "cleanup_verified": mode != "cleanup",
                    "enforcement_verified": True,
                },
            )

    def capture(
        policy, *, investigation, authentication, on_attempt, reauthorize, **kwargs
    ):
        reauthorize()
        on_attempt(True)
        status, body = application.get(investigation["relative_url"], authentication)
        return json.dumps(
            {
                "origin": policy.origin,
                "connected_ip": policy.connected_ip,
                "port": policy.port,
                "method": "GET",
                "relative_url": investigation["relative_url"],
                "request_count": 1,
                "status_code": status,
                "content_type": "text/html"
                if type(body) is str
                else "application/json",
                "body": body if type(body) is str else json.dumps(body),
                "complete": True,
            }
        ).encode()

    monkeypatch.setattr(egress, "ManagedEgress", ControlledEgress)
    monkeypatch.setattr(detection_runner, "run_detection_provider", capture)
    return settings, storage, app, application


@pytest.mark.parametrize("relationship", ["horizontal", "vertical"])
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("vulnerable", "CANDIDATE"),
        ("denial_disclosure", "CANDIDATE"),
        ("anonymous_disclosure", "PARTIAL"),
        ("fixed", "NO_MATCH"),
        ("public", "NO_MATCH"),
        ("ambiguous", "PARTIAL"),
        ("expired", "REFUSED"),
        ("substituted", "REFUSED"),
        ("cleanup", "PARTIAL"),
        ("missing_private", "PARTIAL"),
    ],
)
def test_protected_comparison_and_reports(
    tmp_path, monkeypatch, relationship, mode, expected
):
    settings, storage, app, target = prepare(tmp_path, monkeypatch, mode, relationship)
    client, headers = authenticated(app)
    service = app.state.beeagent_adapter.beescan
    request = {
        **payload(app),
        "mode": "standard",
        "test_profile_id": "controlled-access",
    }
    started = execute(client, headers, request)
    assert started.json()["ok"], started.text
    case_id = started.json()["data"]["case_id"]
    service.executor.submit(lambda: None).result(timeout=10)
    view = service.inspect(case_id, {"user_id": "alice", "role": "operator"})
    assert view["status"] == expected, view
    assert view["evidence_authenticated"]
    assert view["request_count"] == len(target.requests)
    if mode not in {"expired", "substituted", "missing_private"}:
        assert len(target.requests) == 8
    if expected == "CANDIDATE":
        finding = view["findings"][0]["finding_id"]
        reviewed = execute(
            client, headers, web_review_payload(case_id, finding), "beescan_review"
        )
        assert reviewed.json()["ok"], reviewed.text
        review_id = reviewed.json()["data"]["review_id"]
        report = execute(
            client,
            headers,
            web_report_payload(case_id, finding, review_id, complete=True),
            "beescan_report_prepare",
        )
        assert report.json()["ok"], report.text
        assert report.json()["data"]["submission_eligible"]
        query = {
            "case_id": case_id,
            "finding_id": finding,
            "report_run_id": report.json()["data"]["report_run_id"],
            "format": "json",
            "download": "true",
        }
        exported = client.get("/api/beescan/report", params=query)
        assert exported.status_code == 200
        assert exported.json()["finding_type"] == "access_control"
        assert exported.json()["schema_version"] == 2
        assert (
            client.get(
                "/api/beescan/report", params={**query, "format": "markdown"}
            ).status_code
            == 200
        )
        bob, bob_headers = authenticated(app, "bob")
        assert bob.get("/api/beescan/report", params=query).status_code == 403
        assert not execute(
            bob,
            bob_headers,
            web_report_payload(case_id, finding, review_id),
            "beescan_report_prepare",
        ).json()["ok"]
        restarted = build_beeui_app(settings, logging.getLogger("restart"), storage)
        restarted.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(
            settings
        )
        restored, _ = authenticated(restarted)
        assert (
            restored.get("/api/beescan/report", params=query).content
            == exported.content
        )
        assert len(target.requests) == 8
        assert (
            client.get(
                "/beescan", params={"tab": "results", "run_id": case_id}
            ).status_code
            == 200
        )
        resumed = execute(
            client,
            headers,
            {
                **request,
                "case_id": case_id,
                "nonce": service.nonce({"user_id": "alice", "role": "operator"}),
            },
            "beescan_resume",
        )
        assert resumed.json()["ok"] and resumed.json()["data"]["reused"], resumed.text
        monkeypatch.setenv("BEEAGENT_ACCESS_B", "rotated-credential")
        refused = execute(
            client,
            headers,
            {
                **request,
                "case_id": case_id,
                "nonce": service.nonce({"user_id": "alice", "role": "operator"}),
            },
            "beescan_resume",
        )
        assert not refused.json()["ok"]
        assert len(target.requests) == 8
    else:
        assert not view["findings"]
    for path in storage.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert all(token not in text for token in target.tokens)
            assert all(obj["private"] not in text for obj in target.objects)
            assert "Authorization:" not in text
    service.executor.shutdown(wait=True)


@pytest.mark.parametrize(
    "fault", ["rotation", "dns", "timeout", "cancel", "malformed", "inexact"]
)
def test_interrupted_comparison_preserves_accounting(tmp_path, monkeypatch, fault):
    settings, storage, app, target = prepare(tmp_path, monkeypatch)
    original = detection_runner.run_detection_provider

    def interrupted(policy, **kwargs):
        if len(target.requests) == 4:
            if fault == "rotation":
                monkeypatch.setenv("BEEAGENT_ACCESS_A", "rotated")
                kwargs["reauthorize"]()
            if fault == "dns":
                from beeagent_module.integrations.beescan import http_runner

                monkeypatch.setattr(
                    http_runner, "resolve_addresses", lambda _: {"192.0.2.2"}
                )
                kwargs["reauthorize"]()
            if fault == "timeout":
                raise TimeoutError("timeout")
            if fault == "cancel":
                raise KeyboardInterrupt
            if fault == "inexact":
                kwargs["on_attempt"](None)
            raise ValueError("malformed_capture")
        return original(policy, **kwargs)

    monkeypatch.setattr(detection_runner, "run_detection_provider", interrupted)
    client, headers = authenticated(app)
    started = execute(
        client,
        headers,
        {**payload(app), "mode": "standard", "test_profile_id": "controlled-access"},
    )
    assert started.json()["ok"]
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=10)
    view = service.inspect(
        started.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert view["status"] in {"REFUSED", "TIMEOUT", "ERROR"}
    assert view["request_count"] == len(target.requests) == 4
    assert not view["request_count_exact"]
    assert not view["findings"]


@pytest.mark.parametrize(
    "fault",
    ["source_response_id", "session_id", "response_sha256", "receipt", "case_id"],
)
def test_authenticated_evidence_tamper_refused(tmp_path, monkeypatch, fault):
    settings, storage, app, target = prepare(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    started = execute(
        client,
        headers,
        {**payload(app), "mode": "standard", "test_profile_id": "controlled-access"},
    )
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=10)
    case_id = started.json()["data"]["case_id"]
    root = storage / "runs" / case_id / "module-beescan"
    if fault == "receipt":
        path = root / "web_receipt.json"
        record = json.loads(path.read_text())
        record["signature"] = "0" * 64
    elif fault == "case_id":
        path = root / "case.json"
        record = json.loads(path.read_text())
        record["state"]["case_id"] = "foreign"
        record["sha256"] = host.digest(record["state"])
    else:
        path = root / "access_control.json"
        record = json.loads(path.read_text())
        record["execution"]["evidence"][5][fault] = (
            "f" * 64 if fault == "response_sha256" else "foreign"
        )
    path.write_text(json.dumps(record))
    with pytest.raises((ValueError, PermissionError)):
        service.inspect(case_id, {"user_id": "alice", "role": "operator"})
    assert len(target.requests) == 8


def test_csrf_principal_budget_and_unknown_ownership(tmp_path, monkeypatch):
    settings, storage, app, target = prepare(tmp_path, monkeypatch)
    client, headers = authenticated(app)
    request = {
        **payload(app),
        "mode": "standard",
        "test_profile_id": "controlled-access",
    }
    assert execute(client, {}, request).status_code == 403
    for actor in ("viewer", "limited", "bob"):
        other, other_headers = authenticated(app, actor)
        nonce = app.state.beeagent_adapter.beescan.nonce(
            {"user_id": actor, "role": "viewer" if actor == "viewer" else "operator"}
        )
        assert not execute(other, other_headers, {**request, "nonce": nonce}).json()[
            "ok"
        ]
    settings["beescan"]["investigation"]["adaptive"]["max_requests"] = 7
    assert not execute(client, headers, request).json()["ok"]
    assert target.requests == []
    settings["beescan"]["investigation"]["adaptive"]["max_requests"] = 20
    settings["beescan"]["access_control"]["profiles"][0]["resource"][
        "expected_access"
    ] = None
    started = execute(client, headers, request)
    assert started.json()["ok"]
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=10)
    view = service.inspect(
        started.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert view["status"] == "PARTIAL" and not view["findings"]
    assert len(target.requests) == 5


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing",
        "origin",
        "expired",
        "operator",
        "ownership",
        "unknown_profile",
        "quick",
    ],
)
def test_authority_refuses_before_target(tmp_path, monkeypatch, change):
    settings, storage, app, target = prepare(tmp_path, monkeypatch)
    profile = settings["beescan"]["access_control"]["profiles"][0]
    request = {
        **payload(app),
        "mode": "standard",
        "test_profile_id": "controlled-access",
    }
    if change == "duplicate":
        monkeypatch.setenv("BEEAGENT_ACCESS_B", target.tokens[0])
    elif change == "missing":
        monkeypatch.delenv("BEEAGENT_ACCESS_B")
    elif change == "origin":
        request["target"] = "https://other.test"
    elif change == "expired":
        profile["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    elif change == "operator":
        profile["operator_ids"] = ["bob"]
    elif change == "ownership":
        profile["resource"]["owner_id"] = "foreign"
    elif change == "unknown_profile":
        request["test_profile_id"] = "unknown"
    else:
        request["mode"] = "quick"
    client, headers = authenticated(app)
    assert not execute(client, headers, request).json()["ok"]
    assert target.requests == []


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        True,
        {"profiles": None},
        {"profiles": [None]},
        {"profiles": [True]},
        {"profiles": [{}]},
    ],
)
def test_profile_fuzz_refusal(value):
    with pytest.raises(RuntimeError):
        host.validate_access_settings({"beescan": {"access_control": value}})


@pytest.mark.parametrize("value", [None, False, 0, [], {}])
def test_malformed_profile_selection_has_no_fallback(tmp_path, monkeypatch, value):
    _, _, app, target = prepare(tmp_path, monkeypatch)
    service = app.state.beeagent_adapter.beescan
    with pytest.raises(ValueError):
        service.start(
            "beescan_start",
            {**payload(app), "mode": "standard", "test_profile_id": value},
            {"user_id": "alice", "role": "operator"},
        )
    assert not target.requests


def test_comparison_obeys_current_capture_limits(tmp_path, monkeypatch):
    import time

    settings, _, app, _ = prepare(tmp_path, monkeypatch)
    settings["beescan"]["investigation"].update(body_bytes_max=1024, timeout_seconds=2)
    original = detection_runner.run_detection_provider
    observed = []

    def bounded(policy, **kwargs):
        observed.append(
            (
                kwargs["investigation"]["body_bytes_max"],
                kwargs["deadline"] - time.monotonic(),
            )
        )
        return original(policy, **kwargs)

    monkeypatch.setattr(detection_runner, "run_detection_provider", bounded)
    service = app.state.beeagent_adapter.beescan
    service.start(
        "beescan_start",
        {**payload(app), "mode": "standard", "test_profile_id": "controlled-access"},
        {"user_id": "alice", "role": "operator"},
    )
    service.executor.submit(lambda: None).result(timeout=10)
    assert observed and all(size == 1024 and seconds <= 2 for size, seconds in observed)


@pytest.mark.parametrize("exclusion", ["127.0.0.1", "127.0.0.0/8"])
def test_local_profile_cannot_override_server_exclusion(
    tmp_path, monkeypatch, exclusion
):
    settings, _, app, target = prepare(tmp_path, monkeypatch)
    settings["beescan"]["target_policy"] = {"excluded_targets": [exclusion]}
    client, headers = authenticated(app)
    result = execute(
        client,
        headers,
        {**payload(app), "mode": "standard", "test_profile_id": "controlled-access"},
    )
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=10)
    assert not result.json()["ok"] or result.json()["data"]["status"] == "REFUSED"
    assert not target.requests


def test_skipped_denial_body_cannot_complete_negative(tmp_path, monkeypatch):
    _, _, app, _ = prepare(tmp_path, monkeypatch, "fixed")
    original = detection_runner.run_detection_provider

    def skipped(policy, **kwargs):
        capture = json.loads(original(policy, **kwargs))
        if capture["status_code"] == 403:
            capture.pop("body")
            capture.pop("content_type")
            capture["skip_reason"] = "unsupported_response_type"
        return json.dumps(capture).encode()

    monkeypatch.setattr(detection_runner, "run_detection_provider", skipped)
    service = app.state.beeagent_adapter.beescan
    result = service.start(
        "beescan_start",
        {**payload(app), "mode": "standard", "test_profile_id": "controlled-access"},
        {"user_id": "alice", "role": "operator"},
    )
    service.executor.submit(lambda: None).result(timeout=10)
    assert (
        service.inspect(result["case_id"], {"user_id": "alice", "role": "operator"})[
            "status"
        ]
        == "PARTIAL"
    )


@pytest.mark.parametrize("relationship", ["horizontal", "vertical"])
@pytest.mark.parametrize("alternate", [False, True])
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("vulnerable", "CANDIDATE"),
        ("fixed", "NO_MATCH"),
        ("public", "NO_MATCH"),
        ("ambiguous", "PARTIAL"),
        ("no_owner", "PARTIAL"),
        ("html", "CANDIDATE"),
        ("login", "PARTIAL"),
        ("multiple", "CANDIDATE"),
        ("expired", "REFUSED"),
        ("substituted", "PARTIAL"),
    ],
)
def test_autonomous_discovery_workflow(
    tmp_path, monkeypatch, relationship, alternate, mode, expected
):
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile

    target = AutonomousApplication(mode, relationship, alternate)
    settings, storage, app, _ = prepare(tmp_path, monkeypatch, application=target)
    settings["beescan"]["access_control"]["profiles"] = [
        autonomous_profile("http://127.0.0.1:18080", relationship)
    ]
    settings["beescan"]["investigation"]["timeout_seconds"] = 60
    client, headers = authenticated(app)
    service = app.state.beeagent_adapter.beescan
    request = {**payload(app), "mode": "deep", "test_profile_id": "controlled-access"}
    start = execute(client, headers, request)
    assert start.json()["ok"], start.text
    case_id = start.json()["data"]["case_id"]
    service.executor.submit(lambda: None).result(timeout=20)
    view = service.inspect(case_id, {"user_id": "alice", "role": "operator"})
    assert view["status"] == expected, view
    assert view["evidence_authenticated"]
    assert view["request_count"] == len(target.requests) <= 20
    root = storage / "runs" / case_id / "module-beescan"
    state = json.loads((root / "case.json").read_text())["state"]
    assert state["schema_version"] == 6
    if mode == "multiple":
        assert len(state["comparisons"]) == 2
        assert len(target.requests) == 20
    if expected == "CANDIDATE":
        finding = view["findings"][0]["finding_id"]
        reviewed = execute(
            client, headers, web_review_payload(case_id, finding), "beescan_review"
        )
        assert reviewed.json()["ok"], reviewed.text
        report = execute(
            client,
            headers,
            web_report_payload(
                case_id, finding, reviewed.json()["data"]["review_id"], complete=True
            ),
            "beescan_report_prepare",
        )
        assert report.json()["ok"], report.text
        query = {
            "case_id": case_id,
            "finding_id": finding,
            "report_run_id": report.json()["data"]["report_run_id"],
            "format": "json",
            "download": "true",
        }
        downloaded = client.get("/api/beescan/report", params=query)
        assert (
            downloaded.status_code == 200 and downloaded.json()["submission_eligible"]
        )
        before = len(target.requests)
        restarted = build_beeui_app(settings, logging.getLogger("restart"), storage)
        restarted.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(
            settings
        )
        restored, _ = authenticated(restarted)
        assert (
            restored.get("/api/beescan/report", params=query).content
            == downloaded.content
        )
        assert len(target.requests) == before
    for path in storage.rglob("*"):
        if path.is_file():
            assert all(token not in path.read_text() for token in target.tokens)
            assert all(
                str(body.get("private", "never-present-value")) not in path.read_text()
                for _, _, _, body in target.resources
            )
    service.executor.shutdown(wait=True)


@pytest.mark.parametrize(
    "mode,expected_count", [("quick", 2), ("standard", 12), ("deep", 20)]
)
def test_autonomous_effort_and_unknown_authorization(
    tmp_path, monkeypatch, mode, expected_count
):
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile

    target = AutonomousApplication("multiple")
    settings, _, app, _ = prepare(tmp_path, monkeypatch, application=target)
    profile = autonomous_profile("http://127.0.0.1:18080")
    settings["beescan"]["access_control"]["profiles"] = [profile]
    client, headers = authenticated(app)
    service = app.state.beeagent_adapter.beescan
    started = execute(
        client,
        headers,
        {**payload(app), "mode": mode, "test_profile_id": profile["profile_id"]},
    )
    assert started.json()["ok"]
    service.executor.submit(lambda: None).result(timeout=20)
    view = service.inspect(
        started.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert len(target.requests) == view["request_count"] == expected_count
    assert view["status"] == ("CANDIDATE" if mode == "deep" else "PARTIAL")
    profile["expectation"] = "unknown"
    before = len(target.requests)
    started = execute(
        client,
        headers,
        {**payload(app), "mode": "deep", "test_profile_id": profile["profile_id"]},
    )
    service.executor.submit(lambda: None).result(timeout=20)
    view = service.inspect(
        started.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert view["status"] == "PARTIAL"
    assert len(target.requests) - before == 4
    assert view["reason"] == "authorization_expectation_required"
    service.executor.shutdown(wait=True)


def test_autonomous_html_json_links_and_source_limits():
    from beeagent_module.integrations.beescan.access_discovery import observe, safe_link

    principal = {"account_id": "account-a", "role": "user"}
    identity, objects, links = observe(
        '<a href="/api"></a><form method="get" action="/read">'
        '<input name="id" value="123"></form>'
        '<form method="post" action="/write"></form>'
        '<a href="https://foreign.test/private">bad</a>',
        "text/html",
        "https://app.test",
        "/",
        principal,
    )
    assert identity is None and not objects and links == ["/api", "/read?id=123"]
    _, _, links = observe(
        '<link rel="stylesheet" href="/static/app.css"><a href="/api">API</a>',
        "text/html",
        "https://app.test",
        "/",
        principal,
    )
    assert links == ["/api"]
    for path in (
        "/delete?id=1",
        "/read?token=value",
        "https://foreign.test/path",
        "/../private",
        "/read?id=1&id=2",
    ):
        assert safe_link("https://app.test", "/", path) is None
    _, _, links = observe(
        json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/inventory": {"get": {"x-readOnly": True}},
                    "/write": {"post": {}},
                    "/objects/{id}": {"get": {"x-readOnly": True}},
                },
            }
        ),
        "application/json",
        "https://app.test",
        "/",
        principal,
    )
    assert links == ["/inventory"]
    with pytest.raises(ValueError):
        observe(
            json.dumps({"items": [{}] * 33}),
            "application/json",
            "https://app.test",
            "/",
            principal,
        )


@pytest.mark.parametrize(
    "fault", ["rotation", "dns", "timeout", "cancel", "response_length", "cleanup"]
)
def test_autonomous_failure_accounting(tmp_path, monkeypatch, fault):
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile

    target = AutonomousApplication()
    settings, _, app, _ = prepare(
        tmp_path,
        monkeypatch,
        mode="cleanup" if fault == "cleanup" else "vulnerable",
        application=target,
    )
    settings["beescan"]["access_control"]["profiles"] = [
        autonomous_profile("http://127.0.0.1:18080")
    ]
    original = detection_runner.run_detection_provider

    def interrupted(policy, **kwargs):
        if len(target.requests) == 1:
            if fault == "rotation":
                monkeypatch.setenv("BEEAGENT_ACCESS_A", "rotated")
                kwargs["reauthorize"]()
            if fault == "dns":
                from beeagent_module.integrations.beescan import http_runner

                monkeypatch.setattr(
                    http_runner, "resolve_addresses", lambda _: {"192.0.2.2"}
                )
                kwargs["reauthorize"]()
            if fault == "timeout":
                raise TimeoutError
            if fault == "cancel":
                raise KeyboardInterrupt
        result = original(policy, **kwargs)
        if fault == "response_length" and len(target.requests) == 1:
            from beeagent_module.integrations.beescan.capture_worker import (
                ResponseLengthExceeded,
            )

            raise ResponseLengthExceeded(1000000)
        return result

    monkeypatch.setattr(detection_runner, "run_detection_provider", interrupted)
    client, headers = authenticated(app)
    start = execute(
        client,
        headers,
        {**payload(app), "mode": "deep", "test_profile_id": "controlled-access"},
    )
    assert start.json()["ok"]
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=20)
    view = service.inspect(
        start.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert view["status"] in {"REFUSED", "TIMEOUT", "ERROR"}
    assert not view["findings"]
    assert view["request_count"] == len(target.requests)
    assert len(target.requests) == (4 if fault == "cleanup" else 1)
    service.executor.shutdown(wait=True)


@pytest.mark.parametrize(
    "fault", ["session", "source", "hypothesis", "receipt", "foreign_operator"]
)
def test_autonomous_provenance_refuses_substitution(tmp_path, monkeypatch, fault):
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile

    target = AutonomousApplication()
    settings, storage, app, _ = prepare(tmp_path, monkeypatch, application=target)
    settings["beescan"]["access_control"]["profiles"] = [
        autonomous_profile("http://127.0.0.1:18080")
    ]
    client, headers = authenticated(app)
    start = execute(
        client,
        headers,
        {**payload(app), "mode": "standard", "test_profile_id": "controlled-access"},
    )
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=20)
    case = start.json()["data"]["case_id"]
    actor = {"user_id": "alice", "role": "operator"}
    root = storage / "runs" / case / "module-beescan"
    if fault == "foreign_operator":
        actor["user_id"] = "bob"
    else:
        name = (
            "web_receipt.json"
            if fault == "receipt"
            else "case.json"
            if fault == "hypothesis"
            else "discovery_evidence.json"
        )
        path = root / name
        data = json.loads(path.read_text())
        if fault == "receipt":
            data["signature"] = "0" * 64
        elif fault == "hypothesis":
            data["state"]["hypotheses"][0]["owner"]["object_ref"] = "foreign"
            data["sha256"] = host.digest(data["state"])
        else:
            data["objects"][0]["session_id" if fault == "session" else "source_ref"] = (
                "foreign"
            )
        path.write_text(json.dumps(data))
    with pytest.raises((PermissionError, ValueError, KeyError)):
        service.inspect(case, actor)
    assert len(target.requests) == 12
    service.executor.shutdown(wait=True)


def test_public_directory_is_not_identity_proof():
    from beeagent_module.integrations.beescan.access_discovery import observe

    body = {
        "directory": {
            "first": {"id": "account-a", "role": "user"},
            "second": {"id": "account-b", "role": "user"},
        }
    }
    for name in ("a", "b"):
        identity, _, _ = observe(
            json.dumps(body),
            "application/json",
            "https://app.test",
            "/",
            {"account_id": "account-" + name, "role": "user"},
        )
        assert identity is None


def test_autonomous_step_ceiling_stops_before_comparison(tmp_path, monkeypatch):
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile

    target = AutonomousApplication()
    settings, _, app, _ = prepare(tmp_path, monkeypatch, application=target)
    settings["beescan"]["access_control"]["profiles"] = [
        autonomous_profile("http://127.0.0.1:18080")
    ]
    settings["beescan"]["investigation"]["adaptive"]["max_steps"] = 2
    client, headers = authenticated(app)
    start = execute(
        client,
        headers,
        {**payload(app), "mode": "deep", "test_profile_id": "controlled-access"},
    )
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=10)
    view = service.inspect(
        start.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert view["status"] == "PARTIAL" and len(target.requests) == 2
    service.executor.shutdown(wait=True)


def test_autonomous_discovery_excludes_known_foreign_objects(tmp_path, monkeypatch):
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile

    target = AutonomousApplication("fixed")
    original = target.get

    def response(path, credential):
        status, body = original(path, credential)
        if path == "/":
            body["resources"].append(
                {
                    "id": "foreign-object",
                    "owner_id": "third-party",
                    "href": "/third-party-private",
                    "private": "not-retained-foreign-data",
                }
            )
        return status, body

    target.get = response
    settings, _, app, _ = prepare(tmp_path, monkeypatch, application=target)
    settings["beescan"]["access_control"]["profiles"] = [
        autonomous_profile("http://127.0.0.1:18080")
    ]
    client, headers = authenticated(app)
    start = execute(
        client,
        headers,
        {**payload(app), "mode": "deep", "test_profile_id": "controlled-access"},
    )
    service = app.state.beeagent_adapter.beescan
    service.executor.submit(lambda: None).result(timeout=20)
    view = service.inspect(
        start.json()["data"]["case_id"], {"user_id": "alice", "role": "operator"}
    )
    assert view["status"] == "PARTIAL"
    assert all(path != "/third-party-private" for path, _ in target.requests)
    service.executor.shutdown(wait=True)
