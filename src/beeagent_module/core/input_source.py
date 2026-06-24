from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

from beeagent_module.adapters.mailbox import (
    ImapReadonlyMailboxClient,
    MailboxAuthError,
    MailboxReadonlyClient,
    MailboxUnavailableError,
)


class InputSourceError(RuntimeError):
    def __init__(self, message: str, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


def find_active_rop_source(input_sources: list[dict]) -> dict:
    if not input_sources:
        raise RuntimeError("rop.sources is empty: no input source declared in config")

    enabled = [s for s in input_sources if s.get("enabled", False)]

    if not enabled:
        raise RuntimeError(
            "rop.sources: no enabled source found; "
            "set enabled: true for exactly one source"
        )

    if len(enabled) > 1:
        ids = ", ".join(str(s.get("source_id", "?")) for s in enabled)
        raise RuntimeError(
            f"rop.sources: multiple enabled sources found ({ids}); "
            "v0 supports exactly one enabled source"
        )

    return enabled[0]


def select_rop_sources(
    input_sources: list[dict],
    source_id: str | None = None,
    all_sources: bool = False,
) -> tuple[list[dict], str]:
    if source_id and all_sources:
        raise RuntimeError("--source-id and --all-sources cannot be used together")

    if source_id:
        for source in input_sources:
            if source.get("source_id") != source_id:
                continue
            if not source.get("enabled", False):
                raise RuntimeError(f"rop.sources: source '{source_id}' is disabled")
            return [source], "single_explicit"
        raise RuntimeError(f"rop.sources: source '{source_id}' not found")

    if all_sources:
        enabled = [source for source in input_sources if source.get("enabled", False)]
        if not enabled:
            raise RuntimeError(
                "rop.sources: no enabled source found; "
                "--all-sources requires at least one enabled source"
            )
        return enabled, "all_enabled"

    return [find_active_rop_source(input_sources)], "single_active"


def load_rop_source(
    source: dict,
    project_root: Path,
    logger: logging.Logger,
    mailbox_client_factory: Callable[[dict], MailboxReadonlyClient] | None = None,
) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
    source_type = source.get("source_type")

    if source_type == "json_batch":
        try:
            events, metadata = load_json_batch(
                source=source,
                project_root=project_root,
                logger=logger,
            )
        except RuntimeError as exc:
            raise InputSourceError(
                str(exc),
                diagnostics=_make_source_diagnostics(
                    source=source,
                    status="degraded",
                    reason=_classify_json_batch_error(exc),
                ),
            ) from exc
        diagnostics = _make_source_diagnostics(
            source=source,
            status="ok",
            reason=None,
            fetched_count=metadata["raw_item_count"],
            processed_count=metadata["loaded_item_count"],
            skipped_count=metadata["raw_item_count"] - metadata["loaded_item_count"],
            malformed_count=0,
            loaded_at=metadata["loaded_at"],
        )
        return events, metadata, diagnostics

    if source_type == "mailbox_readonly":
        return load_mailbox_readonly(
            source=source,
            logger=logger,
            mailbox_client_factory=mailbox_client_factory,
        )

    raise InputSourceError(
        f"Unsupported rop source_type: {source_type}",
        diagnostics=_make_source_diagnostics(
            source=source,
            status="degraded",
            reason="unsupported_source_type",
        ),
    )


def _resolve_project_file_path(project_root: Path, raw_path: str) -> Path:
    if not raw_path:
        raise RuntimeError("batch.path is empty")

    candidate = (project_root / raw_path).resolve()
    root = project_root.resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"batch.path must stay inside project root: {raw_path}"
        ) from exc

    return candidate


