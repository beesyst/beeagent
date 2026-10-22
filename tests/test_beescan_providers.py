import copy
import hashlib
import io
import os
import stat
import subprocess
import tarfile
import threading
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from http.client import HTTPMessage
from types import SimpleNamespace
from typing import cast

import pytest

from beeagent_module.core import beedrill_toolchain as download
from beeagent_module.integrations.beescan import providers as native


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
    after = custom.stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_mode) == (
        before.st_ino,
        before.st_mtime_ns,
        before.st_mode,
    )
    assert custom.read_bytes() == content
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

    from beeagent_module.integrations.beescan.detection_policy import DetectionPolicy
    from beeagent_module.integrations.beescan.detection_runner import (
        run_detection_provider,
    )
    from beeagent_module.integrations.beescan.http_runner import run_provider
    from beeagent_module.integrations.beescan.policy import ProbePolicy

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


@pytest.fixture
def pasta_distribution(distribution, monkeypatch):
    root, settings, content, _ = distribution
    package = b"p" * native.PASTA_ARTIFACT.size
    binary = b"x" * 277704
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as bundle:
        member = tarfile.TarInfo("./usr/bin/passt")
        member.size = len(binary)
        bundle.addfile(member, io.BytesIO(binary))
    monkeypatch.setattr(
        native,
        "PASTA_ARTIFACT",
        replace(native.PASTA_ARTIFACT, sha256=hashlib.sha256(package).hexdigest()),
    )
    monkeypatch.setattr(native.egress, "PACKAGE_SHA256", native.PASTA_ARTIFACT.sha256)
    monkeypatch.setattr(
        native.egress, "PASTA_SHA256", hashlib.sha256(binary).hexdigest()
    )
    monkeypatch.setattr(native.platform, "libc_ver", lambda: ("glibc", "2.38"))
    root.mkdir(mode=0o700)
    (root / "httpx").write_bytes(content)
    (root / "httpx").chmod(0o555)
    settings["beescan"].update(
        probe_enabled=True, approval={"executable": str(root / "httpx")}
    )
    for key in ("approval", "detection_approval"):
        settings["beescan"][key].update(
            network_namespace=native.egress.MANAGED_NET,
            user_namespace=native.egress.MANAGED_USER,
        )
    calls = []

    class Response(io.BytesIO):
        def geturl(self):
            return native.PASTA_ARTIFACT.url

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == native.PASTA_ARTIFACT.url
            assert timeout == 10
            calls.append(request.full_url)
            return Response(package)

    monkeypatch.setattr(native.urllib.request, "build_opener", lambda *_: Opener())

    def extract(command, **kwargs):
        assert command[:2] == ["/usr/bin/dpkg-deb", "--fsys-tarfile"]
        assert kwargs["timeout"] == 5 and kwargs["check"]
        return SimpleNamespace(stdout=archive.getvalue())

    monkeypatch.setattr(subprocess, "run", extract)
    return root, settings, package, binary, calls


def test_managed_cold_and_offline_warm_bootstrap(pasta_distribution, monkeypatch):
    root, settings, _, binary, calls = pasta_distribution
    original = copy.deepcopy(settings)
    native.ensure_beescan_providers(settings)
    assert calls == [native.PASTA_ARTIFACT.url]
    assert (root / "pasta").read_bytes() == binary
    assert stat.S_IMODE((root / "pasta").stat().st_mode) == 0o500
    assert (root / "nuclei").is_file()
    before = (root / "pasta").stat()
    monkeypatch.setattr(
        native, "_download_pasta", lambda *_: pytest.fail("warm network forbidden")
    )
    native.ensure_beescan_providers(settings)
    after = (root / "pasta").stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_mode) == (
        before.st_ino,
        before.st_mtime_ns,
        before.st_mode,
    )
    assert (root / "pasta").read_bytes() == binary
    assert settings == original
    assert sorted(p.name for p in root.iterdir()) == [
        ".bootstrap.lock",
        "httpx",
        "nuclei",
        "pasta",
    ]


