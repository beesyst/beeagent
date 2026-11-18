import hashlib
import json
import re

from beeagent_module.integrations.beescan.capture_worker import RESPONSE_FAILURES
from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot

_STATUSES = {
    "QUEUED",
    "RUNNING",
    "REFUSED",
    "PARTIAL",
    "ERROR",
    "TIMEOUT",
    "INCONCLUSIVE",
    "MATCH",
    "CANDIDATE",
    "NO_MATCH",
    "UNSUPPORTED",
    "DEFERRED",
    "PENDING",
}
_REASONS = RESPONSE_FAILURES | {
    "dast_deadline",
    "ok",
    "execution_pending",
    "discovery_incomplete",
    "execution_incomplete",
    "investigation_deadline",
    "cleanup_unverified",
    "authorization_refused",
    "target_excluded",
    "internal_destination_denied",
    "dns_changed",
    "dns_unverified",
    "request_budget_exhausted",
    "step_budget_exhausted",
    "time_budget_exhausted",
    "verification_time_insufficient",
    "no_eligible_action",
    "ambiguous_evidence",
    "answer_supported",
    "source_disclosure_supported",
    "cancelled",
    "web_execution_incomplete",
    "capability_disabled",
    "request_count_unverified",
    "required_evidence_or_profile_unavailable",
    "authenticated_check_outcomes",
    "capture_failed",
    "active_dast_expired",
    "approval_changed",
    "authenticated_surface",
    "capability_unavailable",
    "artifact_incomplete",
    "case_checkpoint_unverified",
    "unsupported_investigation_task",
    "invalid_requested_field",
    "reviewed_it11_revision_unavailable",
    "authenticated_case_reused",
    "verification_execution_incomplete",
    "verification_controls_ambiguous",
    "no_eligible_source",
    "no_approved_verification_profile",
    "missing_independent_restriction_expectation",
    "authorization_expectation_required",
    "authenticated_identity_missing",
    "eligible_owned_resource_missing",
}
_PHASES = {
    "investigation",
    "active_dast",
    "execution",
    "case_authentication",
    "receipt_publication",
    "dast_publication",
    "connection_establishment",
    "worker",
}
_CATEGORIES = {
    "deadline",
    "authorization",
    "storage",
    "validation",
    "runtime",
    "unexpected",
}


def failure_reason(error):
    value = str(error)
    return value if value in _REASONS else "execution_incomplete"


def _identifier(value):
    return type(value) is str and re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value
    )


def _count(value):
    return value if type(value) is int and 0 <= value <= 256 else None


def _failure(snapshot, run_id, status):
    failure = None
    try:
        log = snapshot.read(run_id, "web_failure.log").decode("utf-8")[-32768:]
    except OSError, ValueError, UnicodeError:
        log = ""
    headers = re.findall(
        r"^\S+ run_id="
        + re.escape(run_id)
        + r" category=(\w+) phase=(\w+)(?: reason=(\w+))?$",
        log,
        re.MULTILINE,
    )
    if headers:
        category, phase, reason = headers[-1]
        if category in _CATEGORIES and phase in _PHASES:
            failure = {
                "category": category,
                "phase": phase,
                "reason": reason
                if reason in _REASONS
                else status.get("reason")
                if status.get("reason") in _REASONS
                else "execution_incomplete",
            }
            if (
                reason in {"", "capture_failed"}
                and status.get("request_count") == 0
                and "detection_runner.py:" in log
                and " in run_detection_provider" in log
            ):
                failure.update(
                    phase="capture_pre_request", reason="capture_before_request_failed"
                )
    return failure


