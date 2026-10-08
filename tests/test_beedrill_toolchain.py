import io
import json
import logging
import subprocess
import sys
import tarfile
import urllib.error
from dataclasses import replace
from pathlib import Path

import pytest

import beeagent_module.core.beedrill_toolchain as native
import beeagent_module.core.isolated_solana_capability as host

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import start


@pytest.fixture
def small_distribution(tmp_path, monkeypatch):
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as bundle:
        member = tarfile.TarInfo("surfpool")
        content = b"verified-test-binary"
        member.size = len(content)
        member.mode = 0o755
        bundle.addfile(member, io.BytesIO(content))
    artifact = replace(
        native.NATIVE_ARTIFACTS[0],
        size=archive.stat().st_size,
        sha256=native._digest(archive),
    )
    monkeypatch.setattr(native, "NATIVE_ARTIFACTS", (artifact,))
    monkeypatch.setattr(native.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(native.platform, "libc_ver", lambda: ("glibc", "2.39"))
    return archive, artifact, tmp_path / "managed"


def test_first_bootstrap_and_repeated_offline_reuse(small_distribution, monkeypatch):
    archive, artifact, root = small_distribution
    downloads = []
    probes = []

    def download(selected, destination):
        downloads.append(selected)
        destination.write_bytes(archive.read_bytes())

    def probe(command, **kwargs):
        probes.append(kwargs)
        return subprocess.CompletedProcess(command, 0, b"surfpool 1.5.0\n", b"")

    monkeypatch.setattr(native, "_download", download)
    monkeypatch.setattr(native.subprocess, "run", probe)
    native.ensure_native_tools(needs_sbf=False, root=root)
    before = {
        path.relative_to(root): path.stat().st_mtime_ns
        for path in root.rglob("*")
        if path.is_file() and path.name != ".bootstrap.lock"
    }
    native.ensure_native_tools(needs_sbf=False, root=root)
    after = {
        path.relative_to(root): path.stat().st_mtime_ns
        for path in root.rglob("*")
        if path.is_file() and path.name != ".bootstrap.lock"
    }
    assert before == after
    assert downloads == [artifact]
    assert len(probes) == 2
    assert all(probe["env"] == native.native_environment(root) for probe in probes)
    marker = json.loads(
        (root / artifact.destination / ".beeagent-provenance.json").read_text()
    )
    assert marker["url"] == artifact.url
    assert marker["sha256"] == artifact.sha256


@pytest.mark.parametrize(
    "field,value",
    [("system", "Darwin"), ("machine", "aarch64"), ("libc_ver", ("musl", "1.2"))],
)
def test_unsupported_platform_does_not_download_or_write(
    tmp_path, monkeypatch, field, value
):
    monkeypatch.setattr(native.platform, field, lambda: value)
    root = tmp_path / "managed"
    monkeypatch.setattr(
        native, "_download", lambda *_: pytest.fail("download forbidden")
    )
    with pytest.raises(native.NativeToolchainError) as error:
        native.ensure_native_tools(needs_sbf=True, root=root)
    assert error.value.reason == "incompatible_toolchain"
    assert not root.exists()


@pytest.mark.parametrize(
    "name,kind,link",
    [
        ("../escaped", tarfile.REGTYPE, ""),
        ("/tmp/escaped", tarfile.REGTYPE, ""),
        ("link", tarfile.SYMTYPE, "../../escaped"),
        ("link", tarfile.LNKTYPE, "../../escaped"),
        ("device", tarfile.CHRTYPE, ""),
    ],
)
def test_archive_traversal_links_and_devices_are_rejected(tmp_path, name, kind, link):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as bundle:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = link
        bundle.addfile(member)
    with pytest.raises(tarfile.TarError):
        native._extract(archive, tmp_path / "destination")
    assert not (tmp_path / "escaped").exists()


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/tool",
        "https://evil.example/tool",
        "https://user:secret@github.com/tool",
        "https://github.com:444/tool",
        "file:///bin/tool",
    ],
)
def test_artifact_egress_rejects_unofficial_destinations(url):
    assert not native._official_url(url)


