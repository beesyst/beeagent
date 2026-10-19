import hashlib
import os
import platform
import stat
import tempfile
import time
import zipfile
from pathlib import Path

from beeagent_module.core.beedrill_toolchain import (
    NativeArtifact,
    NativeToolchainError,
    _download,
)
from beeagent_module.core.settings import _is_module_enabled
from beeagent_module.integrations.beescan.detection_policy import NUCLEI_SHA256
from beeagent_module.integrations.beescan.policy import HTTPX_SHA256

NUCLEI_ARTIFACT = NativeArtifact(
    "nuclei-3.11.1",
    "https://github.com/projectdiscovery/nuclei/releases/download/"
    "v3.11.1/nuclei_3.11.1_linux_amd64.zip",
    "ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6",
    46148343,
    "nuclei",
    ("nuclei",),
    "provider_unavailable",
)
NUCLEI_BYTES = 143294626
HTTPX_BYTES = 58029060


class ProviderProvisioningError(RuntimeError):
    pass


def provider_root() -> Path:
    return Path.home() / ".local/share/beeagent/beescan-providers"


def _secure_root(root: Path) -> None:
    if not root.is_absolute() or root.resolve() != root:
        raise ProviderProvisioningError("Provider directory must not contain symlinks")
    for directory in reversed((root, *root.parents)):
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid not in {0, os.getuid()}
            or (info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX)
        ):
            raise ProviderProvisioningError(
                "Insecure provider directory ownership or mode"
            )
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise ProviderProvisioningError(
            "Provider directory must be private to its owner"
        )


def _verify(path: Path, digest: str, limit: int, *, managed=False) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or (managed and info.st_uid not in {0, os.getuid()})
            or info.st_mode & 0o022
            or not info.st_mode & 0o111
            or info.st_size != limit
        ):
            raise ProviderProvisioningError(
                "Provider integrity or permissions mismatch"
            )
        checksum = hashlib.sha256()
        remaining = limit + 1
        while remaining and (chunk := stream.read(min(1024 * 1024, remaining))):
            checksum.update(chunk)
            remaining -= len(chunk)
        if remaining != 1 or checksum.hexdigest() != digest:
            raise ProviderProvisioningError("Provider executable SHA-256 mismatch")


def _install_nuclei(root: Path) -> None:
    destination = root / "nuclei"
    if destination.exists() or destination.is_symlink():
        _verify(destination, NUCLEI_SHA256, NUCLEI_BYTES, managed=True)
        return
    with tempfile.TemporaryDirectory(prefix=".nuclei-", dir=root) as temporary:
        directory = Path(temporary)
        archive = directory / "release.zip"
        _download(NUCLEI_ARTIFACT, archive)
        with archive.open("rb") as stream:
            if (
                os.fstat(stream.fileno()).st_size != NUCLEI_ARTIFACT.size
                or hashlib.file_digest(stream, "sha256").hexdigest()
                != NUCLEI_ARTIFACT.sha256
            ):
                raise ProviderProvisioningError("Nuclei archive SHA-256 mismatch")
        binary = directory / "nuclei"
        with zipfile.ZipFile(archive) as bundle:
            matches = [item for item in bundle.infolist() if item.filename == "nuclei"]
            if len(matches) != 1 or matches[0].file_size != NUCLEI_BYTES:
                raise ProviderProvisioningError("Invalid Nuclei archive executable")
            member = matches[0]
            mode = member.external_attr >> 16
            if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                raise ProviderProvisioningError("Invalid Nuclei archive entry type")
            with bundle.open(member) as source, binary.open("xb") as target:
                size = 0
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > NUCLEI_BYTES:
                        raise ProviderProvisioningError(
                            "Nuclei extraction exceeded bounds"
                        )
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
        binary.chmod(0o555)
        _verify(binary, NUCLEI_SHA256, NUCLEI_BYTES, managed=True)
        os.link(binary, destination)
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _check_provider(name, path, digest, size, root):
    try:
        _verify(path, digest, size, managed=path == root / name)
    except FileNotFoundError:
        if name == "httpx":
            raise ProviderProvisioningError(
                "Pinned httpx distribution unavailable: publish the reviewed "
                "Go 1.27.2 static rebuild with SHA-256 "
                f"{HTTPX_SHA256} at a reviewed immutable HTTPS artifact URL. "
                "Until then, provision those exact bytes at the configured "
                "path; upstream httpx is not a compatible substitute."
            ) from None
        raise ProviderProvisioningError(
            "Custom provider path is missing; automatic installation only "
            f"manages {root / name}. No custom path was overwritten."
        ) from None


def ensure_beescan_providers(settings: dict) -> None:
    if not _is_module_enabled(settings, "beescan"):
        return
    config = settings["beescan"]
    selected = [
        (name, config[key]["executable"], digest, size)
        for name, flag, key, digest, size in (
            (
                "nuclei",
                "detection_enabled",
                "detection_approval",
                NUCLEI_SHA256,
                NUCLEI_BYTES,
            ),
            ("httpx", "probe_enabled", "approval", HTTPX_SHA256, HTTPX_BYTES),
        )
        if config.get(flag) is True
    ]
    if not selected:
        return
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ProviderProvisioningError("BeeScan native providers require Linux x86_64")
    import fcntl

    root = provider_root()
    try:
        managed = []
        for name, executable, digest, size in selected:
            path = Path(executable)
            if path == root / name:
                managed.append((name, path, digest, size))
            else:
                _check_provider(name, path, digest, size, root)
        if not managed:
            return
        _secure_root(root)
        descriptor = os.open(
            root / ".bootstrap.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            0o600,
        )
        with os.fdopen(descriptor, "rb+") as lock:
            info = os.fstat(lock.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
            ):
                raise ProviderProvisioningError("Insecure provider bootstrap lock")
            deadline = time.monotonic() + 60
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ProviderProvisioningError(
                            "Provider bootstrap lock timed out"
                        )
                    time.sleep(0.1)
            for name, path, digest, size in managed:
                if name == "nuclei":
                    _install_nuclei(root)
                _check_provider(name, path, digest, size, root)
    except (OSError, ValueError, zipfile.BadZipFile, NativeToolchainError) as exc:
        raise ProviderProvisioningError(
            "Cannot safely provision BeeScan providers. Check official GitHub HTTPS "
            "access, disk space, intact pinned bytes and private directory permissions."
        ) from exc
