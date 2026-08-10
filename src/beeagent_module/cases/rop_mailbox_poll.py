from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from beeagent_module.adapters.mailbox import ImapReadonlyMailboxClient
from beeagent_module.cases.rop_action_drafts import build_action_drafts
from beeagent_module.cases.rop_bitrix_reconciliation import run_reconciliation
from beeagent_module.cases.rop_context_enrichment import (
    build_context_enrichment,
    write_context_enrichment_artifact,
)
from beeagent_module.cases.rop_current_state import (
    build_rop_current_state,
    write_current_state,
)
from beeagent_module.cases.rop_dashboard import build_rop_dashboard, write_rop_dashboard
from beeagent_module.cases.rop_operator import run_rop_batch_case
from beeagent_module.cases.rop_recommendations import (
    build_recommendations,
    build_routing_map,
)
from beeagent_module.core.rop_review_export import export_review_tsv_for_run

CHECKPOINT_VERSION = 1
CHECKPOINT_FILENAME = "rop_mailbox_checkpoint.json"


class MailboxPollError(RuntimeError):
    pass


class _PrefetchedMailboxClient:
    def __init__(self, messages: list[bytes]) -> None:
        self._messages = messages

    def fetch_latest(self, folder: str, items_max: int) -> list[bytes]:
        return self._messages


def _checkpoint_path(storage_dir: Path) -> Path:
    return storage_dir / "interfaces" / CHECKPOINT_FILENAME


