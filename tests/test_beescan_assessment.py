import copy
import json
import logging
from dataclasses import asdict

import pytest

from beeagent_module.integrations.beescan import assessment as host
from beeagent_module.integrations.beescan import detection as beescan_detection
from beeagent_module.integrations.beescan import probe as beescan_probe
from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
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

    def detection_provider(policy, *, reauthorize, http_signals=False):
        reauthorize()
        calls.append("detection")
        capture = captured()
        if http_signals:
            capture["header_facts"] = {
                "nosniff": "nosniff",
                "hsts": "absent",
                "hsts_max_age": None,
                "https": False,
                "complete": True,
            }
        return output(capture), capture

    monkeypatch.setattr(beescan_probe, "run_provider", probe_provider)
    monkeypatch.setattr(beescan_probe, "verify_resolution", lambda policy: None)
    monkeypatch.setattr(beescan_detection, "run_detection_provider", detection_provider)
    monkeypatch.setattr(beescan_detection, "verify_resolution", lambda policy: None)
    return settings, root, calls


def run_assessment(assessment, reload_settings=None, *, http_signals=False):
    settings, root, _ = assessment
    return host.execute_approved_assessment(
        settings=settings,
        reload_settings=reload_settings or (lambda: settings),
        storage_dir=root,
        logger=logging.getLogger("assessment-test"),
        http_signals=http_signals,
    )


@pytest.mark.parametrize("matched", [True, False])
@pytest.mark.parametrize("legacy_contract", [False, True])
def test_assessment_complete_with_fresh_source(
    assessment, monkeypatch, matched, legacy_contract
):
    if legacy_contract:
        from beescan.domain import reporting

        original_input = reporting.AssessmentInput

        def legacy_input(*args):
            monkeypatch.setattr(reporting, "AssessmentInput", original_input)
            return original_input(*args)

        monkeypatch.setattr(reporting, "AssessmentInput", legacy_input)
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
@pytest.mark.parametrize("http_signals", [False, True])
def test_assessment_partial_persistence(
    assessment, monkeypatch, filename, http_signals
):
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
    result = run_assessment(assessment, http_signals=http_signals)
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
@pytest.mark.parametrize("http_signals", [False, True])
def test_assessment_rejects_detection_artifact_tampering(
    assessment, monkeypatch, name, http_signals
):
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
    status = run_assessment(assessment, http_signals=http_signals)
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
@pytest.mark.parametrize("http_signals", [False, True])
def test_assessment_terminal_commit_revalidates_required_state(
    assessment, monkeypatch, mutation, http_signals
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
    result = run_assessment(assessment, http_signals=http_signals)
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


@pytest.mark.parametrize("marker", ["present", "absent"])
@pytest.mark.parametrize("nosniff", ["absent", "nosniff", "other"])
def test_signal_assessment_public_report_and_evidence(
    assessment, monkeypatch, marker, nosniff
):
    from beescan.domain.http_signals import (
        HstsFact,
        HttpHeaderFacts,
        HttpSignalAssessment,
        NosniffFact,
    )
    from beescan.domain.reporting import AssessmentInput, build_assessment_report

    settings, root, calls = assessment
    reports = []
    original = build_assessment_report

    def report(record):
        assert type(record) is AssessmentInput
        assert type(record.signal_assessment) is HttpSignalAssessment
        assert type(record.signal_assessment.facts) is HttpHeaderFacts
        facts = record.signal_assessment.facts
        assert facts.nosniff is NosniffFact(nosniff)
        assert facts.hsts is HstsFact.ABSENT
        result = original(record)
        reports.append(result)
        return result

    def provider(policy, *, reauthorize, http_signals):
        assert http_signals is True
        reauthorize()
        calls.append("detection")
        capture = captured(marker)
        capture["header_facts"] = {
            "nosniff": nosniff,
            "hsts": "absent",
            "hsts_max_age": None,
            "https": False,
            "complete": True,
        }
        return output(capture), capture

    monkeypatch.setattr(beescan_detection, "run_detection_provider", provider)
    monkeypatch.setattr("beescan.domain.reporting.build_assessment_report", report)
    status = host.execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("signals"),
        http_signals=True,
    )
    assert status["complete"], status
    assert calls == ["probe", "detection"]
    expected = (
        "findings"
        if marker == "present"
        else "no_findings"
        if nosniff == "nosniff"
        else "signals"
    )
    assert status["result"] == expected
    parent = root / "runs" / status["assessment_run_id"] / "module-beescan"
    assert (parent / "report.md").read_bytes() == reports[0].markdown.encode()
    assert (parent / "report.json").read_bytes() == reports[0].canonical_json.encode()
    assert reports[0].data["signal_checks"][1]["state"] == "not_applicable"
    for path in root.rglob("*.json"):
        text = path.read_text()
        assert "Set-Cookie" not in text and "lab-secret" not in text


