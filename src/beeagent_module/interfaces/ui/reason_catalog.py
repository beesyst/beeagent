from __future__ import annotations

from typing import Any

# ── Classification reason catalog ────────────────────────────────────────────
# String values match the public ClassificationReasonCode enum.
# Direct import is avoided to respect the module boundary.

_CLASSIFICATION_REASON_DISPLAY: dict[str, dict[str, str]] = {
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
    "duplicate_repeat_signal": {
        "en": "Duplicate: repeat message detected",
        "ru": "Дубликат: обнаружено повторное сообщение",
    },
    "duplicate_metadata_signal": {
        "en": "Duplicate: metadata-based match detected",
        "ru": "Дубликат: обнаружено совпадение метаданных",
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

# ── AI reason codes ──────────────────────────────────────────────────────────

_AI_REASON_DISPLAY: dict[str, dict[str, str]] = {
    "ai_low_confidence_preserve": {
        "en": "AI confidence below threshold; deterministic result preserved",
        "ru": "Уверенность ИИ ниже порога; сохранён детерминированный результат",
    },
    "manual_review_degrade": {
        "en": "AI output conflicts with signal evidence; routed to manual review",
        "ru": "Результат ИИ противоречит сигналам; направлено на ручную проверку",
    },
    "provider_unavailable": {
        "en": "AI adjudicator provider unavailable; deterministic result used",
        "ru": "Провайдер ИИ недоступен; использован детерминированный результат",
    },
    "invalid_output": {
        "en": "AI adjudicator returned invalid output; deterministic result used",
        "ru": "ИИ вернул некорректный результат; использован детерминированный",
    },
    "low_confidence": {
        "en": "AI confidence below threshold; deterministic result preserved",
        "ru": "Уверенность ИИ ниже порога; сохранён детерминированный результат",
    },
    "ai_resolved_risky_false_positive": {
        "en": "AI resolved risky false positive; deterministic ignore preserved",
        "ru": "ИИ разрешил рискованный ложноположительный результат; ignore сохранён",
    },
    "ai_low_confidence_safe_ignore_preserved": {
        "en": "AI low confidence; safe deterministic ignore preserved",
        "ru": "Низкая уверенность ИИ; безопасный ignore сохранён",
    },
    "ai_output_conflict_manual_review": {
        "en": "AI output conflicts with signal evidence; routed to manual review",
        "ru": "Результат ИИ противоречит сигналам; направлено на ручную проверку",
    },
    "ai_low_confidence_manual_review": {
        "en": "AI low confidence for ambiguous case; routed to manual review",
        "ru": "Низкая уверенность ИИ для неоднозначного случая; направлено на ручную проверку",
    },
}

# ── Attention reason codes ───────────────────────────────────────────────────

_ATTENTION_REASON_DISPLAY: dict[str, dict[str, str]] = {
    "ai_low_confidence_preserve": {
        "en": "AI confidence below threshold; deterministic result preserved",
        "ru": "Уверенность ИИ ниже порога; сохранён детерминированный результат",
    },
    "manual_review_degrade": {
        "en": "AI output conflicted with evidence; manual review required",
        "ru": "Результат ИИ противоречит данным; требуется ручная проверка",
    },
    "deterministic_fallback": {
        "en": "Fallback policy applied; deterministic result used",
        "ru": "Применена резервная политика; использован детерминированный результат",
    },
    "ai_adjudicator_unexpected_status": {
        "en": "AI adjudicator returned unexpected status; manual review suggested",
        "ru": "ИИ вернул неожиданный статус; рекомендуется ручная проверка",
    },
}

# ── AI evidence codes catalog ────────────────────────────────────────────────

_AI_EVIDENCE_DISPLAY: dict[str, dict[str, str]] = {
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

# ── Legacy fallback messages ─────────────────────────────────────────────────

_LEGACY_ADJUDICATOR_FALLBACK: dict[str, str] = {
    "en": "AI adjudicator result uses legacy format; no structured reason code available",
    "ru": "Результат ИИ арбитра в старом формате; структурированный код причины отсутствует",
}

_LEGACY_ATTENTION_FALLBACK: dict[str, str] = {
    "en": "Final decision uses legacy format; no structured attention reason code available",
    "ru": "Финальное решение в старом формате; структурированный код причины внимания отсутствует",
}

_LEGACY_CLASSIFICATION_FALLBACK: dict[str, str] = {
    "en": "Classification reason uses legacy code; no localized explanation available",
    "ru": "Причина классификации использует устаревший код; локализованное описание недоступно",
}

_UNKNOWN_REASON_FALLBACK: dict[str, str] = {
    "en": "Unknown reason code; localized explanation unavailable",
    "ru": "Неизвестный код причины; локализованное описание недоступно",
}

_UNKNOWN_EVIDENCE_FALLBACK: dict[str, str] = {
    "en": "Unknown evidence code",
    "ru": "Неизвестный код свидетельства",
}


# ── Public API ───────────────────────────────────────────────────────────────


def get_classification_reason_display(
    reason_code: str | None,
    lang: str,
) -> tuple[str, str | None]:
    """Return (localized_display, warning_or_None) for a classification reason code."""
    if not reason_code:
        return ("", None)

    entry = _CLASSIFICATION_REASON_DISPLAY.get(reason_code)
    if entry:
        return (entry.get(lang, entry.get("en", reason_code)), None)

    legacy_display = _LEGACY_CLASSIFICATION_FALLBACK.get(lang, _LEGACY_CLASSIFICATION_FALLBACK["en"])
    return (legacy_display, f"unknown classification reason_code: {reason_code}")


def get_ai_reason_display(
    reason_code: str | None,
    lang: str,
) -> tuple[str, str | None]:
    """Return (localized_display, warning_or_None) for an AI adjudicator reason code."""
    if not reason_code:
        return ("", None)

    entry = _AI_REASON_DISPLAY.get(reason_code)
    if entry:
        return (entry.get(lang, entry.get("en", reason_code)), None)

    # Legacy fallback: raw AI reason is used, no structured code
    legacy = _LEGACY_ADJUDICATOR_FALLBACK.get(lang, _LEGACY_ADJUDICATOR_FALLBACK["en"])
    return (legacy, f"unknown ai_reason_code: {reason_code}")


def get_attention_reason_display(
    reason_code: str | None,
    lang: str,
) -> tuple[str, str | None]:
    """Return (localized_display, warning_or_None) for an attention reason code."""
    if not reason_code:
        return ("", None)

    entry = _ATTENTION_REASON_DISPLAY.get(reason_code)
    if entry:
        return (entry.get(lang, entry.get("en", reason_code)), None)

    # Legacy fallback: raw attention reason is used, no structured code
    legacy = _LEGACY_ATTENTION_FALLBACK.get(lang, _LEGACY_ATTENTION_FALLBACK["en"])
    return (legacy, f"unknown attention_reason_code: {reason_code}")


def get_ai_evidence_display(
    evidence_code: str,
    lang: str,
) -> tuple[str, str | None]:
    """Return (localized_display, warning_or_None) for an evidence code."""
    entry = _AI_EVIDENCE_DISPLAY.get(evidence_code)
    if entry:
        return (entry.get(lang, entry.get("en", evidence_code)), None)
    fallback = _UNKNOWN_EVIDENCE_FALLBACK.get(lang, _UNKNOWN_EVIDENCE_FALLBACK["en"])
    return (fallback, f"unknown evidence_code: {evidence_code}")


# ── Validation helpers ──────────────────────────────────────────────────────


def is_valid_ai_reason_code(code: str) -> bool:
    return code in _AI_REASON_DISPLAY


def is_valid_attention_reason_code(code: str) -> bool:
    return code in _ATTENTION_REASON_DISPLAY


def is_valid_evidence_code(code: str) -> bool:
    return code in _AI_EVIDENCE_DISPLAY


# ── Enum coverage check ─────────────────────────────────────────────────────


def check_classification_coverage() -> list[str]:
    """Return missing classification reason codes not covered by the catalog."""
    # All known classification reason code string values
    all_known = {
        "new_lead_request_signal",
        "new_lead_attachment_signal",
        "existing_deal_reference_signal",
        "existing_deal_metadata_signal",
        "duplicate_repeat_signal",
        "duplicate_metadata_signal",
        "irrelevant_auto_reply",
        "irrelevant_bulk_signal",
        "irrelevant_supplier_or_bulk_signal",
        "irrelevant_service_notification",
        "irrelevant_finance_document",
        "irrelevant_logistics_notification",
        "attachment_aware_new_lead",
        "attachment_aware_existing_deal",
        "ambiguous_existing_deal_candidate",
        "fallback_reply_context",
        "fallback_attachment_context",
        "fallback_low_signal",
    }
    return sorted(all_known - set(_CLASSIFICATION_REASON_DISPLAY))
