import copy
import json
import logging
import os
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from beeagent_module.integrations.beescan import detection_runner, egress
from beeagent_module.integrations.beescan.assessment import execute_approved_assessment
from beeagent_module.integrations.beescan.dast_runner import snapshot_zap
from beeagent_module.integrations.beescan.git_exposure import GitExposurePolicy
from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
from beeagent_module.integrations.beescan.providers import (
    managed_zap_archive,
    provider_root,
)
from tests import test_beescan_detection
from tests.settings_support import read_test_settings
from tests.test_beescan_detection import settings_for

approved = test_beescan_detection.approved


def _lab_provider(variable: str, name: str) -> Path:
    path = Path(os.environ.get(variable, provider_root() / name))
    if not path.is_file():
        pytest.fail(f"Pinned laboratory provider unavailable: {path}", pytrace=False)
    return path


@pytest.fixture(scope="session")
def zap_distribution(tmp_path_factory):
    archive = managed_zap_archive()
    if not archive.is_file():
        pytest.fail(f"Pinned ZAP archive unavailable: {archive}", pytrace=False)
    return snapshot_zap(archive, tmp_path_factory.mktemp("zap-distribution"))


@pytest.fixture(params=[False, True], ids=["http", "https"])
def managed_lab(approved, monkeypatch, request):
    detection, _, root = approved
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(key, "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    pasta = _lab_provider("BEEAGENT_BEESCAN_PASTA", "pasta")
    httpx = _lab_provider("BEEAGENT_BEESCAN_LAB_PROVIDER", "httpx")
    nuclei = _lab_provider("BEEAGENT_BEESCAN_NUCLEI", "nuclei")
    binary = root / "providers/pasta"
    binary.parent.mkdir(mode=0o700)
    binary.write_bytes(egress._binary(pasta))
    binary.chmod(0o500)
    monkeypatch.setattr(egress, "executable_path", lambda: binary)
    original_spawn = egress.ManagedEgress._spawn
    sessions = []

    def spawn(self, command, **kwargs):
        if "exec" in command:
            command = [*command, "--map-host-loopback", "192.0.2.1"]
            sessions.append(self)
        return original_spawn(self, command, **kwargs)

    monkeypatch.setattr(egress.ManagedEgress, "_spawn", spawn)
    requests = []
    fixture_root = root / "filesystem"
    document_root = fixture_root / "www/images"
    nonrecursive = str(request.param).startswith("dast-nonrecursive")
    if (
        request.param in {"dast-vulnerable", "dast-vulnerable-alt", "dast-fixed"}
        or nonrecursive
    ):
        document_root.mkdir(parents=True)
        (document_root / "fixture.txt").write_text("Synthetic public fixture\n")
        (fixture_root / "etc").mkdir()
        (fixture_root / "etc/passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")

    class Handler(BaseHTTPRequestHandler):
        def respond(self):
            requests.append((self.command, self.path))
            if nonrecursive or request.param in {
                "dast-vulnerable",
                "dast-vulnerable-alt",
                "dast-fixed",
            }:
                from urllib.parse import parse_qs, urlsplit

                parsed = urlsplit(self.path)
                alternate = str(request.param).endswith("-alt")
                field = "document" if alternate else "file"
                expected = "/retrieve" if alternate else "/"
                if parsed.path == "/" and not parsed.query:
                    link = (
                        "/retrieve?document=fixture.txt"
                        if alternate
                        else "/?file=fixture.txt"
                    )
                    body = f'<a href="{link}">fixture</a>'.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if parsed.path != expected:
                    self.send_error(404)
                    return
                selected = parse_qs(parsed.query).get(field, ["fixture.txt"])[0]
                doubledecode = "doubledecode" in str(request.param)
                if doubledecode and selected != "fixture.txt" and "%" not in selected:
                    self.send_error(400)
                    return
                if doubledecode:
                    from urllib.parse import unquote

                    selected = unquote(selected)
                elif nonrecursive:
                    selected = selected.replace("../", "")
                candidate = (
                    (document_root / selected).resolve()
                    if not selected.startswith("/")
                    else (fixture_root / selected.lstrip("/")).resolve()
                )
                boundary = (
                    document_root if "fixed" in str(request.param) else fixture_root
                )
                allowed = candidate.is_relative_to(boundary) and candidate.is_file()
                body = candidate.read_bytes() if allowed else b"Not found"
                if request.param == "dast-nonrecursive-reflection":
                    body, allowed = selected.encode(), True
                if request.param == "dast-nonrecursive-ambiguous":
                    body, allowed = (fixture_root / "etc/passwd").read_bytes(), True
                self.send_response(200 if allowed else 404)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = b"ref: refs/heads/lab-only\n" if self.path == "/.git/HEAD" else b""
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Strict-Transport-Security", "max-age=60")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        do_HEAD = respond
        do_GET = respond

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls = request.param
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
                str(root / "key.pem"),
                "-out",
                str(root / "cert.pem"),
                "-days",
                "1",
                "-subj",
                "/CN=192.0.2.1",
                "-addext",
                "subjectAltName=IP:192.0.2.1",
            ],
            check=True,
            capture_output=True,
            timeout=10,
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(root / "cert.pem", root / "key.pem")
        server.socket = context.wrap_socket(server.socket, server_side=True)
        trust = root / "trust"
        trust.mkdir()
        (trust / "lab.pem").write_bytes((root / "cert.pem").read_bytes())
        subprocess.run(
            ["/usr/bin/openssl", "rehash", str(trust)],
            check=True,
            capture_output=True,
            timeout=3,
        )
        original_process = detection_runner.bounded_process

        def process(argv, **kwargs):
            if "/capture.py" in argv:
                argv = list(argv)
                index = argv.index("/usr/bin/python3") - 1
                argv[index:index] = ["--ro-bind", str(trust), "/etc/ssl/certs"]
            return original_process(argv, **kwargs)

        monkeypatch.setattr(detection_runner, "bounded_process", process)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    logger = logging.getLogger("managed-lab")
    handler = logging.FileHandler(root / "managed.log")
    (root / "managed.log").chmod(0o600)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    previous_umask = os.umask(0o077)
    try:
        origin = f"{'https' if tls else 'http'}://192.0.2.1:{server.server_port}"
        detection = replace(
            detection,
            origin=origin,
            connected_ip="192.0.2.1",
            network_namespace=egress.MANAGED_NET,
            user_namespace=egress.MANAGED_USER,
            executable=str(nuclei),
            time_budget_seconds=30,
        )
        settings = settings_for(detection)
        fields = {
            name: getattr(detection, name) for name in ProbePolicy.__dataclass_fields__
        }
        fields.update(
            method="http_probe",
            sha256=HTTPX_SHA256,
            provider_version="1.12.0",
            executable=str(httpx),
            time_budget_seconds=10,
        )
        probe = ProbePolicy(**fields)
        approval = asdict(probe)
        for name in ("valid_from", "expires_at"):
            approval[name] = approval[name].isoformat()
        settings["beescan"].update(probe_enabled=True, approval=approval)
        yield settings, root, requests, sessions, probe
    finally:
        os.umask(previous_umask)
        logger.removeHandler(handler)
        handler.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("exposure", [False, True])
