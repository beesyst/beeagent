from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Legacy communication lookup используется только для lead/contact/company
ALLOWED_METHODS: frozenset[str] = frozenset({
    "crm.item.list",
    "crm.item.fields",
    "crm.status.list",
    "crm.category.list",
    "crm.lead.list",
    "crm.contact.list",
    "crm.company.list",
})
ENTITY_TYPE_NAMES: dict[int, str] = {
    1: "lead",
    2: "deal",
    3: "contact",
    4: "company",
}
ENTITY_TYPE_IDS: dict[str, int] = {v: k for k, v in ENTITY_TYPE_NAMES.items()}
COMMUNICATION_ENTITY_TYPE_IDS: frozenset[int] = frozenset({1, 3, 4})


# Базовое исключение Bitrix connector
class BitrixConnectorError(RuntimeError):
    pass


# Ошибка аутентификации/доступа
class BitrixAuthError(BitrixConnectorError):
    pass


# Ошибка Bitrix REST API (envelope error)
class BitrixApiError(BitrixConnectorError):
    pass


# Ошибка таймаута при подключении к Bitrix
class BitrixTimeoutError(BitrixConnectorError):
    pass


# Транспортная ошибка (DNS, соединение, HTTP)
class BitrixTransportError(BitrixConnectorError):
    pass


# Ошибка при вызове метода, не входящего в allowlist
class BitrixMethodNotAllowed(ValueError):
    pass


# Невалидный JSON ответ от Bitrix
class BitrixMalformedResponse(BitrixConnectorError):
    pass


