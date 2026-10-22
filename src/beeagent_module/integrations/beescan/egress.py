import hashlib
import io
import json
import os
import platform
import selectors
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from contextvars import ContextVar
from pathlib import Path

MANAGED_NET = "/beeagent-managed/ns/net"
MANAGED_USER = "/beeagent-managed/ns/user"
PASTA_VERSION = "0.0~git20260120.386b5f5-1"
PASTA_SHA256 = "a10789852407f65160c4abfac002efe511b254e6ab2cbfc658e807575db44832"
PACKAGE_SHA256 = "49eaf773c120432bdf439d26d3de4d9867116580a819e6eba815b600c45b9840"
EGRESS_REASONS = frozenset(
    {
        "egress_platform_unavailable",
        "egress_prerequisite_unavailable",
        "egress_helper_integrity",
        "egress_setup_unverified",
        "egress_unverified",
        "egress_session_unavailable",
        "egress_namespace_changed",
        "egress_binding_changed",
        "egress_routes_changed",
        "egress_cleanup_unverified",
    }
)
_active = ContextVar["ManagedEgress | None"]("beescan_managed_egress", default=None)


def namespace_pair(network, user):
    import re

    if (network, user) == (MANAGED_NET, MANAGED_USER):
        return True
    if type(network) is not str or type(user) is not str:
        return False
    match = re.fullmatch(r"/proc/([1-9][0-9]{0,9})/ns/net", network)
    return match is not None and user == f"/proc/{match[1]}/ns/user"


def executable_path():
    from beeagent_module.integrations.beescan.providers import provider_root

    return provider_root() / "pasta"


def _binary(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid not in {0, os.getuid()}
            or info.st_mode & 0o022
            or not info.st_mode & 0o111
            or info.st_size != 277704
        ):
            raise PermissionError("egress_helper_integrity")
        data = stream.read(277705)
    if hashlib.sha256(data).hexdigest() != PASTA_SHA256:
        raise PermissionError("egress_helper_integrity")
    return data