def test_corrupt_download_cache_never_executes(small_distribution, monkeypatch):
    _, artifact, root = small_distribution
    (root / "downloads").mkdir(parents=True)
    (root / "downloads" / f"{artifact.name}.tar").write_bytes(b"corrupt-secret")
    monkeypatch.setattr(
        native.subprocess, "run", lambda *_a, **_k: pytest.fail("execution forbidden")
    )
    with pytest.raises(native.NativeToolchainError) as error:
        native.ensure_native_tools(needs_sbf=False, root=root)
    assert error.value.reason == "incompatible_toolchain"
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "exception,reason",
    [
        (OSError("sentinel-secret"), "missing_surfpool"),
        (TimeoutError("sentinel-secret"), "timeout"),
        (urllib.error.URLError(TimeoutError("sentinel-secret")), "timeout"),
        (urllib.error.URLError("sentinel-secret"), "missing_surfpool"),
    ],
)
def test_download_failures_are_bounded(
    small_distribution, monkeypatch, exception, reason
):
    _, _, root = small_distribution

    def fail(*_):
        raise exception

    monkeypatch.setattr(native, "_download", fail)
    with pytest.raises(native.NativeToolchainError) as error:
        native.ensure_native_tools(needs_sbf=False, root=root)
    assert error.value.reason == reason
    assert "sentinel-secret" not in str(error.value)
    assert not list(root.glob("download-*"))
    assert not list(root.glob("extract-*"))


@pytest.mark.parametrize("entry", ["downloads", ".bootstrap.lock"])
def test_redirected_cache_entries_do_not_write_outside_root(
    small_distribution, monkeypatch, tmp_path, entry
):
    _, _, root = small_distribution
    root.mkdir()
    outside = tmp_path / "outside"
    if entry == "downloads":
        outside.mkdir()
    else:
        outside.write_bytes(b"unchanged")
    (root / entry).symlink_to(outside)
    monkeypatch.setattr(
        native, "_download", lambda *_: pytest.fail("download forbidden")
    )
    with pytest.raises(native.NativeToolchainError) as error:
        native.ensure_native_tools(needs_sbf=False, root=root)
    assert error.value.reason == "incompatible_toolchain"
    if outside.is_dir():
        assert not list(outside.iterdir())
    else:
        assert outside.read_bytes() == b"unchanged"


@pytest.mark.parametrize("compiler_status", [None, 1])
def test_host_linker_failure_is_actionable_without_system_installation(
    small_distribution, monkeypatch, compiler_status
):
    _, _, root = small_distribution
    monkeypatch.setattr(native, "_install", lambda *_: None)
    monkeypatch.setattr(
        native.shutil, "which", lambda *_a, **_k: compiler_status and "/usr/bin/cc"
    )

    def probe(command, **kwargs):
        if "--version" in command:
            name = Path(command[0]).name
            versions = {
                "surfpool": "surfpool 1.5.0",
                "solana": "solana-cli 4.2.2",
                "cargo-build-sbf": "cargo-build-sbf 4.1.0",
                "cargo": "cargo 1.89.0",
                "rustc": "rustc 1.89.0",
            }
            return subprocess.CompletedProcess(command, 0, versions[name].encode(), b"")
        assert command[0] == "/usr/bin/cc"
        assert kwargs["env"] == native.native_environment(root)
        return subprocess.CompletedProcess(
            command, compiler_status, b"", b"sentinel-secret"
        )

    monkeypatch.setattr(native.subprocess, "run", probe)
    with pytest.raises(native.NativeToolchainError) as error:
        native.ensure_native_tools(needs_sbf=True, root=root)
    assert error.value.reason == "incompatible_toolchain"
    assert "development" in str(error.value)
    assert "sentinel-secret" not in str(error.value)


