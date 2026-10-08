from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


@dataclass(frozen=True)
class NativeArtifact:
    name: str
    url: str
    sha256: str
    size: int
    destination: str
    executables: tuple[str, ...]
    missing_reason: str


NATIVE_ARTIFACTS = (
    NativeArtifact(
        "surfpool-1.5.0",
        "https://github.com/solana-foundation/surfpool/releases/download/"
        "v1.5.0/surfpool-linux-x64.tar.gz",
        "5b20a3b46e60c4f819af7b4da5c3ea211f76041710617841cc23247d15887ddc",
        34170467,
        "surfpool-1.5.0",
        ("surfpool",),
        "missing_surfpool",
    ),
    NativeArtifact(
        "agave-4.2.2",
        "https://github.com/anza-xyz/agave/releases/download/"
        "v4.2.2/solana-release-x86_64-unknown-linux-gnu.tar.bz2",
        "5fc8684f7430038105fde953d4308ed56addf627f658daa61709f345448247ee",
        86382236,
        "agave-4.2.2",
        ("solana-release/bin/solana", "solana-release/bin/cargo-build-sbf"),
        "missing_solana_cli",
    ),
    NativeArtifact(
        "platform-tools-1.54",
        "https://github.com/anza-xyz/platform-tools/releases/download/"
        "v1.54/platform-tools-linux-x86_64.tar.bz2",
        "fcc41631c7f77561bf5412218bf297501dccf0305ea280f338f0ace2aab9f31e",
        520154357,
        "home/.cache/solana/v1.54/platform-tools",
        ("rust/bin/cargo", "rust/bin/rustc"),
        "missing_cargo",
    ),
)


class NativeToolchainError(RuntimeError):
    def __init__(self, reason: str, action: str) -> None:
        super().__init__(action)
        self.reason = reason


def toolchain_root() -> Path:
    return Path.home() / ".local/share/beeagent/beedrill-tools"


def native_environment(root: Path | None = None) -> dict[str, str]:
    root = root or toolchain_root()
    return {
        "HOME": str(root / "home"),
        "PATH": os.pathsep.join(
            (
                str(root / "home/.cache/solana/v1.54/platform-tools/rust/bin"),
                str(root / "agave-4.2.2/solana-release/bin"),
                str(root / "surfpool-1.5.0"),
                "/usr/bin",
                "/bin",
            )
        ),
    }


def _official_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname
        in {
            "github.com",
            "release-assets.githubusercontent.com",
            "objects.githubusercontent.com",
        }
        and parsed.username is None
        and parsed.password is None
        and parsed.port in {None, 443}
    )


class _OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _official_url(newurl):
            raise NativeToolchainError(
                "incompatible_toolchain",
                "Official download redirected outside the allowlist.",
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _download(artifact: NativeArtifact, target: Path) -> None:
    if not _official_url(artifact.url):
        raise NativeToolchainError(
            "incompatible_toolchain", "Invalid official artifact manifest."
        )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _OfficialRedirect()
    )
    request = urllib.request.Request(
        artifact.url, headers={"User-Agent": "BeeAgent-BeeDrill"}
    )
    deadline = time.monotonic() + 600
    size = 0
    with opener.open(request, timeout=30) as response, target.open("xb") as stream:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if time.monotonic() > deadline:
                raise NativeToolchainError(
                    "timeout",
                    "Native artifact download timed out. Retry beedrill check.",
                )
            if size > artifact.size:
                raise NativeToolchainError(
                    "incompatible_toolchain",
                    "Official artifact exceeded its pinned size.",
                )
            stream.write(chunk)
    if size != artifact.size or _digest(target) != artifact.sha256:
        raise NativeToolchainError(
            "incompatible_toolchain",
            "Official artifact checksum mismatch. Retry with an intact official distribution.",
        )


