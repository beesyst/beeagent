from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from beeagent_module.core import isolated_litesvm_test_runner as runner


def test_pinned_project_root_survives_a_path_replacement(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    original = tmp_path / "original"

    with runner._pinned_project_root(project) as source:
        project.rename(original)
        project.mkdir()
        (project / "replacement").write_text("replacement", encoding="utf-8")

        assert Path(source).resolve() == original
        assert (Path(source) / "replacement").exists() is False


def test_staging_passes_only_a_pinned_read_only_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    calls: list[dict[str, object]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner._stage_workspace("/usr/bin/bwrap", "/proc/self/fd/17", workspace)

    assert calls == [
        {
            "command": [
                "/usr/bin/bwrap",
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
                "/proc/self/fd/17",
                "/input",
                "--bind",
                str(workspace),
                "/workspace",
                "--",
                "/usr/bin/sh",
                "-c",
                runner._staging_command(),
            ],
            "check": False,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "pass_fds": (17,),
            "timeout": 30,
            "preexec_fn": runner._limit_staging_resources,
        }
    ]
    assert os.stat(workspace).st_mode & 0o777 == 0o700


def test_staging_timeout_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("bwrap", 30)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="staging_failed"):
        runner._stage_workspace("/usr/bin/bwrap", "/proc/self/fd/17", tmp_path / "work")


def test_staging_rejects_bytes_added_after_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bwrap = runner.shutil.which("bwrap", path="/usr/bin:/bin")
    systemd_run = runner.shutil.which("systemd-run", path="/usr/bin:/bin")
    if bwrap is None or systemd_run is None or not runner._sandbox_is_available(bwrap):
        pytest.skip("required isolated runtime is unavailable")
    project = tmp_path / "project"
    temporary = tmp_path / "temporary"
    project.mkdir()
    temporary.mkdir()
    _project_layout(project)
    original_total = sum(path.stat().st_size for path in runner._bounded_files(project))
    original_stage = runner._stage_workspace
    grown = project / "tests" / "grown.ts"

    def grow_then_stage(stage_bwrap: str, input_source: str, workspace: Path) -> None:
        grown.write_bytes(b"x")
        original_stage(stage_bwrap, input_source, workspace)

    monkeypatch.setattr(runner, "_MAX_TOTAL_BYTES", original_total)
    monkeypatch.setattr(runner, "_stage_workspace", grow_then_stage)
    monkeypatch.setattr(runner.tempfile, "tempdir", str(temporary))

    with pytest.raises(RuntimeError, match="staging_failed"):
        runner.run_litesvm_test(str(project), "baseline")

    assert list(temporary.glob("beeagent-litesvm-*")) == []


def test_test_execution_mounts_staged_project_read_only(tmp_path: Path) -> None:
    command = runner._sandbox_command("/usr/bin/bwrap", tmp_path / "project")

    mount_index = command.index("--ro-bind", command.index("--tmpfs"))
    assert command[mount_index : mount_index + 3] == [
        "--ro-bind",
        str(tmp_path / "project"),
        "/project",
    ]


def test_layout_reports_missing_pinned_test_dependencies(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'", encoding="utf-8")
    (tmp_path / "tests" / "litesvm.test.ts").write_text("", encoding="utf-8")

    with pytest.raises(runner.IsolatedTestRefusal, match="missing_test_dependencies"):
        runner._validate_layout(tmp_path)


def test_fingerprint_excludes_only_validated_target_inputs(tmp_path: Path) -> None:
    _project_layout(tmp_path)
    (tmp_path / "programs").mkdir()
    (tmp_path / "programs" / "lib.rs").write_text("one", encoding="utf-8")
    (tmp_path / "target" / "deploy").mkdir(parents=True)
    (tmp_path / "target" / "deploy" / "program.so").write_text("one", encoding="utf-8")
    first = runner._fingerprint(tmp_path)

    (tmp_path / "programs" / "lib.rs").write_text("two", encoding="utf-8")
    (tmp_path / "target" / "deploy" / "program.so").write_text("two", encoding="utf-8")
    second = runner._fingerprint(tmp_path)

    assert first["project"] != second["project"]
    assert first["test"] == second["test"]
    assert first["dependencies"] == second["dependencies"]


@pytest.mark.parametrize(
    "relative", ["tests/helper.ts", "node_modules/example/index.js"]
)
def test_harness_changes_are_not_comparable(tmp_path: Path, relative: str) -> None:
    _project_layout(tmp_path)
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("one", encoding="utf-8")
    first = runner._fingerprint(tmp_path)
    path.write_text("two", encoding="utf-8")

    assert first["dependencies"] != runner._fingerprint(tmp_path)["dependencies"]


def test_ordinary_checkout_metadata_is_excluded_from_staging_projection(
    tmp_path: Path,
) -> None:
    _project_layout(tmp_path)
    (tmp_path / ".git").write_text("gitdir: /outside", encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".cache", encoding="utf-8")
    (tmp_path / "README.md").write_text("ordinary checkout", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "design.md").write_text("metadata", encoding="utf-8")

    runner._validate_layout(tmp_path)
    fingerprint = runner._fingerprint(tmp_path)
    assert fingerprint["project"]
    assert runner._is_supported_input(Path("README.md")) is False
    assert runner._is_supported_input(Path(".git")) is False


def test_importable_target_types_are_harness_inputs(tmp_path: Path) -> None:
    _project_layout(tmp_path)
    helper = tmp_path / "target" / "types" / "generated.ts"
    helper.parent.mkdir(parents=True)
    helper.write_text("one", encoding="utf-8")
    first = runner._fingerprint(tmp_path)
    helper.write_text("two", encoding="utf-8")

    assert first["dependencies"] != runner._fingerprint(tmp_path)["dependencies"]


@pytest.mark.parametrize(
    "relative", ["programs/transfer-switch/helper.ts", "target/idl/helper.mjs"]
)
def test_unsupported_regular_files_do_not_enter_staging_projection(
    tmp_path: Path, relative: str
) -> None:
    _project_layout(tmp_path)
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    runner._validate_layout(tmp_path)
    assert runner._is_supported_input(Path(relative)) is False


def test_special_checkout_file_still_fails_closed(tmp_path: Path) -> None:
    _project_layout(tmp_path)
    os.mkfifo(tmp_path / "README.md")

    with pytest.raises(runner.IsolatedTestRefusal, match="unsafe_project_tree"):
        runner._validate_layout(tmp_path)


def test_directory_depth_limit_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _project_layout(tmp_path)
    monkeypatch.setattr(runner, "_MAX_DEPTH", 1)
    nested = tmp_path / "tests" / "nested"
    nested.mkdir()
    (nested / "helper.ts").write_text("", encoding="utf-8")

    with pytest.raises(runner.IsolatedTestRefusal, match="unsafe_project_tree"):
        runner._bounded_files(tmp_path)


@pytest.mark.parametrize(
    ("limit", "value"),
    [("_MAX_TOTAL_BYTES", 0), ("_MAX_DIRECTORIES", 1)],
)
def test_staged_tree_size_and_directory_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: str, value: int
) -> None:
    _project_layout(tmp_path)
    monkeypatch.setattr(runner, limit, value)

    with pytest.raises(runner.IsolatedTestRefusal, match="unsafe_project_tree"):
        runner._bounded_files(tmp_path)


def test_runner_readiness_requires_separate_status_and_preflight_descriptors(
    tmp_path: Path,
) -> None:
    command = runner._sandbox_command("/usr/bin/bwrap", tmp_path / "project", 17, 18)

    assert command[command.index("--json-status-fd") + 1] == "17"
    assert command[-1] == runner._runner_command(18)
    assert "printf 'ready\\n' >&18" in command[-1]


def test_memory_scope_requires_a_cgroup_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = runner._memory_limited_command("/usr/bin/systemd-run", ["/usr/bin/true"])

    assert command[:8] == [
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--quiet",
        "--collect",
        "--property=MemoryMax=" + str(runner._MEMORY_MAX_BYTES),
        "--property=MemorySwapMax=0",
        "--",
    ]

    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            command, 0, f"{runner._MEMORY_MAX_BYTES}\n0\n"
        ),
    )
    runner._verify_memory_limit("/usr/bin/systemd-run")


