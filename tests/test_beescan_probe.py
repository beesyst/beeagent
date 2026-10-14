import json
import logging
import os
import random
import subprocess
import sys
import time
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest
from beesdk.capabilities import CapabilityStatus

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.beescan_http_runner import (
    bounded_process,
    expected_firewall,
    provider_arguments,
    validate_firewall,
    verify_resolution,
)
from beeagent_module.core.beescan_policy import (
    HTTPX_SHA256,
    ProbePolicy,
    validate_beescan_settings,
)
from beeagent_module.core.beescan_probe import (
    GovernedHttpCaller,
    execute_approved_probe,
    handle_beescan_cli,
    parse_http_output,
)
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import RuntimeContext


@pytest.fixture
def policy():
    message = (
        "BeeScan It4 is required for probe contract tests; install the reviewed package"
    )
    try:
        from beescan.capabilities import http_probe
    except ImportError:
        pytest.fail(message, pytrace=False)
    if not all(
        hasattr(http_probe, name)
        for name in ("HttpFacts", "HttpObservation", "normalize_http_observation")
    ):
        pytest.fail(message, pytrace=False)
    now = datetime.now(UTC)
    return ProbePolicy(
        os.getuid(),
        "project-lab",
        "scope-lab",
        "mission-lab",
        "target-lab",
        "http://127.0.0.1:18080",
        True,
        False,
        now - timedelta(minutes=1),
        now + timedelta(minutes=10),
        "http_probe",
        1,
        2,
        "127.0.0.1",
        True,
        "/opt/beescan/httpx",
        HTTPX_SHA256,
        "1.12.0",
        "/proc/99999999/ns/net",
        "/proc/99999999/ns/user",
        2048,
        16384,
    )


def settings_for(policy):
    config = asdict(policy)
    for key in ("valid_from", "expires_at"):
        config[key] = config[key].isoformat()
    return {
        "modules": {
            "registry": [
                {
                    "id": "beescan",
                    "package": "beescan.module",
                    "entry": "BeeScanModule",
                    "enabled": True,
                }
            ]
        },
        "beescan": {"probe_enabled": True, "approval": config},
    }


def make_caller(policy, tmp_path, reload_policy=None):
    artifacts = ArtifactAPI(
        RuntimeContext(
            "run-test",
            "session-test",
            "http_probe",
            "beescan",
            AuthorityLevel.EXECUTION_CAPABLE,
        ),
        tmp_path,
        logging.getLogger("beescan-test"),
    )
    return GovernedHttpCaller(
        policy=policy,
        reload_policy=reload_policy or (lambda: policy),
        run_id="run-test",
        artifacts=artifacts,
    )


def test_disabled_configuration_without_installed_module():
    validate_beescan_settings({"modules": {"registry": []}})
    validate_beescan_settings({"beescan": {"probe_enabled": False, "approval": None}})
    with pytest.raises(RuntimeError):
        validate_beescan_settings(
            {"beescan": {"probe_enabled": True, "approval": None}}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"approved": False},
        {"excluded": True},
        {"operator_uid": os.getuid() + 1},
        {
            "expires_at": datetime(2020, 1, 1, tzinfo=UTC),
            "valid_from": datetime(2019, 1, 1, tzinfo=UTC),
        },
        {
            "valid_from": datetime(2090, 1, 1, tzinfo=UTC),
            "expires_at": datetime(2091, 1, 1, tzinfo=UTC),
        },
    ],
)
def test_authorization_denies_before_provider(policy, tmp_path, monkeypatch, changes):
    policy = replace(policy, **changes)
    monkeypatch.setattr(
        "beeagent_module.core.beescan_probe.run_provider",
        lambda *a, **k: pytest.fail("unauthorized execution"),
    )
    caller = make_caller(policy, tmp_path)
    result = caller.call("web.probe", policy.intent().payload)
    assert result.status is CapabilityStatus.REFUSED
    assert caller.facts is None
    assert caller.artifacts.list_artifacts() == []


@pytest.mark.parametrize(
    "changes",
    [
        {"origin": "http://other.test"},
        {"request_budget": True},
        {"provider_version": "other"},
        {"method": "GET"},
        {"headers": "secret"},
    ],
)
def test_payload_cannot_override_authority(policy, tmp_path, changes):
    caller = make_caller(policy, tmp_path)
    result = caller.call("web.probe", policy.intent().payload | changes)
    assert result.status is CapabilityStatus.REFUSED
    assert caller.facts is None


