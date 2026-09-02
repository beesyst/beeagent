from __future__ import annotations

import json
import os
import re
import tempfile
import fcntl
import hashlib
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path
from typing import Any

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,63}$")
_STATE_NAME = "rop_sender_blacklist.json"


class SenderBlacklistError(ValueError):
    pass


def normalize_sender_email(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 254:
        raise SenderBlacklistError("Sender email is invalid")
    _, address = parseaddr(value.strip())
    normalized = address.strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise SenderBlacklistError("Sender email is invalid")
    return normalized


def _path(storage_dir: Path) -> Path:
    return storage_dir / "interfaces" / _STATE_NAME


def load_sender_blacklist(storage_dir: Path) -> list[str]:
    path = _path(storage_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SenderBlacklistError("Sender blacklist state is malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {"emails"}:
        raise SenderBlacklistError("Sender blacklist state is malformed")
    emails = payload["emails"]
    if not isinstance(emails, list) or len(emails) > 1000:
        raise SenderBlacklistError("Sender blacklist state is malformed")
    normalized = [normalize_sender_email(item) for item in emails]
    if len(set(normalized)) != len(normalized):
        raise SenderBlacklistError("Sender blacklist state is malformed")
    return sorted(normalized)


def _write(storage_dir: Path, emails: list[str]) -> None:
    path = _path(storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".rop_sender_blacklist-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"emails": sorted(emails)}, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def add_sender_blacklist_email(storage_dir: Path, value: Any) -> tuple[str, bool]:
    email = normalize_sender_email(value)
    lock_path = _path(storage_dir).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        emails = load_sender_blacklist(storage_dir)
        if email in emails:
            return email, False
        _write(storage_dir, [*emails, email])
        return email, True


def remove_sender_blacklist_email(storage_dir: Path, value: Any) -> tuple[str, bool]:
    email = normalize_sender_email(value)
    lock_path = _path(storage_dir).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        emails = load_sender_blacklist(storage_dir)
        if email not in emails:
            return email, False
        _write(storage_dir, [item for item in emails if item != email])
        return email, True


def sender_from_event(event: dict[str, Any]) -> str | None:
    for key in ("original_sender_email", "original_sender", "sender"):
        value = event.get(key)
        try:
            return normalize_sender_email(value)
        except SenderBlacklistError:
            continue
    return None


def apply_sender_blacklist_policy(events: list[dict[str, Any]], storage_dir: Path) -> int:
    emails = frozenset(load_sender_blacklist(storage_dir))
    applied = 0
    for event in events:
        sender = sender_from_event(event)
        if sender is None or sender not in emails:
            continue
        event["policy_override_reason"] = "sender_blacklisted"
        event["policy_sender"] = sender
        event["case_type"] = "irrelevant"
        event["recommended_queue"] = "irrelevant"
        event["correct_action"] = "no_action"
        event["should_rop_see"] = False
        applied += 1
    return applied


def write_sender_blacklist_audit(
    storage_dir: Path,
    *,
    action_id: str,
    actor_id: str | None,
    outcome: str,
    email: str | None,
) -> None:
    interfaces = storage_dir / "interfaces"
    interfaces.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None
    record = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "action_id": action_id,
        "actor_id": actor_id or "unknown",
        "outcome": outcome,
        "email_sha256": digest,
    }
    with (interfaces / "rop_sender_blacklist_audit.jsonl").open(
        "a", encoding="utf-8"
    ) as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
