import array
import hashlib
import json
import os
import selectors
import signal
import socket
import ssl
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from beeagent_module.integrations.beescan import egress
from beeagent_module.integrations.beescan.dast_mediation import DastMediation
from beeagent_module.integrations.beescan.detection_runner import read_regular
from beeagent_module.integrations.beescan.http_runner import (
    bounded_process,
    verify_resolution,
)

CORE_BYTES = 108340737
CORE_SHA256 = "0cb73b7f72d12c263fb61de304edb82a455d7aa4e1813c216c061765c306f5b7"
ADDONS = {
    "ascanrules-release-78.zap": "764a9f803304b6aa266d13f4c39f23b013e206c9e831435cd405871919a021fe",
    "commonlib-release-1.39.0.zap": "477af158c562770951abedefb5bb988fda935ef253a80616c3e298174fc58fb0",
    "network-beta-0.25.0.zap": "bf32c4d2c40c76171efa29da1987375a312cc09595ece29d67018e7ae54d6cf3",
    "database-alpha-0.9.0.zap": "4c58ca142288d9ddc6ae3fd8fe6815e3894462bae67eb0776e540a2d9ddaf87d",
    "oast-beta-0.24.0.zap": "f06ecea02e2c1df4a164e737dd632afba4430225b2fdc2feb6042bdb1e976b3d",
    "callhome-release-0.20.0.zap": "a9e499dfa9f2fc85992faba66ab90db48d46b47e4241dc60106c78094412a679",
    "pscan-alpha-0.6.0.zap": "269ff66f0d8a8012f156e90e13238606a8d503b99521170649b62c9aa7295927",
}


def snapshot_zap(archive, directory):
    data = read_regular(archive, limit=CORE_BYTES)
    if len(data) != CORE_BYTES or hashlib.sha256(data).hexdigest() != CORE_SHA256:
        raise PermissionError("zap_distribution_integrity")
    snapshot = directory / "core.zip"
    snapshot.write_bytes(data)
    root = directory / "zap"
    root.mkdir(mode=0o700)
    with zipfile.ZipFile(snapshot) as bundle:
        entries = bundle.infolist()
        if (
            len(entries) > 4096
            or sum(item.file_size for item in entries) > 300 * 1024 * 1024
        ):
            raise ValueError("zap_distribution_bounds")
        seen = set()
        for entry in entries:
            path = Path(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != "ZAP_2.17.0"
                or entry.filename in seen
                or stat.S_IFMT(entry.external_attr >> 16)
                not in {0, stat.S_IFREG, stat.S_IFDIR}
            ):
                raise ValueError("zap_distribution_entry")
            seen.add(entry.filename)
            relative = Path(*path.parts[1:])
            if (
                entry.is_dir()
                or relative.parts[:1] == ("plugin",)
                and relative.name not in ADDONS
            ):
                continue
            target = root / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            content = bundle.read(entry)
            if (
                relative.parts[:1] == ("plugin",)
                and hashlib.sha256(content).hexdigest() != ADDONS[relative.name]
            ):
                raise PermissionError("zap_addon_integrity")
            target.write_bytes(content)
            target.chmod(0o600)
    if {path.name for path in (root / "plugin").iterdir()} != set(ADDONS):
        raise PermissionError("zap_addon_missing")
    return root


def _sandbox(directory):
    return [
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
        "--setenv",
        "HOME",
        "/tmp",
        "--hostname",
        "localhost",
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
        str(directory / "hosts"),
        "/etc/hosts",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        "134217728",
        "--tmpfs",
        "/tmp",
    ]


