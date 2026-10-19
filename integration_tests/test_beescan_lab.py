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

from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
from beeagent_module.integrations.beescan.probe import execute_approved_probe


@pytest.fixture
def lab(tmp_path, request):
    provider = os.environ.get("BEEAGENT_BEESCAN_LAB_PROVIDER")
    if not provider:
        pytest.fail("Explicit pinned lab provider required", pytrace=False)
    try:
        from beescan.capabilities import http_probe
    except ImportError:
        pytest.fail("BeeScan It4 is required for the laboratory gate", pytrace=False)
    if not all(
        hasattr(http_probe, name)
        for name in ("HttpFacts", "HttpObservation", "normalize_http_observation")
    ):
        pytest.fail("BeeScan It4 is required for the laboratory gate", pytrace=False)
    tls = getattr(request, "param", False)
    if tls:
        subprocess.run(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(tmp_path / "server.key"),
                "-out",
                str(tmp_path / "server.pem"),
                "-days",
                "1",
                "-subj",
                "/CN=127.0.0.1",
                "-addext",
                "subjectAltName=IP:127.0.0.1",
            ],
            check=True,
            capture_output=True,
        )
        trust = tmp_path / "trust"
        trust.mkdir()
        (trust / "lab.pem").write_bytes((tmp_path / "server.pem").read_bytes())
        subprocess.run(
            ["/usr/bin/openssl", "rehash", str(trust)], check=True, capture_output=True
        )
    (tmp_path / "mode").write_text("ok")
    worker = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "beescan_lab_worker.py"
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
        now = datetime.now(UTC)
        policy = ProbePolicy(
            os.getuid(),
            "project-lab",
            "scope-lab",
            "mission-lab",
            "target-lab",
            ("https" if tls else "http") + "://127.0.0.1:18080",
            True,
            False,
            now - timedelta(minutes=1),
            now + timedelta(minutes=10),
            "http_probe",
            1,
            5,
            "127.0.0.1",
            True,
            provider,
            HTTPX_SHA256,
            "1.12.0",
            f"/proc/{process.pid}/ns/net",
            f"/proc/{process.pid}/ns/user",
            2048,
            16384,
        )
        yield policy, tmp_path
    finally:
        process.terminate()
        process.wait(timeout=3)


def run_lab(policy, root):
    config = asdict(policy)
    for key in ("valid_from", "expires_at"):
        config[key] = config[key].isoformat()
    settings = {
        "modules": {"registry": [{"id": "beescan", "enabled": True}]},
        "beescan": {"probe_enabled": True, "approval": config},
    }
    return execute_approved_probe(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("lab-test"),
    )


def assert_kernel_egress(policy):
    script = """import json,socket
results=[]
for address,port,family in (("127.0.0.1",18080,socket.AF_INET),("127.0.0.1",18081,socket.AF_INET),("127.0.0.2",18080,socket.AF_INET),("::1",18080,socket.AF_INET6)):
 s=socket.socket(family);s.settimeout(0.5)
 try:s.connect((address,port));results.append("connected")
 except TimeoutError:results.append("blocked")
 finally:s.close()
print(json.dumps(results))
assert results==["connected","blocked","blocked","blocked"]
"""
    command = [
        "/usr/bin/nsenter",
        "--preserve-credentials",
        "--user=" + policy.user_namespace,
        "--net=" + policy.network_namespace,
        "--",
        "/usr/bin/bwrap",
        "--unshare-all",
        "--unshare-user",
        "--share-net",
        "--disable-userns",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--",
        "/usr/bin/python3",
        "-I",
        "-c",
        script,
    ]
    result = subprocess.run(
        command, capture_output=True, timeout=5, env={"PATH": "/usr/bin:/bin"}
    )
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == ["connected", "blocked", "blocked", "blocked"]


def test_real_provider_positive_redirect_timeout_and_denials(lab, monkeypatch):
    policy, root = lab
    assert_kernel_egress(policy)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://127.0.0.1:18081")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    positive = run_lab(policy, root)
    assert positive["status"] == "ok" and positive["complete"]
    assert json.loads((root / "counts.json").read_text()) == {"18080": 1, "18081": 0}
    (root / "mode").write_text("redirect")
    redirect = run_lab(policy, root)
    assert redirect["status"] == "ok"
    observation = (
        root
        / "storage"
        / "runs"
        / redirect["run_id"]
        / "module-beescan"
        / "http_observation.json"
    )
    assert json.loads(observation.read_text())["facts"]["status_code"] == 302
    assert json.loads((root / "counts.json").read_text()) == {"18080": 2, "18081": 0}
    (root / "mode").write_text("timeout")
    timeout = run_lab(replace(policy, time_budget_seconds=2), root)
    assert timeout["status"] == "timeout" and not timeout["complete"]
    for mode in ("malformed", "oversized"):
        (root / "mode").write_text(mode)
        failed = run_lab(replace(policy, output_bytes=1024), root)
        assert failed["status"] == "error" and not failed["complete"]
        assert failed["evidence_refs"] == []
        assert not (
            root
            / "storage"
            / "runs"
            / failed["run_id"]
            / "module-beescan"
            / "http_observation.json"
        ).exists()
    (root / "mode").write_text("ok")
    count = json.loads((root / "counts.json").read_text())["18080"]
    for changed in (
        replace(policy, connected_ip="127.0.0.2"),
        replace(policy, excluded=True),
        replace(policy, approved=False),
        replace(policy, operator_uid=os.getuid() + 1),
        replace(policy, expires_at=datetime.now(UTC) - timedelta(seconds=1)),
        replace(policy, executable=str(root / "missing-httpx")),
        replace(
            policy,
            network_namespace="/proc/99999999/ns/net",
            user_namespace="/proc/99999999/ns/user",
        ),
    ):
        result = run_lab(changed, root)
        assert result["status"] == "refused" and not result["complete"]
        assert result["evidence_refs"] == []
    assert json.loads((root / "counts.json").read_text()) == {
        "18080": count,
        "18081": 0,
    }
    for artifact in (root / "storage").rglob("*.json"):
        assert "lab-secret" not in artifact.read_text()
        assert "Set-Cookie" not in artifact.read_text()
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
        env={"PATH": "/usr/bin:/bin"},
    )
    unverified = run_lab(policy, root)
    assert unverified["status"] == "refused"
    assert unverified["reason"] == "egress_unverified"
    assert not unverified["complete"] and unverified["evidence_refs"] == []
    assert json.loads((root / "counts.json").read_text()) == {
        "18080": count,
        "18081": 0,
    }