@pytest.mark.parametrize(
    "mutation", ["missing", "type", "incomplete", "https", "unknown", "extra", "age"]
)
def test_signal_assessment_rejects_bad_capture(assessment, monkeypatch, mutation):
    def provider(policy, *, reauthorize, http_signals):
        reauthorize()
        capture = captured("absent")
        header = {
            "nosniff": "nosniff",
            "hsts": "absent",
            "hsts_max_age": None,
            "https": False,
            "complete": True,
        }
        capture["header_facts"] = header
        if mutation == "missing":
            del capture["header_facts"]
        elif mutation == "type":
            header["nosniff"] = True
        elif mutation == "incomplete":
            header["complete"] = False
        elif mutation == "https":
            header["https"] = True
        elif mutation == "unknown":
            header["nosniff"] = "verified"
        elif mutation == "extra":
            header["raw"] = "secret"
        else:
            header["hsts_max_age"] = 1
        return output(capture), capture

    monkeypatch.setattr(beescan_detection, "run_detection_provider", provider)
    settings, root, _ = assessment
    result = host.execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("signals"),
        http_signals=True,
    )
    assert not result["complete"]
    assert result.get("result") != "no_findings"


@pytest.fixture
def git_assessment(assessment, monkeypatch):
    from beeagent_module.integrations.beescan import git_exposure as exposure

    settings, _, calls = assessment
    base = settings["beescan"]["approval"]
    fields = {
        name: base[name]
        for name in exposure.GitExposurePolicy.__dataclass_fields__
        if name in base
    }
    fields.update(
        method="git_head_exposure",
        http_method="GET",
        path="/.git/HEAD",
        output_bytes=4096,
    )
    settings["beescan"].update(git_exposure_enabled=True, git_exposure_approval=fields)

    def provider(policy, *, reauthorize, git_exposure):
        assert git_exposure is True
        reauthorize()
        calls.append("git")
        return json.dumps(
            {
                "origin": policy.origin,
                "connected_ip": policy.connected_ip,
                "port": policy.port,
                "method": "GET",
                "path": "/.git/HEAD",
                "request_count": 1,
                "complete": True,
                "status_code": 200,
                "signature": "symbolic",
            }
        ).encode()

    monkeypatch.setattr(exposure, "run_detection_provider", provider)
    monkeypatch.setattr(exposure, "verify_resolution", lambda policy: None)
    return assessment


def run_git(assessment, *, http_signals=False):
    return host.execute_approved_assessment(
        settings=assessment[0],
        reload_settings=lambda: assessment[0],
        storage_dir=assessment[1],
        logger=logging.getLogger("git-assessment-test"),
        git_exposure=True,
        http_signals=http_signals,
    )


@pytest.mark.parametrize("signals", [False, True])
def test_git_selected_provenance_and_redaction(git_assessment, signals):
    _settings, root, calls = git_assessment
    result = run_git(git_assessment, http_signals=signals)
    assert result["complete"], result
    assert calls == ["probe", "detection", "git"]
    assert result["budgets"]["max_requests"] == 3
    assert (
        len(
            {
                result[key]
                for key in (
                    "assessment_run_id",
                    "probe_run_id",
                    "detection_run_id",
                    "exposure_run_id",
                )
            }
        )
        == 4
    )
    parent = root / "runs" / result["assessment_run_id"] / "module-beescan"
    report = json.loads((parent / "report.json").read_text())
    assert report["schema_version"] == 3
    assert report["exposure"]["state"] == "positive"
    assert report["exposure"]["run_id"] == result["exposure_run_id"]
    child = root / "runs" / result["exposure_run_id"] / "module-beescan"
    facts = json.loads((child / "git_exposure_result.json").read_text())["facts"]
    assert facts["assessment_run_id"] == result["assessment_run_id"]
    assert facts["source_observation_id"] == result["http_observation_id"]
    for directory in (parent, child):
        for path in directory.iterdir():
            assert path.stat().st_mode & 0o077 == 0
            assert all(
                secret not in path.read_text()
                for secret in ("refs/heads", "Set-Cookie", "lab-secret")
            )


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved", False),
        ("excluded", True),
        ("path", "/.git/config"),
        ("http_method", "HEAD"),
        ("method", "http_probe"),
        ("origin", "http://other.test"),
        ("connected_ip", "127.0.0.2"),
        ("expires_at", "2020-01-01T00:00:00+00:00"),
        ("request_budget", 2),
        ("time_budget_seconds", 60),
    ],
)
def test_git_refused_before_any_request(git_assessment, field, value):
    git_assessment[0]["beescan"]["git_exposure_approval"][field] = value
    result = run_git(git_assessment)
    assert not result["complete"]
    assert git_assessment[2] == []


