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
from beeagent_module.integrations.beescan.git_exposure import GitExposurePolicy
from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
from tests import test_beescan_detection
from tests.settings_support import read_test_settings
from tests.test_beescan_detection import settings_for

approved = test_beescan_detection.approved


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
    for name in (
        "BEEAGENT_BEESCAN_PASTA",
        "BEEAGENT_BEESCAN_LAB_PROVIDER",
        "BEEAGENT_BEESCAN_NUCLEI",
    ):
        if not os.environ.get(name):
            pytest.fail(
                f"Explicit pinned laboratory prerequisite required: {name}",
                pytrace=False,
            )
    binary = root / "providers/pasta"
    binary.parent.mkdir(mode=0o700)
    binary.write_bytes(egress._binary(Path(os.environ["BEEAGENT_BEESCAN_PASTA"])))
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

    class Handler(BaseHTTPRequestHandler):
        def respond(self):
            requests.append((self.command, self.path))
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
            executable=os.environ["BEEAGENT_BEESCAN_NUCLEI"],
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
            executable=os.environ["BEEAGENT_BEESCAN_LAB_PROVIDER"],
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
