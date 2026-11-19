import json
import logging
import os
from collections import Counter
from datetime import UTC, datetime

from beeagent_module.integrations.beescan.case_state import digest, load_case
from beeagent_module.integrations.beescan.progress import _REASONS, _count, _identifier
from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot
from beeagent_module.integrations.beescan.web import _read_owned, _sign

_FAILURES = {"PARTIAL", "ERROR", "REFUSED", "TIMEOUT"}
_OUTCOMES = {"CANDIDATE", "NO_MATCH", "MATCH", "INCONCLUSIVE"}
_DAST_STATES = {
    "complete": "COMPLETED",
    "budget": "PARTIAL",
    "cancelled": "PARTIAL",
    "timeout": "TIMEOUT",
    "crashed": "ERROR",
    "error": "ERROR",
}
_DAST_DIAGNOSTICS = _REASONS | {
    "zap_worker_failed",
    "dast_mediator_failed",
}


def publish_lifecycle(api, settings, run_id, status, *, reason=None, execution=None):
    from beeagent_module.integrations.beescan.detection import _persist
    from beeagent_module.integrations.beescan.detection_runner import read_regular

    try:
        now = datetime.now(UTC).isoformat()
        try:
            previous = json.loads(
                read_regular(
                    api.artifact_dir() / "web_execution.json",
                    limit=131072,
                    owner_uid=os.getuid(),
                )
            )
        except FileNotFoundError:
            previous = None
        if previous is not None:
            previous = _signed_lifecycle(previous, run_id, settings)
        stages = previous.get("stages", []) if previous is not None else []
        if execution is None:
            value = {"run_id": run_id, "status": status, "timestamp": now}
            if reason in _REASONS:
                value["reason"] = reason
        else:
            if previous is None:
                return
            value = previous
            stage = next(
                (item for item in stages if item["run_id"] == execution["run_id"]),
                None,
            )
            if stage is None:
                if status != "RUNNING" or len(stages) >= 64:
                    return
                if execution["kind"] == "verification" and stages:
                    discovery = stages[0]
                    if (
                        discovery["kind"] == "discovery"
                        and discovery["status"] == "RUNNING"
                    ):
                        discovery.update(status="COMPLETED", timestamp=now)
                stage = {**execution, "started_at": now}
                stages.append(stage)
            elif stage["status"] != "RUNNING":
                return
            stage.update(status=status, timestamp=now)
        if stages:
            value["stages"] = stages
        _persist(
            api,
            "web_execution.json",
            {"value": value, "signature": _sign(settings, value)},
        )
    except OSError, ValueError, KeyError, TypeError, RecursionError:
        logging.getLogger(__name__).warning(
            "Web execution lifecycle unavailable: run_id=%s", run_id
        )


def _record(run_id, kind, status, *, outcome=None, **fields):
    return {
        "id": "execution-" + run_id,
        "run_id": run_id,
        "kind": kind,
        "status": status
        if status in _FAILURES | {"QUEUED", "RUNNING", "COMPLETED"}
        else "UNAVAILABLE",
        "outcome": outcome if outcome in _OUTCOMES | {"PARTIAL"} else None,
        **fields,
    }


def _dast(snapshot, run_id, action=None):
    from beeagent_module.integrations.beescan.dast import _restore

    intent, execution, _, report = _restore(snapshot, run_id)
    elapsed = (execution.ended_at - intent.started_at).total_seconds()
    raw_marker = snapshot.files.get((run_id, "dast_execution_status.json"))
    marker = json.loads(raw_marker) if raw_marker else {}
    if marker and marker.get("run_id") != run_id:
        raise PermissionError("execution_diagnostics_changed")
    reason = marker.get("reason")
    evidence = snapshot.json(run_id, "dast_evidence.json")
    return _record(
        run_id,
        "verification",
        _DAST_STATES[execution.state.value],
        outcome=report.data["status"],
        action_id=action["action_id"] if action else None,
        source_run_id=action["action"]["entry"]["source_run_id"] if action else None,
        provider=intent.provider_id,
        provider_version=intent.provider_version,
        profile=intent.profile,
        started_at=intent.started_at.isoformat(),
        ended_at=execution.ended_at.isoformat(),
        duration_ms=round(elapsed * 1000) if 0 <= elapsed <= 10**9 else None,
        requests=execution.request_count,
        request_budget=intent.request_budget,
        checks=len(execution.covered_checks),
        checks_total=len(intent.check_ids),
        response_counts=dict(
            Counter(item["status_code"] for item in evidence["requests"])
        ),
        controls=[
            {
                "status_code": item["status_code"],
                "oracle": item["oracle"],
                "role": "baseline"
                if index == 0
                else "negative"
                if index % 2
                else "comparison",
            }
            for index, item in enumerate(evidence.get("verification", []))
        ],
        cleanup=execution.cleanup_verified,
        reason=reason if reason in _DAST_DIAGNOSTICS else None,
        evidence_refs=list(report.data["evidence_refs"])[:8],
        artifact="dast_evidence.json",
    )


