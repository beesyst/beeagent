import importlib.util
import json
import logging
import os
import random
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from beeagent_module.core import beescan_detection as host
from beeagent_module.core import beescan_detection_runner as runner
from beeagent_module.core.beescan_detection_policy import (
    NUCLEI_SHA256,
    NUCLEI_VERSION,
    TEMPLATE_SHA256,
    DetectionPolicy,
)
from beeagent_module.core.beescan_policy import validate_beescan_settings


@pytest.fixture
def approved(tmp_path):
    from beescan.capabilities.http_probe import (
        HostProvenance,
        HttpFacts,
        HttpProbeIntent,
        HttpProbeOutcome,
        normalize_http_observation,
    )
    from beesdk.capabilities import CapabilityStatus

    now = datetime.now(UTC)
    probe = HttpProbeIntent(
        "mission", "target", "http://127.0.0.1:18080", 1, 5, "test-head", "1"
    )
    provenance = HostProvenance("source-run", "test-head", "1")
    facts = HttpFacts(
        probe.origin, True, 200, None, provenance, ("source-evidence",), True
    )
    observation = normalize_http_observation(
        probe,
        HttpProbeOutcome(
            "mission",
            "target",
            CapabilityStatus.OK,
            "ok",
            facts.evidence_refs,
            provenance,
        ),
        facts,
    )
    policy = DetectionPolicy(
        operator_uid=os.getuid(),
        project_id="project",
        scope_id="scope",
        mission_id="mission",
        target_id="target",
        origin=probe.origin,
        approved=True,
        excluded=False,
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
        method="restricted_detection",
        request_budget=1,
        time_budget_seconds=5,
        connected_ip="127.0.0.1",
        allow_private_lab=True,
        executable="/opt/beescan/nuclei",
        sha256=NUCLEI_SHA256,
        provider_version=NUCLEI_VERSION,
        network_namespace="/proc/12345/ns/net",
        user_namespace="/proc/12345/ns/user",
        memory_mb=3072,
        output_bytes=8192,
        source_run_id="source-run",
        source_observation_id=observation.observation_id,
        provider_id="nuclei",
        profile="http-marker-v1",
        template_id="beescan-http-marker",
        template_version="1",
        template_path=str(
            Path(__file__).resolve().parents[1] / "config/beescan-http-marker.yaml"
        ),
        template_sha256=TEMPLATE_SHA256,
    )
    directory = tmp_path / "runs/source-run/module-beescan"
    directory.mkdir(parents=True)
    objects = {
        "http_observation.json": {"schema_version": 1, **asdict(observation)},
        "source-evidence.json": {"schema_version": 1, **asdict(facts)},
        "http_probe_status.json": {
            "schema_version": 1,
            "run_id": "source-run",
            "status": "ok",
            "complete": True,
            "project_id": "project",
            "scope_id": "scope",
            "mission_id": "mission",
            "target_id": "target",
            "provenance": asdict(provenance),
            "evidence_refs": list(facts.evidence_refs),
        },
    }
    for name, data in objects.items():
        path = directory / name
        path.write_text(json.dumps(data))
        path.chmod(0o600)
    return policy, observation, tmp_path


def settings_for(policy):
    values = asdict(policy)
    for key in ("valid_from", "expires_at"):
        values[key] = values[key].isoformat()
    return {
        "modules": {"registry": [{"id": "beescan", "enabled": True}]},
        "beescan": {
            "probe_enabled": False,
            "approval": None,
            "detection_enabled": True,
            "detection_approval": values,
        },
    }


def captured(marker="present"):
    return {
        "origin": "http://127.0.0.1:18080",
        "connected_ip": "127.0.0.1",
        "port": 18080,
        "method": "GET",
        "request_count": 1,
        "status_code": 200,
        "marker_header": marker,
        "complete": True,
    }


def output(capture):
    names = (
        ["completed", "marker"]
        if capture["marker_header"] == "present"
        else ["completed"]
    )
    return b"\n".join(
        json.dumps(
            {
                "template-id": "beescan-http-marker",
                "template-path": "/template.yaml",
                "info": {
                    "name": "BeeScan restricted HTTP marker",
                    "author": ["beesyst"],
                    "tags": None,
                    "severity": "info",
                    "metadata": {"version": "1"},
                },
                "type": "",
                "path": runner.safe_response(capture),
                "matched-at": "/input.txt",
                "matcher-status": True,
                "matcher-name": name,
                "timestamp": "2026-10-15T00:00:00Z",
            }
        ).encode()
        for name in names
    )