@pytest.mark.parametrize("value", [None, False, "true"])
def test_git_selection_requires_separate_enabled_approval(git_assessment, value):
    config = git_assessment[0]["beescan"]
    config["git_exposure_enabled"] = value
    assert not run_git(git_assessment)["complete"]
    assert git_assessment[2] == []


def test_git_unselected_preserves_legacy(git_assessment):
    git_assessment[0]["beescan"]["git_exposure_approval"]["approved"] = False
    result = run_assessment(git_assessment)
    assert result["complete"]
    assert git_assessment[2] == ["probe", "detection"]
    assert "exposure_run_id" not in result


@pytest.mark.parametrize(
    "failure,expected",
    [
        (PermissionError, "refused"),
        (TimeoutError, "timeout"),
        (ValueError, "error"),
        (OSError, "error"),
    ],
)
def test_git_failure_never_complete(git_assessment, monkeypatch, failure, expected):
    from beeagent_module.integrations.beescan import git_exposure as exposure

    def provider(policy, **kwargs):
        kwargs["reauthorize"]()
        raise failure("private-error-must-not-be-logged")

    monkeypatch.setattr(exposure, "run_detection_provider", provider)
    result = run_git(git_assessment)
    assert result["status"] == expected, result
    assert not result["complete"]
    parent = git_assessment[1] / "runs" / result["assessment_run_id"] / "module-beescan"
    report = json.loads((parent / "report.json").read_text())
    assert not report["complete"]
    assert report["result"] != "no_findings"


@pytest.mark.parametrize(
    "mutation", ["revoked", "source", "result", "evidence", "terminal"]
)
def test_git_mutation_and_persistence(git_assessment, monkeypatch, mutation):
    from beeagent_module.integrations.beescan import git_exposure as exposure

    if mutation in {"revoked", "source"}:
        original = exposure.run_detection_provider

        def provider(policy, **kwargs):
            if mutation == "revoked":
                git_assessment[0]["beescan"]["git_exposure_approval"]["approved"] = (
                    False
                )
            else:
                parent = next(
                    git_assessment[1].glob(
                        "runs/*/module-beescan/assessment_status.json"
                    )
                )
                source_run_id = json.loads(parent.read_text())["probe_run_id"]
                path = (
                    git_assessment[1]
                    / "runs"
                    / source_run_id
                    / "module-beescan/http_observation.json"
                )
                path.write_text("{}")
            return original(policy, **kwargs)

        monkeypatch.setattr(exposure, "run_detection_provider", provider)
    else:
        original = host.ArtifactAPI.write_json

        def write(self, name, data):
            if mutation == "result" and name == "git_exposure_result.json":
                raise OSError("persistence")
            path = original(self, name, data)
            if name == "assessment_status.pending.json" and data.get("complete"):
                if mutation == "evidence":
                    next(
                        git_assessment[1].glob(
                            "runs/*/module-beescan/git-evidence-*.json"
                        )
                    ).write_text("{}")
                else:
                    raise OSError("terminal")
            return path

        monkeypatch.setattr(host.ArtifactAPI, "write_json", write)
    result = run_git(git_assessment)
    assert not result["complete"], result


def test_git_capture_envelope_and_fuzz(git_assessment):
    import random

    from beeagent_module.integrations.beescan.git_exposure import (
        GitExposurePolicy,
        parse_git_capture,
    )
    from beeagent_module.integrations.beescan.policy import validate_beescan_settings

    config = git_assessment[0]["beescan"]
    validate_beescan_settings(git_assessment[0])
    policy = GitExposurePolicy.from_config(config["git_exposure_approval"])
    data = {
        "origin": policy.origin,
        "connected_ip": policy.connected_ip,
        "port": policy.port,
        "method": "GET",
        "path": "/.git/HEAD",
        "request_count": 1,
        "complete": True,
        "status_code": 200,
        "signature": None,
    }
    assert parse_git_capture(json.dumps(data).encode(), policy)["signature"] is None
    for key, value in (
        ("path", "/"),
        ("method", "HEAD"),
        ("complete", 1),
        ("request_count", 2),
        ("status_code", 302),
        ("signature", "refs/heads/secret"),
        ("origin", "https://other.test"),
    ):
        with pytest.raises(ValueError):
            parse_git_capture(json.dumps({**data, key: value}).encode(), policy)
    generator = random.Random(315)
    for _ in range(1000):
        with pytest.raises((ValueError, UnicodeError)):
            parse_git_capture(generator.randbytes(generator.randrange(1, 4200)), policy)
    config["git_exposure_approval"] = None
    with pytest.raises(RuntimeError):
        validate_beescan_settings(git_assessment[0])


