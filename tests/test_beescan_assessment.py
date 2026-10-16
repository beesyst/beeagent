import copy
import json
import logging
from dataclasses import asdict

import pytest

from beeagent_module.core import beescan_assessment as host
from beeagent_module.core import beescan_detection, beescan_probe
from beeagent_module.core.beescan_policy import HTTPX_SHA256, ProbePolicy
from tests import test_beescan_detection
from tests.test_beescan_detection import captured, output, settings_for

approved = test_beescan_detection.approved


@pytest.fixture
def assessment(approved, monkeypatch):
    detection, _, root = approved
    fields = {
        name: getattr(detection, name) for name in ProbePolicy.__dataclass_fields__
    }
    fields.update(
        method="http_probe",
        sha256=HTTPX_SHA256,
        provider_version="1.12.0",
        executable="/opt/beescan/httpx",
    )
    probe = ProbePolicy(**fields)
    settings = settings_for(detection)
    values = asdict(probe)
    for name in ("valid_from", "expires_at"):
        values[name] = values[name].isoformat()
    settings["beescan"].update(probe_enabled=True, approval=values)
    calls = []

    def probe_provider(policy, *, reauthorize):
        reauthorize()
        calls.append("probe")
        return json.dumps(
            {"url": policy.origin, "status_code": 200, "failed": False}
        ).encode()

    def detection_provider(policy, *, reauthorize):
        reauthorize()
        calls.append("detection")
        capture = captured()
        return output(capture), capture

    monkeypatch.setattr(beescan_probe, "run_provider", probe_provider)
    monkeypatch.setattr(beescan_probe, "verify_resolution", lambda policy: None)
    monkeypatch.setattr(beescan_detection, "run_detection_provider", detection_provider)
    monkeypatch.setattr(beescan_detection, "verify_resolution", lambda policy: None)
    return settings, root, calls


def run_assessment(assessment, reload_settings=None):
    settings, root, _ = assessment
    return host.execute_approved_assessment(
        settings=settings,
        reload_settings=reload_settings or (lambda: settings),
        storage_dir=root,
        logger=logging.getLogger("assessment-test"),
    )


@pytest.mark.parametrize("matched", [True, False])
def test_assessment_complete_with_fresh_source(assessment, monkeypatch, matched):
    settings, root, calls = assessment
    original = copy.deepcopy(settings)

    def provider(policy, *, reauthorize):
        reauthorize()
        calls.append("detection")
        assert (
            policy.source_run_id
            != original["beescan"]["detection_approval"]["source_run_id"]
        )
        capture = captured("present" if matched else "absent")
        return output(capture), capture

    monkeypatch.setattr(beescan_detection, "run_detection_provider", provider)
    status = run_assessment(assessment)
    assert status["status"] == "ok", status
    assert status["complete"] is True
    assert calls == ["probe", "detection"]
    assert settings == original
    assert (
        len(
            {
                status["assessment_run_id"],
                status["probe_run_id"],
                status["detection_run_id"],
            }
        )
        == 3
    )
    directory = root / "runs" / status["assessment_run_id"] / "module-beescan"
    assert json.loads((directory / "assessment_status.json").read_text()) == status
    report = json.loads((directory / "report.json").read_text())
    assert report["result"] == ("findings" if matched else "no_findings")
    assert report["probe"]["run_id"] == status["probe_run_id"]
    assert report["detection"]["run_id"] == status["detection_run_id"]
    assert report["detection"]["source_observation_id"] == status["http_observation_id"]
    assert (
        report["findings"] == []
        if not matched
        else report["findings"][0]["status"] == "candidate"
    )
    if matched:
        assert report["findings"][0]["review_state"] == "pending"
    assert all(path.stat().st_mode & 0o077 == 0 for path in directory.iterdir())