def test_changed_live_approval_denies(policy, tmp_path):
    caller = make_caller(policy, tmp_path, lambda: replace(policy, approved=False))
    assert (
        caller.call("web.probe", policy.intent().payload).status
        is CapabilityStatus.REFUSED
    )


def test_exact_kernel_firewall_contract(policy):
    rules = expected_firewall(policy.connected_ip, policy.port)
    validate_firewall(json.dumps({"nftables": rules}).encode(), policy)
    for altered in (
        rules[:2],
        rules + [rules[-1]],
        expected_firewall("127.0.0.2", policy.port),
        expected_firewall(policy.connected_ip, 80),
    ):
        with pytest.raises(PermissionError):
            validate_firewall(json.dumps({"nftables": altered}).encode(), policy)
    changed = json.loads(json.dumps(rules))
    changed[1]["chain"]["policy"] = "accept"
    with pytest.raises(PermissionError):
        validate_firewall(json.dumps({"nftables": changed}).encode(), policy)


def test_dns_literal_change_and_fixed_arguments(policy):
    verify_resolution(policy)
    with pytest.raises(PermissionError, match="dns_changed"):
        verify_resolution(replace(policy, connected_ip="127.0.0.2"))
    arguments = provider_arguments(policy)
    assert arguments.count(policy.origin) == 1
    assert "-no-fallback-scheme" in arguments
    assert "-retries" in arguments and "-disable-update-check" in arguments
    assert not {"-follow-redirects", "-follow-host-redirects", "-proxy"} & set(
        arguments
    )
    assert arguments[arguments.index("-protocol") + 1] == "http11"
    assert arguments[arguments.index("-x") + 1] == "HEAD"
    assert "-auth=false" in arguments
    assert not {
        "-update",
        "-http2",
        "-tls-probe",
        "-ztls",
        "-tls-impersonate",
        "-screenshot",
    } & set(arguments)


def test_previous_provider_digest_is_not_authorized(policy):
    with pytest.raises(ValueError, match="invalid_probe_policy"):
        replace(
            policy,
            sha256="6d78b83b4da452a7e0bd3613c4fae04cbf523209f083904b563f4d4406a680b0",
        )


@pytest.mark.parametrize(
    "record",
    [
        {},
        {"url": "http://other.test", "status_code": 200, "failed": False},
        {"status_code": True},
        {"status_code": "200"},
        {"status_code": 600},
        {"failed": True},
        {"failed": 0},
        {"method": "GET"},
        {"scheme": "ftp"},
        {"input": "http://other.test"},
        {"port": "18081"},
        {"port": 18080},
        {"host": "other.test"},
        {"host": "127.0.0.1:18080"},
        {"host": "127.0.0.1:18081"},
        {"host": None},
        {"host": ["127.0.0.1"]},
        {"host": True},
        {"host_ip": "127.0.0.2"},
        {"host_ip": "127.0.0.1:18080"},
        {"host_ip": None},
        {"host_ip": {"ip": "127.0.0.1"}},
        {"host_ip": 2130706433},
        {"path": "/other"},
        {"content_type": "text/html\n"},
        {"body": "secret"},
        {"headers": {}},
        {"final_url": "http://forbidden.test"},
    ],
)
def test_output_schema_denies(policy, record):
    from beescan.capabilities.http_probe import HostProvenance

    base = {"url": policy.origin, "status_code": 200, "failed": False}
    raw = json.dumps(base | record).encode() if record else b"{}"
    with pytest.raises(ValueError):
        parse_http_output(
            raw,
            policy.intent(),
            HostProvenance("run", "projectdiscovery-httpx", "1.12.0"),
            ("evidence",),
            limit=16384,
            connected_ip=policy.connected_ip,
        )


def test_provider_parser_properties(policy):
    from beescan.capabilities.http_probe import HostProvenance

    provenance = HostProvenance("run", "projectdiscovery-httpx", "1.12.0")
    randomizer = random.Random(301)
    for _ in range(1000):
        raw = randomizer.randbytes(randomizer.randrange(0, 300))
        with pytest.raises(ValueError):
            parse_http_output(
                raw,
                policy.intent(),
                provenance,
                ("evidence",),
                limit=16384,
                connected_ip=policy.connected_ip,
            )
    for raw in (b"{}\n{}", b'{"failed":false,"failed":true}', b"x" * 16385):
        with pytest.raises(ValueError):
            parse_http_output(
                raw,
                policy.intent(),
                provenance,
                ("evidence",),
                limit=16384,
                connected_ip=policy.connected_ip,
            )


