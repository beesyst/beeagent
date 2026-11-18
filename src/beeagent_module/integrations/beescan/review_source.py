import json
import os
import stat
from dataclasses import asdict, replace
from pathlib import Path

from beesdk.capabilities import CapabilityResult, CapabilityStatus
from beesdk.modules import AuthorityLevel

from beeagent_module.integrations.beescan.detection import _json
from beeagent_module.integrations.beescan.detection_policy import DetectionPolicy
from beeagent_module.integrations.beescan.detection_runner import (
    parse_capture,
    read_regular,
)
from beeagent_module.integrations.beescan.git_exposure import GitExposurePolicy
from beeagent_module.integrations.beescan.policy import ProbePolicy


def open_directory(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("invalid_storage_path")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_fd
        check_directory(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def check_directory(descriptor, *, private=False):
    info = os.fstat(descriptor)
    if info.st_uid != os.getuid() or info.st_mode & (0o077 if private else 0o022):
        raise PermissionError("unsafe_review_directory")


def open_child(descriptor, name, *, private=False):
    child = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=descriptor,
    )
    try:
        check_directory(child, private=private)
        return child
    except BaseException:
        os.close(child)
        raise


class AssessmentSnapshot:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
        self.files = {}

    def read(self, run_id, name):
        from beescan.domain.models import validate_identifier

        validate_identifier(run_id)
        if (
            type(name) is not str
            or len(name) > 80
            or "/" in name
            or "\\" in name
            or name in {".", ".."}
        ):
            raise ValueError("invalid_artifact_name")
        descriptor = open_directory(self.storage_dir)
        try:
            for part in ("runs", run_id, "module-beescan"):
                child = open_child(descriptor, part)
                os.close(descriptor)
                descriptor = child
            try:
                raw = read_regular(
                    name, limit=131072, dir_fd=descriptor, owner_uid=os.getuid()
                )
            except PermissionError as error:
                if name not in {
                    "investigation_status.json",
                    "investigation_steps.json",
                }:
                    raise
                if str(error) == "invalid_owned_asset":
                    info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_uid != os.getuid()
                        or info.st_mode & 0o077
                        or info.st_nlink != 1
                    ):
                        raise
                elif str(error) != "owned_asset_changed":
                    raise
                raise ValueError("assessment_source_changed") from None
        finally:
            os.close(descriptor)
        key = (run_id, name)
        if key in self.files and self.files[key] != raw:
            raise ValueError("assessment_source_changed")
        self.files[key] = raw
        return raw

    def json(self, run_id, name):
        data = _json(self.read(run_id, name))
        if type(data) is not dict:
            raise ValueError("invalid_assessment_artifact")
        return data

    def verify(self):
        for run_id, name in tuple(self.files):
            self.read(run_id, name)


def same(actual, expected):
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError("inconsistent_assessment_artifact")


def contains(actual, expected):
    if type(actual) is not dict:
        raise ValueError("invalid_assessment_artifact")
    same({key: actual[key] for key in expected}, expected)


