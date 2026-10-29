import fcntl
import json
import logging
import os
import pty
import select
import termios
from dataclasses import replace
from types import SimpleNamespace

import pytest

from beeagent_module.integrations.beescan import investigation as host
from beeagent_module.integrations.beescan import local_cli
from tests.settings_support import read_test_settings
from tests.test_beescan_investigation import configure_approved
from tests.test_beescan_investigation import editable_dependency as editable_dependency

CANARY = "fixture-private-canary-344-82"
NATURAL_TASK = (
    "Find the debug page exposed by the website and identify the SECRET_KEY "
    "disclosed in its response"
)


@pytest.mark.parametrize(
    "task,expected",
    [
        ("Find diagnostic value field=APP_TOKEN", "APP_TOKEN"),
        ("Получить секрет field=PRIVATE_KEY", "PRIVATE_KEY"),
        (NATURAL_TASK, "SECRET_KEY"),
        ("Identify `CUSTOM_TOKEN`.", "CUSTOM_TOKEN"),
    ],
)
def test_field_is_operator_selected(task, expected):
    assert host.requested_debug_field(task) == expected


@pytest.mark.parametrize(
    "task",
    [
        "Find secret",
        "field=",
        "field=A field=B",
        "field=A field=A",
        "field=A field=",
        "field= field=A",
        "field=A.B",
        "field=A/B",
        "field=" + "A" * 65,
        "field=A\u202e",
        "notfield=A",
        "field=A,field=B",
        "Find SECRET_KEY and OTHER_KEY",
        "Find SECRET_KEY SECRET_KEY",
        "Find SECRET_KEY.other",
        "Find SECRET_KEY/other",
        "Find 1SECRET_KEY",
        "Find " + "A" * 65,
        "Find SECRET_KEY\u202e",
    ],
)
def test_invalid_fields(task):
    with pytest.raises(ValueError, match="invalid_requested_field"):
        host.requested_debug_field(task)


@pytest.fixture
def settings():
    return read_test_settings()


