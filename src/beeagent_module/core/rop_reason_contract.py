from __future__ import annotations

AI_REASON_CODES = frozenset(
    {
        "customer_request_detected",
        "tender_or_rfq_detected",
        "existing_deal_continuation",
        "logistics_or_finance_continuation",
        "non_actionable_supplier_outreach",
        "non_actionable_bulk_or_newsletter",
        "non_actionable_service_notification",
        "insufficient_business_signal",
        "conflicting_business_signals",
    }
)
AI_REASON_CODES_BY_CASE_TYPE = {
    "new_lead": frozenset(
        {
            "customer_request_detected",
            "tender_or_rfq_detected",
            "conflicting_business_signals",
        }
    ),
    "existing_deal": frozenset(
        {
            "existing_deal_continuation",
            "logistics_or_finance_continuation",
            "conflicting_business_signals",
        }
    ),
    "irrelevant": frozenset(
        {
            "non_actionable_supplier_outreach",
            "non_actionable_bulk_or_newsletter",
            "non_actionable_service_notification",
            "insufficient_business_signal",
            "conflicting_business_signals",
        }
    ),
}
AI_EVIDENCE_CODES = frozenset(
    {
        "marketing_conflict",
        "spam_rfq_conflict",
        "supplier_outreach",
        "low_signal",
        "ambiguous_bitrix",
        "newsletter_bulk",
        "finance_sales_conflict",
        "business_ignore_conflict",
        "attachment_mismatch",
    }
)
ATTENTION_REASON_CODES = frozenset(
    {
        "ai_low_confidence_safe_ignore_preserved",
        "ai_low_confidence_manual_review",
        "ai_output_conflict_manual_review",
        "ai_validation_error_manual_review",
        "ai_output_with_validation_errors_deterministic_result_preserved",
        "ai_confidence_below_threshold_deterministic_result_preserved",
        "missing_api_key_deterministic_result_preserved",
        "provider_call_failed_deterministic_result_preserved",
        "ai_output_invalid_deterministic_result_preserved",
        "deterministic_result_preserved",
        "ai_adjudicator_unexpected_status",
    }
)
AI_EVIDENCE_CODES_MAX = 5
