import json
import logging

import pytest

from beeagent_module.integrations.beescan import investigation as host
from beeagent_module.integrations.beescan import local_cli, probe
from beeagent_module.integrations.beescan.case_state import (
    _load_general_case,
    load_case,
)
from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot
from tests import test_beescan_debug_disclosure as debug_tests

execution = debug_tests.execution
settings = debug_tests.settings


@pytest.fixture
def general(execution, monkeypatch):
    execution.config["adaptive"].update(
        enabled=True, max_steps=16, max_requests=20, max_depth=4
    )
    calls = []
    state = {
        "patched": False,
        "assessment_body": None,
        "target": "http://127.0.0.1:18080",
        "dast": None,
        "root": "/ops/",
        "cancel": False,
        "robots": False,
        "alternatives": False,
        "skip_binary": False,
        "capture_error": False,
        "timeout": False,
        "timeout_at": None,
        "unresolved_source": False,
        "builder": False,
        "positional_builder": False,
    }

    def capture(policy, *, reauthorize, investigation, on_attempt, deadline):
        reauthorize()
        path = investigation["relative_url"]
        calls.append(path)
        on_attempt(True)
        if state["cancel"] and path != "/":
            raise KeyboardInterrupt
        if state["capture_error"] and path == state["root"]:
            raise host.ResponseLengthExceeded(141714)
        if state["timeout"] and (
            path != "/" if state["timeout_at"] is None else path == state["timeout_at"]
        ):
            raise TimeoutError
        media = "text/html"
        if path == "/":
            body = (
                '<a href="/a"></a><a href="/b"></a>'
                if state["alternatives"]
                else '<a href="/asset.bin"></a><a href="/later/"></a>'
                if state["skip_binary"]
                else '<a href="' + state["root"] + '">Operations</a><a href="/zz"></a>'
                if state["unresolved_source"]
                else ""
                if state["robots"]
                else '<a href="' + state["root"] + '">Operations</a>'
            )
        elif path == "/robots.txt":
            body, media = "Disallow: " + state["root"], "text/plain"
        elif path == state["root"]:
            body, media = (
                (
                    'class SourceConfiguration { String setting = "present"; }',
                    "text/plain",
                )
                if state["unresolved_source"]
                else ('<a href="runtime.conf">Configuration</a>', media)
            )
        elif path == "/asset.bin" and state["skip_binary"]:
            return json.dumps(
                {
                    "origin": policy.origin,
                    "connected_ip": policy.connected_ip,
                    "port": policy.port,
                    "method": "GET",
                    "relative_url": path,
                    "request_count": 1,
                    "status_code": 200,
                    "skip_reason": "unsupported_response_type",
                    "complete": True,
                }
            ).encode()
        elif path.endswith("runtime.conf"):
            body = (
                'class SourceConfiguration { String setting = "present"; }'
                if state["unresolved_source"]
                else 'import common.db.JdbcConnectionBuilder;\nConnectionBuilder connectionBuilder = ConnectionBuilder.from("org.postgresql.Driver", "postgresql", "db", 5432, "app", "user", "transient-positional-canary").withAutoCommit();\nConnection connect = connectionBuilder.connect(30);'
                if state["positional_builder"]
                else 'String url = "jdbc:postgresql://db/app";\nString credential = "transient-builder-canary";\nDataSource source = createSource();\nsource.setUrl(url);\nsource.setPassword(credential);'
                if state["builder"]
                else "Patched"
                if state["patched"]
                else 'POOL_PIN="transient-general-canary"'
            )
            media = "text/plain"
        else:
            body, media = "No disclosure", "text/plain"
        if path == "/" and state["assessment_body"] is not None:
            body = state["assessment_body"]
        return json.dumps(
            {
                "origin": policy.origin,
                "connected_ip": policy.connected_ip,
                "port": policy.port,
                "method": "GET",
                "relative_url": path,
                "request_count": 1,
                "complete": True,
                "status_code": 200,
                "content_type": media,
                "body": body,
            }
        ).encode()

    monkeypatch.setattr(
        "beeagent_module.integrations.beescan.detection_runner.run_detection_provider",
        capture,
    )
    monkeypatch.setattr(
        host,
        "call_structured_ai",
        lambda **kwargs: '{"recommendation":"continue_bounded_discovery"}',
    )
    operator = local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL)
    state["operator"] = operator

    def run(task="Investigate unfamiliar source field=POOL_PIN", **options):
        from tests.settings_support import read_test_settings

        current = read_test_settings()
        current["beescan"]["investigation"].update(execution.config)
        if state["dast"] is not None:
            current["beescan"]["dast"] = state["dast"]
        return host.execute_investigation(
            task=host.InvestigationTask(state["target"], task),
            local_operator=operator,
            settings=current,
            reload_settings=lambda: current,
            storage_dir=execution.root,
            logger=logging.getLogger("general-test"),
            general=True,
            **options,
        )

    return run, state, calls, execution


@pytest.mark.parametrize("root", ["/ops/", "/unfamiliar/record/"])
def test_general_host_vertical_slice_and_portability(general, root):
    run, state, calls, execution = general
    state["root"] = root
    result = run()
    assert result["status"] == "MATCH", result
    assert result["request_count"] == len(calls) == 6
    case, _ = load_case(execution.root, result["case_id"])
    assert case["schema_version"] == 2 and case["terminal"] and not case["pending"]
    assert case["metrics"]["ai_calls"] == 0
    assert execution.shown == ["transient-general-canary"]
    for path in execution.root.rglob("*.json"):
        assert "transient-general-canary" not in path.read_text()
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert "# General web investigation" in report
    assert "inspected_resources" in report
    assert '"target": "http://127.0.0.1:18080"' in report
    assert '"disposition": "CANDIDATE"' in report
    assert (
        '"answer": "Requested field established from authenticated source; value redacted."'
        in report
    )
    assert '"answer_supported": true' in report
    assert '"ambiguous": false' in report
    assert '"decisions"' in report
    assert "transient-general-canary" not in report


def test_general_robots_discovery_is_portable(general):
    run, state, calls, _ = general
    state["robots"] = True
    result = run()
    assert result["status"] == "MATCH", result
    assert calls[0] == "/"
    assert "/robots.txt" in calls
    assert "/ops/" in calls


def test_general_builder_secret_is_tty_only(general):
    run, state, _, execution = general
    state["builder"] = True
    result = run("Find the database password disclosed in exposed backup source files")
    assert result["status"] == "MATCH", result
    assert execution.shown == ["transient-builder-canary"]
    for path in execution.root.rglob("*.json"):
        assert "transient-builder-canary" not in path.read_text()
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert "transient-builder-canary" not in report