def load_assessment(storage_dir, assessment_run_id, settings):
    from beescan.capabilities.detection import (
        correlate_detections,
        normalize_detection,
    )
    from beescan.capabilities.http_probe import (
        HostProvenance,
        HttpFacts,
        HttpObservation,
    )
    from beescan.domain.git_exposure import (
        GitExposureIntent,
        GitExposureResult,
        GitExposureState,
        GitHeadFacts,
    )
    from beescan.domain.http_signals import (
        HstsFact,
        HttpHeaderFacts,
        HttpSignalAssessment,
        NosniffFact,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )
    from beescan.domain.reporting import (
        AssessmentInput,
        StepState,
        build_assessment_report,
    )

    snapshot = AssessmentSnapshot(storage_dir)
    parent = snapshot.json(assessment_run_id, "assessment_status.json")
    contains(
        parent,
        {
            "schema_version": 1,
            "assessment_run_id": assessment_run_id,
            "complete": True,
            "status": "ok",
            "reason": "ok",
            "phase": "terminal",
            "report_artifacts": ["report.md", "report.json"],
        },
    )
    report = snapshot.json(assessment_run_id, "report.json")
    config = settings["beescan"]
    probe = ProbePolicy.from_config(config["approval"])
    from beeagent_module.integrations.beescan.egress import (
        MANAGED_NET,
        PASTA_SHA256,
        PASTA_VERSION,
    )

    if probe.network_namespace == MANAGED_NET:
        contains(parent, {"egress_artifact": "egress_lifecycle.json"})
        contains(
            snapshot.json(assessment_run_id, "egress_lifecycle.json"),
            {
                "schema_version": 1,
                "assessment_run_id": assessment_run_id,
                "backend": "pasta",
                "backend_version": PASTA_VERSION,
                "backend_sha256": PASTA_SHA256,
                "state": "closed",
                "enforcement_verified": True,
                "cleanup_verified": True,
            },
        )
    detection = DetectionPolicy.from_config(config["detection_approval"])
    policies = [probe, detection]
    exposure_selected = "exposure" in report
    if exposure_selected:
        policies.append(GitExposurePolicy.from_config(config["git_exposure_approval"]))
    for policy in policies:
        if not policy.approved or policy.excluded:
            raise ValueError("historical_approval_unavailable")
        for field in (
            "operator_uid",
            "project_id",
            "scope_id",
            "mission_id",
            "target_id",
            "origin",
            "connected_ip",
            "allow_private_lab",
            "network_namespace",
            "user_namespace",
        ):
            if getattr(policy, field) != getattr(probe, field):
                raise ValueError("historical_approval_mismatch")
    contains(
        parent,
        {
            "budgets": {
                "max_requests": sum(policy.request_budget for policy in policies),
                "max_seconds": sum(policy.time_budget_seconds for policy in policies),
                "max_memory_mb": max(policy.memory_mb for policy in policies),
                "max_provider_output_bytes": sum(
                    policy.output_bytes for policy in policies
                ),
            }
        },
    )
    probe_run, detection_run = parent["probe_run_id"], parent["detection_run_id"]
    data = snapshot.json(probe_run, "http_observation.json")
    same(data.pop("schema_version"), 1)
    fields = data["facts"]
    if (
        type(fields["evidence_refs"]) is not list
        or type(data["evidence_refs"]) is not list
    ):
        raise ValueError("invalid_probe_evidence")
    fields["provenance"] = HostProvenance(**fields["provenance"])
    fields["evidence_refs"] = tuple(fields["evidence_refs"])
    data["facts"] = HttpFacts(**fields)
    data["evidence_refs"] = tuple(data["evidence_refs"])
    observation = HttpObservation(**data)
    if observation.facts.provenance != HostProvenance(
        probe_run, probe.intent().provider_id, probe.provider_version
    ):
        raise ValueError("invalid_probe_provider")
    contains(
        snapshot.json(probe_run, "http_probe_status.json"),
        {
            "schema_version": 1,
            "run_id": probe_run,
            "complete": True,
            "status": "ok",
            "reason": "ok",
            "project_id": probe.project_id,
            "scope_id": probe.scope_id,
            "mission_id": probe.mission_id,
            "target_id": probe.target_id,
            "provenance": asdict(observation.facts.provenance),
            "evidence_refs": list(observation.evidence_refs),
        },
    )
    contains(
        parent,
        {
            "http_observation_id": observation.observation_id,
            "source_observation_id": observation.observation_id,
        },
    )
    for ref in observation.evidence_refs:
        same(
            snapshot.json(probe_run, ref + ".json"),
            {"schema_version": 1, **asdict(observation.facts)},
        )
    detection = replace(
        detection,
        source_run_id=probe_run,
        source_observation_id=observation.observation_id,
    )
    from beescan.capabilities.detection import DetectionIntent, DetectionTemplate

    intent = DetectionIntent(
        detection.mission_id,
        detection.target_id,
        detection.origin,
        observation,
        detection.request_budget,
        detection.time_budget_seconds,
        detection.provider_version,
        DetectionTemplate(
            detection.template_id, detection.template_version, detection.template_sha256
        ),
    )
    same(
        snapshot.json(detection_run, "detection_intent.json"),
        {"schema_version": 1, **asdict(intent)},
    )
    terminal = snapshot.json(detection_run, "detection_status.json")
    refs = terminal["evidence_refs"]
    if type(refs) is not list or not 1 <= len(refs) <= 16:
        raise ValueError("invalid_assessment_evidence")
    provenance = HostProvenance(
        detection_run, intent.provider_id, intent.provider_version
    )
    evidence_record = None
    for ref in refs:
        from beescan.domain.models import validate_identifier

        validate_identifier(ref)
        record = snapshot.json(detection_run, ref + ".json")
        if evidence_record is not None:
            same(record, evidence_record)
        evidence_record = record
    if evidence_record is None:
        raise ValueError("missing_assessment_evidence")
    if set(evidence_record) != {
        "schema_version",
        "facts",
        "capture",
        "provenance",
        "profile",
        "source_run_id",
    }:
        raise ValueError("invalid_detection_evidence")
    contains(
        evidence_record,
        {
            "schema_version": 1,
            "provenance": asdict(provenance),
            "profile": intent.profile,
            "source_run_id": probe_run,
        },
    )
    signals_selected = "signal_checks" in report
    capture = parse_capture(
        json.dumps(evidence_record["capture"]).encode(),
        detection,
        http_signals=signals_selected,
    )
    outcome = normalize_detection(
        intent,
        CapabilityResult(
            intent.capability_name,
            CapabilityStatus.OK,
            AuthorityLevel.EXECUTION_CAPABLE,
            "Completed",
            {"evidence_refs": refs},
        ),
        provenance=provenance,
        facts=evidence_record["facts"],
    )
    if outcome.status.value not in {"matched", "no_match"} or bool(outcome.matches) != (
        capture["marker_header"] == "present"
    ):
        raise ValueError("invalid_detection_completion")
    contains(
        terminal,
        {
            "schema_version": 1,
            "run_id": detection_run,
            "complete": True,
            "status": outcome.status.value,
            "reason": "ok",
            "source_run_id": probe_run,
            "source_observation_id": observation.observation_id,
            "provenance": asdict(provenance),
            "evidence_refs": list(outcome.evidence_refs),
        },
    )
    candidates = correlate_detections((outcome,))
    same(
        snapshot.json(detection_run, "detection_outcome.json"),
        {"schema_version": 1, **asdict(outcome)},
    )
    same(
        snapshot.json(detection_run, "detection_candidates.json"),
        {
            "schema_version": 1,
            "candidates": [asdict(candidate) for candidate in candidates],
        },
    )
    signals = None
    if signals_selected:
        header = capture["header_facts"]
        signals = HttpSignalAssessment(
            outcome,
            HttpHeaderFacts(
                intent.mission_id,
                intent.target_id,
                intent.origin,
                observation.observation_id,
                provenance,
                outcome.evidence_refs,
                header["complete"],
                NosniffFact(header["nosniff"]),
                HstsFact(header["hsts"]),
                header["hsts_max_age"],
            ),
        )
    exposure = None
    if exposure_selected:
        policy = policies[2]
        child = parent["exposure_run_id"]
        raw = snapshot.json(child, "git_exposure_result.json")
        if type(raw["facts"]) is not dict:
            raise ValueError("invalid_exposure_facts")
        facts = raw["facts"].copy()
        facts["provenance"] = HostProvenance(**facts["provenance"])
        facts["evidence_refs"] = tuple(facts["evidence_refs"])
        facts["execution_state"] = GitExposureState(facts["execution_state"])
        exposure = GitExposureResult(
            GitExposureIntent(
                policy.mission_id,
                policy.target_id,
                policy.origin,
                observation,
                1,
                policy.time_budget_seconds,
                "host-git-head",
                "1",
            ),
            GitHeadFacts(**facts),
        )
        if exposure.facts.provenance != HostProvenance(child, "host-git-head", "1"):
            raise ValueError("invalid_exposure_child")
        same(raw, {"schema_version": 1, **asdict(exposure)})
        contains(
            snapshot.json(child, "git_exposure_status.json"),
            {
                "schema_version": 1,
                "run_id": child,
                "assessment_run_id": assessment_run_id,
                "status": exposure.facts.execution_state.value,
                "complete": True,
                "evidence_refs": list(exposure.facts.evidence_refs),
                "source_run_id": probe_run,
                "source_observation_id": observation.observation_id,
            },
        )
        for ref in exposure.facts.evidence_refs:
            same(
                snapshot.json(child, ref + ".json"),
                {"schema_version": 1, **asdict(exposure.facts)},
            )
    assessment = AssessmentInput(
        assessment_run_id,
        Project(probe.project_id, "Approved assessment"),
        EngagementScope(
            probe.scope_id,
            probe.project_id,
            (probe.target_id,),
            probe.scope_id,
            valid_from=max(policy.valid_from for policy in policies),
            expires_at=min(policy.expires_at for policy in policies),
            approved_methods=tuple(policy.method for policy in policies),
            max_requests=len(policies),
            max_seconds=max(policy.time_budget_seconds for policy in policies),
        ),
        Mission(
            probe.mission_id,
            probe.project_id,
            probe.scope_id,
            ("web.probe", "web.detect.restricted", "web.exposure.git_head")
            if exposure_selected
            else ("web.probe", "web.detect.restricted"),
        ),
        Target(probe.target_id, probe.project_id, TargetKind.URL, probe.origin),
        StepState.COMPLETE,
        StepState.COMPLETE,
        probe_run,
        detection_run,
        observation,
        outcome,
        candidates,
        signals_selected=signals_selected,
        signal_assessment=signals,
        exposure_selected=exposure_selected,
        exposure_result=exposure,
    )
    expected = build_assessment_report(assessment)
    if not expected.data["complete"]:
        raise ValueError("assessment_incomplete")
    same(report, expected.data)
    if (
        snapshot.read(assessment_run_id, "report.json")
        != expected.canonical_json.encode()
        or snapshot.read(assessment_run_id, "report.md") != expected.markdown.encode()
    ):
        raise ValueError("assessment_report_changed")
    contains(parent, {"result": expected.data["result"]})
    snapshot.verify()
    return assessment, snapshot


