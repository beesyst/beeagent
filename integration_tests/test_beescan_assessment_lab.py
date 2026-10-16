import json
import logging
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from beeagent_module.core import beescan_assessment as host
from beeagent_module.core import beescan_detection, beescan_detection_runner
from beeagent_module.core.beescan_assessment import execute_approved_assessment
from integration_tests import test_beescan_lab
from integration_tests.test_beescan_lab import assert_kernel_egress
from tests import test_beescan_detection
from tests.test_beescan_detection import settings_for

lab = test_beescan_lab.lab
approved = test_beescan_detection.approved


@pytest.fixture
def assessment_lab(lab, approved):
    probe, root = lab
    original, _, _ = approved
    executable = os.environ.get("BEEAGENT_BEESCAN_NUCLEI")
    if not executable:
        pytest.fail("Explicit pinned Nuclei executable required", pytrace=False)
    detection = replace(
        original,
        executable=executable,
        project_id=probe.project_id,
        scope_id=probe.scope_id,
        mission_id=probe.mission_id,
        target_id=probe.target_id,
        origin=probe.origin,
        connected_ip=probe.connected_ip,
        network_namespace=probe.network_namespace,
        user_namespace=probe.user_namespace,
        valid_from=probe.valid_from,
        expires_at=probe.expires_at,
        time_budget_seconds=15,
    )
    settings = settings_for(detection)
    values = asdict(probe)
    for name in ("valid_from", "expires_at"):
        values[name] = values[name].isoformat()
    settings["beescan"].update(probe_enabled=True, approval=values)
    return settings, probe, root


def test_real_httpx_nuclei_assessment(assessment_lab):
    settings, probe, root = assessment_lab
    source_ids = (
        settings["beescan"]["detection_approval"]["source_run_id"],
        settings["beescan"]["detection_approval"]["source_observation_id"],
    )
    logger = logging.getLogger("assessment-lab")
    handler = logging.FileHandler(root / "assessment.log")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    assert_kernel_egress(probe)
    try:
        for mode, expected in (("ok", "findings"), ("negative", "no_findings")):
            (root / "mode").write_text(mode)
            before = json.loads((root / "counts.json").read_text())["18080"]
            request_start = len(json.loads((root / "requests.json").read_text()))
            status = execute_approved_assessment(
                settings=settings,
                reload_settings=lambda: settings,
                storage_dir=root / "storage",
                logger=logger,
            )
            assert status["complete"] is True, status
            assert status["result"] == expected
            assert json.loads((root / "counts.json").read_text()) == {
                "18080": before + 2,
                "18081": 0,
            }
            assert json.loads((root / "requests.json").read_text())[request_start:] == [
                {"port": 18080, "method": "HEAD", "path": "/"},
                {"port": 18080, "method": "GET", "path": "/"},
            ]
            directory = (
                root / "storage/runs" / status["assessment_run_id"] / "module-beescan"
            )
            report = json.loads((directory / "report.json").read_text())
            assert report["probe"]["provider_id"] == "projectdiscovery-httpx"
            assert report["detection"]["provider_id"] == "nuclei"
            assert source_ids == (
                settings["beescan"]["detection_approval"]["source_run_id"],
                settings["beescan"]["detection_approval"]["source_observation_id"],
            )
            assert report["result"] == expected
            assert (
                report["findings"] == []
                if mode == "negative"
                else report["findings"][0]["status"] == "candidate"
            )
            if mode == "ok":
                assert report["findings"][0]["review_state"] == "pending"
                assert report["findings"][0]["review"] is None
            assert (
                json.loads((directory / "assessment_status.json").read_text()) == status
            )
        for section in ("approval", "detection_approval"):
            before = json.loads((root / "counts.json").read_text())
            settings["beescan"][section]["approved"] = False
            denied = execute_approved_assessment(
                settings=settings,
                reload_settings=lambda: settings,
                storage_dir=root / "storage",
                logger=logger,
            )
            assert denied["status"] == "refused" and not denied["complete"]
            assert json.loads((root / "counts.json").read_text()) == before
            settings["beescan"][section]["approved"] = True
        for artifact in (root / "storage").rglob("*"):
            if artifact.is_file():
                assert "lab-secret" not in artifact.read_text()
                assert "Set-Cookie" not in artifact.read_text()
    finally:
        logger.removeHandler(handler)
        handler.close()


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("approval", "approved", False),
        ("detection_approval", "approved", False),
        ("approval", "excluded", True),
        ("detection_approval", "excluded", True),
        ("detection_approval", "mission_id", "other"),
        ("detection_approval", "connected_ip", "127.0.0.2"),
        ("approval", "expires_at", "expired"),
        ("detection_approval", "expires_at", "expired"),
        ("approval", "approval", None),
        ("detection_approval", "detection_approval", None),
    ],
)
def test_real_assessment_authority_refusals(assessment_lab, section, field, value):
    settings, _, root = assessment_lab
    if value == "expired":
        value = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    if field == section:
        settings["beescan"][section] = value
    else:
        settings["beescan"][section][field] = value
    status = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("assessment-lab"),
    )
    assert status["complete"] is False
    assert json.loads((root / "requests.json").read_text()) == []