def execute(policy, root):
    settings = settings_for(policy)
    return host.execute_approved_detection(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("test-bs2"),
    )


@pytest.mark.parametrize("marker", ["present", "absent", None])
def test_complete_domain_pipeline_and_one_shot(approved, monkeypatch, marker):
    if importlib.util.find_spec("beescan.capabilities.detection") is None:
        pytest.fail("Run BS-2 feature contracts in the isolated It5 environment")
    policy, observation, root = approved
    capture = captured(marker)
    calls = []
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)

    def provider(policy, *, reauthorize):
        reauthorize()
        calls.append(policy)
        return output(capture), capture

    monkeypatch.setattr(host, "run_detection_provider", provider)
    status = execute(policy, root)
    assert status["status"] == ("matched" if marker == "present" else "no_match")
    assert status["complete"] is True and len(calls) == 1
    directory = root / "runs" / status["run_id"] / "module-beescan"
    candidates = json.loads((directory / "detection_candidates.json").read_text())[
        "candidates"
    ]
    assert len(candidates) == (1 if marker == "present" else 0)
    if candidates:
        assert candidates[0]["finding"]["status"] == "candidate"
        assert candidates[0]["finding"]["verification_refs"] == []
    intent = policy.intent(observation, at=datetime.now(UTC))
    caller = host.GovernedDetectionCaller(
        policy=policy,
        reload_policy=lambda: policy,
        observation=observation,
        storage_dir=root,
        run_id="test-run",
        artifacts=SimpleNamespace(
            write_json=lambda *args: pytest.fail("unexpected evidence")
        ),
    )
    assert caller.call("wrong", intent.payload).status.value == "refused"
    assert (
        caller.call(intent.capability_name, intent.payload).diagnostics["reason"]
        == "request_budget_exceeded"
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("request_budget", 2),
        ("request_budget", True),
        ("time_budget_seconds", 0),
        ("memory_mb", 100),
        ("output_bytes", 100000),
        ("sha256", "0" * 64),
        ("provider_version", "latest"),
        ("profile", "headless"),
        ("template_id", "custom"),
        ("template_sha256", "0" * 64),
        ("origin", "http://127.0.0.1:18080/path"),
        ("origin", "http://user@127.0.0.1"),
        ("connected_ip", "0.0.0.0"),
        ("allow_private_lab", False),
        ("user_namespace", "/proc/12346/ns/user"),
        ("executable", "/opt/../tmp/tool"),
        ("approved", 1),
    ],
)
def test_policy_rejects_unsafe_inputs(approved, key, value):
    policy, _, _ = approved
    with pytest.raises(ValueError):
        replace(policy, **{key: value})


@pytest.mark.parametrize(
    "change",
    [
        {"excluded": True},
        {"approved": False},
        {"operator_uid": os.getuid() + 1},
        {"expires_at": datetime.now(UTC) - timedelta(seconds=1)},
        {"source_run_id": "other-run"},
        {"source_observation_id": "other-observation"},
    ],
)
def test_authorization_refusals_make_no_requests(approved, monkeypatch, change):
    policy, _, root = approved
    monkeypatch.setattr(
        host,
        "run_detection_provider",
        lambda *args, **kwargs: pytest.fail("unauthorized execution"),
    )
    status = execute(replace(policy, **change), root)
    assert status["complete"] is False and status["evidence_refs"] == []