def _extract(archive: Path, destination: Path) -> None:
    size = 0
    count = 0
    with tarfile.open(archive) as bundle:
        for member in bundle:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise tarfile.FilterError("Unsafe native archive path")
            size += member.size
            count += 1
            if size > 4 * 1024**3 or count > 100_000:
                raise NativeToolchainError(
                    "incompatible_toolchain",
                    "Official archive exceeded extraction bounds.",
                )
            bundle.extract(member, destination, filter="data")


def _install(artifact: NativeArtifact, root: Path) -> None:
    destination = root / artifact.destination
    marker = destination / ".beeagent-provenance.json"
    archive = root / "downloads" / f"{artifact.name}.tar"
    if (
        destination.resolve() != destination.absolute()
        or archive.resolve() != archive.absolute()
    ):
        raise NativeToolchainError(
            "incompatible_toolchain",
            "Native cache paths must not redirect outside their pinned location.",
        )
    if archive.exists() and (
        _digest(archive) != artifact.sha256 or archive.stat().st_size != artifact.size
    ):
        raise NativeToolchainError(
            "incompatible_toolchain",
            "Native download cache is corrupt. Move the affected BeeDrill tool cache aside and retry.",
        )
    if destination.exists():
        if (
            marker.is_file()
            and not marker.is_symlink()
            and marker.stat().st_size <= 65536
        ):
            provenance = json.loads(marker.read_text())
            if (
                isinstance(provenance, dict)
                and provenance.get("sha256") == artifact.sha256
                and provenance.get("url") == artifact.url
            ):
                binaries = provenance.get("executables", {})
                if isinstance(binaries, dict) and all(
                    (destination / name).is_file()
                    and os.access(destination / name, os.X_OK)
                    and binaries.get(name) == _digest(destination / name)
                    for name in artifact.executables
                ):
                    return
        raise NativeToolchainError(
            "incompatible_toolchain",
            "Native installation is incomplete or modified. Move the affected BeeDrill tool cache aside and retry.",
        )
    if not archive.exists():
        with tempfile.TemporaryDirectory(prefix="download-", dir=root) as temporary:
            download = Path(temporary) / "artifact"
            _download(artifact, download)
            download.replace(archive)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix="extract-", dir=destination.parent
    ) as temporary:
        extracted = Path(temporary) / "content"
        extracted.mkdir(mode=0o700)
        _extract(archive, extracted)
        binaries = {}
        for name in artifact.executables:
            binary = extracted / name
            if not binary.is_file() or not os.access(binary, os.X_OK):
                reason = (
                    "missing_sbf_builder"
                    if name.endswith("cargo-build-sbf")
                    else artifact.missing_reason
                )
                raise NativeToolchainError(
                    reason,
                    "Official distribution lacks a required native tool. Use the supported Linux x86_64 environment.",
                )
            binaries[name] = _digest(binary)
        (extracted / marker.name).write_text(
            json.dumps(
                {
                    "url": artifact.url,
                    "sha256": artifact.sha256,
                    "executables": binaries,
                },
                sort_keys=True,
            )
        )
        extracted.replace(destination)