def load_mailbox_readonly(
    source: dict,
    logger: logging.Logger,
    mailbox_client_factory: Callable[[dict], MailboxReadonlyClient] | None = None,
) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
    source_id = str(source.get("source_id", "unknown"))
    items_max = source.get("items_max")
    if not isinstance(items_max, int) or items_max <= 0:
        raise InputSourceError(
            f"rop.sources source_id={source_id}: items_max must be int > 0",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_items_max",
            ),
        )

    mailbox_cfg = source.get("mailbox")
    if not isinstance(mailbox_cfg, dict):
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox must be a mapping",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )

    username_env = mailbox_cfg.get("username_env")
    password_env = mailbox_cfg.get("password_env")
    if not isinstance(username_env, str) or not username_env:
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox.username_env is empty",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )
    if not isinstance(password_env, str) or not password_env:
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox.password_env is empty",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )

    username = os.getenv(username_env, "").strip()
    password = os.getenv(password_env, "").strip()
    if not username or not password:
        raise InputSourceError(
            "mailbox credentials missing in env",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="missing_credentials",
            ),
        )

    factory = mailbox_client_factory or _default_mailbox_client_factory

    try:
        raw_messages = factory(source).fetch_latest(
            folder=str(mailbox_cfg["folder"]),
            items_max=items_max,
        )
    except MailboxAuthError as exc:
        raise InputSourceError(
            str(exc),
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="auth_failure",
            ),
        ) from exc
    except MailboxUnavailableError as exc:
        raise InputSourceError(
            str(exc),
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="mailbox_unavailable",
            ),
        ) from exc

    events: list[dict[str, Any]] = []
    malformed_count = 0

    for index, raw_message in enumerate(raw_messages):
        try:
            events.append(
                _normalize_mailbox_message(
                    raw_message=raw_message,
                    source=source,
                    position=index,
                )
            )
        except ValueError as exc:
            malformed_count += 1
            logger.warning(
                "mailbox_readonly source_id=%s: skipped malformed message index=%d reason=%s",
                source_id,
                index,
                exc,
            )

    if raw_messages and not events:
        raise InputSourceError(
            "all mailbox messages were malformed",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="all_messages_malformed",
                fetched_count=len(raw_messages),
                processed_count=0,
                skipped_count=len(raw_messages),
                malformed_count=malformed_count,
            ),
        )

    mailbox_details = {
        "host": str(mailbox_cfg["host"]),
        "port": int(mailbox_cfg["port"]),
        "use_ssl": bool(mailbox_cfg["use_ssl"]),
        "folder": str(mailbox_cfg["folder"]),
    }

    loaded_at = datetime.now(timezone.utc).isoformat()
    diagnostics = _make_source_diagnostics(
        source=source,
        status="ok",
        reason="empty_inbox" if not raw_messages else None,
        fetched_count=len(raw_messages),
        processed_count=len(events),
        skipped_count=max(len(raw_messages) - len(events), 0),
        malformed_count=malformed_count,
        loaded_at=loaded_at,
    )

    metadata = {
        "source_id": source_id,
        "source_type": "mailbox_readonly",
        "source_role": str(source["source_role"]),
        "client_id": str(source["client_id"]),
        "source_display_name": str(source["display_name"]),
        "authority": source.get("authority", "read_only"),
        "mailbox": mailbox_details,
        "mailbox_folder": mailbox_details["folder"],
        "period": _derive_mailbox_period(events=events, loaded_at=loaded_at),
        "raw_item_count": len(raw_messages),
        "loaded_item_count": len(events),
        "fetched_count": len(raw_messages),
        "loaded_count": len(events),
        "malformed_count": malformed_count,
        "items_max": items_max,
        "loaded_at": loaded_at,
    }

    logger.info(
        "mailbox_readonly loaded: source_id=%s host=%s folder=%s fetched=%d loaded=%d malformed=%d",
        source_id,
        mailbox_details["host"],
        mailbox_details["folder"],
        len(raw_messages),
        len(events),
        malformed_count,
    )

    return events, metadata, diagnostics


def _default_mailbox_client_factory(source: dict) -> MailboxReadonlyClient:
    mailbox_cfg = source["mailbox"]
    username = os.getenv(str(mailbox_cfg["username_env"]), "").strip()
    password = os.getenv(str(mailbox_cfg["password_env"]), "").strip()

    return ImapReadonlyMailboxClient(
        host=str(mailbox_cfg["host"]),
        port=int(mailbox_cfg["port"]),
        use_ssl=bool(mailbox_cfg["use_ssl"]),
        username=username,
        password=password,
    )


def _normalize_mailbox_message(
    raw_message: bytes,
    source: dict,
    position: int,
) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    source_id = str(source.get("source_id", "unknown"))

    message_id = _clean_header_value(message.get("Message-ID"))
    event_id = message_id or _build_fallback_event_id(
        source_id=source_id,
        position=position,
        raw_message=raw_message,
    )

    body_preview = _extract_body_preview(message)
    sender_list = _extract_addresses(message.get_all("From", []))
    to_list = _extract_addresses(message.get_all("To", []))
    cc_list = _extract_addresses(message.get_all("Cc", []))
    attachments = _extract_attachment_metadata(message)
    subject = _clean_header_value(message.get("Subject"))

    if (
        not message_id
        and not sender_list
        and not to_list
        and not cc_list
        and not subject
    ):
        raise ValueError("message missing identifying headers")

    return {
        "event_id": event_id,
        "source": "mailbox_readonly",
        "source_id": source_id,
        "message_id": message_id,
        "sender": sender_list[0] if sender_list else "",
        "to": to_list,
        "cc": cc_list,
        "subject": subject,
        "date": _normalize_message_date(message.get("Date")),
        "body_preview": body_preview,
        "attachments": attachments,
    }


