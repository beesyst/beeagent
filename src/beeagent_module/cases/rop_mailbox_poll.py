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
from beeagent_module.cases.rop_current_state import (
    build_rop_current_state,
    write_current_state,
)
from beeagent_module.cases.rop_dashboard import (
    build_rop_dashboard,
    refresh_rop_web_projection,
    write_rop_dashboard,
)
from beeagent_module.cases.rop_operator import run_rop_batch_case
from beeagent_module.cases.rop_recipient_routing import build_recipient_routing_artifact
from beeagent_module.cases.rop_writeback import (
    build_writeback_plan,
    execute_writeback_pending,
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


def _load_checkpoint(
    path: Path,
    source_id: str,
    folder: str,
    require_source: bool = True,
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise MailboxPollError(
            "Mailbox checkpoint is invalid; run rop poll --rebaseline"
        ) from exc
    if not isinstance(data, dict):
        raise MailboxPollError(
            "Mailbox checkpoint is invalid; run rop poll --rebaseline"
        )
    if data.get("version") != CHECKPOINT_VERSION or not isinstance(
        data.get("sources"), dict
    ):
        raise MailboxPollError(
            "Mailbox checkpoint is invalid; run rop poll --rebaseline"
        )
    if source_id not in data["sources"]:
        if require_source:
            raise MailboxPollError(
                "Mailbox checkpoint is stale or invalid; run rop poll --rebaseline"
            )
        return data
    entry = data["sources"][source_id]
    if (
        not isinstance(entry, dict)
        or entry.get("folder") != folder
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


def _is_poll_mailbox_source(source: dict[str, Any]) -> bool:
    return (
        source.get("source_type") == "mailbox_readonly"
        and source.get("authority") == "read_only"
    )


def _select_poll_sources(
    settings: dict[str, Any],
    source_id: str | None = None,
    all_sources: bool = False,
) -> list[dict[str, Any]]:
    if source_id and all_sources:
        raise MailboxPollError("--source-id and --all-sources cannot be used together")

    input_sources = settings["rop"]["sources"]

    if source_id:
        for source in input_sources:
            if source.get("source_id") != source_id:
                continue
            if not source.get("enabled", False):
                raise MailboxPollError(f"mailbox poll source '{source_id}' is disabled")
            if not _is_poll_mailbox_source(source):
                raise MailboxPollError(
                    f"mailbox poll source '{source_id}' must be read-only mailbox source"
                )
            return [source]
        raise MailboxPollError(
            f"mailbox poll source '{source_id}' not found in rop.sources"
        )

    if all_sources:
        enabled = [
            source
            for source in input_sources
            if source.get("enabled") is True and _is_poll_mailbox_source(source)
        ]
        if not enabled:
            raise MailboxPollError(
                "no enabled read-only mailbox sources configured for all-sources poll"
            )
        return enabled

    poll_source_id = settings["rop"]["mailbox_poll"]["source_id"]
    for source in input_sources:
        if source.get("source_id") == poll_source_id:
            return [source]
    raise MailboxPollError("rop.mailbox_poll.source_id not found in rop.sources")


def handle_mailbox_poll(
    settings: dict,
    storage_dir: Path,
    project_root: Path,
    logger: logging.Logger,
    rebaseline: bool = False,
    source_id: str | None = None,
    all_sources: bool | None = None,
) -> None:
    poll = settings["rop"]["mailbox_poll"]
    if not poll["enabled"]:
        logger.info("mailbox poll disabled")
        return

    if source_id and all_sources:
        raise MailboxPollError("--source-id and --all-sources cannot be used together")

    effective_all_sources = bool(all_sources) or (
        poll.get("sources_all", False) is True
    )
    if source_id:
        effective_all_sources = False

    selected = _select_poll_sources(
        settings,
        source_id=source_id,
        all_sources=effective_all_sources,
    )

    require_checkpoint_source = not (effective_all_sources or bool(source_id))

    if len(selected) == 1:
        processed = _poll_single_source(
            settings=settings,
            storage_dir=storage_dir,
            project_root=project_root,
            logger=logger,
            source=selected[0],
            rebaseline=rebaseline,
            require_checkpoint_source=require_checkpoint_source,
        )
        return

    successes: list[str] = []
    failures: list[str] = []
    processed_any = False
    for source in selected:
        source_key = str(source.get("source_id", "unknown"))
        try:
            processed_any = (
                _poll_single_source(
                    settings=settings,
                    storage_dir=storage_dir,
                    project_root=project_root,
                    logger=logger,
                    source=source,
                    rebaseline=rebaseline,
                    require_checkpoint_source=False,
                )
                or processed_any
            )
            successes.append(source_key)
        except Exception as exc:
            failures.append(source_key)
            logger.warning(
                "mailbox poll source failed: source_id=%s reason=%s",
                source_key,
                exc,
            )

    if failures and not successes:
        raise MailboxPollError(
            "mailbox poll failed for all selected sources: " + ", ".join(failures)
        )
    if failures:
        logger.warning(
            "mailbox poll completed with partial source failures: failed=%s",
            ",".join(failures),
        )


def _writeback_enabled(settings: dict[str, Any]) -> bool:
    return settings.get("bitrix", {}).get("writeback", {}).get("enabled") is True


def _poll_single_source(
    settings: dict,
    storage_dir: Path,
    project_root: Path,
    logger: logging.Logger,
    source: dict[str, Any],
    rebaseline: bool = False,
    require_checkpoint_source: bool = True,
) -> bool:
    source_id = str(source["source_id"])
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
            f"Missing required mailbox environment for poll source: source_id={source_id}"
        )
    if host.lower().startswith(("http://", "https://")) or "/" in host:
        raise MailboxPollError(
            f"Invalid IMAP host for poll source: source_id={source_id}"
        )
    client = ImapReadonlyMailboxClient(
        host, mailbox["port"], mailbox["use_ssl"], username, password
    )
    uidvalidity, available = client.uid_state(folder)
    path = _checkpoint_path(storage_dir)
    if rebaseline:
        data = _load_rebaseline_checkpoint(path)
    else:
        data = _load_checkpoint(
            path,
            source_id,
            folder,
            require_source=require_checkpoint_source,
        )
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
        return False
    if data is None:
        _write_checkpoint(
            path,
            {
                "version": CHECKPOINT_VERSION,
                "sources": {source_id: _entry(folder, uidvalidity, highest)},
            },
        )
        logger.info(
            "mailbox poll baseline initialized: source_id=%s folder=%s uidvalidity=%s uid=%s",
            source_id,
            folder,
            uidvalidity,
            highest,
        )
        return False
    if source_id not in data["sources"]:
        data["sources"][source_id] = _entry(folder, uidvalidity, highest)
        _write_checkpoint(path, data)
        logger.info(
            "mailbox poll baseline initialized for new source: source_id=%s folder=%s uidvalidity=%s uid=%s",
            source_id,
            folder,
            uidvalidity,
            highest,
        )
        return False
    checkpoint = data["sources"][source_id]
    if checkpoint["uidvalidity"] != uidvalidity:
        raise MailboxPollError(
            f"Mailbox UIDVALIDITY changed for source_id={source_id}; run rop poll --rebaseline"
        )
    pending = sorted(uid for uid in available if uid > checkpoint["last_processed_uid"])
    selected = pending[: source["items_max"]]
    if not selected:
        logger.info("mailbox poll: no new messages: source_id=%s", source_id)
        return False
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
    build_recipient_routing_artifact(
        storage_dir=storage_dir,
        run_id=run_id,
        settings=settings,
        logger=logger,
    )
    export_review_tsv_for_run(
        storage_dir=storage_dir,
        run_id=run_id,
        logger=logger,
    )
    writeback_enabled = _writeback_enabled(settings)
    if (
        settings["bitrix"]["enabled"]
        and settings["bitrix"]["reconciliation"]["enabled"]
    ):
        reconciliation = run_reconciliation(storage_dir, run_id, settings, logger)
        try:
            build_writeback_plan(
                storage_dir=storage_dir,
                run_id=run_id,
                settings=settings,
                logger=logger,
            )
        except Exception as exc:
            if writeback_enabled:
                raise MailboxPollError(
                    f"ROP write-back plan persistence failed: {exc}"
                ) from exc
            logger.warning(
                "ROP write-back plan persistence skipped: run_id=%s reason=%s",
                run_id,
                exc,
            )
        build_action_drafts(storage_dir, run_id, reconciliation, logger)
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
    refresh_rop_web_projection(
        storage_dir=storage_dir,
        periods=list(
            settings["rop"]["dashboard"].get(
                "periods", [settings["rop"]["dashboard"]["default_period"]]
            )
        ),
        run_id=run_id,
        logger=logger,
        is_new_run=True,
    )
    data["sources"][source_id] = _entry(folder, uidvalidity, selected[-1])
    _write_checkpoint(path, data)
    if writeback_enabled:
        try:
            execute_result = execute_writeback_pending(
                storage_dir=storage_dir,
                run_id=run_id,
                settings=settings,
                logger=logger,
                scope_run_id=run_id,
            )
            logger.info(
                "ROP write-back executed during poll: run_id=%s status=%s writes=%d",
                run_id,
                execute_result.get("status"),
                execute_result.get("writes_performed", 0),
            )
        except Exception as exc:
            logger.warning(
                "ROP write-back execute skipped after poll: run_id=%s reason=%s",
                run_id,
                exc,
            )
    logger.info(
        "mailbox poll completed: source_id=%s run_id=%s selected_count=%s",
        source_id,
        run_id,
        len(selected),
    )
    return True
