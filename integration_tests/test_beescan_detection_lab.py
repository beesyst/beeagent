import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.beescan_detection import execute_approved_detection
from beeagent_module.core.beescan_detection_policy import (
    NUCLEI_SHA256,
    NUCLEI_VERSION,
    TEMPLATE_SHA256,
    DetectionPolicy,
)
from beeagent_module.core.beescan_detection_runner import _sandbox
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import RuntimeContext
from integration_tests.test_beescan_lab import assert_kernel_egress


@pytest.fixture
def detection_lab(tmp_path):
    executable = os.environ.get("BEEAGENT_BEESCAN_NUCLEI")
    if not executable:
        pytest.fail("Explicit pinned Nuclei executable required", pytrace=False)
    from beescan.capabilities.http_probe import (
        HostProvenance,
        HttpFacts,
        HttpProbeIntent,
        HttpProbeOutcome,
        normalize_http_observation,
    )
    from beesdk.capabilities import CapabilityStatus

    (tmp_path / "mode").write_text("ok")
    worker = (
        Path(__file__).resolve().parents[1] / "tests/fixtures/beescan_lab_worker.py"
    )
    process = subprocess.Popen(
        [
            "/usr/bin/unshare",
            "--user",
            "--map-root-user",
            "--net",
            sys.executable,
            str(worker),
            str(tmp_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin"},
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "ready").exists():
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail("Required rootless lab isolation unavailable")
            time.sleep(0.05)
        prefix = [
            "/usr/bin/nsenter",
            "--preserve-credentials",
            f"--user=/proc/{process.pid}/ns/user",
            f"--net=/proc/{process.pid}/ns/net",
            "--",
        ]
        response = subprocess.run(
            [
                *prefix,
                sys.executable,
                "-I",
                "-c",
                "import http.client; c=http.client.HTTPConnection('127.0.0.1',18080,timeout=2); c.request('HEAD','/'); r=c.getresponse(); print(r.status); c.close()",
            ],
            check=True,
            capture_output=True,
            timeout=5,
        )
        assert response.stdout.strip() == b"200"
        source_run = "run-bs2-lab-source"
        probe = HttpProbeIntent(
            "mission-lab",
            "target-lab",
            "http://127.0.0.1:18080",
            1,
            5,
            "lab-http-head",
            "1",
        )
        provenance = HostProvenance(source_run, "lab-http-head", "1")
        facts = HttpFacts(
            probe.origin, True, 200, None, provenance, ("lab-head-evidence",), True
        )
        observation = normalize_http_observation(
            probe,
            HttpProbeOutcome(
                probe.mission_id,
                probe.target_id,
                CapabilityStatus.OK,
                "ok",
                facts.evidence_refs,
                provenance,
            ),
            facts,
        )
        artifacts = ArtifactAPI(
            RuntimeContext(
                source_run,
                "session-lab",
                "http_probe",
                "beescan",
                AuthorityLevel.EXECUTION_CAPABLE,
            ),
            tmp_path / "storage",
            logging.getLogger("lab-source"),
        )
        artifacts.write_json(
            "lab-head-evidence.json", {"schema_version": 1, **asdict(facts)}
        )
        artifacts.write_json(
            "http_observation.json", {"schema_version": 1, **asdict(observation)}
        )
        artifacts.write_json(
            "http_probe_status.json",
            {
                "schema_version": 1,
                "run_id": source_run,
                "status": "ok",
                "complete": True,
                "project_id": "project-lab",
                "scope_id": "scope-lab",
                "mission_id": probe.mission_id,
                "target_id": probe.target_id,
                "provenance": asdict(provenance),
                "evidence_refs": list(facts.evidence_refs),
            },
        )
        for path in artifacts.artifact_dir().iterdir():
            path.chmod(0o600)
        now = datetime.now(UTC)
        policy = DetectionPolicy(
            operator_uid=os.getuid(),
            project_id="project-lab",
            scope_id="scope-lab",
            mission_id=probe.mission_id,
            target_id=probe.target_id,
            origin=probe.origin,
            approved=True,
            excluded=False,
            valid_from=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=20),
            method="restricted_detection",
            request_budget=1,
            time_budget_seconds=15,
            connected_ip="127.0.0.1",
            allow_private_lab=True,
            executable=executable,
            sha256=NUCLEI_SHA256,
            provider_version=NUCLEI_VERSION,
            network_namespace=f"/proc/{process.pid}/ns/net",
            user_namespace=f"/proc/{process.pid}/ns/user",
            memory_mb=3072,
            output_bytes=8192,
            source_run_id=source_run,
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
        yield policy, tmp_path
    finally:
        process.terminate()
        process.wait(timeout=3)


def run_detection(policy, root):
    config = asdict(policy)
    for key in ("valid_from", "expires_at"):
        config[key] = config[key].isoformat()
    settings = {
        "modules": {"registry": [{"id": "beescan", "enabled": True}]},
        "beescan": {"detection_enabled": True, "detection_approval": config},
    }
    return execute_approved_detection(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("detection-lab"),
    )


def test_real_nuclei_match_no_match_and_fail_closed(detection_lab, monkeypatch):
    policy, root = detection_lab
    assert_kernel_egress(policy)
    isolation = subprocess.run(
        [
            *_sandbox(policy),
            "--ro-bind",
            "/usr",
            "/usr",
            "--ro-bind",
            "/lib",
            "/lib",
            "--ro-bind",
            "/lib64",
            "/lib64",
            "--",
            "/usr/bin/python3",
            "-I",
            "-c",
            "import os,socket; assert 'HTTP_PROXY' not in os.environ; assert not os.path.exists('/host-secret'); s=socket.socket(); s.settimeout(.2)\ntry: s.connect(('127.0.0.1',18080))\nexcept OSError: print('network-denied')\nelse: raise AssertionError('unexpected network')\nassert 'CapEff:\\t0000000000000000' in open('/proc/self/status').read()",
        ],
        capture_output=True,
        timeout=3,
        check=False,
    )
    assert isolation.returncode == 0, isolation.stderr.decode()
    assert isolation.stdout.strip() == b"network-denied"
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://127.0.0.1:18081")
    for mode, expected in (
        ("ok", "matched"),
        ("negative", "no_match"),
        ("redirect", "refused"),
        ("malformed", "error"),
        ("oversized", "error"),
        ("timeout", "timeout"),
    ):
        before = json.loads((root / "counts.json").read_text())["18080"]
        (root / "mode").write_text(mode)
        result = run_detection(
            replace(policy, time_budget_seconds=3 if mode == "timeout" else 15), root
        )
        assert result["status"] == expected, result
        assert result["complete"] is (expected in {"matched", "no_match"})
        assert json.loads((root / "counts.json").read_text()) == {
            "18080": before + 1,
            "18081": 0,
        }
        directory = root / "storage/runs" / result["run_id"] / "module-beescan"
        assert json.loads((directory / "detection_status.json").read_text()) == result
        if result["complete"]:
            candidates = json.loads(
                (directory / "detection_candidates.json").read_text()
            )["candidates"]
            assert len(candidates) == (1 if expected == "matched" else 0)
            if candidates:
                assert candidates[0]["finding"]["status"] == "candidate"
    count = json.loads((root / "counts.json").read_text())["18080"]
    modified_template = root / "modified-template.yaml"
    modified_template.write_bytes(Path(policy.template_path).read_bytes() + b"\n")
    modified_template.chmod(0o600)
    modified_binary = root / "modified-nuclei"
    modified_binary.write_bytes(b"not-the-pinned-executable")
    modified_binary.chmod(0o500)
    for changed in (
        replace(policy, excluded=True),
        replace(policy, approved=False),
        replace(policy, operator_uid=os.getuid() + 1),
        replace(policy, connected_ip="127.0.0.2"),
        replace(policy, executable=str(root / "missing")),
        replace(policy, template_path=str(root / "missing-template")),
        replace(policy, template_path=str(modified_template)),
        replace(policy, executable=str(modified_binary)),
        replace(policy, expires_at=datetime.now(UTC) - timedelta(seconds=1)),
    ):
        result = run_detection(changed, root)
        assert not result["complete"] and result["evidence_refs"] == [], result
    assert json.loads((root / "counts.json").read_text()) == {
        "18080": count,
        "18081": 0,
    }
    subprocess.run(
        [
            "/usr/bin/nsenter",
            "--preserve-credentials",
            "--user=" + policy.user_namespace,
            "--net=" + policy.network_namespace,
            "--",
            "/usr/sbin/nft",
            "delete",
            "table",
            "inet",
            "beescan",
        ],
        check=True,
        timeout=3,
    )
    result = run_detection(policy, root)
    assert result["status"] == "refused" and result["reason"] == "egress_unverified"
    assert not result["complete"] and result["evidence_refs"] == []
    for artifact in (root / "storage").rglob("*.json"):
        assert "lab-secret" not in artifact.read_text()
        assert "Set-Cookie" not in artifact.read_text()
