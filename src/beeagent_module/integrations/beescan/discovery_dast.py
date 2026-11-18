from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from beeagent_module.integrations.beescan.case_state import digest
from beeagent_module.integrations.beescan.dast import _restore, approval_identity

if TYPE_CHECKING:
    from beescan.domain.assessment_selection import AssessmentAction
    from beescan.domain.debug_disclosure import SensitiveValue
    from beescan.domain.general_investigation import GeneralCase


def discovery_selected(settings):
    dast = settings.get("beescan", {}).get("dast", {})
    approval = dast.get("approval")
    return (
        dast.get("enabled") is True
        and type(approval) is dict
        and approval.get("entry_selection") == "authenticated_discovery"
    )


@dataclass(frozen=True)
class SelectedAssessment:
    case: GeneralCase
    action: AssessmentAction
    entry: SensitiveValue
    request_budget: int
    seconds: int
    reauthorize: Callable[[], Any]

    def verify(self, policy):
        from beescan.domain.assessment_selection import (
            validate_action,
            validate_entry_url,
        )

        self.reauthorize()
        validate_action(self.case, self.action, at=datetime.now(UTC))
        validate_entry_url(self.action, self.entry, origin=policy.transport.origin)
        transport = policy.transport
        intent = self.case.intent
        if (
            policy.entry_selection != "authenticated_discovery"
            or self.action.profile != policy.profile
            or (
                transport.project_id,
                transport.scope_id,
                transport.mission_id,
                transport.target_id,
                transport.origin,
            )
            != (
                intent.project.project_id,
                intent.scope.scope_id,
                intent.mission.mission_id,
                intent.spec.target_id,
                intent.origin,
            )
            or type(self.request_budget) is not int
            or self.request_budget < 1
            or type(self.seconds) is not int
            or self.seconds < 1
        ):
            raise PermissionError("discovered_assessment_identity")


def wrap_case(discovery, assessment, policy):
    count = assessment["request_count"] if assessment else 0
    status = assessment["status"] if assessment else "PARTIAL"
    if discovery["status"] in {"ERROR", "TIMEOUT", "REFUSED"}:
        status = discovery["status"]
    return {
        "schema_version": 4,
        "case_id": discovery["case_id"],
        "origin": discovery["origin"],
        "operator_uid": os.getuid(),
        "approval_identity": approval_identity(policy),
        "discovery": discovery,
        "assessment": assessment,
        "pending": discovery["pending"] or bool(assessment and assessment["pending"]),
        "status": status,
        "metrics": {
            **discovery["metrics"],
            "request_count": discovery["metrics"]["request_count"] + count,
        },
    }


