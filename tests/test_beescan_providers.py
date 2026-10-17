import hashlib
import io
import os
import stat
import subprocess
import threading
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.client import HTTPMessage
from typing import cast

import pytest

from beeagent_module.core import beedrill_toolchain as download
from beeagent_module.core import beescan_providers as native


@pytest.fixture
def distribution(tmp_path, monkeypatch):
    content = b"pinned-provider-test-bytes"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("nuclei", content)
    archive = buffer.getvalue()
    artifact = replace(
        native.NUCLEI_ARTIFACT,
        size=len(archive),
        sha256=hashlib.sha256(archive).hexdigest(),
    )
    root = tmp_path / "providers"
    monkeypatch.setattr(native, "NUCLEI_ARTIFACT", artifact)
    monkeypatch.setattr(native, "NUCLEI_SHA256", hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(native, "NUCLEI_BYTES", len(content))
    monkeypatch.setattr(native, "HTTPX_SHA256", hashlib.sha256(content).hexdigest())
    monkeypatch.setattr(native, "HTTPX_BYTES", len(content))
    monkeypatch.setattr(native, "provider_root", lambda: root)
    monkeypatch.setattr(native.platform, "system", lambda: "Linux")
    monkeypatch.setattr(native.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        native, "_download", lambda selected, path: path.write_bytes(archive)
    )
    monkeypatch.setattr(
        subprocess, "Popen", lambda *_a, **_k: pytest.fail("execution forbidden")
    )
    settings = {
        "modules": {"registry": [{"id": "beescan", "enabled": True}]},
        "beescan": {
            "probe_enabled": False,
            "approval": None,
            "detection_enabled": True,
            "detection_approval": {"executable": str(root / "nuclei")},
        },
    }
    return root, settings, content, archive


def test_clean_install_and_warm_offline_startup(distribution, monkeypatch):
    root, settings, content, _ = distribution
    native.ensure_beescan_providers(settings)
    binary = root / "nuclei"
    assert binary.read_bytes() == content
    assert stat.S_IMODE(binary.stat().st_mode) == 0o555
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE((root / ".bootstrap.lock").stat().st_mode) == 0o600
    before = binary.stat().st_mtime_ns
    monkeypatch.setattr(
        native, "_download", lambda *_: pytest.fail("download forbidden")
    )
    native.ensure_beescan_providers(settings)
    assert binary.stat().st_mtime_ns == before
    assert sorted(path.name for path in root.iterdir()) == [
        ".bootstrap.lock",
        "nuclei",
    ]


@pytest.mark.parametrize("disabled", ["module", "providers"])
def test_disabled_does_not_create_cache_or_download(
    distribution, monkeypatch, disabled
):
    root, settings, _, _ = distribution
    if disabled == "module":
        settings["modules"]["registry"][0]["enabled"] = False
    else:
        settings["beescan"]["detection_enabled"] = False
    monkeypatch.setattr(
        native, "_download", lambda *_: pytest.fail("download forbidden")
    )
    monkeypatch.setattr(native.platform, "system", lambda: "Unsupported")
    native.ensure_beescan_providers(settings)
    assert not root.exists()


@pytest.mark.parametrize("selected", ["httpx", "nuclei", "both"])
def test_only_selected_providers_are_prepared(distribution, monkeypatch, selected):
    root, settings, content, _ = distribution
    if selected in {"httpx", "both"}:
        root.mkdir(mode=0o700)
        (root / "httpx").write_bytes(content)
        (root / "httpx").chmod(0o555)
        settings["beescan"].update(
            probe_enabled=True, approval={"executable": str(root / "httpx")}
        )
    if selected == "httpx":
        settings["beescan"]["detection_enabled"] = False
        monkeypatch.setattr(native, "_download", lambda *_: pytest.fail("not selected"))
    native.ensure_beescan_providers(settings)
    assert (root / "nuclei").exists() == (selected != "httpx")
    assert (root / "httpx").exists() == (selected != "nuclei")


@pytest.mark.parametrize("name", ["httpx", "nuclei"])
def test_custom_verified_path_is_preserved(distribution, monkeypatch, name):
    root, settings, content, _ = distribution
    custom = root.parent / "operator-binary"
    custom.write_bytes(content)
    custom.chmod(0o555)
    before = custom.stat()
    settings["beescan"] = {
        "probe_enabled": name == "httpx",
        "approval": {"executable": str(custom)},
        "detection_enabled": name == "nuclei",
        "detection_approval": {"executable": str(custom)},
    }
    monkeypatch.setattr(native, "_download", lambda *_: pytest.fail("custom path"))
    native.ensure_beescan_providers(settings)
    assert custom.stat() == before
    assert not (root / name).exists()


@pytest.mark.parametrize("name", ["httpx", "nuclei"])
def test_missing_custom_path_never_installs_there(distribution, name):
    root, settings, _, _ = distribution
    custom = root.parent / "missing-custom"
    settings["beescan"] = {
        "probe_enabled": name == "httpx",
        "approval": {"executable": str(custom)},
        "detection_enabled": name == "nuclei",
        "detection_approval": {"executable": str(custom)},
    }
    with pytest.raises(native.ProviderProvisioningError):
        native.ensure_beescan_providers(settings)
    assert not custom.exists()
    assert not (root / name).exists()


def test_missing_httpx_reports_exact_distribution_blocker(distribution):
    root, settings, _, _ = distribution
    settings["beescan"].update(
        probe_enabled=True, approval={"executable": str(root / "httpx")}
    )
    with pytest.raises(
        native.ProviderProvisioningError, match="distribution unavailable"
    ) as error:
        native.ensure_beescan_providers(settings)
    assert native.HTTPX_SHA256 in str(error.value)
    assert (root / "nuclei").is_file()
    assert not (root / "httpx").exists()


@pytest.mark.parametrize("mutation", ["bytes", "mode", "symlink", "directory", "fifo"])
def test_modified_provider_fails_without_replacement(
    distribution, monkeypatch, mutation
):
    root, settings, _, _ = distribution
    native.ensure_beescan_providers(settings)
    binary = root / "nuclei"
    if mutation == "bytes":
        binary.chmod(0o600)
        binary.write_bytes(b"corrupt")
        binary.chmod(0o555)
    elif mutation == "mode":
        binary.chmod(0o777)
    else:
        binary.unlink()
        if mutation == "symlink":
            binary.symlink_to(root / "outside")
        elif mutation == "directory":
            binary.mkdir()
        else:
            os.mkfifo(binary)
    before = binary.lstat()
    monkeypatch.setattr(native, "_download", lambda *_: pytest.fail("repair forbidden"))
    with pytest.raises(native.ProviderProvisioningError):
        native.ensure_beescan_providers(settings)
    assert binary.lstat() == before


@pytest.mark.parametrize(
    "failure", ["archive_hash", "binary_hash", "download", "timeout", "disk"]
)
def test_failed_install_is_atomic_and_cleans_temporary_files(
    distribution, monkeypatch, failure
):
    root, settings, _, archive = distribution
    if failure == "binary_hash":
        monkeypatch.setattr(native, "NUCLEI_SHA256", "0" * 64)
    elif failure == "archive_hash":
        monkeypatch.setattr(
            native, "_download", lambda _, path: path.write_bytes(b"bad")
        )
    else:
        error = {
            "download": urllib.error.URLError("unavailable"),
            "timeout": TimeoutError("timeout"),
            "disk": OSError("full disk"),
        }[failure]

        def failed_download(_, path):
            path.write_bytes(archive[:5])
            raise error

        monkeypatch.setattr(native, "_download", failed_download)
    with pytest.raises(native.ProviderProvisioningError):
        native.ensure_beescan_providers(settings)
    assert [path.name for path in root.iterdir()] == [".bootstrap.lock"]


@pytest.mark.parametrize("field,value", [("system", "Darwin"), ("machine", "aarch64")])
def test_unsupported_host_is_rejected_before_writing(
    distribution, monkeypatch, field, value
):
    root, settings, _, _ = distribution
    monkeypatch.setattr(native.platform, field, lambda: value)
    with pytest.raises(native.ProviderProvisioningError, match="Linux x86_64"):
        native.ensure_beescan_providers(settings)
    assert not root.exists()


@pytest.mark.parametrize("entry", ["root", "parent", "lock", "lock_mode", "root_mode"])
def test_unsafe_managed_paths_are_rejected(distribution, monkeypatch, entry):
    root, settings, _, _ = distribution
    outside = root.parent / "outside"
    outside.mkdir()
    if entry == "root":
        root.symlink_to(outside, target_is_directory=True)
    elif entry == "parent":
        link = root.parent / "link"
        link.symlink_to(outside, target_is_directory=True)
        monkeypatch.setattr(native, "provider_root", lambda: link / "providers")
    else:
        root.mkdir(mode=0o700)
        if entry == "lock":
            (root / ".bootstrap.lock").symlink_to(outside / "lock")
        elif entry == "lock_mode":
            (root / ".bootstrap.lock").touch(mode=0o666)
            (root / ".bootstrap.lock").chmod(0o666)
        else:
            root.chmod(0o777)
    monkeypatch.setattr(native, "_download", lambda *_: pytest.fail("unsafe path"))
    with pytest.raises(native.ProviderProvisioningError):
        native.ensure_beescan_providers(settings)
    assert not list(outside.iterdir())


def test_concurrent_bootstrap_installs_once(distribution, monkeypatch):
    root, settings, content, archive = distribution
    calls = []
    barrier = threading.Barrier(2)

    def fetch(_, target):
        calls.append(target)
        target.write_bytes(archive)

    def bootstrap():
        barrier.wait(timeout=5)
        native.ensure_beescan_providers(settings)

    monkeypatch.setattr(native, "_download", fetch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(bootstrap) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    assert len(calls) == 1
    assert (root / "nuclei").read_bytes() == content


@pytest.mark.parametrize("payload", [b"", b"wrong", b"x" * 1024])
def test_bounded_downloader_rejects_unverified_bytes(tmp_path, monkeypatch, payload):
    class Response(io.BytesIO):
        pass

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == native.NUCLEI_ARTIFACT.url
            assert timeout == 30
            return Response(payload)

    monkeypatch.setattr(download.urllib.request, "build_opener", lambda *_: Opener())
    artifact = replace(native.NUCLEI_ARTIFACT, size=10)
    with pytest.raises(download.NativeToolchainError):
        download._download(artifact, tmp_path / "download")


@pytest.mark.parametrize(
    "url", ["http://github.com/x", "https://evil.test/x", "file:///tmp/x"]
)
def test_downloader_rejects_untrusted_redirects(url):
    handler = download._OfficialRedirect()
    with pytest.raises(download.NativeToolchainError):
        handler.redirect_request(
            urllib.request.Request(native.NUCLEI_ARTIFACT.url),
            io.BytesIO(),
            302,
            "redirect",
            HTTPMessage(),
            url,
        )


@pytest.mark.parametrize("provider", ["probe", "detection"])
def test_missing_runtime_prerequisite_remains_fail_closed(monkeypatch, provider):
    from pathlib import Path

    from beeagent_module.core.beescan_detection_policy import DetectionPolicy
    from beeagent_module.core.beescan_detection_runner import run_detection_provider
    from beeagent_module.core.beescan_http_runner import run_provider
    from beeagent_module.core.beescan_policy import ProbePolicy

    original = Path.stat

    def missing(path, *args, **kwargs):
        if str(path) == "/usr/bin/nsenter":
            raise FileNotFoundError("missing prerequisite")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", missing)
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: pytest.fail("execution"))
    from types import SimpleNamespace

    policy = SimpleNamespace(time_budget_seconds=5)
    with pytest.raises(PermissionError, match="isolation_unavailable"):
        if provider == "probe":
            run_provider(
                cast(ProbePolicy, policy),
                reauthorize=lambda: pytest.fail("authorization"),
            )
        else:
            run_detection_provider(
                cast(DetectionPolicy, policy),
                reauthorize=lambda: pytest.fail("authorization"),
            )


def test_bootstrap_lock_timeout_is_bounded(distribution, monkeypatch):
    import fcntl

    root, settings, _, _ = distribution
    elapsed = 0

    def now():
        nonlocal elapsed
        elapsed += 61
        return elapsed

    def busy(*_):
        raise BlockingIOError

    monkeypatch.setattr(fcntl, "flock", busy)
    monkeypatch.setattr(native.time, "monotonic", now)
    with pytest.raises(native.ProviderProvisioningError, match="lock timed out"):
        native.ensure_beescan_providers(settings)
    assert not (root / "nuclei").exists()
