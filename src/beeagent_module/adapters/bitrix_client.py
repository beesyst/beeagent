"""
Bitrix24 read-only REST client v0.

Read-only Bitrix REST client for CRM reconciliation.
Only allowlisted methods are callable. No write methods are exposed.

Allowed methods (read-only):
  - crm.item.list        — универсальный список элементов (не поддерживает %EMAIL/%PHONE)
  - crm.lead.list        — список лидов (поддерживает %EMAIL, %PHONE, %TITLE)
  - crm.deal.list        — список сделок
  - crm.contact.list     — список контактов
  - crm.company.list     — список компаний
  - crm.item.fields      — поля элемента
  - crm.status.list      — справочник статусов
  - crm.category.list    — список воронок

Forbidden (must never be added to ALLOWED_METHODS):
  - crm.item.add
  - crm.item.update
  - crm.item.delete
  - crm.lead.add / update / delete
  - crm.deal.add / update / delete
  - crm.contact.add / update / delete
  - crm.company.add / update / delete
  - tasks.task.add
  - any method with add/update/delete
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Legacy type-specific methods поддерживают фильтры %EMAIL, %PHONE, %TITLE
# Универсальный crm.item.list не поддерживает фильтрацию по email/phone
ALLOWED_METHODS: frozenset[str] = frozenset({
    "crm.item.list",
    "crm.item.fields",
    "crm.status.list",
    "crm.category.list",
    "crm.lead.list",
    "crm.deal.list",
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


class BitrixConnectorError(RuntimeError):
    """Базовое исключение Bitrix connector."""


class BitrixAuthError(BitrixConnectorError):
    """Ошибка аутентификации/доступа."""


class BitrixApiError(BitrixConnectorError):
    """Ошибка Bitrix REST API (envelope error)."""


class BitrixTimeoutError(BitrixConnectorError):
    """Таймаут подключения к Bitrix."""


class BitrixTransportError(BitrixConnectorError):
    """Транспортная ошибка (DNS, соединение, HTTP)."""


class BitrixMethodNotAllowed(ValueError):
    """Вызов метода, не входящего в allowlist."""


class BitrixMalformedResponse(BitrixConnectorError):
    """Невалидный JSON ответ от Bitrix."""


class BitrixReadonlyClient:
    """Read-only Bitrix REST client.

    Использует webhook URL из переменной окружения.
    Никогда не логирует и не сериализует webhook URL.
    """

    def __init__(
        self,
        webhook_url: str,
        timeout_seconds: int = 10,
        logger: logging.Logger | None = None,
    ) -> None:
        if not webhook_url or not webhook_url.startswith("https://"):
            raise BitrixConnectorError(
                "Bitrix webhook URL must be a valid HTTPS URL"
            )
        self._webhook_url = webhook_url.rstrip("/")
        self._timeout = timeout_seconds
        self._logger = logger or logging.getLogger("bitrix_client")

    # --- Public API ---
    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Вызвать read-only метод Bitrix REST API.

        Args:
            method: Имя метода (например 'crm.item.list').
            params: Параметры запроса.

        Returns:
            Ответ Bitrix API (разобранный JSON).

        Raises:
            BitrixMethodNotAllowed: метод не в allowlist.
            BitrixAuthError: 401/403.
            BitrixApiError: ошибка в envelope.
            BitrixTimeoutError: timeout.
            BitrixTransportError: транспортная ошибка.
            BitrixMalformedResponse: невалидный JSON.
        """
        if method not in ALLOWED_METHODS:
            raise BitrixMethodNotAllowed(
                f"Bitrix method '{method}' is not in allowed list: "
                f"{sorted(ALLOWED_METHODS)}"
            )

        url = f"{self._webhook_url}/{method}"
        payload = json.dumps(params or {}).encode("utf-8")

        # Никогда не логируем webhook_url
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
    ) -> dict[str, Any]:
        """crm.item.list с базовым фильтром."""
        params: dict[str, Any] = {
            "entityTypeId": entity_type_id,
        }
        if filter_params:
            params["filter"] = filter_params
        if select:
            params["select"] = select
        if start:
            params["start"] = start
        return self.call("crm.item.list", params)

    def item_fields(self, entity_type_id: int) -> dict[str, Any]:
        """crm.item.fields — метаданные полей сущности."""
        return self.call("crm.item.fields", {"entityTypeId": entity_type_id})

    def status_list(self) -> dict[str, Any]:
        """crm.status.list — список статусов."""
        return self.call("crm.status.list")

    def category_list(self, entity_type_id: int) -> dict[str, Any]:
        """crm.category.list — список категорий для сущности."""
        return self.call("crm.category.list", {"entityTypeId": entity_type_id})

    def search_candidates(
        self,
        entity_type_id: int,
        query: str,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Поиск кандидатов среди сущностей Bitrix.

        Для email/phone использует legacy методы (crm.lead.list и т.д.),
        которые поддерживают фильтры %EMAIL, %PHONE.
        Для поиска по названию использует универсальный crm.item.list.

        Возвращает список найденных сущностей.
        """
        if not query or not query.strip():
            return []

        select_fields = fields or ["ID", "TITLE", "STAGE_ID", "ASSIGNED_BY_ID",
                                    "CONTACT_ID", "COMPANY_ID", "DATE_CREATE"]

        # Определяем тип поиска
        is_email = "@" in query
        is_phone = query.replace(" ", "").replace("+", "").replace("-", "").isdigit() and len(query.strip()) >= 5

        if is_email or is_phone:
            # Используем legacy type-specific метод
            return self._search_by_communication(
                entity_type_id=entity_type_id,
                query=query,
                is_email=is_email,
                select_fields=select_fields,
            )
        else:
            # Поиск по названию через универсальный crm.item.list
            return self._search_by_title(
                entity_type_id=entity_type_id,
                query=query,
                select_fields=select_fields,
            )

    def _search_by_communication(
        self,
        entity_type_id: int,
        query: str,
        is_email: bool,
        select_fields: list[str],
    ) -> list[dict[str, Any]]:
        """Поиск по email или phone через legacy type-specific методы.

        Legacy методы (crm.lead.list, crm.deal.list и т.д.) возвращают
        поля в UPPER_CASE и поддерживают %EMAIL, %PHONE фильтры.
        """
        legacy_method = _entity_type_to_legacy_method(entity_type_id)
        if not legacy_method:
            return []

        filter_key = "%EMAIL" if is_email else "%PHONE"
        params: dict[str, Any] = {
            "filter": {filter_key: query},
            "select": select_fields,
        }

        try:
            data = self.call(legacy_method, params)
        except BitrixConnectorError:
            return []

        items = data.get("result", [])
        if not isinstance(items, list):
            return []
        return items

    def _search_by_title(
        self,
        entity_type_id: int,
        query: str,
        select_fields: list[str],
    ) -> list[dict[str, Any]]:
        """Поиск по названию через универсальный crm.item.list.

        Универсальные методы возвращают поля в camelCase.
        Фильтр %title работает для прямых полей.
        """
        # Конвертируем UPPER_CASE select-поля в camelCase для crm.item.list
        camel_fields = _convert_select_to_camel(select_fields)

        try:
            result = self.item_list(
                entity_type_id=entity_type_id,
                filter_params={"%title": query},
                select=camel_fields,
            )
        except BitrixConnectorError:
            return []

        items = result.get("result", {}).get("items", [])
        if not isinstance(items, list):
            return []
        return items

    def get_portal_url(self) -> str:
        """Извлечь URL портала из webhook URL для artifact.

        Никогда не возвращает полный webhook URL с секретом.
        """
        parts = self._webhook_url.split("/")
        if len(parts) >= 3:
            return f"{parts[0]}//{parts[2]}"
        return ""


def _entity_type_to_legacy_method(entity_type_id: int) -> str | None:
    """Маппинг entityTypeId → legacy метод списка."""
    mapping = {
        1: "crm.lead.list",
        2: "crm.deal.list",
        3: "crm.contact.list",
        4: "crm.company.list",
    }
    return mapping.get(entity_type_id)


def _convert_select_to_camel(fields: list[str]) -> list[str]:
    """Конвертация UPPER_CASE полей в camelCase для универсальных методов.

    Пример: ID → id, TITLE → title, STAGE_ID → stageId, ASSIGNED_BY_ID → assignedById
    """
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

def resolve_bitrix_webhook_url(
    settings: dict,
    logger: logging.Logger | None = None,
) -> str:
    """Прочитать webhook URL из env по имени из settings.

    Никогда не логирует и не возвращает значение URL.
    """
    env_var = settings.get("bitrix", {}).get("webhook_url_env", "BITRIX_WEBHOOK_URL")
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


def build_bitrix_client(
    settings: dict,
    logger: logging.Logger | None = None,
) -> BitrixReadonlyClient:
    """Создать BitrixReadonlyClient из settings.

    Resolve webhook URL из env.
    """
    webhook_url = resolve_bitrix_webhook_url(settings, logger=logger)
    timeout = settings.get("bitrix", {}).get("timeout_seconds", 10)
    return BitrixReadonlyClient(
        webhook_url=webhook_url,
        timeout_seconds=timeout,
        logger=logger,
    )
