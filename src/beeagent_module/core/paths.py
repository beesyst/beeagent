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


def ensure_dirs(project_root: Path | None = None) -> None:
    logs_dir = get_logs_dir(project_root)
    storage_dir = get_storage_dir(project_root)

    logs_dir.mkdir(parents=True, exist_ok=True)
    storage_dir.mkdir(parents=True, exist_ok=True)

    for directory in (logs_dir, storage_dir):
        gitkeep_path = directory / ".gitkeep"
        if not gitkeep_path.exists():
            gitkeep_path.touch()