@pytest.fixture
def execution(settings, monkeypatch, tmp_path):
    pytest.importorskip(
        "beescan.domain.debug_disclosure", reason="Reviewed It11 dependency pending"
    )
    from beescan.domain import web_investigation

    monkeypatch.setattr(host, "_load_domain", lambda **_: (web_investigation, "a" * 40))
    policy = configure_approved(settings, monkeypatch)
    config = settings["beescan"]["investigation"]
    config.update(local_lab_enabled=True, trusted_local_enabled=True)
    calls, ai_calls, presentations = [], [], []
    state = {"mode": "positive", "field": "APP_TOKEN"}
    monkeypatch.setattr(
        "beeagent_module.integrations.beescan.http_runner.resolve_addresses",
        lambda *_: ("127.0.0.1",),
    )
    monkeypatch.setattr(
        "beeagent_module.integrations.beescan.http_runner.verify_resolution",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "beeagent_module.integrations.beescan.egress.checkpoint", lambda *_: None
    )

    class Session:
        def __init__(self, policy, *, artifacts, assessment_run_id, seconds):
            self.artifacts = artifacts
            self.closed = False
            self.helper = self.supervisor = SimpleNamespace(poll=lambda: 0)
            self.evidence = {
                "assessment_run_id": assessment_run_id,
                "state": "active",
                "cleanup_verified": False,
                "enforcement_verified": True,
            }

        def start(self):
            pass

        def close(self):
            from beeagent_module.integrations.beescan.detection import _persist

            self.closed = True
            self.evidence.update(
                state="closed", cleanup_verified=state["mode"] != "cleanup"
            )
            _persist(self.artifacts, "egress_lifecycle.json", self.evidence)

    monkeypatch.setattr(
        "beeagent_module.integrations.beescan.egress.ManagedEgress", Session
    )

    def ai(**kwargs):
        ai_calls.append(kwargs)
        if state["mode"] in {"unsupported", "ambiguous_classification"}:
            return json.dumps(
                {
                    "intent": "unsupported"
                    if state["mode"] == "unsupported"
                    else "ambiguous"
                }
            )
        return '{"intent":"debug_page_secret_disclosure"}'

    monkeypatch.setattr(host, "call_structured_ai", ai)

    def capture(transport, *, reauthorize, investigation, on_attempt, deadline):
        reauthorize()
        path = investigation["relative_url"]
        calls.append(path)
        on_attempt(True)
        if path == "/":
            body = "<!-- diagnostic /ops/config.txt -->"
            if state["mode"] == "ambiguous":
                body += "<!-- debug /another.txt -->"
            if state["mode"] == "traversal":
                body = "<!-- diagnostic ../ops/config.txt -->"
            body += "<!-- " + CANARY + " -->"
            media = "text/html"
        else:
            body = state["field"] + "=" + CANARY
            media = "text/plain"
            if state["mode"] == "patched":
                body = "No disclosure"
            if state["mode"] == "cancel":
                raise KeyboardInterrupt
            if state["mode"] == "framing":
                raise ValueError(CANARY)
            if state["mode"] == "revoke":
                config["trusted_local_enabled"] = False
            if state["mode"] == "oversized":
                body = CANARY * 3000
            if state["mode"] == "malformed_table":
                body = (
                    "<table><div><tr><td>APP_TOKEN</td><td>"
                    + CANARY
                    + "</td></tr></div></table>"
                )
                media = "text/html"
        return json.dumps(
            {
                "origin": transport.origin,
                "connected_ip": transport.connected_ip,
                "port": transport.port,
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

    def present(value, context, policy):
        context.verify(policy)
        directory = tmp_path / "runs" / policy.transport.mission_id / "module-beescan"
        marker = json.loads((directory / "investigation_status.json").read_text())
        assert marker["complete"] and marker["status"] == "MATCH"
        lifecycle = json.loads((directory / "egress_lifecycle.json").read_text())
        assert lifecycle["cleanup_verified"]
        presentations.append(value.reveal_to_host())
        return True

    monkeypatch.setattr(local_cli, "present_sensitive_value", present)
    operator = local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL)

    def execute(task="Find the diagnostic field=APP_TOKEN", *, target=None):
        return host.execute_investigation(
            task=host.InvestigationTask(target or policy.transport.origin, task),
            local_operator=operator,
            settings=settings,
            reload_settings=lambda: settings,
            storage_dir=tmp_path,
            logger=logging.getLogger("debug-test"),
        )

    return SimpleNamespace(
        run=execute,
        state=state,
        calls=calls,
        ai=ai_calls,
        shown=presentations,
        root=tmp_path,
        config=config,
    )


@pytest.mark.parametrize(
    "mode,status,count,revealed",
    [
        ("positive", "MATCH", 2, True),
        ("patched", "NO_MATCH", 2, False),
        ("ambiguous", "INCONCLUSIVE", 1, False),
        ("cleanup", "ERROR", 2, False),
        ("cancel", "INCONCLUSIVE", 2, False),
        ("framing", "ERROR", 2, False),
        ("revoke", "REFUSED", 2, False),
        ("oversized", "ERROR", 2, False),
        ("traversal", "INCONCLUSIVE", 1, False),
        ("malformed_table", "INCONCLUSIVE", 2, False),
        ("unsupported", "ERROR", 0, False),
        ("ambiguous_classification", "ERROR", 0, False),
    ],
)
def test_redacted_execution_and_final_gates(
    execution, mode, status, count, revealed, caplog
):
    execution.state["mode"] = mode
    result = execution.run()
    assert result["status"] == status
    assert result["request_count"] == count == len(execution.calls)
    assert result["request_count_exact"]
    assert execution.shown == ([CANARY] if revealed else [])
    assert len(execution.ai) == 1
    assert CANARY not in str(execution.ai) + caplog.text + json.dumps(result)
    for path in execution.root.rglob("*"):
        if path.is_file():
            assert CANARY not in path.read_text()
            if path.name == "source.json":
                record = json.loads(path.read_text())
                assert record["projection"] == "debug-redacted-v1"
                assert "capture" not in record
                assert record["facts"]["excerpt"] == ""
                assert record["facts"]["links"] == []
                assert len(record["source_authentication"]) == 64


def test_invalid_selector_stops_before_capture(execution):
    result = execution.run("Find diagnostic field=A field=B")
    assert result["reason"] == "invalid_requested_field"
    assert result["request_count"] == 0
    assert execution.calls == execution.shown == []


@pytest.mark.parametrize(
    "field,expected", [("SECRET_KEY", "MATCH"), ("APP_TOKEN", "NO_MATCH")]
)
def test_natural_task_uses_only_operator_field(execution, field, expected):
    execution.state["field"] = field
    result = execution.run(NATURAL_TASK)
    assert result["status"] == expected and result["request_count"] == 2
    assert execution.shown == ([CANARY] if expected == "MATCH" else [])
    assert len(execution.ai) == 1 and CANARY not in str(execution.ai)


@pytest.mark.parametrize("local_lab", [False, True])
def test_public_trusted_operator_dispatch(execution, monkeypatch, local_lab):
    execution.config["local_lab_enabled"] = local_lab
    execution.state["field"] = "SECRET_KEY"
    monkeypatch.setattr(
        "beeagent_module.integrations.beescan.http_runner.resolve_addresses",
        lambda *_: ("1.1.1.1",),
    )
    result = execution.run(NATURAL_TASK, target="https://public.example.test")
    assert result["status"] == "MATCH" and result["complete"]
    assert result["integration_status"] == (
        "LABORATORY_ONLY" if local_lab else "COMPLETE"
    )
    assert result["request_count"] == len(execution.calls) == 2
    assert result["execution_context"]["connected_ip"] == "1.1.1.1"
    assert execution.shown == [CANARY]
    assert len(execution.ai) == 1 and CANARY not in str(execution.ai)
    for path in execution.root.rglob("*.json"):
        assert CANARY not in path.read_text()


@pytest.mark.parametrize(
    "fault",
    [
        "no_context",
        "forged_context",
        "identity",
        "policy",
        "private",
        "installation",
        "module",
    ],
)
def test_public_editable_preserves_authentication(
    settings, monkeypatch, editable_dependency, fault
):
    import importlib.metadata
    import sys

    original = configure_approved(settings, monkeypatch)
    policy = replace(
        original,
        transport=replace(
            original.transport,
            origin="https://public.example.test",
            connected_ip="1.1.1.1",
            allow_private_lab=False,
        ),
    )
    operator = local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL)
    context = local_cli._LocalRun(operator, policy)
    if fault == "no_context":
        context = None
    elif fault == "forged_context":
        context = SimpleNamespace()
    elif fault == "identity":
        context = local_cli._LocalRun(replace(operator, identity=(-1, -1, -1)), policy)
    elif fault == "policy":
        policy = replace(policy, transport=replace(policy.transport, approved=False))
    elif fault == "private":
        policy = replace(
            policy,
            transport=replace(
                policy.transport, connected_ip="127.0.0.1", allow_private_lab=True
            ),
        )
        context = local_cli._LocalRun(operator, policy)
    elif fault == "installation":
        monkeypatch.setattr(
            importlib.metadata,
            "distribution",
            lambda _: SimpleNamespace(
                read_text=lambda _: json.dumps(
                    {"url": "file:///tmp/foreign", "dir_info": {"editable": True}}
                )
            ),
        )
    else:
        monkeypatch.setitem(
            sys.modules,
            "beescan.domain.web_investigation",
            SimpleNamespace(__file__="/tmp/foreign/web_investigation.py"),
        )
    with pytest.raises((ImportError, PermissionError)):
        host._load_domain(policy=policy, local_context=context)


