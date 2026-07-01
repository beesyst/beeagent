from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from beeagent_module.core.env_sync import sync_env_with_example

EXAMPLE_CONTENT = (
    "TELEGRAM_BOT_TOKEN=\n"
    "CHAT_ID=\n"
    "\n"
    "# Bitrix\n"
    "BITRIX_WEBHOOK_URL=\n"
    "\n"
    "# ROP mailbox\n"
    "ROP_MAILBOX_USERNAME=\n"
    "ROP_MAILBOX_PASSWORD=\n"
    "\n"
    "# BeeAgent Web auth\n"
    "BEEAGENT_WEB_SESSION_SECRET=\n"
    "BEEAGENT_WEB_ADMIN1_TOKEN=\n"
    "BEEAGENT_WEB_ADMIN2_TOKEN=\n"
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    (tmp_path / ".env.example").write_text(EXAMPLE_CONTENT, encoding="utf-8")
    return tmp_path


def _env_map(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_creates_env_from_example(project_root: Path) -> None:
    env_path = project_root / ".env"

    sync_env_with_example(project_root)

    assert env_path.read_text(encoding="utf-8") == EXAMPLE_CONTENT
    if os.name == "posix":
        mode = stat.S_IMODE(env_path.stat().st_mode)
        assert mode == (stat.S_IRUSR | stat.S_IWUSR)


def test_appends_missing_keys_without_overwriting_existing_values(
    project_root: Path,
) -> None:
    env_path = project_root / ".env"
    env_path.write_text(
        "# Existing comment\n"
        "TELEGRAM_BOT_TOKEN=my-token\n"
        "CHAT_ID=123\n"
        "# Keep this too\n",
        encoding="utf-8",
    )

    sync_env_with_example(project_root)

    assert env_path.read_text(encoding="utf-8") == (
        "# Existing comment\n"
        "TELEGRAM_BOT_TOKEN=my-token\n"
        "CHAT_ID=123\n"
        "# Keep this too\n"
        "BITRIX_WEBHOOK_URL=\n"
        "ROP_MAILBOX_USERNAME=\n"
        "ROP_MAILBOX_PASSWORD=\n"
        "BEEAGENT_WEB_SESSION_SECRET=\n"
        "BEEAGENT_WEB_ADMIN1_TOKEN=\n"
        "BEEAGENT_WEB_ADMIN2_TOKEN=\n"
    )
    env_map = _env_map(env_path)
    assert env_map["TELEGRAM_BOT_TOKEN"] == "my-token"
    assert env_map["CHAT_ID"] == "123"


def test_does_not_print_secret_values(
    project_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_path = project_root / ".env"
    env_path.write_text(
        "ROP_MAILBOX_USERNAME=my-secret-user\n",
        encoding="utf-8",
    )

    sync_env_with_example(project_root)

    captured = capsys.readouterr()
    assert "my-secret-user" not in captured.out
    assert "my-secret-user" not in captured.err
