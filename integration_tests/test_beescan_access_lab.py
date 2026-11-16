import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import asdict

import pytest
from test_beescan_egress_lab import approved as approved
from test_beescan_egress_lab import managed_lab as managed_lab

from beeagent_module.integrations.beescan.investigation import InvestigationPolicy
from beeagent_module.interfaces.ui.app import build_beeui_app
from tests.beescan_access_support import (
    AccessApplication,
    AutonomousApplication,
    autonomous_profile,
    make_test_profile,
)
from tests.test_beescan_web import (
    authenticated,
    execute,
    web_report_payload,
    web_review_payload,
    web_settings,
)


@pytest.fixture
def access_application(monkeypatch, request):
    mode = request.node.callspec.params["managed_lab"].removeprefix("access-")
    relationship = request.node.callspec.params["relationship"]
    app = (
        AutonomousApplication(
            mode.removeprefix("auto-"),
            relationship,
            request.node.callspec.params.get("alternate", False),
        )
        if mode.startswith("auto-")
        else AccessApplication(mode, relationship)
    )
    for name, value in zip(("A", "B"), app.tokens):
        monkeypatch.setenv("BEEAGENT_ACCESS_" + name, value)
    return app


@pytest.mark.parametrize(
    "managed_lab,expected",
    [
        ("access-vulnerable", "CANDIDATE"),
        ("access-denial_disclosure", "CANDIDATE"),
        ("access-anonymous_disclosure", "PARTIAL"),
        ("access-fixed", "NO_MATCH"),
        ("access-public", "NO_MATCH"),
        ("access-ambiguous", "PARTIAL"),
        ("access-expired", "REFUSED"),
        ("access-substituted", "REFUSED"),
        ("access-redirect", "ERROR"),
        ("access-missing_private", "PARTIAL"),
    ],
    indirect=["managed_lab"],
)
@pytest.mark.parametrize("relationship", ["horizontal", "vertical"])
def test_real_authenticated_web_workflow(
    managed_lab, access_application, monkeypatch, relationship, expected
):
    _, root, requests, sessions, probe = managed_lab
    settings = web_settings(monkeypatch)
    approval = asdict(
        InvestigationPolicy(probe, True, True, True, "GET", "numeric_invalid_v1", 3)
    )
    for name in ("valid_from", "expires_at"):
        approval["transport"][name] = approval["transport"][name].isoformat()
    settings["beescan"]["investigation"].update(
        approval=approval, local_lab_enabled=True
    )
    profile = make_test_profile(
        probe.origin, relationship, access_application.mode == "public"
    )
    settings["beescan"]["access_control"] = {"profiles": [profile]}
    storage = root / "access-web-storage"
    storage.mkdir(mode=0o700)
    app = build_beeui_app(settings, logging.getLogger("managed-lab"), storage)
    service = app.state.beeagent_adapter.beescan
    service.reload_settings = lambda: deepcopy(settings)
    client, headers = authenticated(app)
    page = client.get("/beescan")
    assert page.status_code == 200 and "test_profile_id" in page.text
    actor = {"user_id": "alice", "role": "operator"}
    payload = {
        "target": probe.origin,
        "task": "Assess approved access boundaries",
        "mode": "standard",
        "nonce": service.nonce(actor),
        "test_profile_id": profile["profile_id"],
    }
    started = execute(client, headers, payload)
    assert started.json()["ok"], started.text
    case_id = started.json()["data"]["case_id"]
    service.executor.submit(lambda: None).result(timeout=90)
    view = service.inspect(case_id, actor)
    assert view["status"] == expected, view
    assert view["evidence_authenticated"]
    expected_count = {
        "expired": 1,
        "substituted": 2,
        "redirect": 1,
        "missing_private": 5,
    }.get(access_application.mode, 8)
    assert (
        view["request_count"]
        == len(requests)
        == len(access_application.requests)
        == expected_count
    )
    assert (
        access_application.requests
        == [
            ("/whoami", 0),
            ("/whoami", 1),
            ("/records/a", 0),
            ("/records/b", 1),
            ("/records/a", None),
            ("/records/a", 1),
            ("/whoami", 0),
            ("/whoami", 1),
        ][:expected_count]
    )
    if expected == "CANDIDATE":
        finding = view["findings"][0]["finding_id"]
        assert (
            access_application.objects[0]["id"] != access_application.objects[1]["id"]
        )
        assert (
            access_application.objects[0]["private"]
            != access_application.objects[1]["private"]
        )
        evidence = (
            "Independent fixture owner inspection confirms two separate accounts, "
            "distinct owned objects, "
            "and a policy requiring denial of the second account at the first object. "
            "The target request ledger independently confirms the cross-account GET."
        )
        reviewed = execute(
            client,
            headers,
            {**web_review_payload(case_id, finding), "evidence_text": evidence},
            "beescan_review",
        )
        assert reviewed.json()["ok"], reviewed.text
        prepared = execute(
            client,
            headers,
            web_report_payload(
                case_id, finding, reviewed.json()["data"]["review_id"], complete=True
            ),
            "beescan_report_prepare",
        )
        assert prepared.json()["ok"], prepared.text
        query = {
            "case_id": case_id,
            "finding_id": finding,
            "report_run_id": prepared.json()["data"]["report_run_id"],
            "format": "json",
            "download": "true",
        }
        exported = client.get("/api/beescan/report", params=query)
        assert exported.status_code == 200 and exported.json()["submission_eligible"]
        assert (
            client.get(
                "/api/beescan/report", params={**query, "format": "markdown"}
            ).status_code
            == 200
        )
        restarted = build_beeui_app(settings, logging.getLogger("restart"), storage)
        restarted.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(
            settings
        )
        restored, _ = authenticated(restarted)
        assert (
            restored.get("/api/beescan/report", params=query).content
            == exported.content
        )
        print(
            json.dumps(
                {
                    "case_id": case_id,
                    "relationship": relationship,
                    "finding_id": finding,
                    "report_run_id": query["report_run_id"],
                    "export_sha256": hashlib.sha256(exported.content).hexdigest(),
                    "target_requests": len(requests),
                    "review_report_export_requests": 0,
                }
            )
        )
    assert len(requests) == expected_count
    for session in sessions:
        assert (
            session.closed
            and session.evidence["cleanup_verified"]
            and session.evidence["enforcement_verified"]
        )
        assert (
            session.helper.poll() is not None and session.supervisor.poll() is not None
        )
    for path in storage.rglob("*"):
        if path.is_file():
            text = path.read_text()
            assert all(value not in text for value in access_application.tokens)
            assert all(obj["private"] not in text for obj in access_application.objects)
    assert (
        client.get("/beescan", params={"tab": "results", "run_id": case_id}).status_code
        == 200
    )
    service.executor.shutdown(wait=True)