def test_memory_scope_failure_is_infrastructure_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, ""),
    )

    with pytest.raises(
        runner.IsolatedTestInfrastructureFailure, match="memory_limit_unavailable"
    ):
        runner._verify_memory_limit("/usr/bin/systemd-run")


def test_timeout_cleanup_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Process:
        pid = 123

        def wait(self, timeout: int) -> int:
            raise subprocess.TimeoutExpired("runner", timeout)

        def poll(self) -> None:
            return None

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    outcomes = iter(("failed", "ok"))
    monkeypatch.setattr(runner, "_terminate_process_group", lambda _: next(outcomes))

    with pytest.raises(RuntimeError, match="cleanup_failed"):
        runner._run_test_process(
            "/usr/bin/bwrap",
            "/usr/bin/systemd-run",
            tmp_path,
            tmp_path / "runner.log",
        )


def test_timeout_kills_all_scoped_sandbox_descendants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bwrap = runner.shutil.which("bwrap", path="/usr/bin:/bin")
    systemd_run = runner.shutil.which("systemd-run", path="/usr/bin:/bin")
    systemctl = runner.shutil.which("systemctl", path="/usr/bin:/bin")
    if (
        bwrap is None
        or systemd_run is None
        or systemctl is None
        or not runner._sandbox_is_available(bwrap)
    ):
        pytest.skip("required isolated runtime is unavailable")
    unit = f"beeagent-litesvm-timeout-{os.getpid()}-{time.monotonic_ns()}.scope"

    def scoped_command(executable: str, command: list[str]) -> list[str]:
        return [
            executable,
            "--user",
            "--scope",
            "--quiet",
            "--collect",
            "--unit=" + unit,
            "--property=MemoryMax=" + str(runner._MEMORY_MAX_BYTES),
            "--property=MemorySwapMax=0",
            "--",
            *command,
        ]

    monkeypatch.setattr(runner, "_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(runner, "_memory_limited_command", scoped_command)
    monkeypatch.setattr(
        runner,
        "_runner_command",
        lambda _descriptor, **_: "/usr/bin/sleep 30 & wait",
    )

    assert runner._run_test_process(
        bwrap, systemd_run, tmp_path, tmp_path / "runner.log"
    ) == (124, True, "ok")

    deadline = time.monotonic() + 5
    while True:
        completed = subprocess.run(
            [systemctl, "--user", "show", unit, "--property=ActiveState", "--value"],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if completed.returncode == 0 and completed.stdout.strip() == "inactive":
            break
        if time.monotonic() >= deadline:
            pytest.fail("sandbox scope retained a descendant after timeout cleanup")
        time.sleep(0.05)


def test_checkout_metadata_and_root_env_files_are_excluded(tmp_path: Path) -> None:
    _project_layout(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("private", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / ".env.local").write_text("SECRET=value", encoding="utf-8")

    assert runner._bounded_files(tmp_path)
    runner._validate_layout(tmp_path)


def test_nested_env_files_are_excluded_from_supported_inputs(tmp_path: Path) -> None:
    _project_layout(tmp_path)
    (tmp_path / "tests" / ".env").write_text("SECRET=value", encoding="utf-8")
    env_path = tmp_path / "node_modules" / "package" / ".env.local"
    env_path.parent.mkdir()
    env_path.write_text("SECRET=value", encoding="utf-8")

    assert runner._bounded_files(tmp_path)
    runner._validate_layout(tmp_path)


def test_staging_projection_excludes_nested_secret_directories(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "staged"
    source.mkdir()
    _project_layout(source)
    (source / ".git").mkdir()
    (source / ".git" / "config").write_text("private", encoding="utf-8")
    for relative in (
        "tests/.env/token",
        "tests/.env.local/token",
        "node_modules/package/.env/token",
        "node_modules/package/.env.local/token",
    ):
        secret = source / relative
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("SECRET=value", encoding="utf-8")

    runner._validate_layout(source)
    script = runner._STAGE_SCRIPT.replace("Path(\"/input\")", f"Path({str(source)!r})")
    script = script.replace(
        "Path(\"/workspace/project\")", f"Path({str(destination)!r})"
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(runner._MAX_TOTAL_BYTES),
            str(runner._MAX_FILE_BYTES),
            str(runner._MAX_FILES),
            str(runner._MAX_DIRECTORIES),
            str(runner._MAX_DEPTH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (destination / "tests" / "litesvm.test.ts").is_file()
    assert not (destination / ".git").exists()
    assert not (destination / "tests" / ".env").exists()
    assert not (destination / "tests" / ".env.local").exists()
    assert not (destination / "node_modules" / "package" / ".env").exists()
    assert not (destination / "node_modules" / "package" / ".env.local").exists()


def test_host_selected_node_is_used_inside_the_fixed_runner(tmp_path: Path) -> None:
    command = runner._sandbox_command(
        "/usr/bin/bwrap", tmp_path / "project", node="/bin/node"
    )

    assert "/bin/node" in command
    assert "/bin/node" in runner._runner_command(18, node="/bin/node")
    assert "--reporter json" in runner._runner_command(18, node="/bin/node")


def test_staging_reads_input_through_pinned_no_follow_descriptors() -> None:
    assert "os.O_NOFOLLOW" in runner._STAGE_SCRIPT
    assert "dir_fd=parent_fd" in runner._STAGE_SCRIPT
    assert "os.fstat(descriptor)" in runner._STAGE_SCRIPT
    assert "os.fdopen(os.dup(descriptor), \"rb\")" in runner._STAGE_SCRIPT
    assert "inode_changed" in runner._STAGE_SCRIPT


@pytest.mark.parametrize(
    ("output", "exit_code", "expected"),
    [
        (b'{"stats":{"tests":2,"failures":0}}', 0, 2),
        (b'{"stats":{"tests":2,"failures":1}}', 1, 2),
        (b'{"stats":{"tests":2,"failures":1}}', 0, 0),
        (b'{"stats":{"tests":2,"failures":0}}', 1, 0),
        (b'{"stats":{"tests":0,"failures":0}}', 0, 0),
        (b'{"stats":{"tests":1000000001,"failures":0}}', 0, 0),
        (b'{"stats":{"tests":true,"failures":0}}', 0, 0),
        (b'{"stats":{"tests":1,"failures":-1}}', 1, 0),
        (b"not-json", 0, 0),
    ],
)
def test_completed_test_count_requires_a_nonempty_json_report(
    output: bytes, exit_code: int, expected: int
) -> None:
    assert runner._completed_test_count(output, exit_code) == expected


def test_completed_test_count_rejects_bounded_malformed_bytes() -> None:
    for value in range(256):
        assert runner._completed_test_count(bytes([value]) * 64, 0) == 0
    output = b'{"stats":{"tests":' + b"9" * 5000 + b"}}"
    assert runner._completed_test_count(output, 0) == 0


def _project_layout(root: Path) -> None:
    (root / "tests").mkdir()
    (root / "node_modules" / "mocha" / "bin").mkdir(parents=True)
    (root / "node_modules" / "tsx" / "dist").mkdir(parents=True)
    (root / "package.json").write_text("{}", encoding="utf-8")
    (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'", encoding="utf-8")
    (root / "tests" / "litesvm.test.ts").write_text("", encoding="utf-8")
    (root / "node_modules" / "mocha" / "bin" / "mocha.js").write_text(
        "", encoding="utf-8"
    )
    (root / "node_modules" / "tsx" / "dist" / "loader.mjs").write_text(
        "", encoding="utf-8"
    )