def ensure_native_tools(*, needs_sbf: bool, root: Path | None = None) -> None:
    libc, version = platform.libc_ver()
    if (
        platform.system() != "Linux"
        or platform.machine() != "x86_64"
        or libc != "glibc"
        or tuple(int(part) for part in version.split(".") if part.isdigit()) < (2, 34)
    ):
        raise NativeToolchainError(
            "incompatible_toolchain",
            "Use Linux x86_64 with glibc 2.34 or newer; automatic native preparation is unsupported here.",
        )
    import fcntl

    root = root or toolchain_root()
    required = NATIVE_ARTIFACTS if needs_sbf else NATIVE_ARTIFACTS[:1]
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if root.is_symlink():
            raise NativeToolchainError(
                "incompatible_toolchain", "Native cache root must not be a symlink."
            )
        downloads = root / "downloads"
        if (
            downloads.resolve() != downloads.absolute()
            or (root / ".bootstrap.lock").is_symlink()
        ):
            raise NativeToolchainError(
                "incompatible_toolchain",
                "Native cache paths must not redirect outside their pinned location.",
            )
        downloads.mkdir(exist_ok=True, mode=0o700)
        with (root / ".bootstrap.lock").open("a") as lock:
            deadline = time.monotonic() + 60
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise NativeToolchainError(
                            "timeout",
                            "Another native preparation is busy. Retry beedrill check.",
                        )
                    time.sleep(0.1)
            for artifact in required:
                try:
                    _install(artifact, root)
                except TimeoutError as exc:
                    raise NativeToolchainError(
                        "timeout",
                        "Native artifact download timed out. Retry beedrill check.",
                    ) from exc
                except urllib.error.URLError as exc:
                    if isinstance(exc.reason, TimeoutError):
                        raise NativeToolchainError(
                            "timeout",
                            "Native artifact download timed out. Retry beedrill check.",
                        ) from exc
                    raise NativeToolchainError(
                        artifact.missing_reason,
                        "Cannot safely prepare the required native tool. Check HTTPS access to official GitHub releases, free disk space and user-local write permission, then retry beedrill check.",
                    ) from exc
                except OSError as exc:
                    raise NativeToolchainError(
                        artifact.missing_reason,
                        "Cannot safely prepare the required native tool. Check HTTPS access to official GitHub releases, free disk space and user-local write permission, then retry beedrill check.",
                    ) from exc
            (root / "home").mkdir(exist_ok=True, mode=0o700)
            probes = [(root / "surfpool-1.5.0/surfpool", "surfpool 1.5.0")]
            if needs_sbf:
                probes.extend(
                    [
                        (
                            root / "agave-4.2.2/solana-release/bin/solana",
                            "solana-cli 4.2.2",
                        ),
                        (
                            root / "agave-4.2.2/solana-release/bin/cargo-build-sbf",
                            "cargo-build-sbf 4.1.0",
                        ),
                        (
                            root
                            / "home/.cache/solana/v1.54/platform-tools/rust/bin/cargo",
                            "cargo 1.89.0",
                        ),
                        (
                            root
                            / "home/.cache/solana/v1.54/platform-tools/rust/bin/rustc",
                            "rustc 1.89.0",
                        ),
                    ]
                )
            for binary, expected in probes:
                completed = subprocess.run(
                    [str(binary), "--version"],
                    env=native_environment(root),
                    capture_output=True,
                    timeout=10,
                    check=False,
                )
                if completed.returncode != 0 or not completed.stdout.startswith(
                    expected.encode()
                ):
                    raise NativeToolchainError(
                        "incompatible_toolchain",
                        "Pinned native tools cannot run on this host. Use a compatible glibc Linux x86_64 environment.",
                    )
            if needs_sbf:
                compiler = shutil.which("cc", path="/usr/bin:/bin")
                if compiler is None:
                    raise NativeToolchainError(
                        "incompatible_toolchain",
                        "SBF builds require a Linux development environment with a working C linker and glibc development files. Use a prepared development image; BeeAgent does not install system packages.",
                    )
                with tempfile.TemporaryDirectory(
                    prefix="linker-probe-", dir=root
                ) as temporary:
                    completed = subprocess.run(
                        [
                            compiler,
                            "-x",
                            "c",
                            "-",
                            "-o",
                            str(Path(temporary) / "probe"),
                        ],
                        input=b"int main(void) { return 0; }\n",
                        env=native_environment(root),
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    if completed.returncode != 0:
                        raise NativeToolchainError(
                            "incompatible_toolchain",
                            "The host C linker cannot build native Rust dependencies. Use a Linux development image with glibc development files; no system packages are installed by BeeAgent.",
                        )
    except subprocess.TimeoutExpired as exc:
        raise NativeToolchainError(
            "timeout", "Native tool readiness probe timed out. Retry beedrill check."
        ) from exc
    except (OSError, ValueError, tarfile.TarError) as exc:
        raise NativeToolchainError(
            "incompatible_toolchain",
            "Native cache or environment is incompatible. Check the supported platform and intact user-local cache, then retry beedrill check.",
        ) from exc