def test_general_positional_builder_secret_is_tty_only(general):
    run, state, calls, execution = general
    state["positional_builder"] = True
    result = run("Find the database password disclosed in exposed backup source files")
    assert result["status"] == "MATCH", result
    assert execution.shown == ["transient-positional-canary"]
    assert calls[-1] == "/ops/runtime.conf"
    for path in execution.root.rglob("*.json"):
        assert "transient-positional-canary" not in path.read_text()
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert "transient-positional-canary" not in report


def test_general_patched_is_meaningful_partial(general):
    run, state, calls, execution = general
    state["patched"] = True
    result = run()
    assert result["status"] == "INCONCLUSIVE" and not result["complete"], result
    assert result["request_count"] == len(calls)
    assert result["inspected_resources"] and result["next_actions"]
    assert execution.shown == []
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert '"status": "INCONCLUSIVE"' in report
    assert '"disposition": null' in report
    assert '"answer": null' in report
    assert '"decisions"' in report
    assert "transient-general-canary" not in report


def test_general_skips_binary_once_and_retains_observations(general):
    run, state, calls, execution = general
    state["skip_binary"] = True
    result = run("Find an exposed source or configuration resource")
    assert result["status"] in {"MATCH", "INCONCLUSIVE"}
    assert calls.count("/asset.bin") == 1
    assert result["inspected_resources"]
    assert result["skipped_resources"] == [
        {"relative_url": "/asset.bin", "reason": "unsupported_response_type"}
    ]
    case, _ = load_case(execution.root, result["case_id"])
    assert case["skipped_resources"] == result["skipped_resources"]
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert '"relative_url": "/"' in report
    assert '"skipped_resources"' in report
    assert '"reason": "unsupported_response_type"' in report


def test_general_error_retains_completed_observations(general):
    run, state, _, execution = general
    state["capture_error"] = True
    result = run()
    assert result["status"] == "ERROR"
    assert result["reason"] == "response_length_exceeds_limit"
    assert result["inspected_resources"]
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert '"relative_url": "/"' in report
    assert '"reason": "response_length_exceeds_limit"' in report
    assert f'"request_count": {result["request_count"]}' in report


def test_fieldless_source_disclosure_loads_and_inspects(general, capsys):
    run, state, _, execution = general
    result = run("Find an exposed source or configuration resource")
    assert result["status"] == "MATCH"
    assert result["disposition"] == "CANDIDATE"
    case, _ = load_case(execution.root, result["case_id"])
    assert case["status"] == "MATCH" and case["requested_field"] is None
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert '"answer": "Authenticated source/configuration resource observed."' in report
    assert '"source_disclosure": true' in report
    assert '"answer_supported": false' in report
    assert '"ambiguous": false' in report
    from tests.settings_support import read_test_settings

    current = read_test_settings()
    current["beescan"]["investigation"].update(execution.config)
    assert (
        probe.handle_beescan_cli(
            ["investigate", "--inspect", result["case_id"]],
            settings=current,
            reload_settings=lambda: current,
            storage_dir=execution.root,
            logger=logging.getLogger("fieldless-inspect-test"),
            local_operator=state["operator"],
        )
        == 0
    )
    assert '"status": "MATCH"' in capsys.readouterr().out


def test_exact_field_match_rejects_any_ambiguous_surface(general):
    run, _, _, execution = general
    result = run()
    snapshot = AssessmentSnapshot(execution.root)
    state = snapshot.json(result["case_id"], "case.json")["state"]
    state["entries"][0]["surface"]["ambiguous"] = True
    with pytest.raises(ValueError, match="unsupported_general_match"):
        _load_general_case(state, snapshot, result["case_id"])


def test_general_actual_limits(general):
    run, _, calls, execution = general
    execution.config["adaptive"].update(max_requests=2)
    result = run()
    assert len(calls) == result["request_count"] == 2, result
    assert result["reason"] == "request_budget_exhausted"


def test_general_deterministic_path_does_not_call_ai(general, monkeypatch):
    run, state, calls, execution = general
    state["alternatives"] = True
    execution.config["adaptive"].update(max_steps=2)
    monkeypatch.setattr(
        host, "_ai", lambda *args, **kwargs: pytest.fail("unexpected AI")
    )
    result = run()
    assert result["status"] == "INCONCLUSIVE"
    assert calls == ["/", "/robots.txt"]


def test_general_runs_without_ai_credentials(general, monkeypatch):
    run, _, _, _ = general
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = run()
    assert result["status"] == "MATCH", result


def test_general_interruption_never_releases_secret(general):
    run, state, _, execution = general
    state["cancel"] = True
    result = run()
    assert not result["complete"] and result["status"] == "INCONCLUSIVE"
    assert execution.shown == []
    case, _ = load_case(execution.root, result["case_id"])
    assert len(case["entries"]) == 1


def test_general_resume_reuses_authenticated_surfaces(general):
    run, _, calls, execution = general
    execution.config["adaptive"].update(max_steps=1)
    first = run()
    assert first["reason"] == "step_budget_exhausted"
    calls.clear()
    resumed = run(resume_case_id=first["case_id"])
    assert resumed["reason"] == "step_budget_exhausted", resumed
    assert calls == ["/robots.txt"]