@pytest.mark.parametrize(
    "filename",
    ["http_observation.json", "http_probe_status.json", "source-evidence.json"],
)
@pytest.mark.parametrize(
    "mode", ["missing", "symlink", "oversized", "malformed", "writable"]
)
def test_source_artifacts_fail_closed(approved, filename, mode):
    policy, _, root = approved
    path = root / "runs/source-run/module-beescan" / filename
    if mode == "missing":
        path.unlink()
    elif mode == "symlink":
        target = root / "elsewhere"
        path.rename(target)
        path.symlink_to(target)
    elif mode == "writable":
        path.chmod(0o666)
    else:
        path.write_bytes(
            b"x" * 32769 if mode == "oversized" else b'{"duplicate":1,"duplicate":2}'
        )
    with pytest.raises((OSError, ValueError, TypeError, KeyError)):
        host.load_source(root, policy)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "extra",
        "duplicate",
        "incomplete",
        "authority",
        "provenance",
        "severity",
        "destination",
        "type",
        "oversized",
        "timestamp",
        "completion-only",
        "match-only",
    ],
)
def test_untrusted_output_rejected(kind):
    capture = captured()
    records = [json.loads(line) for line in output(capture).splitlines()]
    if kind == "empty":
        raw = b""
    elif kind == "duplicate":
        raw = b'{"template-id":"a","template-id":"b"}'
    elif kind == "oversized":
        raw = b"x" * 8193
    else:
        if kind == "extra":
            records.append(records[0])
        elif kind == "incomplete":
            records[0]["matcher-status"] = False
        elif kind in {"authority", "provenance"}:
            records[0][kind] = "forged"
        elif kind == "severity":
            records[0]["info"]["severity"] = "critical"
        elif kind == "destination":
            records[0]["matched-at"] = "http://evil.test"
        elif kind == "type":
            records[0]["matcher-status"] = 1
        elif kind == "timestamp":
            records[0]["timestamp"] = "yesterday"
        elif kind == "completion-only":
            records = records[:1]
        elif kind == "match-only":
            records = records[1:]
        raw = b"\n".join(json.dumps(record).encode() for record in records)
    with pytest.raises(ValueError):
        host.parse_detection_output(raw, capture, limit=8192)


def test_parser_bounded_fuzz():
    generator = random.Random(304)
    for _ in range(500):
        raw = generator.randbytes(generator.randrange(4096))
        with pytest.raises(ValueError):
            host.parse_detection_output(raw, captured(), limit=8192)


@pytest.mark.parametrize(
    "point",
    [
        "detection-evidence-",
        "detection_intent.json",
        "detection_outcome.json",
        "detection_candidates.json",
        "detection_status.pending.json",
    ],
)
def test_partial_artifact_writes_never_complete(approved, monkeypatch, point):
    policy, _, root = approved
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)
    monkeypatch.setattr(
        host,
        "run_detection_provider",
        lambda *args, **kwargs: (output(captured()), captured()),
    )
    original = host.ArtifactAPI.write_json

    def failed(self, name, data):
        if name.startswith(point):
            raise OSError("test persistence failure")
        return original(self, name, data)

    monkeypatch.setattr(host.ArtifactAPI, "write_json", failed)
    try:
        status = execute(policy, root)
        assert status["complete"] is False
    except OSError:
        pass
    statuses = list(root.glob("runs/run-*/module-beescan/detection_status.json"))
    assert len(statuses) == 1
    assert json.loads(statuses[0].read_text())["complete"] is False


def test_current_approval_and_source_rechecked(approved, monkeypatch):
    policy, observation, root = approved
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)
    intent = policy.intent(observation, at=datetime.now(UTC))
    caller = host.GovernedDetectionCaller(
        policy=policy,
        reload_policy=lambda: replace(policy, approved=False),
        observation=observation,
        storage_dir=root,
        run_id="run-test",
        artifacts=None,
    )
    monkeypatch.setattr(
        host,
        "run_detection_provider",
        lambda *args, **kwargs: pytest.fail("changed approval executed"),
    )
    assert (
        caller.call(intent.capability_name, intent.payload).diagnostics["reason"]
        == "approval_or_source_changed"
    )


def test_source_changed_during_execution_refuses(approved, monkeypatch):
    policy, _, root = approved
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)
    executed = []

    def provider(policy, *, reauthorize):
        path = root / "runs/source-run/module-beescan/source-evidence.json"
        path.write_text("{}")
        reauthorize()
        executed.append(True)
        return output(captured()), captured()

    monkeypatch.setattr(host, "run_detection_provider", provider)
    result = execute(policy, root)
    assert not result["complete"] and executed == []


@pytest.mark.parametrize(
    "error,expected",
    [
        (OSError("cleanup failed"), "error"),
        (TimeoutError(), "timeout"),
        (ValueError("output_limit"), "error"),
    ],
)
def test_cleanup_and_timeout_failures(approved, monkeypatch, error, expected):
    policy, _, root = approved
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)

    def failed(*args, **kwargs):
        raise error

    monkeypatch.setattr(host, "run_detection_provider", failed)
    result = execute(policy, root)
    assert result["status"] == expected and not result["complete"]
    assert result["evidence_refs"] == []


