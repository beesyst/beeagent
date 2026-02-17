from pathlib import Path


# Русский комментарий
def get_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


# Русский комментарий
def get_logs_dir(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    return root / "logs"


# Русский комментарий
def get_storage_dir(project_root: Path | None = None) -> Path:
    root = project_root or get_project_root()
    return root / "storage"


# Русский комментарий
def get_app_log_path(project_root: Path | None = None) -> Path:
    return get_logs_dir(project_root) / "app.log"


# Русский комментарий
def ensure_dirs(project_root: Path | None = None) -> None:
    logs_dir = get_logs_dir(project_root)
    storage_dir = get_storage_dir(project_root)

    logs_dir.mkdir(parents=True, exist_ok=True)
    storage_dir.mkdir(parents=True, exist_ok=True)

    for directory in (logs_dir, storage_dir):
        gitkeep_path = directory / ".gitkeep"
        if not gitkeep_path.exists():
            gitkeep_path.touch()
