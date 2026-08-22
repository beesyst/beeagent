from __future__ import annotations

from beeagent_rop.contracts import ClassificationReasonCode

from beeagent_module.core.rop_reason_contract import (
    AI_EVIDENCE_CODES,
    AI_REASON_CODES,
    ATTENTION_REASON_CODES,
)

_CLASSIFICATION_REASON_DISPLAY = {
    "new_lead_request_signal": {
        "en": "New lead: request or RFQ signal detected",
        "ru": "Новый лид: обнаружен сигнал запроса или RFQ",
    },
    "new_lead_attachment_signal": {
        "en": "New lead: attachment-based signal detected",
        "ru": "Новый лид: обнаружен сигнал на основе вложения",
    },
    "existing_deal_reference_signal": {
        "en": "Existing deal: reference signal detected",
        "ru": "Существующая сделка: обнаружен сигнал ссылки",
    },
    "existing_deal_metadata_signal": {
        "en": "Existing deal: metadata-based signal detected",
        "ru": "Существующая сделка: обнаружен сигнал метаданных",
    },
    "existing_deal_conversation_continuation": {
        "en": "Existing deal: reply continues an existing lead conversation",
        "ru": "Существующая сделка: ответ продолжает переписку по лиду",
    },
    "duplicate_repeat_signal": {
        "en": "Duplicate: repeat message detected",
        "ru": "Дубликат: обнаружено повторное сообщение",
    },
    "duplicate_metadata_signal": {
        "en": "Duplicate: metadata-based match detected",
        "ru": "Дубликат: обнаружено совпадение метаданных",
    },
    "duplicate_candidate_confirmed": {
        "en": "Duplicate: confirmed match with a batch candidate",
        "ru": "Дубликат: подтверждено совпадение с кандидатом текущего батча",
    },
    "irrelevant_auto_reply": {
        "en": "Irrelevant: automatic reply detected",
        "ru": "Не релевантно: обнаружен автоответ",
    },
    "irrelevant_bulk_signal": {
        "en": "Irrelevant: bulk or mass mailing signal detected",
        "ru": "Не релевантно: обнаружена массовая рассылка",
    },
    "irrelevant_supplier_or_bulk_signal": {
        "en": "Irrelevant: supplier outreach or bulk signal detected",
        "ru": "Не релевантно: обнаружено обращение поставщика или рассылка",
    },
    "irrelevant_service_notification": {
        "en": "Irrelevant: service notification detected",
        "ru": "Не релевантно: обнаружено служебное уведомление",
    },
    "irrelevant_finance_document": {
        "en": "Irrelevant: finance document detected",
        "ru": "Не релевантно: обнаружен финансовый документ",
    },
    "irrelevant_logistics_notification": {
        "en": "Irrelevant: logistics notification detected",
        "ru": "Не релевантно: обнаружено логистическое уведомление",
    },
    "attachment_aware_new_lead": {
        "en": "New lead: attachment-aware classification",
        "ru": "Новый лид: классификация с учётом вложений",
    },
    "attachment_aware_existing_deal": {
        "en": "Existing deal: attachment-aware classification",
        "ru": "Существующая сделка: классификация с учётом вложений",
    },
    "ambiguous_existing_deal_candidate": {
        "en": "Existing deal: ambiguous candidate, needs review",
        "ru": "Существующая сделка: неоднозначный кандидат, требуется проверка",
    },
    "fallback_reply_context": {
        "en": "Fallback: reply context classification applied",
        "ru": "Резерв: классификация по контексту ответа",
    },
    "fallback_attachment_context": {
        "en": "Fallback: attachment context classification applied",
        "ru": "Резерв: классификация по контексту вложения",
    },
    "fallback_low_signal": {
        "en": "Fallback: low signal, fallback classification applied",
        "ru": "Резерв: слабый сигнал, применена резервная классификация",
    },
}
_AI_REASON_DISPLAY = {
    "customer_request_detected": {
        "en": "Customer request detected",
        "ru": "Обнаружен запрос клиента",
    },
    "tender_or_rfq_detected": {
        "en": "Tender or RFQ detected",
        "ru": "Обнаружен тендер или RFQ",
    },
    "existing_deal_continuation": {
        "en": "Existing deal continuation detected",
        "ru": "Обнаружено продолжение существующей сделки",
    },
    "logistics_or_finance_continuation": {
        "en": "Logistics or finance continuation detected",
        "ru": "Обнаружено продолжение логистического или финансового процесса",
    },
    "non_actionable_supplier_outreach": {
        "en": "Non-actionable supplier outreach detected",
        "ru": "Обнаружено нерелевантное обращение поставщика",
    },
    "non_actionable_bulk_or_newsletter": {
        "en": "Non-actionable bulk or newsletter content detected",
        "ru": "Обнаружена нерелевантная рассылка",
    },
    "non_actionable_service_notification": {
        "en": "Non-actionable service notification detected",
        "ru": "Обнаружено нерелевантное служебное уведомление",
    },
    "insufficient_business_signal": {
        "en": "Insufficient business signal",
        "ru": "Недостаточно бизнес-сигналов",
    },
    "conflicting_business_signals": {
        "en": "Conflicting business signals detected",
        "ru": "Обнаружены противоречивые бизнес-сигналы",
    },
    "duplicate_hypothesis_confirmed": {
        "en": "Possible duplicate confirmed by AI adjudication",
        "ru": "Возможный дубликат подтверждён ИИ-проверкой",
    },
    "duplicate_hypothesis_rejected": {
        "en": "Possible duplicate rejected by AI adjudication",
        "ru": "Возможный дубликат отклонён ИИ-проверкой",
    },
}
_ATTENTION_REASON_DISPLAY = {
    "ai_low_confidence_safe_ignore_preserved": {
        "en": "AI confidence was low; safe deterministic ignore preserved",
        "ru": "Уверенность ИИ низкая; безопасный детерминированный ignore сохранён",
    },
    "ai_low_confidence_manual_review": {
        "en": "AI confidence was low; manual review required",
        "ru": "Уверенность ИИ низкая; требуется ручная проверка",
    },
    "ai_output_conflict_manual_review": {
        "en": "AI output conflicted with signals; manual review required",
        "ru": "Результат ИИ противоречит сигналам; требуется ручная проверка",
    },
    "ai_validation_error_manual_review": {
        "en": "AI output validation failed; manual review required",
        "ru": "Проверка результата ИИ не пройдена; требуется ручная проверка",
    },
    "possible_duplicate_manual_review": {
        "en": "Possible duplicate requires manual review",
        "ru": "Возможный дубликат требует ручной проверки",
    },
    "ai_output_conflict_deterministic_result_preserved": {
        "en": "AI output conflicted with signals; deterministic result preserved",
        "ru": "Результат ИИ противоречит сигналам; детерминированный результат сохранён",
    },
    "ai_output_unresolved_deterministic_result_preserved": {
        "en": "AI did not resolve a semantic decision; deterministic result preserved",
        "ru": "ИИ не принял семантическое решение; детерминированный результат сохранён",
    },
    "ai_transition_rule_not_satisfied_deterministic_result_preserved": {
        "en": (
            "AI semantic transition was not authorized by an explicit evidence "
            "rule; deterministic result preserved"
        ),
        "ru": (
            "Семантический переход ИИ не разрешён явным правилом улик; "
            "детерминированный результат сохранён"
        ),
    },
    "possible_duplicate_unresolved_base_preserved": {
        "en": "Possible duplicate could not be resolved; base classification preserved",
        "ru": "Возможный дубликат не разрешён; базовая классификация сохранена",
    },
    "ai_output_with_validation_errors_deterministic_result_preserved": {
        "en": "AI output had validation errors; deterministic result preserved",
        "ru": "Результат ИИ содержит ошибки проверки; детерминированный результат сохранён",
    },
    "ai_confidence_below_threshold_deterministic_result_preserved": {
        "en": "AI confidence was below threshold; deterministic result preserved",
        "ru": "Уверенность ИИ ниже порога; детерминированный результат сохранён",
    },
    "missing_api_key_deterministic_result_preserved": {
        "en": "AI API key was unavailable; deterministic result preserved",
        "ru": "Ключ API ИИ недоступен; детерминированный результат сохранён",
    },
    "provider_call_failed_deterministic_result_preserved": {
        "en": "AI provider call failed; deterministic result preserved",
        "ru": "Вызов провайдера ИИ не выполнен; детерминированный результат сохранён",
    },
    "ai_output_invalid_deterministic_result_preserved": {
        "en": "AI output was invalid; deterministic result preserved",
        "ru": "Результат ИИ некорректен; детерминированный результат сохранён",
    },
    "deterministic_result_preserved": {
        "en": "Deterministic result preserved",
        "ru": "Детерминированный результат сохранён",
    },
    "ai_adjudicator_unexpected_status": {
        "en": "AI adjudicator returned an unexpected status",
        "ru": "ИИ-арбитр вернул неожиданный статус",
    },
    "semantic_unresolved_no_operator_queue": {
        "en": "Semantic decision unresolved without an operator queue",
        "ru": "Семантическое решение не разрешено без операторской очереди",
    },
}
_AI_EVIDENCE_DISPLAY = {
    "marketing_conflict": {
        "en": "Marketing content detected alongside business signal",
        "ru": "Обнаружен маркетинговый контент вместе с бизнес-сигналом",
    },
    "spam_rfq_conflict": {
        "en": "Spam label detected alongside request signal",
        "ru": "Обнаружена пометка спама вместе с сигналом запроса",
    },
    "supplier_outreach": {
        "en": "Supplier or product outreach detected",
        "ru": "Обнаружено обращение поставщика или реклама продукта",
    },
    "low_signal": {
        "en": "Weak or ambiguous signal; insufficient evidence",
        "ru": "Слабый или неоднозначный сигнал; недостаточно данных",
    },
    "ambiguous_bitrix": {
        "en": "Ambiguous Bitrix match; multiple candidates found",
        "ru": "Неоднозначное совпадение в Bitrix; найдено несколько кандидатов",
    },
    "newsletter_bulk": {
        "en": "Newsletter or bulk mailing characteristics detected",
        "ru": "Обнаружены признаки рассылки или массовой отправки",
    },
    "finance_sales_conflict": {
        "en": "Finance document content with sales classification",
        "ru": "Финансовый документ при классификации продаж",
    },
    "business_ignore_conflict": {
        "en": "Business-relevant content with ignore recommendation",
        "ru": "Бизнес-релевантный контент с рекомендацией ignore",
    },
    "attachment_mismatch": {
        "en": "Attachment content does not match expected case type",
        "ru": "Содержимое вложения не соответствует ожидаемому типу",
    },
}
_LEGACY = {
    "classification": {
        "en": "Classification uses a legacy contract; no structured reason code is available",
        "ru": "Классификация использует устаревший контракт; структурированный код причины отсутствует",
    },
    "ai": {
        "en": "AI adjudicator uses a legacy contract; no structured reason code is available",
        "ru": "ИИ-арбитр использует устаревший контракт; структурированный код причины отсутствует",
    },
    "attention": {
        "en": "Final decision uses a legacy contract; no structured attention reason code is available",
        "ru": "Финальное решение использует устаревший контракт; структурированный код причины внимания отсутствует",
    },
}
_LEGACY_AI_STATUS_DISPLAY = {
    "ok": {
        "en": "AI adjudicator completed; structured reason unavailable",
        "ru": "ИИ-арбитр завершил обработку; структурированная причина недоступна",
    },
    "manual_review_degrade": {
        "en": "AI adjudicator routed the event to manual review",
        "ru": "ИИ-арбитр направил событие на ручную проверку",
    },
    "low_confidence_preserve": {
        "en": "AI confidence was low; deterministic result preserved",
        "ru": "Уверенность ИИ низкая; детерминированный результат сохранён",
    },
    "low_confidence": {
        "en": "AI confidence was below threshold; deterministic result preserved",
        "ru": "Уверенность ИИ ниже порога; детерминированный результат сохранён",
    },
    "invalid": {
        "en": "AI output was invalid; deterministic result preserved",
        "ru": "Результат ИИ некорректен; детерминированный результат сохранён",
    },
    "degraded": {
        "en": (
            "AI adjudicator was unavailable or degraded; deterministic result preserved"
        ),
        "ru": (
            "ИИ-арбитр недоступен или деградировал; "
            "детерминированный результат сохранён"
        ),
    },
    "not_eligible": {
        "en": "AI adjudicator was not applied; deterministic result used",
        "ru": "ИИ-арбитр не применялся; использован детерминированный результат",
    },
    "module_contract_unavailable": {
        "en": "AI adjudicator contract was unavailable; deterministic result used",
        "ru": "Контракт ИИ-арбитра недоступен; использован детерминированный результат",
    },
}
_UNKNOWN = {
    "en": "Unknown reason code; localized explanation unavailable",
    "ru": "Неизвестный код причины; локализованное описание недоступно",
}
_ATTENTION_WARNING = {
    "legacy": {
        "en": "Legacy final-decision format: the attention reason code is missing. A compatible explanation is shown; no data was modified.",
        "ru": "Старый формат итогового решения: код причины внимания отсутствует. Показано совместимое объяснение; данные не изменялись.",
    },
    "unknown": {
        "en": "The attention reason code is unknown. A safe compatible explanation is shown.",
        "ru": "Код причины внимания неизвестен. Показано безопасное совместимое объяснение.",
    },
}
_MAX_REASON_CODE_LENGTH = 80