@pytest.mark.parametrize(
    "origin,hostname,connected_ip,port",
    [
        ("http://127.0.0.1:18080", "127.0.0.1", "127.0.0.1", "18080"),
        ("https://lab.example.test", "lab.example.test", "127.0.0.1", "443"),
        ("http://lab.example.test:18080", "lab.example.test", "127.0.0.1", "18080"),
        ("http://[::1]:18080", "::1", "::1", "18080"),
    ],
)
def test_provider_origin_metadata_matches_trusted_policy(
    policy, origin, hostname, connected_ip, port
):
    from beescan.capabilities.http_probe import HostProvenance

    policy = replace(policy, origin=origin, connected_ip=connected_ip)
    raw = json.dumps(
        {
            "url": origin,
            "status_code": 302,
            "failed": False,
            "host": hostname,
            "host_ip": connected_ip,
            "port": port,
        }
    ).encode()
    facts = parse_http_output(
        raw,
        policy.intent(),
        HostProvenance("run", "projectdiscovery-httpx", "1.12.0"),
        ("evidence",),
        limit=16384,
        connected_ip=policy.connected_ip,
    )
    assert facts.origin == origin and facts.status_code == 302 and facts.complete


@pytest.mark.parametrize(
    "metadata",
    [
        {"host": "other.test", "host_ip": "127.0.0.1"},
        {"host": "127.0.0.1", "host_ip": "127.0.0.2"},
    ],
)
def test_contradictory_provider_metadata_never_observes(
    policy, tmp_path, monkeypatch, metadata
):
    raw = json.dumps(
        {"url": policy.origin, "status_code": 200, "failed": False} | metadata
    ).encode()
    monkeypatch.setattr(
        "beeagent_module.core.beescan_probe.run_provider", lambda *a, **k: raw
    )
    caller = make_caller(policy, tmp_path)
    result = caller.call("web.probe", policy.intent().payload)
    assert result.status is CapabilityStatus.ERROR and not result.data
    assert caller.facts is None and caller.artifacts.list_artifacts() == []
    settings = settings_for(policy)
    status = execute_approved_probe(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=tmp_path,
        logger=logging.getLogger("test"),
    )
    assert status["status"] == "error" and status["complete"] is False
    assert status["evidence_refs"] == []
    assert not list(tmp_path.rglob("http_observation.json"))
    assert not list(tmp_path.rglob("http-evidence-*.json"))


def test_host_handoff_and_artifacts_with_fixture_provider(
    policy, tmp_path, monkeypatch
):
    raw = json.dumps(
        {
            "url": policy.origin,
            "status_code": 302,
            "failed": False,
            "method": "HEAD",
            "content_type": "text/html; charset=utf-8",
        }
    ).encode()
    monkeypatch.setattr(
        "beeagent_module.core.beescan_probe.run_provider", lambda *a, **k: raw
    )
    settings = settings_for(policy)
    status = execute_approved_probe(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=tmp_path,
        logger=logging.getLogger("test"),
    )
    assert status["status"] == "ok" and status["complete"]
    directory = tmp_path / "runs" / status["run_id"] / "module-beescan"
    observation = json.loads((directory / "http_observation.json").read_text())
    assert observation["facts"]["status_code"] == 302
    assert observation["mission_id"] == policy.mission_id
    assert observation["facts"]["provenance"]["run_id"] == status["run_id"]
    for ref in status["evidence_refs"]:
        assert (directory / (ref + ".json")).is_file()
    assert "charset" not in (directory / "http_observation.json").read_text()


@pytest.mark.parametrize(
    "failure,status",
    [
        (PermissionError("egress_unverified"), "refused"),
        (TimeoutError(), "timeout"),
        (ValueError("malformed"), "error"),
        (OSError("cleanup failed"), "error"),
        (subprocess.TimeoutExpired("sentinel-secret", 2), "error"),
    ],
)
def test_failed_execution_never_observes(
    policy, tmp_path, monkeypatch, failure, status
):
    def fail(*a, **k):
        raise failure

    monkeypatch.setattr("beeagent_module.core.beescan_probe.run_provider", fail)
    settings = settings_for(policy)
    result = execute_approved_probe(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=tmp_path,
        logger=logging.getLogger("test"),
    )
    assert result["status"] == status
    assert result["complete"] is False and result["evidence_refs"] == []
    assert not list(tmp_path.rglob("http_observation.json"))


def test_real_missing_namespace_refuses_without_observation(policy, tmp_path):
    caller = make_caller(policy, tmp_path)
    result = caller.call("web.probe", policy.intent().payload)
    assert result.status is not CapabilityStatus.OK
    assert caller.facts is None


