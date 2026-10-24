import os
import stat
from pathlib import Path


def find_project_root(start_path: Path | None = None) -> Path:
    start = (
        Path(start_path).resolve()
        if start_path is not None
        else Path(__file__).resolve()
    )

    cur_dir = start if start.is_dir() else start.parent

    for directory in (cur_dir, *cur_dir.parents):
        if (directory / "pyproject.toml").is_file():
            return directory

    raise FileNotFoundError(
        "Unable to locate project root: pyproject.toml not found in parent directories. "
        "Ensure you run BeeAgent from the project tree or install it as a package."
    )


ROOT_DIR = find_project_root()
CONFIG_DIR = ROOT_DIR / "config"
LOGS_DIR = ROOT_DIR / "logs"
STORAGE_DIR = ROOT_DIR / "storage"


def get_project_root() -> Path:
    return ROOT_DIR


def get_logs_dir(project_root: Path | None = None) -> Path:
    root = project_root or ROOT_DIR
    return root / "logs"


def get_storage_dir(project_root: Path | None = None) -> Path:
    root = project_root or ROOT_DIR
    return (root / "storage").resolve()


def get_app_log_path(project_root: Path | None = None) -> Path:
    return get_logs_dir(project_root) / "app.log"


def _ensure_private_directory(name: str, *, dir_fd: int) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=dir_fd)
    except FileExistsError:
        pass
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=dir_fd,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise PermissionError("unsafe_storage_directory")
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.fchmod(descriptor, 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def ensure_dirs(project_root: Path | None = None) -> None:
    logs_dir = get_logs_dir(project_root)

    logs_dir.mkdir(parents=True, exist_ok=True)
    root_fd = os.open(
        project_root or ROOT_DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    )
    try:
        storage_fd = _ensure_private_directory("storage", dir_fd=root_fd)
        try:
            runs_fd = _ensure_private_directory("runs", dir_fd=storage_fd)
            os.close(runs_fd)
            try:
                gitkeep_fd = os.open(
                    ".gitkeep",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                    dir_fd=storage_fd,
                )
            except FileExistsError:
                pass
            else:
                os.close(gitkeep_fd)
        finally:
            os.close(storage_fd)
    finally:
        os.close(root_fd)

    gitkeep_path = logs_dir / ".gitkeep"
    if not gitkeep_path.exists():
        gitkeep_path.touch()
