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
    "rop_review_table_tsv": "rop_review_table.tsv",
    "module_result_json": "module-beeagent-rop/module_result.json",
    "rop_summary_result_json": "module-beeagent-rop/rop_summary_result.json",
    "lead_classification_result_json": (
        "module-beeagent-rop/lead_classification_result.json"
    ),
    "steps_json": "steps.json",
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
    "module_result_json": "application/json",
    "rop_summary_result_json": "application/json",
    "lead_classification_result_json": "application/json",
    "steps_json": "application/json",
}


# Разрешение allowlisted артефакта для ран-уровня, с защитой от path traversal и проверкой существования
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


# Получение типа содержимого для разрешенного артефакта
def get_artifact_content_type(artifact_id: str) -> str:
    return CONTENT_TYPE_MAP.get(artifact_id, "application/octet-stream")


# Список разрешенных артефактов для ран-уровня, с защитой от path traversal и проверкой существования
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


# Чек, что артефакт в allowlist и его путь корректный, с защитой от path traversal
def is_artifact_id_allowed(artifact_id: str) -> bool:
    return artifact_id in ARTIFACT_ALLOWLIST
