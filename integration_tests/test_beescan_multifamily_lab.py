import hashlib
import json
import logging
import os
import ssl
import threading
import time
from copy import deepcopy
from dataclasses import asdict, replace
from functools import wraps
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from test_beescan_egress_lab import approved as approved
from test_beescan_egress_lab import managed_lab as managed_lab

from beeagent_module.integrations.beescan import dast_runner, investigation
from beeagent_module.integrations.beescan.case_state import load_case
from beeagent_module.interfaces.ui.app import build_beeui_app
from tests.beescan_access_support import AutonomousApplication, autonomous_profile
from tests.test_beescan_conversation import arguments
from tests.test_beescan_web import (
    authenticated,
    execute,
    web_report_payload,
    web_review_payload,
    web_settings,
)


@pytest.fixture
def access_application(approved, monkeypatch, request):
    _, _, root = approved
    administrative = request.node.callspec.params["administrative"]
    fixed = request.node.callspec.params["fixed"]
    application = AutonomousApplication(
        "fixed" if administrative else "vulnerable",
        "vertical" if administrative else "horizontal",
    )
    for name, token in zip(("A", "B"), application.tokens):
        monkeypatch.setenv("BEEAGENT_ACCESS_" + name, token)
    filesystem = root / "controlled-filesystem"
    documents = filesystem / "www/images"
    documents.mkdir(parents=True)
    (documents / "fixture").write_text("Synthetic public fixture\n")
    (filesystem / "etc").mkdir()
    (filesystem / "etc/passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")
    original = application.get

    def response(path, credential):
        parsed = urlsplit(path)
        if path == "/" and credential is None:
            application.requests.append((path, None))
            return (
                200,
                '<img src="/read?document=fixture"><a href="/source.conf">source</a>',
            )
        if path == "/source.conf":
            application.requests.append((path, None))
            return 200, 'DB_PASSWORD="controlled-source-canary"'
        if parsed.path == "/read":
            application.requests.append((path, None))
            supplied = parse_qs(parsed.query).get("document", [""])[0]
            selected = (documents / supplied.replace("../", "")).resolve()
            if (
                not selected.is_relative_to(filesystem)
                or fixed
                and not selected.is_relative_to(documents)
            ):
                return 404, "Missing"
            if selected.is_file():
                return 200, selected.read_text()
            return 404, "Missing"
        code, body = original(path, credential)
        if (
            administrative
            and credential is None
            and path == application.resources[0][0]
        ):
            return 200, application.resources[0][3]
        return code, body

    application.get = response
    original_header = BaseHTTPRequestHandler.send_header

    def header(handler, name, value):
        if name == "Content-Type" and urlsplit(handler.path).path in {
            "/source.conf",
            "/read",
        }:
            value = "text/plain"
        original_header(handler, name, value)

    monkeypatch.setattr(BaseHTTPRequestHandler, "send_header", header)
    return application