def _discovery(snapshot, state, run_id, marker, *, integrated, verified_child):
    steps = json.loads(snapshot.read(run_id, "investigation_steps.json"))
    if (
        type(steps) is not list
        or len(steps) > 64
        or any(type(step) is not dict for step in steps)
    ):
        raise ValueError("invalid_execution_steps")
    lifecycle = snapshot.files.get((run_id, "egress_lifecycle.json"))
    cleanup = json.loads(lifecycle).get("cleanup_verified") if lifecycle else None
    metrics = state["metrics"]
    count = (
        _count(metrics["request_count"])
        if metrics["request_count_exact"] is True
        else None
    )
    entries = [
        entry for entry in state.get("entries", []) if entry["segment_run_id"] == run_id
    ]
    references = [ref for entry in entries for ref in entry["surface"]["evidence_refs"]]
    status = state["status"]
    if (status in _OUTCOMES or verified_child) and not state["pending"]:
        status = "COMPLETED"
    reason = state.get("reason")
    return _record(
        run_id,
        "discovery",
        status,
        provider="host-web-capture",
        capture_steps=len(steps),
        requests=count,
        request_budget=_count(
            marker.get("execution_context", {}).get("effective_request_budget")
        ),
        cleanup=cleanup if type(cleanup) is bool else None,
        reason=reason if not integrated and reason in _REASONS else None,
        steps=[
            {"phase": step["step"], "status": step["status"]}
            for step in steps[:8]
            if step.get("step")
            in {
                "discovery",
                "resource",
                "baseline",
                "mutation",
                "diagnostic",
                "identity",
                "hypothesis",
                "comparison",
            }
            and step.get("status")
            in {"incomplete", "captured", "authenticated", "redirected", "skipped"}
        ],
        evidence_refs=list(dict.fromkeys(references))[:8],
        artifact="investigation_steps.json",
    )


def _access(snapshot, child, run_id, status, *, record=None):
    metrics = child.get("metrics", child)
    reason = child.get("reason")
    lifecycle = snapshot.files.get((run_id, "egress_lifecycle.json"))
    cleanup = json.loads(lifecycle).get("cleanup_verified") if lifecycle else None
    return _record(
        run_id,
        "verification",
        "COMPLETED" if status in _OUTCOMES else status,
        outcome=status,
        action_id=record["action_id"] if record else child.get("action_id"),
        source_run_id=record["source"]["source_run_id"] if record else None,
        profile=child.get("profile_id"),
        requests=_count(metrics.get("request_count"))
        if metrics.get("request_count_exact") is True
        else None,
        cleanup=cleanup if type(cleanup) is bool else None,
        reason=reason if reason in _REASONS else None,
        evidence_refs=(record or child).get("evidence_refs", [])[:8],
        artifact="case.json",
    )


def _signed_lifecycle(value, run_id, settings):
    event = value["value"]
    if event["run_id"] != run_id or value.get("signature") != _sign(settings, event):
        raise PermissionError("execution_lifecycle_changed")
    return event


def _lifecycle_record(event, live):
    status = event["status"]
    return _record(
        event["run_id"],
        event.get("kind", "investigation"),
        "UNAVAILABLE" if status in {"RUNNING", "QUEUED"} and not live else status,
        observed_at=event["timestamp"],
        reason=event.get("reason"),
        event_status=status,
        started_at=event.get(
            "started_at", event["timestamp"] if status == "RUNNING" else ""
        ),
        **{
            key: event[key]
            for key in ("action_id", "provider", "profile")
            if key in event
        },
    )


def _check_child_owner(host, settings, child_id, actor, binding):
    owned = _read_owned(host.storage, settings, child_id, actor)
    if any(
        owned.get(key) != binding.get(key)
        for key in (
            "case_id",
            "parent_case_id",
            "target",
            "principal_id",
            "context_sha256",
            "authority_sha256",
            "task_sha256",
        )
    ):
        raise PermissionError("execution_child_binding_changed")