def investigation_timeline(
    storage, owned, status, steps, state, authenticated, child_owner=None
):
    from beescan.capabilities.catalog import ACCESS_CONTROL_GET, TRAVERSAL_NONRECURSIVE

    run_id = owned["run_id"]
    snapshot = AssessmentSnapshot(storage)
    operational = AssessmentSnapshot(storage)
    events = []

    def add(identity, kind, **values):
        event_id = hashlib.sha256((run_id + ":" + identity).encode()).hexdigest()[:48]
        events.append({"id": "progress-" + event_id, "kind": kind, **values})

    execution = status.get("execution_context", {})
    if type(execution) is not dict:
        execution = {}
    add(
        "authority",
        "authority",
        target=owned["target"],
        mode=owned["mode"],
        requests=_count(execution.get("effective_request_budget")),
        steps=_count(execution.get("step_budget")),
    )
    for index, step in enumerate(steps):
        if type(step) is not dict:
            continue
        reference = step.get("request_id")
        add(
            "capture:" + str(index),
            "capture",
            phase=step["step"],
            status=step["status"],
            requests=_count(step.get("request_count")),
            reference=reference if _identifier(reference) else None,
            provider="host-web-capture",
            profile=None,
            reason="authorized_discovery",
        )
    if state is None:
        try:
            state = operational.json(owned["case_id"], "case.json").get("state")
        except OSError, ValueError:
            state = None
    if type(state) is dict and state.get("schema_version") == 7:
        context = state.get("context", {})
        spec = context.get("spec", {}) if type(context) is dict else {}
        if type(spec) is dict:
            events[0]["seconds"] = _count(spec.get("time_budget_seconds"))
        discovery = state.get("discovery", {})
        segments = discovery.get("segments", []) if type(discovery) is dict else []
        for key, profile in (
            ("assessments", TRAVERSAL_NONRECURSIVE),
            ("access", ACCESS_CONTROL_GET),
        ):
            records = state.get(key, [])
            if type(records) is not list or len(records) > 64:
                continue
            for record in records:
                if type(record) is not dict or not _identifier(record.get("action_id")):
                    continue
                action = record.get("action", {})
                if key == "assessments" and (
                    type(action) is not dict
                    or action.get("provider_id") != profile.tool_id
                    or action.get("profile") != profile.profile_id
                ):
                    continue
                source = (
                    action.get("entry", {})
                    if key == "assessments"
                    else record.get("source", {})
                )
                source_run = (
                    source.get("source_run_id") if type(source) is dict else None
                )
                if run_id not in segments or (
                    source_run is not None and not _identifier(source_run)
                ):
                    continue
                child_status = (
                    "PENDING"
                    if record.get("pending") is True
                    else record.get("status", status["status"])
                )
                if child_status not in _STATUSES:
                    continue
                add(
                    "verification:" + record["action_id"],
                    "verification",
                    phase="verification",
                    status=child_status,
                    requests=None
                    if record.get("pending")
                    else _count(record.get("request_count")),
                    provider=profile.tool_id,
                    profile=profile.profile_id,
                    qualified=profile.qualified,
                    reason="evidence_qualified_profile",
                    reference=source_run,
                )
                child_id = record.get("run_id")
                if (
                    child_owner is not None
                    and isinstance(child_id, str)
                    and _identifier(child_id)
                ):
                    binding = child_owner(child_id)
                    if any(
                        binding.get(key) != owned.get(key)
                        for key in ("case_id", "target", "principal_id")
                    ):
                        raise PermissionError("web_progress_child_changed")
                    if record.get("pending") is True:
                        try:
                            child_status = operational.json(
                                child_id, "investigation_status.json"
                            )
                        except OSError, ValueError:
                            child_status = {}
                        if child_status.get("status") in _STATUSES:
                            events[-1]["status"] = child_status["status"]
                            events[-1]["requests"] = _count(
                                child_status.get("request_count")
                            )
                            events[-1]["exact"] = (
                                child_status.get("request_count_exact") is True
                            )
                    child_failure = _failure(
                        operational, child_id, {"reason": "execution_incomplete"}
                    )
                    if child_failure:
                        add(
                            "failure:" + child_id,
                            "failure",
                            reference=child_id,
                            **child_failure,
                        )
    coverage = status.get("coverage_summary", {})
    for family in ("information_disclosure", "path_traversal", "access_control"):
        item = coverage.get(family) if type(coverage) is dict else None
        add(
            "coverage:" + family,
            "coverage",
            family=family,
            status=item["status"]
            if type(item) is dict and item.get("status") in _STATUSES
            else "NOT_YET_ESTABLISHED",
            authenticated=authenticated,
        )
    failure = _failure(snapshot, run_id, status)
    if failure:
        add("failure", "failure", **failure)
    reason = status.get("stop_reason") or status.get("reason")
    add(
        "status",
        "status",
        status=status["status"],
        reason=reason if reason in _REASONS else "execution_incomplete",
        requests=_count(status.get("request_count")),
        exact=status.get("request_count_exact") is True,
        terminal=status["status"] in {"ERROR", "REFUSED", "TIMEOUT"}
        or status["status"] not in {"RUNNING", "QUEUED"}
        and not (type(state) is dict and state.get("pending") is True),
        authenticated=authenticated,
    )
    return events