@pytest.mark.parametrize(
    "managed_lab,expected",
    [
        ("access-auto-vulnerable", "CANDIDATE"),
        ("access-auto-fixed", "NO_MATCH"),
        ("access-auto-public", "NO_MATCH"),
        ("access-auto-ambiguous", "PARTIAL"),
        ("access-auto-multiple", "CANDIDATE"),
        ("access-auto-html", "CANDIDATE"),
        ("access-auto-login", "PARTIAL"),
    ],
    indirect=["managed_lab"],
)
@pytest.mark.parametrize(
    "relationship,alternate", [("horizontal", False), ("vertical", True)]
)
def test_real_autonomous_web_investigation(
    managed_lab, access_application, monkeypatch, relationship, alternate, expected
):
    _, root, requests, sessions, probe = managed_lab
    settings = web_settings(monkeypatch)
    approval = asdict(
        InvestigationPolicy(probe, True, True, True, "GET", "numeric_invalid_v1", 3)
    )
    for key in ("valid_from", "expires_at"):
        approval["transport"][key] = approval["transport"][key].isoformat()
    settings["beescan"]["investigation"].update(
        approval=approval, local_lab_enabled=True, timeout_seconds=60
    )
    profile = autonomous_profile(probe.origin, relationship)
    settings["beescan"]["access_control"] = {"profiles": [profile]}
    assert not any(
        key in str(profile)
        for key in ("object_id", "private_fields", "identity_path", "baseline_path")
    )
    storage = root / "autonomous-storage"
    storage.mkdir(mode=0o700)
    app = build_beeui_app(settings, logging.getLogger("managed-lab"), storage)
    service = app.state.beeagent_adapter.beescan
    service.reload_settings = lambda: deepcopy(settings)
    client, headers = authenticated(app)
    assert client.get("/beescan").status_code == 200
    actor = {"user_id": "alice", "role": "operator"}
    request = {
        "target": probe.origin,
        "task": "Investigate authorization boundaries autonomously",
        "mode": "deep",
        "nonce": service.nonce(actor),
        "test_profile_id": profile["profile_id"],
    }
    started = execute(client, headers, request)
    assert started.json()["ok"], started.text
    case_id = started.json()["data"]["case_id"]
    service.executor.submit(lambda: None).result(timeout=90)
    view = service.inspect(case_id, actor)
    assert view["status"] == expected, view
    assert view["evidence_authenticated"]
    assert (
        view["request_count"] == len(requests) == len(access_application.requests) <= 20
    )
    before = len(requests)
    if expected == "CANDIDATE":
        finding = view["findings"][0]["finding_id"]
        reviewed = execute(
            client, headers, web_review_payload(case_id, finding), "beescan_review"
        )
        assert reviewed.json()["ok"], reviewed.text
        prepared = execute(
            client,
            headers,
            web_report_payload(
                case_id, finding, reviewed.json()["data"]["review_id"], complete=True
            ),
            "beescan_report_prepare",
        )
        assert prepared.json()["ok"], prepared.text
        query = {
            "case_id": case_id,
            "finding_id": finding,
            "report_run_id": prepared.json()["data"]["report_run_id"],
            "format": "json",
            "download": "true",
        }
        output = client.get("/api/beescan/report", params=query)
        assert output.status_code == 200 and output.json()["schema_version"] == 2
        assert (
            client.get(
                "/api/beescan/report", params={**query, "format": "markdown"}
            ).status_code
            == 200
        )
        restarted = build_beeui_app(settings, logging.getLogger("restarted"), storage)
        restarted.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(
            settings
        )
        restored, _ = authenticated(restarted)
        assert (
            restored.get("/api/beescan/report", params=query).content == output.content
        )
    assert len(requests) == before
    assert all(
        s.closed
        and s.evidence["cleanup_verified"]
        and s.evidence["enforcement_verified"]
        for s in sessions
    )
    for file in storage.rglob("*"):
        if file.is_file():
            content = file.read_text()
            assert all(token not in content for token in access_application.tokens)
            assert all(
                p.get("private", "not-recorded-test-marker") not in content
                for _, _, _, p in access_application.resources
            )
    print(
        json.dumps(
            {
                "case_id": case_id,
                "status": view["status"],
                "relationship": relationship,
                "alternate": alternate,
                "target_requests": before,
                "review_report_export_requests": 0,
                "storage": str(storage),
            }
        )
    )
    service.executor.shutdown(wait=True)
