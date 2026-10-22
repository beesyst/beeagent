import copy
import json
import random

import pytest

from beeagent_module.integrations.beescan import egress
from tests import test_beescan_assessment
from tests.test_beescan_assessment import run_assessment

approved = test_beescan_assessment.approved
assessment = test_beescan_assessment.assessment


def managed(settings):
    for section in ("approval", "detection_approval"):
        settings["beescan"][section].update(
            network_namespace=egress.MANAGED_NET, user_namespace=egress.MANAGED_USER
        )


@pytest.fixture
def lifecycle(assessment, monkeypatch):
    managed(assessment[0])
    sessions = []

    def start(self):
        sessions.append(self)
        self.evidence.update(state="ready")
        self.persist()

    def close(self):
        self.closed = True
        self.evidence.update(
            state="closed", enforcement_verified=True, cleanup_verified=True
        )
        self.persist()

    monkeypatch.setattr(egress.ManagedEgress, "start", start)
    monkeypatch.setattr(egress.ManagedEgress, "close", close)
    return assessment, sessions


def test_managed_session_reused_and_original_approvals_immutable(lifecycle):
    target, sessions = lifecycle
    original = copy.deepcopy(target[0])
    result = run_assessment(target)
    assert result["complete"], result
    assert target[0] == original
    assert target[2] == ["probe", "detection"]
    assert len(sessions) == 1 and sessions[0].closed
    parent = target[1] / "runs" / result["assessment_run_id"] / "module-beescan"
    evidence = parent / result["egress_artifact"]
    assert evidence.stat().st_mode & 0o077 == 0
    assert json.loads(evidence.read_text())["cleanup_verified"] is True


@pytest.mark.parametrize("section", ["approval", "detection_approval"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("approved", False),
        ("excluded", True),
        ("expires_at", "2020-01-01T00:00:00+00:00"),
    ],
)
def test_invalid_authority_creates_zero_sessions(lifecycle, section, field, value):
    target, sessions = lifecycle
    target[0]["beescan"][section][field] = value
    assert not run_assessment(target)["complete"]
    assert sessions == [] and target[2] == []


@pytest.mark.parametrize("flag", ["probe_enabled", "detection_enabled"])
def test_disabled_creates_zero_sessions(lifecycle, flag):
    target, sessions = lifecycle
    target[0]["beescan"][flag] = False
    assert not run_assessment(target)["complete"]
    assert sessions == [] and target[2] == []


@pytest.mark.parametrize("section", ["approval", "detection_approval"])
def test_null_approval_creates_zero_sessions(lifecycle, section):
    target, sessions = lifecycle
    target[0]["beescan"][section] = None
    assert not run_assessment(target)["complete"]
    assert sessions == [] and target[2] == []


@pytest.mark.parametrize(
    "failure", [PermissionError, TimeoutError, OSError, KeyboardInterrupt]
)
def test_setup_failure_cleans_session(lifecycle, monkeypatch, failure):
    target, sessions = lifecycle

    def start(self):
        sessions.append(self)
        raise failure("setup_failed")

    monkeypatch.setattr(egress.ManagedEgress, "start", start)
    if failure is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            run_assessment(target)
    else:
        assert not run_assessment(target)["complete"]
    assert len(sessions) == 1 and sessions[0].closed
    assert target[2] == []


def test_cleanup_failure_prevents_complete_report(lifecycle, monkeypatch):
    target, sessions = lifecycle

    def close(self):
        self.closed = True
        raise OSError("cleanup_failed")

    monkeypatch.setattr(egress.ManagedEgress, "close", close)
    result = run_assessment(target)
    assert not result["complete"]
    assert target[2] == ["probe", "detection"]
    assert len(sessions) == 1


def test_lifecycle_tampering_prevents_terminal_success(lifecycle, monkeypatch):
    from beeagent_module.integrations.beescan.assessment import ArtifactAPI

    target, _ = lifecycle
    original = ArtifactAPI.write_json

    def write(self, name, data):
        path = original(self, name, data)
        if name == "assessment_status.pending.json" and data.get("complete"):
            (path.parent / "egress_lifecycle.json").write_text("{}")
        return path

    monkeypatch.setattr(ArtifactAPI, "write_json", write)
    assert not run_assessment(target)["complete"]


@pytest.mark.parametrize("tampered", [False, True])
def test_offline_review_verifies_managed_lifecycle(lifecycle, tampered):
    from beeagent_module.integrations.beescan.review_source import load_assessment

    target, _ = lifecycle
    result = run_assessment(target)
    assert result["complete"]
    for path in target[1].rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
    if tampered:
        path = (
            target[1]
            / "runs"
            / result["assessment_run_id"]
            / "module-beescan/egress_lifecycle.json"
        )
        path.write_text("{}")
        with pytest.raises((KeyError, ValueError)):
            load_assessment(target[1], result["assessment_run_id"], target[0])
    else:
        load_assessment(target[1], result["assessment_run_id"], target[0])


def test_managed_binding_is_assessment_scoped():
    assert egress.namespace_pair(egress.MANAGED_NET, egress.MANAGED_USER)
    assert egress.namespace_pair("/proc/12/ns/net", "/proc/12/ns/user")
    assert not egress.namespace_pair(egress.MANAGED_NET, "/proc/12/ns/user")
    with pytest.raises(PermissionError):
        egress.resolve_namespace(egress.MANAGED_NET)
    generator = random.Random(326)
    for _ in range(1000):
        value = generator.randbytes(generator.randrange(1, 256)).hex()
        assert not egress.namespace_pair(value, value)


@pytest.mark.parametrize("mode", ["wrong_bytes", "symlink", "fifo"])
def test_untrusted_provisioning_input_rejected(tmp_path, mode):
    package = tmp_path / "package.deb"
    if mode == "symlink":
        package.symlink_to(tmp_path / "missing")
    elif mode == "fifo":
        import os

        os.mkfifo(package)
    else:
        package.write_bytes(b"x" * 259676)
    with pytest.raises((OSError, PermissionError)):
        egress.provision(package)