@pytest.mark.parametrize(
    "failure",
    [
        "httpx_missing",
        "httpx_modified",
        "nuclei_missing",
        "template",
        "namespace",
        "timeout",
    ],
)
def test_real_assessment_provider_failures(assessment_lab, failure):
    settings, _, root = assessment_lab
    if failure == "timeout":
        (root / "mode").write_text("timeout")
        settings["beescan"]["approval"]["time_budget_seconds"] = 2
    elif failure == "namespace":
        for section in ("approval", "detection_approval"):
            settings["beescan"][section].update(
                network_namespace="/proc/99999999/ns/net",
                user_namespace="/proc/99999999/ns/user",
            )
    elif failure == "template":
        path = root / "modified-template.yaml"
        path.write_text("invalid template")
        path.chmod(0o600)
        settings["beescan"]["detection_approval"]["template_path"] = str(path)
    else:
        section = "detection_approval" if failure == "nuclei_missing" else "approval"
        path = root / "unavailable-provider"
        if failure == "httpx_modified":
            path.write_bytes(b"modified")
            path.chmod(0o555)
        settings["beescan"][section]["executable"] = str(path)
    status = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("assessment-lab"),
    )
    assert status["complete"] is False, status
    requests = json.loads((root / "requests.json").read_text())
    assert all(
        item == {"port": 18080, "method": "HEAD", "path": "/"} for item in requests
    )
    assert len(requests) <= 1
    parent = root / "storage/runs" / status["assessment_run_id"] / "module-beescan"
    saved = json.loads((parent / "assessment_status.json").read_text())
    assert saved["complete"] is False


@pytest.mark.parametrize(
    "mutation",
    ["missing", "symlink", "changed", "cross_run", "evidence", "revoked"],
)
def test_real_assessment_source_integrity(assessment_lab, monkeypatch, mutation):
    settings, _, root = assessment_lab
    original = host.execute_approved_probe

    def changed(**kwargs):
        result = original(**kwargs)
        assert result["complete"] is True
        directory = root / "storage/runs" / result["run_id"] / "module-beescan"
        path = directory / "http_observation.json"
        if mutation == "missing":
            path.unlink()
        elif mutation == "symlink":
            saved = path.with_suffix(".saved")
            path.rename(saved)
            path.symlink_to(saved)
        elif mutation == "revoked":
            settings["beescan"]["detection_approval"]["approved"] = False
        elif mutation == "evidence":
            next(directory.glob("http-evidence-*.json")).write_text("{}")
        else:
            data = json.loads(path.read_text())
            if mutation == "changed":
                data["facts"]["status_code"] = 201
            else:
                data["facts"]["provenance"]["run_id"] = "historical-run"
            path.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(host, "execute_approved_probe", changed)
    status = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("assessment-lab"),
    )
    assert status["complete"] is False, status
    assert json.loads((root / "requests.json").read_text()) == [
        {"port": 18080, "method": "HEAD", "path": "/"}
    ]


@pytest.mark.parametrize("mutation", ["report.md", "report.json", "child", "terminal"])
def test_real_assessment_terminal_failure(assessment_lab, monkeypatch, mutation):
    settings, _, root = assessment_lab
    original = host.ArtifactAPI.write_json

    def changed(self, name, data):
        path = original(self, name, data)
        if name == "assessment_status.pending.json" and data.get("complete") is True:
            if mutation == "terminal":
                raise OSError("lab terminal write failure")
            if mutation == "child":
                child = (
                    root / "storage/runs" / data["detection_run_id"] / "module-beescan"
                )
                (child / "detection_status.json").write_text("{}")
            else:
                (self.artifact_dir() / mutation).write_text("partial")
        return path

    monkeypatch.setattr(host.ArtifactAPI, "write_json", changed)
    status = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("assessment-lab"),
    )
    assert status["complete"] is False, status
    parent = root / "storage/runs" / status["assessment_run_id"] / "module-beescan"
    saved = json.loads((parent / "assessment_status.json").read_text())
    assert saved["complete"] is False
    assert json.loads((root / "requests.json").read_text()) == [
        {"port": 18080, "method": "HEAD", "path": "/"},
        {"port": 18080, "method": "GET", "path": "/"},
    ]


@pytest.mark.parametrize("failure", ["source_before_capture", "cleanup"])
def test_real_assessment_execution_boundary(assessment_lab, monkeypatch, failure):
    settings, _, root = assessment_lab
    original = beescan_detection.run_detection_provider
    temporary_directory = beescan_detection_runner.tempfile.TemporaryDirectory

    class FailedCleanup(temporary_directory):
        def cleanup(self):
            super().cleanup()
            raise OSError("lab cleanup failure")

    def provider(policy, *, reauthorize):
        def changed():
            path = (
                root
                / "storage/runs"
                / policy.source_run_id
                / "module-beescan/http_observation.json"
            )
            path.write_bytes(path.read_bytes() + b" ")
            reauthorize()

        with monkeypatch.context() as patch:
            if failure == "cleanup":
                patch.setattr(
                    beescan_detection_runner.tempfile,
                    "TemporaryDirectory",
                    FailedCleanup,
                )
            return original(
                policy,
                reauthorize=(
                    changed if failure == "source_before_capture" else reauthorize
                ),
            )

    monkeypatch.setattr(beescan_detection, "run_detection_provider", provider)
    status = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("assessment-lab"),
    )
    assert status["complete"] is False, status
    requests = [{"port": 18080, "method": "HEAD", "path": "/"}]
    if failure == "cleanup":
        requests.append({"port": 18080, "method": "GET", "path": "/"})
    assert json.loads((root / "requests.json").read_text()) == requests
    parent = root / "storage/runs" / status["assessment_run_id"] / "module-beescan"
    assert json.loads((parent / "assessment_status.json").read_text()) == status
