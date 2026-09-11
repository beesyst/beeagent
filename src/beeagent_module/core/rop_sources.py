from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_SOURCE_ID = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,63}$")
_SOURCE_TYPES = frozenset({"json_batch", "mailbox_readonly"})
_AUTHORITIES = frozenset({"read_only", "draft_only", "execution_capable"})
_MAX_SOURCES = 1000
_CONNECTION_HEALTH_FILENAME = "rop_source_connection_health.json"
_CONNECTION_HEALTH_REASONS = frozenset(
    {"ok", "missing_credentials", "auth_failure", "mailbox_unavailable"}
)
_CONNECTION_HEALTH_STATUSES = frozenset({"connected", "failed"})

logger = logging.getLogger(__name__)


class RopSourcesError(ValueError):
    pass


def connection_health_path(storage_dir: Path) -> Path:
    return storage_dir / "interfaces" / _CONNECTION_HEALTH_FILENAME


def _valid_connection_health_entry(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "reason_code",
        "checked_at_utc",
    }:
        return None
    status = value.get("status")
    reason = value.get("reason_code")
    checked_at = value.get("checked_at_utc")
    if (
        status not in _CONNECTION_HEALTH_STATUSES
        or reason not in _CONNECTION_HEALTH_REASONS
        or not isinstance(checked_at, str)
        or not checked_at
    ):
        return None
    return {
        "status": status,
        "reason_code": reason,
        "checked_at_utc": checked_at,
    }


def load_rop_source_connection_health(storage_dir: Path) -> dict[str, dict[str, str]]:
    path = connection_health_path(storage_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError, TypeError:
        logger.warning("ROP source connection health is unavailable")
        return {}
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("sources"), dict)
        or set(data) != {"schema_version", "sources"}
    ):
        logger.warning("ROP source connection health is malformed")
        return {}
    health: dict[str, dict[str, str]] = {}
    for source_id, entry in data["sources"].items():
        if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
            logger.warning("ROP source connection health is malformed")
            return {}
        normalized = _valid_connection_health_entry(entry)
        if normalized is None:
            logger.warning("ROP source connection health is malformed")
            return {}
        health[source_id] = normalized
    return health


