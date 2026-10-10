from __future__ import annotations

import os
import subprocess
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


def test_unclassified_project_input_fails_closed(tmp_path: Path) -> None:
    _project_layout(tmp_path)
    (tmp_path / "unverified").mkdir()
    (tmp_path / "unverified" / "input.js").write_text("", encoding="utf-8")

    with pytest.raises(runner.IsolatedTestRefusal, match="unsupported_layout"):
        runner._validate_layout(tmp_path)


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
def test_unsupported_target_harness_file_fails_closed(
    tmp_path: Path, relative: str
) -> None:
    _project_layout(tmp_path)
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("", encoding="utf-8")

    with pytest.raises(runner.IsolatedTestRefusal, match="unsupported_layout"):
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
        lambda _descriptor: "/usr/bin/sleep 30 & wait",
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