def _display(values: dict[str, str], lang: str) -> str:
    return values.get(lang, values["en"])


def _warning_code(value: str) -> str:
    return value.strip()[:_MAX_REASON_CODE_LENGTH]


def get_classification_reason_display(
    reason_code: str | None, lang: str
) -> tuple[str, str | None]:
    if not reason_code:
        return _display(
            _LEGACY["classification"], lang
        ), "legacy classification reason_code missing"
    entry = _CLASSIFICATION_REASON_DISPLAY.get(reason_code)
    if entry:
        return _display(entry, lang), None
    return (
        _display(_UNKNOWN, lang),
        f"unknown classification reason_code: {_warning_code(reason_code)}",
    )


def get_ai_reason_display(
    reason_code: str | None,
    lang: str,
    ai_status: str | None = None,
    merge_reason: str | None = None,
) -> tuple[str, str | None]:
    if reason_code:
        entry = _AI_REASON_DISPLAY.get(reason_code)
        if entry:
            return _display(entry, lang), None
        return (
            _display(_UNKNOWN, lang),
            f"unknown ai_reason_code: {_warning_code(reason_code)}",
        )
    if isinstance(merge_reason, str) and merge_reason in _ATTENTION_REASON_DISPLAY:
        return (
            _display(_ATTENTION_REASON_DISPLAY[merge_reason], lang),
            "legacy ai_reason_code missing",
        )

    if isinstance(ai_status, str):
        status_entry = _LEGACY_AI_STATUS_DISPLAY.get(ai_status)
        if status_entry is not None:
            return (
                _display(status_entry, lang),
                "legacy ai_reason_code missing",
            )

    return (
        _display(_LEGACY["ai"], lang),
        "legacy ai_reason_code missing",
    )