@pytest.mark.parametrize(
    "selection", ["disabled", "probe_only", "detection_only", "legacy", "mixed", "git"]
)
def test_unselected_managed_helper_is_not_provisioned(pasta_distribution, selection):
    root, settings, _, _, calls = pasta_distribution
    config = settings["beescan"]
    if selection == "disabled":
        settings["modules"]["registry"][0]["enabled"] = False
    elif selection == "probe_only":
        config["detection_enabled"] = False
    elif selection == "detection_only":
        config["probe_enabled"] = False
    elif selection == "git":
        config.update(git_exposure_enabled=True, git_exposure_approval=None)
    else:
        for key in (
            ("approval", "detection_approval")
            if selection == "legacy"
            else ("approval",)
        ):
            config[key].update(
                network_namespace="/proc/123/ns/net", user_namespace="/proc/123/ns/user"
            )
    before = (root / "httpx").stat()
    native.ensure_beescan_providers(settings)
    assert not calls and not (root / "pasta").exists()
    after = (root / "httpx").stat()
    assert (after.st_ino, after.st_mtime_ns, after.st_mode) == (
        before.st_ino,
        before.st_mtime_ns,
        before.st_mode,
    )
    if selection == "disabled":
        assert sorted(p.name for p in root.iterdir()) == ["httpx"]


@pytest.mark.parametrize("mutation", ["bytes", "mode", "symlink", "fifo", "directory"])
def test_existing_pasta_is_never_silently_replaced(pasta_distribution, mutation):
    root, settings, _, binary, calls = pasta_distribution
    path = root / "pasta"
    if mutation == "symlink":
        path.symlink_to(root / "missing")
    elif mutation == "fifo":
        os.mkfifo(path)
    elif mutation == "directory":
        path.mkdir()
    else:
        path.write_bytes(binary if mutation == "mode" else b"bad")
        path.chmod(0o777 if mutation == "mode" else 0o500)
    before = path.lstat()
    with pytest.raises(native.ProviderProvisioningError):
        native.ensure_beescan_providers(settings)
    assert path.lstat() == before and not calls


@pytest.mark.parametrize(
    "failure", ["size", "digest", "interrupt", "extraction", "binary"]
)
def test_pasta_failure_cleans_private_temporary_files(
    pasta_distribution, monkeypatch, failure
):
    root, settings, package, _, _ = pasta_distribution
    if failure in {"size", "digest", "interrupt"}:

        def fetch(target):
            target.write_bytes(
                package[:-1] if failure == "size" else b"z" * len(package)
            )
            if failure == "interrupt":
                raise KeyboardInterrupt

        monkeypatch.setattr(native, "_download_pasta", fetch)
    elif failure == "extraction":
        monkeypatch.setattr(
            subprocess, "run", lambda *_a, **_k: SimpleNamespace(stdout=b"partial tar")
        )
    else:
        monkeypatch.setattr(native.egress, "PASTA_SHA256", "0" * 64)
    error = (
        KeyboardInterrupt
        if failure == "interrupt"
        else native.ProviderProvisioningError
    )
    with pytest.raises(error):
        native.ensure_beescan_providers(settings)
    assert not (root / "pasta").exists()
    assert sorted(p.name for p in root.iterdir()) == [".bootstrap.lock", "httpx"]


def test_concurrent_managed_bootstrap_installs_once(pasta_distribution):
    root, settings, _, binary, calls = pasta_distribution
    barrier = threading.Barrier(2)

    def bootstrap():
        barrier.wait(timeout=5)
        native.ensure_beescan_providers(settings)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(bootstrap) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    assert calls == [native.PASTA_ARTIFACT.url]
    assert (root / "pasta").read_bytes() == binary


@pytest.mark.parametrize(
    "url",
    [
        "https://archive.ubuntu.com/other",
        "http://archive.ubuntu.com/x",
        "https://evil.test/x",
    ],
)
def test_pasta_rejects_every_redirect(url):
    with pytest.raises(native.ProviderProvisioningError, match="must not redirect"):
        native._PastaRedirect().redirect_request(
            urllib.request.Request(native.PASTA_ARTIFACT.url),
            io.BytesIO(),
            302,
            "redirect",
            HTTPMessage(),
            url,
        )