def test_real_bootstrap_preserves_read_only(policy, tmp_path, capsys):
    settings = settings_for(policy)
    settings["beescan"]["probe_enabled"] = False
    assert (
        handle_beescan_cli(
            ["bootstrap"],
            settings=settings,
            reload_settings=lambda: settings,
            storage_dir=tmp_path,
            logger=logging.getLogger("test"),
        )
        == 0
    )
    result = json.loads(next(tmp_path.rglob("module_result.json")).read_text())
    assert result["authority"] == "read_only"
    assert list(tmp_path.rglob("bootstrap_health.json"))
    assert not list(tmp_path.rglob("http_probe_status.json"))


def test_real_bounded_process_timeout_output_and_environment():
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        bounded_process(
            [sys.executable, "-I", "-c", "import time;time.sleep(10)"],
            seconds=1,
            limit=1024,
            memory_mb=256,
        )
    assert time.monotonic() - started < 4
    with pytest.raises(ValueError, match="output_limit"):
        bounded_process(
            [sys.executable, "-I", "-c", 'print("x"*20000)'],
            seconds=2,
            limit=1024,
            memory_mb=256,
        )
    code, raw = bounded_process(
        [sys.executable, "-I", "-c", "import os;print(sorted(os.environ))"],
        seconds=2,
        limit=1024,
        memory_mb=256,
    )
    assert code == 0
    assert b"OPENAI_API_KEY" not in raw and b"PROXY" not in raw


def test_dns_rebinding_rechecked_before_provider(policy, tmp_path, monkeypatch):
    changed = replace(policy, origin="http://lab.example.test:18080")
    addresses = iter([b'["127.0.0.1"]', b'["127.0.0.2"]'])
    monkeypatch.setattr(
        "beeagent_module.core.beescan_http_runner.bounded_process",
        lambda *a, **k: (0, next(addresses)),
    )

    def provider(*args, reauthorize):
        reauthorize()
        pytest.fail("Changed DNS must refuse before provider execution")

    monkeypatch.setattr("beeagent_module.core.beescan_probe.run_provider", provider)
    caller = make_caller(changed, tmp_path)
    result = caller.call("web.probe", changed.intent().payload)
    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics["reason"] == "dns_changed"
    assert caller.facts is None


def test_one_shot_budget_and_evidence_envelope(policy, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "beeagent_module.core.beescan_probe.run_provider",
        lambda *a, **k: json.dumps(
            {"url": policy.origin, "status_code": 200, "failed": False}
        ).encode(),
    )
    caller = make_caller(policy, tmp_path)
    result = caller.call("web.probe", policy.intent().payload)
    assert result.status is CapabilityStatus.OK
    assert set(result.data) == {"evidence_refs"} and not result.diagnostics
    repeated = caller.call("web.probe", policy.intent().payload)
    assert repeated.status is CapabilityStatus.REFUSED
    assert repeated.diagnostics["reason"] == "request_budget_exceeded"


def test_real_memory_limit_and_descendant_cleanup(tmp_path):
    code, output = bounded_process(
        [
            sys.executable,
            "-I",
            "-c",
            'try: value=bytearray(400*1024*1024)\nexcept MemoryError: print("bounded")',
        ],
        seconds=2,
        limit=1024,
        memory_mb=256,
    )
    assert code == 0 and output.strip() == b"bounded"
    pid_file = tmp_path / "child-pid"
    script = (
        "import os,time;from pathlib import Path;pid=os.fork();"
        f"Path({str(pid_file)!r}).write_text(str(os.getpid())) if pid==0 else None;"
        "time.sleep(10)"
    )
    with pytest.raises(TimeoutError):
        bounded_process(
            [sys.executable, "-I", "-c", script], seconds=1, limit=1024, memory_mb=256
        )
    pid = int(pid_file.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            state = open(f"/proc/{pid}/stat").read().split()[2]
        except FileNotFoundError, ProcessLookupError:
            return
        if state == "Z":
            return
        time.sleep(0.02)
    pytest.fail("Worker descendant survived timeout")


@pytest.mark.parametrize("kind", ["fifo", "symlink"])
def test_provider_special_file_refuses_without_blocking(policy, tmp_path, kind):
    from beeagent_module.core.beescan_http_runner import _provider_snapshot

    executable = tmp_path / "httpx"
    if kind == "fifo":
        os.mkfifo(executable)
    else:
        executable.symlink_to(sys.executable)
    started = time.monotonic()
    with pytest.raises(PermissionError, match="provider_integrity"):
        _provider_snapshot(replace(policy, executable=str(executable)), tmp_path)
    assert time.monotonic() - started < 1