def test_real_managed_assessment(managed_lab, exposure):
    settings, root, requests, sessions, probe = managed_lab
    if exposure:
        fields = {
            name: getattr(probe, name)
            for name in GitExposurePolicy.__dataclass_fields__
            if hasattr(probe, name)
        }
        fields.update(
            method="git_head_exposure",
            http_method="GET",
            path="/.git/HEAD",
            output_bytes=4096,
        )
        for name in ("valid_from", "expires_at"):
            fields[name] = fields[name].isoformat()
        settings["beescan"].update(
            git_exposure_enabled=True, git_exposure_approval=fields
        )
    original = copy.deepcopy(settings)
    result = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-lab"),
        http_signals=True,
        git_exposure=exposure,
    )
    assert result["complete"], result
    assert settings == original
    assert requests == [
        ("HEAD", "/"),
        ("GET", "/"),
        *(([("GET", "/.git/HEAD")]) if exposure else []),
    ]
    assert len(sessions) == 1
    session = sessions[0]
    assert egress._active.get() is None
    assert session.helper is not None
    assert session.supervisor is not None
    assert (
        session.closed
        and session.helper.poll() is not None
        and session.supervisor.poll() is not None
    )
    parent = root / "storage/runs" / result["assessment_run_id"] / "module-beescan"
    evidence = json.loads((parent / "egress_lifecycle.json").read_text())
    assert (
        evidence["cleanup_verified"]
        and evidence["assessment_run_id"] == result["assessment_run_id"]
    )
    for artifact in (root / "storage").rglob("*.json"):
        assert artifact.stat().st_mode & 0o077 == 0
        assert "refs/heads" not in artifact.read_text()
    from beeagent_module.integrations.beescan.review_source import load_assessment

    _, snapshot = load_assessment(
        root / "storage", result["assessment_run_id"], settings
    )
    assert (result["assessment_run_id"], "egress_lifecycle.json") in snapshot.files


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
def test_real_missing_helper_fails_closed(managed_lab):
    settings, root, requests, sessions, _probe = managed_lab
    egress.executable_path().unlink()
    result = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-prerequisite"),
    )
    assert result["status"] == "refused"
    assert result["reason"] == "egress_prerequisite_unavailable"
    assert not result["complete"]
    assert requests == [] and sessions == []


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
def test_real_managed_provider_denials_and_firewall_immutability(managed_lab):
    _settings, root, requests, sessions, probe = managed_lab

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    with socket.socket() as forbidden:
        forbidden.bind(("127.0.0.1", 0))
        forbidden.listen(8)
        forbidden.settimeout(0.2)
        denied_port = forbidden.getsockname()[1]
        script = root / "untrusted.py"
        script.write_text("""import ctypes,json,os,socket,subprocess,sys
port,denied=map(int,sys.argv[1:])
results={}
for name,family,address,p in (("allowed",socket.AF_INET,"192.0.2.1",port),("port",socket.AF_INET,"192.0.2.1",denied),("ip",socket.AF_INET,"192.0.2.2",port),("ipv6",socket.AF_INET6,"::1",port),("loopback",socket.AF_INET,"127.0.0.1",denied),("route",socket.AF_INET,"10.0.2.2",denied)):
 with socket.socket(family) as s:
  s.settimeout(.3 if name == "allowed" else .1)
  try:
   s.connect((address,p));s.sendall(b"HEAD / HTTP/1.0\\r\\n\\r\\n");results[name]=s.recv(16).startswith(b"HTTP/")
  except OSError:results[name]=False
for name,command in (("firewall",["/usr/sbin/nft","flush","ruleset"]),("routes",["/usr/sbin/ip","route","add","default","dev","lo"]),("userns",["/usr/bin/unshare","-Urn","true"])):
 results[name]=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2).returncode
try:socket.socket(socket.AF_PACKET,socket.SOCK_RAW).close();results["raw"]=True
except OSError:results["raw"]=False
results["proxy"]=[k for k in os.environ if "proxy" in k.lower()]
fd=os.open("/proc/1/ns/net",os.O_RDONLY)
results["setns"]=ctypes.CDLL(None).setns(fd,0)
os.close(fd)
print(json.dumps(results))
assert results["allowed"] and not any(results[k] for k in ("port","ip","ipv6","loopback","route","raw","proxy"))
assert all(results[k]!=0 for k in ("firewall","routes","userns","setns"))
""")
        session = egress.ManagedEgress(
            probe,
            artifacts=Artifacts(),
            assessment_run_id="run-egress-gate",
            seconds=10,
        )
        try:
            session.start()
            from beeagent_module.integrations.beescan.http_runner import _open_namespace

            assert session.supervisor is not None
            namespace = f"/proc/{session.supervisor.pid}/ns/net"
            for kind, uid in (
                (0x40000000, os.getuid() + 1),
                (0x10000000, os.getuid()),
            ):
                with pytest.raises(PermissionError, match="isolation_unavailable"):
                    _open_namespace(namespace, kind, uid)
            identities = session.identities
            assert identities is not None
            try:
                session.identities = tuple(value + 1 for value in identities)
                with pytest.raises(PermissionError, match="egress_namespace_changed"):
                    session.check_alive()
            finally:
                session.identities = identities
            before = session.inspect("/usr/sbin/nft", "-j", "list", "ruleset")
            raw = session.inspect(
                "/usr/bin/bwrap",
                "--unshare-all",
                "--unshare-user",
                "--share-net",
                "--disable-userns",
                "--cap-drop",
                "ALL",
                "--uid",
                "0",
                "--gid",
                "0",
                "--die-with-parent",
                "--new-session",
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
                "--ro-bind",
                str(script),
                "/untrusted.py",
                "--",
                "/usr/bin/python3",
                "-I",
                "/untrusted.py",
                str(probe.port),
                str(denied_port),
            )
            assert json.loads(raw)["allowed"]
            assert before == session.inspect("/usr/sbin/nft", "-j", "list", "ruleset")
            with pytest.raises(TimeoutError):
                forbidden.accept()
            assert requests == [("HEAD", "/")]
        finally:
            session.close()
        assert len(sessions) == 1 and session.evidence["cleanup_verified"]


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
@pytest.mark.parametrize("mutation", ["firewall", "route"])
def test_real_enforcement_change_refuses_next_stage(managed_lab, monkeypatch, mutation):
    from beeagent_module.integrations.beescan import assessment as host

    settings, root, requests, sessions, _probe = managed_lab
    original = host.execute_approved_probe

    def probe(**kwargs):
        result = original(**kwargs)
        assert result["complete"]
        session = sessions[0]
        if mutation == "firewall":
            session.inspect("/usr/sbin/nft", "flush", "ruleset")
        else:
            session.inspect("/usr/sbin/ip", "route", "replace", "default", "dev", "lo")
        return result

    monkeypatch.setattr(host, "execute_approved_probe", probe)
    result = host.execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-enforcement"),
    )
    assert not result["complete"]
    assert requests == [("HEAD", "/")]
    session = sessions[0]
    assert session.helper is not None
    assert session.supervisor is not None
    assert (
        session.closed
        and session.helper.poll() is not None
        and session.supervisor.poll() is not None
    )
    assert session.evidence["enforcement_verified"] is False


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
@pytest.mark.parametrize("failure", [KeyboardInterrupt, TimeoutError, OSError])
def test_real_partial_setup_cleanup(managed_lab, monkeypatch, failure):
    _settings, root, _requests, _sessions, probe = managed_lab
    original_spawn = egress.ManagedEgress._spawn

    def spawn(self, command, **kwargs):
        if "exec" in command:
            raise failure("interrupted_setup")
        return original_spawn(self, command, **kwargs)

    monkeypatch.setattr(egress.ManagedEgress, "_spawn", spawn)

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    session = egress.ManagedEgress(
        probe, artifacts=Artifacts(), assessment_run_id="run-interrupted", seconds=5
    )
    with pytest.raises(failure):
        session.start()
    assert session.supervisor is not None
    assert session.closed and session.supervisor.poll() is not None
    assert session.evidence["cleanup_verified"]


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
def test_real_readiness_timeout_cleanup(managed_lab, monkeypatch):
    _settings, root, _requests, _sessions, probe = managed_lab
    original_inspect = egress.ManagedEgress.inspect

    def inspect(self, *arguments):
        if arguments[0] == "/usr/sbin/ip":
            return b"[]"
        return original_inspect(self, *arguments)

    monkeypatch.setattr(egress.ManagedEgress, "inspect", inspect)

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    session = egress.ManagedEgress(
        probe, artifacts=Artifacts(), assessment_run_id="run-timeout", seconds=5
    )
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        session.start()
    assert time.monotonic() - started < 8
    assert session.helper is not None
    assert session.supervisor is not None
    assert (
        session.closed
        and session.helper.poll() is not None
        and session.supervisor.poll() is not None
    )


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
@pytest.mark.parametrize("_repeat", range(5))
@pytest.mark.parametrize("parent_signal", [signal.SIGKILL, signal.SIGTERM])
def test_parent_death_removes_managed_execution_authority(
    managed_lab, _repeat, parent_signal
):
    import selectors

    _settings, root, _requests, _sessions, _probe = managed_lab
    script = root / "parent.py"
    script.write_text("""import json,os,signal,sys
from pathlib import Path
from types import SimpleNamespace
from beeagent_module.integrations.beescan import egress
root=Path(sys.argv[1]);egress.executable_path=lambda:root/"providers/pasta"
class Artifacts:
 def write_json(self,name,data):
  path=root/name;path.write_text(json.dumps(data));return path
policy=SimpleNamespace(connected_ip="192.0.2.1",port=443,operator_uid=os.getuid())
session=egress.ManagedEgress(policy,artifacts=Artifacts(),assessment_run_id="run-parent-death",seconds=5)
session.start()
assert session.supervisor is not None
assert session.helper is not None
assert session.temporary is not None
print(json.dumps({"pids":[session.supervisor.pid,session.helper.pid],"temporary":session.temporary.name}),flush=True)
signal.pause()
""")
    process = subprocess.Popen(
        [sys.executable, "-I", str(script), str(root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        stdout = process.stdout
        assert stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(stdout, selectors.EVENT_READ)
            assert selector.select(5)
            ready = json.loads(os.read(stdout.fileno(), 4096))
            pids = ready["pids"]
        process.send_signal(parent_signal)
        process.wait(timeout=2)
        deadline = time.monotonic() + 3
        while True:
            live = []
            for pid in pids:
                try:
                    state = (
                        Path(f"/proc/{pid}/stat")
                        .read_text()
                        .split(")", 1)[1]
                        .split()[0]
                    )
                except FileNotFoundError:
                    continue
                if state != "Z":
                    live.append(pid)
            if not live:
                break
            assert time.monotonic() < deadline, live
            time.sleep(0.05)
        assert not Path(ready["temporary"]).exists()
    finally:
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
        finally:
            if process.stdout is not None:
                process.stdout.close()


def test_sequential_managed_assessments_do_not_inherit_authority(managed_lab):
    settings, root, requests, sessions, _probe = managed_lab
    results = []
    for _ in range(2):
        result = execute_approved_assessment(
            settings=settings,
            reload_settings=lambda: settings,
            storage_dir=root / "storage",
            logger=logging.getLogger("managed-lab"),
        )
        assert result["complete"], result
        results.append(result)
        assert egress._active.get() is None
        session = sessions[-1]
        assert session.helper is not None
        assert session.supervisor is not None
        assert session.temporary is not None
        assert session.helper.poll() is not None
        assert session.supervisor.poll() is not None
        assert not Path(session.temporary.name).exists()
        for process in (session.helper, session.supervisor):
            for stream in (process.stdin, process.stdout):
                assert stream is None or stream.closed
        assert session.identities is not None
        handles = {
            f"user:[{session.identities[0]}]",
            f"net:[{session.identities[1]}]",
        }
        for descriptor in Path("/proc/self/fd").iterdir():
            try:
                target = str(descriptor.readlink())
            except FileNotFoundError:
                continue
            assert target not in handles
        with pytest.raises(PermissionError, match="egress_session_unavailable"):
            session.check_alive()
        with pytest.raises(PermissionError):
            egress.resolve_namespace(egress.MANAGED_NET)
    assert len(sessions) == 2
    assert results[0]["assessment_run_id"] != results[1]["assessment_run_id"]
    assert sessions[0] is not sessions[1]
    assert requests == [("HEAD", "/"), ("GET", "/")] * 2


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
@pytest.mark.parametrize("remove_approved", [False, True])
def test_managed_dns_membership_does_not_expand_authority(
    managed_lab, monkeypatch, remove_approved
):
    from beeagent_module.integrations.beescan import http_runner

    settings, root, requests, sessions, probe = managed_lab
    for section in ("approval", "detection_approval"):
        settings["beescan"][section]["origin"] = f"http://lab.test:{probe.port}"
    original = http_runner.bounded_process
    resolutions = []

    def process(argv, **kwargs):
        if any("socket.getaddrinfo" in item for item in argv):
            addresses = ["192.0.2.2", "2001:db8::1"]
            if not remove_approved or not requests:
                addresses.append("192.0.2.1")
            resolutions.append(addresses)
            return 0, json.dumps(addresses).encode()
        return original(argv, **kwargs)

    monkeypatch.setattr(http_runner, "bounded_process", process)
    result = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-lab"),
    )
    assert result["complete"] is not remove_approved, result
    assert requests == [("HEAD", "/"), *([] if remove_approved else [("GET", "/")])]
    assert resolutions and len(sessions) == 1
    assert sessions[0].evidence["cleanup_verified"]
    assert sessions[0].helper is not None
    assert sessions[0].supervisor is not None
    assert sessions[0].helper.poll() is not None
    assert sessions[0].supervisor.poll() is not None


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
def test_trusted_firewall_removal_exposes_helper_trust_boundary(managed_lab):
    _settings, root, _requests, _sessions, probe = managed_lab

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    with socket.socket() as forbidden:
        forbidden.bind(("127.0.0.1", 0))
        forbidden.listen(1)
        forbidden.settimeout(0.2)
        port = forbidden.getsockname()[1]
        session = egress.ManagedEgress(
            probe,
            artifacts=Artifacts(),
            assessment_run_id="run-trust-boundary",
            seconds=5,
        )
        script = (
            "import socket; s=socket.socket(); s.settimeout(.2); "
            f"print(s.connect_ex(('192.0.2.1',{port}))); s.close()"
        )
        try:
            session.start()
            assert session.inspect("/usr/bin/python3", "-I", "-c", script) != b"0\n"
            with pytest.raises(TimeoutError):
                forbidden.accept()
            session.inspect("/usr/sbin/nft", "flush", "ruleset")
            assert session.inspect("/usr/bin/python3", "-I", "-c", script) == b"0\n"
            connection, _ = forbidden.accept()
            connection.close()
        finally:
            with pytest.raises(PermissionError, match="egress_unverified"):
                session.close()
        assert not session.evidence["enforcement_verified"]
        assert session.evidence["cleanup_verified"]
        assert session.helper is not None
        assert session.supervisor is not None
        assert session.helper.poll() is not None
        assert session.supervisor.poll() is not None


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
def test_real_launcher_managed_assessment(managed_lab):
    import yaml

    settings, root, requests, _sessions, _probe = managed_lab
    repository = Path(__file__).resolve().parents[1]
    (root / "beescan").symlink_to(
        repository.parent / "beescan", target_is_directory=True
    )
    project = root / "cli-project"
    project.mkdir(mode=0o700)
    for source in repository.iterdir():
        if source.name not in {
            ".git",
            ".venv",
            ".env",
            ".env.example",
            "config",
            "logs",
            "storage",
            "build",
            "dist",
        }:
            (project / source.name).symlink_to(source)
    (project / "config").mkdir()
    for source in (repository / "config").iterdir():
        if source.name != "settings.yml":
            (project / "config" / source.name).symlink_to(source)
    config = read_test_settings()
    config["beescan"] = settings["beescan"]
    for item in config["modules"]["registry"]:
        item["enabled"] = item["id"] == "beescan"
    (project / "config/settings.yml").write_text(yaml.safe_dump(config))
    for name in (".env", ".env.example"):
        (project / name).touch(mode=0o600)
    hooks = project / "hooks"
    hooks.mkdir()
    (hooks / "sitecustomize.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "from beeagent_module.core import paths\n"
        "from beeagent_module.integrations.beescan import egress\n"
        "paths.ROOT_DIR=Path(os.environ['BEEAGENT_BS7_LAB_ROOT'])\n"
        "egress.executable_path=lambda:paths.ROOT_DIR.parent/'providers/pasta'\n"
        "original=egress.ManagedEgress._spawn\n"
        "def spawn(self,command,**kwargs):\n"
        " if 'exec' in command:command=[*command,'--map-host-loopback','192.0.2.1']\n"
        " return original(self,command,**kwargs)\n"
        "egress.ManagedEgress._spawn=spawn\n"
    )
    uv = shutil.which("uv")
    assert uv is not None
    subprocess.run(
        [uv, "sync", "--frozen", "--no-dev", "--extra", "beescan"],
        cwd=project,
        env={
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(project / ".venv"),
            "UV_OFFLINE": "1",
        },
        capture_output=True,
        check=True,
        timeout=120,
    )
    result = subprocess.run(
        ["./start.sh", "beescan", "assess", "--http-signals"],
        cwd=project,
        env={
            **os.environ,
            "PYTHONPATH": str(hooks),
            "BEEAGENT_BS7_LAB_ROOT": str(project),
            "UV_PROJECT_ENVIRONMENT": str(project / ".venv"),
            "UV_OFFLINE": "1",
        },
        capture_output=True,
        check=False,
        timeout=120,
    )
    (root / "launcher.stdout").write_bytes(result.stdout)
    (root / "launcher.stderr").write_bytes(result.stderr)
    assert result.returncode == 0, (result.stdout, result.stderr)
    terminal = json.loads(result.stdout.splitlines()[-1])
    assert terminal["complete"]
    assert requests == [("HEAD", "/"), ("GET", "/")]
    evidence = json.loads(
        (
            project
            / "storage/runs"
            / terminal["assessment_run_id"]
            / "module-beescan/egress_lifecycle.json"
        ).read_text()
    )
    assert evidence["state"] == "closed" and evidence["cleanup_verified"]
    for key in ("helper_pid", "supervisor_pid"):
        assert not Path(f"/proc/{evidence[key]}").exists()


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
@pytest.mark.parametrize("section", ["approval", "detection_approval"])
@pytest.mark.parametrize("disabled", [False, True])
def test_real_missing_authority_creates_no_session(managed_lab, section, disabled):
    settings, root, requests, sessions, _probe = managed_lab
    if disabled:
        flag = "probe_enabled" if section == "approval" else "detection_enabled"
        settings["beescan"][flag] = False
    else:
        settings["beescan"][section] = None
    result = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-lab"),
    )
    assert not result["complete"]
    assert not sessions and not requests
    assert egress._active.get() is None


@pytest.mark.parametrize("managed_lab", [False], indirect=True)
@pytest.mark.parametrize("section", ["approval", "detection_approval"])
def test_real_revocation_stops_managed_assessment(managed_lab, monkeypatch, section):
    from beeagent_module.integrations.beescan import assessment as host

    settings, root, requests, sessions, _probe = managed_lab
    original = host.execute_approved_probe

    def probe(**kwargs):
        result = original(**kwargs)
        assert result["complete"], result
        settings["beescan"][section]["approved"] = False
        return result

    monkeypatch.setattr(host, "execute_approved_probe", probe)
    result = execute_approved_assessment(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root / "storage",
        logger=logging.getLogger("managed-lab"),
    )
    assert not result["complete"]
    assert requests == [("HEAD", "/")]
    assert len(sessions) == 1
    assert sessions[0].evidence["cleanup_verified"]
    assert sessions[0].helper is not None
    assert sessions[0].supervisor is not None
    assert sessions[0].helper.poll() is not None
    assert sessions[0].supervisor.poll() is not None


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
@pytest.mark.parametrize("mode", ["keepalive", "separate", "concurrent"])
def test_dast_preflight_current_egress_has_no_http_ceiling(managed_lab, mode):
    _settings, root, _requests, _sessions, probe = managed_lab
    received = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            with lock:
                received.append(self.client_address[1])
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(root / "cert.pem", root / "key.pem")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    policy = replace(
        probe, origin=f"https://192.0.2.1:{server.server_port}", request_budget=1
    )
    script = root / "dast-ceiling.py"
    script.write_text("""import concurrent.futures,http.client,json,socket,ssl,sys
port=int(sys.argv[1]);mode=sys.argv[2]
context=ssl.create_default_context(cafile='/cert.pem')
def connection():
 return http.client.HTTPSConnection('192.0.2.1',port,context=context,timeout=1)
def request(client):
 client.request('GET','/');response=client.getresponse();response.read()
 assert response.status==200
def independent():
 client=connection()
 try:request(client)
 finally:client.close()
if mode=='keepalive':
 client=connection()
 try:
  request(client);original=client.sock;request(client)
  assert client.sock is original
 finally:client.close()
elif mode=='concurrent':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  list(pool.map(lambda _:independent(),range(2)))
else:
 independent();independent()
with socket.create_connection(('192.0.2.1',port),timeout=1) as raw:
 try:context.wrap_socket(raw,server_hostname='wrong.test')
 except ssl.SSLCertVerificationError:pass
 else:raise AssertionError('hostname_mismatch_accepted')
with socket.create_connection(('192.0.2.1',port),timeout=1) as raw:
 try:ssl.create_default_context().wrap_socket(raw,server_hostname='192.0.2.1')
 except ssl.SSLCertVerificationError:pass
 else:raise AssertionError('untrusted_certificate_accepted')
print(json.dumps({'mode':mode,'client_completed':2,'tls_negative_checks':2}))
""")

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    session = egress.ManagedEgress(
        policy, artifacts=Artifacts(), assessment_run_id="dast-preflight", seconds=10
    )
    try:
        session.start()
        before = session.inspect("/usr/sbin/nft", "-j", "list", "ruleset")
        output = session.inspect(
            "/usr/bin/bwrap",
            "--unshare-all",
            "--unshare-user",
            "--share-net",
            "--disable-userns",
            "--cap-drop",
            "ALL",
            "--uid",
            "0",
            "--gid",
            "0",
            "--die-with-parent",
            "--new-session",
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
            "--ro-bind",
            str(script),
            "/client.py",
            "--ro-bind",
            str(root / "cert.pem"),
            "/cert.pem",
            "--",
            "/usr/bin/python3",
            "-I",
            "/client.py",
            str(policy.port),
            mode,
        )
        assert json.loads(output)["client_completed"] == 2
        session.validate(policy)
        assert before == session.inspect("/usr/sbin/nft", "-j", "list", "ruleset")
        assert len(received) == 2 > policy.request_budget
        assert len(set(received)) == (1 if mode == "keepalive" else 2)
        print(
            json.dumps(
                {
                    "verdict": "NO-GO",
                    "mode": mode,
                    "declared_budget": 1,
                    "target_requests": len(received),
                    "connections": len(set(received)),
                    "firewall_unchanged": True,
                }
            )
        )
    finally:
        try:
            session.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    assert not thread.is_alive()
    assert session.evidence["cleanup_verified"]
    assert session.supervisor is not None and session.supervisor.poll() is not None
    assert session.helper is not None and session.helper.poll() is not None
    assert session.temporary is not None and not Path(session.temporary.name).exists()
    assert egress._active.get() is None


@pytest.fixture
def dast_mediator(managed_lab):
    from beeagent_module.integrations.beescan.dast_mediation import DastMediation

    _settings, root, requests, _sessions, probe = managed_lab
    downstream = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    downstream.load_cert_chain(root / "cert.pem", root / "key.pem")
    upstream = ssl.create_default_context(cafile=str(root / "cert.pem"))
    endpoint = root / "mediator.sock"
    mediator = DastMediation(
        origin=probe.origin,
        connected_ip="127.0.0.1",
        request_budget=1,
        seconds=10,
        response_bytes=65536,
        socket_path=endpoint,
        downstream_tls=downstream,
        upstream_tls=upstream,
        authorize=lambda: None,
        resolve=lambda origin: {"127.0.0.1"},
    )
    mediator.start()
    try:
        yield mediator, root, requests, probe
    finally:
        mediator.close()


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
@pytest.mark.parametrize("mode", ["keepalive", "separate", "concurrent"])
def test_dast_mediated_hard_ceiling_without_scanner_egress(dast_mediator, mode):
    from beeagent_module.integrations.beescan.http_runner import bounded_process

    mediator, root, requests, probe = dast_mediator
    endpoint = mediator.socket_path
    script = root / "mediated-client.py"
    script.write_text("""import concurrent.futures,http.client,json,socket,ssl,sys
port=int(sys.argv[1]);mode=sys.argv[2]
def connect():
 raw=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);raw.settimeout(2);raw.connect('/gate.sock')
 raw.sendall(('CONNECT 192.0.2.1:'+str(port)+' HTTP/1.1\\r\\nHost: 192.0.2.1:'+str(port)+'\\r\\n\\r\\n').encode())
 data=b''
 while not data.endswith(b'\\r\\n\\r\\n'):data+=raw.recv(1)
 assert data.startswith(b'HTTP/1.1 200')
 return ssl.create_default_context(cafile='/cert.pem').wrap_socket(raw,server_hostname='192.0.2.1')
def request(stream):
 stream.sendall(('GET / HTTP/1.1\\r\\nHost: 192.0.2.1:'+str(port)+'\\r\\n\\r\\n').encode())
 response=http.client.HTTPResponse(stream);response.begin();response.read();return response.status
def independent():
 with connect() as stream:return request(stream)
if mode=='keepalive':
 with connect() as stream:statuses=[request(stream),request(stream)]
elif mode=='concurrent':
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(lambda _:independent(),range(2)))
else:statuses=[independent(),independent()]
assert sorted(statuses)==[200,403],statuses
for family,address in ((socket.AF_INET,'127.0.0.1'),(socket.AF_INET,'192.0.2.1'),(socket.AF_INET6,'::1')):
 with socket.socket(family) as connection:
  connection.settimeout(.1)
  assert connection.connect_ex((address,port))!=0
print(json.dumps({'statuses':statuses,'direct_connections_denied':3}))
""")
    try:
        code, output = bounded_process(
            [
                "/usr/bin/bwrap",
                "--unshare-all",
                "--unshare-user",
                "--disable-userns",
                "--cap-drop",
                "ALL",
                "--uid",
                "0",
                "--gid",
                "0",
                "--die-with-parent",
                "--new-session",
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
                "--ro-bind",
                str(script),
                "/client.py",
                "--ro-bind",
                str(root / "cert.pem"),
                "/cert.pem",
                "--ro-bind",
                str(endpoint),
                "/gate.sock",
                "--",
                "/usr/bin/python3",
                "-I",
                "/client.py",
                str(probe.port),
                mode,
            ],
            seconds=8,
            limit=8192,
            memory_mb=256,
            capture_stderr=True,
        )
        assert code == 0, output.decode()
        assert json.loads(output)["direct_connections_denied"] == 3
        assert requests == [("GET", "/")]
        assert mediator.reserved == mediator.completed == 1
        assert not mediator.failed
        print(json.dumps({"mode": mode, "target_requests": len(requests), "cap": 1}))
    finally:
        mediator.close()
    assert not endpoint.exists()


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
@pytest.mark.parametrize(
    "attack",
    [
        "connect",
        "host",
        "absolute",
        "chunked",
        "body",
        "upgrade",
        "method",
        "dns",
        "revoked",
        "tls",
        "deadline",
        "duplicate",
        "target",
    ],
)
def test_dast_mediation_fail_closed_before_target_http(dast_mediator, attack):
    mediator, root, requests, probe = dast_mediator
    authority = f"192.0.2.1:{probe.port}"
    if attack == "target":
        mediator.allowed_targets = ("/selected?file=one",)
    if attack == "dns":
        mediator.resolve = lambda origin: {"127.0.0.2"}
    if attack == "revoked":

        def refuse():
            raise PermissionError("revoked")

        mediator.authorize = refuse
    if attack == "tls":
        mediator.upstream_tls = ssl.create_default_context()
    raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    raw.settimeout(2)
    raw.connect(str(mediator.socket_path))
    stream = raw
    try:
        destination = "foreign.invalid:443" if attack == "connect" else authority
        raw.sendall(
            f"CONNECT {destination} HTTP/1.1\r\nHost: {destination}\r\n\r\n".encode()
        )
        response = bytearray()
        while not response.endswith(b"\r\n\r\n"):
            response.extend(raw.recv(1))
        if attack == "connect":
            assert response.startswith(b"HTTP/1.1 403")
        else:
            assert response.startswith(b"HTTP/1.1 200")
            stream = ssl.create_default_context(
                cafile=str(root / "cert.pem")
            ).wrap_socket(raw, server_hostname="192.0.2.1")
            if attack == "deadline":
                mediator.deadline = time.monotonic() - 1
            host = "foreign.invalid" if attack == "host" else authority
            method = "POST" if attack == "method" else "GET"
            target = "https://foreign.invalid/" if attack == "absolute" else "/"
            extra = {
                "chunked": "Transfer-Encoding: chunked\r\n",
                "body": "Content-Length: 1\r\n",
                "upgrade": "Upgrade: websocket\r\n",
                "duplicate": f"Host: {authority}\r\n",
            }.get(attack, "")
            stream.sendall(
                f"{method} {target} HTTP/1.1\r\nHost: {host}\r\n{extra}\r\n".encode()
            )
            try:
                result = stream.recv(1024)
            except ssl.SSLError, ConnectionError:
                result = b""
            assert not result or result.startswith(b"HTTP/1.1 403"), result
    finally:
        stream.close()
        raw.close()
        mediator.close()
    assert requests == []
    assert mediator.completed == 0
    assert not mediator.failed


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
def test_dast_mediation_binds_absolute_form_to_canonical_target(dast_mediator):
    import hashlib
    import http.client

    mediator, root, requests, probe = dast_mediator
    target = "/selected?file=one"
    mediator.allowed_targets = (target,)
    authority = f"192.0.2.1:{probe.port}"

    def request(value):
        raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        raw.settimeout(2)
        raw.connect(str(mediator.socket_path))
        stream = raw
        try:
            raw.sendall(
                f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode()
            )
            response = bytearray()
            while not response.endswith(b"\r\n\r\n"):
                response.extend(raw.recv(1))
            assert response.startswith(b"HTTP/1.1 200")
            stream = ssl.create_default_context(
                cafile=str(root / "cert.pem")
            ).wrap_socket(raw, server_hostname="192.0.2.1")
            stream.sendall(
                f"GET {value} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\n\r\n".encode()
            )
            response = http.client.HTTPResponse(stream)
            response.begin()
            return response.status, response.read()
        finally:
            stream.close()
            raw.close()

    status, body = request(probe.origin + target)
    assert status == 200
    assert requests == [("GET", target)]
    assert mediator.records == [
        {
            "request_sha256": hashlib.sha256(target.encode()).hexdigest(),
            "response_sha256": hashlib.sha256(body).hexdigest(),
            "status_code": 200,
        }
    ]
    status, body = request("https://foreign.invalid" + target)
    assert status == 403 and body == b""
    assert requests == [("GET", target)]
    assert mediator.completed == mediator.reserved == 1
    assert not mediator.failed


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
def test_dast_fixed_zap_headless_through_mediation(dast_mediator, zap_distribution):
    from beeagent_module.integrations.beescan.http_runner import bounded_process

    mediator, root, requests, probe = dast_mediator
    worker = (
        Path(__file__).resolve().parents[1]
        / "src/beeagent_module/integrations/beescan/dast_worker.py"
    )
    mediator.deadline = time.monotonic() + 60
    mediator.budget = 100
    hosts = root / "hosts"
    hosts.write_text("127.0.0.1 localhost\n")
    try:
        code, output = bounded_process(
            [
                "/usr/bin/bwrap",
                "--unshare-all",
                "--unshare-user",
                "--disable-userns",
                "--hostname",
                "localhost",
                "--cap-drop",
                "ALL",
                "--uid",
                "0",
                "--gid",
                "0",
                "--die-with-parent",
                "--new-session",
                "--clearenv",
                "--setenv",
                "HOME",
                "/tmp",
                "--ro-bind",
                "/usr",
                "/usr",
                "--ro-bind",
                "/lib",
                "/lib",
                "--ro-bind",
                "/lib64",
                "/lib64",
                "--ro-bind",
                "/etc/java-25-openjdk",
                "/etc/java-25-openjdk",
                "--ro-bind",
                str(hosts),
                "/etc/hosts",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
                "--ro-bind",
                str(worker),
                "/worker.py",
                "--ro-bind",
                str(zap_distribution),
                "/zap",
                "--ro-bind",
                str(mediator.socket_path),
                "/gate.sock",
                "--",
                "/usr/bin/python3",
                "-I",
                "/worker.py",
                json.dumps(
                    {
                        "origin": probe.origin,
                        "entries": ["/?file=fixture.txt"],
                        "seconds": 55,
                    }
                ),
            ],
            seconds=58,
            limit=8192,
            memory_mb=4096,
            capture_stderr=True,
            file_descriptors=256,
            file_bytes=16777216,
        )
        print(
            json.dumps(
                {
                    "code": code,
                    "target_requests": len(requests),
                    "reserved": mediator.reserved,
                    "denied": mediator.denied,
                    "worker": output.decode(),
                }
            )
        )
        assert code == 0, output.decode()
        result = json.loads(output)
        assert result["complete"] and result["rule_id"] == "6"
        assert result["alerts"] == []
        assert 1 <= len(requests) == mediator.completed <= 100
    finally:
        mediator.close()


@pytest.mark.parametrize(
    "managed_lab",
    ["dast-vulnerable", "dast-vulnerable-alt", "dast-fixed"],
    indirect=True,
)
def test_dast_real_managed_egress_and_paired_contract(
    managed_lab, monkeypatch, request
):
    from datetime import UTC, datetime, timedelta

    from beescan.capabilities.dast import (
        DastEvidence,
        DastExecution,
        DastIntent,
        DastStatus,
        ExecutionState,
        ScannerMatch,
        ScannerOutcome,
        normalize_dast,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    from beeagent_module.integrations.beescan.dast_runner import run_zap

    _settings, root, requests, sessions, probe = managed_lab

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    now = datetime.now(UTC)
    intent = DastIntent(
        Project("project", "Local assessment"),
        Target("target", "project", TargetKind.URL, probe.origin),
        EngagementScope(
            "scope",
            "project",
            ("target",),
            "approval",
            valid_from=now,
            expires_at=now + timedelta(minutes=5),
            approved_methods=("active_dast",),
            max_requests=100,
            max_seconds=60,
        ),
        Mission("mission", "project", "scope", ("web.dast",)),
        "parent",
        "child",
        "zap",
        "2.17.0",
        "rule6-v1",
        ("6",),
        ("check-1",),
        100,
        60,
        now,
    )
    raw, records, count = run_zap(
        probe,
        origin=probe.origin,
        entries=(
            (
                "/retrieve?document=fixture.txt"
                if request.node.callspec.params["managed_lab"] == "dast-vulnerable-alt"
                else "/?file=fixture.txt"
            ),
        ),
        archive=managed_zap_archive(),
        artifacts=Artifacts(),
        run_id="child",
        request_budget=100,
        seconds=55,
        authorize=lambda: None,
        upstream_tls=ssl.create_default_context(cafile=str(root / "cert.pem")),
    )
    assert raw["complete"]
    vulnerable = request.node.callspec.params["managed_lab"] in {
        "dast-vulnerable",
        "dast-vulnerable-alt",
    }
    assert bool(raw["alerts"]) is vulnerable
    assert len(requests) == count == len(records) > 0
    assert sessions[0].closed and sessions[0].evidence["cleanup_verified"]
    accepted = records[0]
    if vulnerable:
        alert = raw["alerts"][0]
        accepted = next(
            item
            for item in records
            if item["request_sha256"] == alert["request_sha256"]
            and item["response_sha256"] == alert["response_sha256"]
        )
    import hashlib

    evidence_path = root / "paired_evidence.json"
    evidence_path.write_text(json.dumps(records))
    evidence_path.chmod(0o600)
    evidence = DastEvidence(
        "ev-1",
        hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        accepted["request_sha256"],
        accepted["response_sha256"],
    )
    execution = DastExecution(
        intent.identity,
        "child",
        "zap",
        "2.17.0",
        "rule6-v1",
        ("6",),
        ExecutionState.COMPLETE,
        ("check-1",) if vulnerable else (),
        (evidence,),
        count,
        True,
        datetime.now(UTC),
    )
    outcome = ScannerOutcome(
        intent.identity,
        "child",
        "zap",
        "2.17.0",
        "rule6-v1",
        ("6",),
        (ScannerMatch("6", "check-1", evidence),) if vulnerable else (),
    )
    expected = DastStatus.CANDIDATE if vulnerable else DastStatus.PARTIAL
    assert normalize_dast(intent, execution, outcome).status is expected
    print(
        json.dumps(
            {
                "target": "vulnerable" if vulnerable else "fixed",
                "status": expected.value,
                "requests": count,
            }
        )
    )


@pytest.mark.parametrize(
    "managed_lab",
    ["dast-vulnerable", "dast-vulnerable-alt", "dast-fixed"],
    indirect=True,
)
def test_dast_operator_case_report_and_resume(
    managed_lab, monkeypatch, request, capsys
):
    from datetime import UTC, datetime, timedelta

    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.case_state import load_case
    from beeagent_module.integrations.beescan.local_cli import (
        _SEAL,
        _identity,
        _LocalOperator,
    )
    from beeagent_module.integrations.beescan.probe import handle_beescan_cli

    settings, root, requests, sessions, probe = managed_lab
    now = datetime.now(UTC)
    probe = replace(probe, valid_from=now, expires_at=now + timedelta(minutes=5))
    transport = asdict(probe)
    for key in ("valid_from", "expires_at"):
        transport[key] = transport[key].isoformat()
    settings["beescan"]["investigation"] = {
        "task_chars_max": 4000,
        "trusted_local_enabled": True,
    }
    approval = {
        "transport": transport,
        "approved": False,
        "method": "active_dast",
        "entries": [
            "/retrieve?document=fixture.txt"
            if request.node.callspec.params["managed_lab"] == "dast-vulnerable-alt"
            else "/?file=fixture.txt"
        ],
        "request_budget": 100,
        "seconds": 55,
        "archive": str(managed_zap_archive()),
    }
    settings["beescan"]["dast"] = {"enabled": True, "approval": approval}
    storage = root / "dast-storage"
    storage.mkdir(mode=0o700)
    options = {
        "settings": settings,
        "reload_settings": lambda: copy.deepcopy(settings),
        "storage_dir": storage,
        "logger": logging.getLogger("managed-lab"),
        "local_operator": _LocalOperator(_identity(), _SEAL),
    }
    args = ["investigate", "--target", probe.origin, "--task", "Assess Path Traversal"]
    assert handle_beescan_cli(args, **options) == 3
    assert requests == [] and sessions == []
    capsys.readouterr()
    approval["approved"] = True
    settings["beescan"]["investigation"]["trusted_local_enabled"] = False
    assert handle_beescan_cli(args, **options) == 3
    assert requests == [] and sessions == []
    capsys.readouterr()
    settings["beescan"]["investigation"]["trusted_local_enabled"] = True
    original = dast_runner.run_zap
    context = ssl.create_default_context(cafile=str(root / "cert.pem"))

    def run(transport, **kwargs):
        result = original(transport, **kwargs, upstream_tls=context)
        assert result[0]["host_complete"], result[0]["denial_reasons"]
        return result

    monkeypatch.setattr(dast_runner, "run_zap", run)
    vulnerable = request.node.callspec.params["managed_lab"] in {
        "dast-vulnerable",
        "dast-vulnerable-alt",
    }
    code = handle_beescan_cli(args, **options)
    captured = capsys.readouterr()
    assert code == (0 if vulnerable else 5), captured
    result = json.loads(captured.out)
    assert result["status"] == ("CANDIDATE" if vulnerable else "PARTIAL")
    state, snapshot = load_case(storage, result["case_id"])
    assert not state["pending"]
    assert state["status"] == result["status"]
    assert len(requests) == result["request_count"] <= 100
    assert sessions[0].closed and sessions[0].evidence["cleanup_verified"]
    report = snapshot.json(result["run_id"], "report.json")
    assert not any(
        word in json.dumps(report)
        for word in ("root:x", "fixture.txt", "Cookie", "passwd")
    )
    if vulnerable:
        before = len(requests)
        assert (
            handle_beescan_cli(
                [
                    "investigate",
                    "--resume",
                    result["case_id"],
                    "--task",
                    "Assess Path Traversal",
                ],
                **options,
            )
            == 0
        )
        assert len(requests) == before
        capsys.readouterr()
    before = len(requests)
    approval["request_budget"] = 99
    assert (
        handle_beescan_cli(
            [
                "investigate",
                "--resume",
                result["case_id"],
                "--task",
                "Assess Path Traversal",
            ],
            **options,
        )
        == 3
    )
    assert len(requests) == before
    capsys.readouterr()
    approval["request_budget"] = 100
    path = Path(result["report_location"])
    path.write_text("substituted")
    with pytest.raises(ValueError, match="dast_report_changed"):
        load_case(storage, result["case_id"])


@pytest.mark.parametrize(
    "managed_lab",
    [
        "dast-vulnerable",
        "dast-vulnerable-alt",
        "dast-fixed",
        "dast-nonrecursive",
        "dast-nonrecursive-alt",
        "dast-nonrecursive-fixed",
        "dast-nonrecursive-fixed-alt",
        "dast-nonrecursive-reflection",
        "dast-nonrecursive-ambiguous",
        "dast-nonrecursive-budget",
    ],
    indirect=True,
)
def test_dast_autonomous_discovery_to_zap(managed_lab, monkeypatch, request, capsys):
    from datetime import UTC, datetime, timedelta

    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.case_state import load_case
    from beeagent_module.integrations.beescan.local_cli import (
        _SEAL,
        _identity,
        _LocalOperator,
    )
    from beeagent_module.integrations.beescan.probe import handle_beescan_cli

    lab_settings, root, requests, sessions, probe = managed_lab
    settings = read_test_settings()
    settings["beescan"].update(lab_settings["beescan"])
    now = datetime.now(UTC)
    probe = replace(
        probe,
        valid_from=now,
        expires_at=now + timedelta(minutes=5),
        time_budget_seconds=60,
    )
    transport = asdict(probe)
    for key in ("valid_from", "expires_at"):
        transport[key] = transport[key].isoformat()
    settings["beescan"]["investigation"] = {
        "enabled": True,
        "approval": None,
        "local_lab_enabled": True,
        "trusted_local_enabled": True,
        "ai_profile": "openrouter",
        "task_bytes_max": 16384,
        "task_chars_max": 4000,
        "timeout_seconds": 60,
        "input_chars_max": 16000,
        "output_chars_max": 4000,
        "body_bytes_max": 73728,
        "adaptive": {
            "enabled": True,
            "max_steps": 4,
            "max_requests": 32,
            "max_depth": 2,
        },
    }
    settings["beescan"]["dast"] = {
        "enabled": True,
        "approval": {
            "transport": transport,
            "approved": True,
            "method": "active_dast",
            "entries": [],
            "entry_selection": "authenticated_discovery",
            "max_candidates": 1,
            "request_budget": 100,
            "seconds": 55,
        },
    }
    fixture = request.node.callspec.params["managed_lab"]
    nonrecursive = fixture.startswith("dast-nonrecursive")
    if nonrecursive:
        settings["beescan"]["dast"]["approval"]["profile"] = "traversal-nonrecursive-v1"
    if fixture == "dast-nonrecursive-budget":
        settings["beescan"]["dast"]["approval"]["request_budget"] = 3
    storage = root / "autonomous-dast-storage"
    storage.mkdir(mode=0o700)
    context = ssl.create_default_context(cafile=str(root / "cert.pem"))
    original = dast_runner.run_zap

    def run(transport, **kwargs):
        return original(transport, **kwargs, upstream_tls=context)

    monkeypatch.setattr(dast_runner, "run_zap", run)
    options = {
        "settings": settings,
        "reload_settings": lambda: copy.deepcopy(settings),
        "storage_dir": storage,
        "logger": logging.getLogger("managed-lab"),
        "local_operator": _LocalOperator(_identity(), _SEAL),
    }
    args = ["investigate", "--target", probe.origin, "--task", "Assess Path Traversal"]
    vulnerable = fixture in {
        "dast-vulnerable",
        "dast-vulnerable-alt",
        "dast-nonrecursive",
        "dast-nonrecursive-alt",
    }
    expected = (
        "CANDIDATE"
        if vulnerable
        else "NO_MATCH"
        if nonrecursive
        and fixture not in {"dast-nonrecursive-ambiguous", "dast-nonrecursive-budget"}
        else "PARTIAL"
    )
    code = handle_beescan_cli(args, **options)
    captured = capsys.readouterr()
    assert code == (0 if expected in {"CANDIDATE", "NO_MATCH"} else 5), captured
    result = json.loads(captured.out)
    assert result["status"] == expected
    assert requests[0] == ("GET", "/")
    state, snapshot = load_case(storage, result["case_id"])
    assert state["schema_version"] == 4 and not state["pending"]
    assert state["metrics"]["request_count"] == len(requests) <= 100
    assert sessions[0].closed and sessions[0].evidence["cleanup_verified"]
    report = snapshot.json(result["run_id"], "report.json")
    assert bool(report["findings"]) is vulnerable
    if nonrecursive:
        from beeagent_module.integrations.beescan.dast_worker import (
            verification_targets,
        )

        entry = (
            "/retrieve?document=fixture.txt"
            if fixture.endswith("-alt")
            else "/?file=fixture.txt"
        )
        limit = 3 if fixture == "dast-nonrecursive-budget" else 5
        assert requests[1:] == [
            ("GET", target) for target in verification_targets(entry)[:limit]
        ]
        active = state["assessment"]
        evidence = snapshot.json(active["run_id"], "dast_evidence.json")
        assert len(evidence["verification"]) == limit
        assert evidence["verification"][2]["oracle"] is vulnerable or fixture in {
            "dast-nonrecursive-ambiguous",
            "dast-nonrecursive-budget",
        }
        assert active["action"]["profile"] == "traversal-nonrecursive-v1"
    for path in storage.rglob("*"):
        if path.is_file():
            assert "fixture.txt" not in path.read_text()
    before = len(requests)
    assert handle_beescan_cli(
        [
            "investigate",
            "--resume",
            result["case_id"],
            "--task",
            "Assess Path Traversal",
        ],
        **options,
    ) == (0 if expected in {"CANDIDATE", "NO_MATCH"} else 5)
    assert len(requests) == before
    capsys.readouterr()
    assert (
        handle_beescan_cli(["investigate", "--inspect", result["case_id"]], **options)
        == 0
    )
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["schema_version"] == 4
    if nonrecursive:
        resume_input = root / "resume_input.json"
        resume_input.write_text(
            json.dumps(
                {
                    "settings": settings,
                    "storage": str(storage),
                    "case": result["case_id"],
                }
            )
        )
        resume_input.chmod(0o600)
        script = """import copy,json,logging,sys
from pathlib import Path
from beeagent_module.integrations.beescan.local_cli import _LocalOperator,_identity,_SEAL
from beeagent_module.integrations.beescan.probe import handle_beescan_cli
v=json.loads(Path(sys.argv[1]).read_text())
sys.exit(handle_beescan_cli(['investigate','--resume',v['case'],'--task','Assess Path Traversal'],settings=v['settings'],reload_settings=lambda:copy.deepcopy(v['settings']),storage_dir=Path(v['storage']),logger=logging.getLogger('resume'),local_operator=_LocalOperator(_identity(),_SEAL)))
"""
        resumed = subprocess.run(
            [sys.executable, "-c", script, str(resume_input)],
            capture_output=True,
            timeout=15,
        )
        assert resumed.returncode == (
            0 if expected in {"CANDIDATE", "NO_MATCH"} else 5
        ), resumed.stderr.decode()
        assert json.loads(resumed.stdout)["reason"] == "authenticated_case_reused"
        assert len(requests) == before
        from beeagent_module.integrations.beescan.case_state import digest

        case_path = storage / "runs" / result["case_id"] / "module-beescan/case.json"
        original_case = case_path.read_bytes()
        for field in ("profile", "scope_id", "mission_id", "case_id"):
            envelope = json.loads(original_case)
            envelope["state"]["assessment"]["action"][field] = "foreign"
            envelope["sha256"] = digest(envelope["state"])
            case_path.write_text(json.dumps(envelope))
            with pytest.raises(ValueError):
                load_case(storage, result["case_id"])
        case_path.write_bytes(original_case)
        evidence_path = (
            storage
            / "runs"
            / state["assessment"]["run_id"]
            / "module-beescan/dast_evidence.json"
        )
        original_evidence = evidence_path.read_bytes()
        altered = json.loads(original_evidence)
        altered["verification"][0]["oracle"] = not altered["verification"][0]["oracle"]
        evidence_path.write_text(json.dumps(altered))
        with pytest.raises(ValueError):
            load_case(storage, result["case_id"])
        evidence_path.write_bytes(original_evidence)
        active_approval = settings["beescan"]["dast"]["approval"]
        active_approval["profile"] = "rule6-v1"
        assert (
            handle_beescan_cli(
                [
                    "investigate",
                    "--resume",
                    result["case_id"],
                    "--task",
                    "Assess Path Traversal",
                ],
                **options,
            )
            == 3
        )
        capsys.readouterr()
        active_approval["profile"] = "traversal-nonrecursive-v1"
        assert len(requests) == before


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
@pytest.mark.parametrize("fault", ["crash", "timeout", "cancel", "forged", "malformed"])
@pytest.mark.parametrize("profile", ["rule6-v1", "traversal-nonrecursive-v1"])
def test_dast_managed_failure_cleanup(managed_lab, monkeypatch, fault, profile):
    from beeagent_module.integrations.beescan import dast_runner, http_runner

    _settings, root, requests, sessions, probe = managed_lab
    original = dast_runner.bounded_process
    selector_type = http_runner.selectors.DefaultSelector

    class InterruptedSelector(selector_type):
        def select(self, timeout=None):
            raise KeyboardInterrupt

    def process(argv, **kwargs):
        if "/worker.py" not in argv:
            return original(argv, **kwargs)
        prefix = argv[: argv.index("--") + 1]
        program = (
            "import os;os._exit(7)"
            if fault == "crash"
            else "import time;time.sleep(30)"
        )
        if fault == "forged":
            program = 'import json;print(json.dumps({"complete":True,"rule_id":"6","alerts":[{"rule_id":"6","request_sha256":"a"*64,"response_sha256":"b"*64}],"entries":1}))'
        if fault == "malformed":
            program = 'print("malformed")'
        command = [*prefix, "/usr/bin/python3", "-I", "-c", program]
        kwargs["seconds"] = 1
        if fault == "cancel":
            with monkeypatch.context() as scoped:
                scoped.setattr(
                    http_runner.selectors, "DefaultSelector", InterruptedSelector
                )
                return original(command, **kwargs)
        return original(command, **kwargs)

    monkeypatch.setattr(dast_runner, "bounded_process", process)

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    expected = {
        "crash": ValueError,
        "timeout": TimeoutError,
        "cancel": KeyboardInterrupt,
        "forged": ValueError,
        "malformed": ValueError,
    }[fault]
    with pytest.raises(expected):
        dast_runner.run_zap(
            probe,
            origin=probe.origin,
            entries=("/",) if profile == "rule6-v1" else ("/?file=fixture.txt",),
            archive=managed_zap_archive(),
            artifacts=Artifacts(),
            run_id="failure-test",
            request_budget=1,
            seconds=15,
            authorize=lambda: None,
            upstream_tls=ssl.create_default_context(cafile=str(root / "cert.pem")),
            **({"profile": profile} if profile != "rule6-v1" else {}),
        )
    assert requests == []
    assert sessions[0].closed and sessions[0].evidence["cleanup_verified"]
    status = json.loads((root / "dast_execution_status.json").read_text())
    assert status["request_count"] == 0 and status["cleanup_verified"]
    diagnostic = status["worker_diagnostic"]
    assert diagnostic["phase"] == "worker"
    assert (diagnostic["exit_code"] is None) is (fault in {"timeout", "cancel"})
    assert diagnostic["signal"] is None
    assert diagnostic["mediator_failed"] is False
    assert diagnostic["reason_code"] in {
        "execution_incomplete",
        "zap_invalid_result",
        "zap_unauthenticated_alert",
        "zap_worker_failed",
    }
    if profile != "rule6-v1":
        return
    from beeagent_module.integrations.beescan.case_state import load_case
    from beeagent_module.integrations.beescan.dast import execute_dast_investigation
    from beeagent_module.integrations.beescan.investigation import InvestigationTask
    from beeagent_module.integrations.beescan.local_cli import (
        _SEAL,
        _identity,
        _LocalOperator,
    )

    transport = asdict(probe)
    for key in ("valid_from", "expires_at"):
        transport[key] = transport[key].isoformat()
    _settings["beescan"]["dast"] = {
        "enabled": True,
        "approval": {
            "transport": transport,
            "approved": True,
            "method": "active_dast",
            "entries": ["/"],
            "request_budget": 1,
            "seconds": 15,
            "archive": str(managed_zap_archive()),
        },
    }
    storage = root / "failed-case"
    storage.mkdir(mode=0o700)
    _settings["beescan"]["investigation"] = {"trusted_local_enabled": True}
    result = execute_dast_investigation(
        task=InvestigationTask(probe.origin, "Assess Path Traversal"),
        settings=_settings,
        reload_settings=lambda: copy.deepcopy(_settings),
        storage_dir=storage,
        logger=logging.getLogger("managed-lab"),
        local_operator=_LocalOperator(_identity(), _SEAL),
    )
    assert not result["complete"]
    assert result["status"] == (
        "PARTIAL" if fault in {"timeout", "cancel"} else "ERROR"
    )
    case, _snapshot = load_case(storage, result["case_id"])
    assert case["pending"] is False
    assert not requests


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
def test_dast_response_body_oserror_preserves_safe_phase_diagnostic(
    managed_lab, monkeypatch
):
    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.dast_mediation import DastMediation

    _settings, root, requests, sessions, probe = managed_lab
    original = DastMediation.event

    def interrupted(self, protocol, connection, *, read_size=1):
        if self.failure_diagnostic["phase"] == "response_body":
            raise OSError("private transport failure")
        return original(self, protocol, connection, read_size=read_size)

    monkeypatch.setattr(DastMediation, "event", interrupted)

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    with pytest.raises(ValueError, match="zap_execution_incomplete"):
        dast_runner.run_zap(
            probe,
            origin=probe.origin,
            entries=("/?file=fixture.txt",),
            archive=managed_zap_archive(),
            artifacts=Artifacts(),
            run_id="response-body-oserror",
            request_budget=10,
            seconds=55,
            authorize=lambda: None,
            upstream_tls=ssl.create_default_context(cafile=str(root / "cert.pem")),
            profile="traversal-nonrecursive-v1",
        )
    status = json.loads((root / "dast_execution_status.json").read_text())
    assert status["request_count"] == 1
    assert status["completed_count"] == 0
    assert status["denial_reasons"].get("OSError", 0) >= 1
    assert status["mediator_diagnostic"] == {
        "phase": "response_body",
        "exception_category": "OSError",
    }
    assert status["cleanup_verified"]
    assert len(requests) == 1
    assert sessions[0].closed and sessions[0].evidence["cleanup_verified"]


@pytest.mark.parametrize("managed_lab", [True], indirect=True)
def test_dast_managed_cleanup_failure_never_completes(managed_lab, monkeypatch):
    from beeagent_module.integrations.beescan import dast_runner
    from beeagent_module.integrations.beescan.dast_mediation import DastMediation

    _, root, requests, sessions, probe = managed_lab
    close = DastMediation.close

    def failed_close(self):
        close(self)
        raise RuntimeError("dast_cleanup_unverified")

    monkeypatch.setattr(DastMediation, "close", failed_close)

    class Artifacts:
        def write_json(self, name, data):
            path = root / name
            path.write_text(json.dumps(data))
            return path

    with pytest.raises(RuntimeError, match="dast_cleanup_unverified"):
        dast_runner.run_zap(
            probe,
            origin=probe.origin,
            entries=("/read?file=one",),
            archive=managed_zap_archive(),
            artifacts=Artifacts(),
            run_id="cleanup-failure",
            request_budget=10,
            seconds=55,
            authorize=lambda: None,
            upstream_tls=ssl.create_default_context(cafile=str(root / "cert.pem")),
            profile="traversal-nonrecursive-v1",
        )
    assert len(requests) == 5
    assert sessions[0].closed and sessions[0].evidence["cleanup_verified"]
    assert sessions[0].helper.poll() is not None
    assert sessions[0].supervisor.poll() is not None
    status = json.loads((root / "dast_execution_status.json").read_text())
    assert status["cleanup_verified"] is False
    assert status["reason"] == "cleanup_unverified"
