from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

from beeagent_module.cases.rop_context_enrichment import (
    build_context_enrichment,
    write_context_enrichment_artifact,
)
from beeagent_module.cases.rop_current_state import (
    build_rop_current_state,
    write_current_state,
)
from beeagent_module.cases.rop_evaluation import (
    evaluate_reviewed_tsv,
    write_evaluation_artifact,
)
from beeagent_module.cases.rop_mvp_pack import (
    build_rop_mvp_pack,
    write_mvp_pack_artifacts,
)
from beeagent_module.cases.rop_operator import run_rop_batch_case
from beeagent_module.cases.rop_recommendations import (
    build_recommendations,
    build_routing_map,
)
from beeagent_module.core.paths import get_project_root, get_storage_dir

REVIEW_BODY_SHORT_MAX_CHARS = 500
_SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _validate_cli_run_id(run_id: str) -> None:
    if not isinstance(run_id, str):
        raise RopCliError("Invalid run_id")

    if not _SAFE_RUN_ID_RE.fullmatch(run_id):
        raise RopCliError(f"Invalid run_id: {run_id}")

    if ".." in run_id:
        raise RopCliError(f"Invalid run_id: {run_id}")


class RopCliError(Exception):
    pass


def _dashboard_default_period(settings: dict) -> str:
    return settings["rop"]["dashboard"]["default_period"]


def _dashboard_periods(settings: dict) -> list[str]:
    return list(settings["rop"]["dashboard"]["periods"])