def load_integrated_case(state, snapshot, case_id):

    from beeagent_module.integrations.beescan.case_state import _load_general_case

    if (
        set(state)
        != {
            "schema_version",
            "case_id",
            "origin",
            "operator_uid",
            "approval_identity",
            "discovery",
            "assessment",
            "pending",
            "status",
            "metrics",
        }
        or state["case_id"] != case_id
        or state["operator_uid"] != os.getuid()
        or type(state["operator_uid"]) is not int
        or state["schema_version"] != 4
        or type(state["approval_identity"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", state["approval_identity"]) is None
        or state["pending"] is not False
        or state["origin"] != state["discovery"]["origin"]
    ):
        raise ValueError("invalid_integrated_case")
    if state["discovery"].get("schema_version") != 2:
        raise ValueError("invalid_integrated_discovery")
    discovery, _ = _load_general_case(state["discovery"], snapshot, case_id)
    assessment = state["assessment"]
    if assessment is not None:
        if (
            type(assessment) is not dict
            or set(assessment)
            != {
                "action",
                "action_id",
                "run_id",
                "pending",
                "status",
                "request_count",
                "source_sha256",
            }
            or assessment["pending"] is not False
        ):
            raise ValueError("incomplete_integrated_assessment")
        validate_assessment(assessment, discovery, state["origin"], snapshot, case_id)
    expected_count = discovery["metrics"]["request_count"] + (
        assessment["request_count"] if assessment else 0
    )
    expected_status = (
        discovery["status"]
        if discovery["status"] in {"ERROR", "TIMEOUT", "REFUSED"}
        else assessment["status"]
        if assessment
        else "PARTIAL"
    )
    if state["status"] != expected_status or state["metrics"] != {
        **discovery["metrics"],
        "request_count": expected_count,
    }:
        raise ValueError("integrated_metrics_changed")
    segment = discovery["segments"][-1]
    receipt = snapshot.json(segment, "unified_report_receipt.json")
    report = snapshot.json(segment, "report.json")
    marker = snapshot.json(segment, "investigation_status.json")
    if (
        receipt
        != {
            "report_sha256": digest(report),
            "markdown_sha256": hashlib.sha256(
                snapshot.read(segment, "report.md")
            ).hexdigest(),
            "status_sha256": digest(marker),
        }
        or report["status"] != state["status"]
        or marker["status"] != state["status"]
        or report["metrics"] != state["metrics"]
        or marker["metrics"] != state["metrics"]
        or report.get("assessment") != assessment
    ):
        raise ValueError("integrated_report_changed")
    snapshot.verify()
    return state, snapshot


def validate_assessment(
    assessment, discovery, origin, snapshot, case_id, *, pending=False
):
    from beescan.domain.assessment_selection import AssessmentAction, ObservedEntry

    raw = dict(assessment["action"])
    entry = dict(raw["entry"])
    entry["evidence_refs"] = tuple(entry["evidence_refs"])
    entry["parameter_names"] = tuple(entry["parameter_names"])
    raw["entry"] = ObservedEntry(**entry)
    action = AssessmentAction(**raw)
    if action.entry is None:
        raise ValueError("integrated_source_missing")
    if action.case_id != case_id or action.objective_id != discovery["objective_id"]:
        raise ValueError("integrated_action_identity")
    source = next(
        (
            item
            for item in discovery["entries"]
            if item["surface"]["response_id"] == action.entry.source_response_id
        ),
        None,
    )
    if source is None:
        raise ValueError("integrated_source_missing")
    surface = source["surface"]
    record = snapshot.json(action.entry.source_run_id, "source.json")
    observations = snapshot.json(
        action.entry.source_run_id, "assessment_observations.json"
    )
    from beeagent_module.integrations.beescan.dast import _plain

    if (
        assessment["action_id"] != action.action_id
        or assessment["source_sha256"] != digest(record)
        or observations
        != {"source_sha256": digest(record), "entries": observations.get("entries")}
        or _plain(action.entry) not in observations["entries"]
        or action.entry.context_id != surface["context_id"]
        or action.entry.source_request_id != surface["request_id"]
        or action.entry.source_run_id != surface["source_run_id"]
        or list(action.entry.evidence_refs) != surface["evidence_refs"]
        or action.context_id != surface["context_id"]
        or action.mission_id != record["facts"]["request"]["mission_id"]
        or action.target_id != record["facts"]["request"]["target_id"]
    ):
        raise ValueError("integrated_source_changed")
    if pending:
        return action
    intent, execution, _, report = _restore(snapshot, assessment["run_id"])
    if action.profile == "traversal-nonrecursive-v1":
        facts = snapshot.json(assessment["run_id"], "dast_evidence.json")[
            "verification"
        ]
        if facts and facts[0]["request_sha256"] != action.entry.entry_sha256:
            raise ValueError("integrated_verification_source_changed")
    if (
        intent.parent_run_id != case_id
        or intent.target.locator != origin
        or (
            intent.project.project_id,
            intent.scope.scope_id,
            intent.mission.mission_id,
            intent.target.target_id,
        )
        != (action.project_id, action.scope_id, action.mission_id, action.target_id)
        or intent.check_ids != (action.check_id,)
        or intent.profile != action.profile
        or intent.rule_ids != (action.rule_id,)
        or intent.provider_id != action.provider_id
        or intent.provider_version != action.provider_version
        or assessment["status"] != report.data["status"]
        or assessment["request_count"] != execution.request_count
    ):
        raise ValueError("integrated_execution_changed")
    return action


def access_verification_refs(state, snapshot, result):
    refs = tuple(
        ref for item in result["observations"] for ref in item["evidence_refs"]
    )
    if refs:
        return refs
    return tuple(
        dict.fromkeys(
            evidence["evidence_ref"]
            for name in state["comparisons"]
            for evidence in snapshot.json(state["case_id"], name)["execution"][
                "evidence"
            ]
        )
    )


def completed_access_owner_paths(state, snapshot):
    from beescan.domain.access_control import evaluate_access

    from beeagent_module.integrations.beescan.access_control import restore

    return tuple(
        hypothesis["owner"]["relative_url"]
        for name, hypothesis in zip(state["comparisons"], state["hypotheses"])
        if evaluate_access(*restore(snapshot.json(state["case_id"], name))).status
        in {"CANDIDATE", "NO_MATCH"}
    )


def load_multifamily_case(state, snapshot, case_id):
    from beescan.domain.assessment_selection import (
        BUDGET_REASONS,
        VerificationOutcome,
        access_discovery_action_id,
        coverage_summary,
        disclosure_action_id,
        verification_coverage,
        verification_coverage_data,
    )

    from beeagent_module.integrations.beescan.case_state import (
        _load_general_case,
    )

    if (
        set(state)
        != {
            "schema_version",
            "case_id",
            "origin",
            "operator_uid",
            "authority_sha256",
            "discovery",
            "assessments",
            "access",
            "outcomes",
            "findings",
            "status",
            "metrics",
            "pending",
            "egress_runs",
            "context",
        }
        or state["case_id"] != case_id
        or state["operator_uid"] != os.getuid()
        or type(state["operator_uid"]) is not int
        or type(state["pending"]) is not bool
        or state["pending"]
        and (
            state["metrics"]["request_count_exact"] is not False
            or state["status"] not in {"ERROR", "REFUSED", "TIMEOUT", "PARTIAL"}
        )
        or state["origin"] != state["discovery"]["origin"]
        or re.fullmatch(r"[0-9a-f]{64}", state["authority_sha256"]) is None
        or type(state["assessments"]) is not list
        or len(state["assessments"]) > 32
        or type(state["access"]) is not list
        or len(state["access"]) > 32
    ):
        raise ValueError("invalid_multifamily_case")
    discovery, _ = _load_general_case(state["discovery"], snapshot, case_id)
    if (
        type(state["egress_runs"]) is not list
        or len(state["egress_runs"]) > 64
        or len(set(state["egress_runs"])) != len(state["egress_runs"])
    ):
        raise ValueError("invalid_discovery_egress_history")
    for run in state["egress_runs"]:
        lifecycle = snapshot.json(run, "egress_lifecycle.json")
        if (
            lifecycle.get("assessment_run_id") != run
            or lifecycle.get("state") != "closed"
            or lifecycle.get("cleanup_verified") is not True
            or lifecycle.get("enforcement_verified") is not True
        ):
            raise ValueError("discovery_egress_incomplete")
    intent = restore_general_intent(state["context"])
    if (
        intent.run_id not in discovery["segments"]
        or intent.origin != state["origin"]
        or any(
            entry["surface"]["context_id"] != intent.binding
            for entry in discovery["entries"]
        )
    ):
        raise ValueError("multifamily_context_changed")
    outcomes = tuple(
        VerificationOutcome(
            **{
                **item,
                "evidence_refs": tuple(item["evidence_refs"]),
                "finding_ids": tuple(item["finding_ids"]),
            }
        )
        for item in state["outcomes"]
    )
    verification_coverage(outcomes)
    identifiers = [
        record["action_id"] for record in (*state["assessments"], *state["access"])
    ]
    runs = [
        record["run_id"]
        for record in (*state["assessments"], *state["access"])
        if record["run_id"] is not None
    ]
    if len(set(identifiers)) != len(identifiers) or len(set(runs)) != len(runs):
        raise ValueError("repeated_multifamily_action")
    accepted = {}
    findings = []
    count = discovery["metrics"]["request_count"]
    deferred = {}
    for record in state["assessments"]:
        if record.get("deferred") is not None:
            action = validate_assessment(
                record, discovery, state["origin"], snapshot, case_id, pending=True
            )
            if (
                record["deferred"] not in BUDGET_REASONS
                or record["pending"] is not False
                or record["run_id"] is not None
                or record["request_count"] != 0
                or record["status"] != "PARTIAL"
            ):
                raise ValueError("invalid_deferred_assessment")
            deferred[record["action_id"]] = record["deferred"]
            accepted[record["action_id"]] = (
                "path_traversal",
                "PARTIAL",
                action.entry.evidence_refs,
                (),
            )
            continue
        if record["pending"] is True:
            action = validate_assessment(
                record, discovery, state["origin"], snapshot, case_id, pending=True
            )
            if not state["pending"] or record["request_count"] != 0:
                raise ValueError("incomplete_multifamily_assessment")
            accepted[record["action_id"]] = (
                "path_traversal",
                state["status"],
                action.entry.evidence_refs,
                (),
            )
            continue
        if record["pending"] is not False or record["run_id"] is None:
            raise ValueError("incomplete_multifamily_assessment")
        validate_assessment(record, discovery, state["origin"], snapshot, case_id)
        report = snapshot.json(record["run_id"], "report.json")
        accepted[record["action_id"]] = (
            "path_traversal",
            report["status"],
            tuple(report["evidence_refs"]),
            tuple(f["finding_id"] for f in report["findings"]),
        )
        findings.extend(report["findings"])
        count += record["request_count"]
    inspected_access_paths = set()
    compared_owner_paths = set()
    for record in state["access"]:
        surface = next(
            (
                entry["surface"]
                for entry in discovery["entries"]
                if entry["surface"] == record["source"]
            ),
            None,
        )
        if surface is None or record["run_id"] == case_id:
            raise ValueError("unbound_access_discovery")
        expected_id = access_discovery_action_id(
            case_id,
            discovery["objective_id"],
            restore_surface(surface),
            record["profile_id"],
        )
        if record["action_id"] != expected_id:
            raise ValueError("access_discovery_source_changed")
        if record.get("kind") == "administrative":
            child_envelope = snapshot.json(record["run_id"], "case.json")
            child = child_envelope.get("state", {})
            comparison = snapshot.json(
                record["run_id"], "administrative_comparison.json"
            )
            result = snapshot.json(record["run_id"], "investigation_result.json")
            if (
                child_envelope.get("sha256") != digest(child)
                or child.get("schema_version") != 8
                or child.get("case_id") != record["run_id"]
                or child.get("parent_case_id") != case_id
                or child.get("action_id") != expected_id
                or child.get("source") != surface
                or child.get("profile_id") != record["profile_id"]
                or child.get("source_sha256")
                != digest(snapshot.json(surface["source_run_id"], "source.json"))
                or child.get("request_count") != 2
                or child.get("request_count_exact") is not True
                or tuple(child.get("evidence_refs", ()))
                != tuple(record["evidence_refs"])
                or comparison.get("source_sha256") != child.get("source_sha256")
                or comparison.get("profile_sha256") != child.get("profile_sha256")
                or comparison.get("execution", {}).get("source_reused") is not True
                or comparison.get("execution", {}).get("request_count") != 2
                or result.get("status") != child.get("status")
                or record["pending"] is not False
                or record["request_count"] != 2
            ):
                raise ValueError("administrative_child_changed")
            accepted[expected_id] = (
                "access_control",
                result["status"],
                tuple(record["evidence_refs"]),
                tuple(item["finding_id"] for item in result["findings"]),
            )
            findings.extend(result["findings"])
            count += 2
            continue
        if record.get("deferred") is not None:
            if (
                record["deferred"] not in BUDGET_REASONS
                or record["pending"] is not False
                or record["run_id"] is not None
                or record["request_count"] != 0
                or tuple(record["evidence_refs"]) != tuple(surface["evidence_refs"])
            ):
                raise ValueError("invalid_deferred_access")
            deferred[expected_id] = record["deferred"]
            accepted[expected_id] = (
                "access_control",
                "PARTIAL",
                tuple(surface["evidence_refs"]),
                (),
            )
            continue
        if record["pending"] is True:
            if not state["pending"] or record["request_count"] != 0:
                raise ValueError("incomplete_multifamily_access")
            accepted[expected_id] = (
                "access_control",
                state["status"],
                tuple(surface["evidence_refs"]),
                (),
            )
            continue
        if record["pending"] is not False:
            raise ValueError("incomplete_multifamily_access")
        child_envelope = snapshot.json(record["run_id"], "case.json")
        if (
            set(child_envelope) != {"state", "sha256"}
            or child_envelope["sha256"] != digest(child_envelope["state"])
            or child_envelope["state"].get("schema_version") != 6
        ):
            raise ValueError("invalid_access_discovery_child")
        from beeagent_module.integrations.beescan.access_discovery import (
            load_discovery_case,
        )

        child, _ = load_discovery_case(
            child_envelope["state"], snapshot, record["run_id"]
        )
        if "discovery_source" in child and (
            child["discovery_source"] != surface["relative_url"]
            or child["discovery_source"] in inspected_access_paths
            or child["excluded_owner_paths"] != sorted(compared_owner_paths)
            or any(
                item["owner"]["relative_url"] in compared_owner_paths
                for item in child["hypotheses"]
            )
        ):
            raise ValueError("replayed_access_discovery_source")
        inspected_access_paths.update(
            item["relative_url"]
            for item in snapshot.json(record["run_id"], "discovery_evidence.json")[
                "observations"
            ]
            if item["complete"] is True
        )
        compared_owner_paths.update(completed_access_owner_paths(child, snapshot))
        result = snapshot.json(record["run_id"], "investigation_result.json")
        if (
            child["schema_version"] != 6
            or child["profile_id"] != record["profile_id"]
            or child["metrics"]["request_count"] != record["request_count"]
            or record["step_count"]
            != child["discovery_request_count"] + len(child["comparisons"])
        ):
            raise ValueError("access_discovery_child_changed")
        accepted[expected_id] = (
            "access_control",
            result["status"],
            tuple(record["evidence_refs"]),
            tuple(f["finding_id"] for f in result["findings"]),
        )
        if tuple(record["evidence_refs"]) != access_verification_refs(
            child, snapshot, result
        ):
            raise ValueError("access_discovery_evidence_changed")
        findings.extend(result["findings"])
        count += record["request_count"]
    for entry in discovery["entries"]:
        surface = entry["surface"]
        if not surface["source_disclosure"] or surface["ambiguous"]:
            continue
        action_id = disclosure_action_id(
            case_id, discovery["objective_id"], restore_surface(surface)
        )
        finding = disclosure_finding(case_id, surface)
        accepted[action_id] = (
            "information_disclosure",
            "CANDIDATE",
            tuple(surface["evidence_refs"]),
            (finding["finding_id"],),
        )
        findings.append(finding)
    for item in outcomes:
        expected = accepted.pop(item.action_id, None)
        if expected != (
            item.family,
            item.status,
            item.evidence_refs,
            item.finding_ids,
        ) or item.reason != deferred.get(item.action_id):
            raise ValueError("multifamily_outcome_changed")
    findings.sort(key=lambda item: item["finding_id"])
    if (
        accepted
        or state["findings"] != findings
        or len({f["finding_id"] for f in findings}) != len(findings)
    ):
        raise ValueError("multifamily_findings_changed")
    if count > intent.spec.request_budget or state["metrics"] != {
        **discovery["metrics"],
        "request_count": count,
    }:
        raise ValueError("multifamily_accounting_changed")
    segment = discovery["segments"][-1]
    report = snapshot.json(segment, "report.json")
    marker = snapshot.json(segment, "investigation_status.json")
    executed_steps = (
        len(discovery["entries"])
        + sum(item.reason is None for item in outcomes)
        + sum(max(0, record.get("step_count", 1) - 1) for record in state["access"])
    )
    remaining_seconds = (
        intent.spec.time_budget_seconds - state["metrics"]["elapsed_seconds"]
    )
    for reason in deferred.values():
        if (
            reason == "request_budget_exhausted"
            and count < intent.spec.request_budget
            or reason == "step_budget_exhausted"
            and executed_steps < marker["execution_context"]["step_budget"]
            or reason == "time_budget_exhausted"
            and remaining_seconds >= 1
            or reason == "verification_time_insufficient"
            and remaining_seconds >= 10
        ):
            raise ValueError("unproven_verification_budget_stop")
    receipt = snapshot.json(segment, "unified_report_receipt.json")
    if (
        receipt
        != {
            "report_sha256": digest(report),
            "markdown_sha256": hashlib.sha256(
                snapshot.read(segment, "report.md")
            ).hexdigest(),
            "status_sha256": digest(marker),
        }
        or report["findings"] != findings
        or report["metrics"] != state["metrics"]
        or report["status"] != state["status"]
        or marker["status"] != state["status"]
        or marker["metrics"] != state["metrics"]
    ):
        raise ValueError("multifamily_report_changed")
    expected_status = (
        state["status"]
        if state["pending"]
        else discovery["status"]
        if discovery["status"] in {"ERROR", "TIMEOUT", "REFUSED"}
        else "CANDIDATE"
        if findings
        else "PARTIAL"
    )
    expected_coverage = json.loads(json.dumps(verification_coverage_data(outcomes)))
    if (
        report.get("coverage_summary") != coverage_summary(outcomes)
        or marker.get("coverage_summary") != coverage_summary(outcomes)
        or report.get("coverage") != expected_coverage
        or marker.get("coverage") != expected_coverage
    ):
        raise ValueError("multifamily_coverage_changed")
    if state["status"] != expected_status:
        raise ValueError("multifamily_status_changed")
    snapshot.verify()
    return state, snapshot


def restore_surface(raw):
    from beescan.domain.assessment_selection import ObservedEntry
    from beescan.domain.general_investigation import Resource, Surface

    return Surface(
        **{
            **raw,
            "evidence_refs": tuple(raw["evidence_refs"]),
            "parameter_names": tuple(raw["parameter_names"]),
            "resources": tuple(
                Resource(**{**item, "evidence_refs": tuple(item["evidence_refs"])})
                for item in raw["resources"]
            ),
            "assessment_entries": tuple(
                ObservedEntry(
                    **{
                        **item,
                        "evidence_refs": tuple(item["evidence_refs"]),
                        "parameter_names": tuple(item["parameter_names"]),
                    }
                )
                for item in raw.get("assessment_entries", ())
            ),
        }
    )


def disclosure_finding(case_id, surface):
    from dataclasses import asdict

    from beescan.domain.assessment_selection import disclosure_finding as finding

    return json.loads(json.dumps(asdict(finding(case_id, restore_surface(surface)))))


def restore_general_intent(raw):
    from datetime import datetime

    from beescan.domain.models import (
        EngagementScope,
        Mission,
        MissionSpec,
        Project,
        Target,
        TargetKind,
    )
    from beescan.domain.web_investigation import InvestigationIntent

    values = dict(raw)
    scope = dict(values["scope"])
    for key in ("target_ids", "excluded_target_ids", "approved_methods"):
        scope[key] = tuple(scope[key])
    for key in ("valid_from", "expires_at"):
        scope[key] = datetime.fromisoformat(scope[key])
    values.update(
        project=Project(**values["project"]),
        targets=tuple(
            Target(**{**item, "kind": TargetKind(item["kind"])})
            for item in values["targets"]
        ),
        scope=EngagementScope(**scope),
        mission=Mission(
            **{
                **values["mission"],
                "capability_ids": tuple(values["mission"]["capability_ids"]),
            }
        ),
        spec=MissionSpec(**values["spec"]),
        started_at=datetime.fromisoformat(values["started_at"]),
    )
    return InvestigationIntent(**values)
