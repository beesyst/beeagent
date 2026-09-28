from __future__ import annotations

import hmac
import os
from urllib.parse import urlparse
from typing import Any

from beeagent_module.adapters.bitrix_client import BitrixReadonlyClient
from beeagent_module.core.rop_sender_blacklist import (
    SenderBlacklistError,
    add_sender_blacklist_entry,
    load_sender_blacklist_entries,
    normalize_sender_email,
    update_sender_blacklist_entry,
    write_sender_blacklist_audit,
)


def _lead_text(lead: dict[str, Any], key: str) -> str:
    value = lead.get(key)
    if not isinstance(value, str):
        return ""
    return value.strip()[:128]


def process_blacklist_stage_trigger(
    storage_dir: Any,
    settings: dict[str, Any],
    lead_id: Any,
    supplied_secret: str | None,
    *,
    authenticated: bool = False,
) -> tuple[str, bool]:
    cfg = settings.get("bitrix", {}).get("blacklist_trigger", {})
    if not isinstance(cfg, dict) or not cfg.get("enabled", False):
        return "disabled", False
    secret = os.getenv(str(cfg.get("secret_env", "")), "")
    if not authenticated and (
        not secret
        or not isinstance(supplied_secret, str)
        or not hmac.compare_digest(secret, supplied_secret)
    ):
        return "unauthorized", False
    if not isinstance(lead_id, str) or not lead_id.isdigit() or not 0 < int(lead_id) <= 2_147_483_647:
        return "invalid_lead", False
    bitrix = settings.get("bitrix", {})
    try:
        client = BitrixReadonlyClient(
            os.getenv(str(bitrix.get("webhook_env", "")), ""),
            timeout=int(bitrix.get("timeout", 10)),
            page_size=int(bitrix.get("page_size", 50)),
            pages_max=int(bitrix.get("pages_max", 1)),
        )
        field = cfg["classification_field"]
        response = client.item_list(
            1,
            {"=id": int(lead_id)},
            ["id", "stageId", "name", "lastName", "secondName", "post", "email", field],
            limit=2,
        )
        result = response.get("result")
        if isinstance(result, dict):
            result = result.get("items")
        if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
            return "lead_unavailable", False
        lead = result[0]
        if str(lead.get("id", lead.get("ID", ""))) != lead_id:
            return "lead_unavailable", False
        if str(lead.get("stageId", lead.get("STATUS_ID", ""))) != cfg["stage_id"]:
            return "wrong_stage", False
        reason = lead.get(field)
        if reason is None or reason == "":
            reason = ""
        elif not isinstance(reason, str) or len(reason.strip()) > 128:
            return "invalid_classification", False
        else:
            reason = reason.strip()
        email_value = lead.get("email", lead.get("EMAIL"))
        if isinstance(email_value, list):
            values = [item.get("VALUE") for item in email_value if isinstance(item, dict)]
            if len(values) != 1:
                return "invalid_sender", False
            email_value = values[0]
        email = normalize_sender_email(email_value)
        name = " ".join(
            part
            for part in (
                _lead_text(lead, "lastName"),
                _lead_text(lead, "name"),
                _lead_text(lead, "secondName"),
            )
            if part
        )[:128]
        entry = {
            "name": name,
            "title": _lead_text(lead, "post"),
            "email": email,
            "reason": reason,
        }
        current = next(
            (
                item
                for item in load_sender_blacklist_entries(storage_dir)
                if item["email"] == email
            ),
            None,
        )
        if current is None:
            _, changed = add_sender_blacklist_entry(storage_dir, entry)
        else:
            entry = {
                "name": current["name"] or entry["name"],
                "title": current["title"] or entry["title"],
                "email": email,
                "reason": current["reason"] or entry["reason"],
            }
            _, changed = update_sender_blacklist_entry(storage_dir, email, entry)
    except (KeyError, TypeError, ValueError, SenderBlacklistError, RuntimeError):
        return "connector_error", False
    write_sender_blacklist_audit(storage_dir, action_id="bitrix_blacklist_stage", actor_id="bitrix", outcome="changed" if changed else "unchanged", email=email)
    return "ok", changed


def process_bitrix_lead_update_event(
    storage_dir: Any,
    settings: dict[str, Any],
    payload: Any,
) -> tuple[str, bool]:
    cfg = settings.get("bitrix", {}).get("blacklist_trigger", {})
    if not isinstance(cfg, dict) or not cfg.get("enabled", False):
        return "disabled", False
    if not isinstance(payload, dict) or payload.get("event") != "ONCRMLEADUPDATE":
        return "invalid_event", False
    data = payload.get("data")
    fields = data.get("FIELDS") if isinstance(data, dict) else None
    auth = payload.get("auth")
    if not isinstance(fields, dict) or not isinstance(auth, dict):
        return "invalid_event", False
    token = auth.get("application_token")
    expected = os.getenv(str(cfg.get("event_application_token_env", "")), "")
    domain = auth.get("domain")
    portal = settings.get("bitrix", {}).get("embedded_app", {}).get("portal_origin", "")
    expected_domain = urlparse(str(portal)).hostname
    if (
        not expected
        or not isinstance(token, str)
        or not hmac.compare_digest(expected, token)
        or not isinstance(domain, str)
        or domain.casefold() != (expected_domain or "").casefold()
    ):
        return "unauthorized", False
    return process_blacklist_stage_trigger(
        storage_dir, settings, fields.get("ID"), None, authenticated=True
    )
