import json
import logging
import ssl
from copy import deepcopy
from dataclasses import asdict, replace

import pytest
from test_beescan_egress_lab import approved as approved
from test_beescan_egress_lab import managed_lab as managed_lab

from beeagent_module.integrations.beescan import dast_runner
from beeagent_module.integrations.beescan.investigation import InvestigationPolicy
from beeagent_module.interfaces.ui.app import build_beeui_app
from tests.test_beescan_web import authenticated, execute, web_settings


@pytest.mark.parametrize(
    "managed_lab,mode,objective,expected_status,expected_requests",
    [
        (False, "quick", "Inspect supported exposures", None, None),
        (False, "standard", "Inspect supported exposures", None, None),
        (
            "dast-nonrecursive-vulnerable",
            "standard",
            "Assess Path Traversal",
            "CANDIDATE",
            6,
        ),
        (
            "dast-nonrecursive-fixed",
            "standard",
            "Assess Path Traversal",
            "NO_MATCH",
            6,
        ),
        (
            "dast-nonrecursive-doubledecode-vulnerable",
            "standard",
            "Assess Path Traversal",
            "CANDIDATE",
            10,
        ),
        (
            "dast-nonrecursive-doubledecode-fixed",
            "standard",
            "Assess Path Traversal",
            "NO_MATCH",
            10,
        ),
        (
            "dast-nonrecursive-vulnerable",
            "quick",
            "Assess supported exposures",
            None,
            None,
        ),
        (
            "dast-nonrecursive-vulnerable",
            "standard",
            "Assess supported exposures",
            None,
            None,
        ),
        (
            "dast-nonrecursive-vulnerable",
            "deep",
            "Assess supported exposures",
            None,
            None,
        ),
    ],
    indirect=["managed_lab"],
)
@pytest.mark.parametrize("server_policy", [False, True])
def test_real_web_investigation_case_and_resume(
    managed_lab,
    monkeypatch,
    mode,
    objective,
    expected_status,
    expected_requests,
    capsys,
    server_policy,
):
    from beescan.capabilities.catalog import EffortMode
    from beescan.domain import assessment_selection

    decisions = []
    decide_assessment = assessment_selection.decide_assessment

    def decide(*args, **kwargs):
        result = decide_assessment(*args, **kwargs)
        decisions.append((kwargs["mode"], args[1], result))
        return result

    monkeypatch.setattr(assessment_selection, "decide_assessment", decide)
    _, root, requests, sessions, probe = managed_lab
    settings = web_settings(monkeypatch)
    config = settings["beescan"]["investigation"]
    probe = replace(probe, time_budget_seconds=60)
    approval = asdict(
        InvestigationPolicy(probe, True, True, True, "GET", "numeric_invalid_v1", 3)
    )
    for key in ("valid_from", "expires_at"):
        approval["transport"][key] = approval["transport"][key].isoformat()
    config.update(approval=approval, local_lab_enabled=True, timeout_seconds=60)
    dast = probe.origin.startswith("https:")
    dast_calls = []
    if dast:
        config["trusted_local_enabled"] = True
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
        original = dast_runner.run_zap

        def run(transport, **kwargs):
            dast_calls.append(kwargs["profile"])
            return original(transport, **kwargs, upstream_tls=context)

        monkeypatch.setattr(dast_runner, "run_zap", run)
    if server_policy:
        from beeagent_module.integrations.beescan import policy as target_policy

        original_public = target_policy.public_destination
        monkeypatch.setattr(
            target_policy,
            "public_destination",
            lambda value: value == probe.connected_ip or original_public(value),
        )
        settings["beescan"]["target_policy"] = {"excluded_targets": []}
        config["approval"] = None
        if dast:
            settings["beescan"]["dast"]["approval"] = None
    storage = root / "web-storage"
    storage.mkdir(mode=0o700)
    app = build_beeui_app(settings, logging.getLogger("managed-lab"), storage)
    service = app.state.beeagent_adapter.beescan
    service.logger = logging.getLogger("managed-lab")
    service.reload_settings = lambda: deepcopy(settings)
    client, headers = authenticated(app)
    actor = {"user_id": "alice", "role": "operator"}
    payload = {
        "target": probe.origin,
        "task": objective,
        "mode": mode,
        "nonce": service.nonce(actor),
    }
    if dast and mode == "quick":
        refused = execute(
            client,
            headers,
            {
                **payload,
                "task": "Assess Path Traversal",
            },
        )
        if server_policy:
            assert (
                refused.json()["ok"] and refused.json()["data"]["status"] == "REFUSED"
            ), refused.text
            refused_view = client.get(
                "/api/beescan/status",
                params={"run_id": refused.json()["data"]["run_id"]},
            ).json()["data"]
            assert refused_view["reason"] == "web_dast_profile_unsupported"
            assert refused_view["request_count"] == 0
            payload["nonce"] = service.nonce(actor)
        else:
            assert not refused.json()["ok"], refused.text
        assert requests == decisions == dast_calls == []
        if not server_policy:
            assert list(storage.iterdir()) == []
    response = execute(client, headers, payload)
    assert response.json()["ok"], response.text
    identity = response.json()["data"]
    service.executor.submit(lambda: None).result(timeout=90)
    url = "/api/beescan/status?run_id=" + identity["run_id"]
    status = client.get(url).json()["data"]
    assert status["case_status"] != "unavailable", status
    assert status["status"] not in {"ERROR", "REFUSED", "QUEUED"}, status
    assert status["request_count"] == len(requests) > 0
    assert status["evidence_authenticated"]
    projection = status["presentation"]
    assert projection["complete"]
    assert projection["messages"][0]["text"] == objective
    assert len({message["id"] for message in projection["messages"]}) == len(
        projection["messages"]
    )
    assert all(not message["timestamp"] for message in projection["messages"])
    from beeagent_module.interfaces.ui.beescan import workspace

    layout = workspace(service, {"run_id": identity["case_id"]}, actor)["layout"]
    chat = next(block for block in layout if block["type"] == "chat_workspace")
    assert chat["composer"]["args"]["task"] == objective
    assert chat["composer"]["args"]["target"] == probe.origin
    assert chat["composer"]["args"]["mode"] == mode
    assert chat["refresh"] is None
    expected_history = 2 if server_policy and dast and mode == "quick" else 1
    assert len(chat["history"]) == expected_history
    assert status["intake"] == {
        "case_id": identity["case_id"],
        "target": payload["target"],
        "task": payload["task"],
        "mode": mode,
    }
    assert len(service.history(actor)) == expected_history
    parent = storage / "runs" / identity["case_id"] / "module-beescan"
    assert (parent / "case.json").is_file()
    assert (parent / "web_receipt.json").is_file()
    assert (parent / "report.md").is_file()
    if dast:
        assert decisions and all(
            decision[0] is EffortMode(mode) for decision in decisions
        )
        assert any(entries for _, entries, _ in decisions)
        if mode == "quick":
            assert all(result.action is None for _, _, result in decisions)
            assert status["status"] == "PARTIAL"
            assert not status["findings"]
            assert not dast_calls
            assert not list(storage.rglob("dast_execution_status.json"))
            assert 1 <= len(requests) <= 2
        else:
            assert status["status"] in {"CANDIDATE", "NO_MATCH"}
            assert dast_calls == ["traversal-nonrecursive-v1"]
            assert len(requests) == expected_requests
    if expected_status is not None:
        assert status["status"] == expected_status, status
    if expected_status == "CANDIDATE":
        with capsys.disabled():
            _review_report_acceptance(
                client,
                headers,
                app,
                settings,
                storage,
                identity,
                status,
                requests,
                root,
            )
    if expected_status == "NO_MATCH":
        from tests.test_beescan_web import web_report_payload

        assert not status["findings"]
        saved = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
        assert not execute(
            client,
            headers,
            web_report_payload(
                identity["case_id"], "missing-finding", "", complete=True
            ),
            "beescan_report_prepare",
        ).json()["ok"]
        assert saved == {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
        assert len(requests) == expected_requests
    before_requests = list(requests)
    before = {str(p): p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    for _ in range(3):
        assert client.get(url).status_code == 200
        assert client.get("/beescan?run_id=" + identity["run_id"]).status_code == 200
    results = client.get(
        "/beescan", params={"tab": "results", "run_id": identity["run_id"]}
    )
    assert results.status_code == 200
    assert "data-chat-composer" not in results.text
    assert status["status"] in results.text
    assert identity["case_id"] in results.text
    search = client.get(
        "/beescan",
        params={
            "tab": "investigation",
            "run_id": identity["run_id"],
            "q": "no-such-case-362",
        },
    )
    assert search.status_code == 200
    assert "No matching Cases." in search.text
    assert 'aria-current="page"' in search.text
    assert identity["case_id"] in search.text
    assert requests == before_requests
    assert before == {str(p): p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    if dast and mode == "quick":
        for session in sessions:
            assert session.closed and session.evidence["cleanup_verified"]
        service.executor.shutdown(wait=True)
        return
    resume_payload = {
        **payload,
        "nonce": service.nonce(actor),
        "case_id": identity["case_id"],
    }
    resumed = execute(client, headers, resume_payload, "beescan_resume")
    assert resumed.json()["ok"], resumed.text
    assert resumed.json()["data"]["case_id"] == identity["case_id"]
    if mode == "quick":
        service.executor.submit(lambda: None).result(timeout=90)
        assert len(requests) > len(before_requests)
        assert all(requests.count(item) == 1 for item in before_requests)
    else:
        assert requests == before_requests
        assert resumed.json()["data"]["reused"]
    assert not execute(client, headers, resume_payload, "beescan_resume").json()["ok"]
    bob, bob_headers = authenticated(app, "bob")
    assert bob.get(url).status_code == 403
    assert not execute(
        bob,
        bob_headers,
        {
            **resume_payload,
            "nonce": service.nonce({"user_id": "bob", "role": "operator"}),
        },
        "beescan_resume",
    ).json()["ok"]
    for path in storage.rglob("web_owner.json"):
        record = json.loads(path.read_text())
        assert record["binding"]["principal_id"] == "alice"
        run_id = record["binding"]["run_id"]
        for prefix in ("/runs/", "/api/runs/"):
            for suffix in ("", "/artifacts", "/artifacts/run_json"):
                assert bob.get(prefix + run_id + suffix).status_code == 403
    for session in sessions:
        assert session.closed and session.evidence["cleanup_verified"]
    app2 = build_beeui_app(settings, logging.getLogger("managed-lab"), storage)
    app2.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(settings)
    restored, _ = authenticated(app2)
    assert restored.get(url).json()["data"]["status"] == status["status"]
    request_total = len(requests)
    altered_task = {
        **resume_payload,
        "nonce": service.nonce(actor),
        "task": "Different objective",
    }
    assert not execute(client, headers, altered_task, "beescan_resume").json()["ok"]
    receipt = parent / "web_receipt.json"
    original_receipt = receipt.read_bytes()
    damaged = json.loads(receipt.read_text())
    damaged["signature"] = "0" * 64
    receipt.write_text(json.dumps(damaged))
    assert not execute(
        client,
        headers,
        {
            **resume_payload,
            "nonce": service.nonce(actor),
        },
        "beescan_resume",
    ).json()["ok"]
    assert len(requests) == request_total
    receipt.write_bytes(original_receipt)
    history = service.history(actor)
    assert len(history) == 1
    assert history[0]["case_id"] == identity["case_id"]
    current_view = client.get(url).json()["data"]
    assert len({item["id"] for item in current_view["events"]}) == len(
        current_view["events"]
    )
    assert current_view["intake"]["task"] == objective
    intake_file = parent / "web_intake.json"
    original_intake = intake_file.read_bytes()
    changed_intake = json.loads(original_intake)
    changed_intake["intake"]["task"] = "Foreign objective"
    intake_file.write_text(json.dumps(changed_intake))
    assert client.get(url).status_code == 403
    intake_file.write_bytes(original_intake)
    if dast:
        if objective == "Assess Path Traversal":
            from beeagent_module.integrations.beescan.local_cli import (
                _SEAL,
                _identity,
                _LocalOperator,
            )
            from beeagent_module.integrations.beescan.probe import handle_beescan_cli

            decisions.clear()
            if server_policy:
                config["approval"] = approval
                settings["beescan"]["dast"]["approval"] = {
                    "transport": approval["transport"],
                    "approved": True,
                    "method": "active_dast",
                    "entries": [],
                    "entry_selection": "authenticated_discovery",
                    "max_candidates": 1,
                    "profile": "traversal-nonrecursive-v1",
                    "request_budget": 10,
                    "seconds": 55,
                }
            cli_storage = root / "cli-storage"
            cli_storage.mkdir(mode=0o700)
            code = handle_beescan_cli(
                ["investigate", "--target", probe.origin, "--task", objective],
                settings=settings,
                reload_settings=lambda: deepcopy(settings),
                storage_dir=cli_storage,
                logger=logging.getLogger("managed-lab"),
                local_operator=_LocalOperator(_identity(), _SEAL),
            )
            output = capsys.readouterr()
            assert code == 0, output
            assert decisions and all(
                mode is EffortMode.STANDARD for mode, _, _ in decisions
            )
            assert len(requests) == request_total + expected_requests
            assert json.loads(output.out)["request_count"] == expected_requests
        request_total = len(requests)
        if server_policy:
            settings["beescan"]["dast"]["enabled"] = False
        else:
            settings["beescan"]["dast"]["approval"]["approved"] = False
        refused = execute(
            client,
            headers,
            {
                **payload,
                "task": "Assess Path Traversal",
                "nonce": service.nonce(actor),
            },
        )
        if server_policy:
            assert (
                refused.json()["ok"] and refused.json()["data"]["status"] == "REFUSED"
            ), refused.text
        else:
            assert not refused.json()["ok"], refused.text
        assert len(requests) == request_total
    service.executor.shutdown(wait=True)


def _review_report_acceptance(
    client, headers, app, settings, storage, identity, status, requests, root
):
    import hashlib

    from beeagent_module.integrations.beescan.review import inspect_web_reports
    from tests.test_beescan_web import web_report_payload, web_review_payload

    case_id = identity["case_id"]
    finding_id = status["findings"][0]["finding_id"]
    fixture = root / "filesystem/etc/passwd"
    independently_inspected = fixture.read_bytes()
    assert independently_inspected.startswith(b"root:x:0:0:")
    evidence = (
        "Controlled fixture owner inspection: the laboratory account file exists outside "
        "the configured image root; its independent SHA-256 is "
        + hashlib.sha256(independently_inspected).hexdigest()
        + ". This is a laboratory test-principal attestation."
    )
    original = {p: p.read_bytes() for p in storage.rglob("*") if p.is_file()}
    counted = list(requests)
    reviewed = execute(
        client,
        headers,
        {
            **web_review_payload(case_id, finding_id),
            "evidence_text": evidence,
            "decision_basis": "Controlled laboratory owner inspection and independent fixture integrity",
        },
        "beescan_review",
    )
    assert reviewed.json()["ok"], reviewed.text
    review_id = reviewed.json()["data"]["review_id"]
    prepared = execute(
        client,
        headers,
        web_report_payload(case_id, finding_id, review_id, complete=True),
        "beescan_report_prepare",
    )
    assert prepared.json()["ok"], prepared.text
    assert prepared.json()["data"]["submission_eligible"]
    run_id = prepared.json()["data"]["report_run_id"]
    query = {
        "case_id": case_id,
        "finding_id": finding_id,
        "report_run_id": run_id,
        "format": "json",
        "download": "true",
    }
    json_export = client.get("/api/beescan/report", params=query)
    markdown = client.get("/api/beescan/report", params={**query, "format": "markdown"})
    assert json_export.status_code == markdown.status_code == 200
    report = json_export.json()
    assert report["finding_id"] == finding_id and report["provenance"]["action_id"]
    assert report["endpoint_path"] == "/" and report["parameter_names"] == ["file"]
    assert report["review"]["reviewer_id"] == "alice"
    assert evidence not in json_export.text + markdown.text
    page = client.get("/beescan", params={"run_id": case_id, "tab": "results"})
    assert page.status_code == 200 and "beescan_report_prepare" in page.text
    fresh = build_beeui_app(settings, logging.getLogger("lab-report-restart"), storage)
    fresh.state.beeagent_adapter.beescan.reload_settings = lambda: deepcopy(settings)
    restored, _ = authenticated(fresh)
    assert (
        restored.get("/api/beescan/report", params=query).content == json_export.content
    )
    assert inspect_web_reports(
        fresh.state.beeagent_adapter.beescan,
        case_id,
        finding_id,
        {"user_id": "alice", "role": "operator"},
    )["reports"]
    assert requests == counted
    assert all(p.read_bytes() == raw for p, raw in original.items())
    print(
        json.dumps(
            {
                "case_id": case_id,
                "finding_id": finding_id,
                "dast_run_id": report["provenance"]["run_id"],
                "review_id": review_id,
                "report_run_id": run_id,
                "original_requests": len(counted),
                "review_export_requests": 0,
                "report_sha256": hashlib.sha256(json_export.content).hexdigest(),
            }
        )
    )