@pytest.mark.parametrize(
    "local_lab,revision,integration,complete",
    [
        (True, "editable:/home/bee/Pro/beescan", "LABORATORY_ONLY", True),
        (False, "a" * 40, "COMPLETE", True),
        (False, "editable:/home/bee/Pro/beescan", "LOCAL_EDITABLE", True),
        (False, "editable:/home/bee/Pro/beescan", "PENDING", False),
        (False, "unreviewed", "PENDING", False),
    ],
)
def test_production_it11_gate(
    execution, monkeypatch, local_lab, revision, integration, complete
):
    from beescan.domain import web_investigation

    execution.config["local_lab_enabled"] = local_lab
    monkeypatch.setattr(
        host, "_load_domain", lambda **kwargs: (web_investigation, revision)
    )
    target = "https://public.example.test" if integration == "LOCAL_EDITABLE" else None
    if target:
        monkeypatch.setattr(
            "beeagent_module.integrations.beescan.http_runner.resolve_addresses",
            lambda *_: ("1.1.1.1",),
        )
    result = execution.run(target=target)
    assert result["integration_status"] == integration
    assert result["dependency_revision"] == revision
    assert result["complete"] is complete
    assert result["request_count"] == len(execution.calls) == (2 if complete else 0)
    assert execution.shown == ([CANARY] if complete else [])
    if complete:
        assert result["status"] == "MATCH"
    else:
        assert result["reason"] == "reviewed_it11_revision_unavailable"
    for path in execution.root.rglob("*.json"):
        assert CANARY not in path.read_text()