# Read-only Bitrix REST client
class BitrixReadonlyClient:
    def __init__(
        self,
        webhook_url: str,
        timeout: int = 10,
        page_size: int = 50,
        pages_max: int = 3,
        logger: logging.Logger | None = None,
    ) -> None:
        if not webhook_url or not webhook_url.startswith("https://"):
            raise BitrixConnectorError(
                "Bitrix webhook URL must be a valid HTTPS URL"
            )
        self._webhook_url = webhook_url.rstrip("/")
        self._timeout = timeout
        self._page_size = page_size
        self._pages_max = pages_max
        self._logger = logger or logging.getLogger("bitrix_client")

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise BitrixMethodNotAllowed(
                f"Bitrix method '{method}' is not in allowed list: "
                f"{sorted(ALLOWED_METHODS)}"
            )

        url = f"{self._webhook_url}/{method}"
        payload = json.dumps(params or {}).encode("utf-8")

        self._logger.debug(
            "bitrix call: method=%s params_keys=%s",
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
                raise BitrixAuthError(
                    f"Bitrix auth/permission error: HTTP {exc.code}"
                ) from exc
            raise BitrixTransportError(
                f"Bitrix HTTP error: {exc.code}"
            ) from exc
        except URLError as exc:
            if "timed out" in str(exc).lower():
                raise BitrixTimeoutError(
                    f"Bitrix request timed out after {self._timeout}s"
                ) from exc
            raise BitrixTransportError(
                f"Bitrix transport error: {exc.reason}"
            ) from exc
        except OSError as exc:
            raise BitrixTransportError(
                f"Bitrix connection error: {exc}"
            ) from exc

        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise BitrixMalformedResponse(
                f"Bitrix returned malformed JSON: {exc}"
            ) from exc

        if "error" in data:
            error_desc = data.get("error_description", data.get("error", "unknown"))
            raise BitrixApiError(
                f"Bitrix API error: {error_desc}"
            )

        return data

    def item_list(
        self,
        entity_type_id: int,
        filter_params: dict[str, Any] | None = None,
        select: list[str] | None = None,
        start: int = 0,
        limit: int | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "entityTypeId": entity_type_id,
        }
        if filter_params:
            params["filter"] = filter_params
        if select:
            params["select"] = select
        if limit:
            params["limit"] = limit
        if start:
            params["start"] = start
        return self.call("crm.item.list", params)

    def item_fields(self, entity_type_id: int) -> dict[str, Any]:
        return self.call("crm.item.fields", {"entityTypeId": entity_type_id})

    def status_list(self) -> dict[str, Any]:
        return self.call("crm.status.list")

    def category_list(self, entity_type_id: int) -> dict[str, Any]:
        return self.call("crm.category.list", {"entityTypeId": entity_type_id})

    def search_candidates(
        self,
        entity_type_id: int,
        query: str,
        fields: list[str] | None = None,
        date_from: str | None = None,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            return []

        select_fields = fields or [
            "ID",
            "TITLE",
            "STAGE_ID",
            "STATUS_ID",
            "ASSIGNED_BY_ID",
            "CONTACT_ID",
            "COMPANY_ID",
            "DATE_CREATE",
            "EMAIL",
            "PHONE",
        ]

        is_email = "@" in query
        normalized_phone = (
            query.replace(" ", "").replace("+", "").replace("-", "")
        )
        is_phone = normalized_phone.isdigit() and len(query.strip()) >= 5

        if is_email or is_phone:
            return self._search_by_communication(
                entity_type_id=entity_type_id,
                query=query,
                is_email=is_email,
                select_fields=select_fields,
                date_from=date_from,
            )
        return self._search_by_title(
            entity_type_id=entity_type_id,
            query=query,
            select_fields=select_fields,
            date_from=date_from,
        )

    def _search_by_communication(
        self,
        entity_type_id: int,
        query: str,
        is_email: bool,
        select_fields: list[str],
        date_from: str | None = None,
    ) -> list[dict[str, Any]]:
        if entity_type_id not in COMMUNICATION_ENTITY_TYPE_IDS:
            return []

        legacy_method = _entity_type_to_legacy_method(entity_type_id)
        if not legacy_method:
            return []

        filter_key = "%EMAIL" if is_email else "%PHONE"
        filter_params: dict[str, Any] = {filter_key: query}
        if date_from:
            filter_params[">=DATE_CREATE"] = date_from
        params: dict[str, Any] = {
            "filter": filter_params,
            "select": select_fields,
            "limit": self._page_size,
        }

        return self._collect_legacy_pages(legacy_method, params)

    def _search_by_title(
        self,
        entity_type_id: int,
        query: str,
        select_fields: list[str],
        date_from: str | None = None,
    ) -> list[dict[str, Any]]:
        camel_fields = _convert_select_to_camel(select_fields)
        filter_params: dict[str, Any] = {"%title": query}
        if date_from:
            filter_params[">=createdTime"] = date_from

        items: list[dict[str, Any]] = []
        start = 0
        for _ in range(self._pages_max):
            result = self.item_list(
                entity_type_id=entity_type_id,
                filter_params=filter_params,
                select=camel_fields,
                start=start,
                limit=self._page_size,
            )

            result_payload = result.get("result")
            if not isinstance(result_payload, dict):
                raise BitrixMalformedResponse(
                    "Bitrix returned malformed crm.item.list result"
                )
            page_items = result_payload.get("items", [])
            if not isinstance(page_items, list):
                raise BitrixMalformedResponse(
                    "Bitrix returned malformed crm.item.list items"
                )
            items.extend(page_items)

            next_start = result.get("next")
            if next_start is None:
                break
            if not isinstance(next_start, int):
                raise BitrixMalformedResponse(
                    "Bitrix returned malformed pagination cursor"
                )
            start = next_start
        return items

    def _collect_legacy_pages(
        self,
        method: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        for _ in range(self._pages_max):
            page_params = dict(params)
            if start:
                page_params["start"] = start
            data = self.call(method, page_params)
            page_items = data.get("result", [])
            if not isinstance(page_items, list):
                raise BitrixMalformedResponse(
                    f"Bitrix returned malformed {method} result"
                )
            items.extend(page_items)

            next_start = data.get("next")
            if next_start is None:
                break
            if not isinstance(next_start, int):
                raise BitrixMalformedResponse(
                    "Bitrix returned malformed pagination cursor"
                )
            start = next_start
        return items

    def get_portal_url(self) -> str:
        parts = self._webhook_url.split("/")
        if len(parts) >= 3:
            return f"{parts[0]}//{parts[2]}"
        return ""


# Маппинг entityTypeId -> legacy метод списка
def _entity_type_to_legacy_method(entity_type_id: int) -> str | None:
    mapping = {
        1: "crm.lead.list",
        3: "crm.contact.list",
        4: "crm.company.list",
    }
    return mapping.get(entity_type_id)


# Конвертация UPPER_CASE полей в camelCase
def _convert_select_to_camel(fields: list[str]) -> list[str]:
    camel_map: dict[str, str] = {
        "ID": "id",
        "TITLE": "title",
        "STAGE_ID": "stageId",
        "STATUS_ID": "statusId",
        "ASSIGNED_BY_ID": "assignedById",
        "CONTACT_ID": "contactId",
        "COMPANY_ID": "companyId",
        "DATE_CREATE": "createdTime",
    }
    return [camel_map.get(f, f.lower()) for f in fields]


# Разрешить URL вебхука из env по имени из settings
def resolve_bitrix_webhook_url(
    settings: dict,
    logger: logging.Logger | None = None,
) -> str:
    env_var = settings.get("bitrix", {}).get("webhook_env", "BITRIX_WEBHOOK_URL")
    url = os.environ.get(env_var)

    if not url:
        raise BitrixConnectorError(
            f"Bitrix webhook URL not found in env: {env_var}. "
            "Set this variable or disable Bitrix connector (bitrix.enabled: false)."
        )

    if not url.startswith("https://"):
        raise BitrixConnectorError(
            "Bitrix webhook URL must be an HTTPS URL"
        )

    return url


# Фабрика BitrixReadonlyClient из settings
def build_bitrix_client(
    settings: dict,
    logger: logging.Logger | None = None,
) -> BitrixReadonlyClient:
    webhook_url = resolve_bitrix_webhook_url(settings, logger=logger)
    bitrix_cfg = settings.get("bitrix", {})
    timeout = bitrix_cfg.get("timeout", 10)
    page_size = bitrix_cfg.get("page_size", 50)
    pages_max = bitrix_cfg.get("pages_max", 3)
    return BitrixReadonlyClient(
        webhook_url=webhook_url,
        timeout=timeout,
        page_size=page_size,
        pages_max=pages_max,
        logger=logger,
    )
