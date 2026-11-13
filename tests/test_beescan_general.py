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
    result = run("Assess web security")
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
    result = run("Assess web security")
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
    result = run("Assess web security")
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