@pytest.mark.parametrize("redirected", [0, 1, 2])
def test_non_tty_never_reveals(settings, monkeypatch, redirected):
    SensitiveValue = pytest.importorskip(
        "beescan.domain.debug_disclosure"
    ).SensitiveValue
    monkeypatch.setattr(os, "isatty", lambda descriptor: descriptor != redirected)
    monkeypatch.setattr(os, "open", lambda *_: pytest.fail("No terminal write"))
    policy = configure_approved(settings, monkeypatch)
    context = local_cli._LocalRun(
        local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL), policy
    )
    assert (
        local_cli.present_sensitive_value(SensitiveValue(CANARY), context, policy)
        is False
    )


def test_real_controlling_tty_only(settings, monkeypatch):
    SensitiveValue = pytest.importorskip(
        "beescan.domain.debug_disclosure"
    ).SensitiveValue
    policy = configure_approved(settings, monkeypatch)
    master, slave = pty.openpty()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(master)
            os.setsid()
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            for descriptor in (0, 1, 2):
                os.dup2(slave, descriptor)
            context = local_cli._LocalRun(
                local_cli._LocalOperator(local_cli._identity(), local_cli._SEAL), policy
            )
            success = local_cli.present_sensitive_value(
                SensitiveValue(CANARY), context, policy
            )
            os._exit(0 if success else 1)
        except BaseException:
            os._exit(2)
    os.close(slave)
    try:
        assert select.select([master], [], [], 5)[0]
        output = os.read(master, 4096)
        assert output == (CANARY + "\r\n").encode()
        assert os.waitpid(pid, 0)[1] == 0
    finally:
        os.close(master)


@pytest.mark.parametrize("fault", ["source", "publication"])
def test_artifact_verification_precedes_release(execution, monkeypatch, fault):
    from beeagent_module.integrations.beescan import detection

    original = detection._persist
    failed = False

    def persist(api, name, value):
        nonlocal failed
        if fault == "source" and name == "source.json":
            value = dict(value, response_id="substituted-source")
        if (
            fault == "publication"
            and name == "investigation_status.pending.json"
            and not failed
        ):
            failed = True
            raise OSError(CANARY)
        return original(api, name, value)

    monkeypatch.setattr(detection, "_persist", persist)
    result = execution.run()
    assert result["status"] == "ERROR" and not result["complete"]
    assert execution.shown == []
    for path in execution.root.rglob("*.json"):
        assert CANARY not in path.read_text()


def test_missing_it11_never_claims_complete_integration(execution, monkeypatch):
    def unavailable(domain):
        raise ImportError("missing It11")

    monkeypatch.setattr(host, "_load_debug_domain", unavailable)
    result = execution.run()
    assert result["integration_status"] == "PENDING"
    assert result["reason"] == "reviewed_it11_revision_unavailable"
    assert result["request_count"] == 0 and execution.shown == []


def test_published_artifact_tampering_blocks_terminal_release(execution, monkeypatch):
    from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot

    original = AssessmentSnapshot.verify
    checks = 0

    def verify(snapshot):
        nonlocal checks
        markers = [
            run for run, name in snapshot.files if name == "investigation_status.json"
        ]
        if markers:
            checks += 1
            if checks == 2:
                path = (
                    execution.root
                    / "runs"
                    / markers[0]
                    / "module-beescan"
                    / "report.json"
                )
                path.write_text("{}")
        return original(snapshot)

    monkeypatch.setattr(AssessmentSnapshot, "verify", verify)
    result = execution.run()
    assert checks >= 2
    assert result["status"] == "ERROR" and not result["complete"]
    assert result["reason"] == "artifact_incomplete"
    assert execution.shown == []
