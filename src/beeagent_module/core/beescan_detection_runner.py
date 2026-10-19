import fcntl
import hashlib
import json
import os
import stat
import tempfile
import time
from pathlib import Path

from beeagent_module.core.beescan_detection_policy import TEMPLATE_SHA256
from beeagent_module.core.beescan_http_runner import (
    _open_namespace,
    _provider_snapshot,
    bounded_process,
    validate_firewall,
)
from beeagent_module.core.beescan_probe import _unique_object


def read_regular(path, *, limit, dir_fd=None):
    descriptor = os.open(
        path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o022
            or info.st_size > limit
        ):
            raise PermissionError("invalid_asset")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise PermissionError("invalid_asset")
        return data


def snapshot_template(policy, directory):
    try:
        data = read_regular(policy.template_path, limit=4096)
    except OSError:
        raise PermissionError("template_integrity") from None
    if (
        hashlib.sha256(data).hexdigest() != TEMPLATE_SHA256
        or policy.template_sha256 != TEMPLATE_SHA256
    ):
        raise PermissionError("template_integrity")
    snapshot = directory / "template.yaml"
    snapshot.write_bytes(data)
    snapshot.chmod(0o444)
    return snapshot


def safe_response(capture):
    marker = capture["marker_header"]
    header = "" if marker is None else f"X-Beescan-Marker: {marker}\r\n"
    return f"HTTP/1.1 {capture['status_code']} Captured\r\n{header}X-Beescan-Completion: complete\r\nContent-Length: 0\r\n\r\n"


def parse_capture(raw, policy, *, http_signals=False):
    if type(http_signals) is not bool:
        raise ValueError("invalid_signal_selection")
    if type(raw) is not bytes or not 1 <= len(raw) <= 4096:
        raise ValueError("invalid_capture")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
        fields = {
            "origin",
            "connected_ip",
            "port",
            "method",
            "request_count",
            "status_code",
            "marker_header",
            "complete",
        }
        if http_signals:
            fields.add("header_facts")
        if type(data) is not dict or set(data) != fields:
            raise ValueError
        expected = {
            "origin": policy.origin,
            "connected_ip": policy.connected_ip,
            "port": policy.port,
            "method": "GET",
            "request_count": 1,
            "complete": True,
        }
        if any(
            type(data[key]) is not type(value) or data[key] != value
            for key, value in expected.items()
        ):
            raise ValueError
        if (
            type(data["status_code"]) is not int
            or not 200 <= data["status_code"] <= 599
            or 300 <= data["status_code"] <= 399
        ):
            raise ValueError
        if data["marker_header"] is not None and (
            type(data["marker_header"]) is not str
            or data["marker_header"] not in {"present", "absent"}
        ):
            raise ValueError
        if http_signals:
            facts = data["header_facts"]
            if type(facts) is not dict or set(facts) != {
                "nosniff",
                "hsts",
                "hsts_max_age",
                "https",
                "complete",
            }:
                raise ValueError
            if (
                type(facts["nosniff"]) is not str
                or facts["nosniff"] not in {"absent", "nosniff", "other"}
                or type(facts["hsts"]) is not str
                or facts["hsts"] not in {"absent", "max_age", "other"}
                or type(facts["https"]) is not bool
                or facts["https"] != policy.origin.startswith("https:")
                or facts["complete"] is not True
            ):
                raise ValueError
            age = facts["hsts_max_age"]
            if facts["hsts"] == "max_age":
                if type(age) is not int or not 0 <= age <= 2**63 - 1:
                    raise ValueError
            elif age is not None:
                raise ValueError
        return data
    except ValueError, TypeError, KeyError, RecursionError, UnicodeError:
        raise ValueError("invalid_capture") from None


def nuclei_arguments():
    return [
        "/provider",
        "-passive",
        "-u",
        "/input.txt",
        "-t",
        "/template.yaml",
        "-jsonl",
        "-silent",
        "-no-color",
        "-duc",
        "-ni",
        "-auth=false",
        "-no-stdin",
        "-omit-raw",
        "-omit-template",
        "-c",
        "1",
        "-bs",
        "1",
        "-retries",
        "0",
        "-dr",
        "-nh",
        "-dc",
    ]


def _sandbox(policy):
    command = [
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
        "--setenv",
        "GOMEMLIMIT",
        f"{policy.memory_mb // 2}MiB",
        "--setenv",
        "GOMAXPROCS",
        "2",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        "/tmp",
    ]
    for source in ("PUBLIC", "GITHUB", "GITLAB", "AWS", "AZURE"):
        command += ["--setenv", f"DISABLE_NUCLEI_TEMPLATES_{source}_DOWNLOAD", "true"]
    return command