def authenticated_observations(state, snapshot):
    if state is None or state.get("schema_version") != 7:
        return []
    from beescan.domain.access_control import SLOTS, evaluate_access

    from beeagent_module.integrations.beescan.access_control import restore
    from beeagent_module.integrations.beescan.dast_runner import verification_coverage

    observations = []

    def source(raw):
        path = raw.get("endpoint_path", raw.get("relative_url", "")).split("?", 1)[0]
        return {
            "endpoint": path
            if re.fullmatch(r"/(?!/)[A-Za-z0-9_./~-]{0,191}", path)
            else "[protected path]",
            "parameters": [
                value
                for value in raw.get("parameter_names", [])[:8]
                if _identifier(value)
                and not re.search(
                    r"secret|password|token|credential|key|session|auth|csrf",
                    value,
                    re.IGNORECASE,
                )
            ],
            "references": [
                value
                for value in raw.get("evidence_refs", [])[:4]
                if _identifier(value)
            ],
        }

    for record in state["assessments"][:8]:
        if record["pending"] or record.get("deferred"):
            continue
        run_id = record["run_id"]
        handoff = snapshot.json(run_id, "dast_handoff.json")
        evidence = snapshot.json(run_id, "dast_evidence.json")
        facts = evidence.get("verification", [])
        observations.append(
            {
                **source(record["action"]["entry"]),
                "run_id": run_id,
                "profile": record["action"]["profile"],
                "status": record["status"],
                "reason": "positive_oracle_requires_independent_review"
                if handoff["outcome"]["matches"]
                else "completed_controls_without_positive_oracle"
                if verification_coverage(facts)
                else "verification_controls_incomplete",
                "controls_complete": verification_coverage(facts),
                "controls": [
                    {
                        "index": index,
                        "role": "baseline"
                        if index == 0
                        else "negative"
                        if index % 2
                        else "oracle_comparison",
                        "technique": "nonrecursive"
                        if index < 5
                        else "superfluous-url-decode",
                        "status_code": item["status_code"],
                        "oracle": item["oracle"],
                        "request_ref": item["request_sha256"],
                        "response_ref": item["response_sha256"],
                    }
                    for index, item in enumerate(facts)
                ],
                "evidence_ref": "dast_evidence.json",
                "missing_control_indexes": list(
                    range(len(facts), 9 if len(facts) > 5 else 5)
                ),
            }
        )
    for record in state["access"][:8]:
        if record["pending"] or record.get("deferred"):
            continue
        run_id = record["run_id"]
        child = snapshot.json(run_id, "case.json")["state"]
        if child.get("schema_version") == 8:
            comparison = snapshot.json(run_id, "administrative_comparison.json")
            execution = comparison.get("execution", {})
            evidence = execution.get("evidence", [])
            if (
                child.get("request_count") != 2
                or child.get("request_count_exact") is not True
                or execution.get("source_reused") is not True
                or [item.get("slot") for item in evidence]
                != ["source", "anonymous", "negative"]
            ):
                raise ValueError("administrative_progress_changed")
            observations.append(
                {
                    **source(
                        {
                            "endpoint_path": comparison["intent"]["endpoint_path"],
                            "evidence_refs": record["source"]["evidence_refs"],
                        }
                    ),
                    "run_id": run_id,
                    "profile": comparison["intent"]["profile_id"],
                    "status": child["status"],
                    "reason": child["reason"],
                    "evidence_ref": "administrative_comparison.json",
                    "controls": [
                        {
                            "slot": item["slot"],
                            "status": "denied" if item["denied"] else "observed",
                        }
                        for item in evidence
                    ],
                    "controls_complete": True,
                    "missing_control_indexes": [],
                    "request_count": 2,
                    "source_reused": True,
                }
            )
            continue
        for name in child["comparisons"][:8]:
            intent, execution = restore(snapshot.json(run_id, name))
            result = evaluate_access(intent, execution)
            completed = {item.slot: item for item in execution.evidence}
            observations.append(
                {
                    **source(
                        {
                            "endpoint_path": intent.endpoint_path,
                            "evidence_refs": record["source"]["evidence_refs"],
                        }
                    ),
                    "run_id": run_id,
                    "profile": "access-control-get-v1",
                    "status": result.status,
                    "reason": result.reason,
                    "controls_complete": all(
                        slot in completed and completed[slot].complete for slot in SLOTS
                    ),
                    "controls": [
                        {"slot": slot, "complete": False}
                        if slot not in completed
                        else {
                            "slot": slot,
                            **{
                                key: getattr(completed[slot], key)
                                for key in (
                                    "complete",
                                    "authenticated",
                                    "object_bound",
                                    "private_match",
                                    "denied",
                                    "evidence_ref",
                                )
                            },
                        }
                        for slot in SLOTS
                    ],
                    "evidence_ref": name,
                }
            )
    for entry in state["discovery"]["entries"][:32]:
        surface = entry["surface"]
        if surface["source_disclosure"]:
            observations.append(
                {
                    **source(surface),
                    "run_id": surface["source_run_id"],
                    "profile": "authenticated_source_observation",
                    "status": "CANDIDATE" if not surface["ambiguous"] else "PARTIAL",
                    "reason": "source_disclosure_requires_independent_review"
                    if not surface["ambiguous"]
                    else "ambiguous_evidence",
                    "status_code": surface["status_code"],
                    "controls": [],
                    "evidence_ref": "source.json",
                }
            )
    bounded = []
    for item in observations:
        if len(json.dumps([*bounded, item]).encode()) > 12288:
            break
        bounded.append(item)
    return bounded