@pytest.mark.parametrize("managed_lab", ["access-multifamily"], indirect=True)
@pytest.mark.parametrize("administrative", [False, True])
@pytest.mark.parametrize("fixed", [False, True])
def test_real_multifamily_web(
    managed_lab, access_application, administrative, fixed, monkeypatch
):
    _, root, requests, sessions, probe = managed_lab
    source = Path("/home/bee/Pro/beescan")
    project = root / "paired-project"
    project.mkdir()
    (root / "beescan").symlink_to(source, target_is_directory=True)
    (project / "pyproject.toml").write_text(
        '[tool.uv.sources]\nbeescan = {path = "../beescan", editable = true}\n'
    )
    (project / "config").symlink_to(
        Path(__file__).resolve().parents[1] / "config", target_is_directory=True
    )
    metadata = root / "paired-metadata"
    distribution = metadata / "beescan-0.18.0.dist-info"
    distribution.mkdir(parents=True)
    (distribution / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: beescan\nVersion: 0.18.0\n"
    )
    (distribution / "direct_url.json").write_text(
        json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})
    )
    monkeypatch.syspath_prepend(str(metadata))
    monkeypatch.setattr(investigation, "get_project_root", lambda: project)
    settings = web_settings(monkeypatch)
    probe = replace(probe, time_budget_seconds=60)
    approval = asdict(
        investigation.InvestigationPolicy(
            probe, True, True, True, "GET", "numeric_invalid_v1", 3
        )
    )
    for name in ("valid_from", "expires_at"):
        approval["transport"][name] = approval["transport"][name].isoformat()
    config = settings["beescan"]["investigation"]
    config.update(
        approval=approval,
        local_lab_enabled=True,
        trusted_local_enabled=True,
        timeout_seconds=60,
    )
    config["adaptive"].update(enabled=True, max_steps=16, max_requests=20, max_depth=4)
    profile = autonomous_profile(
        probe.origin,
        "vertical" if administrative else "horizontal",
        "administrative_restricted" if administrative else "owned_private",
    )
    if administrative:
        profile.update(
            restriction_reference="independently-inspected-role-policy",
            restricted_resource_type="resource-0",
            resource_path=access_application.resources[0][0],
            negative_path="/independent-denial-control",
        )
        profile.pop("principals")
    settings["beescan"]["access_control"] = {"profiles": [profile]}
    settings["beescan"]["dast"] = {
        "enabled": True,
        "approval": {
            "transport": approval["transport"],
            "approved": True,
            "method": "active_dast",
            "entries": [],
            "entry_selection": "authenticated_discovery",
            "max_candidates": 1,
            "profile": "traversal-nonrecursive-v1",
            "request_budget": 10,
            "seconds": 55,
        },
    }
    context = ssl.create_default_context(cafile=str(root / "cert.pem"))
    original_zap = dast_runner.run_zap

    def run(transport, **kwargs):
        return original_zap(transport, **kwargs, upstream_tls=context)

    monkeypatch.setattr(dast_runner, "run_zap", run)
    storage = root / "multifamily-storage"
    storage.mkdir(mode=0o700)
    app = build_beeui_app(settings, logging.getLogger("managed-lab"), storage)
    service = app.state.beeagent_adapter.beescan
    service.reload_settings = lambda: deepcopy(settings)
    client, headers = authenticated(app)
    actor = {"user_id": "alice", "role": "operator"}
    parent_id = service.conversations.execute(
        "beescan_context",
        {"nonce": service.nonce(actor), "key": "target", "value": probe.origin},
        actor,
    )["case_id"]
    for key, value in (("profile", profile["profile_id"]),):
        service.conversations.execute(
            "beescan_context",
            {**arguments(service, actor, parent_id), "key": key, "value": value},
            actor,
        )
    from beeagent_module.integrations.beescan import detection_runner

    captured, release = threading.Event(), threading.Event()
    original_capture = detection_runner.run_detection_provider
    capture_calls = []

    @wraps(original_capture)
    def live_capture(*args, **kwargs):
        if capture_calls:
            captured.set()
            assert release.wait(
                180 if os.getenv("BEEAGENT_MULTIFAMILY_BROWSER_SMOKE") == "1" else 45
            )
        capture_calls.append(True)
        return original_capture(*args, **kwargs)

    monkeypatch.setattr(detection_runner, "run_detection_provider", live_capture)
    started = execute(
        client,
        headers,
        {
            **arguments(service, actor, parent_id),
            "task": "Assess web security",
            "mode": "deep",
            "confirmation": "INVESTIGATE",
        },
        "beescan_investigate",
    )
    assert started.json()["ok"], started.text
    case_id = service.conversations.read(parent_id, actor)["runs"][-1]["run_id"]
    browser = os.getenv("BEEAGENT_MULTIFAMILY_BROWSER_SMOKE") == "1"
    server = thread = None
    try:
        assert captured.wait(60), "No live checkpoint after HTTP capture"
        before_poll = {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in storage.rglob("*")
            if p.is_file()
        }
        before_requests = len(requests)
        live = client.get("/api/beescan/status", params={"run_id": parent_id}).json()[
            "data"
        ]
        assert live["status"] == "RUNNING"
        assert "not yet authenticated" in json.dumps(live["presentation"])
        for offset in range(0, live["message_count"], 8):
            page = service.conversations.view(parent_id, actor, offset=offset)
            assert len({item["id"] for item in page["timeline"]}) == len(
                page["timeline"]
            )
        assert any(
            item["kind"] == "capture" and item.get("requests") == 1
            for offset in range(0, live["message_count"], 8)
            for item in service.conversations.view(parent_id, actor, offset=offset)[
                "timeline"
            ]
        )
        assert before_poll == {
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in storage.rglob("*")
            if p.is_file()
        }
        assert len(requests) == before_requests
        if browser:
            import uvicorn

            server = uvicorn.Server(
                uvicorn.Config(app, host="127.0.0.1", port=18765, log_level="warning")
            )
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            ready = Path("/tmp/beescan-live-timeline/browser-ready.json")
            done = Path("/tmp/beescan-live-timeline/browser-running-done")
            done.unlink(missing_ok=True)
            ready.write_text(
                json.dumps(
                    {
                        "case_id": parent_id,
                        "run_id": case_id,
                        "url": "http://127.0.0.1:18765/beescan?run_id=" + parent_id,
                        "storage": str(storage),
                    }
                )
            )
            until = time.monotonic() + 150
            while not done.exists() and time.monotonic() < until:
                time.sleep(0.25)
            assert done.exists(), "Live browser smoke was not completed"
            assert len(requests) == before_requests
    finally:
        release.set()
    service.executor.submit(lambda: None).result(timeout=90)
    view = service.inspect(case_id, actor)
    assert view["status"] == "CANDIDATE" and view["evidence_authenticated"], view
    assert len(view["findings"]) == 2 - int(administrative and fixed), view
    assert view["request_count_exact"] is True
    assert view["complete"] is False
    observations = view["observations"]
    traversal = next(
        item for item in observations if item["profile"] == "traversal-nonrecursive-v1"
    )
    assert traversal["endpoint"] == "/read" and traversal["parameters"] == ["document"]
    if administrative:
        assert traversal["controls_complete"] and len(traversal["controls"]) == 5
        assert traversal["missing_control_indexes"] == []
    else:
        assert traversal["status"] == "PARTIAL"
        assert not traversal["controls_complete"] and len(traversal["controls"]) == 3
        assert traversal["missing_control_indexes"] == [3, 4]
        assert view["request_count"] == 20
        assert sorted(
            finding["finding_id"].split("-", 1)[0] for finding in view["findings"]
        ) == ["acf", "df"]
    assert any(item["oracle"] for item in traversal["controls"]) is (not fixed)
    access = next(
        item
        for item in observations
        if item["profile"]
        == ("controlled-access" if administrative else "access-control-get-v1")
    )
    assert access["controls_complete"] and len(access["controls"]) == (
        3 if administrative else 8
    )
    if administrative:
        assert access["status"] == "PARTIAL"
        assert all(
            not finding["finding_id"].startswith("aaf-") for finding in view["findings"]
        )
    for locale in ("ru", "en"):
        from beeagent_module.interfaces.ui.conversation import presentation

        projected = presentation(service.conversations.view(parent_id, actor), locale)
        assert "/read" in json.dumps(projected) and "oracle=" in json.dumps(projected)
        assert "controlled-source-canary" not in json.dumps(projected)
    assert view["coverage"]["path_traversal"][0]["status"] == (
        ("NO_MATCH" if fixed else "CANDIDATE") if administrative else "PARTIAL"
    )
    assert all(
        view["coverage"][family]
        for family in ("information_disclosure", "path_traversal", "access_control")
    )
    assert (
        view["request_count"] == len(requests) == len(access_application.requests) <= 20
    )
    before = len(requests)
    for finding in view["findings"]:
        review = web_review_payload(case_id, finding["finding_id"])
        review["evidence_text"] += (
            " Independent fixture inspection for " + finding["finding_id"]
        )
        reviewed = execute(client, headers, review, "beescan_review")
        assert reviewed.json()["ok"], reviewed.text
        report = execute(
            client,
            headers,
            web_report_payload(
                case_id,
                finding["finding_id"],
                reviewed.json()["data"]["review_id"],
                complete=True,
            ),
            "beescan_report_prepare",
        )
        assert report.json()["ok"], report.text
        query = {
            "case_id": case_id,
            "finding_id": finding["finding_id"],
            "report_run_id": report.json()["data"]["report_run_id"],
            "format": "json",
            "download": "true",
        }
        assert client.get("/api/beescan/report", params=query).status_code == 200
    case, snapshot = load_case(storage, case_id)
    assert case["schema_version"] == 7
    assert len(case["assessments"]) == 1 and len(case["access"]) == 1
    if not administrative:
        child = snapshot.json(
            case["assessments"][0]["run_id"], "investigation_status.json"
        )
        assert child["reason"] == "request_budget_exhausted"
        assert child["request_count"] == 3
        assert case["discovery"]["metrics"]["request_count"] == 5
        assert case["access"][0]["request_count"] == 12
    if administrative:
        child_id = case["access"][0]["run_id"]
        result = snapshot.json(child_id, "investigation_result.json")
        assert result["status"] == "PARTIAL"
        assert result["reason"] == "administrative_equivalence_unproven"
        assert result["findings"] == []
    assert all(
        s.closed
        and s.helper.poll() is not None
        and s.supervisor.poll() is not None
        and s.evidence["cleanup_verified"]
        and s.evidence["enforcement_verified"]
        for s in sessions
    )
    snapshot.verify()
    assert len(requests) == before
    for file in storage.rglob("*"):
        if file.is_file():
            content = file.read_text()
            assert "controlled-source-canary" not in content
            assert all(token not in content for token in access_application.tokens)
    assert (
        client.get("/beescan", params={"tab": "results", "run_id": case_id}).status_code
        == 200
    )
    print(
        json.dumps(
            {
                "case_id": case_id,
                "status": view["status"],
                "administrative": administrative,
                "fixed": fixed,
                "requests": before,
                "findings": len(view["findings"]),
                "storage": str(storage),
                "postprocessing_requests": len(requests) - before,
            }
        )
    )
    if browser:
        prior_response = access_application.get

        def patched_response(path, credential):
            if path == "/source.conf":
                access_application.requests.append((path, None))
                return 200, "Controlled patched configuration"
            return prior_response(path, credential)

        access_application.get = patched_response
        signal = Path("/tmp/beescan-browser-done")
        signal.unlink(missing_ok=True)
        Path("/tmp/beescan-browser-ready.json").write_text(
            json.dumps(
                {
                    "case_id": parent_id,
                    "url": "http://127.0.0.1:18765/beescan?run_id=" + parent_id,
                    "storage": str(storage),
                }
            )
        )
        deadline = time.monotonic() + 180
        while not signal.exists() and time.monotonic() < deadline:
            time.sleep(0.25)
        assert server is not None and thread is not None
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert signal.exists(), "Browser smoke was not completed"
        service.executor.submit(lambda: None).result(timeout=90)
        runs = service.conversations.read(parent_id, actor)["runs"]
        assert len(runs) == 2
        followup = service.inspect(runs[-1]["run_id"], actor)
        assert followup["status"] == "PARTIAL", followup
        assert followup["request_count"] == len(requests) - before <= 2
        assert service.inspect(case_id, actor)["findings"] == view["findings"]
        print(
            json.dumps(
                {
                    "parent_case": parent_id,
                    "followup_run": runs[-1]["run_id"],
                    "followup_status": followup["status"],
                    "followup_requests": followup["request_count"],
                    "prior_findings_preserved": True,
                }
            )
        )
    service.executor.shutdown(wait=True)
