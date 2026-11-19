import hashlib
import json
import logging
from copy import deepcopy
from datetime import timedelta

import pytest
from beeui_module.blocks.chat_workspace import normalize_messages

from beeagent_module.integrations.beescan.progress import investigation_timeline
from beeagent_module.integrations.beescan.web import WebInvestigations, record_failure
from beeagent_module.interfaces.ui.conversation import presentation
from tests import test_beescan_conversation as conversation_tests
from tests import test_beescan_general as general_tests
from tests.test_beescan_web import web_settings

conversation = conversation_tests.conversation
arguments = conversation_tests.arguments
execution = general_tests.execution
settings = general_tests.settings
general = general_tests.general
discovery_dast = general_tests.discovery_dast


def test_live_parent_progress_is_read_only_and_stable(conversation, monkeypatch):
    service, actor, case_id, _ = conversation
    service.conversations.execute(
        "beescan_context",
        {
            **arguments(service, actor, case_id),
            "key": "target",
            "value": "http://app.example.local/",
        },
        actor,
    )
    state = service.conversations.read(case_id, actor)
    child_id = "web-" + "a" * 48
    service.conversations.append(
        state,
        "run",
        {"run_id": child_id, "context_revision": state["context_revision"]},
        "test-progress",
        actor,
    )
    data = {
        "status": "RUNNING",
        "evidence_authenticated": False,
        "timeline": [
            {
                "id": "progress-capture",
                "kind": "capture",
                "status": "incomplete",
                "requests": None,
            }
        ],
    }
    monkeypatch.setattr(service, "inspect", lambda *args, **kwargs: deepcopy(data))
    service.conversations.running.add(child_id)
    before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in service.storage.rglob("*")
        if p.is_file()
    }
    first = service.conversations.view(case_id, actor)
    data["timeline"][0].update(status="authenticated", requests=1)
    second = service.conversations.view(case_id, actor)
    assert first["status"] == second["status"] == "RUNNING"
    assert first["timeline"][0]["requests"] is None
    assert second["timeline"][0]["requests"] == 1
    assert first["timeline"][0]["id"] == second["timeline"][0]["id"]
    for locale in ("ru", "en"):
        messages = presentation(second, locale)["messages"]
        normalize_messages(messages)
        assert len({item["id"] for item in messages}) == len(messages)
        assert all(item.get("kind") not in {"execution", "result"} for item in messages)
        assert messages[0]["text"] == "What is CSRF?"
    service.conversations.running.clear()
    data["status"] = "TIMEOUT"
    restored = WebInvestigations(
        service.storage, service.settings, service.reload_settings
    )
    monkeypatch.setattr(restored, "inspect", lambda *args, **kwargs: deepcopy(data))
    assert restored.conversations.view(case_id, actor)["timeline"] == second["timeline"]
    after = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in service.storage.rglob("*")
        if p.is_file()
    }
    assert before == after
    with pytest.raises(PermissionError):
        restored.conversations.view(case_id, {"user_id": "bob", "role": "operator"})


@pytest.mark.parametrize("terminal", ["TIMEOUT", "ERROR", "REFUSED"])
def test_terminal_progress_preserves_capture_and_safe_stop(tmp_path, terminal):
    owned = {
        "run_id": "web-progress",
        "case_id": "web-progress",
        "target": "https://example.test",
        "mode": "deep",
    }
    status = {
        "status": terminal,
        "reason": "investigation_deadline"
        if terminal == "TIMEOUT"
        else "authorization_refused"
        if terminal == "REFUSED"
        else "execution_incomplete",
        "request_count": 1,
        "request_count_exact": True,
    }
    steps = [
        {
            "step": "discovery",
            "status": "authenticated",
            "request_id": "request-safe",
            "request_count": 1,
            "body": "SECRET_BODY",
        },
        {"step": "resource", "status": "incomplete", "request_count": 0},
    ]
    events = investigation_timeline(tmp_path, owned, status, steps, {}, False)
    assert [event["requests"] for event in events if event["kind"] == "capture"] == [
        1,
        0,
    ]
    assert events[-1]["status"] == terminal and events[-1]["terminal"]
    assert "SECRET_BODY" not in json.dumps(events)
    assert events == investigation_timeline(tmp_path, owned, status, steps, {}, False)


