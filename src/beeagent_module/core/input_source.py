from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any

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


def _normalized_mailbox_value(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _resolve_mailbox_value(
    mailbox_cfg: dict[str, Any],
    env_key: str,
    direct_key: str,
) -> tuple[str, str]:
    env_name = _normalized_mailbox_value(mailbox_cfg.get(env_key))
    if env_name:
        return os.getenv(env_name, "").strip(), env_name
    return _normalized_mailbox_value(mailbox_cfg.get(direct_key)), ""


def _is_invalid_mailbox_host(host: str) -> bool:
    lowered = host.lower()
    return (
        lowered.startswith("http://") or lowered.startswith("https://") or "/" in host
    )


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
    email_preview_body_chars_max: int,
    mailbox_client_factory: Callable[[dict], MailboxReadonlyClient] | None = None,
) -> tuple[list[dict], dict[str, Any], dict[str, Any]]:
    source_type = source.get("source_type")

    if source_type == "json_batch":
        try:
            events, metadata = load_json_batch(
                source=source,
                project_root=project_root,
                logger=logger,
                email_preview_body_chars_max=email_preview_body_chars_max,
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
            email_preview_body_chars_max=email_preview_body_chars_max,
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
    email_preview_body_chars_max: int,
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

    username_env = _normalized_mailbox_value(mailbox_cfg.get("username_env"))
    password_env = _normalized_mailbox_value(mailbox_cfg.get("password_env"))
    if not username_env:
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox.username_env is empty",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )
    if not password_env:
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox.password_env is empty",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )

    host, host_env_name = _resolve_mailbox_value(mailbox_cfg, "host_env", "host")
    folder, folder_env_name = _resolve_mailbox_value(
        mailbox_cfg, "folder_env", "folder"
    )
    if not host:
        missing_key = host_env_name or "mailbox.host"
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox host is empty ({missing_key})",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )
    if _is_invalid_mailbox_host(host):
        invalid_key = host_env_name or "mailbox.host"
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox host must be IMAP host, not URL ({invalid_key})",
            diagnostics=_make_source_diagnostics(
                source=source,
                status="degraded",
                reason="invalid_mailbox_config",
            ),
        )
    if not folder:
        missing_key = folder_env_name or "mailbox.folder"
        raise InputSourceError(
            f"rop.sources source_id={source_id}: mailbox folder is empty ({missing_key})",
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
            folder=folder,
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
                    email_preview_body_chars_max=email_preview_body_chars_max,
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

    events = _sort_events_by_date_desc(events)
    events = events[:items_max]

    date_fallback_count = sum(1 for e in events if e.get("_date_fallback"))
    if date_fallback_count > 0:
        logger.warning(
            "mailbox_readonly source_id=%s: %d event(s) had no reliable date, used UID/order fallback",
            source_id,
            date_fallback_count,
        )

    mailbox_details = {
        "host": host,
        "port": int(mailbox_cfg["port"]),
        "use_ssl": bool(mailbox_cfg["use_ssl"]),
        "folder": folder,
    }

    loaded_at = datetime.now(UTC).isoformat()
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
    host, _ = _resolve_mailbox_value(mailbox_cfg, "host_env", "host")
    username = os.getenv(str(mailbox_cfg["username_env"]), "").strip()
    password = os.getenv(str(mailbox_cfg["password_env"]), "").strip()

    return ImapReadonlyMailboxClient(
        host=host,
        port=int(mailbox_cfg["port"]),
        use_ssl=bool(mailbox_cfg["use_ssl"]),
        username=username,
        password=password,
    )


_TRANSPORT_PREFIXES: tuple[tuple[str, str], ...] = (
    ("[AUTO-FWD]", "auto_fwd"),
    ("AUTO-FWD:", "auto_fwd"),
    ("FWD:", "fwd"),
    ("FW:", "fwd"),
    ("RE:", "re"),
    ("*** SPAM ***", "spam"),
)
_FORWARDED_FORM_EMAIL_RE = re.compile(
    r"^Email\s*:\s*(.+)",
    re.IGNORECASE,
)
_FORWARDED_ORIGINAL_SENDER_RE = re.compile(
    r"^Оригинальный\s*отправитель\s*:\s*(.+)",
    re.IGNORECASE,
)
_FORWARDED_FROM_RE = re.compile(
    r"^От\s*кого\s*:\s*(.+)",
    re.IGNORECASE,
)
_FORWARDED_RECIPIENT_RE = re.compile(
    r"^(?:Оригинальный\s*адрес\s*получения|Кому)\s*:\s*(.+)",
    re.IGNORECASE,
)
_FORWARDED_DATE_RE = re.compile(
    r"^Дата\s*:\s*(.+)",
    re.IGNORECASE,
)
_FORWARDED_X_EMAIL_ID_RE = re.compile(
    r"^X-Email-ID\s*:\s*(.+)",
    re.IGNORECASE,
)
_FORWARDED_MARKER_RE = re.compile(
    r"^-{2,}\s*(?:Original|Пересылаемое|Forwarded|Переадресованное)\s*(?:Message|сообщение|message)?\s*-{2,}",
    re.IGNORECASE,
)


_ALLOWED_TRANSPORT_LABELS = frozenset({"auto_fwd", "fwd", "re", "spam"})


def _normalize_transport_labels(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        if item not in _ALLOWED_TRANSPORT_LABELS:
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _extract_clean_subject(subject: Any) -> str:
    if not isinstance(subject, str) or not subject.strip():
        return ""
    result = subject.strip()
    changed = True
    while changed:
        changed = False
        for prefix, _label in _TRANSPORT_PREFIXES:
            if result.upper().startswith(prefix.upper()):
                result = result[len(prefix) :].strip()
                changed = True
                break
    return _sanitize_text(result)


def _extract_transport_labels(subject: Any) -> list[str]:
    if not isinstance(subject, str) or not subject.strip():
        return []
    result = subject.strip()
    labels: list[str] = []
    seen: set[str] = set()
    changed = True
    while changed:
        changed = False
        for prefix, label in _TRANSPORT_PREFIXES:
            if result.upper().startswith(prefix.upper()):
                result = result[len(prefix) :].strip()
                if label not in seen:
                    seen.add(label)
                    labels.append(label)
                changed = True
                break
    return labels


def _extract_email_from_sender(sender_display: str) -> str:
    if not isinstance(sender_display, str) or not sender_display.strip():
        return ""
    try:
        pairs = getaddresses([sender_display])
        for _name, addr in pairs:
            if addr and "@" in addr:
                return addr.strip()
    except TypeError, ValueError, IndexError:
        pass
    return ""


def _extract_forwarded_wrapper_fields(
    body_text: str,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "form_email": "",
        "original_sender": "",
        "original_sender_email": "",
        "original_recipient": "",
        "original_message_date": "",
        "date_source": "",
        "x_email_id": "",
        "forwarded_wrapper": False,
    }
    if not isinstance(body_text, str) or not body_text.strip():
        return result

    lines = body_text.splitlines()
    found_any = False
    marker_found = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if _FORWARDED_MARKER_RE.match(stripped):
            found_any = True
            marker_found = True
            continue

        match = _FORWARDED_FORM_EMAIL_RE.match(stripped)
        if match and not result["form_email"]:
            result["form_email"] = _sanitize_text(match.group(1))
            found_any = True
            continue

        match = _FORWARDED_ORIGINAL_SENDER_RE.match(stripped)
        if match and not result["original_sender"]:
            result["original_sender"] = _sanitize_text(match.group(1))
            found_any = True
            continue

        match = _FORWARDED_FROM_RE.match(stripped)
        if match and not result["original_sender"]:
            result["original_sender"] = _sanitize_text(match.group(1))
            found_any = True
            continue

        match = _FORWARDED_RECIPIENT_RE.match(stripped)
        if match and not result["original_recipient"]:
            result["original_recipient"] = _sanitize_text(match.group(1))
            found_any = True
            continue

        match = _FORWARDED_DATE_RE.match(stripped)
        if match and not result["original_message_date"]:
            date_str = _sanitize_text(match.group(1))
            parsed = _parse_original_date(date_str, logger=logger)
            if parsed:
                result["original_message_date"] = parsed
                result["date_source"] = "original_forwarded_date"
            found_any = True
            continue

        match = _FORWARDED_X_EMAIL_ID_RE.match(stripped)
        if match and not result["x_email_id"]:
            result["x_email_id"] = _sanitize_text(match.group(1))
            found_any = True
            continue

    if not _has_forwarded_wrapper_evidence(marker_found, result):
        result["forwarded_wrapper"] = False
        result["form_email"] = ""
        result["original_sender"] = ""
        result["original_sender_email"] = ""
        result["original_recipient"] = ""
        result["original_message_date"] = ""
        result["date_source"] = ""
        result["x_email_id"] = ""
    else:
        result["forwarded_wrapper"] = True
        if not result["original_sender"] and result["form_email"]:
            result["original_sender"] = result["form_email"]
        if result["original_sender"]:
            result["original_sender_email"] = _extract_email_from_sender(
                result["original_sender"]
            )
    return result


def _has_forwarded_wrapper_evidence(
    marker_found: bool,
    fields: dict[str, Any],
) -> bool:
    if marker_found:
        return True
    forwarded_field_keys = (
        "form_email",
        "original_sender",
        "original_recipient",
        "original_message_date",
        "x_email_id",
    )
    count = sum(1 for k in forwarded_field_keys if fields.get(k))
    if count == 1 and fields.get("form_email"):
        return False
    return count >= 2


def _parse_original_date(
    date_str: str,
    logger: logging.Logger | None = None,
) -> str:
    if not date_str:
        return ""
    try:
        parsed = parsedate_to_datetime(date_str)
    except TypeError, ValueError, IndexError:
        if logger:
            logger.debug("failed to parse forwarded date: %s", date_str[:200])
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _extract_raw_body_text(message: Any, chars_max: int) -> str:
    text_parts: list[str] = []
    remaining = max(0, chars_max)

    def collect_text(part: Any) -> None:
        nonlocal remaining

        if remaining <= 0:
            return
        if part.get_content_disposition() == "attachment":
            return

        content_type = str(part.get_content_type() or "").strip().lower()
        if content_type != "text/plain":
            return

        payload = part.get_content()
        if isinstance(payload, str) and payload.strip():
            bounded = payload[:remaining]
            text_parts.append(bounded)
            remaining -= len(bounded)

    if message.is_multipart():
        for part in message.walk():
            if remaining <= 0:
                break
            if part.is_multipart():
                continue
            collect_text(part)
    else:
        collect_text(message)

    return "\n".join(text_parts)


def _normalize_mailbox_message(
    raw_message: bytes,
    source: dict,
    position: int,
    email_preview_body_chars_max: int,
) -> dict[str, Any]:
    message = BytesParser(policy=policy.default).parsebytes(raw_message)
    source_id = str(source.get("source_id", "unknown"))

    message_id = _clean_header_value(message.get("Message-ID"))
    event_id = message_id or _build_fallback_event_id(
        source_id=source_id,
        position=position,
        raw_message=raw_message,
    )

    body_preview_fields = _extract_body_preview(
        message,
        email_preview_body_chars_max=email_preview_body_chars_max,
    )
    sender_list = _extract_addresses(message, "From")
    to_list = _extract_addresses(message, "To")
    cc_list = _extract_addresses(message, "Cc")
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

    date_raw = message.get("Date")
    received_at = _normalize_message_date(date_raw) or None

    clean_subject = _extract_clean_subject(subject)
    transport_labels = _extract_transport_labels(subject)
    spam_label_present = "spam" in transport_labels
    reply_label_present = "re" in transport_labels

    raw_body_text = _extract_raw_body_text(
        message,
        chars_max=email_preview_body_chars_max,
    )
    forwarded_fields = _extract_forwarded_wrapper_fields(raw_body_text)

    original_message_date = forwarded_fields.get("original_message_date", "")
    if original_message_date:
        date_value = original_message_date
        date_source = "original_forwarded_date"
        date_fallback = False
    elif received_at:
        date_value = received_at
        date_source = "mailbox_header"
        date_fallback = False
    else:
        date_value = ""
        date_source = "fallback_order"
        date_fallback = True

    return {
        "event_id": event_id,
        "source": "mailbox_readonly",
        "source_id": source_id,
        "message_id": message_id,
        "sender": sender_list[0] if sender_list else "",
        "to": to_list,
        "cc": cc_list,
        "subject": subject,
        "clean_subject": clean_subject,
        "transport_labels": transport_labels,
        "spam_label_present": spam_label_present,
        "reply_label_present": reply_label_present,
        "forwarded_wrapper": forwarded_fields["forwarded_wrapper"],
        "form_email": forwarded_fields["form_email"],
        "original_sender": forwarded_fields["original_sender"],
        "original_sender_email": forwarded_fields["original_sender_email"],
        "original_recipient": forwarded_fields["original_recipient"],
        "original_message_date": original_message_date,
        "date_source": date_source,
        "x_email_id": forwarded_fields["x_email_id"],
        "date": date_value,
        "received_at": received_at,
        "_date_fallback": date_fallback,
        **body_preview_fields,
        "attachments": attachments,
    }


def _extract_body_preview(
    message: Any,
    email_preview_body_chars_max: int,
) -> dict[str, Any]:
    text_parts: list[str] = []
    html_parts: list[str] = []

    def collect_part(part: Any) -> None:
        if part.get_content_disposition() == "attachment":
            return

        content_type = str(part.get_content_type() or "").strip().lower()
        if content_type not in {"text/plain", "text/html"}:
            return

        payload = part.get_content()
        if not isinstance(payload, str) or not payload.strip():
            return

        if content_type == "text/plain":
            text_parts.append(payload)
        elif content_type == "text/html":
            html_parts.append(payload)

    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            collect_part(part)
    else:
        collect_part(message)

    if text_parts:
        return _build_body_preview_metadata(
            text="\n".join(text_parts),
            source="text_plain",
            email_preview_body_chars_max=email_preview_body_chars_max,
        )

    if html_parts:
        return _build_body_preview_metadata(
            text=_strip_html("\n".join(html_parts)),
            source="html_text",
            email_preview_body_chars_max=email_preview_body_chars_max,
        )

    return _empty_body_preview_metadata()


def _empty_body_preview_metadata() -> dict[str, Any]:
    return {
        "body_preview": "",
        "body_preview_chars": 0,
        "body_preview_truncated": False,
        "body_preview_source": "unavailable",
    }


def _build_body_preview_metadata(
    text: str,
    source: str,
    email_preview_body_chars_max: int,
) -> dict[str, Any]:
    cleaned = _sanitize_text(text)
    if not cleaned:
        return _empty_body_preview_metadata()

    truncated = len(cleaned) > email_preview_body_chars_max
    preview = cleaned[:email_preview_body_chars_max]

    return {
        "body_preview": preview,
        "body_preview_chars": len(preview),
        "body_preview_truncated": truncated,
        "body_preview_source": source,
    }


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


def _extract_addresses(message: Any, header_name: str) -> list[str]:
    addresses: list[str] = []
    for name, value in message.raw_items():
        if name.lower() != header_name.lower():
            continue
        try:
            header = message.policy.header_fetch_parse(name, value)
            pairs = getaddresses([header])
        except TypeError, ValueError, IndexError:
            continue
        addresses.extend(addr for _name, addr in pairs if addr)
    return addresses


def _normalize_message_date(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""

    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError, IndexError:
        return ""

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed.astimezone(UTC).isoformat()


def _derive_mailbox_period(events: list[dict[str, Any]], loaded_at: str) -> str:
    for event in events:
        raw_date = event.get("date")
        if not isinstance(raw_date, str) or not raw_date:
            continue
        try:
            parsed = datetime.fromisoformat(raw_date)
        except ValueError:
            continue
        return parsed.astimezone(UTC).strftime("%Y-%m")

    try:
        loaded_dt = datetime.fromisoformat(loaded_at)
    except ValueError:
        loaded_dt = datetime.now(UTC)

    return loaded_dt.astimezone(UTC).strftime("%Y-%m")


def _build_fallback_event_id(source_id: str, position: int, raw_message: bytes) -> str:
    digest = hashlib.sha256(raw_message).hexdigest()[:16]
    return f"{source_id}-{position}-{digest}"


def _clean_header_value(value: Any) -> str:
    if value is None:
        return ""
    return _sanitize_text(str(value))


def _is_blocked_email_attachment(filename: str, content_type: str) -> bool:
    normalized_filename = filename.strip().lower()
    normalized_content_type = content_type.strip().lower()
    return (
        normalized_filename.endswith(".eml")
        or normalized_content_type == "message/rfc822"
    )


def _sort_events_by_date_desc(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _sort_key(event: dict[str, Any]) -> tuple[int, str, int]:
        raw_date = event.get("date") or event.get("received_at") or ""
        if isinstance(raw_date, str) and raw_date:
            try:
                dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                return (0, dt.isoformat(), 0)
            except ValueError:
                return (1, raw_date, 0)
        uid = event.get("source_message_id") or event.get("uid") or ""
        return (1, uid, 1)

    return sorted(events, key=_sort_key, reverse=True)


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
        "loaded_at": loaded_at or datetime.now(UTC).isoformat(),
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
    email_preview_body_chars_max: int,
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
        email_preview_body_chars_max=email_preview_body_chars_max,
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
        "loaded_at": datetime.now(UTC).isoformat(),
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
    email_preview_body_chars_max: int,
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
        valid.append(
            _sanitize_batch_item(
                item,
                email_preview_body_chars_max=email_preview_body_chars_max,
            )
        )

    if skipped:
        logger.warning(
            "json_batch source_id=%s: skipped %d non-dict items",
            source_id,
            skipped,
        )

    sorted_valid = sorted(
        valid,
        key=lambda e: (
            e.get("date") or e.get("received_at") or e.get("event_date") or ""
        ),
        reverse=True,
    )

    truncated = sorted_valid[:items_max]

    if len(valid) > items_max:
        logger.info(
            "json_batch source_id=%s: sorted by date, truncated to items_max=%d (total valid=%d)",
            source_id,
            items_max,
            len(valid),
        )

    return truncated


def _sanitize_batch_item(
    item: dict[str, Any],
    email_preview_body_chars_max: int,
) -> dict[str, Any]:
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

    forwarded_body_text = "\n".join(
        value.strip()
        for key in ("body", "text", "text_plain", "body_preview")
        if isinstance((value := sanitized.get(key)), str) and value.strip()
    )
    forwarded_fields = _extract_forwarded_wrapper_fields(
        forwarded_body_text[:email_preview_body_chars_max]
        if email_preview_body_chars_max > 0
        else ""
    )

    body_preview = _build_batch_body_preview(
        sanitized,
        email_preview_body_chars_max=email_preview_body_chars_max,
    )
    if body_preview is not None:
        sanitized["body_preview"] = body_preview["body_preview"]
        sanitized["body_preview_chars"] = body_preview["body_preview_chars"]
        sanitized["body_preview_truncated"] = body_preview["body_preview_truncated"]
        sanitized["body_preview_source"] = body_preview["body_preview_source"]

    raw_subject = sanitized.get("subject")
    if "clean_subject" not in sanitized:
        sanitized["clean_subject"] = _extract_clean_subject(raw_subject)

    raw_transport_labels = sanitized.get("transport_labels")
    transport_labels = _normalize_transport_labels(raw_transport_labels)
    if not transport_labels:
        transport_labels = _extract_transport_labels(raw_subject)
    sanitized["transport_labels"] = transport_labels

    if "spam_label_present" not in sanitized:
        sanitized["spam_label_present"] = "spam" in transport_labels
    if "reply_label_present" not in sanitized:
        sanitized["reply_label_present"] = "re" in transport_labels

    for key in (
        "forwarded_wrapper",
        "form_email",
        "original_sender",
        "original_sender_email",
        "original_recipient",
        "original_message_date",
        "date_source",
        "x_email_id",
    ):
        value = sanitized.get(key)
        if key == "forwarded_wrapper":
            if not isinstance(value, bool):
                sanitized[key] = forwarded_fields[key]
            continue
        if not isinstance(value, str) or not value:
            sanitized[key] = forwarded_fields[key]

    original_sender = sanitized.get("original_sender")
    original_sender_email = sanitized.get("original_sender_email")
    if (
        isinstance(original_sender, str)
        and original_sender
        and (not isinstance(original_sender_email, str) or not original_sender_email)
    ):
        sanitized["original_sender_email"] = _extract_email_from_sender(original_sender)

    _od = sanitized.get("original_message_date", "")
    if _od:
        sanitized["date"] = _od
        received_at_value = sanitized.get("received_at")
        if isinstance(received_at_value, str) and received_at_value.strip():
            sanitized["received_at"] = received_at_value.strip()
        else:
            sanitized["received_at"] = None
        sanitized["date_source"] = "original_forwarded_date"
        sanitized["_date_fallback"] = False
    elif sanitized.get("date") or sanitized.get("received_at"):
        _d = sanitized.get("date") or sanitized.get("received_at", "")
        sanitized["date"] = _d
        sanitized["received_at"] = _d
        sanitized["date_source"] = "mailbox_header"
        sanitized["_date_fallback"] = False
    else:
        sanitized["date"] = ""
        sanitized["received_at"] = None
        sanitized["date_source"] = "fallback_order"
        sanitized["_date_fallback"] = True

    return sanitized


def _build_batch_body_preview(
    item: dict[str, Any],
    email_preview_body_chars_max: int,
) -> dict[str, Any] | None:
    raw_body = ""
    source = "text_plain"

    for key in ("body", "text", "text_plain", "body_preview"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            raw_body = value
            source = "existing" if key == "body_preview" else "text_plain"
            break

    if not raw_body:
        payload = item.get("payload")
        if isinstance(payload, dict):
            for key in ("body", "text", "text_plain"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    raw_body = value
                    break

    if not raw_body:
        return None

    stripped = _strip_html(raw_body)
    is_html = stripped != raw_body
    preview_source = (
        source if source == "existing" else ("html_text" if is_html else "text_plain")
    )

    return _build_body_preview_metadata(
        text=stripped if is_html else raw_body,
        source=preview_source,
        email_preview_body_chars_max=email_preview_body_chars_max,
    )


_HTML_TAG_RE = re.compile(r"<[^>]*>")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_html(text: str) -> str:
    without_script = _SCRIPT_STYLE_RE.sub("", text)
    without_tags = _HTML_TAG_RE.sub("", without_script)
    return without_tags


def _sanitize_text(text: str) -> str:
    without_control = _CONTROL_CHARS_RE.sub("", text)
    normalized = re.sub(r"\s+", " ", without_control).strip()
    return normalized