def conversation_run(view, *, active=False):
    events = view.get("timeline", [])
    authenticated = view.get("evidence_authenticated") is True
    intake = view.get("intake") or {}
    captures = [item for item in events if item["kind"] == "capture"]
    verifications = [item for item in events if item["kind"] == "verification"]
    coverage = [
        {"family": item["family"], "status": item["status"]}
        for item in events
        if item["kind"] == "coverage"
    ]
    findings = view.get("findings", []) if authenticated else []
    verified = authenticated and any(
        value == "verified" for value in view.get("finding_reviews", {}).values()
    )
    terminal = next((item for item in reversed(events) if item["kind"] == "status"), {})
    status = "RUNNING" if active else view["status"]
    return {
        "run_id": view.get("run_id"),
        "status": status,
        "objective": intake.get("task", ""),
        "target": intake.get("target", ""),
        "captured": sum(item.get("status") == "authenticated" for item in captures),
        "capture_pending": any(item.get("status") == "incomplete" for item in captures),
        "providers": [
            {
                key: item.get(key)
                for key in ("provider", "profile", "status", "qualified")
            }
            for item in verifications[:8]
        ],
        "coverage": coverage,
        "findings": [
            {key: item.get(key) for key in ("finding_id", "status", "title")}
            for item in findings[:16]
        ],
        "vulnerability": "verified"
        if verified
        else "candidate"
        if findings
        else "not_established",
        "authenticated": authenticated,
        "observations": view.get("observations", []) if authenticated else [],
        "reason": terminal.get("reason", "execution_incomplete"),
        "failure": next(
            (item for item in reversed(events) if item["kind"] == "failure"), None
        ),
        "details": json.dumps(events, ensure_ascii=False, indent=2)[:4096],
        "source_available": authenticated
        and bool(
            findings or any(item.get("status") == "authenticated" for item in captures)
        ),
    }
