from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from beeagent_module.adapters.bitrix_client import (
    BitrixApiError,
    BitrixAuthError,
    BitrixConnectorError,
    BitrixMalformedResponse,
    BitrixMethodNotAllowed,
    BitrixTimeoutError,
    BitrixTransportError,
)

WRITE_ALLOWED_METHODS: frozenset[str] = frozenset({
    "crm.item.add",
    "crm.activity.add",
    "crm.activity.update",
})
LEAD_ENTITY_TYPE_ID = 1
_ACTIVITY_TYPE_EMAIL = 4
_ACTIVITY_SUBJECT_MAX = 255
_ACTIVITY_DESCRIPTION_MAX = 3000
_ACTIVITY_EMAIL_MAX = 320
_ACTIVITY_ORIGIN_MAX = 200
_ACTIVITY_FILENAME_MAX = 255


class BitrixWriteClient:
    def __init__(
        self,
        webhook_url: str,
        timeout: int = 10,
        logger: logging.Logger | None = None,
    ) -> None:
        if not webhook_url or not webhook_url.startswith("https://"):
            raise BitrixConnectorError(
                "Bitrix write webhook URL must be a valid HTTPS URL"
            )
        self._webhook_url = webhook_url.rstrip("/")
        self._timeout = timeout
        self._logger = logger or logging.getLogger("bitrix_write_client")

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method not in WRITE_ALLOWED_METHODS:
            raise BitrixMethodNotAllowed(
                f"Bitrix write method '{method}' is not in allowed list: "
                f"{sorted(WRITE_ALLOWED_METHODS)}"
            )

        url = f"{self._webhook_url}/{method}"
        payload = json.dumps(params or {}).encode("utf-8")

        self._logger.debug(
            "bitrix write call: method=%s params_keys=%s",
            method,
            list(params.keys()) if params else [],
        )

        req = Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except HTTPError as exc:
            if exc.code in (401, 403):
                error = BitrixAuthError(
                    f"Bitrix write auth/permission error: HTTP {exc.code}"
                )
                error.code = exc.code
                raise error from exc
            error = BitrixTransportError(f"Bitrix write HTTP error: {exc.code}")
            error.code = exc.code
            raise error from exc
        except URLError as exc:
            if "timed out" in str(exc).lower():
                raise BitrixTimeoutError(
                    f"Bitrix write request timed out after {self._timeout}s"
                ) from exc
            raise BitrixTransportError(
                f"Bitrix write transport error: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise BitrixTransportError(
                f"Bitrix write connection error: {exc}"
            ) from exc

        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BitrixMalformedResponse(
                f"Bitrix returned malformed write JSON: {exc}"
            ) from exc

        if "error" in data:
            error_desc = data.get("error_description", data.get("error", "unknown"))
            error = BitrixApiError(f"Bitrix write API error: {error_desc}")
            error.code = data.get("error")
            raise error

        return data

    def add_lead(self, fields: dict[str, Any]) -> int:
        result = self.call(
            "crm.item.add",
            {"entityTypeId": LEAD_ENTITY_TYPE_ID, "fields": fields},
        )
        return _extract_added_item_id(result)

    def add_email_activity(
        self,
        owner_entity_type_id: int,
        owner_id: int,
        responsible_id: int,
        origin_id: str,
        subject: str,
        description: str,
        sender_email: str,
        completed: str = "Y",
    ) -> int:
        fields: dict[str, Any] = {
            "OWNER_TYPE_ID": owner_entity_type_id,
            "OWNER_ID": owner_id,
            "TYPE_ID": _ACTIVITY_TYPE_EMAIL,
            "RESPONSIBLE_ID": responsible_id,
            "PROVIDER_ID": "beeagent-rop",
            "PROVIDER_TYPE_ID": origin_id[:_ACTIVITY_ORIGIN_MAX],
            "SUBJECT": (subject or "")[:_ACTIVITY_SUBJECT_MAX],
            "DESCRIPTION": (description or "")[:_ACTIVITY_DESCRIPTION_MAX],
            "COMPLETED": completed if completed in ("Y", "N") else "Y",
            "DIRECTION": 1,
            "COMMUNICATIONS": [
                {
                    "ENTITY_TYPE_ID": owner_entity_type_id,
                    "ENTITY_ID": owner_id,
                    "VALUE": (sender_email or "")[:_ACTIVITY_EMAIL_MAX],
                    "TYPE": "EMAIL",
                }
            ],
        }
        result = self.call("crm.activity.add", {"fields": fields})
        return _extract_activity_id(result)

    def attach_files_to_activity(
        self,
        activity_id: int,
        files: list[tuple[str, bytes]],
    ) -> None:
        file_data: list[dict[str, Any]] = []
        for filename, content in files:
            if not isinstance(filename, str):
                filename = "attachment"
            if not isinstance(content, bytes):
                continue
            file_data.append(
                {
                    "fileData": [
                        filename[: _ACTIVITY_FILENAME_MAX],
                        base64.b64encode(content).decode("ascii"),
                    ]
                }
            )
        if not file_data:
            return
        self.call(
            "crm.activity.update",
            {
                "id": activity_id,
                "fields": {"FILES": file_data},
            },
        )


def _extract_added_item_id(data: dict[str, Any]) -> int:
    result = data.get("result")
    if isinstance(result, dict):
        item = result.get("item")
        if isinstance(item, dict):
            item_id = item.get("id")
            if isinstance(item_id, int) and not isinstance(item_id, bool) and item_id > 0:
                return item_id
            if isinstance(item_id, str) and item_id.strip().isdigit():
                return int(item_id)
        raw_id = result.get("id")
        if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
            return raw_id
        if isinstance(raw_id, str) and raw_id.strip().isdigit():
            return int(raw_id)
    raise BitrixMalformedResponse(
        "Bitrix returned malformed crm.item.add result without an item id"
    )


def _extract_activity_id(data: dict[str, Any]) -> int:
    result = data.get("result")
    if isinstance(result, int) and not isinstance(result, bool) and result > 0:
        return result
    if isinstance(result, dict):
        raw_id = result.get("id")
        if isinstance(raw_id, int) and not isinstance(raw_id, bool) and raw_id > 0:
            return raw_id
        if isinstance(raw_id, str) and raw_id.strip().isdigit():
            return int(raw_id)
    raise BitrixMalformedResponse(
        "Bitrix returned malformed crm.activity.add result without an id"
    )


def resolve_bitrix_write_webhook_url(
    settings: dict,
    logger: logging.Logger | None = None,
) -> str:
    writeback_cfg = settings.get("bitrix", {}).get("writeback", {})
    env_var = writeback_cfg.get("webhook_env", "BITRIX_WRITEBACK_WEBHOOK_URL")
    url = os.environ.get(env_var)

    if not url:
        raise BitrixConnectorError(
            f"Bitrix write webhook URL not found in env: {env_var}. "
            "Set this variable or keep bitrix.writeback.enabled: false."
        )

    if not url.startswith("https://"):
        raise BitrixConnectorError(
            "Bitrix write webhook URL must be an HTTPS URL"
        )

    return url


def build_bitrix_write_client(
    settings: dict,
    logger: logging.Logger | None = None,
) -> BitrixWriteClient:
    webhook_url = resolve_bitrix_write_webhook_url(settings, logger=logger)
    writeback_cfg = settings.get("bitrix", {}).get("writeback", {})
    timeout = writeback_cfg.get("timeout", 10)
    return BitrixWriteClient(
        webhook_url=webhook_url,
        timeout=timeout,
        logger=logger,
    )
