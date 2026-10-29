import json
import logging
from types import SimpleNamespace

import pytest

from beeagent_module.integrations.beescan import investigation as host
from beeagent_module.integrations.beescan import local_cli
from beeagent_module.integrations.beescan.case_state import load_case
from tests import test_beescan_debug_disclosure as debug_tests

execution = debug_tests.execution
settings = debug_tests.settings

pytest.importorskip(
    "beescan.domain.investigation_case",
    reason="Reviewed It12 dependency pending; use paired local source for development",
)


@pytest.fixture
def adaptive(execution, monkeypatch):
    execution.config["adaptive"].update(enabled=True, max_steps=2, max_requests=6)
    state = {"root": "both", "cancel": False, "negative": True}
    calls = []

    def capture(policy, *, reauthorize, investigation, on_attempt, deadline):
        reauthorize()
        path = investigation["relative_url"]
        calls.append(path)
        on_attempt(True)
        if state["cancel"] and path != "/":
            raise KeyboardInterrupt
        if path == "/":
            body = ""
            if state["root"] in {"both", "framework"}:
                body += (
                    '<a href="'
                    + state.get("resource", "/unfamiliar/record?entry=852")
                    + '">View</a>'
                )
            if state["root"] in {"both", "debug"}:
                body += "<!-- diagnostic /unfamiliar/support.txt -->"
            body += "<!-- private-adaptive-canary -->"
            media = "text/html"
        elif path.endswith("support.txt"):
            body, media = "APP_TOKEN=private-adaptive-canary", "text/plain"
        else:
            body, media = "Ordinary bounded response", "text/plain"
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
    monkeypatch.setattr(local_cli, "present_sensitive_value", lambda *args: True)
    monkeypatch.setattr(
        host,
        "call_structured_ai",
        lambda **kwargs: '{"objective":"supported_disclosures"}',
    )
    operator = local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL)

    def run(resume=None, task="Investigate disclosures field=APP_TOKEN"):
        from tests.settings_support import read_test_settings

        current = read_test_settings()
        current["beescan"]["investigation"].update(execution.config)
        return host.execute_investigation(
            task=host.InvestigationTask("http://127.0.0.1:18080", task),
            local_operator=operator,
            settings=current,
            reload_settings=lambda: current,
            storage_dir=execution.root,
            logger=logging.getLogger("adaptive-test"),
            adaptive=True,
            resume_case_id=resume,
        )

    return SimpleNamespace(run=run, state=state, calls=calls, execution=execution)


def test_negative_result_selects_other_existing_family(adaptive):
    result = adaptive.run()
    assert result["status"] == "MATCH", result
    assert result["request_count"] == 6 == len(adaptive.calls)
    state, _ = load_case(adaptive.execution.root, result["case_id"])
    assert [step["outcome"]["status"] for step in state["outcomes"]] == [
        "no_match",
        "match",
    ]
    assert state["metrics"]["request_count"] == 6
    assert state["metrics"]["ai_calls"] == 1
    assert state["metrics"]["tokens"] is state["metrics"]["cost"] is None
    assert state["terminal"] and not state["pending"]
    for path in adaptive.execution.root.rglob("*.json"):
        assert "private-adaptive-canary" not in path.read_text()


@pytest.mark.parametrize(
    "root,family,count",
    [
        ("framework", "framework_version_disclosure", 4),
        ("debug", "debug_page_secret_disclosure", 3),
        ("none", None, 1),
    ],
)
def test_discovery_changes_selection(adaptive, root, family, count):
    adaptive.state["root"] = root
    result = adaptive.run()
    assert result["request_count"] == count, result
    state, _ = load_case(adaptive.execution.root, result["case_id"])
    assert (
        state["outcomes"][0]["outcome"]["task_family"] if state["outcomes"] else None
    ) == family


def test_resume_reuses_sufficient_completed_action(adaptive):
    adaptive.execution.config["adaptive"]["max_steps"] = 1
    first = adaptive.run()
    assert first["request_count"] == 4
    state, _ = load_case(adaptive.execution.root, first["case_id"])
    assert not state["terminal"]
    assert state["outcomes"][0]["outcome"]["sufficient"]
    adaptive.calls.clear()
    second = adaptive.run(first["case_id"])
    assert second["status"] == "MATCH", second
    assert second["request_count"] == len(adaptive.calls) == 3
    assert not any("entry=" in path for path in adaptive.calls)
    resumed, _ = load_case(adaptive.execution.root, first["case_id"])
    assert len(resumed["segments"]) == 2
    assert resumed["metrics"]["request_count"] == 7


def test_corrupt_checkpoint_and_missing_source_refuse(adaptive):
    adaptive.execution.config["adaptive"]["max_steps"] = 1
    first = adaptive.run()
    path = (
        adaptive.execution.root / "runs" / first["case_id"] / "module-beescan/case.json"
    )
    envelope = json.loads(path.read_text())
    envelope["state"]["outcomes"][0]["outcome"]["status"] = "match"
    path.write_text(json.dumps(envelope))
    adaptive.calls.clear()
    result = adaptive.run(first["case_id"])
    assert not result["complete"] and adaptive.calls == []
    with pytest.raises(ValueError):
        load_case(adaptive.execution.root, first["case_id"])


