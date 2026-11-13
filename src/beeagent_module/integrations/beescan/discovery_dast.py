from __future__ import annotations

import hashlib
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
    from beescan.domain.assessment_selection import AssessmentAction, ObservedEntry

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
        raw = dict(assessment["action"])
        entry = dict(raw["entry"])
        entry["evidence_refs"] = tuple(entry["evidence_refs"])
        entry["parameter_names"] = tuple(entry["parameter_names"])
        raw["entry"] = ObservedEntry(**entry)
        action = AssessmentAction(**raw)
        if (
            action.case_id != case_id
            or action.objective_id != discovery["objective_id"]
        ):
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
        intent, execution, _, report = _restore(snapshot, assessment["run_id"])
        if action.profile == "traversal-nonrecursive-v1":
            facts = snapshot.json(assessment["run_id"], "dast_evidence.json")[
                "verification"
            ]
            if facts and facts[0]["request_sha256"] != action.entry.entry_sha256:
                raise ValueError("integrated_verification_source_changed")
        if (
            intent.parent_run_id != case_id
            or intent.target.locator != state["origin"]
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
    expected_count = discovery["metrics"]["request_count"] + (
        assessment["request_count"] if assessment else 0
    )
    expected_status = (
        discovery["status"]
        if discovery["status"] in {"ERROR", "TIMEOUT", "REFUSED"}
        else assessment["status"] if assessment else "PARTIAL"
    )
    if state["status"] != expected_status or state[
        "metrics"
    ] != {**discovery["metrics"], "request_count": expected_count}:
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