def load_web_dast(service, settings, case_id, finding_id, actor):
    from beescan.domain.assessment_selection import AssessmentAction, ObservedEntry
    from beescan.domain.reviewed_case import DastReviewInput

    from beeagent_module.integrations.beescan.case_state import load_case
    from beeagent_module.integrations.beescan.dast import _restore
    from beeagent_module.integrations.beescan.web import _read_owned

    binding = _read_owned(service.storage, settings, case_id, actor)
    if binding["case_id"] != case_id:
        raise PermissionError("exact_web_case_required")
    state, snapshot = load_case(service.storage, case_id)
    if state["schema_version"] == 7:
        from beescan.domain.access_control import (
            AccessReviewInput,
            AdministrativeEvidence,
            AdministrativeExecution,
            AdministrativeIntent,
            AdministrativeReviewInput,
            evaluate_access,
        )
        from beescan.domain.general_investigation import GeneralCase
        from beescan.domain.reviewed_case import DisclosureReviewInput

        from beeagent_module.integrations.beescan.access_control import restore
        from beeagent_module.integrations.beescan.discovery_dast import (
            restore_general_intent,
            restore_surface,
        )

        if snapshot.json(case_id, "web_receipt.json") != service._receipt(
            snapshot, settings
        ):
            raise PermissionError("web_source_authentication_failed")
        if finding_id not in {item["finding_id"] for item in state["findings"]}:
            raise ValueError("original_multifamily_candidate_required")
        for record in state["assessments"]:
            if record["pending"] or record.get("deferred") is not None:
                continue
            intent, execution, outcome, report = _restore(snapshot, record["run_id"])
            if finding_id not in {
                item["finding_id"] for item in report.data["findings"]
            }:
                continue
            raw = dict(record["action"])
            entry = raw["entry"]
            action = AssessmentAction(
                **{
                    **raw,
                    "entry": ObservedEntry(
                        **{
                            **entry,
                            "parameter_names": tuple(entry["parameter_names"]),
                            "evidence_refs": tuple(entry["evidence_refs"]),
                        }
                    ),
                }
            )
            return DastReviewInput(
                intent, execution, outcome, finding_id, action
            ), snapshot
        for record in state["access"]:
            if record["pending"] or record.get("deferred") is not None:
                continue
            child = snapshot.json(record["run_id"], "case.json")["state"]
            if child.get("schema_version") == 8:
                comparison = snapshot.json(
                    record["run_id"], "administrative_comparison.json"
                )
                raw_intent = dict(comparison["intent"])
                raw_execution = dict(comparison["execution"])
                from datetime import datetime

                from beescan.domain.models import (
                    EngagementScope,
                    Mission,
                    Project,
                    Target,
                    TargetKind,
                )

                scope = raw_intent["scope"]
                raw_intent.update(
                    project=Project(**raw_intent["project"]),
                    scope=EngagementScope(
                        **{
                            **scope,
                            "target_ids": tuple(scope["target_ids"]),
                            "excluded_target_ids": tuple(scope["excluded_target_ids"]),
                            "approved_methods": tuple(scope["approved_methods"]),
                            "valid_from": datetime.fromisoformat(scope["valid_from"]),
                            "expires_at": datetime.fromisoformat(scope["expires_at"]),
                        }
                    ),
                    mission=Mission(
                        **{
                            **raw_intent["mission"],
                            "capability_ids": tuple(
                                raw_intent["mission"]["capability_ids"]
                            ),
                        }
                    ),
                    target=Target(
                        **{
                            **raw_intent["target"],
                            "kind": TargetKind(raw_intent["target"]["kind"]),
                        }
                    ),
                )
                intent = AdministrativeIntent(**raw_intent)
                raw_execution["evidence"] = tuple(
                    AdministrativeEvidence(
                        **{
                            **item,
                            "captured_at": datetime.fromisoformat(item["captured_at"]),
                        }
                    )
                    for item in raw_execution["evidence"]
                )
                raw_execution["ended_at"] = datetime.fromisoformat(
                    raw_execution["ended_at"]
                )
                execution = AdministrativeExecution(**raw_execution)
                if (
                    child["parent_case_id"] != case_id
                    or child["action_id"] != record["action_id"]
                    or child["profile_id"] != intent.profile_id
                    or child["request_count"] != 2
                ):
                    raise ValueError("administrative_child_changed")
                from beescan.domain.access_control import evaluate_administrative_access

                if finding_id in {
                    item.finding_id
                    for item in evaluate_administrative_access(
                        intent, execution
                    ).findings
                }:
                    return AdministrativeReviewInput(
                        intent, execution, finding_id, case_id
                    ), snapshot
                continue
            for name in child["comparisons"]:
                intent, execution = restore(snapshot.json(record["run_id"], name))
                if finding_id in {
                    item.finding_id
                    for item in evaluate_access(intent, execution).findings
                }:
                    return AccessReviewInput(
                        intent, execution, finding_id, case_id
                    ), snapshot
        intent = restore_general_intent(state["context"])
        surfaces = tuple(
            restore_surface(item["surface"]) for item in state["discovery"]["entries"]
        )
        case = GeneralCase(
            case_id,
            intent,
            state["discovery"]["objective_id"],
            state["discovery"]["requested_field"],
            surfaces,
        )
        from beescan.domain.assessment_selection import disclosure_finding

        for surface in surfaces:
            if (
                surface.source_disclosure
                and not surface.ambiguous
                and disclosure_finding(case_id, surface).finding_id == finding_id
            ):
                return DisclosureReviewInput(
                    case, surface, finding_id, intent.started_at
                ), snapshot
        raise ValueError("original_multifamily_candidate_required")
    if state["schema_version"] in {5, 6}:
        from beescan.domain.access_control import AccessReviewInput

        from beeagent_module.integrations.beescan.access_control import restore

        if snapshot.json(case_id, "web_receipt.json") != service._receipt(
            snapshot, settings
        ):
            raise PermissionError("web_source_authentication_failed")
        names = (
            state["comparisons"]
            if state["schema_version"] == 6
            else ["access_control.json"]
        )
        sources = [restore(snapshot.json(case_id, name)) for name in names]
        from beescan.domain.access_control import evaluate_access

        selected = [
            (i, e)
            for i, e in sources
            if any(f.finding_id == finding_id for f in evaluate_access(i, e).findings)
        ]
        if len(selected) != 1:
            raise ValueError("original_access_candidate_required")
        intent, execution = selected[0]
        source = AccessReviewInput(intent, execution, finding_id)
        snapshot.verify()
        return source, snapshot
    if (
        state["schema_version"] not in {3, 4}
        or state["status"] != "CANDIDATE"
        or state["pending"] is not False
    ):
        raise ValueError("completed_dast_candidate_required")
    if snapshot.json(case_id, "web_receipt.json") != service._receipt(
        snapshot, settings
    ):
        raise PermissionError("web_source_authentication_failed")
    action = None
    if state["schema_version"] == 4:
        raw = dict(state["assessment"]["action"])
        entry = dict(raw["entry"])
        for key in ("parameter_names", "evidence_refs"):
            entry[key] = tuple(entry[key])
        action = AssessmentAction(**{**raw, "entry": ObservedEntry(**entry)})
        child = state["assessment"]["run_id"]
    else:
        child = state["segments"][-1]
    intent, execution, outcome, _ = _restore(snapshot, child)
    source = DastReviewInput(intent, execution, outcome, finding_id, action)
    snapshot.verify()
    return source, snapshot