def test_general_timeout_reports_and_resumes_evidence_resource(general):
    run, state, calls, execution = general
    state["timeout"] = True
    first = run("Find an exposed source or configuration resource")
    assert first["status"] == "TIMEOUT"
    assert any("/robots.txt" in action for action in first["next_actions"])
    report = (
        execution.root / "runs" / first["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert '"status": "TIMEOUT"' in report
    assert "/robots.txt" in report
    calls.clear()
    state["timeout"] = False
    resumed = run(
        "Find an exposed source or configuration resource",
        resume_case_id=first["case_id"],
    )
    assert calls[0] == "/robots.txt"
    assert "/" not in calls
    assert resumed["request_count"] > first["request_count"]


def test_timeout_reports_unresolved_authenticated_source(general):
    run, state, _, execution = general
    state.update(unresolved_source=True, timeout=True, timeout_at="/zz")
    result = run()
    assert result["status"] == "TIMEOUT"
    assert result["source_analysis"] == {
        "relative_url": "/ops/",
        "status_code": 200,
        "source_disclosure": True,
        "answer_supported": False,
        "reason": "requested_field_not_established",
    }
    assert any("/ops/" in action for action in result["next_actions"])
    report = (
        execution.root / "runs" / result["run_id"] / "module-beescan" / "report.md"
    ).read_text()
    assert '"source_analysis"' in report
    assert "database connection credential syntax" in report
    assert "transient-general-canary" not in report


def test_direct_cli_selects_general_workflow(settings, tmp_path, monkeypatch):
    captured = {}

    def execute(**kwargs):
        captured.update(kwargs)
        return {"status": "INCONCLUSIVE", "complete": False}

    monkeypatch.setattr(host, "execute_investigation", execute)
    assert (
        probe.handle_beescan_cli(
            [
                "investigate",
                "--target",
                "https://example.test",
                "--task",
                "Map the public surface",
            ],
            settings=settings,
            reload_settings=lambda: settings,
            storage_dir=tmp_path,
            logger=logging.getLogger("general-cli-test"),
        )
        == 5
    )
    assert captured["general"] is True


def test_adaptive_cli_preserves_legacy_workflow(settings, tmp_path, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        host,
        "execute_investigation",
        lambda **kwargs: (
            captured.update(kwargs) or {"status": "INCONCLUSIVE", "complete": False}
        ),
    )
    assert (
        probe.handle_beescan_cli(
            [
                "investigate",
                "--adaptive",
                "--target",
                "https://example.test",
                "--task",
                "Map the public surface",
            ],
            settings=settings,
            reload_settings=lambda: settings,
            storage_dir=tmp_path,
            logger=logging.getLogger("adaptive-cli-test"),
        )
        == 5
    )
    assert captured["adaptive"] is True
    assert captured["general"] is False


@pytest.fixture
def discovery_dast(general, monkeypatch):
    from copy import deepcopy

    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.detection import _persist

    run, state, calls, harness = general

    state["target"] = "https://example.test"
    transport = deepcopy(harness.config["approval"]["transport"])
    transport["origin"] = state["target"]
    transport["time_budget_seconds"] = 60
    state["dast"] = {
        "enabled": True,
        "approval": {
            "transport": transport,
            "approved": True,
            "method": "active_dast",
            "entries": [],
            "entry_selection": "authenticated_discovery",
            "max_candidates": 1,
            "request_budget": 10,
            "seconds": 20,
            "archive": "/tmp/operator-zap.zip",
        },
    }
    monkeypatch.setattr(
        local_cli,
        "present_sensitive_value",
        lambda *args: state.get("presentation", lambda *_: False)(*args),
    )
    active = []
    state["matched"] = True

    def scanner(
        transport,
        *,
        entries,
        artifacts,
        run_id,
        request_budget,
        seconds,
        authorize,
        **kwargs,
    ):
        authorize()
        active.append((entries, request_budget, seconds))
        record = {
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "status_code": 200,
        }
        _persist(
            artifacts,
            "egress_lifecycle.json",
            {
                "state": "closed",
                "cleanup_verified": True,
                "enforcement_verified": True,
                "assessment_run_id": run_id,
            },
        )
        _persist(
            artifacts,
            "dast_execution_status.json",
            {
                "cleanup_verified": True,
                "request_count": 1,
            },
        )
        authorize()
        return (
            {
                "alerts": [
                    {
                        "target": entries[0],
                        "request_sha256": "a" * 64,
                        "response_sha256": "b" * 64,
                    }
                ]
                if state["matched"]
                else [],
                "host_complete": True,
            },
            (record,),
            1,
        )

    monkeypatch.setattr(dast_runner, "run_zap", scanner)
    return run, state, calls, harness, active


@pytest.mark.parametrize(
    "body,expected",
    [
        ('<img src="/photo?name=public-canary.jpg">', "/photo?name=public-canary.jpg"),
        (
            '<form action="/retrieve"><input name="document" value="record-canary"></form>',
            "/retrieve?document=record-canary",
        ),
    ],
)
def test_discovery_to_dast_one_parent_and_no_replay(discovery_dast, body, expected):
    from beeagent_module.integrations.beescan.discovery_dast import validate_assessment

    run, state, calls, harness, active = discovery_dast
    state["assessment_body"] = body
    result = run("Assess Path Traversal")
    assert result["status"] == "CANDIDATE", result
    assert result["complete"] and result["request_count"] == 2
    assert result["reproduction"] == "TTY_REQUIRED"
    assert calls == ["/"]
    assert active[0][0] == (expected,)
    case, snapshot = load_case(harness.root, result["case_id"])
    assert case["schema_version"] == 4
    pending_action = validate_assessment(
        case["assessment"],
        case["discovery"],
        case["origin"],
        snapshot,
        result["case_id"],
        pending=True,
    )
    completed_action = validate_assessment(
        case["assessment"],
        case["discovery"],
        case["origin"],
        snapshot,
        result["case_id"],
    )
    assert pending_action == completed_action
    assert completed_action.action_id == case["assessment"]["action_id"]
    assert case["metrics"]["request_count"] == 2
    assert case["discovery"]["metrics"]["request_count"] == 1
    assert (
        snapshot.json(case["assessment"]["run_id"], "dast_handoff.json")["intent"][
            "parent_run_id"
        ]
        == result["case_id"]
    )
    report = snapshot.json(result["run_id"], "report.json")
    assert report["findings"] and report["assessment"]["action_id"]
    for path in harness.root.rglob("*"):
        if path.is_file():
            assert expected.split("=")[1] not in path.read_text()
            assert expected not in path.read_text()
    resumed = run("Assess Path Traversal", resume_case_id=result["case_id"])
    assert resumed["status"] == "CANDIDATE", resumed
    assert len(active) == 1 and calls == ["/"]


def test_multifamily_operator_task_uses_image_not_generic_product_link(
    discovery_dast,
):
    run, state, _calls, _harness, active = discovery_dast
    state["assessment_body"] = (
        '<a href="/product?productId=1"></a><img src="/read?document=fixture">'
    )
    result = run(
        "Assess this authorized web application for supported information disclosure, "
        "path traversal, and access control vulnerabilities."
    )
    assert result["status"] == "CANDIDATE", result
    assert active and all(
        entries == ("/read?document=fixture",) for entries, *_ in active
    )


def test_discovered_candidate_is_presented_after_parent_publication(
    discovery_dast, monkeypatch
):
    run, state, _, harness, _ = discovery_dast
    presented = []

    def present(value, context, policy):
        presented.append(
            (
                value.reveal_to_host(),
                bool(list(harness.root.rglob("unified_report_receipt.json"))),
                bool(list(harness.root.rglob("case.json"))),
            )
        )
        return True

    monkeypatch.setattr(host.local_cli, "present_sensitive_value", present)
    state["assessment_body"] = '<img src="/retrieve?document=record-canary">'
    result = run("Assess Path Traversal")
    assert result["status"] == "CANDIDATE" and result["complete"], result
    assert result["reproduction"] == "TTY_PRESENTED"
    assert presented == [
        (
            "GET /retrieve?document=record-canary HTTP/1.1\\r\\nHost: example.test",
            True,
            True,
        )
    ]
    for path in harness.root.rglob("*"):
        if path.is_file():
            assert "record-canary" not in path.read_text()


@pytest.mark.parametrize("fault", ["publication", "approval"])
def test_discovered_candidate_never_releases_before_parent_verification(
    discovery_dast, monkeypatch, fault
):
    from beeagent_module.integrations.beescan import case_state

    run, state, _, harness, _ = discovery_dast
    presented = []
    original = case_state.load_case

    def load(storage_dir, case_id):
        if fault == "approval":
            state["dast"]["approval"]["approved"] = False
        if fault == "publication":
            raise ValueError("case_receipt_changed")
        return original(storage_dir, case_id)

    monkeypatch.setattr(case_state, "load_case", load)
    monkeypatch.setattr(
        host.local_cli,
        "present_sensitive_value",
        lambda value, *_: presented.append(value),
    )
    state["assessment_body"] = '<img src="/retrieve?document=record-canary">'
    result = run("Assess Path Traversal")
    assert result["status"] == "ERROR" and not result["complete"], result
    assert result["reason"] == "artifact_incomplete"
    assert presented == []
    for path in harness.root.rglob("*"):
        if path.is_file():
            assert "record-canary" not in path.read_text()


@pytest.mark.parametrize("fault", ["disabled", "unapproved", "expired", "foreign"])
def test_discovered_dast_refuses_without_authority(discovery_dast, fault):
    run, state, calls, _, active = discovery_dast
    state["assessment_body"] = '<img src="/photo?name=one.jpg">'
    if fault == "disabled":
        state["dast"]["enabled"] = False
    elif fault == "unapproved":
        state["dast"]["approval"]["approved"] = False
    elif fault == "expired":
        state["dast"]["approval"]["transport"]["expires_at"] = (
            "2026-01-01T00:00:00+00:00"
        )
        state["dast"]["approval"]["transport"]["valid_from"] = (
            "2025-01-01T00:00:00+00:00"
        )
    else:
        state["target"] = "https://foreign.test"
    result = run("Assess Path Traversal")

    if fault == "disabled":
        assert active == []
        assert calls
    else:
        assert not result["complete"]
        assert active == calls == []


def test_discovered_fixed_target_is_partial(discovery_dast):
    run, state, _, harness, active = discovery_dast
    state.update(
        assessment_body='<img src="/retrieve?document=record-7">', matched=False
    )
    result = run("Assess Path Traversal")
    assert result["status"] == "PARTIAL" and not result["complete"], result
    assert result["reproduction"] == "NOT_AVAILABLE"
    _case, snapshot = load_case(harness.root, result["case_id"])
    assert not snapshot.json(result["run_id"], "report.json")["findings"]
    run("Assess web security", resume_case_id=result["case_id"])
    assert len(active) == 1


def test_discovered_cumulative_budget_prevents_scanner(discovery_dast):
    run, state, _, harness, active = discovery_dast
    harness.config["adaptive"]["max_requests"] = 1
    state["assessment_body"] = '<img src="/retrieve?document=record-7">'
    result = run("Assess web security")
    assert not result["complete"] and result["request_count"] == 1
    assert active == []


def test_discovered_source_substitution_refuses_inspect(discovery_dast):
    run, state, _, harness, _ = discovery_dast
    state["assessment_body"] = '<img src="/retrieve?document=record-7">'
    result = run("Assess Path Traversal")
    case, _ = load_case(harness.root, result["case_id"])
    source_id = case["assessment"]["action"]["entry"]["source_run_id"]
    path = (
        harness.root
        / "runs"
        / source_id
        / "module-beescan"
        / "assessment_observations.json"
    )
    path.write_text('{"entries":[]}')
    with pytest.raises(ValueError):
        load_case(harness.root, result["case_id"])


def test_discovered_case_inspection_in_fresh_process(discovery_dast):
    import subprocess
    import sys

    run, state, _, harness, active = discovery_dast
    state["assessment_body"] = '<img src="/retrieve?document=record-7">'
    result = run("Assess Path Traversal")
    script = (
        "import sys; from beeagent_module.integrations.beescan.case_state import load_case; "
        "state,_=load_case(sys.argv[1],sys.argv[2]); "
        "assert state['status']=='CANDIDATE'; print(state['metrics']['request_count'])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(harness.root), result["case_id"]],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "2"
    assert len(active) == 1


@pytest.mark.parametrize(
    "artifact", ["report.json", "report.md", "investigation_status.json"]
)
def test_discovered_unified_report_tamper(discovery_dast, artifact):
    run, state, _, harness, _ = discovery_dast
    state["assessment_body"] = '<img src="/retrieve?document=record-7">'
    result = run("Assess web security")
    path = harness.root / "runs" / result["run_id"] / "module-beescan" / artifact
    path.write_text("{}")
    with pytest.raises(ValueError):
        load_case(harness.root, result["case_id"])


def test_dast_selection_mode_compatibility_and_fail_fast(discovery_dast):
    from copy import deepcopy

    from beeagent_module.integrations.beescan.dast import DastPolicy

    _, state, _, _, _ = discovery_dast
    raw = deepcopy(state["dast"]["approval"])
    assert DastPolicy.from_config(raw).entries == ()
    legacy = {
        key: value
        for key, value in raw.items()
        if key not in {"entry_selection", "max_candidates"}
    }
    legacy["entries"] = ["/operator?entry=one"]
    assert DastPolicy.from_config(legacy).entry_selection == "exact_entry"
    legacy_without_archive = dict(legacy)
    legacy_without_archive.pop("archive")
    assert DastPolicy.from_config(legacy_without_archive).archive.endswith(
        "/ZAP_2.17.0_Core.zip"
    )
    for change in (
        {"entries": ["/operator?entry=one"]},
        {"max_candidates": True},
        {"max_candidates": 2},
        {"entry_selection": "automatic"},
    ):
        with pytest.raises(ValueError):
            DastPolicy.from_config({**raw, **change})
    raw.pop("max_candidates")
    with pytest.raises(ValueError):
        DastPolicy.from_config(raw)


def test_enabled_dast_without_approval_provisions_but_cannot_execute():
    from beeagent_module.integrations.beescan.dast import (
        _current,
        validate_dast_settings,
    )

    settings = {
        "modules": {"registry": [{"id": "beescan", "enabled": True}]},
        "beescan": {
            "dast": {"enabled": True, "approval": None},
            "investigation": {"trusted_local_enabled": True},
        },
    }
    validate_dast_settings(settings["beescan"], enabled=True)
    with pytest.raises(PermissionError, match="active_dast_not_approved"):
        _current(settings)


def test_discovery_mode_requires_enabled_dast(discovery_dast):
    from beeagent_module.integrations.beescan.discovery_dast import discovery_selected

    _, state, _, _, _ = discovery_dast
    settings = {"beescan": {"dast": state["dast"]}}

    assert discovery_selected(settings)

    state["dast"]["enabled"] = False
    assert not discovery_selected(settings)


@pytest.mark.parametrize("matched", [False, True])
@pytest.mark.parametrize("expire_after_restore", [1, 2])
def test_integrated_deadline_preserves_case_and_accounting(
    discovery_dast, monkeypatch, matched, expire_after_restore
):
    from beeagent_module.integrations.beescan import dast

    run, state, calls, harness, _ = discovery_dast
    state["assessment_body"] = '<img src="/retrieve?document=record-7">'
    state["matched"] = matched
    original_restore = dast._restore
    original_clock = host.time.monotonic
    expired = False
    restores = 0

    def restore(*args, **kwargs):
        nonlocal expired, restores
        result = original_restore(*args, **kwargs)
        restores += 1
        expired = restores >= expire_after_restore
        return result

    monkeypatch.setattr(dast, "_restore", restore)
    monkeypatch.setattr(
        host.time, "monotonic", lambda: original_clock() + (120 if expired else 0)
    )
    result = run("Assess Path Traversal")
    assert result["status"] == "TIMEOUT"
    assert result["reason"] == "investigation_deadline"
    assert result["request_count"] == 2 and calls == ["/"]
    case, snapshot = load_case(harness.root, result["case_id"])
    assert case["status"] == "TIMEOUT" and case["pending"] is False
    assert case["assessment"]["request_count"] == 1
    assert case["metrics"]["request_count"] == 2
    assert snapshot.json(result["run_id"], "report.json")["status"] == "TIMEOUT"


def test_multifamily_partial_traversal_continues_to_disclosure(discovery_dast):
    run, state, calls, harness, active = discovery_dast
    state.update(
        assessment_body=(
            '<form action="/retrieve"><input name="document" value="record-7"></form>'
            '<form action="/other"><input name="file" value="second"></form>'
        ),
        matched=False,
    )
    result = run("Assess web security")
    assert result["status"] == "CANDIDATE", result
    assert len(active) == 2
    assert "/ops/runtime.conf" in calls
    assert len(result["coverage"]["path_traversal"]) == 2
    assert result["coverage"]["information_disclosure"][0]["status"] == "CANDIDATE"
    assert result["coverage"]["access_control"] == []
    case, snapshot = load_case(harness.root, result["case_id"])
    assert case["schema_version"] == 7
    assert case["metrics"]["request_count"] == len(calls) + 2
    assert len(case["findings"]) == 1
    snapshot.verify()
    before = len(calls)
    reused = run("Assess web security", resume_case_id=case["case_id"])
    assert reused["request_count"] == 0
    assert len(calls) == before and len(active) == 2


def test_multifamily_multiple_positive_findings_and_tamper(discovery_dast):
    run, state, _, harness, active = discovery_dast
    state["assessment_body"] = (
        '<form action="/first"><input name="item" value="one"></form>'
        '<form action="/second"><input name="record" value="two"></form>'
    )
    result = run("Assess web security")
    assert result["status"] == "CANDIDATE", result
    case, snapshot = load_case(harness.root, result["case_id"])
    assert len(active) == 2 and len(case["findings"]) == 3
    report = snapshot.json(result["run_id"], "report.json")
    assert report["coverage"] == result["coverage"]
    path = (
        harness.root
        / "runs"
        / case["assessments"][0]["action"]["entry"]["source_run_id"]
        / "module-beescan"
        / "assessment_observations.json"
    )
    path.write_text('{"entries": []}')
    with pytest.raises(ValueError):
        load_case(harness.root, result["case_id"])


def test_multifamily_cumulative_request_and_step_limits(discovery_dast):
    run, state, calls, harness, active = discovery_dast
    harness.config["adaptive"].update(max_requests=3, max_steps=3)
    state["assessment_body"] = (
        '<form action="/first"><input name="item" value="one"></form>'
        '<form action="/second"><input name="record" value="two"></form>'
    )
    result = run("Assess web security")
    assert result["request_count"] <= 3
    assert len(calls) + len(active) == result["request_count"]
    assert result["coverage"]["path_traversal"][-1]["status"] == "PARTIAL"


@pytest.mark.parametrize(
    "access_mode",
    [
        "vulnerable",
        "fixed",
        "budget_deferred",
        "new_source",
        "new_source_after_candidate",
        "failure_ERROR",
        "failure_REFUSED",
        "failure_TIMEOUT",
    ],
)
def test_multifamily_protected_web_review_and_export(
    discovery_dast, tmp_path, monkeypatch, access_mode
):
    from copy import deepcopy

    from beeagent_module.integrations.beescan import detection_runner
    from tests.beescan_access_support import AutonomousApplication, autonomous_profile
    from tests.test_beescan_web import (
        authenticated,
        execute,
        payload,
        setup_app,
        web_report_payload,
        web_review_payload,
    )

    _, scanner_state, _, _, active = discovery_dast
    current, storage, app = setup_app(tmp_path, monkeypatch)
    config = current["beescan"]["investigation"]
    config.update(
        local_lab_enabled=True, trusted_local_enabled=True, timeout_seconds=60
    )
    config["adaptive"].update(enabled=True, max_requests=20, max_steps=16, max_depth=4)
    config["approval"]["transport"].update(
        origin="https://example.test", time_budget_seconds=60
    )
    current["beescan"]["dast"] = scanner_state["dast"]
    target = AutonomousApplication("fixed" if access_mode == "fixed" else "vulnerable")
    if access_mode.startswith("failure_"):
        target = AutonomousApplication("multiple")
        target.mode = "vulnerable"
    for name, token in zip(("A", "B"), target.tokens):
        monkeypatch.setenv("BEEAGENT_ACCESS_" + name, token)
    current["beescan"]["access_control"] = {
        "profiles": [autonomous_profile("https://example.test")]
    }
    if access_mode.startswith("failure_"):
        current["beescan"]["access_control"]["profiles"][0]["discovery_budget"] = 2
    calls = []
    traversal_deferred = access_mode in {
        "budget_deferred",
        "new_source",
        "new_source_after_candidate",
    }

    def capture(
        policy, *, investigation, on_attempt, reauthorize, authentication=None, **kwargs
    ):
        reauthorize()
        if access_mode.startswith("failure_") and len(target.requests) == 10:
            on_attempt(False)
            raise {
                "failure_ERROR": OSError,
                "failure_REFUSED": PermissionError,
                "failure_TIMEOUT": TimeoutError,
            }[access_mode]("controlled_comparison_failure")
        on_attempt(True)
        path = investigation["relative_url"]
        calls.append(path)
        if path == "/" and authentication is None:
            code, body = (
                200,
                '<img src="/photo?name=public.jpg"><a href="/config.txt">source</a>',
            )
            if access_mode in {
                "budget_deferred",
                "new_source",
                "new_source_after_candidate",
            }:
                body += '<a href="/later">later</a>'
        elif path == "/config.txt":
            code, body = 200, 'DB_PASSWORD="private-web-canary"'
        elif path == "/later" and access_mode == "budget_deferred":
            code, body = 200, '<img src="/second?file=fixture">'
        elif access_mode == "new_source" and path == "/" and authentication is not None:
            target.requests.append((path, target.tokens.index(authentication)))
            code, body = (
                200,
                {"identity": target.accounts[target.tokens.index(authentication)]},
            )
        elif (
            access_mode in {"new_source", "new_source_after_candidate"}
            and path == "/later"
        ):
            if authentication is None:
                code, body = 200, '<a href="/later/objects">records</a>'
            else:
                code, body = target.get("/", authentication)
        else:
            code, body = target.get(path, authentication)
        return json.dumps(
            {
                "origin": policy.origin,
                "connected_ip": policy.connected_ip,
                "port": policy.port,
                "method": "GET",
                "relative_url": path,
                "request_count": 1,
                "complete": True,
                "status_code": code,
                "content_type": "text/plain"
                if path == "/config.txt"
                else "text/html"
                if type(body) is str
                else "application/json",
                "body": body if type(body) is str else json.dumps(body),
            }
        ).encode()

    monkeypatch.setattr(detection_runner, "run_detection_provider", capture)
    service = app.state.beeagent_adapter.beescan
    service.reload_settings = lambda: deepcopy(current)
    client, headers = authenticated(app)
    request = {
        **payload(app),
        "target": "https://example.test",
        "task": "Assess web security",
        "mode": "deep",
        "test_profile_id": "controlled-access",
    }
    started = execute(client, headers, request)
    assert started.json()["ok"], started.text
    case_id = started.json()["data"]["case_id"]
    service.executor.submit(lambda: None).result(timeout=30)
    view = service.inspect(case_id, {"user_id": "alice", "role": "operator"})
    expected_status = (
        access_mode.removeprefix("failure_")
        if access_mode.startswith("failure_")
        else "CANDIDATE"
    )
    assert view["status"] == expected_status, view
    assert view["evidence_authenticated"], view
    if access_mode.startswith("failure_"):
        (finding,) = view["findings"]
        assert view["coverage"]["information_disclosure"][0]["finding_ids"] == [
            finding["finding_id"]
        ]
        assert not view["coverage"]["access_control"][-1]["finding_ids"]
        assert not view["coverage"]["path_traversal"] and not active
        assert not view["complete"]
    elif traversal_deferred:
        assert sorted(
            item["finding_id"].split("-", 1)[0] for item in view["findings"]
        ) == ["acf", "df"]
        assert not active and not view["complete"]
        assert view["request_count_exact"] and view["request_count"] == 20
        assert view["coverage_summary"]["path_traversal"]["reason"] == (
            "request_budget_exhausted"
        )
    else:
        assert len(view["findings"]) == (2 if access_mode == "fixed" else 3)
        assert len(active) == 1
        assert all(
            view["coverage"][family]
            for family in ("information_disclosure", "path_traversal", "access_control")
        )
    assert view["coverage"]["access_control"][-1]["status"] == (
        access_mode.removeprefix("failure_")
        if access_mode.startswith("failure_")
        else "PARTIAL"
        if access_mode in {"budget_deferred", "new_source_after_candidate"}
        else "NO_MATCH"
        if access_mode == "fixed"
        else "CANDIDATE"
    )
    if access_mode not in {"budget_deferred", "new_source_after_candidate"}:
        assert view["coverage"]["access_control"][-1]["evidence_refs"]
    saved, snapshot = load_case(storage, case_id)
    if traversal_deferred:
        (assessment,) = saved["assessments"]
        assert assessment["deferred"] == "request_budget_exhausted"
        assert assessment["status"] == "PARTIAL"
        assert assessment["run_id"] is None and not assessment["pending"]
        assert assessment["request_count"] == 0
    if access_mode in {"new_source", "new_source_after_candidate"}:
        assert len(saved["access"]) == 2
        assert [r["source"]["relative_url"] for r in saved["access"]] == ["/", "/later"]
        assert len({r["action_id"] for r in saved["access"]}) == 2
        before_resume = len(calls)
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
        assert resumed.json()["ok"] and resumed.json()["data"]["reused"]
        assert len(calls) == before_resume
        assert (
            sum(
                len(snapshot.json(item["run_id"], "case.json")["state"]["comparisons"])
                for item in saved["access"]
            )
            == 1
        )
    if access_mode.startswith("failure_"):
        assert saved["assessments"] == []
        child = snapshot.json(saved["access"][0]["run_id"], "case.json")["state"]
        (comparison,) = child["comparisons"]
        evidence = snapshot.json(child["case_id"], comparison)["execution"]
        assert evidence["request_count"] == len(evidence["evidence"]) == 6
        assert child["discovery_request_count"] == 2
        assert child["metrics"]["request_count"] == 8
        assert saved["metrics"]["request_count"] == len(calls) == 12
        assert saved["metrics"]["request_count_exact"]
        assert child["status"] == expected_status
    before = len(calls)
    report_identity = None
    for finding in view["findings"]:
        review_payload = web_review_payload(case_id, finding["finding_id"])
        review_payload["evidence_text"] += " Selected finding " + finding["finding_id"]
        reviewed = execute(
            client,
            headers,
            review_payload,
            "beescan_review",
        )
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
        report_identity = (
            finding["finding_id"],
            report.json()["data"]["report_run_id"],
        )
        exported = client.get(
            "/api/beescan/report",
            params={
                "case_id": case_id,
                "finding_id": finding["finding_id"],
                "report_run_id": report.json()["data"]["report_run_id"],
                "format": "json",
                "download": "true",
            },
        )
        assert exported.status_code == 200
    assert len(calls) == before
    if access_mode.startswith("failure_"):
        assert report_identity is not None
        finding_id, report_run_id = report_identity
        from beeagent_module.interfaces.ui.app import build_beeui_app

        restarted = build_beeui_app(
            current, logging.getLogger("failed-comparison-restart"), storage
        )
        restarted_service = restarted.state.beeagent_adapter.beescan
        restarted_service.reload_settings = lambda: deepcopy(current)
        restored, _ = authenticated(restarted)
        assert (
            restored.get(
                "/api/beescan/report",
                params={
                    "case_id": case_id,
                    "finding_id": finding_id,
                    "report_run_id": report_run_id,
                    "format": "json",
                    "download": "true",
                },
            ).status_code
            == 200
        )
        assert len(calls) == before
        restarted_service.executor.shutdown(wait=True)
    assert (
        client.get("/beescan", params={"tab": "results", "run_id": case_id}).status_code
        == 200
    )
    for path in storage.rglob("*.json"):
        assert "private-web-canary" not in path.read_text()
        assert all(token not in path.read_text() for token in target.tokens)
    service.executor.shutdown(wait=True)


def test_multifamily_resume_preserves_sources_and_cumulative_budget(general):
    run, state, calls, harness = general
    state["cancel"] = True
    first = run("Assess web security")
    assert first["status"] == "PARTIAL", first
    saved, _ = load_case(harness.root, first["case_id"])
    original = saved["discovery"]["entries"][0]
    assert saved["discovery"]["terminal"] is False
    state["cancel"] = False
    first_count = len(calls)
    resumed = run("Assess web security", resume_case_id=first["case_id"])
    assert resumed["status"] == "CANDIDATE", resumed
    restored, _ = load_case(harness.root, first["case_id"])
    assert restored["discovery"]["entries"][0] == original
    assert "/" not in calls[first_count:]
    assert restored["metrics"]["request_count"] == len(calls) <= 20


def test_multifamily_rejects_rehashed_inconsistent_coverage(discovery_dast):
    from beeagent_module.integrations.beescan.case_state import digest

    run, state, _, harness, _ = discovery_dast
    state["assessment_body"] = '<img src="/read?file=example">'
    result = run("Assess web security")
    root = harness.root / "runs" / result["run_id"] / "module-beescan"
    marker = json.loads((root / "investigation_status.json").read_text())
    marker["coverage"]["path_traversal"][0]["status"] = "NO_MATCH"
    (root / "investigation_status.json").write_text(json.dumps(marker))
    receipt = json.loads((root / "unified_report_receipt.json").read_text())
    receipt["status_sha256"] = digest(marker)
    (root / "unified_report_receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="multifamily_coverage_changed"):
        load_case(harness.root, result["case_id"])


def test_multifamily_setup_failure_closes_created_egress(general, monkeypatch):
    from beeagent_module.integrations.beescan import egress

    run, _, _, _ = general
    created = []

    def start(session):
        created.append(session)
        raise OSError("controlled_setup_failure")

    monkeypatch.setattr(egress.ManagedEgress, "start", start)
    result = run("Assess web security")
    assert result["status"] == "ERROR"
    assert created and all(session.closed for session in created)
    assert result["request_count"] == 0


def test_multifamily_cli_resume_uses_existing_general_entrypoint(general, capsys):
    from tests.settings_support import read_test_settings

    run, state, calls, harness = general
    state["cancel"] = True
    first = run("Assess web security")
    assert first["status"] == "PARTIAL"
    state["cancel"] = False
    current = read_test_settings()
    current["beescan"]["investigation"].update(harness.config)
    code = probe.handle_beescan_cli(
        ["investigate", "--resume", first["case_id"], "--task", "Assess web security"],
        settings=current,
        reload_settings=lambda: current,
        storage_dir=harness.root,
        logger=logging.getLogger("multifamily-cli"),
        local_operator=state["operator"],
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert code == 5, captured
    assert result["status"] == "CANDIDATE" and not result["complete"]
    assert result["coverage_summary"]["information_disclosure"]["status"] == "CANDIDATE"
    assert result["coverage_summary"]["access_control"]["status"] == "UNSUPPORTED"
    assert calls.count("/") == 1
    saved, _ = load_case(harness.root, first["case_id"])
    assert saved["status"] == "CANDIDATE" and saved["metrics"]["request_count"] == len(
        calls
    )


def test_multifamily_resume_refuses_inexact_request_accounting(general, monkeypatch):
    from beeagent_module.integrations.beescan import detection_runner

    run, _, calls, harness = general
    original = detection_runner.run_detection_provider
    failed = False

    def capture(policy, **kwargs):
        nonlocal failed
        if kwargs["investigation"]["relative_url"] != "/" and not failed:
            failed = True
            kwargs["on_attempt"](None)
            raise OSError("unknown_target_attempt")
        return original(policy, **kwargs)

    monkeypatch.setattr(detection_runner, "run_detection_provider", capture)
    first = run("Assess web security")
    assert first["status"] == "ERROR" and first["request_count_exact"] is False
    saved, _ = load_case(harness.root, first["case_id"])
    assert saved["metrics"]["request_count_exact"] is False
    before = len(calls)
    resumed = run("Assess web security", resume_case_id=first["case_id"])
    assert resumed["status"] == "REFUSED" and resumed["request_count"] == 0
    assert len(calls) == before


def test_multifamily_refuses_destructive_redirect(general, monkeypatch):
    from beeagent_module.integrations.beescan import detection_runner

    run, state, calls, harness = general
    original = detection_runner.run_detection_provider

    def capture(policy, **kwargs):
        if kwargs["investigation"]["relative_url"] == state["root"]:
            kwargs["reauthorize"]()
            kwargs["on_attempt"](True)
            calls.append(state["root"])
            return json.dumps(
                {
                    "origin": policy.origin,
                    "connected_ip": policy.connected_ip,
                    "port": policy.port,
                    "method": "GET",
                    "relative_url": state["root"],
                    "request_count": 1,
                    "status_code": 302,
                    "redirect_location": "/admin/destroy",
                    "complete": True,
                }
            ).encode()
        return original(policy, **kwargs)

    monkeypatch.setattr(detection_runner, "run_detection_provider", capture)
    result = run("Assess web security")
    assert "/admin/destroy" not in calls
    assert result["request_count"] == len(calls)
    saved, _ = load_case(harness.root, result["case_id"])
    assert saved["metrics"]["request_count_exact"]
    assert any(
        item["relative_url"] == state["root"] and item["outcome"] == "refused"
        for item in saved["discovery"]["redirect_resources"]
    )


@pytest.mark.parametrize("fault", ["timeout", "revoked"])
def test_multifamily_child_failure_preserves_completed_findings(
    discovery_dast, monkeypatch, fault
):
    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.detection import _persist

    run, state, calls, harness, active = discovery_dast
    state["assessment_body"] = (
        '<img src="/first?item=one"><img src="/second?record=two">'
    )
    original = dast_runner.run_zap

    def scanner(transport, **kwargs):
        if not active:
            return original(transport, **kwargs)
        if fault == "revoked":
            raise PermissionError("approval_changed")
        _persist(
            kwargs["artifacts"],
            "egress_lifecycle.json",
            {
                "state": "closed",
                "cleanup_verified": True,
                "enforcement_verified": True,
                "assessment_run_id": kwargs["run_id"],
            },
        )
        _persist(
            kwargs["artifacts"],
            "dast_execution_status.json",
            {"cleanup_verified": True, "request_count": 0},
        )
        raise TimeoutError("controlled_child_timeout")

    monkeypatch.setattr(dast_runner, "run_zap", scanner)
    result = run("Assess web security")
    assert result["status"] == ("ERROR" if fault == "revoked" else "CANDIDATE")
    assert len(active) == 1
    saved, snapshot = load_case(harness.root, result["case_id"])
    finding_ids = {finding["finding_id"] for finding in saved["findings"]}
    assert finding_ids == {
        finding_id
        for outcome in saved["outcomes"]
        if outcome["status"] == "CANDIDATE"
        for finding_id in outcome["finding_ids"]
    }
    assert sorted(finding_id.split("-", 1)[0] for finding_id in finding_ids) == [
        "dast",
        "df",
    ]
    assert not result["complete"]
    assert saved["metrics"]["request_count"] == len(calls) + 1
    assert saved["pending"] is (fault == "revoked")
    assert result["coverage"]["path_traversal"][1]["status"] == (
        "ERROR" if fault == "revoked" else "PARTIAL"
    )
    snapshot.verify()
    before = len(calls)
    resumed = run("Assess web security", resume_case_id=result["case_id"])
    if fault == "revoked":
        assert resumed["request_count"] == 0 and len(calls) == before
    assert len(active) == 1
    if fault == "revoked":
        from beeagent_module.integrations.beescan.case_state import digest

        path = harness.root / "runs" / result["case_id"] / "module-beescan/case.json"
        envelope = json.loads(path.read_text())
        envelope["state"]["assessments"][-1]["action_id"] = "assessment-foreign"
        envelope["sha256"] = digest(envelope["state"])
        path.write_text(json.dumps(envelope))
        with pytest.raises(ValueError, match="integrated_source_changed"):
            load_case(harness.root, result["case_id"])


@pytest.mark.parametrize("budget", ["request", "step", "time", "minimum_time"])
def test_multifamily_eligible_budget_stop_is_partial(
    discovery_dast, monkeypatch, budget
):
    from beescan.domain import assessment_selection, general_investigation

    run, state, calls, harness, active = discovery_dast
    state["assessment_body"] = '<img src="/read?file=fixture">'
    if budget == "request":
        harness.config["adaptive"]["max_requests"] = 1
    if budget == "step":
        harness.config["adaptive"]["max_steps"] = 1
    calls_before_minimum = []
    if budget in {"time", "minimum_time"}:
        original_clock = host.time.monotonic
        accepted = False

        if budget == "time":
            original_record = general_investigation.record_surface

            def record(*args):
                nonlocal accepted
                result = original_record(*args)
                accepted = True
                return result

            monkeypatch.setattr(general_investigation, "record_surface", record)
        else:
            original_decide = assessment_selection.decide_verification

            def decide(*args, **kwargs):
                nonlocal accepted
                decision = original_decide(*args, **kwargs)
                if decision.family == "path_traversal":
                    calls_before_minimum[:] = calls
                    accepted = True
                return decision

            monkeypatch.setattr(assessment_selection, "decide_verification", decide)
        monkeypatch.setattr(
            host.time,
            "monotonic",
            lambda: (
                original_clock() + ((61 if budget == "time" else 55) if accepted else 0)
            ),
        )
    result = run("Assess web security")
    reason = {
        "request": "request_budget_exhausted",
        "step": "step_budget_exhausted",
        "minimum_time": "verification_time_insufficient",
    }.get(budget)
    assert active == []
    if budget == "time":
        assert calls == ["/"]
        assert result["status"] == "TIMEOUT" and not result["complete"]
        assert result["reason"] == "investigation_deadline"
        saved, snapshot = load_case(harness.root, result["case_id"])
        assert saved["metrics"]["request_count"] == 1
        assert saved["assessments"] == []
        snapshot.verify()
        return
    assert calls == (calls_before_minimum if budget == "minimum_time" else ["/"])
    assert result["coverage_summary"]["path_traversal"]["status"] == "PARTIAL", result
    assert result["coverage_summary"]["path_traversal"]["reason"] == reason
    assert result["stop_reason"] == reason
    assert result["coverage_summary"]["access_control"]["status"] == "UNSUPPORTED"
    saved, snapshot = load_case(harness.root, result["case_id"])
    assert saved["metrics"]["request_count"] == len(calls)
    assert saved["assessments"][0]["deferred"] == reason
    snapshot.verify()
    if budget == "request":
        from copy import deepcopy

        from beeagent_module.integrations.beescan.discovery_dast import (
            load_multifamily_case,
        )

        substituted = deepcopy(saved)
        substituted["assessments"][0]["deferred"] = "step_budget_exhausted"
        substituted["outcomes"][0]["reason"] = "step_budget_exhausted"
        with pytest.raises(ValueError, match="unproven_verification_budget_stop"):
            load_multifamily_case(substituted, snapshot, result["case_id"])


def test_multifamily_unavailable_profile_is_unsupported(discovery_dast):
    run, state, calls, harness, active = discovery_dast
    state["assessment_body"] = '<img src="/read?file=fixture">'
    state["dast"]["enabled"] = False
    harness.config["adaptive"]["max_requests"] = 1
    result = run("Assess web security")
    assert calls == ["/"] and active == []
    assert result["coverage"]["path_traversal"] == []
    assert result["coverage_summary"]["path_traversal"]["status"] == "UNSUPPORTED"
    load_case(harness.root, result["case_id"])


def test_access_discovery_ignores_valueless_attributes():
    from beeagent_module.integrations.beescan.access_discovery import GetLinks

    parser = GetLinks()
    parser.feed(
        '<link href="/bad" rel><form action="/bad" method>'
        '<input name="x" value="y"></form>'
        '<form action="/search"><input name><input name="missing" value>'
        '<input name="q" value="ok"></form>'
    )
    assert parser.links == ["/search?q=ok"]