def handle_rop_run(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    project_root = get_project_root()

    effective_settings = _apply_source_overrides(
        settings=settings,
        source_id=args.source_id,
        all_sources=args.all_sources,
        items_max=args.items_max,
        logger=logger,
    )

    run_id = args.run_id

    logger.info(
        "ROP CLI: starting run with overrides source_id=%s items_max=%s",
        args.source_id or "default",
        args.items_max or "default",
    )

    try:
        result = run_rop_batch_case(
            settings=effective_settings,
            storage_dir=storage_dir,
            project_root=project_root,
            logger=logger,
            run_id=run_id,
            period_override=args.period,
            source_id=args.source_id,
            all_sources=args.all_sources,
        )

        operator_text = result.get("operator_text", "")
        print("\n" + operator_text + "\n")

        effective_run_id = str(result.get("run_id") or run_id or "")
        try:
            tsv_output_path = _export_review_tsv_for_run(
                storage_dir=storage_dir,
                run_id=effective_run_id,
                logger=logger,
            )
        except Exception as exc:
            logger.error(
                "ROP CLI: review TSV export failed for run_id=%s: %s",
                effective_run_id,
                exc,
            )
            raise RopCliError(
                f"ROP run completed but review TSV export failed: {exc}"
            ) from exc

        print("Paste this TSV into Google Sheets for human review.")

        try:
            state = build_rop_current_state(
                storage_dir=storage_dir,
                run_id=effective_run_id,
                logger=logger,
            )
            write_current_state(
                storage_dir=storage_dir,
                run_id=effective_run_id,
                state=state,
                logger=logger,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: current-state build failed after run: %s",
                exc,
            )

        try:
            from beeagent_module.cases.rop_dashboard import (
                build_rop_dashboard,
                write_rop_dashboard,
            )

            dashboard = build_rop_dashboard(
                storage_dir=storage_dir,
                period=_dashboard_default_period(settings),
                logger=logger,
                run_id=effective_run_id,
            )
            write_rop_dashboard(
                storage_dir=storage_dir,
                dashboard=dashboard,
                logger=logger,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: dashboard build failed after run: %s",
                exc,
            )

        logger.info(
            "ROP CLI: run completed successfully: run_id=%s status=%s",
            result.get("run_id"),
            result.get("status"),
        )

    except Exception as exc:
        logger.error("ROP CLI: run failed: %s", exc)
        raise RopCliError(f"ROP run failed: {exc}") from exc


def handle_rop_summary(
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    summary_path = storage_dir / "runs" / run_id / "operator_summary.json"

    if not summary_path.exists():
        raise RopCliError(
            f"operator_summary.json not found for run_id={run_id} at {summary_path}"
        )

    try:
        with summary_path.open("r", encoding="utf-8") as f:
            summary_data = json.load(f)
    except json.JSONDecodeError as exc:
        raise RopCliError(f"Failed to parse operator_summary.json: {exc}") from exc

    summary_text = _build_summary_text(summary_data)
    print("\n" + summary_text + "\n")

    logger.info("ROP CLI: summary displayed for run_id=%s", run_id)


def handle_rop_export_review(
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id
    format_type = args.format

    if format_type != "tsv":
        raise RopCliError(
            f"Unsupported format for v1: {format_type}. Only 'tsv' is supported."
        )

    _export_review_tsv_for_run(storage_dir=storage_dir, run_id=run_id, logger=logger)


def handle_rop_reconcile_bitrix(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    logger.info(
        "ROP CLI: starting bitrix reconciliation for run_id=%s",
        run_id,
    )

    from beeagent_module.cases.rop_bitrix_reconciliation import run_reconciliation

    try:
        result = run_reconciliation(
            storage_dir=storage_dir,
            run_id=run_id,
            settings=settings,
            logger=logger,
        )
        status = result.get("status", "?")
        aggregate = result.get("aggregate", {})
        print(
            f"\nBitrix reconciliation completed: status={status}\n"
            f"  events:              {aggregate.get('event_count', 0)}\n"
            f"  safe_matched:        {aggregate.get('safe_matched_count', 0)}\n"
            f"  matched:             {aggregate.get('matched_count', 0)}\n"
            f"  weak_match:          {aggregate.get('weak_match_count', 0)}\n"
            f"  not_found:           {aggregate.get('not_found_count', 0)}\n"
            f"  duplicates:          {aggregate.get('duplicate_candidate_count', 0)}\n"
            f"  ambiguous:           {aggregate.get('ambiguous_count', 0)}\n"
            f"  skipped:             {aggregate.get('skipped_count', 0)}\n"
            f"  connector_degraded:  {aggregate.get('connector_degraded_count', 0)}\n"
            f"  errors:              {aggregate.get('error_count', 0)}\n"
            f"  manual_review:       {aggregate.get('manual_review_count', 0)}\n"
        )

        try:
            state = build_rop_current_state(
                storage_dir=storage_dir,
                run_id=run_id,
                logger=logger,
            )
            write_current_state(
                storage_dir=storage_dir,
                run_id=run_id,
                state=state,
                logger=logger,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: current-state build failed after bitrix reconciliation: %s",
                exc,
            )

        logger.info(
            "ROP CLI: bitrix reconciliation finished: run_id=%s status=%s",
            run_id,
            status,
        )

        try:
            from beeagent_module.cases.rop_dashboard import (
                build_rop_dashboard,
                write_rop_dashboard,
            )

            dashboard = build_rop_dashboard(
                storage_dir=storage_dir,
                period=_dashboard_default_period(settings),
                logger=logger,
                run_id=run_id,
            )
            write_rop_dashboard(
                storage_dir=storage_dir,
                dashboard=dashboard,
                logger=logger,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: dashboard build failed after reconciliation: %s",
                exc,
            )

        try:
            from beeagent_module.cases.rop_action_drafts import build_action_drafts

            build_action_drafts(
                storage_dir=storage_dir,
                run_id=run_id,
                reconciliation=result,
                logger=logger,
            )
            logger.info(
                "ROP CLI: action drafts auto-generated after reconciliation: run_id=%s",
                run_id,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: action drafts generation failed after reconciliation: %s",
                exc,
            )

    except Exception as exc:
        logger.error("ROP CLI: bitrix reconciliation failed: %s", exc)
        raise RopCliError(f"Bitrix reconciliation failed: {exc}") from exc


def _apply_source_overrides(
    settings: dict,
    source_id: str | None,
    all_sources: bool,
    items_max: int | None,
    logger: logging.Logger,
) -> dict:
    import copy

    effective = copy.deepcopy(settings)

    sources = effective.get("rop", {}).get("sources", [])
    if not sources:
        raise RopCliError("rop.sources is not configured")

    if source_id and all_sources:
        raise RopCliError("--source-id and --all-sources cannot be used together")

    if source_id:
        selected_source: dict[str, Any] | None = None

        for source in sources:
            if source.get("source_id") == source_id:
                selected_source = source
                break

        if selected_source is None:
            raise RopCliError(f"Source not found in rop.sources: source_id={source_id}")

        if not selected_source.get("enabled", False):
            raise RopCliError(
                f"Source is disabled in rop.sources: source_id={source_id}"
            )

        for source in sources:
            source["enabled"] = source is selected_source

        if items_max is not None:
            selected_source["items_max"] = items_max

        logger.debug(
            "CLI override applied: source_id=%s items_max=%s",
            source_id,
            items_max,
        )
    elif all_sources:
        enabled_sources = [source for source in sources if source.get("enabled", False)]
        if not enabled_sources:
            raise RopCliError(
                "No enabled sources found in rop.sources for --all-sources"
            )

        for source in enabled_sources:
            if items_max is not None:
                source["items_max"] = items_max

        logger.debug(
            "CLI override applied: all enabled sources items_max=%s count=%d",
            items_max,
            len(enabled_sources),
        )
    else:
        for source in sources:
            if source.get("enabled", False):
                if items_max is not None:
                    source["items_max"] = items_max

    return effective


def _export_review_tsv_for_run(
    storage_dir: Any,
    run_id: str,
    logger: logging.Logger,
) -> str:
    normalized_path = storage_dir / "runs" / run_id / "normalized_events.json"
    classified_path = storage_dir / "runs" / run_id / "classified_events.json"
    tsv_output_path = storage_dir / "runs" / run_id / "rop_review_table.tsv"

    if not normalized_path.exists():
        raise RopCliError(f"normalized_events.json not found for run_id={run_id}")
    if not classified_path.exists():
        raise RopCliError(f"classified_events.json not found for run_id={run_id}")

    try:
        with normalized_path.open("r", encoding="utf-8") as f:
            normalized_events = json.load(f)
        with classified_path.open("r", encoding="utf-8") as f:
            classified_events = json.load(f)
    except json.JSONDecodeError as exc:
        raise RopCliError(f"Failed to parse JSON artifacts: {exc}") from exc

    reconciliation_path = storage_dir / "runs" / run_id / "bitrix_reconciliation.json"
    reconciliation_data = None
    if reconciliation_path.exists():
        try:
            reconciliation_data = json.loads(
                reconciliation_path.read_text(encoding="utf-8")
            )
            logger.debug(
                "ROP CLI: bitrix reconciliation artifact found for TSV enrichment: %s",
                reconciliation_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "ROP CLI: failed to read bitrix reconciliation artifact: %s", exc
            )

    action_drafts_path = storage_dir / "runs" / run_id / "rop_action_drafts.json"
    action_drafts_data = None
    if action_drafts_path.exists():
        try:
            action_drafts_data = json.loads(
                action_drafts_path.read_text(encoding="utf-8")
            )
            logger.debug(
                "ROP CLI: action drafts artifact found for TSV enrichment: %s",
                action_drafts_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("ROP CLI: failed to read action drafts artifact: %s", exc)

    tsv_rows = _build_review_tsv_rows(
        normalized_events,
        classified_events,
        reconciliation_data=reconciliation_data,
        action_drafts_data=action_drafts_data,
    )

    try:
        with tsv_output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=_tsv_columns(),
                delimiter="\t",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(tsv_rows)
    except Exception as exc:
        raise RopCliError(f"Failed to write TSV: {exc}") from exc

    print(f"\nReview TSV exported: {tsv_output_path}")
    logger.info(
        "ROP CLI: review TSV exported for run_id=%s path=%s rows=%d",
        run_id,
        tsv_output_path,
        len(tsv_rows),
    )
    return tsv_output_path.as_posix()


def _build_summary_text(summary_data: dict[str, Any]) -> str:
    run_id = summary_data.get("run_id", "?")
    module_id = summary_data.get("module_id", "?")
    case_type = summary_data.get("case_type", "?")
    status = summary_data.get("status", "?")
    module_status = summary_data.get("module_status", "?")
    summary = summary_data.get("summary", "")
    source = summary_data.get("source", {}) or {}
    sources = summary_data.get("sources", []) or []
    classification = summary_data.get("classification", {}) or {}
    artifact_refs = summary_data.get("artifact_refs", [])

    source_block = ""
    if isinstance(source, dict) and source:
        if source.get("mode"):
            source_block = (
                f"source_mode: {source.get('mode', '?')}\n"
                f"source_count: {source.get('source_count', '?')}\n"
                f"loaded_sources: {source.get('loaded_source_count', '?')}\n"
                f"degraded_sources: {source.get('degraded_source_count', '?')}\n"
                f"fetched_count: {source.get('fetched_count', '?')}\n"
                f"loaded_count: {source.get('loaded_count', '?')}\n"
                f"malformed_count: {source.get('malformed_count', '?')}\n"
                f"status_reason: {source.get('reason', '?')}\n"
            )
        else:
            source_block = (
                f"source_id: {source.get('source_id', '?')}\n"
                f"source_type: {source.get('source_type', '?')}\n"
                f"source_role: {source.get('source_role', '?')}\n"
                f"source_display_name: {source.get('source_display_name', '?')}\n"
                f"client_id: {source.get('client_id', '?')}\n"
                f"mailbox_folder: {source.get('mailbox_folder', '?')}\n"
                f"loaded_items: {source.get('loaded_item_count', '?')}\n"
                f"fetched_count: {source.get('fetched_count', '?')}\n"
                f"loaded_count: {source.get('loaded_count', '?')}\n"
                f"malformed_count: {source.get('malformed_count', '?')}\n"
                f"period: {source.get('period', '?')}\n"
            )

    classification_block = ""
    if isinstance(classification, dict) and classification:
        classification_block = (
            f"normalized_count: {classification.get('normalized_count', '?')}\n"
            f"classified_count: {classification.get('classified_count', '?')}\n"
            f"classification_failed_count: {classification.get('classification_failed_count', '?')}\n"
        )

    artifacts_text = "\n".join(f"- {item}" for item in artifact_refs) or "- none"

    text = (
        "ROP operator summary\n"
        f"run_id: {run_id}\n"
        f"module_id: {module_id}\n"
        f"case_type: {case_type}\n"
        f"status: {status}\n"
        f"module_status: {module_status}\n"
        f"summary: {summary}\n"
    )

    if source_block:
        text += f"{source_block}"
    if classification_block:
        text += f"{classification_block}"

    if isinstance(sources, list) and sources:
        source_lines = []
        for item in sources:
            if not isinstance(item, dict):
                continue
            source_lines.append(
                "- "
                f"{item.get('source_id', '?')} "
                f"[{item.get('status', '?')}] "
                f"loaded={item.get('loaded_count', '?')} "
                f"fetched={item.get('fetched_count', '?')} "
                f"reason={item.get('reason', '-')}"
            )
        if source_lines:
            text += "sources:\n" + "\n".join(source_lines) + "\n"

    text += f"artifacts:\n{artifacts_text}"

    return text


def _safe_tsv_value(value: Any) -> str:
    if value is None or value == "":
        return ""

    text = str(value)
    text = text.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    text = " ".join(text.split())
    return text


def _build_body_short(normalized_evt: dict) -> str:
    preview = normalized_evt.get("body_preview")
    if preview and isinstance(preview, str) and preview.strip():
        return _safe_tsv_value(preview[:REVIEW_BODY_SHORT_MAX_CHARS])

    preview = normalized_evt.get("text_preview")
    if preview and isinstance(preview, str) and preview.strip():
        return _safe_tsv_value(preview[:REVIEW_BODY_SHORT_MAX_CHARS])

    body = normalized_evt.get("body")
    if body and isinstance(body, str) and body.strip():
        return _safe_tsv_value(body[:REVIEW_BODY_SHORT_MAX_CHARS])

    return ""


def _is_blocked_email_attachment(att: dict[str, Any]) -> bool:
    filename = str(att.get("filename") or "").strip().lower()
    content_type = str(att.get("content_type") or "").strip().lower()
    return filename.endswith(".eml") or content_type == "message/rfc822"


def _build_attachment_summary(attachments: Any) -> str:
    if not attachments or not isinstance(attachments, list):
        return ""

    summaries = []
    for att in attachments:
        if not isinstance(att, dict):
            continue
        if _is_blocked_email_attachment(att):
            continue

        filename = _safe_tsv_value(att.get("filename", ""))
        content_type = _safe_tsv_value(att.get("content_type", ""))
        size_bytes = att.get("size_bytes")

        if not filename:
            continue

        parts = [filename]
        meta = []

        if content_type:
            meta.append(content_type)

        if size_bytes is not None:
            try:
                size_int = int(size_bytes)
                meta.append(str(size_int))
            except ValueError, TypeError:
                pass

        summary = " ".join(parts)
        if meta:
            summary += f" ({', '.join(meta)})"
        summaries.append(_safe_tsv_value(summary))

    return _safe_tsv_value("; ".join(summaries))


def handle_rop_evaluate_review(
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()

    if args.tsv:
        tsv_path = Path(args.tsv)
        if not tsv_path.is_absolute():
            project_root = get_project_root()
            tsv_path = (project_root / tsv_path).resolve()
        run_id = args.run_id or "direct-tsv-evaluation"
        _validate_cli_run_id(run_id)
    elif args.run_id:
        run_id = args.run_id
        _validate_cli_run_id(run_id)
        tsv_path = storage_dir / "runs" / run_id / "rop_review_table.tsv"
        if not tsv_path.exists():
            raise RopCliError(
                f"rop_review_table.tsv not found for run_id={run_id}. "
                "Run rop run first, or provide --tsv path."
            )
    else:
        raise RopCliError("Either --run-id or --tsv is required for evaluate-review")

    logger.info(
        "ROP CLI: evaluating reviewed TSV: run_id=%s path=%s",
        run_id,
        tsv_path,
    )

    try:
        artifact = evaluate_reviewed_tsv(
            tsv_path=tsv_path,
            run_id=run_id,
            logger=logger,
        )
        eval_path = write_evaluation_artifact(
            storage_dir=storage_dir,
            run_id=run_id,
            artifact=artifact,
            logger=logger,
        )

        print(f"\nEvaluation artifact written: {eval_path}")
        print(f"Status: {artifact['status']}")
        print(f"Acceptance: {artifact['acceptance']['acceptance_status']}")

        metrics = artifact.get("metrics", {})
        for metric_name in (
            "case_type_accuracy",
            "case_subtype_accuracy",
            "recommended_queue_accuracy",
            "correct_action_accuracy",
            "fallback_rate",
            "critical_false_negative_rate",
            "existing_deal_as_irrelevant_count",
        ):
            value = metrics.get(metric_name)
            display = f"{value:.4f}" if isinstance(value, float) else str(value)
            print(f"  {metric_name}: {display}")

        not_evaluable = metrics.get("not_evaluable", {})
        if not_evaluable:
            print("Not evaluable metrics:")
            for key, info in not_evaluable.items():
                print(f"  {key}: {info.get('count', 0)} events")

        for check in artifact["acceptance"].get("checks", []):
            status_icon = (
                "PASS"
                if check["passed"]
                else ("N/A" if check["passed"] is None else "FAIL")
            )
            print(f"  [{status_icon}] {check['target']}: {check['value']}")

        logger.info(
            "ROP CLI: evaluate-review completed: run_id=%s status=%s",
            run_id,
            artifact["status"],
        )

    except Exception as exc:
        logger.error("ROP CLI: evaluate-review failed: %s", exc)
        raise RopCliError(f"evaluate-review failed: {exc}") from exc


def handle_rop_recommendations(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    logger.info("ROP CLI: building recommendations for run_id=%s", run_id)

    try:
        routing_map = build_routing_map(
            settings=settings,
            storage_dir=storage_dir,
            logger=logger,
        )
        logger.info(
            "ROP CLI: routing map built: queues=%d entries=%d",
            len(routing_map.get("queues", {})),
            len(routing_map.get("routing_entries", [])),
        )

        context_enrichment = build_context_enrichment(
            storage_dir=storage_dir,
            run_id=run_id,
            logger=logger,
        )
        write_context_enrichment_artifact(
            storage_dir=storage_dir,
            run_id=run_id,
            artifact=context_enrichment,
            logger=logger,
        )
        logger.info(
            "ROP CLI: context enrichment built: events=%d enriched=%d",
            context_enrichment.get("aggregate", {}).get("event_count", 0),
            context_enrichment.get("aggregate", {}).get("enriched_count", 0),
        )

        recommendations = build_recommendations(
            storage_dir=storage_dir,
            run_id=run_id,
            settings=settings,
            logger=logger,
        )

        print(f"\nRecommendations artifact written for run_id={run_id}")
        agg = recommendations.get("aggregate", {})
        print(f"  total:           {agg.get('recommendation_count', 0)}")
        print(f"  actionable:      {agg.get('actionable_count', 0)}")
        print(f"  manual_review:   {agg.get('manual_review_count', 0)}")
        print(f"  ignore:          {agg.get('ignore_count', 0)}")
        print(f"  safe_to_execute: {recommendations.get('safe_to_execute', False)}")

        logger.info(
            "ROP CLI: recommendations completed: run_id=%s items=%d",
            run_id,
            len(recommendations.get("items", [])),
        )

        try:
            from beeagent_module.cases.rop_dashboard import (
                build_rop_dashboard,
                write_rop_dashboard,
            )

            dashboard = build_rop_dashboard(
                storage_dir=storage_dir,
                period=_dashboard_default_period(settings),
                logger=logger,
                run_id=run_id,
            )
            write_rop_dashboard(
                storage_dir=storage_dir,
                dashboard=dashboard,
                logger=logger,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: dashboard build failed after recommendations: %s",
                exc,
            )

    except Exception as exc:
        logger.error("ROP CLI: recommendations failed: %s", exc)
        raise RopCliError(f"recommendations failed: {exc}") from exc


def _tsv_columns() -> list[str]:
    return [
        "event_id",
        "source_id",
        "source_type",
        "source_role",
        "source_display_name",
        "client_id",
        "sender",
        "subject",
        "body_short",
        "attachments",
        "bot_case_type",
        "bot_case_subtype",
        "bot_recommended_queue",
        "bot_should_rop_see",
        "bot_correct_action",
        "bot_reason_code",
        "bot_priority",
        "bot_confidence",
        "bot_is_fallback",
        "bot_reasoning",
        "bitrix_match_status",
        "bitrix_match_quality",
        "bitrix_confidence",
        "needs_manual_review",
        "safe_to_use_as_target",
        "recommended_action",
        "recommended_next_step",
        "action_queue",
        "action_draft_id",
        "human_case_type",
        "human_case_subtype",
        "human_recommended_queue",
        "human_should_rop_see",
        "human_correct_action",
        "bitrix_status",
        "notes",
        "bitrix_lead_id",
        "bitrix_deal_id",
        "bitrix_responsible",
        "is_duplicate",
        "duplicate_of",
    ]


def _build_review_tsv_rows(
    normalized_events: list[dict],
    classified_events: list[dict],
    reconciliation_data: dict | None = None,
    action_drafts_data: dict | None = None,
) -> list[dict[str, str]]:
    normalized_lookup = {evt.get("event_id"): evt for evt in normalized_events}

    bitrix_lookup: dict[str, dict] = {}
    if reconciliation_data and isinstance(reconciliation_data, dict):
        items = reconciliation_data.get("items", [])
        if isinstance(items, list):
            for item in items:
                eid = item.get("event_id", "")
                if eid:
                    bitrix_lookup[eid] = item

    action_drafts_lookup: dict[str, dict] = {}
    if action_drafts_data and isinstance(action_drafts_data, dict):
        items = action_drafts_data.get("items", [])
        if isinstance(items, list):
            for item in items:
                eid = item.get("event_id", "")
                if eid:
                    action_drafts_lookup[eid] = item

    rows: list[dict[str, str]] = []

    for classified_evt in classified_events:
        event_id = classified_evt.get("event_id", "")
        original_event_id = classified_evt.get("original_event_id", event_id)
        normalized_evt = normalized_lookup.get(original_event_id, {})

        body_short = _build_body_short(normalized_evt)
        attachments_summary = _build_attachment_summary(
            normalized_evt.get("attachments")
        )
        bot_priority = classified_evt.get("priority", "")
        bot_reasoning = classified_evt.get("reasoning", "")
        is_duplicate = classified_evt.get("is_duplicate")
        duplicate_of = classified_evt.get("duplicate_of", "")

        recon_item = bitrix_lookup.get(event_id, {})
        bitrix_entity_type = recon_item.get("bitrix_entity_type", "")

        bitrix_status = recon_item.get("bitrix_match_status", "")
        if not bitrix_status and bitrix_entity_type:
            bitrix_status = bitrix_entity_type

        bitrix_lead_id = ""
        bitrix_deal_id = ""
        bitrix_entity_id = recon_item.get("bitrix_entity_id")
        if bitrix_entity_id is not None:
            if bitrix_entity_type == "lead":
                bitrix_lead_id = str(bitrix_entity_id)
            elif bitrix_entity_type == "deal":
                bitrix_deal_id = str(bitrix_entity_id)

        bitrix_responsible = ""
        responsible_id = recon_item.get("bitrix_responsible_id")
        if responsible_id is not None:
            bitrix_responsible = str(responsible_id)

        bitrix_match_quality = recon_item.get("bitrix_match_quality", "")
        bitrix_confidence = recon_item.get("bitrix_confidence", "")
        needs_manual_review = recon_item.get("needs_manual_review", "")
        safe_to_use_as_target = recon_item.get("safe_to_use_as_target", "")

        action_draft_item = action_drafts_lookup.get(event_id, {})
        action_draft_id = action_draft_item.get("action_draft_id", "")
        recommended_action = action_draft_item.get("recommended_action", "")
        recommended_next_step = action_draft_item.get("recommended_next_step", "")
        action_queue = action_draft_item.get("queue", "")

        bot_should_rop_see = classified_evt.get("should_rop_see")
        bot_should_rop_see_value = (
            str(bot_should_rop_see).lower() if bot_should_rop_see is not None else ""
        )

        row = {
            "event_id": _safe_tsv_value(event_id),
            "source_id": _safe_tsv_value(classified_evt.get("source_id", "")),
            "source_type": _safe_tsv_value(classified_evt.get("source_type", "")),
            "source_role": _safe_tsv_value(classified_evt.get("source_role", "")),
            "source_display_name": _safe_tsv_value(
                classified_evt.get("source_display_name", "")
            ),
            "client_id": _safe_tsv_value(classified_evt.get("client_id", "")),
            "sender": _safe_tsv_value(normalized_evt.get("sender", "")),
            "subject": _safe_tsv_value(normalized_evt.get("subject", "")),
            "body_short": body_short,
            "attachments": _safe_tsv_value(attachments_summary),
            "bot_case_type": _safe_tsv_value(classified_evt.get("case_type", "")),
            "bot_case_subtype": _safe_tsv_value(classified_evt.get("case_subtype", "")),
            "bot_recommended_queue": _safe_tsv_value(
                classified_evt.get("recommended_queue", "")
            ),
            "bot_should_rop_see": _safe_tsv_value(bot_should_rop_see_value),
            "bot_correct_action": _safe_tsv_value(
                classified_evt.get("correct_action", "")
            ),
            "bot_reason_code": _safe_tsv_value(classified_evt.get("reason_code", "")),
            "bot_priority": _safe_tsv_value(bot_priority),
            "bot_confidence": _safe_tsv_value(classified_evt.get("confidence", "")),
            "bot_is_fallback": _safe_tsv_value(
                str(classified_evt.get("is_fallback", False)).lower()
            ),
            "bot_reasoning": _safe_tsv_value(bot_reasoning),
            "bitrix_match_status": _safe_tsv_value(bitrix_status),
            "bitrix_match_quality": _safe_tsv_value(bitrix_match_quality),
            "bitrix_confidence": _safe_tsv_value(bitrix_confidence),
            "needs_manual_review": _safe_tsv_value(str(needs_manual_review).lower()),
            "safe_to_use_as_target": _safe_tsv_value(
                str(safe_to_use_as_target).lower()
            ),
            "recommended_action": _safe_tsv_value(recommended_action),
            "recommended_next_step": _safe_tsv_value(recommended_next_step),
            "action_queue": _safe_tsv_value(action_queue),
            "action_draft_id": _safe_tsv_value(action_draft_id),
            "human_case_type": "",
            "human_case_subtype": "",
            "human_recommended_queue": "",
            "human_should_rop_see": "",
            "human_correct_action": "",
            "bitrix_status": "",
            "notes": "",
            "bitrix_lead_id": _safe_tsv_value(bitrix_lead_id),
            "bitrix_deal_id": _safe_tsv_value(bitrix_deal_id),
            "bitrix_responsible": _safe_tsv_value(bitrix_responsible),
            "is_duplicate": (
                _safe_tsv_value(str(is_duplicate).lower())
                if is_duplicate is not None
                else ""
            ),
            "duplicate_of": _safe_tsv_value(duplicate_of),
        }
        rows.append(row)

    return rows


def handle_rop_current(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    logger.info("ROP CLI: building current-state for run_id=%s", run_id)

    try:
        state = build_rop_current_state(
            storage_dir=storage_dir,
            run_id=run_id,
            logger=logger,
        )
        write_current_state(
            storage_dir=storage_dir,
            run_id=run_id,
            state=state,
            logger=logger,
        )

        print(f"\nROP current-state built: run_id={run_id}")
        print(f"  status:          {state.get('status', '?')}")
        print(f"  current_alias:   {state.get('current_alias', '?')}")
        print(f"  client_id:       {state.get('client_id', '?')}")
        kpi = state.get("kpi", {})
        print(f"  events_total:    {kpi.get('events_total', 0)}")
        print(f"  normalized:      {kpi.get('normalized_count', 0)}")
        print(f"  classified:      {kpi.get('classified_count', 0)}")
        print(f"  safe_matched:    {kpi.get('safe_matched_count', 0)}")
        print(f"  matched_in_bitrix:  {kpi.get('matched_in_bitrix', 0)}")
        print(f"  weak_match:        {kpi.get('weak_match_count', 0)}")
        print(f"  lost_in_bitrix:     {kpi.get('lost_in_bitrix', 0)}")
        print(f"  unreconciled:       {kpi.get('unreconciled', 0)}")
        print(f"  connector_degraded: {kpi.get('connector_degraded', 0)}")
        warnings = state.get("warnings", [])
        if warnings:
            print(f"  warnings: {len(warnings)}")
            for w in warnings:
                print(f"    - [{w.get('code', '?')}] {w.get('message', '')}")
        print()

        try:
            from beeagent_module.cases.rop_dashboard import (
                build_rop_dashboard,
                write_rop_dashboard,
            )

            dashboard = build_rop_dashboard(
                storage_dir=storage_dir,
                period=_dashboard_default_period(settings),
                logger=logger,
                run_id=run_id,
            )
            write_rop_dashboard(
                storage_dir=storage_dir,
                dashboard=dashboard,
                logger=logger,
            )
        except Exception as exc:
            logger.warning(
                "ROP CLI: dashboard build failed after current-state: %s",
                exc,
            )

        logger.info(
            "ROP CLI: current-state built successfully: run_id=%s status=%s warnings=%d",
            run_id,
            state.get("status"),
            len(warnings),
        )
    except Exception as exc:
        logger.error("ROP CLI: current-state build failed: %s", exc)
        raise RopCliError(f"ROP current-state build failed: {exc}") from exc


def handle_rop_dashboard(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    period = args.period or _dashboard_default_period(settings)
    if period not in _dashboard_periods(settings):
        raise RopCliError(
            f"Invalid period '{period}', expected one of: {_dashboard_periods(settings)}"
        )
    run_id = args.run_id

    logger.info(
        "ROP CLI: building dashboard for period=%s run_id=%s",
        period,
        run_id or "latest",
    )

    from beeagent_module.cases.rop_dashboard import (
        build_rop_dashboard,
        write_rop_dashboard,
    )

    try:
        dashboard = build_rop_dashboard(
            storage_dir=storage_dir,
            period=period,
            logger=logger,
            run_id=run_id,
        )

        path = write_rop_dashboard(
            storage_dir=storage_dir,
            dashboard=dashboard,
            logger=logger,
        )

        status = dashboard.get("status", "?")
        bkpi = dashboard.get("business_kpi", {})
        print(f"\nROP dashboard built: period={period} status={status}")
        print(f"  artifact:          {path}")
        print(f"  run_id:            {dashboard.get('run_id', '?')}")
        print(f"  client_id:         {dashboard.get('client_id', '?')}")
        print(f"  processed_events:  {bkpi.get('processed_events', 0)}")
        print(f"  new_leads:         {bkpi.get('new_leads', 0)}")
        print(f"  high_priority:     {bkpi.get('high_priority', 0)}")
        print(f"  needs_review:      {bkpi.get('needs_review', 0)}")
        print(f"  lost_in_bitrix:    {bkpi.get('lost_in_bitrix', 0)}")
        print(f"  unreconciled:      {bkpi.get('unreconciled', 0)}")
        print(f"  source_degraded:   {bkpi.get('source_degraded', 0)}")
        print(f"  attachment_refused: {bkpi.get('attachment_refused', 0)}")

        recs = dashboard.get("rop_recommendations", [])
        if recs:
            print(f"  recommendations:   {len(recs)}")
            for rec in recs:
                print(
                    f"    - [{rec.get('severity', '?')}] "
                    f"{rec.get('title', '')} "
                    f"({rec.get('count', 0)})"
                )

        warnings = dashboard.get("warnings", [])
        if warnings:
            print(f"  warnings:          {len(warnings)}")
            for w in warnings:
                print(f"    - [{w.get('code', '?')}] {w.get('message', '')}")
        print()

        logger.info(
            "ROP CLI: dashboard built successfully: period=%s run_id=%s status=%s",
            period,
            dashboard.get("run_id", "?"),
            status,
        )
    except Exception as exc:
        logger.error("ROP CLI: dashboard build failed: %s", exc)
        raise RopCliError(f"ROP dashboard build failed: {exc}") from exc


def handle_rop_mvp_pack(
    args: argparse.Namespace,
    settings: dict,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    try:
        configured_periods = _dashboard_periods(settings)
        period = args.period or _dashboard_default_period(settings)
    except KeyError as exc:
        raise RopCliError(
            "rop.dashboard.default_period and rop.dashboard.periods are required "
            "for ROP MVP pack period selection"
        ) from exc

    if period not in configured_periods:
        raise RopCliError(
            f"Invalid period '{period}', expected one of: {configured_periods}"
        )

    logger.info(
        "ROP CLI: building MVP pack for run_id=%s period=%s",
        run_id,
        period,
    )

    try:
        pack = build_rop_mvp_pack(
            storage_dir=storage_dir,
            run_id=run_id,
            period=period,
            settings=settings,
            logger=logger,
        )
        paths = write_mvp_pack_artifacts(
            storage_dir=storage_dir,
            run_id=run_id,
            pack=pack,
            logger=logger,
        )

        print(f"\nROP MVP pack built: run_id={run_id} period={period}")
        print(f"  status:             {pack.get('status', '?')}")
        print(f"  client_id:          {pack.get('client_id', '?')}")
        print(
            f"  configured_sources: {pack.get('source_coverage', {}).get('configured', 0)}"
        )
        print(
            f"  loaded_sources:     {pack.get('source_coverage', {}).get('loaded', 0)}"
        )
        print(
            f"  degraded_sources:   {pack.get('source_coverage', {}).get('degraded', 0)}"
        )
        print(
            f"  classified_events:  {pack.get('business_summary', {}).get('classified_count', 0)}"
        )
        print(
            f"  high_priority:      {pack.get('business_summary', {}).get('high_priority', 0)}"
        )
        print(
            f"  demo_readiness:     {pack.get('demo_readiness', {}).get('status', '?')}"
        )
        print()
        print(f"  pack JSON:   {paths['pack']}")
        print(f"  report MD:   {paths['report']}")
        print(f"  interface:   {paths['latest']}")
        print()

        warnings = pack.get("warnings", [])
        if warnings:
            print(f"  warnings: {len(warnings)}")
            for w in warnings:
                print(f"    - {w}")
        print()

        limitations = pack.get("limitations", [])
        if limitations:
            print("  Known limitations:")
            for lim in limitations:
                print(f"    - {lim}")
        print()

        logger.info(
            "ROP CLI: MVP pack built successfully: run_id=%s status=%s warnings=%d",
            run_id,
            pack.get("status"),
            len(warnings),
        )
    except FileNotFoundError as exc:
        logger.error("ROP CLI: MVP pack build failed (run not found): %s", exc)
        raise RopCliError(str(exc)) from exc
    except ValueError as exc:
        logger.error("ROP CLI: MVP pack build failed (invalid input): %s", exc)
        raise RopCliError(str(exc)) from exc
    except Exception as exc:
        logger.error("ROP CLI: MVP pack build failed: %s", exc)
        raise RopCliError(f"ROP MVP pack build failed: {exc}") from exc


def handle_rop_action_drafts(
    args: argparse.Namespace,
    logger: logging.Logger,
) -> None:
    storage_dir = get_storage_dir()
    run_id = args.run_id

    logger.info(
        "ROP CLI: generating action drafts for run_id=%s",
        run_id,
    )

    from beeagent_module.cases.rop_action_drafts import build_action_drafts

    runs_dir = (storage_dir / "runs").resolve()
    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        raise RopCliError(f"Invalid run_id: path traversal detected for '{run_id}'")

    reconciliation_path = run_dir / "bitrix_reconciliation.json"
    if not reconciliation_path.exists():
        raise RopCliError(
            f"bitrix_reconciliation.json not found for run_id={run_id}. "
            "Run rop reconcile-bitrix first."
        )

    try:
        reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RopCliError(f"Failed to read bitrix_reconciliation.json: {exc}") from exc

    artifact = build_action_drafts(
        storage_dir=storage_dir,
        run_id=run_id,
        reconciliation=reconciliation,
        logger=logger,
    )

    aggregate = artifact.get("aggregate", {})
    print(
        f"\nROP action drafts generated: run_id={run_id}\n"
        f"  items:                    {len(artifact.get('items', []))}\n"
        f"  actionable:               {aggregate.get('matched_actionable', 0)}\n"
        f"  ignore:                   {aggregate.get('ignore_count', 0)}\n"
        f"  degraded:                 {aggregate.get('degraded_count', 0)}\n"
        f"  unreconciled:             {aggregate.get('unreconciled_count', 0)}\n"
        f"  needs_manual_review:      {aggregate.get('needs_manual_review_count', 0)}\n"
        f"  safe_to_use_as_target:    {aggregate.get('safe_to_use_as_target_count', 0)}\n"
    )

    logger.info(
        "ROP CLI: action drafts generated: run_id=%s items=%d",
        run_id,
        len(artifact.get("items", [])),
    )


def create_rop_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start.py rop",
        description="ROP CLI entrypoint for batch processing",
    )

    subparsers = parser.add_subparsers(dest="rop_command", required=True)

    run_parser = subparsers.add_parser("run", help="Run ROP batch pipeline")
    run_parser.add_argument(
        "--source-id",
        type=str,
        default=None,
        help="Override source_id from rop.sources (optional)",
    )
    run_parser.add_argument(
        "--all-sources",
        action="store_true",
        help="Run all enabled sources from rop.sources",
    )
    run_parser.add_argument(
        "--items-max",
        type=int,
        default=None,
        help="Override items_max for selected source (optional)",
    )
    run_parser.add_argument(
        "--period",
        type=str,
        default=None,
        help="Override period for batch source (optional)",
    )
    run_parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Explicit run_id (optional, generated if not provided)",
    )

    summary_parser = subparsers.add_parser("summary", help="Display run summary")
    summary_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to display summary for",
    )

    export_parser = subparsers.add_parser(
        "export-review", help="Export TSV for human review"
    )
    export_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to export review for",
    )
    export_parser.add_argument(
        "--format",
        type=str,
        choices=["tsv"],
        default="tsv",
        help="Export format (default: tsv)",
    )

    current_parser = subparsers.add_parser(
        "current",
        help="Build current-state index for a ROP run",
    )
    current_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to build current-state for",
    )

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Build ROP business dashboard with period analytics",
    )
    dashboard_parser.add_argument(
        "--period",
        type=str,
        default=None,
        help="Period for dashboard analytics; defaults to rop.dashboard.default_period",
    )
    dashboard_parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Explicit run_id (optional, uses latest ROP run if not provided)",
    )

    reconcile_parser = subparsers.add_parser(
        "reconcile-bitrix",
        help="Reconcile existing ROP run artifacts with Bitrix CRM (read-only)",
    )
    reconcile_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to reconcile with Bitrix",
    )

    mvp_parser = subparsers.add_parser(
        "mvp-pack",
        help="Build ROP MVP handoff/readiness pack from existing artifacts",
    )
    mvp_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to build MVP pack for",
    )
    mvp_parser.add_argument(
        "--period",
        type=str,
        default=None,
        help="Period label for report (e.g. 7d, 30d); defaults to rop.dashboard.default_period",
    )

    action_drafts_parser = subparsers.add_parser(
        "action-drafts",
        help="Generate ROP action draft artifacts from Bitrix reconciliation",
    )
    action_drafts_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to generate action drafts for",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate-review",
        help="Evaluate classification quality from reviewed TSV",
    )
    evaluate_parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="run_id to evaluate (reads rop_review_table.tsv from run dir)",
    )
    evaluate_parser.add_argument(
        "--tsv",
        type=str,
        default=None,
        help="Direct path to reviewed TSV file",
    )

    recommendations_parser = subparsers.add_parser(
        "recommendations",
        help="Build ROP recommendations artifact from existing run artifacts",
    )
    recommendations_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="run_id to build recommendations for",
    )

    return parser