def run_zap(
    transport,
    *,
    origin,
    entries,
    archive,
    artifacts,
    run_id,
    request_budget,
    seconds,
    authorize,
    upstream_tls=None,
):
    if (
        origin != transport.origin
        or type(request_budget) is not int
        or not 1 <= request_budget <= 100
        or type(seconds) is not int
        or not 10 <= seconds <= 60
        or not origin.startswith("https://")
        or type(entries) is not tuple
        or not 1 <= len(entries) <= 8
        or any(
            type(entry) is not str or not entry.startswith("/") or len(entry) > 512
            for entry in entries
        )
    ):
        raise ValueError("invalid_zap_request")
    authorize()
    verify_resolution(transport)
    session = egress.ManagedEgress(
        transport, artifacts=artifacts, assessment_run_id=run_id, seconds=seconds
    )
    broker = mediator = None
    code = None
    failure = "execution_incomplete"
    with tempfile.TemporaryDirectory(prefix="bee-zap-") as temporary:
        directory = Path(temporary)
        root = snapshot_zap(archive, directory)
        (directory / "hosts").write_text("127.0.0.1 localhost\n", encoding="ascii")
        host = urlsplit(origin).hostname
        try:
            import ipaddress

            ipaddress.ip_address(host)
            san = "IP:" + host
        except ValueError:
            san = "DNS:" + host
        code, _raw = bounded_process(
            [
                "/usr/bin/openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(directory / "key.pem"),
                "-out",
                str(directory / "cert.pem"),
                "-days",
                "1",
                "-subj",
                "/CN=BeeAgent-DAST",
                "-addext",
                "subjectAltName=" + san,
            ],
            seconds=5,
            limit=8192,
            memory_mb=256,
        )
        if code:
            raise PermissionError("dast_certificate_failed")
        downstream = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        downstream.load_cert_chain(directory / "cert.pem", directory / "key.pem")
        try:
            session.start()
            authorize()
            if session.supervisor is None:
                raise PermissionError("dast_namespace_unavailable")
            broker_dir = directory / "broker"
            broker_dir.mkdir(mode=0o700)
            connector = Path(__file__).with_name("dast_socket_worker.py")
            sandbox = _sandbox(directory)
            sandbox.insert(2, "--share-net")
            command = [
                "/usr/bin/nsenter",
                "--preserve-credentials",
                f"--user=/proc/{session.supervisor.pid}/ns/user",
                f"--net=/proc/{session.supervisor.pid}/ns/net",
                "--",
                *sandbox,
                "--bind",
                str(broker_dir),
                "/broker",
                "--ro-bind",
                str(connector),
                "/connector.py",
                "--",
                "/usr/bin/python3",
                "-I",
                "/connector.py",
                json.dumps(
                    {
                        "connected_ip": transport.connected_ip,
                        "port": transport.port,
                        "seconds": seconds,
                        "requests": request_budget,
                    }
                ),
            ]
            broker = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "LANG": "C"},
                start_new_session=True,
            )
            if broker.stdout is None:
                raise PermissionError("dast_connector_unavailable")
            with selectors.DefaultSelector() as selector:
                selector.register(broker.stdout, selectors.EVENT_READ)
                if not selector.select(3) or broker.stdout.readline(32) != b"ready\n":
                    raise PermissionError("dast_connector_unavailable")

            def connect():
                authorize()
                session.validate(transport)
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as control:
                    control.settimeout(3)
                    control.connect(str(broker_dir / "open.sock"))
                    data, ancillary, flags, _address = control.recvmsg(
                        1,
                        socket.CMSG_SPACE(array.array("i").itemsize),
                        socket.MSG_CMSG_CLOEXEC,
                    )
                received = []
                for level, kind, value in ancillary:
                    if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                        descriptors = array.array("i")
                        descriptors.frombytes(value)
                        received.extend(descriptors)
                if (
                    data != b"1"
                    or flags & ~socket.MSG_CMSG_CLOEXEC
                    or len(received) != 1
                ):
                    for descriptor in received:
                        os.close(descriptor)
                    raise PermissionError("dast_connection_refused")
                connection = socket.socket(fileno=received[0])
                if connection.getpeername()[:2] != (
                    transport.connected_ip,
                    transport.port,
                ):
                    connection.close()
                    raise PermissionError("dast_connection_mismatch")
                return connection

            mediator = DastMediation(
                origin=origin,
                connected_ip=transport.connected_ip,
                request_budget=request_budget,
                seconds=seconds,
                response_bytes=262144,
                socket_path=directory / "gate.sock",
                downstream_tls=downstream,
                upstream_tls=upstream_tls or ssl.create_default_context(),
                authorize=authorize,
                resolve=lambda value: (
                    {transport.connected_ip}
                    if verify_resolution(transport) is None
                    else set()
                ),
                connect=connect,
            )
            mediator.start()
            worker = Path(__file__).with_name("dast_worker.py")
            code, output = bounded_process(
                [
                    *_sandbox(directory),
                    "--ro-bind",
                    str(root),
                    "/zap",
                    "--ro-bind",
                    str(worker),
                    "/worker.py",
                    "--ro-bind",
                    str(mediator.socket_path),
                    "/gate.sock",
                    "--",
                    "/usr/bin/python3",
                    "-I",
                    "/worker.py",
                    json.dumps(
                        {"origin": origin, "entries": entries, "seconds": seconds - 2}
                    ),
                ],
                seconds=seconds,
                limit=16384,
                memory_mb=4096,
                file_descriptors=256,
                file_bytes=16777216,
                capture_stderr=False,
            )
            if code or mediator.failed:
                try:
                    diagnostic = json.loads(output)
                    if type(diagnostic) is dict and diagnostic.get("failure") in {
                        "zap_api_ascan_scan_400",
                        "zap_api_core_accessUrl_400",
                        "zap_api_core_accessUrl_500",
                        "zap_api_rejected",
                        "zap_start_failed",
                        "zap_unapproved_rule",
                        "zap_worker_failed",
                        "zap_api_pscan_disableAllScanners_400",
                        "zap_version",
                        "zap_rule_policy",
                        "zap_api_limit",
                        "zap_scan_incomplete",
                        "zap_alert_limit",
                    }:
                        failure = diagnostic["failure"]
                except ValueError:
                    pass
                raise ValueError("zap_execution_incomplete")
            result = json.loads(output)
            if (
                type(result) is not dict
                or set(result) != {"complete", "rule_id", "alerts", "entries"}
                or result["complete"] is not True
                or result["rule_id"] != "6"
                or type(result["entries"]) is not int
                or result["entries"] != len(entries)
                or type(result["alerts"]) is not list
                or len(result["alerts"]) > 32
            ):
                raise ValueError("zap_invalid_result")
            seen = set()
            for alert in result["alerts"]:
                if (
                    type(alert) is not dict
                    or set(alert)
                    != {"rule_id", "target", "request_sha256", "response_sha256"}
                    or alert["rule_id"] != "6"
                    or type(alert["target"]) is not str
                    or not alert["target"].startswith("/")
                    or alert["target"].startswith("//")
                    or len(alert["target"]) > 4096
                    or any(
                        ord(value) < 33 or ord(value) > 126 for value in alert["target"]
                    )
                    or hashlib.sha256(alert["target"].encode("ascii")).hexdigest()
                    != alert["request_sha256"]
                    or not any(
                        alert["request_sha256"] == record["request_sha256"]
                        and alert["response_sha256"] == record["response_sha256"]
                        for record in mediator.records
                    )
                ):
                    raise ValueError("zap_unauthenticated_alert")
                identity = (alert["request_sha256"], alert["response_sha256"])
                if identity in seen:
                    raise ValueError("zap_duplicate_alert")
                seen.add(identity)
            result["host_complete"] = (
                mediator.denied == 0 and mediator.completed == mediator.reserved
            )
            result["denial_reasons"] = dict(mediator.denial_reasons)
            authorize()
            failure = "ok"
            return result, tuple(mediator.records), mediator.reserved
        except (ValueError, PermissionError) as error:
            if str(error) in {
                "zap_invalid_result",
                "zap_unauthenticated_alert",
                "zap_duplicate_alert",
            }:
                failure = str(error)
            raise
        finally:
            if mediator is not None:
                mediator.close()
            try:
                if broker is not None:
                    try:
                        os.killpg(broker.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    broker.wait(timeout=2)
                    if broker.stdout is not None:
                        broker.stdout.close()
            finally:
                session.close()
                from beeagent_module.integrations.beescan.detection import _persist

                _persist(
                    artifacts,
                    "dast_execution_status.json",
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "exit_code": code,
                        "reason": failure,
                        "request_count": mediator.reserved if mediator else 0,
                        "completed_count": mediator.completed if mediator else 0,
                        "denial_reasons": dict(mediator.denial_reasons)
                        if mediator
                        else {},
                        "cleanup_verified": session.closed
                        and session.evidence.get("cleanup_verified") is True,
                    },
                )