@pytest.mark.parametrize("field", ["provenance", "evidence_record"])
def test_assessment_rejects_missing_detection_evidence(assessment, monkeypatch, field):
    original = beescan_detection.GovernedDetectionCaller.call

    def missing(self, capability_name, payload):
        result = original(self, capability_name, payload)
        assert result.status.value == "ok"
        setattr(self, field, None)
        return result

    monkeypatch.setattr(beescan_detection.GovernedDetectionCaller, "call", missing)
    status = run_assessment(assessment)
    assert status["complete"] is False
    assert status["status"] == "incomplete"
    directory = assessment[1] / "runs" / status["detection_run_id"] / "module-beescan"
    assert not (directory / "detection_outcome.json").exists()
    assert (
        json.loads((directory / "detection_status.json").read_text())["complete"]
        is False
    )


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("approval", "approved", False),
        ("detection_approval", "approved", False),
        ("approval", "excluded", True),
        ("detection_approval", "excluded", True),
        ("detection_approval", "mission_id", "other"),
        ("detection_approval", "connected_ip", "127.0.0.2"),
        ("detection_approval", "operator_uid", 2147483647),
        ("approval", "expires_at", "2020-01-01T00:00:00+00:00"),
    ],
)
def test_assessment_refuses_before_requests(assessment, section, field, value):
    settings, _, calls = assessment
    settings["beescan"][section][field] = value
    status = run_assessment(assessment)
    assert status["complete"] is False
    assert calls == []


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("approval", "approved", False),
        ("detection_approval", "approved", False),
        ("approval", "scope_id", "changed"),
        ("detection_approval", "source_run_id", "changed"),
        ("detection_approval", "source_observation_id", "changed"),
    ],
)
def test_assessment_revalidates_original_approvals(
    assessment, monkeypatch, section, field, value
):
    settings, _, calls = assessment
    original_execute = host.execute_approved_probe

    def mutate(**kwargs):
        result = original_execute(**kwargs)
        settings["beescan"][section][field] = value
        return result

    monkeypatch.setattr(host, "execute_approved_probe", mutate)
    result = run_assessment(assessment)
    assert result["complete"] is False
    assert calls == ["probe"]


@pytest.mark.parametrize(
    "name", ["http_observation.json", "http_probe_status.json", "evidence"]
)
def test_assessment_source_mutation_before_detector_request(
    assessment, monkeypatch, name
):
    _, root, calls = assessment

    def provider(policy, *, reauthorize):
        directory = root / "runs" / policy.source_run_id / "module-beescan"
        selected = (
            next(directory.glob("http-evidence-*.json"))
            if name == "evidence"
            else directory / name
        )
        selected.write_bytes(selected.read_bytes() + b" ")
        reauthorize()
        calls.append("detection")
        raise AssertionError("Request must be refused")

    monkeypatch.setattr(beescan_detection, "run_detection_provider", provider)
    result = run_assessment(assessment)
    assert result["complete"] is False
    assert calls == ["probe"]


@pytest.mark.parametrize(
    "failure,expected",
    [
        (TimeoutError, "timeout"),
        (PermissionError, "refused"),
        (RuntimeError, "error"),
        (OSError, "error"),
        (ValueError, "error"),
    ],
)
def test_assessment_provider_and_cleanup_failures(
    assessment, monkeypatch, failure, expected
):
    def provider(policy, *, reauthorize):
        reauthorize()
        raise failure("test")

    monkeypatch.setattr(beescan_detection, "run_detection_provider", provider)
    result = run_assessment(assessment)
    assert result["complete"] is False
    assert result["status"] == expected


@pytest.mark.parametrize(
    "filename", ["report.md", "report.json", "assessment_status.pending.json"]
)
def test_assessment_partial_persistence(assessment, monkeypatch, filename):
    original_text = host.ArtifactAPI.write_text
    original_json = host.ArtifactAPI.write_json

    def text_write(self, name, content):
        return original_text(self, name, content[:20] if name == filename else content)

    def json_write(self, name, data):
        if name == filename:
            raise OSError("disk failure")
        return original_json(self, name, data)

    monkeypatch.setattr(host.ArtifactAPI, "write_text", text_write)
    monkeypatch.setattr(host.ArtifactAPI, "write_json", json_write)
    result = run_assessment(assessment)
    assert result["complete"] is False
    _, root, _ = assessment
    saved = json.loads(
        (
            root
            / "runs"
            / result["assessment_run_id"]
            / "module-beescan/assessment_status.json"
        ).read_text()
    )
    assert saved["complete"] is False


@pytest.mark.parametrize("field,value", [("complete", 1), ("schema_version", True)])
def test_assessment_terminal_marker_rejects_json_type_corruption(
    assessment, monkeypatch, field, value
):
    original = host.ArtifactAPI.write_json

    def corrupted(self, name, data):
        if name == "assessment_status.pending.json" and data.get("complete") is True:
            data = dict(data)
            data[field] = value
        return original(self, name, data)

    monkeypatch.setattr(host.ArtifactAPI, "write_json", corrupted)
    result = run_assessment(assessment)
    assert result["complete"] is False
    path = (
        assessment[1]
        / "runs"
        / result["assessment_run_id"]
        / "module-beescan/assessment_status.json"
    )
    assert json.loads(path.read_text())["complete"] is False


