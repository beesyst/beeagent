from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
from pathlib import Path
from typing import Any

DASHBOARD_ARTIFACT = "rop_dashboard.json"
ALLOWED_PERIODS: tuple[str, ...] = (
    "today",
    "yesterday",
    "7d",
    "30d",
    "90d",
    "365d",
    "all",
)

ALLOWED_CASE_TYPES: tuple[str, ...] = (
    "new_lead",
    "existing_client",
    "existing_deal",
    "existing_lead",
    "follow_up",
    "reminder",
    "irrelevant",
    "spam",
    "ignore",
    "needs_review",
    "unclear",
    "finance_document",
    "other",
)
ALLOWED_PRIORITIES: tuple[str, ...] = ("low", "medium", "high", "critical")
ALLOWED_BITRIX_STATUSES: tuple[str, ...] = (
    "not_found",
    "weak_match",
    "ambiguous",
    "duplicate_candidate",
    "connector_degraded",
    "error",
    "skipped",
    "unreconciled",
)
ALLOWED_SORT_FIELDS: tuple[str, ...] = (
    "received_at",
    "date",
    "event_date",
    "sender",
    "subject",
    "case_type",
    "priority",
    "bitrix_status",
)
ALLOWED_PAGE_SIZES: tuple[int, ...] = (25, 50, 100)
DEFAULT_PAGE_SIZE = 25

ALLOWED_QUEUE_IDS: tuple[str, ...] = (
    "high_priority",
    "needs_review",
    "lost_in_bitrix",
    "ambiguous",
    "degraded",
    "unreconciled",
)
ALLOWED_COLUMN_KEYS: tuple[str, ...] = (
    "priority",
    "client",
    "subject",
    "date",
    "classification",
    "bitrix_status",
)
ALLOWED_DROPDOWN_KEYS: tuple[str, ...] = (
    "case_type",
    "priority",
    "bitrix_status",
)


def validate_filter_params(
    params: dict[str, str],
) -> list[str]:
    errors: list[str] = []

    allowed_keys = frozenset({
        "date_from",
        "date_to",
        "q",
        "sender",
        "subject",
        "case_type",
        "classification",
        "priority",
        "bitrix_status",
        "is_fallback",
        "queue",
        "columns",
        "columns_open",
        "open_dropdowns",
    })
    for key in params:
        if key not in allowed_keys:
            errors.append(f"Unknown filter key: '{key}'")

    classification = params.get("classification", "")
    if classification:
        for val in classification.split(","):
            val = val.strip()
            if val and val not in ALLOWED_CASE_TYPES:
                errors.append(
                    f"Invalid classification '{val}', "
                    f"expected one of: {ALLOWED_CASE_TYPES}"
                )

    case_type = params.get("case_type", "")
    if case_type:
        for val in case_type.split(","):
            val = val.strip()
            if val and val not in ALLOWED_CASE_TYPES:
                errors.append(
                    f"Invalid case_type '{val}', expected one of: {ALLOWED_CASE_TYPES}"
                )

    priority = params.get("priority", "")
    if priority:
        for val in priority.split(","):
            val = val.strip()
            if val and val not in ALLOWED_PRIORITIES:
                errors.append(
                    f"Invalid priority '{val}', expected one of: {ALLOWED_PRIORITIES}"
                )

    is_fallback = params.get("is_fallback", "")
    if is_fallback and is_fallback not in ("true", "false"):
        errors.append(f"Invalid is_fallback '{is_fallback}', expected 'true' or 'false'")

    bitrix_status = params.get("bitrix_status", "")
    if bitrix_status:
        for val in bitrix_status.split(","):
            val = val.strip()
            if val:
                if val.startswith("matched_"):
                    pass  # matched_{entity_type} — динамический статус от Bitrix
                elif val not in ALLOWED_BITRIX_STATUSES:
                    errors.append(
                        f"Invalid bitrix_status '{val}', "
                        f"expected one of: {ALLOWED_BITRIX_STATUSES}"
                    )

    date_from = params.get("date_from", "")
    if date_from:
        try:
            datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Invalid date_from '{date_from}', expected YYYY-MM-DD")

    date_to = params.get("date_to", "")
    if date_to:
        try:
            datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Invalid date_to '{date_to}', expected YYYY-MM-DD")

    if date_from and date_to:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d")
            d_to = datetime.strptime(date_to, "%Y-%m-%d")
            if d_from > d_to:
                errors.append("date_from must not be after date_to")
        except ValueError:
            pass

    queue = params.get("queue", "")
    if queue:
        if queue not in ALLOWED_QUEUE_IDS:
            errors.append(
                f"Invalid queue '{queue}', expected one of: {ALLOWED_QUEUE_IDS}"
            )

    columns = params.get("columns", "")
    if columns:
        for val in columns.split(","):
            val = val.strip()
            if val and val not in ALLOWED_COLUMN_KEYS:
                errors.append(
                    f"Invalid column '{val}', expected one of: {ALLOWED_COLUMN_KEYS}"
                )

    columns_open = params.get("columns_open", "")
    if columns_open and columns_open not in ("1", "true"):
        errors.append(f"Invalid columns_open '{columns_open}', expected '1' or 'true'")

    open_dropdowns = params.get("open_dropdowns", "")
    if open_dropdowns:
        for val in open_dropdowns.split(","):
            val = val.strip()
            if val and val not in ALLOWED_DROPDOWN_KEYS:
                errors.append(
                    f"Invalid open_dropdowns key '{val}', "
                    f"expected one of: {ALLOWED_DROPDOWN_KEYS}"
                )

    return errors


