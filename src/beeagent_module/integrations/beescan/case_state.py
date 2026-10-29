import hashlib
import json
import math
import os
import re
from dataclasses import asdict
from ipaddress import ip_address

from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot


def digest(data):
    return hashlib.sha256(
        json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def save_case(artifacts, state):
    envelope = json.loads(json.dumps({"state": state, "sha256": digest(state)}))
    path = _persist(artifacts, "case.pending.json", envelope)
    destination = artifacts.artifact_dir() / "case.json"
    os.replace(path, destination)
    descriptor = os.open(artifacts.artifact_dir(), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    stored = artifacts.read_json("case.json")
    if stored != envelope:
        raise OSError("case_readback_failed")
    return stored


def load_case(storage_dir, case_id):
    try:
        return _load_case(storage_dir, case_id)
    except KeyError, TypeError, AttributeError, OverflowError, RecursionError:
        raise ValueError("invalid_case_checkpoint") from None


def _load_case(storage_dir, case_id):
    from beescan.capabilities.http_probe import HostProvenance
    from beescan.domain.investigation_case import (
        FAMILIES,
        ActionOutcome,
        CaseDecision,
        DecisionKind,
    )
    from beescan.domain.locators import canonical_locator
    from beescan.domain.models import (
        TargetKind,
        validate_identifier,
        validate_references,
    )
    from beescan.domain.web_investigation import (
        InvestigationStatus,
        WebRequestIntent,
        WebResponseFacts,
    )

    validate_identifier(case_id)
    snapshot = AssessmentSnapshot(storage_dir)
    envelope = snapshot.json(case_id, "case.json")
    if (
        set(envelope) != {"state", "sha256"}
        or type(envelope["state"]) is not dict
        or envelope["sha256"] != digest(envelope["state"])
    ):
        raise ValueError("invalid_case_checkpoint")
    state = envelope["state"]
    if (
        set(state)
        != {
            "schema_version",
            "case_id",
            "identity",
            "origin",
            "connected_ip",
            "project_id",
            "scope_id",
            "mission_id",
            "target_id",
            "requested_field",
            "dependency_revision",
            "segments",
            "outcomes",
            "decisions",
            "status",
            "reason",
            "terminal",
            "pending",
            "metrics",
            "evidence_refs",
        }
        or type(state["schema_version"]) is not int
        or state["schema_version"] != 1
        or state["case_id"] != case_id
        or type(state["segments"]) is not list
        or not 1 <= len(state["segments"]) <= 8
        or type(state["outcomes"]) is not list
        or len(state["outcomes"]) > 2
        or type(state["decisions"]) is not list
        or len(state["decisions"]) > 24
        or type(state["evidence_refs"]) is not list
        or type(state["terminal"]) is not bool
        or type(state["pending"]) is not bool
        or state["status"]
        not in {"MATCH", "NO_MATCH", "INCONCLUSIVE", "REFUSED", "TIMEOUT", "ERROR"}
    ):
        raise ValueError("invalid_case_checkpoint")
    validate_references(tuple(state["segments"]))
    validate_references(tuple(state["evidence_refs"]), required=False)
    if canonical_locator(TargetKind.URL, state["origin"]) != state["origin"]:
        raise ValueError("invalid_case_origin")
    if (
        type(state["connected_ip"]) is not str
        or str(ip_address(state["connected_ip"])) != state["connected_ip"]
    ):
        raise ValueError("invalid_case_destination")
    validate_identifier(state["reason"])
    if (
        type(state["requested_field"]) not in {str, type(None)}
        or state["requested_field"] is not None
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", state["requested_field"])
        is None
        or type(state["dependency_revision"]) is not str
        or not (
            re.fullmatch(r"[0-9a-f]{40}", state["dependency_revision"])
            or state["dependency_revision"] == "editable:/home/bee/Pro/beescan"
        )
    ):
        raise ValueError("invalid_case_context")
    for raw in state["decisions"]:
        if type(raw) is not dict or set(raw) != {
            "kind",
            "reason",
            "evidence_refs",
            "task_family",
            "capability_id",
            "run_id",
            "explanation",
        }:
            raise ValueError("invalid_case_decision")
        decision = CaseDecision(
            DecisionKind(raw["kind"]),
            raw["reason"],
            tuple(raw["evidence_refs"]),
            raw["task_family"],
            raw["capability_id"],
        )
        if (
            type(raw["evidence_refs"]) is not list
            or raw["run_id"] not in state["segments"]
            or raw["explanation"] != decision.explanation
        ):
            raise ValueError("invalid_case_decision")
    for key in ("identity", "project_id", "scope_id", "mission_id", "target_id"):
        validate_identifier(state[key])
    metrics = state["metrics"]
    if (
        type(metrics) is not dict
        or set(metrics)
        != {
            "request_count",
            "request_count_exact",
            "capture_launch_count",
            "elapsed_seconds",
            "ai_calls",
            "tokens",
            "cost",
            "usage_status",
        }
        or any(
            type(metrics[key]) is not int or not 0 <= metrics[key] <= 48
            for key in ("request_count", "capture_launch_count", "ai_calls")
        )
        or type(metrics["request_count_exact"]) is not bool
        or type(metrics["elapsed_seconds"]) not in {float, int}
        or not math.isfinite(metrics["elapsed_seconds"])
        or metrics["elapsed_seconds"] < 0
        or metrics["tokens"] is not None
        or metrics["cost"] is not None
        or metrics["usage_status"] != "unavailable"
        or metrics["request_count"] > metrics["capture_launch_count"]
    ):
        raise ValueError("invalid_case_metrics")
    families = set()
    for entry in state["outcomes"]:
        if type(entry) is not dict or set(entry) != {
            "outcome",
            "sources",
            "segment_run_id",
            "sha256",
        }:
            raise ValueError("invalid_case_action")
        payload = {key: entry[key] for key in ("outcome", "sources", "segment_run_id")}
        if (
            digest(payload) != entry["sha256"]
            or entry["segment_run_id"] not in state["segments"]
        ):
            raise ValueError("invalid_case_action")
        raw = dict(entry["outcome"])
        raw["status"] = InvestigationStatus(raw["status"])
        raw["evidence_refs"] = tuple(raw["evidence_refs"])
        outcome = ActionOutcome(**raw)
        if (
            outcome.case_id != case_id
            or outcome.identity != state["identity"]
            or outcome.task_family in families
            or (outcome.task_family, outcome.capability_id) not in FAMILIES
        ):
            raise ValueError("inconsistent_case_action")
        families.add(outcome.task_family)
        stored = snapshot.json(
            entry["segment_run_id"], "case_action_" + outcome.task_family + ".json"
        )
        if stored != payload:
            raise ValueError("case_action_changed")
        if type(entry["sources"]) is not list or not 1 <= len(entry["sources"]) <= 3:
            raise ValueError("missing_case_evidence")
        refs = []
        for source in entry["sources"]:
            if (
                type(source) is not dict
                or set(source)
                != {
                    "run_id",
                    "request_id",
                    "response_id",
                    "evidence_refs",
                    "artifact",
                    "source_sha256",
                    "marker_sha256",
                }
                or source["artifact"] != "source.json"
            ):
                raise ValueError("invalid_case_source")
            record = snapshot.json(source["run_id"], "source.json")
            marker = snapshot.json(source["run_id"], "capture_status.json")
            if set(record) != {
                "schema_version",
                "parent_run_id",
                "integration_status",
                "dependency_revision",
                "run_id",
                "request_id",
                "response_id",
                "facts",
                "projection",
                "source_authentication",
            }:
                raise ValueError("invalid_case_source")
            facts = record["facts"]
            request = facts["request"]
            typed_request = WebRequestIntent(**request)
            typed_facts = dict(facts)
            typed_facts.update(
                request=typed_request,
                provenance=HostProvenance(**facts["provenance"]),
                evidence_refs=tuple(facts["evidence_refs"]),
                links=tuple(facts["links"]),
                failure=InvestigationStatus(facts["failure"])
                if facts["failure"]
                else None,
            )
            WebResponseFacts(**typed_facts)
            if (
                digest(record) != source["source_sha256"]
                or digest(marker) != source["marker_sha256"]
                or record["projection"] != "adaptive-redacted-v1"
                or record["parent_run_id"] != entry["segment_run_id"]
                or record["run_id"] != source["run_id"]
                or record["request_id"] != source["request_id"]
                or record["response_id"] != source["response_id"]
                or re.fullmatch(r"[0-9a-f]{64}", record["source_authentication"])
                is None
                or record["dependency_revision"] != state["dependency_revision"]
                or marker["parent_run_id"] != entry["segment_run_id"]
                or marker["complete"] is not True
                or type(marker["request_count"]) is not int
                or marker["request_count"] != 1
                or marker["run_id"] != source["run_id"]
                or request["run_id"] != outcome.run_id
                or request["origin"] != state["origin"]
                or request["mission_id"] != state["mission_id"]
                or request["target_id"] != state["target_id"]
                or facts["provenance"]["run_id"] != source["run_id"]
                or facts["evidence_refs"] != source["evidence_refs"]
                or facts["response_id"] != source["response_id"]
                or typed_request.child_run_id != source["run_id"]
                or typed_request.request_id != source["request_id"]
                or marker["request_id"] != source["request_id"]
                or marker["response_id"] != source["response_id"]
                or marker["evidence_refs"] != source["evidence_refs"]
                or facts["complete"] is not True
            ):
                raise ValueError("inconsistent_case_evidence")
            if facts["excerpt"] or facts["links"] or "capture" in record:
                raise ValueError("unsafe_case_evidence")
            refs.extend(facts["evidence_refs"])
        if outcome.sufficient and sorted(refs) != sorted(outcome.evidence_refs):
            raise ValueError("insufficient_case_evidence")
        lifecycle = snapshot.json(entry["segment_run_id"], "egress_lifecycle.json")
        if (
            lifecycle.get("cleanup_verified") is not True
            or lifecycle.get("enforcement_verified") is not True
            or lifecycle.get("assessment_run_id") != entry["segment_run_id"]
            or lifecycle.get("state") != "closed"
        ):
            raise ValueError("case_cleanup_unverified")
    snapshot.verify()
    if state["status"] == "MATCH" and not any(
        entry["outcome"]["status"] == "match" and entry["outcome"]["sufficient"]
        for entry in state["outcomes"]
    ):
        raise ValueError("incomplete_case_match")
    if (
        sorted(
            {
                ref
                for entry in state["outcomes"]
                for ref in entry["outcome"]["evidence_refs"]
            }
        )
        != state["evidence_refs"]
    ):
        raise ValueError("inconsistent_case_references")
    return state, snapshot


def restored_outcomes(state):
    from beescan.domain.investigation_case import ActionOutcome
    from beescan.domain.web_investigation import InvestigationStatus

    result = []
    for entry in state["outcomes"]:
        raw = dict(entry["outcome"])
        raw["status"] = InvestigationStatus(raw["status"])
        raw["evidence_refs"] = tuple(raw["evidence_refs"])
        if not raw["sufficient"] or raw.get("action_id") is None:
            raise ValueError("case_evidence_insufficient")
        result.append(ActionOutcome(**raw))
    return tuple(result)


def action_record(outcome, sources, segment_run_id):
    payload = json.loads(
        json.dumps(
            {
                "outcome": asdict(outcome),
                "sources": sources,
                "segment_run_id": segment_run_id,
            }
        )
    )
    return payload, {**payload, "sha256": digest(payload)}