def records_for_run(host, conversation_id, run, actor):
    from beescan.domain.locators import canonical_locator
    from beescan.domain.models import TargetKind

    run_id = run["run_id"]
    settings = host.reload_settings()
    binding = _read_owned(host.storage, settings, run_id, actor)
    if (
        binding["case_id"] != run_id
        or binding.get("parent_case_id") != conversation_id
        or binding.get("authority_sha256") != run.get("authority_sha256")
        or binding.get("context_sha256")
        != digest(
            {"context": run.get("context"), "attachments": run.get("attachments")}
        )
    ):
        raise PermissionError("execution_conversation_binding_changed")
    target = run.get("context", {}).get("target")
    if type(target) is not str or canonical_locator(
        TargetKind.URL, target
    ) != canonical_locator(TargetKind.URL, binding["target"]):
        raise PermissionError("execution_conversation_binding_changed")
    source = AssessmentSnapshot(host.storage)
    try:
        receipt = source.json(run_id, "web_receipt.json")
    except FileNotFoundError:
        live = (
            run_id in host.conversations.running or run_id in host.conversations.pending
        )
        try:
            event = _signed_lifecycle(
                source.json(run_id, "web_execution.json"), run_id, settings
            )
        except FileNotFoundError:
            return []
        stages = event.get("stages", [])
        if not live and not stages and event["status"] not in _FAILURES:
            try:
                source.read(run_id, "case.json")
            except FileNotFoundError:
                pass
            else:
                raise PermissionError("execution_receipt_missing") from None
        records = []
        seen = set()
        for stage in stages:
            child_id = stage["run_id"]
            if child_id in seen or not _identifier(child_id):
                raise PermissionError("execution_lifecycle_changed")
            seen.add(child_id)
            if child_id != run_id:
                _check_child_owner(host, settings, child_id, actor, binding)
            if (
                child_id == run_id
                and stage["status"] == "RUNNING"
                and event["status"] in _FAILURES
            ):
                stage = {
                    **stage,
                    "status": event["status"],
                    "timestamp": event["timestamp"],
                    "reason": event.get("reason"),
                }
            records.append(
                _lifecycle_record(
                    stage, live and event["status"] in {"QUEUED", "RUNNING"}
                )
            )
        source.verify()
        return records or [_lifecycle_record(event, live)]
    if receipt.get("signature") != _sign(settings, receipt["files"]):
        raise PermissionError("execution_receipt_changed")
    state, snapshot = load_case(host.storage, run_id)
    if receipt != host._receipt(snapshot, settings):
        raise PermissionError("execution_receipt_changed")
    signed = set(snapshot.files)
    marker = snapshot.json(run_id, "investigation_status.json")
    schema = state["schema_version"]
    if schema == 3:
        records = [_dast(snapshot, run_id)]
    elif schema in {5, 6, 8}:
        records = [_access(snapshot, state, run_id, state["status"])]
    else:
        discovery = state.get("discovery", state)
        if discovery["segments"] != [run_id]:
            return []
        records = []
        children = {
            item["action_id"]: item
            for item in (*state.get("assessments", []), *state.get("access", []))
        }
        order = (
            [item["action_id"] for item in state.get("outcomes", [])]
            if schema == 7
            else []
        )
        if schema == 4 and state.get("assessment"):
            child = state["assessment"]
            children[child["action_id"]] = child
            order = [child["action_id"]]
        for action_id in order:
            child = children.get(action_id)
            if child is None or child.get("pending") or not child.get("run_id"):
                continue
            child_id = child["run_id"]
            _check_child_owner(host, settings, child_id, actor, binding)
            if "action" in child:
                records.append(_dast(snapshot, child_id, child))
            else:
                child_state = snapshot.json(child_id, "case.json")["state"]
                result = snapshot.json(child_id, "investigation_result.json")
                records.append(
                    _access(
                        snapshot, child_state, child_id, result["status"], record=child
                    )
                )
        records.insert(
            0,
            _discovery(
                snapshot,
                discovery,
                run_id,
                marker,
                integrated=schema in {4, 7},
                verified_child=bool(records),
            ),
        )
        try:
            lifecycle = _signed_lifecycle(
                source.json(run_id, "web_execution.json"), run_id, settings
            )
        except FileNotFoundError:
            lifecycle = {}
        for stage in lifecycle.get("stages", []):
            if stage["run_id"] == run_id and stage["kind"] == "discovery":
                records[0]["started_at"] = stage["started_at"]
                break
    if set(snapshot.files) != signed or any(
        not _identifier(item["run_id"]) for item in records
    ):
        raise PermissionError("execution_source_not_authenticated")
    snapshot.verify()
    source.verify()
    return records