@pytest.mark.parametrize("payload", [b"", b"short", b"z" * 259676, b"x" * 259677])
def test_pasta_download_rejects_wrong_size_or_digest(tmp_path, monkeypatch, payload):
    class Response(io.BytesIO):
        def geturl(self):
            return native.PASTA_ARTIFACT.url

    class Opener:
        def open(self, *_a, **_k):
            return Response(payload)

    monkeypatch.setattr(native.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(native.ProviderProvisioningError):
        native._download_pasta(tmp_path / "package.deb")


def test_pasta_uses_system_tls_and_no_proxy(pasta_distribution, monkeypatch):
    import ssl

    root, settings, _, _, _ = pasta_distribution
    original = native.urllib.request.build_opener

    def opener(*handlers):
        proxy, https, redirects = handlers
        assert proxy.proxies == {}
        assert https._context.check_hostname
        assert https._context.verify_mode == ssl.CERT_REQUIRED
        assert isinstance(redirects, native._PastaRedirect)
        return original(*handlers)

    monkeypatch.setattr(native.urllib.request, "build_opener", opener)
    native.ensure_beescan_providers(settings)
    assert (root / "pasta").exists()


def test_pasta_download_deadline_and_socket_failure(pasta_distribution, monkeypatch):
    root, settings, _, _, calls = pasta_distribution
    now = iter([0, 0, 31])
    monkeypatch.setattr(native.time, "monotonic", lambda: next(now))
    with pytest.raises(native.ProviderProvisioningError, match="timed out"):
        native.ensure_beescan_providers(settings)
    assert calls and not (root / "pasta").exists()


@pytest.mark.parametrize("libc,version", [("glibc", "2.37"), ("musl", "1.2")])
def test_managed_incompatible_libc_refuses_without_download(
    pasta_distribution, monkeypatch, libc, version
):
    root, settings, _, _, calls = pasta_distribution
    monkeypatch.setattr(native.platform, "libc_ver", lambda: (libc, version))
    with pytest.raises(native.ProviderProvisioningError, match="glibc 2.38"):
        native.ensure_beescan_providers(settings)
    assert not calls and not (root / ".bootstrap.lock").exists()


@pytest.mark.parametrize("failure", ["timeout", "tls", "origin", "partial"])
def test_pasta_transport_failure_is_atomic(pasta_distribution, monkeypatch, failure):
    root, settings, _, _, _ = pasta_distribution

    class Response(io.BytesIO):
        def geturl(self):
            return (
                "https://evil.test/package.deb"
                if failure == "origin"
                else native.PASTA_ARTIFACT.url
            )

        def read1(self, size: int | None = -1):
            if self.tell():
                raise ConnectionResetError("interrupted download")
            return super().read1(size)

    class Opener:
        def open(self, *_a, **_k):
            if failure == "timeout":
                raise TimeoutError("socket timeout")
            if failure == "tls":
                raise urllib.error.URLError(
                    native.ssl.SSLCertVerificationError("untrusted certificate")
                )
            return Response(b"partial")

    monkeypatch.setattr(native.urllib.request, "build_opener", lambda *_: Opener())
    with pytest.raises(native.ProviderProvisioningError):
        native.ensure_beescan_providers(settings)
    assert sorted(p.name for p in root.iterdir()) == [".bootstrap.lock", "httpx"]


def test_pasta_missing_extractor_refuses_without_install(
    pasta_distribution, monkeypatch
):
    root, settings, _, _, _ = pasta_distribution

    def missing(*_a, **_k):
        raise FileNotFoundError("/usr/bin/dpkg-deb")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(
        native.ProviderProvisioningError, match="system extraction prerequisites"
    ):
        native.ensure_beescan_providers(settings)
    assert not (root / "pasta").exists()
    assert sorted(p.name for p in root.iterdir()) == [".bootstrap.lock", "httpx"]


def test_managed_helper_with_custom_providers_and_git(pasta_distribution):
    root, settings, _, _, calls = pasta_distribution
    native.ensure_beescan_providers(settings)
    for key, name in (("approval", "httpx"), ("detection_approval", "nuclei")):
        custom = root.parent / name
        (root / name).rename(custom)
        settings["beescan"][key]["executable"] = str(custom)
    settings["beescan"].update(
        git_exposure_enabled=True,
        git_exposure_approval={
            "network_namespace": native.egress.MANAGED_NET,
            "user_namespace": native.egress.MANAGED_USER,
        },
    )
    (root / "pasta").unlink()
    native.ensure_beescan_providers(settings)
    assert len(calls) == 2
    assert sorted(p.name for p in root.iterdir()) == [".bootstrap.lock", "pasta"]


def test_missing_httpx_does_not_hide_completed_pasta_provisioning(pasta_distribution):
    root, settings, _, binary, calls = pasta_distribution
    (root / "httpx").unlink()
    with pytest.raises(
        native.ProviderProvisioningError, match="distribution unavailable"
    ):
        native.ensure_beescan_providers(settings)
    assert calls == [native.PASTA_ARTIFACT.url]
    assert (root / "pasta").read_bytes() == binary
    assert (root / "nuclei").is_file()
