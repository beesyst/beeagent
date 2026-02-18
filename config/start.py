from dotenv import load_dotenv

from beeagent_module.core.app import run_app
from beeagent_module.core.log import get_logger, setup_logging
from beeagent_module.core.paths import ensure_dirs, get_app_log_path, get_project_root
from beeagent_module.core.settings import load_settings


def main() -> None:
    project_root = get_project_root()

    env_path = project_root / ".env"
    load_dotenv(dotenv_path=env_path, override=False)

    settings_path = project_root / "config" / "settings.yml"
    settings = load_settings(settings_path)

    ensure_dirs()
    log_path = get_app_log_path()

    log_cfg = settings["logging"]
    setup_logging(
        log_path=log_path,
        level=log_cfg["level"],
        clear_logs=log_cfg["clear_logs"],
        utc=log_cfg["utc"],
    )

    logger = get_logger("app")
    run_app(settings=settings, logger=logger)


if __name__ == "__main__":
    main()