def _extract_body_preview(message: Any) -> str:
    body_parts: list[str] = []

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() != "text/plain":
                continue
            payload = part.get_content()
            if isinstance(payload, str) and payload.strip():
                body_parts.append(payload)
    else:
        payload = message.get_content()
        if isinstance(payload, str) and payload.strip():
            body_parts.append(payload)

    normalized = _sanitize_text("\n".join(body_parts))
    return normalized[:1000]


def _extract_attachment_metadata(message: Any) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []

    for part in message.iter_attachments():
        payload = part.get_payload(decode=False)
        size: int | None = None
        if isinstance(payload, str):
            size = len(payload.encode("utf-8", errors="ignore"))
        elif isinstance(payload, bytes):
            size = len(payload)

        filename = part.get_filename() or ""
        content_type = part.get_content_type()

        if _is_blocked_email_attachment(filename=filename, content_type=content_type):
            continue

        item: dict[str, Any] = {
            "filename": filename,
            "content_type": content_type,
            "size": size,
        }
        attachments.append(item)

    return attachments


def _extract_addresses(headers: list[str]) -> list[str]:
    return [addr for _name, addr in getaddresses(headers) if addr]


def _normalize_message_date(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""

    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError, IndexError:
        return _clean_header_value(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).isoformat()


def _derive_mailbox_period(events: list[dict[str, Any]], loaded_at: str) -> str:
    for event in events:
        raw_date = event.get("date")
        if not isinstance(raw_date, str) or not raw_date:
            continue
        try:
            parsed = datetime.fromisoformat(raw_date)
        except ValueError:
            continue
        return parsed.astimezone(timezone.utc).strftime("%Y-%m")

    try:
        loaded_dt = datetime.fromisoformat(loaded_at)
    except ValueError:
        loaded_dt = datetime.now(timezone.utc)

    return loaded_dt.astimezone(timezone.utc).strftime("%Y-%m")


def _build_fallback_event_id(source_id: str, position: int, raw_message: bytes) -> str:
    digest = hashlib.sha256(raw_message).hexdigest()[:16]
    return f"{source_id}-{position}-{digest}"


def _clean_header_value(value: Any) -> str:
    if value is None:
        return ""
    return _sanitize_text(str(value))


def _sanitize_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    return compact


def _is_blocked_email_attachment(filename: str, content_type: str) -> bool:
    normalized_filename = filename.strip().lower()
    normalized_content_type = content_type.strip().lower()
    return (
        normalized_filename.endswith(".eml")
        or normalized_content_type == "message/rfc822"
    )


def _make_source_diagnostics(
    source: dict,
    status: str,
    reason: str | None,
    fetched_count: int = 0,
    processed_count: int = 0,
    skipped_count: int = 0,
    malformed_count: int = 0,
    loaded_at: str | None = None,
) -> dict[str, Any]:
    mailbox_cfg = source.get("mailbox") if isinstance(source, dict) else None
    mailbox_folder = None
    if isinstance(mailbox_cfg, dict):
        folder = mailbox_cfg.get("folder")
        if isinstance(folder, str) and folder:
            mailbox_folder = folder

    return {
        "source_id": str(source.get("source_id", "unknown")),
        "source_type": str(source.get("source_type", "unknown")),
        "source_role": str(source.get("source_role", "")),
        "client_id": str(source.get("client_id", "")),
        "source_display_name": str(source.get("display_name", "")),
        "authority": str(source.get("authority", "")),
        "mailbox_folder": mailbox_folder,
        "items_max": source.get("items_max"),
        "status": status,
        "reason": reason,
        "fetched_count": fetched_count,
        "loaded_count": processed_count,
        "processed_count": processed_count,
        "skipped_count": skipped_count,
        "malformed_count": malformed_count,
        "loaded_at": loaded_at or datetime.now(timezone.utc).isoformat(),
    }


def _classify_json_batch_error(exc: RuntimeError) -> str:
    message = str(exc).lower()
    if "not found" in message:
        return "batch_file_not_found"
    if "not valid json" in message:
        return "invalid_batch_json"
    if "top-level json object" in message or "'items' as a list" in message:
        return "invalid_batch_shape"
    if "batch.path" in message:
        return "invalid_batch_path"
    if "batch.period" in message:
        return "invalid_batch_period"
    if "items_max" in message:
        return "invalid_items_max"
    return "json_batch_load_error"


def load_json_batch(
    source: dict,
    project_root: Path,
    logger: logging.Logger,
) -> tuple[list[dict], dict[str, Any]]:
    source_id: str = source.get("source_id", "unknown")

    items_max = source.get("items_max")
    if not isinstance(items_max, int) or items_max <= 0:
        raise RuntimeError(
            f"rop.sources source_id={source_id}: items_max must be int > 0"
        )

    batch_cfg = source.get("batch")
    if not isinstance(batch_cfg, dict):
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch must be a mapping"
        )

    raw_path = batch_cfg.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        raise RuntimeError(f"rop.sources source_id={source_id}: batch.path is empty")

    period = batch_cfg.get("period")
    if not isinstance(period, str) or not period:
        raise RuntimeError(f"rop.sources source_id={source_id}: batch.period is empty")

    batch_path = _resolve_project_file_path(project_root, raw_path)

    if not batch_path.exists():
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch file not found: {raw_path}"
        )

    try:
        raw = json.loads(batch_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"rop.sources source_id={source_id}: batch file is not valid JSON: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise RuntimeError(
            f"rop.sources source_id={source_id}: "
            "batch file must contain a top-level JSON object"
        )

    items = raw.get("items")
    if not isinstance(items, list):
        raise RuntimeError(
            f"rop.sources source_id={source_id}: "
            "batch file must contain 'items' as a list"
        )

    file_period = raw.get("period")
    effective_period = (
        file_period if isinstance(file_period, str) and file_period else period
    )

    events = _normalize_batch_items(
        items=items,
        source_id=source_id,
        items_max=items_max,
        logger=logger,
    )

    metadata: dict[str, Any] = {
        "source_id": source_id,
        "source_type": "json_batch",
        "source_role": str(source["source_role"]),
        "client_id": str(source["client_id"]),
        "source_display_name": str(source["display_name"]),
        "authority": source.get("authority", "read_only"),
        "batch_path": raw_path,
        "period": effective_period,
        "raw_item_count": len(items),
        "loaded_item_count": len(events),
        "fetched_count": len(items),
        "loaded_count": len(events),
        "malformed_count": 0,
        "mailbox_folder": None,
        "items_max": items_max,
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "json_batch loaded: source_id=%s path=%s raw_items=%d loaded=%d period=%s",
        source_id,
        raw_path,
        len(items),
        len(events),
        effective_period,
    )

    return events, metadata