def test_candidates_require_independent_human_review(approved, monkeypatch):
    from beescan.capabilities import detection
    from beescan.domain.triage import HostReview, ReviewDisposition, review_finding

    policy, _, root = approved
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)
    monkeypatch.setattr(
        host,
        "run_detection_provider",
        lambda *args, **kwargs: (output(captured()), captured()),
    )
    saved = []
    original = detection.correlate_detections

    def correlate(outcomes):
        candidates = original(outcomes)
        saved.extend(candidates)
        return candidates

    monkeypatch.setattr(detection, "correlate_detections", correlate)
    result = execute(policy, root)
    assert result["status"] == "matched" and len(saved) == 1
    candidate = saved[0]
    review = HostReview(
        "review",
        candidate.finding.finding_id,
        policy.mission_id,
        policy.target_id,
        "reviewer",
        datetime.now(UTC),
        True,
        tuple(result["evidence_refs"]),
    )
    with pytest.raises(ValueError, match="independent"):
        review_finding(
            candidate,
            ReviewDisposition.VERIFIED,
            decision_basis="scanner evidence only",
            host_review=review,
        )
    assert candidate.finding.status.value == "candidate"


@pytest.mark.parametrize(
    "key,value",
    [
        ("detection_enabled", "true"),
        ("detection_approval", {}),
        ("detection_approval", None),
    ],
)
def test_settings_fail_fast(approved, key, value):
    policy, _, _ = approved
    settings = settings_for(policy)
    settings["beescan"][key] = value
    with pytest.raises(RuntimeError):
        validate_beescan_settings(settings)


def test_disabled_settings_preserve_old_contract():
    settings = {
        "modules": {"registry": []},
        "beescan": {
            "probe_enabled": False,
            "approval": None,
            "detection_enabled": False,
            "detection_approval": None,
        },
    }
    validate_beescan_settings(settings)
    del settings["beescan"]["detection_enabled"]
    with pytest.raises(RuntimeError):
        validate_beescan_settings(settings)


def test_template_integrity_and_symlink(approved, tmp_path):
    policy, _, _ = approved
    path = tmp_path / "template.yaml"
    path.write_text("untrusted")
    path.chmod(0o600)
    with pytest.raises(PermissionError):
        runner.snapshot_template(replace(policy, template_path=str(path)), tmp_path)
    path.unlink()
    path.symlink_to(policy.template_path)
    with pytest.raises(PermissionError):
        runner.snapshot_template(replace(policy, template_path=str(path)), tmp_path)


def test_namespace_cleanup_closes_user_even_if_net_close_fails(approved, monkeypatch):
    policy, _, _ = approved
    user_fd = os.open("/dev/null", os.O_RDONLY)
    net_fd = os.open("/dev/null", os.O_RDONLY)
    descriptors = iter((user_fd, net_fd))
    original_close = os.close
    monkeypatch.setattr(
        runner.Path, "stat", lambda self: SimpleNamespace(st_uid=0, st_mode=0)
    )
    monkeypatch.setattr(runner.os, "access", lambda *args: True)
    monkeypatch.setattr(runner, "_open_namespace", lambda *args: next(descriptors))
    monkeypatch.setattr(runner.fcntl, "ioctl", lambda *args: os.dup(user_fd))
    monkeypatch.setattr(runner, "bounded_process", lambda *args, **kwargs: (1, b""))

    def failed_close(descriptor):
        if descriptor == net_fd:
            raise OSError("injected network namespace close error")
        original_close(descriptor)

    monkeypatch.setattr(runner.os, "close", failed_close)
    try:
        with pytest.raises(OSError, match="injected"):
            runner.run_detection_provider(policy, reauthorize=lambda: None)
        with pytest.raises(OSError):
            os.fstat(user_fd)
    finally:
        original_close(net_fd)


def test_expiry_at_execution_boundary_refuses(approved, monkeypatch):
    policy, _, root = approved
    monkeypatch.setattr(host, "verify_resolution", lambda policy: None)

    def provider(policy, *, reauthorize):
        monkeypatch.setattr(
            host,
            "datetime",
            SimpleNamespace(now=lambda zone: policy.expires_at + timedelta(seconds=1)),
        )
        reauthorize()
        pytest.fail("Expired approval executed")

    monkeypatch.setattr(host, "run_detection_provider", provider)
    result = execute(policy, root)
    assert result["status"] == "refused" and result["complete"] is False