def test_pre_request_failure_log_is_allowlisted(tmp_path, monkeypatch):
    web_settings(monkeypatch)
    run_id = "web-progress"

    def run_detection_provider():
        raise ValueError("PRIVATE-token and response body")

    try:
        run_detection_provider()
    except ValueError as error:
        record_failure(
            tmp_path, logging.getLogger(__name__), run_id, error, "investigation"
        )
    owned = {
        "run_id": run_id,
        "case_id": run_id,
        "target": "https://example.test",
        "mode": "deep",
    }
    status = {
        "status": "ERROR",
        "reason": "execution_incomplete",
        "request_count": 0,
        "request_count_exact": True,
    }
    events = investigation_timeline(tmp_path, owned, status, [], {}, False)
    failure = next(event for event in events if event["kind"] == "failure")
    assert failure["category"] == "validation"
    assert failure["phase"] == "investigation"
    assert failure["reason"] == "execution_incomplete"
    assert "PRIVATE" not in json.dumps(events)
    assert "Traceback" not in json.dumps(events)


def test_pending_verification_is_operational_and_qualified(tmp_path, monkeypatch):
    owned = {
        "run_id": "web-progress",
        "case_id": "web-progress",
        "target": "https://example.test",
        "mode": "deep",
    }
    status = {
        "status": "PARTIAL",
        "reason": "discovery_incomplete",
        "request_count": 1,
        "request_count_exact": False,
    }
    state = {
        "schema_version": 7,
        "pending": True,
        "discovery": {"segments": ["web-progress"]},
        "context": {"spec": {"time_budget_seconds": 45}},
        "assessments": [
            {
                "action_id": "assessment-one",
                "pending": True,
                "request_count": 0,
                "action": {
                    "provider_id": "zap",
                    "profile": "traversal-nonrecursive-v1",
                    "entry": {
                        "source_run_id": "child-safe",
                        "endpoint_path": "/secret?token=PRIVATE",
                    },
                },
            }
        ],
    }
    events = investigation_timeline(tmp_path, owned, status, [], state, False)
    verification = next(event for event in events if event["kind"] == "verification")
    assert verification["qualified"] is True
    assert verification["requests"] is None
    assert not events[-1]["terminal"]
    assert "PRIVATE" not in json.dumps(events)
    assert not any(event["kind"] == "finding" for event in events)
    state["assessments"][0]["run_id"] = "dast-running"
    from beeagent_module.integrations.beescan import progress

    monkeypatch.setattr(
        progress.AssessmentSnapshot,
        "json",
        lambda *args: {
            "status": "RUNNING",
            "request_count": 2,
            "request_count_exact": False,
        },
    )
    events = investigation_timeline(
        tmp_path, owned, status, [], state, False, child_owner=lambda _: owned
    )
    verification = next(event for event in events if event["kind"] == "verification")
    assert verification["status"] == "RUNNING"
    assert verification["requests"] == 2 and verification["exact"] is False
    with pytest.raises(PermissionError, match="web_progress_child_changed"):
        investigation_timeline(
            tmp_path,
            owned,
            status,
            [],
            state,
            False,
            child_owner=lambda _: {**owned, "target": "https://foreign.test"},
        )


