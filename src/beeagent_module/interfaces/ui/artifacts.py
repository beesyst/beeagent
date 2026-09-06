from __future__ import annotations

from pathlib import Path

ARTIFACT_ALLOWLIST: dict[str, str] = {
    "run_json": "run.json",
    "operator_summary_json": "operator_summary.json",
    "source_diagnostics_json": "source_diagnostics.json",
    "intake_metadata_json": "intake_metadata.json",
    "normalized_events_json": "normalized_events.json",
    "classified_events_json": "classified_events.json",
    "attachment_extraction_json": "attachment_extraction.json",
    "attachment_manifest_json": "attachment_manifest.json",
    "attachment_analysis_json": "attachment_analysis.json",
    "rop_review_table_tsv": "rop_review_table.tsv",
    "rop_current_state_json": "rop_current_state.json",
    "bitrix_reconciliation_json": "bitrix_reconciliation.json",
    "rop_recipient_routing_json": "rop_recipient_routing.json",
    "module_result_json": "module-beeagent-rop/module_result.json",
    "rop_summary_result_json": "module-beeagent-rop/rop_summary_result.json",
    "lead_classification_result_json": (
        "module-beeagent-rop/lead_classification_result.json"
    ),
    "steps_json": "steps.json",
    "rop_mvp_pack_json": "rop_mvp_pack.json",
    "rop_mvp_report_md": "rop_mvp_report.md",
    "mailbox_selection_json": "mailbox_selection.json",
    "mail_thread_index_json": "mail_thread_index.json",
    "mail_thread_context_json": "mail_thread_context.json",
    "rop_conversation_json": "rop_conversation.json",
    "rop_outbound_correlation_json": "bitrix_outbound_correlation.json",
    "rop_ai_assist_requests_json": "rop_ai_assist_requests.json",
    "rop_ai_assist_decisions_json": "rop_ai_assist_decisions.json",
    "rop_ai_assist_results_json": "rop_ai_assist_results.json",
    "rop_ai_adjudicator_requests_json": "rop_ai_adjudicator_requests.json",
    "rop_ai_adjudicator_decisions_json": "rop_ai_adjudicator_decisions.json",
    "rop_ai_adjudicator_results_json": "rop_ai_adjudicator_results.json",
    "rop_final_decisions_json": "rop_final_decisions.json",
    "rop_writeback_summary_json": "rop_writeback_summary.json",
}
MODULE_ARTIFACT_IDS = frozenset(
    {
        "module_result_json",
        "rop_summary_result_json",
        "lead_classification_result_json",
    }
)
CONTENT_TYPE_MAP: dict[str, str] = {
    "run_json": "application/json",
    "operator_summary_json": "application/json",
    "source_diagnostics_json": "application/json",
    "intake_metadata_json": "application/json",
    "normalized_events_json": "application/json",
    "classified_events_json": "application/json",
    "attachment_extraction_json": "application/json",
    "rop_review_table_tsv": "text/tab-separated-values",
    "rop_current_state_json": "application/json",
    "bitrix_reconciliation_json": "application/json",
    "rop_recipient_routing_json": "application/json",
    "module_result_json": "application/json",
    "rop_summary_result_json": "application/json",
    "lead_classification_result_json": "application/json",
    "steps_json": "application/json",
    "rop_mvp_pack_json": "application/json",
    "rop_mvp_report_md": "text/markdown",
    "mailbox_selection_json": "application/json",
    "mail_thread_index_json": "application/json",
    "mail_thread_context_json": "application/json",
    "rop_conversation_json": "application/json",
    "rop_outbound_correlation_json": "application/json",
    "rop_ai_assist_requests_json": "application/json",
    "rop_ai_assist_decisions_json": "application/json",
    "rop_ai_assist_results_json": "application/json",
    "rop_ai_adjudicator_requests_json": "application/json",
    "rop_ai_adjudicator_decisions_json": "application/json",
    "rop_ai_adjudicator_results_json": "application/json",
    "rop_final_decisions_json": "application/json",
    "rop_writeback_summary_json": "application/json",
}


def resolve_artifact_path(
    storage_dir: Path, run_id: str, artifact_id: str
) -> Path | None:
    rel_path_str = ARTIFACT_ALLOWLIST.get(artifact_id)
    if rel_path_str is None:
        return None

    runs_dir = (storage_dir / "runs").resolve()
    run_dir = (runs_dir / run_id).resolve()

    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        return None

    artifact_path = (run_dir / rel_path_str).resolve()

    try:
        artifact_path.relative_to(run_dir)
    except ValueError:
        return None

    if not artifact_path.exists():
        return None

    return artifact_path


def get_artifact_content_type(artifact_id: str) -> str:
    return CONTENT_TYPE_MAP.get(artifact_id, "application/octet-stream")


def list_available_artifact_ids(storage_dir: Path, run_id: str) -> list[dict[str, str]]:
    runs_dir = (storage_dir / "runs").resolve()
    run_dir = (runs_dir / run_id).resolve()

    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        return []

    if not run_dir.is_dir():
        return []

    available: list[dict[str, str]] = []
    for aid, rel_path in ARTIFACT_ALLOWLIST.items():
        artifact_path = (run_dir / rel_path).resolve()
        try:
            artifact_path.relative_to(run_dir)
        except ValueError:
            continue
        if artifact_path.exists():
            available.append(
                {
                    "artifact_id": aid,
                    "content_type": get_artifact_content_type(aid),
                }
            )

    return available


def is_artifact_id_allowed(artifact_id: str) -> bool:
    return artifact_id in ARTIFACT_ALLOWLIST