def validate_pagination_params(
    page_raw: str | None,
    page_size_raw: str | None,
    sort: str | None,
    order: str | None,
) -> list[str]:
    errors: list[str] = []

    if page_raw is not None and page_raw.strip():
        try:
            p = int(page_raw)
            if p < 1:
                errors.append(f"Invalid page '{page_raw}', page must be >= 1")
        except ValueError:
            errors.append(f"Invalid page '{page_raw}', expected an integer")

    if page_size_raw is not None and page_size_raw.strip():
        try:
            ps = int(page_size_raw)
            if ps not in ALLOWED_PAGE_SIZES:
                errors.append(
                    f"Invalid page_size '{page_size_raw}', "
                    f"expected one of: {ALLOWED_PAGE_SIZES}"
                )
        except ValueError:
            errors.append(
                f"Invalid page_size '{page_size_raw}', expected an integer"
            )

    if sort is not None and sort.strip():
        if sort not in ALLOWED_SORT_FIELDS:
            errors.append(
                f"Invalid sort '{sort}', expected one of: {ALLOWED_SORT_FIELDS}"
            )

    if order is not None and order.strip():
        if order not in ("asc", "desc"):
            errors.append(f"Invalid order '{order}', expected 'asc' or 'desc'")

    if bool(sort and sort.strip()) != bool(order and order.strip()):
        errors.append("sort and order must be provided together")

    return errors