def test_expired_child_execution_is_timeout_not_invalid_context(
    discovery_dast, monkeypatch
):
    from beescan.capabilities.dast import DastIntent

    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.detection import _persist

    run, state, _, harness, _ = discovery_dast
    state["assessment_body"] = '<img src="/first?item=one">'
    validate = DastIntent.validate_at
    expired = []

    def validate_at(self, instant):
        if expired and instant != self.started_at:
            instant = self.started_at + timedelta(seconds=self.seconds, microseconds=1)
        return validate(self, instant)

    monkeypatch.setattr(DastIntent, "validate_at", validate_at)

    def scanner(transport, **kwargs):
        _persist(
            kwargs["artifacts"],
            "egress_lifecycle.json",
            {"state": "closed", "cleanup_verified": True, "enforcement_verified": True},
        )
        _persist(
            kwargs["artifacts"],
            "dast_execution_status.json",
            {"cleanup_verified": True, "request_count": 0},
        )
        expired.append(True)
        kwargs["authorize"]()
        raise AssertionError("An expired DAST intent must refuse execution")

    monkeypatch.setattr(dast_runner, "run_zap", scanner)
    result = run("Assess web security")
    handoffs = list(harness.root.glob("runs/dast-*/module-beescan/dast_handoff.json"))
    assert len(handoffs) == 1
    assert json.loads(handoffs[0].read_text())["execution"]["state"] == "timeout"
    assert result["coverage"]["path_traversal"][0]["status"] == "PARTIAL"


def test_conversation_without_session_does_not_override_profile_credentials(
    conversation,
):
    from types import SimpleNamespace

    service, actor, case_id, _ = conversation
    invocation = SimpleNamespace(run_id="web-profile")
    binding = (case_id, {"profile": "approved-profile"}, actor, [])
    service.conversations.pending[invocation.run_id] = binding
    assert service.conversations.resolver(invocation) is None
    assert invocation.conversation_binding == binding
    assert invocation.run_id in service.conversations.running
    service.conversations.pending[invocation.run_id] = (
        case_id,
        {"cookie": "session-reference"},
        actor,
        [],
    )
    assert callable(service.conversations.resolver(invocation))


def test_parent_deadline_after_child_preserves_completed_accounting(
    discovery_dast, monkeypatch
):
    from beescan.domain import assessment_selection

    from beeagent_module.integrations.beescan.case_state import load_case

    run, state, calls, harness, active = discovery_dast
    state["assessment_body"] = '<img src="/first?item=one">'
    original_decide = assessment_selection.decide_verification

    def decide(*args, **kwargs):
        if active:
            raise ValueError("investigation_deadline")
        return original_decide(*args, **kwargs)

    monkeypatch.setattr(assessment_selection, "decide_verification", decide)
    result = run("Assess web security")
    assert (
        result["status"] == "TIMEOUT" and result["reason"] == "investigation_deadline"
    )
    assert len(active) == 1
    assert result["request_count"] == len(calls) + 1
    assert result["request_count_exact"]
    saved, snapshot = load_case(harness.root, result["case_id"])
    (assessment,) = saved["assessments"]
    assert assessment["status"] == "CANDIDATE"
    assert assessment["run_id"] and not assessment["pending"]
    assert assessment["request_count"] == 1
    snapshot.verify()


