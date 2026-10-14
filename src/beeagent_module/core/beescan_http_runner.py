import fcntl
import hashlib
import json
import os
import selectors
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from beeagent_module.core.beescan_policy import ProbePolicy

ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": "/tmp"}


def bounded_process(
    argv, *, seconds, limit, memory_mb, pass_fds=(), capture_stderr=False
):
    command = [
        "/usr/bin/prlimit",
        f"--as={memory_mb * 1024 * 1024}",
        f"--cpu={max(1, seconds)}",
        "--nofile=64",
        "--fsize=65536",
        "--core=0",
        "--",
        *argv,
    ]
    output = bytearray()
    stderr_bytes = 0
    error_output = bytearray()
    deadline = time.monotonic() + seconds
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
        start_new_session=True,
        pass_fds=pass_fds,
    )
    try:
        if process.stdout is None or process.stderr is None:
            raise RuntimeError("missing_process_pipes")
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout.fileno(), selectors.EVENT_READ, "stdout")
            selector.register(process.stderr.fileno(), selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timeout")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.data == "stdout":
                        output.extend(chunk)
                    else:
                        stderr_bytes += len(chunk)
                        if capture_stderr:
                            error_output.extend(chunk)
                    if len(output) + stderr_bytes > limit:
                        raise ValueError("output_limit")
            code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            return code, bytes(output + error_output)
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def expected_firewall(address: str, port: int) -> list[dict]:
    family = "ip" if ip_address(address).version == 4 else "ip6"
    return [
        {"table": {"family": "inet", "name": "beescan"}},
        {
            "chain": {
                "family": "inet",
                "table": "beescan",
                "name": "output",
                "type": "filter",
                "hook": "output",
                "prio": -150,
                "policy": "drop",
            }
        },
        {
            "rule": {
                "family": "inet",
                "table": "beescan",
                "chain": "output",
                "expr": [
                    {
                        "match": {
                            "op": "==",
                            "left": {"payload": {"protocol": family, "field": "daddr"}},
                            "right": address,
                        }
                    },
                    {
                        "match": {
                            "op": "==",
                            "left": {"payload": {"protocol": "tcp", "field": "dport"}},
                            "right": port,
                        }
                    },
                    {"accept": None},
                ],
            }
        },
        {
            "rule": {
                "family": "inet",
                "table": "beescan",
                "chain": "output",
                "expr": [
                    {
                        "match": {
                            "op": "in",
                            "left": {"ct": {"key": "state"}},
                            "right": "established",
                        }
                    },
                    {
                        "match": {
                            "op": "!=",
                            "left": {
                                "&": [
                                    {"payload": {"protocol": "tcp", "field": "flags"}},
                                    {"|": ["syn", "ack"]},
                                ]
                            },
                            "right": "syn",
                        }
                    },
                    {"accept": None},
                ],
            }
        },
    ]


def validate_firewall(raw: bytes, policy: ProbePolicy) -> None:
    try:
        document = json.loads(raw)
        if type(document) is not dict or set(document) != {"nftables"}:
            raise ValueError
        items = document["nftables"]
        if type(items) is not list or not 4 <= len(items) <= 5:
            raise ValueError
        normalized = []
        for item in items:
            if type(item) is not dict or len(item) != 1:
                raise ValueError
            key, value = next(iter(item.items()))
            if key == "metainfo":
                continue
            if type(value) is not dict:
                raise ValueError
            normalized.append({key: {k: v for k, v in value.items() if k != "handle"}})
        if normalized != expected_firewall(policy.connected_ip, policy.port):
            raise ValueError
    except ValueError, TypeError, KeyError, RecursionError:
        raise PermissionError("egress_unverified") from None


def _provider_snapshot(policy, directory):
    try:
        descriptor = os.open(
            policy.executable,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    except OSError:
        raise PermissionError("provider_integrity") from None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o022
            or info.st_size > 64 * 1024 * 1024
        ):
            raise PermissionError("provider_integrity")
        binary = stream.read(64 * 1024 * 1024 + 1)
    if hashlib.sha256(binary).hexdigest() != policy.sha256:
        raise PermissionError("provider_integrity")
    if len(binary) < 64 or binary[:6] != b"\x7fELF\x02\x01":
        raise PermissionError("provider_integrity")
    offset = struct.unpack_from("<Q", binary, 32)[0]
    size, count = struct.unpack_from("<HH", binary, 54)
    if size < 56 or count > 64 or offset + size * count > len(binary):
        raise PermissionError("provider_integrity")
    if any(
        struct.unpack_from("<I", binary, offset + i * size)[0] == 3
        for i in range(count)
    ):
        raise PermissionError("provider_not_static")
    snapshot = directory / "httpx"
    snapshot.write_bytes(binary)
    snapshot.chmod(0o555)
    return snapshot


def _open_namespace(path, kind, operator_uid):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    except OSError:
        raise PermissionError("isolation_unavailable") from None
    try:
        info = os.fstat(descriptor)
        if (
            Path(path).parents[1].stat().st_uid != operator_uid
            or fcntl.ioctl(descriptor, 0xB703) != kind
        ):
            raise PermissionError("isolation_unavailable")
        name = "net" if kind == 0x40000000 else "user"
        if info.st_ino == os.stat("/proc/self/ns/" + name).st_ino:
            raise PermissionError("host_network_denied")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def provider_arguments(policy):
    return [
        "/provider",
        "-u",
        policy.origin,
        "-json",
        "-silent",
        "-no-color",
        "-disable-update-check",
        "-no-fallback-scheme",
        "-x",
        "HEAD",
        "-threads",
        "1",
        "-rate-limit",
        "1",
        "-retries",
        "0",
        "-timeout",
        str(policy.time_budget_seconds),
        "-omit-body",
        "-response-size-to-read",
        "1024",
        "-protocol",
        "http11",
        "-random-agent=false",
        "-status-code",
        "-content-type",
        "-cdn=false",
        "-follow-redirects=false",
        "-follow-host-redirects=false",
        "-respect-hsts=false",
        "-auth=false",
        "-no-stdin",
        "-no-decode",
    ]


def run_provider(policy: ProbePolicy, *, reauthorize):
    for executable in (
        "/usr/bin/nsenter",
        "/usr/bin/bwrap",
        "/usr/sbin/nft",
        "/usr/bin/prlimit",
    ):
        try:
            info = Path(executable).stat()
        except OSError:
            raise PermissionError("isolation_unavailable") from None
        if (
            info.st_uid != 0
            or info.st_mode & 0o022
            or not os.access(executable, os.X_OK)
        ):
            raise PermissionError("isolation_unavailable")
    user_descriptor = _open_namespace(
        policy.user_namespace, 0x10000000, policy.operator_uid
    )
    try:
        descriptor = _open_namespace(
            policy.network_namespace, 0x40000000, policy.operator_uid
        )
    except BaseException:
        os.close(user_descriptor)
        raise
    try:
        owner_descriptor = fcntl.ioctl(descriptor, 0xB701)
        try:
            if os.fstat(owner_descriptor).st_ino != os.fstat(user_descriptor).st_ino:
                raise PermissionError("isolation_unavailable")
        finally:
            os.close(owner_descriptor)
        prefix = [
            "/usr/bin/nsenter",
            "--preserve-credentials",
            f"--user=/proc/self/fd/{user_descriptor}",
            f"--net=/proc/self/fd/{descriptor}",
            "--",
        ]
        code, raw = bounded_process(
            [*prefix, "/usr/sbin/nft", "-j", "list", "ruleset"],
            seconds=3,
            limit=65536,
            memory_mb=256,
            pass_fds=(user_descriptor, descriptor),
        )
        if code:
            raise PermissionError("egress_unverified")
        validate_firewall(raw, policy)
        with tempfile.TemporaryDirectory(prefix="bee-http-") as temporary:
            directory = Path(temporary)
            snapshot = _provider_snapshot(policy, directory)
            hosts = directory / "hosts"
            hostname = urlsplit(policy.origin).hostname
            hosts.write_text(f"{policy.connected_ip} {hostname}\n", encoding="ascii")
            sandbox = [
                *prefix,
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
                "--setenv",
                "HOME",
                "/tmp",
                "--setenv",
                "GOMEMLIMIT",
                f"{policy.memory_mb // 2}MiB",
                "--tmpfs",
                "/tmp",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--dir",
                "/etc",
                "--ro-bind",
                str(hosts),
                "/etc/hosts",
                "--ro-bind",
                str(snapshot),
                "/provider",
                "--chdir",
                "/tmp",
            ]
            if Path("/etc/ssl/certs").is_dir():
                sandbox += ["--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs"]
            code, version = bounded_process(
                [
                    *sandbox,
                    "--",
                    "/provider",
                    "-version",
                    "-auth=false",
                    "-disable-update-check",
                    "-no-color",
                ],
                seconds=3,
                limit=4096,
                memory_mb=policy.memory_mb,
                pass_fds=(user_descriptor, descriptor),
                capture_stderr=True,
            )
            if code:
                raise PermissionError("isolation_unavailable")
            if b"Current Version: v1.12.0" not in version:
                raise PermissionError("provider_version_unverified")
            reauthorize()
            code, output = bounded_process(
                [*sandbox, "--", *provider_arguments(policy)],
                seconds=policy.time_budget_seconds,
                limit=policy.output_bytes,
                memory_mb=policy.memory_mb,
                pass_fds=(user_descriptor, descriptor),
            )
            if code:
                raise ValueError("provider_failed")
            return output
    finally:
        os.close(descriptor)
        os.close(user_descriptor)


def verify_resolution(policy):
    hostname = urlsplit(policy.origin).hostname
    try:
        addresses = {str(ip_address(hostname))}
    except ValueError:
        script = (
            "import json,socket,sys;"
            "print(json.dumps(sorted({r[4][0] for r in "
            "socket.getaddrinfo(sys.argv[1],None,0,socket.SOCK_STREAM)})))"
        )
        code, output = bounded_process(
            [sys.executable, "-I", "-c", script, hostname],
            seconds=3,
            limit=4096,
            memory_mb=256,
        )
        if code:
            raise PermissionError("dns_unverified")
        try:
            records = json.loads(output)
            if type(records) is not list or not 1 <= len(records) <= 16:
                raise ValueError
            addresses = {str(ip_address(value)) for value in records}
        except ValueError, TypeError:
            raise PermissionError("dns_unverified") from None
    if addresses != {policy.connected_ip}:
        raise PermissionError("dns_changed")