def test_interrupted_step_is_not_reused(adaptive):
    adaptive.state["cancel"] = True
    first = adaptive.run()
    assert first["status"] == "INCONCLUSIVE"
    state, _ = load_case(adaptive.execution.root, first["case_id"])
    assert not state["outcomes"] and not state["terminal"]
    adaptive.state["cancel"] = False
    second = adaptive.run(first["case_id"])
    assert second["status"] == "MATCH", second
    assert second["request_count"] == 6


def test_resume_does_not_change_requested_field(adaptive):
    adaptive.execution.config["adaptive"]["max_steps"] = 1
    first = adaptive.run()
    adaptive.calls.clear()
    second = adaptive.run(first["case_id"], task="Investigate field=OTHER")
    assert second["status"] == "REFUSED" and adaptive.calls == []


@pytest.mark.parametrize("budget,expected", [(1, 1), (3, 3), (4, 4), (6, 6)])
def test_actual_budget_constrains_capability_availability(adaptive, budget, expected):
    adaptive.execution.config["adaptive"]["max_requests"] = budget
    result = adaptive.run()
    assert result["request_count"] == len(adaptive.calls) == expected
    assert result["metrics"]["request_count_exact"]


@pytest.mark.parametrize(
    "fault", ["missing_source", "changed_source", "pending", "destination", "authority"]
)
def test_resume_rechecks_evidence_and_authority(adaptive, monkeypatch, fault):
    adaptive.execution.config["adaptive"]["max_steps"] = 1
    first = adaptive.run()
    state, _ = load_case(adaptive.execution.root, first["case_id"])
    if fault in {"missing_source", "changed_source"}:
        child = state["outcomes"][0]["sources"][0]["run_id"]
        path = adaptive.execution.root / "runs" / child / "module-beescan/source.json"
        if fault == "missing_source":
            path.unlink()
        else:
            record = json.loads(path.read_text())
            record["facts"]["status_code"] = 500
            path.write_text(json.dumps(record))
    elif fault == "pending":
        from beeagent_module.integrations.beescan.case_state import digest

        path = (
            adaptive.execution.root
            / "runs"
            / first["case_id"]
            / "module-beescan/case.json"
        )
        envelope = json.loads(path.read_text())
        envelope["state"]["pending"] = True
        envelope["sha256"] = digest(envelope["state"])
        path.write_text(json.dumps(envelope))
    elif fault == "destination":
        monkeypatch.setattr(
            "beeagent_module.integrations.beescan.http_runner.resolve_addresses",
            lambda *_: ("127.0.0.2",),
        )
    else:
        adaptive.execution.config["trusted_local_enabled"] = False
    adaptive.calls.clear()
    second = adaptive.run(first["case_id"])
    assert not second["complete"] and second["status"] in {"ERROR", "REFUSED"}
    assert adaptive.calls == []


def test_ai_executable_parameters_fail_before_discovery(adaptive, monkeypatch):
    monkeypatch.setattr(
        host,
        "call_structured_ai",
        lambda **kwargs: (
            '{"objective":"supported_disclosures","url":"https://foreign.test","method":"POST"}'
        ),
    )
    result = adaptive.run()
    assert result["status"] == "ERROR" and result["request_count"] == 0
    assert result["metrics"]["ai_calls"] == 1
    assert adaptive.calls == []


def test_rejected_objective_resume_preserves_checkpoint(adaptive, monkeypatch):
    adaptive.state["cancel"] = True
    first = adaptive.run()
    path = (
        adaptive.execution.root / "runs" / first["case_id"] / "module-beescan/case.json"
    )
    original = path.read_bytes()
    adaptive.state["cancel"] = False
    adaptive.calls.clear()
    monkeypatch.setattr(
        host,
        "call_structured_ai",
        lambda **kwargs: '{"objective":"debug_page_secret_disclosure"}',
    )
    second = adaptive.run(first["case_id"])
    assert second["status"] == "REFUSED"
    assert adaptive.calls == []
    assert path.read_bytes() == original


@pytest.mark.parametrize("root", ["both", "framework"])
def test_case_tampering_after_readback_blocks_sensitive_release(
    adaptive, monkeypatch, root
):
    from beeagent_module.integrations.beescan import detection

    adaptive.state["root"] = root
    original = detection._persist
    marker_count = 0
    presented = []

    def persist(api, name, data):
        nonlocal marker_count
        path = original(api, name, data)
        if name == "investigation_status.pending.json":
            marker_count += 1
            if marker_count == 2:
                (api.artifact_dir() / "case.json").write_text("corrupted")
        return path

    monkeypatch.setattr(detection, "_persist", persist)
    monkeypatch.setattr(
        local_cli, "present_sensitive_value", lambda *args: presented.append(True)
    )
    result = adaptive.run()
    assert marker_count >= 2
    assert result["status"] == "ERROR"
    assert not result["complete"]
    assert presented == []


def test_resume_refuses_non_equivalent_resource(adaptive):
    adaptive.execution.config["adaptive"]["max_steps"] = 1
    first = adaptive.run()
    adaptive.state["resource"] = "/other/resource?item=9"
    adaptive.calls.clear()
    result = adaptive.run(first["case_id"])
    assert result["status"] == "INCONCLUSIVE", result
    assert result["reason"] == "evidence_not_equivalent"
    assert adaptive.calls == ["/"]
    state, _ = load_case(adaptive.execution.root, first["case_id"])
    assert state["metrics"]["request_count"] == 5
    assert len(state["outcomes"]) == 1
    assert "new authorized Case" in result["next_actions"][0]