def provision(package):
    from beeagent_module.integrations.beescan.providers import _secure_root

    descriptor = os.open(package, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != 259676:
            raise PermissionError("egress_package_integrity")
        data = stream.read(259677)
    if hashlib.sha256(data).hexdigest() != PACKAGE_SHA256:
        raise PermissionError("egress_package_integrity")
    root = executable_path().parent
    _secure_root(root)
    with tempfile.TemporaryDirectory(prefix=".egress-provision-", dir=root) as name:
        directory = Path(name)
        archive = directory / "package.deb"
        archive.write_bytes(data)
        result = subprocess.run(
            ["/usr/bin/dpkg-deb", "--fsys-tarfile", str(archive)],
            capture_output=True,
            timeout=5,
            check=True,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
        if len(result.stdout) > 1024 * 1024:
            raise PermissionError("egress_package_integrity")
        with tarfile.open(fileobj=io.BytesIO(result.stdout)) as bundle:
            entry = bundle.getmember("./usr/bin/passt")
            if not entry.isfile() or entry.size != 277704:
                raise PermissionError("egress_package_integrity")
            stream = bundle.extractfile(entry)
            if stream is None:
                raise PermissionError("egress_package_integrity")
            binary = directory / "pasta"
            binary.write_bytes(stream.read(277705))
            binary.chmod(0o500)
            _binary(binary)
            if executable_path().exists() or executable_path().is_symlink():
                _binary(executable_path())
            else:
                os.link(binary, executable_path())


def resolve_namespace(path):
    if path not in (MANAGED_NET, MANAGED_USER):
        return path
    session = _active.get()
    if session is None or session.closed:
        raise PermissionError("isolation_unavailable")
    session.check_alive()
    if session.supervisor is None:
        raise PermissionError("egress_session_unavailable")
    kind = "net" if path == MANAGED_NET else "user"
    return f"/proc/{session.supervisor.pid}/ns/{kind}"


def checkpoint(policy):
    if policy.network_namespace != MANAGED_NET:
        return
    session = _active.get()
    if session is None or session.closed:
        raise PermissionError("isolation_unavailable")
    session.validate(policy)


class ManagedEgress:
    def __init__(self, policy, *, artifacts, assessment_run_id, seconds):
        self.policy = policy
        self.artifacts = artifacts
        self.seconds = seconds
        self.supervisor = self.helper = None
        self.temporary = None
        self.token = None
        self.closed = False
        self.identities = None
        self.routes = None
        self.evidence = {
            "schema_version": 1,
            "assessment_run_id": assessment_run_id,
            "backend": "pasta",
            "backend_version": PASTA_VERSION,
            "backend_sha256": PASTA_SHA256,
            "state": "preparing",
            "cleanup_verified": False,
        }

    def persist(self):
        from beeagent_module.integrations.beescan.detection import _persist

        _persist(self.artifacts, "egress_lifecycle.json", self.evidence)

    def _spawn(self, command, *, stdin=subprocess.DEVNULL):
        return subprocess.Popen(
            command,
            stdin=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "LANG": "C"},
            start_new_session=True,
        )

    def start(self):
        from beeagent_module.integrations.beescan.http_runner import bounded_process
        from beeagent_module.integrations.beescan.providers import (
            ProviderProvisioningError,
            _secure_root,
        )

        self.persist()
        try:
            if platform.system() != "Linux" or platform.machine() != "x86_64":
                raise PermissionError("egress_platform_unavailable")
            for executable in (
                "/usr/bin/unshare",
                "/usr/bin/nsenter",
                "/usr/bin/bwrap",
                "/usr/sbin/nft",
                "/usr/sbin/ip",
                "/usr/bin/python3",
                "/usr/bin/prlimit",
            ):
                info = Path(executable).stat()
                if (
                    info.st_uid != 0
                    or info.st_mode & 0o022
                    or not os.access(executable, os.X_OK)
                ):
                    raise PermissionError("egress_prerequisite_unavailable")
            _secure_root(executable_path().parent)
            binary = _binary(executable_path())
            self.temporary = tempfile.TemporaryDirectory(prefix="bee-egress-")
            directory = Path(self.temporary.name)
            snapshot = directory / "pasta"
            snapshot.write_bytes(binary)
            snapshot.chmod(0o500)
            worker = directory / "worker.py"
            worker.write_bytes(
                Path(__file__).with_name("egress_worker.py").read_bytes()
            )
            worker.chmod(0o400)
            code, version = bounded_process(
                [str(snapshot), "--version"],
                seconds=2,
                limit=4096,
                memory_mb=256,
            )
            if code or not version.startswith(f"pasta {PASTA_VERSION}\n".encode()):
                raise PermissionError("egress_helper_integrity")
            self.supervisor = self._spawn(
                [
                    "/usr/bin/unshare",
                    "-Urn",
                    "/usr/bin/python3",
                    "-I",
                    str(worker),
                    str(os.getpid()),
                    "supervise",
                    self.policy.connected_ip,
                    str(self.policy.port),
                    str(self.seconds + 15),
                ],
                stdin=subprocess.PIPE,
            )
            if self.supervisor.stdout is None:
                raise RuntimeError("egress_setup_unverified")
            with selectors.DefaultSelector() as selector:
                selector.register(self.supervisor.stdout, selectors.EVENT_READ)
                if not selector.select(3):
                    raise TimeoutError("egress_setup_timeout")
                try:
                    ready = json.loads(os.read(self.supervisor.stdout.fileno(), 128))
                except ValueError:
                    raise PermissionError("egress_setup_unverified") from None
            if ready != {"pid": self.supervisor.pid}:
                raise PermissionError("egress_setup_unverified")
            pid = self.supervisor.pid
            self.helper = self._spawn(
                [
                    "/usr/bin/python3",
                    "-I",
                    str(worker),
                    str(os.getpid()),
                    "exec",
                    str(snapshot),
                    str(self.seconds + 15),
                    "-f",
                    "-6" if ":" in self.policy.connected_ip else "-4",
                    "--config-net",
                    "--no-map-gw",
                    "--no-splice",
                    "--no-udp",
                    "--no-icmp",
                    "--no-dhcp",
                    "--no-dhcpv6",
                    "--no-ndp",
                    "--no-ra",
                    "-t",
                    "none",
                    "-u",
                    "none",
                    "-T",
                    "none",
                    "-U",
                    "none",
                    "--userns",
                    f"/proc/{pid}/ns/user",
                    "--netns",
                    f"/proc/{pid}/ns/net",
                ]
            )
            self.identities = tuple(
                os.stat(f"/proc/{pid}/ns/{kind}").st_ino for kind in ("user", "net")
            )
            deadline = time.monotonic() + 3
            while True:
                self.check_alive()
                routes = self.inspect(
                    "/usr/sbin/ip", "-j", "route", "show", "table", "all"
                )
                if any(item.get("dst") == "default" for item in json.loads(routes)):
                    self.routes = routes
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("egress_readiness_timeout")
                time.sleep(0.05)
            self.validate(self.policy)
            self.token = _active.set(self)
            self.evidence.update(
                state="ready",
                enforcement_verified=True,
                firewall_sha256=hashlib.sha256(
                    self.inspect("/usr/sbin/nft", "-j", "list", "ruleset")
                ).hexdigest(),
                routes_sha256=hashlib.sha256(self.routes).hexdigest(),
                supervisor_pid=pid,
                helper_pid=self.helper.pid,
                user_namespace_inode=self.identities[0],
                network_namespace_inode=self.identities[1],
            )
            self.persist()
        except FileNotFoundError, ProviderProvisioningError:
            self.close()
            raise PermissionError("egress_prerequisite_unavailable") from None
        except BaseException:
            self.close()
            raise

    def check_alive(self):
        if (
            self.closed
            or self.supervisor is None
            or self.helper is None
            or self.supervisor.poll() is not None
            or self.helper.poll() is not None
        ):
            raise PermissionError("egress_session_unavailable")
        if self.identities is not None and self.identities != tuple(
            os.stat(f"/proc/{self.supervisor.pid}/ns/{kind}").st_ino
            for kind in ("user", "net")
        ):
            raise PermissionError("egress_namespace_changed")

    def inspect(self, *arguments):
        from beeagent_module.integrations.beescan.http_runner import bounded_process

        if self.supervisor is None:
            raise PermissionError("egress_session_unavailable")
        pid = self.supervisor.pid
        code, raw = bounded_process(
            [
                "/usr/bin/nsenter",
                "--preserve-credentials",
                f"--user=/proc/{pid}/ns/user",
                f"--net=/proc/{pid}/ns/net",
                "--",
                *arguments,
            ],
            seconds=2,
            limit=65536,
            memory_mb=256,
        )
        if code:
            raise PermissionError("egress_unverified")
        return raw

    def validate(self, policy):
        from beeagent_module.integrations.beescan.http_runner import validate_firewall

        self.check_alive()
        if (policy.connected_ip, policy.port, policy.operator_uid) != (
            self.policy.connected_ip,
            self.policy.port,
            self.policy.operator_uid,
        ):
            raise PermissionError("egress_binding_changed")
        validate_firewall(
            self.inspect("/usr/sbin/nft", "-j", "list", "ruleset"), policy
        )
        if (
            self.routes is not None
            and self.inspect("/usr/sbin/ip", "-j", "route", "show", "table", "all")
            != self.routes
        ):
            raise PermissionError("egress_routes_changed")

    def close(self):
        if self.closed:
            return
        enforcement_error = False
        if self.evidence["state"] == "ready":
            try:
                self.validate(self.policy)
            except OSError, ValueError, RuntimeError, subprocess.SubprocessError:
                enforcement_error = True
                self.evidence["enforcement_verified"] = False
        self.closed = True
        if self.token is not None:
            _active.reset(self.token)
            self.token = None
        errors = []
        for process in (self.helper, self.supervisor):
            if process is None:
                continue
            try:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            except OSError, subprocess.TimeoutExpired:
                errors.append("process_cleanup_failed")
            finally:
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()
        if self.temporary is not None:
            self.temporary.cleanup()
        self.evidence.update(
            state="cleanup_failed" if errors else "closed", cleanup_verified=not errors
        )
        self.persist()
        if errors:
            raise RuntimeError("egress_cleanup_unverified")
        if enforcement_error:
            raise PermissionError("egress_unverified")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "provision":
        raise SystemExit(
            "Usage: python -m beeagent_module.integrations.beescan.egress provision PACKAGE.deb"
        )
    provision(Path(sys.argv[2]))