def _write_connection_health(
    storage_dir: Path, sources: dict[str, dict[str, str]]
) -> None:
    path = connection_health_path(storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".rop_source_connection_health.", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {"schema_version": 1, "sources": sources},
                handle,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_rop_source_connection_health(
    storage_dir: Path, source_id: str, status: str, reason_code: str
) -> None:
    if not _SOURCE_ID.fullmatch(source_id):
        raise RopSourcesError("Source ID is invalid")
    if (
        status not in _CONNECTION_HEALTH_STATUSES
        or reason_code not in _CONNECTION_HEALTH_REASONS
    ):
        raise RopSourcesError("Source connection health is invalid")
    sources = load_rop_source_connection_health(storage_dir)
    sources[source_id] = {
        "status": status,
        "reason_code": reason_code,
        "checked_at_utc": datetime.now(UTC).isoformat(),
    }
    _write_connection_health(storage_dir, sources)


def remove_rop_source_connection_health(storage_dir: Path, source_id: str) -> None:
    if not _SOURCE_ID.fullmatch(source_id):
        raise RopSourcesError("Source ID is invalid")
    sources = load_rop_source_connection_health(storage_dir)
    if source_id in sources:
        del sources[source_id]
        _write_connection_health(storage_dir, sources)


def resolve_sources_path(project_root: Path, settings: dict[str, Any]) -> Path:
    value = settings.get("rop", {}).get("sources_path")
    if not isinstance(value, str) or not value.strip():
        raise RopSourcesError("Invalid rop.sources_path")
    root = project_root.resolve()
    config_root = (root / "config").resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(config_root)
    except ValueError as exc:
        raise RopSourcesError("rop.sources_path must stay under config") from exc
    if candidate.suffix not in {".yml", ".yaml"}:
        raise RopSourcesError("rop.sources_path must be a YAML file")
    return candidate


def credential_env_names(source_id: Any) -> tuple[str, str]:
    if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
        raise RopSourcesError("Source ID is invalid")
    normalized = source_id.upper()
    return (
        f"BEEAGENT_ROP_SOURCE_{normalized}_USERNAME",
        f"BEEAGENT_ROP_SOURCE_{normalized}_PASSWORD",
    )


def _single_email(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value == value.strip()
        and bool(_EMAIL.fullmatch(value))
    )


def validate_sources(
    sources: Any, mailbox_poll: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(sources, list) or len(sources) > _MAX_SOURCES:
        raise RopSourcesError("ROP sources must be a bounded list")
    normalized: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise RopSourcesError(f"ROP source {index} must be a mapping")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not _SOURCE_ID.fullmatch(source_id):
            raise RopSourcesError(f"ROP source {index} has an invalid source_id")
        if source_id in ids:
            raise RopSourcesError("ROP source_id values must be unique")
        ids.add(source_id)
        allowed_source_keys = {
            "source_id",
            "source_type",
            "source_role",
            "client_id",
            "display_name",
            "enabled",
            "authority",
            "items_max",
            "batch",
            "mailbox",
            "routing",
        }
        if set(source) - allowed_source_keys:
            raise RopSourcesError(f"ROP source {source_id} has unsupported fields")
        for key in (
            "source_type",
            "source_role",
            "client_id",
            "display_name",
            "authority",
        ):
            if not isinstance(source.get(key), str) or not source[key].strip():
                raise RopSourcesError(f"ROP source {source_id} has an invalid {key}")
        if source["source_type"] not in _SOURCE_TYPES:
            raise RopSourcesError(
                f"ROP source {source_id} has an unsupported source_type"
            )
        if source["authority"] not in _AUTHORITIES:
            raise RopSourcesError(f"ROP source {source_id} has an invalid authority")
        if not isinstance(source.get("enabled"), bool):
            raise RopSourcesError(
                f"ROP source {source_id} has an invalid enabled value"
            )
        if (
            not isinstance(source.get("items_max"), int)
            or isinstance(source["items_max"], bool)
            or source["items_max"] <= 0
        ):
            raise RopSourcesError(f"ROP source {source_id} has an invalid items_max")
        if source["source_type"] == "json_batch":
            batch = source.get("batch")
            if (
                not isinstance(batch, dict)
                or not isinstance(batch.get("path"), str)
                or not batch["path"].strip()
                or not isinstance(batch.get("period"), str)
                or not batch["period"].strip()
            ):
                raise RopSourcesError(f"ROP source {source_id} has an invalid batch")
        else:
            if source["authority"] != "read_only":
                raise RopSourcesError(
                    "mailbox_readonly source authority must be read_only"
                )
            mailbox = source.get("mailbox")
            if not isinstance(mailbox, dict):
                raise RopSourcesError(f"ROP source {source_id} has an invalid mailbox")
            if set(mailbox) - {
                "host",
                "port",
                "use_ssl",
                "folder",
                "username_env",
                "password_env",
            }:
                raise RopSourcesError(
                    f"ROP source {source_id} has unsupported mailbox fields"
                )
            if not isinstance(mailbox.get("host"), str) or not mailbox["host"].strip():
                raise RopSourcesError(
                    f"ROP source {source_id} has an invalid mailbox host"
                )
            host = mailbox["host"]
            if (
                host != host.strip()
                or any(char.isspace() for char in host)
                or "://" in host
                or "/" in host
            ):
                raise RopSourcesError(
                    f"ROP source {source_id} has an invalid mailbox host"
                )
            if (
                not isinstance(mailbox.get("folder"), str)
                or not mailbox["folder"].strip()
            ):
                raise RopSourcesError(
                    f"ROP source {source_id} has an invalid mailbox folder"
                )
            if (
                not isinstance(mailbox.get("port"), int)
                or isinstance(mailbox["port"], bool)
                or not 1 <= mailbox["port"] <= 65535
            ):
                raise RopSourcesError(
                    f"ROP source {source_id} has an invalid mailbox port"
                )
            if not isinstance(mailbox.get("use_ssl"), bool):
                raise RopSourcesError(
                    f"ROP source {source_id} has an invalid mailbox use_ssl"
                )
            for key in ("username_env", "password_env"):
                if not isinstance(mailbox.get(key), str) or not mailbox[key].strip():
                    raise RopSourcesError(
                        f"ROP source {source_id} has an invalid {key}"
                    )
        routing = source.get("routing")
        if routing is not None:
            if not isinstance(routing, dict):
                raise RopSourcesError(f"Unsupported routing for ROP source {source_id}")
            unsupported_routing = sorted(set(routing) - {"email_recipient"})
            if unsupported_routing:
                raise RopSourcesError(
                    "Unsupported routing fields: " + ", ".join(unsupported_routing)
                )
            if "email_recipient" in routing and not _single_email(
                routing["email_recipient"]
            ):
                raise RopSourcesError(
                    f"ROP source {source_id} has an invalid routing.email_recipient"
                )
        normalized.append(source)
    if not isinstance(mailbox_poll, dict) or not isinstance(
        mailbox_poll.get("enabled"), bool
    ):
        raise RopSourcesError("Invalid rop.mailbox_poll")
    all_sources = mailbox_poll.get("sources_all", False)
    if not isinstance(all_sources, bool):
        raise RopSourcesError("Invalid rop.mailbox_poll.sources_all")
    selected = mailbox_poll.get("source_id")
    if mailbox_poll["enabled"] and not all_sources:
        if not isinstance(selected, str) or not selected.strip():
            raise RopSourcesError("Invalid rop.mailbox_poll.source_id")
        source = next(
            (item for item in normalized if item["source_id"] == selected), None
        )
        if source is None:
            raise RopSourcesError("rop.mailbox_poll.source_id not found in registry")
        if (
            source["source_type"] != "mailbox_readonly"
            or source["authority"] != "read_only"
        ):
            raise RopSourcesError(
                "rop.mailbox_poll source must be read_only mailbox_readonly"
            )
    return normalized


def load_rop_sources(
    project_root: Path, settings: dict[str, Any]
) -> list[dict[str, Any]]:
    path = resolve_sources_path(project_root, settings)
    if not path.is_file():
        raise RopSourcesError("ROP source registry was not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RopSourcesError("ROP source registry is malformed") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "sources"}
        or data.get("version") != 1
    ):
        raise RopSourcesError("ROP source registry must contain version 1 and sources")
    return validate_sources(
        data["sources"], settings.get("rop", {}).get("mailbox_poll", {})
    )


def _write(path: Path, sources: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".rop_sources-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                {"version": 1, "sources": sources},
                handle,
                allow_unicode=True,
                sort_keys=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _mutate(
    project_root: Path, settings: dict[str, Any], operation: Any
) -> tuple[dict[str, Any] | str, bool]:
    path = resolve_sources_path(project_root, settings)
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        sources = load_rop_sources(project_root, settings)
        result, candidate, changed = operation(sources)
        validate_sources(candidate, settings["rop"]["mailbox_poll"])
        if changed:
            _write(path, candidate)
        return result, changed


def add_rop_source(
    project_root: Path, settings: dict[str, Any], source: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        validate_sources([source], {"enabled": False})
        if any(item["source_id"] == source["source_id"] for item in sources):
            raise RopSourcesError("ROP source already exists")
        return source, [*sources, source], True

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def update_rop_source(
    project_root: Path, settings: dict[str, Any], source_id: str, source: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        current = next(
            (item for item in sources if item["source_id"] == source_id), None
        )
        if current is None:
            raise RopSourcesError("ROP source was not found")
        if source.get("source_id") != source_id or source.get(
            "source_type"
        ) != current.get("source_type"):
            raise RopSourcesError("Source ID and source type are immutable")
        candidate = [
            source if item["source_id"] == source_id else item for item in sources
        ]
        return source, candidate, current != source

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def remove_rop_source(
    project_root: Path, settings: dict[str, Any], source_id: str
) -> tuple[str, bool]:
    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]], bool]:
        if not any(item["source_id"] == source_id for item in sources):
            return source_id, sources, False
        return (
            source_id,
            [item for item in sources if item["source_id"] != source_id],
            True,
        )

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def add_mailbox_source(
    project_root: Path,
    settings: dict[str, Any],
    values: dict[str, Any],
    before_commit: Any | None = None,
) -> tuple[dict[str, Any], bool]:
    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        selected = settings["rop"]["mailbox_poll"].get("source_id")
        profile = next(
            (
                item
                for item in sources
                if item["source_id"] == selected
                and item["source_type"] == "mailbox_readonly"
                and item["authority"] == "read_only"
            ),
            None,
        )
        if profile is None:
            raise RopSourcesError("A mailbox deployment profile is required")
        existing_ids = {item["source_id"] for item in sources}
        for _ in range(10):
            source_id = "mailbox_" + uuid.uuid4().hex[:8]
            if source_id not in existing_ids:
                break
        else:
            raise RopSourcesError("Unable to generate a mailbox source ID")
        username_env, password_env = credential_env_names(source_id)
        source = {
            "source_id": source_id,
            "source_type": "mailbox_readonly",
            "source_role": profile["source_role"],
            "client_id": profile["client_id"],
            "display_name": values.get("display_name"),
            "enabled": values.get("enabled"),
            "authority": "read_only",
            "items_max": profile["items_max"],
            "mailbox": {
                "host": values.get("host"),
                "port": 993,
                "use_ssl": True,
                "folder": values.get("folder") or "INBOX",
                "username_env": username_env,
                "password_env": password_env,
            },
        }
        candidate = [*sources, source]
        validate_sources(candidate, settings["rop"]["mailbox_poll"])
        if before_commit is not None:
            before_commit(source)
        return source, candidate, True

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def update_mailbox_source(
    project_root: Path,
    settings: dict[str, Any],
    source_id: str,
    values: dict[str, Any],
    before_commit: Any | None = None,
) -> tuple[dict[str, Any], bool]:
    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        current = next(
            (item for item in sources if item["source_id"] == source_id), None
        )
        if current is None or current["source_type"] != "mailbox_readonly":
            raise RopSourcesError("Mailbox source was not found")
        candidate = {
            **current,
            "display_name": values.get("display_name"),
            "mailbox": {
                **current["mailbox"],
                "host": values.get("host"),
                "folder": values.get("folder"),
            },
        }
        sources_candidate = [
            candidate if item["source_id"] == source_id else item for item in sources
        ]
        validate_sources(sources_candidate, settings["rop"]["mailbox_poll"])
        if before_commit is not None:
            before_commit(candidate)
        return candidate, sources_candidate, candidate != current

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def update_rop_source_display_name(
    project_root: Path,
    settings: dict[str, Any],
    source_id: str,
    display_name: Any,
) -> tuple[dict[str, Any], bool]:
    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        current = next(
            (item for item in sources if item["source_id"] == source_id), None
        )
        if current is None or current["source_type"] != "json_batch":
            raise RopSourcesError("JSON batch source was not found")
        candidate = {**current, "display_name": display_name}
        return (
            candidate,
            [candidate if item["source_id"] == source_id else item for item in sources],
            candidate != current,
        )

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def set_rop_source_enabled(
    project_root: Path, settings: dict[str, Any], source_id: str, enabled: Any
) -> tuple[dict[str, Any], bool]:
    if not isinstance(enabled, bool):
        raise RopSourcesError("Source enabled value is invalid")

    def operation(
        sources: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
        current = next(
            (item for item in sources if item["source_id"] == source_id), None
        )
        if current is None:
            raise RopSourcesError("ROP source was not found")
        candidate = {**current, "enabled": enabled}
        return (
            candidate,
            [candidate if item["source_id"] == source_id else item for item in sources],
            candidate != current,
        )

    return _mutate(project_root, settings, operation)  # type: ignore[return-value]


def write_rop_sources_audit(
    storage_dir: Path,
    *,
    action_id: str,
    actor_id: str | None,
    source_id: str | None,
    outcome: str,
) -> None:
    target = storage_dir / "interfaces" / "rop_sources_audit.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "action_id": action_id,
        "actor_id": actor_id or "unknown",
        "source_id": source_id or "unknown",
        "outcome": outcome,
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