def test_logical_case_history_keeps_requests_runs_and_conclusions(
    conversation, monkeypatch
):
    service, actor, case_id, _ = conversation
    state = service.conversations.read(case_id, actor)
    original = [item["id"] for item in state["messages"]]
    for index in range(28):
        rid = "web-" + f"{index:048x}"
        for kind, data in (
            (
                "message",
                {
                    "id": "request-" + str(index),
                    "sender": "operator",
                    "text": "Original objective " + str(index),
                    "timestamp": "2026-11-17T12:00:00+00:00",
                    "type": "investigation_request",
                    "source": None,
                },
            ),
            ("run", {"run_id": rid, "context_revision": state["context_revision"]}),
            (
                "message",
                {
                    "id": "conclusion-" + str(index),
                    "sender": "host",
                    "text": "Recorded conclusion " + str(index),
                    "timestamp": "2026-11-17T12:01:00+00:00",
                    "type": "investigation",
                    "source": rid,
                },
            ),
        ):
            service.conversations.append(
                state, kind, data, "history-" + str(index), actor
            )

    def inspect(rid, *args, **kwargs):
        return {
            "run_id": rid,
            "status": "PARTIAL",
            "evidence_authenticated": True,
            "intake": {"target": "https://example.test", "task": "Original objective"},
            "timeline": [
                {
                    "id": rid + "-coverage",
                    "kind": "coverage",
                    "family": "path_traversal",
                    "status": "UNSUPPORTED",
                    "authenticated": True,
                }
            ],
        }

    monkeypatch.setattr(service, "inspect", inspect)
    first = service.conversations.view(case_id, actor, offset=0)
    assert [item["id"] for item in first["messages"][:2]] == original
    entries = [
        item
        for offset in range(0, first["message_count"], 8)
        for item in service.conversations.view(case_id, actor, offset=offset)[
            "messages"
        ]
    ]
    assert len(entries) == len({item["id"] for item in entries}) == 86
    assert [item["id"] for item in entries[2:5]] == [
        "request-0",
        "run-web-" + "0" * 48,
        "conclusion-0",
    ]
    model = presentation(first)
    assert any(
        link["label"] == "Later"
        for item in model["messages"]
        for link in item.get("links", [])
    )
    assert "Authenticated evidence" not in json.dumps(model)
    conclusions = [item for item in model["messages"] if item.get("kind") == "result"]
    assert [item["id"] for item in conclusions] == [
        f"result-web-{number:048x}" for number in range(2)
    ]
    assert all(
        item["name"] == "Result"
        and "tab=results" in item["result"]["href"]
        and not item["text"]
        for item in conclusions
    )
    block = conversation_tests.workspace(service, {"run_id": case_id}, actor)["layout"]
    assert len(block) == 1 and block[0]["type"] == "chat_workspace"
    before = first["message_count"]
    monkeypatch.setattr(
        service,
        "inspect",
        lambda rid, *args, **kwargs: {
            **inspect(rid),
            "timeline": [{"kind": "capture", "status": "authenticated", "requests": 1}]
            * 32,
        },
    )
    assert service.conversations.view(case_id, actor)["message_count"] == before
    restored = WebInvestigations(
        service.storage, service.settings, service.reload_settings
    )
    monkeypatch.setattr(restored, "inspect", inspect)
    assert [
        item["id"]
        for item in restored.conversations.view(case_id, actor, offset=0)["messages"]
    ] == [item["id"] for item in first["messages"]]


def test_contextual_investigation_uses_existing_protected_action(
    conversation, monkeypatch
):
    service, actor, case_id, _ = conversation
    approval = service.settings["beescan"]["investigation"]["approval"]["transport"]
    for key, value in (
        ("target", approval["origin"]),
        ("scope", approval["scope_id"]),
        ("authority", approval["mission_id"]),
    ):
        service.conversations.execute(
            "beescan_context",
            {**arguments(service, actor, case_id), "key": key, "value": value},
            actor,
        )
    state = service.conversations.read(case_id, actor)
    rid = "web-" + "a" * 48
    service.conversations.append(
        state,
        "run",
        {"run_id": rid, "context_revision": state["context_revision"]},
        "source-run",
        actor,
    )
    monkeypatch.setattr(
        service,
        "inspect",
        lambda *args, **kwargs: {
            "run_id": rid,
            "status": "PARTIAL",
            "evidence_authenticated": True,
            "intake": {"target": approval["origin"], "task": "Assess web security"},
            "timeline": [{"kind": "capture", "status": "authenticated", "requests": 1}],
        },
    )
    view = service.conversations.view(case_id, actor)
    assert view["next_actions"] == []
    assert view["next_action_reason"] == "source_bound_continuation_unavailable"
    block = conversation_tests.workspace(service, {"run_id": case_id}, actor)["layout"][
        0
    ]
    assert block["composer"].get("primary") is None
    payload = view["retry_actions"][0]
    assert payload["task"] == "Assess web security (fresh full retry)"
    assert block["context"]["title"] == "Summary"
    assert not any(
        row["id"] == "retry" for row in block["context"]["sections"][0]["items"]
    )
    assert block["context"] == presentation(view)["context"]
    service.settings["beescan"]["investigation"]["web"]["principal_ids"].remove("alice")
    assert not service.conversations.view(case_id, actor)["retry_actions"]
    service.settings["beescan"]["investigation"]["web"]["principal_ids"].append("alice")
    approval["excluded"] = True
    refused = conversation_tests.workspace(service, {"run_id": case_id}, actor)[
        "layout"
    ][0]
    assert refused["composer"].get("primary") is None
    assert not any(
        row.get("focus_primary") for row in refused["context"]["sections"][0]["items"]
    )
    assert "unavailable" in next(
        row["value"]
        for row in refused["context"]["sections"][0]["items"]
        if row["id"] == "next"
    )
    approval["excluded"] = False
    with pytest.raises(PermissionError):
        service.conversations.execute(
            "beescan_investigate", payload, {"user_id": "bob", "role": "operator"}
        )
    with pytest.raises(PermissionError, match="source_changed"):
        service.conversations.execute(
            "beescan_investigate", {**payload, "source_run_id": "web-foreign"}, actor
        )
    calls = []

    def start(action_id, payload, actor):
        calls.append((action_id, payload))
        return {"status": "QUEUED", "run_id": service._run_id(actor, payload["nonce"])}

    monkeypatch.setattr(service, "start", start)
    result = service.conversations.execute("beescan_investigate", payload, actor)
    assert result["case_id"] == case_id
    assert len(service.conversations.read(case_id, actor)["runs"]) == 2
    assert calls[0][0] == "beescan_start"
    with pytest.raises(PermissionError):
        service.conversations.execute("beescan_investigate", payload, actor)