def get_attention_reason_display(
    reason_code: str | None, lang: str, merge_reason: str | None = None
) -> tuple[str, str | None]:
    if reason_code:
        entry = _ATTENTION_REASON_DISPLAY.get(reason_code)
        if entry:
            return _display(entry, lang), None
        return (
            _display(_UNKNOWN, lang),
            _display(_ATTENTION_WARNING["unknown"], lang),
        )
    if isinstance(merge_reason, str) and merge_reason in _ATTENTION_REASON_DISPLAY:
        return (
            _display(_ATTENTION_REASON_DISPLAY[merge_reason], lang),
            _display(_ATTENTION_WARNING["legacy"], lang),
        )
    return (
        _display(_LEGACY["attention"], lang),
        _display(_ATTENTION_WARNING["legacy"], lang),
    )


def get_ai_evidence_display(evidence_code: str, lang: str) -> tuple[str, str | None]:
    entry = _AI_EVIDENCE_DISPLAY.get(evidence_code)
    if entry:
        return _display(entry, lang), None
    return (
        _display(_UNKNOWN, lang),
        f"unknown evidence_code: {_warning_code(evidence_code)}",
    )


def is_valid_ai_reason_code(code: str) -> bool:
    return code in AI_REASON_CODES


def is_valid_attention_reason_code(code: str) -> bool:
    return code in ATTENTION_REASON_CODES


def is_valid_evidence_code(code: str) -> bool:
    return code in AI_EVIDENCE_CODES


def check_classification_coverage() -> list[str]:
    public_codes = {code.value for code in ClassificationReasonCode}
    return sorted(public_codes - set(_CLASSIFICATION_REASON_DISPLAY))


def check_reason_catalog_coverage() -> list[str]:
    catalogs = (
        ("ai", AI_REASON_CODES, _AI_REASON_DISPLAY),
        ("attention", ATTENTION_REASON_CODES, _ATTENTION_REASON_DISPLAY),
        ("evidence", AI_EVIDENCE_CODES, _AI_EVIDENCE_DISPLAY),
    )
    return sorted(
        {
            f"{name}:{code}"
            for name, contract_codes, display_codes in catalogs
            for code in contract_codes ^ set(display_codes)
        }
        | {
            f"{name}:{code}:missing_locale"
            for name, contract_codes, display_codes in catalogs
            for code in contract_codes
            if not {"en", "ru"}.issubset(display_codes.get(code, {}))
        }
    )