def test_assessment_aggregate_deadline_and_no_cli_payload(assessment, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(host, "monotonic", lambda: clock[0])
    original = host.execute_approved_probe

    def delayed(**kwargs):
        result = original(**kwargs)
        clock[0] = 6.0
        return result

    monkeypatch.setattr(host, "execute_approved_probe", delayed)
    result = run_assessment(assessment)
    assert result["status"] == "timeout"
    assert assessment[2] == ["probe"]
    for args in (
        ["assess", "https://evil.test"],
        ["assess", "-t", "anything"],
        ["assess", "--verified"],
    ):
        assert (
            beescan_probe.handle_beescan_cli(
                args,
                settings={},
                reload_settings=dict,
                storage_dir=assessment[1],
                logger=logging.getLogger("cli"),
            )
            == 2
        )


@pytest.mark.parametrize("mutation", ["malformed", "symlink", "facts", "provenance"])
def test_assessment_rejects_source_changed_before_binding(
    assessment, monkeypatch, mutation
):
    original = host.execute_approved_probe

    def changed(**kwargs):
        result = original(**kwargs)
        path = (
            assessment[1]
            / "runs"
            / result["run_id"]
            / "module-beescan/http_observation.json"
        )
        if mutation == "malformed":
            path.write_bytes(b'{"facts":')
        elif mutation == "symlink":
            saved = path.with_suffix(".saved")
            path.rename(saved)
            path.symlink_to(saved)
        else:
            data = json.loads(path.read_text())
            if mutation == "facts":
                data["facts"]["status_code"] = 201
            else:
                data["facts"]["provenance"]["run_id"] = "historical-run"
            path.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(host, "execute_approved_probe", changed)
    status = run_assessment(assessment)
    assert not status["complete"]
    assert assessment[2] == ["probe"]


@pytest.mark.parametrize(
    "name", ["detection_status.json", "detection_candidates.json", "evidence"]
)
def test_assessment_rejects_detection_artifact_tampering(assessment, monkeypatch, name):
    original = host.execute_approved_detection

    def changed(**kwargs):
        result = original(**kwargs)
        directory = assessment[1] / "runs" / result["run_id"] / "module-beescan"
        path = (
            next(directory.glob("detection-evidence-*.json"))
            if name == "evidence"
            else directory / name
        )
        data = json.loads(path.read_text())
        if name == "detection_status.json":
            data["complete"] = 1
        elif name == "evidence":
            data["capture"]["marker_header"] = "absent"
        else:
            data["candidates"][0]["finding"]["status"] = "verified"
        path.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(host, "execute_approved_detection", changed)
    status = run_assessment(assessment)
    assert not status["complete"]


def test_assessment_interruption_retains_incomplete_parent(assessment, monkeypatch):
    def interrupted(policy, *, reauthorize):
        reauthorize()
        raise KeyboardInterrupt

    monkeypatch.setattr(beescan_detection, "run_detection_provider", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_assessment(assessment)
    parents = list(assessment[1].glob("runs/*/module-beescan/assessment_status.json"))
    assert len(parents) == 1
    status = json.loads(parents[0].read_text())
    assert status["complete"] is False
    assert status["phase"] == "detection"
    assert status["probe_run_id"] and status["detection_run_id"]


def test_assessment_cli_dispatch(assessment, capsys):
    settings, root, _ = assessment
    settings["modules"]["registry"][0].update(
        package="beescan.module", entry="BeeScanModule"
    )
    code = beescan_probe.handle_beescan_cli(
        ["assess"],
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("assessment-cli"),
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["complete"] is True


@pytest.mark.parametrize(
    "mutation", ["report.md", "report.json", "child", "approval", "deadline"]
)
def test_assessment_terminal_commit_revalidates_required_state(
    assessment, monkeypatch, mutation
):
    original = host.ArtifactAPI.write_json
    clock = [0.0]
    monkeypatch.setattr(host, "monotonic", lambda: clock[0])

    def corrupted(self, name, data):
        path = original(self, name, data)
        if name == "assessment_status.pending.json" and data.get("complete") is True:
            if mutation.startswith("report."):
                (self.artifact_dir() / mutation).unlink()
            elif mutation == "child":
                child = (
                    assessment[1]
                    / "runs"
                    / data["detection_run_id"]
                    / "module-beescan/detection_status.json"
                )
                child.write_text("{}")
            elif mutation == "approval":
                assessment[0]["beescan"]["detection_approval"]["approved"] = False
            else:
                clock[0] = 11.0
        return path

    monkeypatch.setattr(host.ArtifactAPI, "write_json", corrupted)
    result = run_assessment(assessment)
    assert result["complete"] is False
    marker = (
        assessment[1]
        / "runs"
        / result["assessment_run_id"]
        / "module-beescan/assessment_status.json"
    )
    assert json.loads(marker.read_text())["complete"] is False
    if mutation == "approval":
        assert result["status"] == "refused"
    elif mutation == "deadline":
        assert result["status"] == "timeout"