@pytest.mark.parametrize("outcome", ["positive", "negative", "incomplete"])
def test_authenticated_comparison_projection_is_bounded_and_redacted(outcome):
    from types import SimpleNamespace

    from beeagent_module.integrations.beescan.progress import (
        authenticated_observations,
        conversation_run,
    )
    from beeagent_module.interfaces.ui.conversation import observation_text

    facts = [
        {
            "request_sha256": f"{index:064x}",
            "response_sha256": f"{index + 10:064x}",
            "status_code": 200
            if index == 0 or outcome == "positive" and index == 2
            else 404,
            "oracle": outcome == "positive" and index == 2,
        }
        for index in range(2 if outcome == "incomplete" else 5)
    ]
    artifacts = {
        "dast_handoff.json": {
            "outcome": {"matches": ["matched"] if outcome == "positive" else []}
        },
        "dast_evidence.json": {"verification": facts},
    }
    snapshot = SimpleNamespace(json=lambda run_id, name: artifacts[name])
    state = {
        "schema_version": 7,
        "assessments": [
            {
                "pending": False,
                "run_id": "dast-safe",
                "status": "CANDIDATE"
                if outcome == "positive"
                else "PARTIAL"
                if outcome == "incomplete"
                else "NO_MATCH",
                "action": {
                    "profile": "traversal-nonrecursive-v1",
                    "entry": {
                        "endpoint_path": "/read?file=PRIVATE_QUERY",
                        "parameter_names": ["file", "access_token", "PRIVATE;HEADER"],
                        "evidence_refs": ["source-safe"],
                    },
                },
            }
        ],
        "access": [],
        "discovery": {"entries": []},
    }
    projected = authenticated_observations(state, snapshot)
    assert projected[0]["endpoint"] == "/read"
    assert projected[0]["parameters"] == ["file"]
    assert projected[0]["controls_complete"] is (outcome != "incomplete")
    assert projected[0]["missing_control_indexes"] == (
        [2, 3, 4] if outcome == "incomplete" else []
    )
    assert "PRIVATE" not in json.dumps(projected) and "access_token" not in json.dumps(
        projected
    )
    rendered = observation_text(projected[0])
    assert "source-safe" in rendered and "oracle=" in rendered
    assert (
        conversation_run({"status": "PARTIAL", "observations": projected})[
            "observations"
        ]
        == []
    )
