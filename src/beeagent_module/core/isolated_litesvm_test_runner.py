from __future__ import annotations

import hashlib
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_RUNNER_ID = "litesvm_mocha_tsx_v1"
_TEST_PATH = Path("tests/litesvm.test.ts")
_REQUIRED_FILES = (
    Path("package.json"),
    Path("pnpm-lock.yaml"),
    _TEST_PATH,
    Path("node_modules/mocha/bin/mocha.js"),
    Path("node_modules/tsx/dist/loader.mjs"),
)
_MAX_OUTPUT_BYTES = 65_536
_TIMEOUT_SECONDS = 90
_MAX_FILES = 10_000
_MAX_TOTAL_BYTES = 256 * 1024**2
_MAX_FILE_BYTES = 64 * 1024**2
_MAX_DIRECTORIES = 4096
_MAX_DEPTH = 32
_STAGING_TIMEOUT_SECONDS = 30
_MEMORY_MAX_BYTES = 768 * 1024**2
_MEMORY_PROBE_TIMEOUT_SECONDS = 5
_HARNESS_ROOT_FILES = frozenset(
    {"package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "tsconfig.json"}
)
_TARGET_ROOT_FILES = frozenset({"Anchor.toml", "Cargo.lock", "Cargo.toml"})
_HARNESS_DIRECTORIES = frozenset({"node_modules", "tests"})
_STAGE_SCRIPT = """
import os
import stat
import sys
from pathlib import Path

source = Path("/input")
destination = Path("/workspace/project")
max_total, max_file, max_files, max_directories, max_depth = map(int, sys.argv[1:])
total = 0
files = 0
directories_seen = 0
for current, directories, names in os.walk(source, followlinks=False):
    current_path = Path(current)
    relative = current_path.relative_to(source)
    if current_path.is_symlink() or any(
        (current_path / name).is_symlink() for name in directories + names
    ):
        raise RuntimeError("symlink")
    directories_seen += 1
    if directories_seen > max_directories or len(relative.parts) > max_depth:
        raise RuntimeError("directory_limit")
    output_directory = destination / relative
    output_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in names:
        input_path = current_path / name
        input_stat = input_path.stat(follow_symlinks=False)
        if not stat.S_ISREG(input_stat.st_mode):
            raise RuntimeError("unsafe_file")
        files += 1
        if files > max_files:
            raise RuntimeError("file_limit")
        copied = 0
        output_path = output_directory / name
        with input_path.open("rb") as input_file, output_path.open("xb") as output_file:
            while chunk := input_file.read(65536):
                copied += len(chunk)
                if copied > max_file or total + len(chunk) > max_total:
                    raise RuntimeError("byte_limit")
                output_file.write(chunk)
                total += len(chunk)
        os.chmod(output_path, stat.S_IMODE(input_stat.st_mode))
""".strip()


class IsolatedTestRefusal(ValueError):
    pass


class IsolatedTestInfrastructureFailure(RuntimeError):
    pass


def run_litesvm_test(project_root: str, side: str) -> dict[str, Any]:
    root = _validated_project_root(project_root)
    _validate_layout(root)
    node = shutil.which("node", path="/usr/bin:/bin")
    bwrap = shutil.which("bwrap", path="/usr/bin:/bin")
    systemd_run = shutil.which("systemd-run", path="/usr/bin:/bin")
    if node is None:
        raise IsolatedTestRefusal("missing_node")
    if bwrap is None:
        raise IsolatedTestRefusal("sandbox_unavailable")
    if systemd_run is None:
        raise IsolatedTestInfrastructureFailure("memory_limit_unavailable")
    if not _sandbox_is_available(bwrap):
        raise IsolatedTestRefusal("sandbox_unavailable")
    _verify_memory_limit(systemd_run)
    started = time.monotonic()
    with _pinned_project_root(root) as input_source:
        with tempfile.TemporaryDirectory(prefix="beeagent-litesvm-") as temporary:
            workspace = Path(temporary) / "workspace"
            _stage_workspace(bwrap, input_source, workspace)
            project = workspace / "project"
            _validate_layout(project)
            fingerprint = _fingerprint(project)
            output_path = Path(temporary) / "runner.log"
            exit_code, timed_out, cleanup = _run_test_process(
                bwrap, systemd_run, project, output_path
            )
            elapsed = round(time.monotonic() - started, 3)
            output = output_path.read_bytes()[:_MAX_OUTPUT_BYTES]
    if cleanup != "ok":
        raise RuntimeError("cleanup_failed")
    return {
        "schema_version": 1,
        "side": side,
        "runner_id": _RUNNER_ID,
        "runner_version": _node_version(node),
        "isolation": "bubblewrap_unshare_all",
        "isolation_result": "verified",
        "project_fingerprint": fingerprint["project"],
        "test_path": _TEST_PATH.as_posix(),
        "test_fingerprint": fingerprint["test"],
        "dependency_fingerprint": fingerprint["dependencies"],
        "exit_code": exit_code,
        "timed_out": timed_out,
        "execution_status": "timeout" if timed_out else "completed",
        "outcome": "incomplete"
        if timed_out
        else ("passed" if exit_code == 0 else "failed"),
        "elapsed_seconds": elapsed,
        "cleanup": cleanup,
        "diagnostic_output_sha256": hashlib.sha256(output).hexdigest(),
    }


def _validated_project_root(value: str) -> Path:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise IsolatedTestRefusal("invalid_project_root")
    raw = Path(value)
    if not raw.is_absolute() or raw.is_symlink() or not raw.is_dir():
        raise IsolatedTestRefusal("invalid_project_root")
    resolved = raw.resolve(strict=True)
    if resolved != raw:
        raise IsolatedTestRefusal("invalid_project_root")
    return resolved


def _validate_layout(root: Path) -> None:
    _bounded_files(root)
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink():
            raise IsolatedTestRefusal("symlink_not_allowed")
        if any((current_path / name).is_symlink() for name in directories + files):
            raise IsolatedTestRefusal("symlink_not_allowed")
    for path in _bounded_files(root):
        _input_kind(path.relative_to(root))
    for relative in _REQUIRED_FILES:
        path = root / relative
        if not path.is_file():
            if relative.is_relative_to(Path("node_modules")):
                raise IsolatedTestRefusal("missing_test_dependencies")
            raise IsolatedTestRefusal("unsupported_layout")
        if path.is_symlink():
            raise IsolatedTestRefusal("unsupported_layout")


def _bounded_files(root: Path) -> list[Path]:
    files: list[Path] = []
    total = 0
    directories_seen = 0
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink() or any(
            (current_path / name).is_symlink() for name in directories + names
        ):
            raise IsolatedTestRefusal("symlink_not_allowed")
        directories_seen += 1
        if (
            directories_seen > _MAX_DIRECTORIES
            or len(current_path.relative_to(root).parts) > _MAX_DEPTH
        ):
            raise IsolatedTestRefusal("unsafe_project_tree")
        for name in names:
            path = current_path / name
            stat = path.stat(follow_symlinks=False)
            if not path.is_file() or stat.st_size > _MAX_FILE_BYTES:
                raise IsolatedTestRefusal("unsafe_project_tree")
            files.append(path)
            total += stat.st_size
            if len(files) > _MAX_FILES or total > _MAX_TOTAL_BYTES:
                raise IsolatedTestRefusal("unsafe_project_tree")
    return files


def _input_kind(relative: Path) -> str:
    if len(relative.parts) == 1:
        if relative.name in _HARNESS_ROOT_FILES:
            return "harness"
        if relative.name in _TARGET_ROOT_FILES:
            return "target"
    if relative.parts[0] in _HARNESS_DIRECTORIES:
        return "harness"
    if relative.parts[0] == "programs":
        if relative.name in {"Cargo.toml", "Xargo.toml"} or relative.suffix == ".rs":
            return "target"
        raise IsolatedTestRefusal("unsupported_layout")
    if relative.parts[0] == "target":
        if (
            len(relative.parts) == 3
            and relative.parts[1] == "deploy"
            and (relative.suffix == ".so" or relative.name.endswith("-keypair.json"))
        ):
            return "target"
        if (
            len(relative.parts) == 3
            and relative.parts[1] == "idl"
            and relative.suffix == ".json"
        ):
            return "target"
        if (
            len(relative.parts) == 3
            and relative.parts[1] == "types"
            and relative.suffix in {".cjs", ".js", ".mjs", ".ts", ".tsx"}
        ):
            return "harness"
        raise IsolatedTestRefusal("unsupported_layout")
    raise IsolatedTestRefusal("unsupported_layout")


@contextmanager
def _pinned_project_root(root: Path) -> Iterator[str]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        stat = os.fstat(descriptor)
        if not os.path.samestat(stat, root.stat(follow_symlinks=False)):
            raise IsolatedTestRefusal("invalid_project_root")
        yield f"/proc/self/fd/{descriptor}"
    finally:
        os.close(descriptor)


def _stage_workspace(bwrap: str, input_source: str, workspace: Path) -> None:
    workspace.mkdir(mode=0o700)
    descriptor = int(input_source.rsplit("/", maxsplit=1)[1])
    try:
        completed = subprocess.run(
            [
                bwrap,
                "--unshare-all",
                "--die-with-parent",
                "--new-session",
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
                "--ro-bind",
                input_source,
                "/input",
                "--bind",
                str(workspace),
                "/workspace",
                "--",
                "/usr/bin/sh",
                "-c",
                _staging_command(),
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(descriptor,),
            timeout=_STAGING_TIMEOUT_SECONDS,
            preexec_fn=_limit_staging_resources,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("staging_failed") from exc
    if completed.returncode != 0:
        raise RuntimeError("staging_failed")


def _fingerprint(root: Path) -> dict[str, str]:
    project = hashlib.sha256()
    harness = hashlib.sha256()
    for path in sorted(_bounded_files(root)):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        project.update(relative)
        project.update(b"\0")
        project.update(_hash_file(path).encode("ascii"))
        if _input_kind(path.relative_to(root)) == "harness":
            harness.update(relative)
            harness.update(b"\0")
            harness.update(_hash_file(path).encode("ascii"))
    return {
        "project": project.hexdigest(),
        "test": _hash_file(root / _TEST_PATH),
        "dependencies": harness.hexdigest(),
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _staging_command() -> str:
    values = " ".join(
        str(value)
        for value in (
            _MAX_TOTAL_BYTES,
            _MAX_FILE_BYTES,
            _MAX_FILES,
            _MAX_DIRECTORIES,
            _MAX_DEPTH,
        )
    )
    return f"exec /usr/bin/python3 -c {_shell_quote(_STAGE_SCRIPT)} {values}"


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\\"'\\\"'") + "'"


def _sandbox_command(
    bwrap: str,
    workspace: Path,
    status_descriptor: int | None = None,
    runner_ready_descriptor: int | None = None,
) -> list[str]:
    command = [
        bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
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
        "--ro-bind",
        str(workspace),
        "/project",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--chdir",
        "/project",
    ]
    if status_descriptor is None:
        if runner_ready_descriptor is not None:
            raise ValueError("runner_ready_descriptor requires status_descriptor")
        return command + _node_test_command()
    if runner_ready_descriptor is None:
        raise ValueError("runner_ready_descriptor is required")
    return command + [
        "--json-status-fd",
        str(status_descriptor),
        "--",
        "/usr/bin/sh",
        "-c",
        _runner_command(runner_ready_descriptor),
    ]


def _node_test_command() -> list[str]:
    return [
        "--",
        "/usr/bin/node",
        "--max-old-space-size=512",
        "--import",
        "/project/node_modules/tsx/dist/loader.mjs",
        "/project/node_modules/mocha/bin/mocha.js",
        "--reporter",
        "dot",
        "/project/tests/litesvm.test.ts",
    ]


def _runner_command(runner_ready_descriptor: int) -> str:
    node = (
        "/usr/bin/node --max-old-space-size=512 "
        "--import /project/node_modules/tsx/dist/loader.mjs"
    )
    mocha = "/project/node_modules/mocha/bin/mocha.js"
    return (
        f"{node} {mocha} --version >/dev/null 2>&1 || exit 125; "
        f"printf 'ready\\n' >&{runner_ready_descriptor}; "
        f"exec {node} {mocha} --reporter dot /project/tests/litesvm.test.ts"
    )


def _run_test_process(
    bwrap: str, systemd_run: str, workspace: Path, output_path: Path
) -> tuple[int, bool, str]:
    status_read, status_write = os.pipe()
    runner_ready_read, runner_ready_write = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    timed_out = False
    cleanup = "ok"
    try:
        with output_path.open("wb") as output:
            process = subprocess.Popen(
                _memory_limited_command(
                    systemd_run,
                    _sandbox_command(
                        bwrap, workspace, status_write, runner_ready_write
                    ),
                ),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                preexec_fn=_limit_resources,
                pass_fds=(status_write, runner_ready_write),
            )
            os.close(status_write)
            status_write = -1
            os.close(runner_ready_write)
            runner_ready_write = -1
            try:
                exit_code = process.wait(timeout=_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                cleanup = _terminate_process_group(process)
                exit_code = 124
        status = os.read(status_read, _MAX_OUTPUT_BYTES)
        runner_ready = os.read(runner_ready_read, _MAX_OUTPUT_BYTES)
    finally:
        if status_write >= 0:
            os.close(status_write)
        if runner_ready_write >= 0:
            os.close(runner_ready_write)
        os.close(status_read)
        os.close(runner_ready_read)
        if process is not None and process.poll() is None:
            final_cleanup = _terminate_process_group(process)
            if cleanup != "ok" or final_cleanup != "ok":
                cleanup = "failed"
    if cleanup != "ok":
        raise RuntimeError("cleanup_failed")
    if not timed_out and (not status or runner_ready != b"ready\n"):
        raise IsolatedTestInfrastructureFailure("runner_unavailable")
    return exit_code, timed_out, cleanup


def _sandbox_is_available(bwrap: str) -> bool:
    completed = subprocess.run(
        [
            bwrap,
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
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
            "/usr/bin/true",
        ],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    return completed.returncode == 0


def _memory_limited_command(systemd_run: str, command: list[str]) -> list[str]:
    return [
        systemd_run,
        "--user",
        "--scope",
        "--quiet",
        "--collect",
        "--property=MemoryMax=" + str(_MEMORY_MAX_BYTES),
        "--property=MemorySwapMax=0",
        "--",
        *command,
    ]


def _verify_memory_limit(systemd_run: str) -> None:
    probe = (
        "cgroup=$(cut -d: -f3 /proc/self/cgroup); "
        'cat /sys/fs/cgroup"$cgroup"/memory.max; '
        'cat /sys/fs/cgroup"$cgroup"/memory.swap.max'
    )
    try:
        completed = subprocess.run(
            _memory_limited_command(systemd_run, ["/usr/bin/sh", "-c", probe]),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_MEMORY_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IsolatedTestInfrastructureFailure("memory_limit_unavailable") from exc
    if completed.returncode != 0 or completed.stdout != f"{_MEMORY_MAX_BYTES}\n0\n":
        raise IsolatedTestInfrastructureFailure("memory_limit_unavailable")


def _limit_resources() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (_TIMEOUT_SECONDS, _TIMEOUT_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_OUTPUT_BYTES, _MAX_OUTPUT_BYTES))


def _limit_staging_resources() -> None:
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (_STAGING_TIMEOUT_SECONDS, _STAGING_TIMEOUT_SECONDS),
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_FILE_BYTES, _MAX_FILE_BYTES))


def _terminate_process_group(process: subprocess.Popen[bytes]) -> str:
    try:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        return "ok"
    except OSError, subprocess.TimeoutExpired:
        return "failed"


def _node_version(node: str) -> str:
    completed = subprocess.run(
        [node, "--version"],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=5,
    )
    if completed.returncode != 0:
        raise IsolatedTestRefusal("missing_node")
    version = completed.stdout.strip()
    if not version or len(version) > 64:
        raise IsolatedTestRefusal("missing_node")
    return version