@pytest.mark.parametrize(
    "key,value",
    [
        ("origin", "http://evil.test"),
        ("connected_ip", "127.0.0.2"),
        ("request_count", 2),
        ("request_count", True),
        ("method", "POST"),
        ("complete", False),
        ("status_code", 302),
        ("marker_header", "untrusted-secret"),
    ],
)
def test_capture_contract_bound_to_policy(approved, key, value):
    policy, _, _ = approved
    capture = captured()
    capture[key] = value
    with pytest.raises(ValueError):
        runner.parse_capture(json.dumps(capture).encode(), policy)


@pytest.mark.parametrize(
    "value,kind,age",
    [
        (None, "absent", None),
        ("max-age=0", "max_age", 0),
        ('MAX-AGE="60"; includeSubDomains; preload', "max_age", 60),
        ("includeSubDomains", "other", None),
        ("", "other", None),
    ],
)
def test_normalized_hsts(value, kind, age):
    from beeagent_module.core.beescan_capture_worker import normalized_headers

    headers = {} if value is None else {"strict-transport-security": value}
    result = normalized_headers(headers, https=True)
    assert result == {
        "nosniff": "absent",
        "hsts": kind,
        "hsts_max_age": age,
        "https": True,
        "complete": True,
    }


@pytest.mark.parametrize(
    "value",
    [
        "max-age=-1",
        "max-age=no",
        "max-age",
        "max-age=1; max-age=2",
        "max-age=18446744073709551616",
        'max-age="1',
        "max-age=1, max-age=2",
        "max-age=1; preload; preload",
        "<secret>",
    ],
)
def test_malformed_hsts_rejected(value):
    from beeagent_module.core.beescan_capture_worker import normalized_headers

    with pytest.raises(ValueError):
        normalized_headers({"strict-transport-security": value}, https=True)


def test_signal_capture_seeded_malformed_protocol(approved):
    policy = approved[0]
    generator = random.Random(310)
    for _ in range(1000):
        raw = generator.randbytes(generator.randrange(4097))
        with pytest.raises(ValueError):
            runner.parse_capture(raw, policy, http_signals=True)
    capture = captured()
    capture["header_facts"] = {
        "nosniff": "nosniff",
        "hsts": "absent",
        "hsts_max_age": None,
        "https": False,
        "complete": True,
    }
    raw = json.dumps(capture).encode()
    assert runner.parse_capture(raw, policy, http_signals=True) == capture
    for malformed in (
        raw.replace(b'"nosniff": "nosniff"', b'"nosniff":"nosniff","nosniff":"other"'),
        raw + b" " * 4096,
    ):
        with pytest.raises(ValueError):
            runner.parse_capture(malformed, policy, http_signals=True)


@pytest.mark.parametrize(
    "headers",
    [
        b"X-Content-Type-Options: nosniff\r\nX-Content-Type-Options: nosniff\r\n\r\n",
        b"Strict-Transport-Security: max-age=1\r\nstrict-transport-security: max-age=1\r\n\r\n",
        b"X-Content-Type-Options: \xff\r\n\r\n",
        b"X-Content-Type-Options: nosniff\r\n",
        b"X-Content-Type-Options: " + b"a" * 1025 + b"\r\n\r\n",
        b"X-Content-Type-Options: " + b"a" * 8192 + b"\r\n\r\n",
        b" X-Content-Type-Options: nosniff\r\n\r\n",
        b"Strict-Transport-Security: max-age=1; max-age=1\r\n\r\n",
    ],
)
def test_signal_worker_rejects_unsafe_header_blocks(monkeypatch, headers):
    from beeagent_module.core import beescan_capture_worker as worker

    response = bytearray(b"HTTP/1.1 200 OK\r\n" + headers)
    requests = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def settimeout(self, seconds):
            pass

        def connect(self, destination):
            assert destination == ("127.0.0.1", 18080)

        def sendall(self, request):
            requests.append(request)

        def recv(self, size):
            return bytes([response.pop(0)]) if response else b""

        def close(self):
            pass

    monkeypatch.setattr(worker.socket, "socket", lambda *args: Connection())
    with pytest.raises((ValueError, UnicodeError)):
        worker.capture(
            {
                "origin": "http://127.0.0.1:18080",
                "connected_ip": "127.0.0.1",
                "port": 18080,
                "seconds": 1,
                "http_signals": True,
            }
        )
    assert len(requests) == 1
    assert requests[0].startswith(b"GET / HTTP/1.1\r\n")