def _normalize_batch_items(
    items: list[Any],
    source_id: str,
    items_max: int,
    logger: logging.Logger,
) -> list[dict]:
    valid: list[dict] = []
    skipped = 0

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            logger.warning(
                "json_batch source_id=%s: item[%d] is not a dict, skipped",
                source_id,
                idx,
            )
            skipped += 1
            continue
        valid.append(_sanitize_batch_item(item))

    if skipped:
        logger.warning(
            "json_batch source_id=%s: skipped %d non-dict items",
            source_id,
            skipped,
        )

    truncated = valid[:items_max]

    if len(valid) > items_max:
        logger.info(
            "json_batch source_id=%s: truncated to items_max=%d (total valid=%d)",
            source_id,
            items_max,
            len(valid),
        )

    return truncated


def _sanitize_batch_item(item: dict[str, Any]) -> dict[str, Any]:
    blocked_top_level_keys = {
        "raw_eml",
        "raw_message",
        "attachment_content",
        "content",
        "content_bytes",
        "payload_bytes",
    }

    sanitized = {
        key: value for key, value in item.items() if key not in blocked_top_level_keys
    }

    attachments = sanitized.get("attachments")
    if isinstance(attachments, list):
        safe_attachments = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue

            safe_attachment = {
                key: value
                for key, value in attachment.items()
                if key not in blocked_top_level_keys
            }
            safe_attachments.append(safe_attachment)

        sanitized["attachments"] = safe_attachments

    return sanitized