def apply_queue_filters(
    items: list[dict[str, Any]],
    bitrix_status_by_event: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    if not params:
        return items

    case_type_raw = params.get("case_type") or params.get("classification", "")
    case_types = {v.strip() for v in case_type_raw.split(",") if v.strip()} if case_type_raw else set()
    priority_raw = params.get("priority", "")
    priorities = {v.strip() for v in priority_raw.split(",") if v.strip()} if priority_raw else set()
    bitrix_status_raw = params.get("bitrix_status", "")
    bitrix_statuses = {v.strip() for v in bitrix_status_raw.split(",") if v.strip()} if bitrix_status_raw else set()
    q = params.get("q", "").lower().strip()
    is_fallback_raw = params.get("is_fallback", "").lower().strip()
    date_from = params.get("date_from", "")
    date_to = params.get("date_to", "")

    parsed_date_from: datetime | None = None
    parsed_date_to: datetime | None = None
    if date_from:
        try:
            parsed_date_from = datetime.strptime(date_from, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            logging.getLogger(__name__).warning(
                "Invalid date_from value: %r, ignoring", date_from
            )
    if date_to:
        try:
            parsed_date_to = datetime.strptime(date_to, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc
            )
        except ValueError:
            logging.getLogger(__name__).warning(
                "Invalid date_to value: %r, ignoring", date_to
            )

    is_fallback_filter: bool | None = None
    if is_fallback_raw == "true":
        is_fallback_filter = True
    elif is_fallback_raw == "false":
        is_fallback_filter = False

    filtered: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        if is_fallback_filter is not None:
            if bool(item.get("is_fallback")) != is_fallback_filter:
                continue

        if case_types:
            item_ct = str(item.get("case_type") or item.get("bot_case_type", ""))
            if item_ct not in case_types:
                continue

        if priorities:
            item_pri = str(item.get("priority") or item.get("bot_priority", ""))
            if item_pri not in priorities:
                continue

        if bitrix_statuses:
            item_bs = str(item.get("bitrix_status", ""))
            if not item_bs and bitrix_status_by_event:
                event_id = str(item.get("event_id", ""))
                item_bs = str(bitrix_status_by_event.get(event_id, ""))
            if item_bs not in bitrix_statuses:
                continue

        search_q = q
        legacy_sender = params.get("sender", "").lower().strip()
        legacy_subject = params.get("subject", "").lower().strip()
        if search_q or legacy_sender or legacy_subject:
            sender = str(item.get("sender", "")).lower()
            subject = str(item.get("subject", "")).lower()
            if search_q and search_q not in sender and search_q not in subject:
                continue
            if legacy_sender and legacy_sender not in sender:
                continue
            if legacy_subject and legacy_subject not in subject:
                continue

        if parsed_date_from or parsed_date_to:
            ts = _event_timestamp(item)
            if ts is None:
                continue
            if parsed_date_from and ts < parsed_date_from:
                continue
            if parsed_date_to and ts > parsed_date_to:
                continue

        filtered.append(item)

    return filtered


def validate_sort_params(
    sort: str,
    order: str,
) -> tuple[str, str]:
    if sort not in ALLOWED_SORT_FIELDS:
        sort = "received_at"
    if order not in ("asc", "desc"):
        order = "desc"
    return sort, order


def sort_queue_items(
    items: list[dict[str, Any]],
    sort: str = "received_at",
    order: str = "desc",
) -> list[dict[str, Any]]:
    sort, order = validate_sort_params(sort, order)
    fallback_field = {
        "received_at": "date",
        "date": "received_at",
        "event_date": "received_at",
    }.get(sort, sort)
    valid: list[tuple[Any, dict[str, Any]]] = []
    missing: list[dict[str, Any]] = []

    for item in items:
        raw = item.get(sort)
        if raw is None or raw == "":
            raw = item.get(fallback_field)

        if sort in ("received_at", "date", "event_date"):
            timestamp = _parse_iso(str(raw) if raw is not None else None)
            if timestamp is None:
                missing.append(item)
            else:
                valid.append((timestamp, item))
            continue

        normalized = str(raw).strip().casefold() if raw is not None else ""
        if not normalized:
            missing.append(item)
        else:
            valid.append((normalized, item))

    valid.sort(key=lambda entry: entry[0], reverse=order == "desc")
    return [item for _, item in valid] + missing


def paginate_items(
    items: list[dict[str, Any]],
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if page_size not in ALLOWED_PAGE_SIZES:
        page_size = DEFAULT_PAGE_SIZE
    if page < 1:
        page = 1

    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    if page > total_pages:
        page = total_pages

    start = (page - 1) * page_size
    end = start + page_size
    paginated = items[start:end]

    pagination_info = {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "start": start + 1 if total > 0 else 0,
        "end": min(end, total),
    }
    return paginated, pagination_info


def parse_period(period: str) -> dict[str, Any]:
    period = period.strip().lower()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1) - timedelta(microseconds=1)

    if period == "today":
        return {
            "period": "today",
            "period_start_utc": today_start.isoformat(),
            "period_end_utc": today_end.isoformat(),
            "time_basis": "event_timestamp",
        }
    if period == "yesterday":
        yesterday_start = today_start - timedelta(days=1)
        yesterday_end = today_start - timedelta(microseconds=1)
        return {
            "period": "yesterday",
            "period_start_utc": yesterday_start.isoformat(),
            "period_end_utc": yesterday_end.isoformat(),
            "time_basis": "event_timestamp",
        }
    if period == "7d":
        return {
            "period": "7d",
            "period_start_utc": (today_start - timedelta(days=7)).isoformat(),
            "period_end_utc": today_end.isoformat(),
            "time_basis": "event_timestamp",
        }
    if period == "30d":
        return {
            "period": "30d",
            "period_start_utc": (today_start - timedelta(days=30)).isoformat(),
            "period_end_utc": today_end.isoformat(),
            "time_basis": "event_timestamp",
        }
    if period == "90d":
        return {
            "period": "90d",
            "period_start_utc": (today_start - timedelta(days=90)).isoformat(),
            "period_end_utc": today_end.isoformat(),
            "time_basis": "event_timestamp",
        }
    if period == "365d":
        return {
            "period": "365d",
            "period_start_utc": (today_start - timedelta(days=365)).isoformat(),
            "period_end_utc": today_end.isoformat(),
            "time_basis": "event_timestamp",
        }
    if period == "all":
        return {
            "period": "all",
            "period_start_utc": None,
            "period_end_utc": None,
            "time_basis": "event_timestamp",
        }
    raise ValueError(f"Unsupported period: '{period}'")


def validate_period(period: str) -> None:
    if period not in ALLOWED_PERIODS:
        raise ValueError(
            f"Invalid period '{period}', expected one of: {ALLOWED_PERIODS}"
        )


def build_rop_dashboard(
    storage_dir: Path,
    period: str,
    logger: logging.Logger,
    run_id: str | None = None,
) -> dict[str, Any]:
    validate_period(period)
    period_info = parse_period(period)

    runs_dir = (storage_dir / "runs").resolve()
    if not runs_dir.is_dir():
        return _empty_dashboard(period, "no_runs_directory")

    if run_id is None:
        run_ids = _list_run_ids(runs_dir)
        if not run_ids:
            return _empty_dashboard(period, "no_runs_found")
        run_id = run_ids[0]

    run_dir = (runs_dir / run_id).resolve()
    try:
        run_dir.relative_to(runs_dir)
    except ValueError:
        return _empty_dashboard(period, "invalid_run_id")

    if not run_dir.is_dir():
        return _empty_dashboard(period, "run_not_found")

    normalized_events = _read_json_list(run_dir / "normalized_events.json")
    classified_events = _read_json_list(run_dir / "classified_events.json")
    source_diag = _read_json_dict(run_dir / "source_diagnostics.json")
    intake = _read_json_dict(run_dir / "intake_metadata.json")
    current_state = _read_json_dict(run_dir / "rop_current_state.json")
    bitrix_reconciliation = _read_json_dict(run_dir / "bitrix_reconciliation.json")
    attachment_extraction = _read_json_dict(run_dir / "attachment_extraction.json")
    operator_summary = _read_json_dict(run_dir / "operator_summary.json")
    ai_assist_results = _read_json_dict(run_dir / "rop_ai_assist_results.json")
    ai_adjudicator_results = _read_json_dict(run_dir / "rop_ai_adjudicator_results.json")

    warnings: list[dict[str, Any]] = []
    client_id = _resolve_client_id(source_diag, intake, current_state)
    run_generated_at = _resolve_generated_at(current_state, run_dir, logger)
    fallback_ts = _parse_iso(run_generated_at)

    classified_list = (
        list(classified_events) if isinstance(classified_events, list) else []
    )
    normalized_list = (
        list(normalized_events) if isinstance(normalized_events, list) else []
    )

    if period_info["period"] != "all" and period_info.get("period_start_utc"):
        period_start = _parse_iso(period_info["period_start_utc"])
        period_end = _parse_iso(period_info["period_end_utc"])
        if period_start and period_end:
            classified_list, classified_filter_stats = _filter_by_period(
                classified_list,
                period_start,
                period_end,
                fallback_ts=fallback_ts,
            )
            normalized_list, normalized_filter_stats = _filter_by_period(
                normalized_list,
                period_start,
                period_end,
                fallback_ts=fallback_ts,
            )
            if (
                classified_filter_stats["fallback"] > 0
                or normalized_filter_stats["fallback"] > 0
            ):
                warnings.append(
                    {
                        "code": "time_basis_fallback",
                        "message": "Some events had no timestamp and were filtered using run_generated_at.",
                    }
                )
            period_info["time_basis"] = _resolve_time_basis(classified_filter_stats)

    bitrix_period_state = _build_bitrix_period_state(
        classified_list=classified_list,
        bitrix_reconciliation=bitrix_reconciliation,
        run_id=run_id,
    )

    business_kpi = _build_business_kpi(
        classified_list=classified_list,
        normalized_list=normalized_list,
        bitrix_state=bitrix_period_state,
        source_diag=source_diag,
        attachment_extraction=attachment_extraction,
    )

    series = _build_series(
        classified_list=classified_list,
        bitrix_state=bitrix_period_state,
        fallback_ts=fallback_ts,
    )

    queues = _build_queues(
        classified_list=classified_list,
        bitrix_state=bitrix_period_state,
        run_id=run_id,
    )

    rop_recommendations = _build_recommendations(
        business_kpi=business_kpi,
        classified_list=classified_list,
        current_state=current_state,
    )

    evidence_links = _build_evidence_links(storage_dir, run_id)

    if source_diag is None:
        warnings.append(
            {
                "code": "missing_artifact",
                "artifact": "source_diagnostics.json",
                "message": "Source diagnostics missing.",
            }
        )
    if current_state is None:
        warnings.append(
            {
                "code": "missing_artifact",
                "artifact": "rop_current_state.json",
                "message": "Current state missing; Bitrix evidence may be incomplete.",
            }
        )

    ai_assist_summary: dict[str, Any] = {}

    if isinstance(ai_adjudicator_results, dict):
        adj_counters = ai_adjudicator_results.get("counters", {})
        if isinstance(adj_counters, dict):
            ai_assist_summary = {
                "eligible": adj_counters.get("adjudicator_eligible_count", 0),
                "requested": adj_counters.get("adjudicator_eligible_count", 0),
                "ok": adj_counters.get("adjudicator_used_count", 0),
                "degraded": adj_counters.get("adjudicator_degraded_count", 0),
            }
    if not ai_assist_summary and isinstance(ai_assist_results, dict):
        counters = ai_assist_results.get("counters", {})
        if isinstance(counters, dict):
            ai_assist_summary = {
                "eligible": counters.get("ai_assist_enabled", 0),
                "requested": counters.get("ai_assist_requested_count", 0),
                "ok": counters.get("ai_assist_used_count", 0),
                "invalid": counters.get("ai_assist_invalid_count", 0),
                "degraded": counters.get("ai_assist_degraded_count", 0),
            }

    dashboard: dict[str, Any] = {
        "run_id": run_id,
        "status": "ok",
        "read_only": True,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "client_id": client_id,
        "period": period,
        "period_start_utc": period_info.get("period_start_utc"),
        "period_end_utc": period_info.get("period_end_utc"),
        "time_basis": period_info.get("time_basis", "run_generated_at"),
        "business_kpi": business_kpi,
        "series": series,
        "queues": queues,
        "rop_recommendations": rop_recommendations,
        "evidence_links": evidence_links,
        "warnings": warnings,
        "ai_assist_summary": ai_assist_summary,
    }

    return dashboard


def write_rop_dashboard(
    storage_dir: Path,
    dashboard: dict[str, Any],
    logger: logging.Logger,
) -> Path:
    interfaces_dir = (storage_dir / "interfaces").resolve()
    interfaces_dir.mkdir(parents=True, exist_ok=True)

    artifact_path = interfaces_dir / DASHBOARD_ARTIFACT
    artifact_path.write_text(
        json.dumps(dashboard, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(
        "ROP dashboard artifact written: path=%s period=%s run_id=%s",
        str(artifact_path.relative_to(storage_dir)),
        dashboard.get("period", "?"),
        dashboard.get("run_id", "?"),
    )
    return artifact_path


def _empty_dashboard(period: str, reason: str) -> dict[str, Any]:
    return {
        "status": "empty",
        "read_only": True,
        "period": period,
        "reason": reason,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "business_kpi": {},
        "series": {},
        "queues": {},
        "rop_recommendations": [],
        "evidence_links": [],
        "warnings": [{"code": reason, "message": f"No dashboard data: {reason}"}],
    }


def _list_run_ids(runs_dir: Path) -> list[str]:
    return sorted(
        (d.name for d in runs_dir.iterdir() if d.is_dir()),
        key=lambda n: (runs_dir / n).stat().st_mtime,
        reverse=True,
    )


def _read_json_list(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except json.JSONDecodeError, OSError:
        pass
    return None


def _read_json_dict(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError, OSError:
        pass
    return None


def _resolve_client_id(
    source_diag: dict | None,
    intake: dict | None,
    current_state: dict | None,
) -> str:
    if current_state and isinstance(current_state, dict):
        cid = current_state.get("client_id")
        if isinstance(cid, str) and cid:
            return cid

    for data in (source_diag, intake):
        if isinstance(data, dict):
            sources = data.get("sources")
            if isinstance(sources, list):
                for s in sources:
                    if isinstance(s, dict) and s.get("client_id"):
                        return str(s["client_id"])
    return "unknown"


def _resolve_generated_at(
    current_state: dict | None,
    run_dir: Path,
    logger: logging.Logger,
) -> str | None:
    if current_state and isinstance(current_state, dict):
        ga = current_state.get("generated_at_utc")
        if isinstance(ga, str):
            return ga
    try:
        mtime = run_dir.stat().st_mtime
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        logger.debug("Cannot read run_dir mtime: %s", run_dir)
        return None


def _parse_iso(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _filter_by_period(
    events: list[dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    fallback_ts: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    filtered: list[dict[str, Any]] = []
    stats = {"event_timestamp": 0, "fallback": 0, "unknown": 0}
    for evt in events:
        ts = _event_timestamp(evt)
        basis = "event_timestamp"
        if ts is None:
            if fallback_ts is None:
                stats["unknown"] += 1
                continue
            ts = fallback_ts
            basis = "fallback"
        if period_start <= ts <= period_end:
            filtered.append(evt)
            stats[basis] += 1
    return filtered, stats


def _resolve_time_basis(stats: dict[str, int]) -> str:
    event_count = stats.get("event_timestamp", 0)
    fallback_count = stats.get("fallback", 0)

    if event_count and fallback_count:
        return "mixed"
    if fallback_count:
        return "run_generated_at"
    return "event_timestamp"


def _event_timestamp(evt: dict[str, Any]) -> datetime | None:
    for key in ("event_date", "received_at", "timestamp", "created_at", "date"):
        raw = evt.get(key)
        if isinstance(raw, str) and raw.strip():
            parsed = _parse_iso(raw)
            if parsed is not None:
                return parsed
    return None


def _build_business_kpi(
    classified_list: list[dict[str, Any]],
    normalized_list: list[dict[str, Any]],
    bitrix_state: dict[str, Any],
    source_diag: dict | None,
    attachment_extraction: dict | None,
) -> dict[str, Any]:
    normalized_count = len(normalized_list)
    classified_count = len(classified_list)

    new_leads = 0
    existing_clients = 0
    follow_ups = 0
    high_priority = 0
    needs_review = 0

    for evt in classified_list:
        ct = evt.get("case_type", "")
        if ct == "new_lead":
            new_leads += 1
        elif ct in ("existing_deal", "existing_lead", "existing_client"):
            existing_clients += 1
        elif ct in ("follow_up", "reminder"):
            follow_ups += 1
        if evt.get("priority") == "high":
            high_priority += 1
        if evt.get("is_fallback") or evt.get("priority") == "high":
            needs_review += 1

    bitrix_kpi = bitrix_state.get("kpi", {})
    if not isinstance(bitrix_kpi, dict):
        bitrix_kpi = {}

    source_degraded = 0
    if isinstance(source_diag, dict):
        agg = source_diag.get("aggregate", {})
        if isinstance(agg, dict):
            source_degraded = _int(agg.get("degraded_source_count", 0))

    attachment_refused = _count_period_attachment_refused(
        attachment_extraction=attachment_extraction,
        classified_list=classified_list,
        normalized_list=normalized_list,
    )

    return {
        "processed_events": classified_count,
        "processed_emails": classified_count,
        "new_leads": new_leads,
        "existing_clients": existing_clients,
        "follow_ups": follow_ups,
        "high_priority": high_priority,
        "needs_review": needs_review,
        "lost_in_bitrix": _int(bitrix_kpi.get("lost_in_bitrix", 0)),
        "weak_match": _int(bitrix_kpi.get("weak_match", 0)),
        "ambiguous_or_duplicate": _int(bitrix_kpi.get("ambiguous_or_duplicate", 0)),
        "unreconciled": _int(bitrix_kpi.get("unreconciled", 0)),
        "matched_in_bitrix": _int(bitrix_kpi.get("matched_in_bitrix", 0)),
        "bitrix_errors": _int(bitrix_kpi.get("bitrix_errors", 0)),
        "source_degraded": source_degraded,
        "attachment_refused": attachment_refused,
        "normalized_count": normalized_count,
        "classified_count": classified_count,
    }


def _count_period_attachment_refused(
    attachment_extraction: dict | None,
    classified_list: list[dict[str, Any]],
    normalized_list: list[dict[str, Any]],
) -> int:
    if not isinstance(attachment_extraction, dict):
        return 0

    event_ids: set[str] = set()
    for evt in [*classified_list, *normalized_list]:
        if not isinstance(evt, dict):
            continue
        event_id = evt.get("event_id")
        if isinstance(event_id, str) and event_id:
            event_ids.add(event_id)

    items = attachment_extraction.get("items")
    if isinstance(items, list):
        count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            event_id = item.get("event_id")
            if not isinstance(event_id, str) or event_id not in event_ids:
                continue
            status = str(item.get("extraction_status") or "").lower()
            if (
                item.get("is_refused") is True
                or item.get("is_blocked") is True
                or status in ("refused", "blocked")
            ):
                count += 1
        return count

    agg = attachment_extraction.get("aggregate", {})
    if isinstance(agg, dict):
        return _int(agg.get("refused_count", 0)) + _int(agg.get("blocked_count", 0))
    return 0


def _build_series(
    classified_list: list[dict[str, Any]],
    bitrix_state: dict[str, Any],
    fallback_ts: datetime | None = None,
) -> dict[str, Any]:
    series: dict[str, Any] = {}

    day_counts: dict[str, int] = {}
    hp_day_counts: dict[str, int] = {}
    for evt in classified_list:
        ts = _event_timestamp(evt) or fallback_ts
        if ts is not None:
            day_key = ts.strftime("%Y-%m-%d")
            day_counts[day_key] = day_counts.get(day_key, 0) + 1
            if evt.get("priority") == "high":
                hp_day_counts[day_key] = hp_day_counts.get(day_key, 0) + 1

    if day_counts:
        slabels = sorted(day_counts.keys())
        series["processed_by_day"] = {
            "labels": slabels,
            "series": [
                {
                    "name": "Processed",
                    "data": [day_counts.get(d, 0) for d in slabels],
                },
                {
                    "name": "High priority",
                    "data": [hp_day_counts.get(d, 0) for d in slabels],
                },
            ],
        }

    ct_dist: dict[str, int] = {}
    for evt in classified_list:
        ct = evt.get("case_type", "other")
        ct_dist[ct] = ct_dist.get(ct, 0) + 1
    if ct_dist:
        clabels = sorted(ct_dist.keys())
        series["classification_distribution"] = {
            "labels": clabels,
            "series": [ct_dist.get(l, 0) for l in clabels],
        }

    bitrix_kpi = bitrix_state.get("kpi", {})
    if not isinstance(bitrix_kpi, dict):
        bitrix_kpi = {}
    b_matched = _int(bitrix_kpi.get("matched_in_bitrix", 0))
    b_lost = _int(bitrix_kpi.get("lost_in_bitrix", 0))
    b_weak = _int(bitrix_kpi.get("weak_match", 0))
    b_ambiguous = _int(bitrix_kpi.get("ambiguous_or_duplicate", 0))
    b_unreconciled = _int(bitrix_kpi.get("unreconciled", 0))
    if classified_list:
        series["bitrix_distribution"] = {
            "labels": ["matched", "lost", "weak", "ambiguous", "unreconciled"],
            "series": [b_matched, b_lost, b_weak, b_ambiguous, b_unreconciled],
        }

    source_dist: dict[str, int] = {}
    for evt in classified_list:
        sid = evt.get("source_id", "unknown")
        source_dist[sid] = source_dist.get(sid, 0) + 1
    if source_dist:
        slabels = sorted(source_dist.keys())
        series["source_contribution"] = {
            "labels": slabels,
            "series": [source_dist.get(l, 0) for l in slabels],
        }

    return series


def _build_queues(
    classified_list: list[dict[str, Any]],
    bitrix_state: dict[str, Any],
    run_id: str,
) -> dict[str, list[dict[str, Any]]]:
    high_priority: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []

    bitrix_queues = bitrix_state.get("queues", {})
    if not isinstance(bitrix_queues, dict):
        bitrix_queues = {}

    bitrix_status_by_event: dict[str, str] = {}
    for queue_items in bitrix_queues.values():
        if not isinstance(queue_items, list):
            continue
        for item in queue_items:
            if not isinstance(item, dict):
                continue
            event_id = item.get("event_id")
            bitrix_status = item.get("bitrix_status")
            if (
                isinstance(event_id, str)
                and event_id
                and isinstance(bitrix_status, str)
                and bitrix_status
            ):
                bitrix_status_by_event[event_id] = bitrix_status

    seen_review: set[str] = set()

    for evt in classified_list:
        if not isinstance(evt, dict):
            continue

        raw_event_id = evt.get("event_id")
        event_id = raw_event_id if isinstance(raw_event_id, str) else ""
        bitrix_status = bitrix_status_by_event.get(event_id, "")
        entry = _operator_queue_entry(
            evt,
            bitrix_status,
            run_id,
            "manual_review",
        )

        if evt.get("priority") == "high":
            high_priority.append(entry)

        if evt.get("is_fallback") or evt.get("priority") == "high":
            if event_id not in seen_review:
                needs_review.append(entry)
                seen_review.add(event_id)

    return {
        "high_priority": high_priority,
        "needs_review": needs_review,
        "matched": list(bitrix_queues.get("matched", [])),
        "lost_in_bitrix": list(bitrix_queues.get("lost_in_bitrix", [])),
        "weak_match": list(bitrix_queues.get("weak_match", [])),
        "ambiguous": list(bitrix_queues.get("ambiguous", [])),
        "degraded": list(bitrix_queues.get("degraded", [])),
        "unreconciled": list(bitrix_queues.get("unreconciled", [])),
    }


def _build_bitrix_period_state(
    classified_list: list[dict[str, Any]],
    bitrix_reconciliation: dict | None,
    run_id: str,
) -> dict[str, Any]:
    kpi = {
        "matched_in_bitrix": 0,
        "lost_in_bitrix": 0,
        "weak_match": 0,
        "ambiguous_or_duplicate": 0,
        "bitrix_errors": 0,
        "connector_degraded": 0,
        "unreconciled": 0,
    }
    queues: dict[str, list[dict[str, Any]]] = {
        "matched": [],
        "lost_in_bitrix": [],
        "weak_match": [],
        "ambiguous": [],
        "degraded": [],
        "unreconciled": [],
    }

    reconciliation_lookup: dict[str, dict[str, Any]] = {}
    if isinstance(bitrix_reconciliation, dict):
        items = bitrix_reconciliation.get("items", [])
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                event_id = item.get("event_id")
                if isinstance(event_id, str) and event_id:
                    reconciliation_lookup[event_id] = item

    for evt in classified_list:
        if not isinstance(evt, dict):
            continue
        event_id = str(evt.get("event_id", ""))
        recon_item = reconciliation_lookup.get(event_id)
        status = ""
        if isinstance(recon_item, dict):
            status = str(
                recon_item.get("bitrix_match_status")
                or recon_item.get("match_status")
                or recon_item.get("bitrix_status")
                or ""
            )

        if status.startswith("matched_"):
            kpi["matched_in_bitrix"] += 1
            queues["matched"].append(
                _bitrix_queue_entry(evt, status, run_id, "matched")
            )
        elif status == "not_found":
            kpi["lost_in_bitrix"] += 1
            queues["lost_in_bitrix"].append(
                _bitrix_queue_entry(evt, status, run_id, "lost_in_bitrix")
            )
        elif status == "weak_match":
            kpi["weak_match"] += 1
            kpi["ambiguous_or_duplicate"] += 1
            queues["weak_match"].append(
                _bitrix_queue_entry(evt, status, run_id, "ambiguous")
            )
        elif status in ("ambiguous", "duplicate_candidate"):
            kpi["ambiguous_or_duplicate"] += 1
            queues["ambiguous"].append(
                _bitrix_queue_entry(evt, status, run_id, "ambiguous")
            )
        elif status in ("connector_degraded", "error"):
            kpi["bitrix_errors"] += 1
            kpi["connector_degraded"] += 1
            queues["degraded"].append(
                _bitrix_queue_entry(evt, status, run_id, "degraded")
            )
        elif status == "skipped":
            continue
        else:
            kpi["unreconciled"] += 1
            queues["unreconciled"].append(
                _bitrix_queue_entry(evt, status, run_id, "unreconciled")
            )

    return {"kpi": kpi, "queues": queues}


def _bitrix_queue_entry(
    evt: dict[str, Any],
    status: str,
    run_id: str,
    queue_kind: str,
) -> dict[str, Any]:
    return _operator_queue_entry(evt, status, run_id, queue_kind)


def _operator_queue_entry(
    evt: dict[str, Any],
    status: str,
    run_id: str,
    queue_kind: str,
) -> dict[str, Any]:
    case_type = evt.get("case_type", "")
    priority = evt.get("priority", "")
    return {
        "event_id": evt.get("event_id", ""),
        "source_id": evt.get("source_id", ""),
        "source_display_name": evt.get("source_display_name")
        or evt.get("source_id", ""),
        "sender": evt.get("sender", ""),
        "subject": evt.get("subject", ""),
        "case_type": case_type,
        "priority": priority,
        "bot_case_type": case_type,
        "bot_priority": priority,
        "bitrix_status": status or "unreconciled",
        "reason": evt.get("reasoning") or evt.get("reason_code", ""),
        "recommended_next_step": _recommended_next_step(priority, status, queue_kind),
        "date": evt.get("received_at") or evt.get("date") or evt.get("event_date", ""),
        "run_id": run_id,
        "evidence_href": f"/runs/{run_id}/artifacts/classified_events_json",
        "is_fallback": bool(evt.get("is_fallback")),
    }


def _recommended_next_step(priority: object, status: str, queue_kind: str) -> str:
    if priority == "high":
        return "manual_review"
    if queue_kind == "lost_in_bitrix" or status == "not_found":
        return "check_crm_gap"
    if queue_kind == "ambiguous" or status in ("ambiguous", "duplicate_candidate"):
        return "resolve_duplicate_or_ambiguous_match"
    if queue_kind == "degraded" or status in ("connector_degraded", "error"):
        return "check_bitrix_connector"
    if queue_kind == "unreconciled" or status in ("skipped", ""):
        return "run_read_only_reconciliation"
    return ""


def _build_recommendations(
    business_kpi: dict[str, Any],
    classified_list: list[dict[str, Any]],
    current_state: dict | None,
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []

    high_priority = business_kpi.get("high_priority", 0)
    if high_priority > 0:
        recs.append(
            {
                "severity": "warning",
                "title": "Review high-priority cases",
                "detail": f"{high_priority} high-priority classified events need immediate operator review.",
                "reason_code": "high_priority",
                "count": high_priority,
                "read_only": True,
                "action_type": "manual_review",
                "evidence_href": "/rop?tab=queue",
            }
        )

    lost_in_bitrix = business_kpi.get("lost_in_bitrix", 0)
    if lost_in_bitrix > 0:
        recs.append(
            {
                "severity": "warning",
                "title": "Review lost Bitrix leads",
                "detail": (
                    f"{lost_in_bitrix} classified events were not found in Bitrix. "
                    "Check CRM gap or manual lead review."
                ),
                "reason_code": "lost_in_bitrix",
                "count": lost_in_bitrix,
                "read_only": True,
                "action_type": "manual_review",
                "evidence_href": "/rop?tab=bitrix",
            }
        )

    ambiguous_or_duplicate = business_kpi.get("ambiguous_or_duplicate", 0)
    if ambiguous_or_duplicate > 0:
        recs.append(
            {
                "severity": "warning",
                "title": "Resolve ambiguous/duplicate Bitrix matches",
                "detail": (
                    f"{ambiguous_or_duplicate} events have ambiguous or duplicate Bitrix matches. "
                    "Manual resolution recommended."
                ),
                "reason_code": "ambiguous_or_duplicate",
                "count": ambiguous_or_duplicate,
                "read_only": True,
                "action_type": "manual_review",
                "evidence_href": "/rop?tab=bitrix",
            }
        )

    unreconciled = business_kpi.get("unreconciled", 0)
    if unreconciled > 0:
        recs.append(
            {
                "severity": "info",
                "title": "Run Bitrix reconciliation",
                "detail": (
                    f"{unreconciled} events have not been reconciled with Bitrix. "
                    "Run read-only reconcile-bitrix to update evidence."
                ),
                "reason_code": "unreconciled",
                "count": unreconciled,
                "read_only": True,
                "action_type": "run_reconciliation",
                "evidence_href": "/rop?tab=evidence",
            }
        )

    source_degraded = business_kpi.get("source_degraded", 0)
    if source_degraded > 0:
        recs.append(
            {
                "severity": "warning",
                "title": "Check degraded sources",
                "detail": (
                    f"{source_degraded} source(s) reported degradation. "
                    "Investigate source/mailbox ingestion."
                ),
                "reason_code": "source_degraded",
                "count": source_degraded,
                "read_only": True,
                "action_type": "check_source",
                "evidence_href": "/rop?tab=sources",
            }
        )

    attachment_refused = business_kpi.get("attachment_refused", 0)
    if attachment_refused > 0:
        recs.append(
            {
                "severity": "info",
                "title": "Review refused attachment metadata",
                "detail": (
                    f"{attachment_refused} attachment(s) were refused during extraction. "
                    "Manual review of attachment metadata recommended."
                ),
                "reason_code": "attachment_refused",
                "count": attachment_refused,
                "read_only": True,
                "action_type": "manual_review",
                "evidence_href": "/rop?tab=attachments",
            }
        )

    return recs


def _build_evidence_links(
    storage_dir: Path,
    run_id: str,
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    evidence_ids = (
        "operator_summary_json",
        "source_diagnostics_json",
        "intake_metadata_json",
        "attachment_extraction_json",
        "normalized_events_json",
        "classified_events_json",
        "rop_review_table_tsv",
        "rop_current_state_json",
        "bitrix_reconciliation_json",
        "rop_action_drafts_json",
        "module_result_json",
        "rop_summary_result_json",
    )
    for aid in evidence_ids:
        links.append(
            {
                "artifact_id": aid,
                "href": f"/runs/{run_id}/artifacts/{aid}",
            }
        )
    return links


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