def _load_checkpoint(path: Path, source_id: str, folder: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = data["sources"][source_id]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MailboxPollError(
            "Mailbox checkpoint is invalid; run rop poll --rebaseline"
        ) from exc
    if data.get("version") != CHECKPOINT_VERSION or not isinstance(entry, dict):
        raise MailboxPollError(
            "Mailbox checkpoint is invalid; run rop poll --rebaseline"
        )
    if (
        entry.get("folder") != folder
        or type(entry.get("uidvalidity")) is not int
        or entry["uidvalidity"] <= 0
        or type(entry.get("last_processed_uid")) is not int
        or entry["last_processed_uid"] < 0
    ):
        raise MailboxPollError(
            "Mailbox checkpoint is stale or invalid; run rop poll --rebaseline"
        )
    return data


def _load_rebaseline_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": CHECKPOINT_VERSION, "sources": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {"version": CHECKPOINT_VERSION, "sources": {}}
    if not isinstance(data, dict):
        return {"version": CHECKPOINT_VERSION, "sources": {}}
    if data.get("version") != CHECKPOINT_VERSION or not isinstance(
        data.get("sources"), dict
    ):
        return {"version": CHECKPOINT_VERSION, "sources": {}}
    return data


def _write_checkpoint(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".rop_mailbox_checkpoint.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _entry(folder: str, uidvalidity: int, uid: int) -> dict[str, Any]:
    return {
        "folder": folder,
        "uidvalidity": uidvalidity,
        "last_processed_uid": uid,
        "updated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def handle_mailbox_poll(
    settings: dict,
    storage_dir: Path,
    project_root: Path,
    logger: logging.Logger,
    rebaseline: bool = False,
) -> None:
    poll = settings["rop"]["mailbox_poll"]
    if not poll["enabled"]:
        logger.info("mailbox poll disabled")
        return
    source_id = poll["source_id"]
    source = next(
        source
        for source in settings["rop"]["sources"]
        if source["source_id"] == source_id
    )
    mailbox = source["mailbox"]
    folder = (
        os.getenv(
            mailbox.get("folder_env", ""),
            mailbox.get("folder") or "",
        )
        or ""
    ).strip()
    host = (
        os.getenv(
            mailbox.get("host_env", ""),
            mailbox.get("host") or "",
        )
        or ""
    ).strip()
    username = os.getenv(mailbox["username_env"], "").strip()
    password = os.getenv(mailbox["password_env"], "").strip()
    if not all((folder, host, username, password)):
        raise MailboxPollError(
            "Missing required mailbox environment for configured poll source"
        )
    if host.lower().startswith(("http://", "https://")) or "/" in host:
        raise MailboxPollError("Invalid IMAP host for configured poll source")
    client = ImapReadonlyMailboxClient(
        host, mailbox["port"], mailbox["use_ssl"], username, password
    )
    uidvalidity, available = client.uid_state(folder)
    path = _checkpoint_path(storage_dir)
    if rebaseline:
        data = _load_rebaseline_checkpoint(path)
    else:
        data = _load_checkpoint(path, source_id, folder)
    highest = max(available, default=0)
    if rebaseline:
        data = data or {"version": CHECKPOINT_VERSION, "sources": {}}
        data["sources"][source_id] = _entry(folder, uidvalidity, highest)
        _write_checkpoint(path, data)
        logger.info(
            "mailbox poll baseline initialized: source_id=%s folder=%s uidvalidity=%s uid=%s",
            source_id,
            folder,
            uidvalidity,
            highest,
        )
        return
    if data is None:
        _write_checkpoint(
            path,
            {
                "version": CHECKPOINT_VERSION,
                "sources": {source_id: _entry(folder, uidvalidity, highest)},
            },
        )
        logger.info("mailbox poll baseline initialized")
        return
    checkpoint = data["sources"][source_id]
    if checkpoint["uidvalidity"] != uidvalidity:
        raise MailboxPollError("Mailbox UIDVALIDITY changed; run rop poll --rebaseline")
    pending = sorted(uid for uid in available if uid > checkpoint["last_processed_uid"])
    selected = pending[: source["items_max"]]
    if not selected:
        logger.info("mailbox poll: no new messages")
        return
    messages = client.fetch_uids(
        folder,
        selected,
        expected_uidvalidity=uidvalidity,
    )
    result = run_rop_batch_case(
        settings=settings,
        storage_dir=storage_dir,
        project_root=project_root,
        logger=logger,
        source_id=source_id,
        mailbox_client_factory=lambda _source: _PrefetchedMailboxClient(messages),
    )
    if str(result.get("status", "")).lower() in {"degraded", "error"} or str(
        result.get("module_status", "")
    ).lower() in {"degraded", "error"}:
        raise MailboxPollError("ROP poll batch did not complete successfully")
    source_result = result.get("source")
    if isinstance(source_result, dict) and source_result.get("malformed_count", 0) > 0:
        raise MailboxPollError("ROP poll batch contains malformed mailbox messages")
    run_id = str(result["run_id"])
    export_review_tsv_for_run(
        storage_dir=storage_dir,
        run_id=run_id,
        logger=logger,
    )
    if (
        settings["bitrix"]["enabled"]
        and settings["bitrix"]["reconciliation"]["enabled"]
    ):
        reconciliation = run_reconciliation(storage_dir, run_id, settings, logger)
        if reconciliation.get("status") != "ok":
            raise MailboxPollError(
                "Bitrix reconciliation did not complete successfully"
            )
        build_action_drafts(storage_dir, run_id, reconciliation, logger)
    enrichment = build_context_enrichment(
        storage_dir=storage_dir, run_id=run_id, logger=logger
    )
    write_context_enrichment_artifact(
        storage_dir=storage_dir, run_id=run_id, artifact=enrichment, logger=logger
    )
    build_routing_map(settings, storage_dir, logger)
    build_recommendations(storage_dir, run_id, settings, logger)
    state = build_rop_current_state(storage_dir, run_id, logger)
    write_current_state(storage_dir, run_id, state, logger)
    dashboard = build_rop_dashboard(
        storage_dir,
        settings["rop"]["dashboard"]["default_period"],
        logger,
        run_id,
        aggregate_runs=True,
    )
    write_rop_dashboard(storage_dir, dashboard, logger)
    data["sources"][source_id] = _entry(folder, uidvalidity, selected[-1])
    _write_checkpoint(path, data)
    logger.info(
        "mailbox poll completed: source_id=%s run_id=%s selected_count=%s",
        source_id,
        run_id,
        len(selected),
    )