def test_host_resolution_ignores_interactive_path(monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path))
    malicious = tmp_path / "surfpool"
    malicious.write_text("unexpected")
    malicious.chmod(0o755)
    seen = []

    def which(name, *, path):
        seen.append(path)

    monkeypatch.setattr(host.shutil, "which", which)
    from beeagent_module.core.module_contract import AuthorityLevel

    caller = host.ScopedSolanaLifecycleCaller(
        "run-1",
        "session-1",
        "beedrill",
        "spl_token_freeze_containment_replay",
        AuthorityLevel.READ_ONLY,
        logging.getLogger("test"),
    )
    result = caller.call(
        "solana.spl_token_freeze_containment",
        {
            "target_profile": "surfpool_local",
            "target_id": "spl_token_freeze_containment",
            "defense_condition": "fixed",
        },
    )
    assert result.diagnostics == {"reason": "missing_surfpool"}
    assert seen == [native.native_environment()["PATH"]]
    assert str(tmp_path) not in seen[0]


@pytest.mark.parametrize(
    "command,needs_sbf",
    [
        (["check"], True),
        (["run", "--scenario", "reference_target_containment_replay"], True),
        (["run", "--scenario", "spl_token_freeze_containment_replay"], False),
    ],
)
def test_cli_bootstrap_failure_is_incomplete_without_execution(
    monkeypatch, capsys, tmp_path, command, needs_sbf
):
    requirements = []

    def prepare(*, needs_sbf):
        requirements.append(needs_sbf)
        raise native.NativeToolchainError("missing_cargo", "Retry native preparation.")

    monkeypatch.setattr(start, "ensure_native_tools", prepare)
    monkeypatch.setattr(start, "build_registry", lambda *_: object())
    monkeypatch.setattr(start, "get_storage_dir", lambda: tmp_path)
    monkeypatch.setattr(
        start, "execute_module_case", lambda **_: pytest.fail("suite must not execute")
    )
    result = start._handle_beedrill_cli(
        command,
        {"modules": {"registry": [{"id": "beedrill", "enabled": True}]}},
        logging.getLogger("test"),
    )
    assert result == 3
    assert requirements == [needs_sbf]
    captured = capsys.readouterr()
    assert "INCOMPLETE" in captured.err
    assert "Retry native preparation" in captured.err


def test_unrelated_and_invalid_cli_do_not_provision(monkeypatch, capsys):
    monkeypatch.setattr(
        start, "ensure_native_tools", lambda **_: pytest.fail("provisioning forbidden")
    )
    assert (
        start._handle_beedrill_cli(
            ["check", "--target", "evil"], {}, logging.getLogger("test")
        )
        == 2
    )
    assert (
        start._handle_beedrill_cli(
            ["run", "--scenario", "evil"], {}, logging.getLogger("test")
        )
        == 2
    )


def test_real_command_timeout_kills_builder_descendants(monkeypatch, tmp_path):
    monkeypatch.setattr(host, "_BUILD_TIMEOUT_SECONDS", 1)
    pid_file = tmp_path / "child-pid"
    code = (
        "import os, time; from pathlib import Path; pid = os.fork(); "
        f"Path({str(pid_file)!r}).write_text(str(os.getpid())) if pid == 0 else None; "
        "time.sleep(30)"
    )
    with pytest.raises(host._ReferenceTargetTimeout, match="build_timeout"):
        host._run_target_command([sys.executable, "-c", code], "build")
    child_pid = int(pid_file.read_text())
    state = Path(f"/proc/{child_pid}/stat")
    assert not state.exists() or state.read_text().split()[2] == "Z"


def test_command_cleanup_failure_is_explicit(monkeypatch):
    class Process:
        pid = 12345

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("bounded-command", timeout)

    monkeypatch.setattr(host.subprocess, "Popen", lambda *_a, **_k: Process())

    def denied(*_):
        raise PermissionError("sentinel-secret")

    monkeypatch.setattr(host.os, "killpg", denied)
    with pytest.raises(host._ReferenceTargetFailure, match="^cleanup_failed$"):
        host._run_target_command(["/fixed-command"], "build")