def run_detection_provider(
    policy, *, reauthorize, http_signals=False, git_exposure=False
):
    if type(git_exposure) is not bool or (git_exposure and http_signals):
        raise ValueError("invalid_capture_selection")
    deadline = time.monotonic() + policy.time_budget_seconds

    def run(argv, *, limit, pass_fds=(), stderr=False):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("timeout")
        return bounded_process(
            ["/usr/bin/prlimit", "--nproc=4096", "--", *argv],
            seconds=remaining,
            limit=limit,
            memory_mb=policy.memory_mb,
            pass_fds=pass_fds,
            capture_stderr=stderr,
        )

    for executable in (
        "/usr/bin/nsenter",
        "/usr/bin/bwrap",
        "/usr/sbin/nft",
        "/usr/bin/prlimit",
        "/usr/bin/python3",
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
    user_fd = _open_namespace(policy.user_namespace, 0x10000000, policy.operator_uid)
    net_fd = None
    try:
        net_fd = _open_namespace(
            policy.network_namespace, 0x40000000, policy.operator_uid
        )
        owner_fd = fcntl.ioctl(net_fd, 0xB701)
        try:
            if os.fstat(owner_fd).st_ino != os.fstat(user_fd).st_ino:
                raise PermissionError("isolation_unavailable")
        finally:
            os.close(owner_fd)
        prefix = [
            "/usr/bin/nsenter",
            "--preserve-credentials",
            f"--user=/proc/self/fd/{user_fd}",
            f"--net=/proc/self/fd/{net_fd}",
            "--",
        ]
        descriptors = (user_fd, net_fd)
        code, rules = run(
            [*prefix, "/usr/sbin/nft", "-j", "list", "ruleset"],
            limit=65536,
            pass_fds=descriptors,
        )
        if code:
            raise PermissionError("egress_unverified")
        validate_firewall(rules, policy)
        with tempfile.TemporaryDirectory(prefix="bee-detect-") as temporary:
            directory = Path(temporary)
            if not git_exposure:
                binary = _provider_snapshot(
                    policy, directory, limit_bytes=192 * 1024 * 1024
                )
                template = snapshot_template(policy, directory)
                offline = [
                    *_sandbox(policy),
                    "--ro-bind",
                    str(binary),
                    "/provider",
                    "--ro-bind",
                    str(template),
                    "/template.yaml",
                ]
                code, version = run(
                    [
                        *offline,
                        "--",
                        "/provider",
                        "-version",
                        "-duc",
                        "-auth=false",
                        "-no-color",
                    ],
                    limit=4096,
                    stderr=True,
                )
                if code:
                    raise PermissionError("isolation_unavailable")
                if b"Nuclei Engine Version: v3.11.1\n" not in version:
                    raise PermissionError("provider_version_unverified")
            worker = directory / "capture.py"
            worker.write_bytes(
                Path(__file__).with_name("beescan_capture_worker.py").read_bytes()
            )
            worker.chmod(0o444)
            capture_sandbox = _sandbox(policy)
            capture_sandbox += [
                "--share-net",
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
                str(worker),
                "/capture.py",
            ]
            if Path("/etc/ssl/certs").is_dir():
                capture_sandbox += ["--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs"]
            if git_exposure:
                from beescan.domain import git_head_signature

                signature = directory / "git_head_signature.py"
                signature.write_bytes(
                    read_regular(git_head_signature.__file__, limit=8192)
                )
                signature.chmod(0o444)
                capture_sandbox += [
                    "--ro-bind",
                    str(signature),
                    "/git_head_signature.py",
                ]
            reauthorize()
            config = {
                "origin": policy.origin,
                "connected_ip": policy.connected_ip,
                "port": policy.port,
                "seconds": max(0.001, deadline - time.monotonic()),
            }
            if http_signals:
                config["http_signals"] = True
            if git_exposure:
                config["git_exposure"] = True
            code, raw_capture = run(
                [
                    *prefix,
                    *capture_sandbox,
                    "--",
                    "/usr/bin/python3",
                    "-I",
                    "-S",
                    "/capture.py",
                    json.dumps(config),
                ],
                limit=4096,
                pass_fds=descriptors,
            )
            if code == 3:
                raise PermissionError("redirect_refused")
            if code == 4:
                raise TimeoutError("timeout")
            if code:
                raise ValueError("capture_failed")
            if git_exposure:
                return raw_capture
            capture = parse_capture(raw_capture, policy, http_signals=http_signals)
            input_file = directory / "input.txt"
            input_file.write_text(safe_response(capture), encoding="ascii")
            input_file.chmod(0o444)
            reauthorize()
            code, output = run(
                [
                    *offline,
                    "--ro-bind",
                    str(input_file),
                    "/input.txt",
                    "--",
                    *nuclei_arguments(),
                ],
                limit=policy.output_bytes,
            )
            if code:
                raise ValueError("provider_failed")
            return output, capture
    finally:
        try:
            if net_fd is not None:
                os.close(net_fd)
        finally:
            os.close(user_fd)