@pytest.mark.parametrize(
    "body,status,extra,expected",
    [
        (b"ref: refs/heads/secret\n", 200, b"", "symbolic"),
        (b"a" * 40, 200, b"", "detached"),
        (b"ref: refs/heads/secret\n", 404, b"", None),
        (b"<html>ref: refs/heads/secret</html>", 200, b"", None),
        (b"ref: refs/heads/secret\n", 200, b"Content-Type: text/html\r\n", None),
        (b"ref: refs/heads/a..b\n", 200, b"", None),
    ],
)
def test_git_worker_fixed_request(monkeypatch, body, status, extra, expected):
    result = git_worker_response(monkeypatch, body, status=status, extra=extra)
    assert result is not None
    assert result["signature"] == expected


def git_worker_response(monkeypatch, body, *, status=200, extra=b"", length=None):
    import sys

    from beescan.domain import git_head_signature

    from beeagent_module.integrations.beescan import capture_worker as worker

    monkeypatch.setitem(sys.modules, "git_head_signature", git_head_signature)
    response = bytearray(
        f"HTTP/1.1 {status} Captured\r\nContent-Length: {len(body) if length is None else length}\r\n".encode()
        + extra
        + b"\r\n"
        + body
    )
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
            chunk = bytes(response[:size])
            del response[:size]
            return chunk

        def close(self):
            pass

    monkeypatch.setattr(worker.socket, "socket", lambda *args: Connection())
    code, result = worker.capture(
        {
            "origin": "http://127.0.0.1:18080",
            "connected_ip": "127.0.0.1",
            "port": 18080,
            "seconds": 1,
            "git_exposure": True,
        }
    )
    assert len(requests) == 1
    assert requests[0].startswith(b"GET /.git/HEAD HTTP/1.1\r\n")
    if status == 302:
        assert code == 3 and result is None
    return result


@pytest.mark.parametrize(
    "body,extra,length",
    [
        (b"a" * 1025, b"", None),
        (b"a" * 40, b"", 41),
        (b"a" * 40, b"", 39),
        (b"a" * 40, b"Content-Length: 40\r\n", None),
        (b"a" * 40, b"Transfer-Encoding: chunked\r\n", None),
        (b"a" * 40, b"Content-Encoding: gzip\r\n", None),
        (b"a" * 40, b"Content-Type: text/plain\r\nContent-Type: text/plain\r\n", None),
    ],
)
def test_git_worker_rejects_ambiguous_framing(monkeypatch, body, extra, length):
    with pytest.raises(ValueError):
        git_worker_response(monkeypatch, body, extra=extra, length=length)


def test_git_worker_redirect(monkeypatch):
    git_worker_response(monkeypatch, b"", status=302)


@pytest.mark.parametrize(
    "options",
    [
        ["--git-exposure"],
        ["--git-exposure", "--http-signals"],
        ["--http-signals", "--git-exposure"],
    ],
)
def test_git_cli_combinations(git_assessment, options, capsys):
    settings, root, calls = git_assessment
    settings["modules"]["registry"][0].update(
        package="beescan.module", entry="BeeScanModule"
    )
    code = beescan_probe.handle_beescan_cli(
        ["assess", *options],
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("git-cli"),
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    assert calls == ["probe", "detection", "git"]


def test_git_missing_contract_refuses_before_network(git_assessment, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "beescan.domain.git_exposure", None)
    result = run_git(git_assessment)
    assert result["status"] == "refused" and not result["complete"]
    assert git_assessment[2] == []


def test_git_completed_negative_assessment(git_assessment, monkeypatch):
    from beeagent_module.integrations.beescan import git_exposure as exposure

    original = exposure.run_detection_provider

    def git_provider(policy, **kwargs):
        raw = original(policy, **kwargs)
        assert isinstance(raw, bytes)
        data = json.loads(raw)
        data["signature"] = None
        return json.dumps(data).encode()

    def marker_provider(policy, *, reauthorize):
        reauthorize()
        git_assessment[2].append("detection")
        capture = captured("absent")
        return output(capture), capture

    monkeypatch.setattr(exposure, "run_detection_provider", git_provider)
    monkeypatch.setattr(beescan_detection, "run_detection_provider", marker_provider)
    result = run_git(git_assessment)
    assert result["complete"] and result["result"] == "no_findings", result
    assert git_assessment[2] == ["probe", "detection", "git"]
    parent = git_assessment[1] / "runs" / result["assessment_run_id"] / "module-beescan"
    assert (
        json.loads((parent / "report.json").read_text())["exposure"]["state"]
        == "no_match"
    )
