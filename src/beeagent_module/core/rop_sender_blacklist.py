from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from email.utils import parseaddr
from pathlib import Path
from typing import Any

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,63}$")
_STATE_NAME = "rop_sender_blacklist.json"
_MAX_ENTRIES = 1000
_ENTRY_LIMITS = {"name": 128, "title": 128, "role": 64}


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


def _text(value: Any, key: str, default: str = "") -> str:
    if value is None and default:
        return default
    if not isinstance(value, str):
        raise SenderBlacklistError("Sender blacklist entry is invalid")
    normalized = value.strip()
    if len(normalized) > _ENTRY_LIMITS[key]:
        raise SenderBlacklistError("Sender blacklist entry is invalid")
    return normalized or default


def normalize_sender_blacklist_entry(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"name", "title", "email", "role"}:
        raise SenderBlacklistError("Sender blacklist entry is invalid")
    return {"name": _text(value["name"], "name"), "title": _text(value["title"], "title"), "email": normalize_sender_email(value["email"]), "role": _text(value["role"], "role", "User")}


def _path(storage_dir: Path) -> Path:
    return storage_dir / "interfaces" / _STATE_NAME


def load_sender_blacklist_entries(storage_dir: Path) -> list[dict[str, str]]:
    path = _path(storage_dir)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SenderBlacklistError("Sender blacklist state is malformed") from exc
    if not isinstance(payload, dict):
        raise SenderBlacklistError("Sender blacklist state is malformed")
    if set(payload) == {"emails"}:
        emails = payload["emails"]
        if not isinstance(emails, list) or len(emails) > _MAX_ENTRIES:
            raise SenderBlacklistError("Sender blacklist state is malformed")
        entries: Any = [{"name": "", "title": "", "email": email, "role": "User"} for email in emails]
    elif set(payload) == {"version", "entries"} and payload.get("version") == 2:
        entries = payload["entries"]
        if not isinstance(entries, list) or len(entries) > _MAX_ENTRIES:
            raise SenderBlacklistError("Sender blacklist state is malformed")
    else:
        raise SenderBlacklistError("Sender blacklist state is malformed")
    try:
        normalized = [normalize_sender_blacklist_entry(entry) for entry in entries]
    except SenderBlacklistError as exc:
        raise SenderBlacklistError("Sender blacklist state is malformed") from exc
    if len({entry["email"] for entry in normalized}) != len(normalized):
        raise SenderBlacklistError("Sender blacklist state is malformed")
    return sorted(normalized, key=lambda entry: entry["email"])


def load_sender_blacklist(storage_dir: Path) -> list[str]:
    return [entry["email"] for entry in load_sender_blacklist_entries(storage_dir)]


def _write(storage_dir: Path, entries: list[dict[str, str]]) -> None:
    path = _path(storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".rop_sender_blacklist-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"version": 2, "entries": entries}, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _locked(storage_dir: Path, operation: Any) -> Any:
    lock_path = _path(storage_dir).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return operation(load_sender_blacklist_entries(storage_dir))


def add_sender_blacklist_entry(storage_dir: Path, value: dict[str, Any]) -> tuple[dict[str, str], bool]:
    entry = normalize_sender_blacklist_entry(value)
    def operation(entries: list[dict[str, str]]) -> tuple[dict[str, str], bool]:
        if any(item["email"] == entry["email"] for item in entries):
            return entry, False
        if len(entries) >= _MAX_ENTRIES:
            raise SenderBlacklistError("Sender blacklist is full")
        _write(storage_dir, sorted([*entries, entry], key=lambda item: item["email"]))
        return entry, True
    return _locked(storage_dir, operation)


def update_sender_blacklist_entry(storage_dir: Path, original_email: Any, value: dict[str, Any]) -> tuple[dict[str, str], bool]:
    original = normalize_sender_email(original_email)
    entry = normalize_sender_blacklist_entry(value)
    def operation(entries: list[dict[str, str]]) -> tuple[dict[str, str], bool]:
        current = next((item for item in entries if item["email"] == original), None)
        if current is None:
            raise SenderBlacklistError("Sender blacklist entry was not found")
        if entry["email"] != original and any(item["email"] == entry["email"] for item in entries):
            raise SenderBlacklistError("Sender blacklist entry already exists")
        if current == entry:
            return entry, False
        _write(storage_dir, sorted([entry if item["email"] == original else item for item in entries], key=lambda item: item["email"]))
        return entry, True
    return _locked(storage_dir, operation)


def remove_sender_blacklist_email(storage_dir: Path, value: Any) -> tuple[str, bool]:
    email = normalize_sender_email(value)
    def operation(entries: list[dict[str, str]]) -> tuple[str, bool]:
        if not any(item["email"] == email for item in entries):
            return email, False
        _write(storage_dir, [item for item in entries if item["email"] != email])
        return email, True
    return _locked(storage_dir, operation)


def add_sender_blacklist_email(storage_dir: Path, value: Any) -> tuple[str, bool]:
    entry, changed = add_sender_blacklist_entry(storage_dir, {"name": "", "title": "", "email": value, "role": "User"})
    return entry["email"], changed


def sender_from_event(event: dict[str, Any]) -> str | None:
    for key in ("original_sender_email", "original_sender", "sender"):
        try:
            return normalize_sender_email(event.get(key))
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


def write_sender_blacklist_audit(storage_dir: Path, *, action_id: str, actor_id: str | None, outcome: str, email: str | None) -> None:
    interfaces = storage_dir / "interfaces"
    interfaces.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(email.encode("utf-8")).hexdigest() if email else None
    record = {"timestamp_utc": datetime.now(UTC).isoformat(), "action_id": action_id, "actor_id": actor_id or "unknown", "outcome": outcome, "email_sha256": digest}
    with (interfaces / "rop_sender_blacklist_audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")
