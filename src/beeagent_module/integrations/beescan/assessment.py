import json
import logging
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from subprocess import SubprocessError
from time import monotonic

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)
from beeagent_module.integrations.beescan.detection import (
    AssessmentSourceBinding,
    _json,
    _persist,
    execute_approved_detection,
    load_source,
)
from beeagent_module.integrations.beescan.detection import (
    _current_policy as detection_policy,
)
from beeagent_module.integrations.beescan.detection_runner import read_regular
from beeagent_module.integrations.beescan.probe import (
    _current_policy as probe_policy,
)
from beeagent_module.integrations.beescan.probe import (
    execute_approved_probe,
)


def _read_run(storage_dir, run_id, name):
    from beescan.domain.models import validate_identifier

    validate_identifier(run_id)
    descriptor = os.open(storage_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in ("runs", run_id, "module-beescan"):
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_fd
        return read_regular(name, limit=131072, dir_fd=descriptor)
    finally:
        os.close(descriptor)


def _expect(storage_dir, run_id, name, data):
    actual = _json(_read_run(storage_dir, run_id, name))
    if json.dumps(actual, sort_keys=True) != json.dumps(data, sort_keys=True):
        raise ValueError("assessment_artifact_changed")


def _policies(settings):
    probe, detection = probe_policy(settings), detection_policy(settings)
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
        if getattr(probe, field) != getattr(detection, field):
            raise PermissionError("assessment_identity_mismatch")
    now = datetime.now(UTC)
    probe.authorize(probe.intent(), operator_uid=os.getuid(), at=now)
    detection.authorize_operator(operator_uid=os.getuid(), at=now)
    return probe, detection


def _write_report(artifacts, name, content):
    encoded = content.encode("utf-8")
    if len(encoded) > 65536:
        raise ValueError("report_limit_exceeded")
    path = artifacts.write_text(name, content)
    path.chmod(0o600)
    if read_regular(path, limit=65536) != encoded:
        raise OSError("report_incomplete")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def execute_approved_assessment(
    *,
    settings,
    reload_settings,
    storage_dir: Path,
    logger: logging.Logger,
    http_signals=False,
    git_exposure=False,
):
    run_id = generate_run_id()
    artifacts = ArtifactAPI(
        RuntimeContext(
            run_id=run_id,
            session_id=generate_session_id(),
            case_type="assessment",
            module_id="beescan",
            authority=AuthorityLevel.EXECUTION_CAPABLE,
        ),
        storage_dir,
        logger,
    )
    artifacts.artifact_dir().chmod(0o700)
    status = {
        "schema_version": 1,
        "assessment_run_id": run_id,
        "status": "incomplete",
        "complete": False,
        "reason": "assessment_incomplete",
        "probe_run_id": None,
        "detection_run_id": None,
        "http_observation_id": None,
        "source_observation_id": None,
        "report_artifacts": [],
    }
    _persist(artifacts, "assessment_status.json", status)
    probe = detection = observation = outcome = None
    candidates = ()
    probe_state, detection_state = "incomplete", "incomplete"
    report = detection_snapshot = None
    signal_assessment = None
    exposure_policy = exposure_result = exposure_snapshot = None
    egress_session = None

    def close_egress():
        if egress_session is not None and not egress_session.closed:
            egress_session.close()

    def current_settings():
        current = reload_settings()
        if _policies(current) != (probe, detection):
            raise PermissionError("assessment_approval_changed")
        if git_exposure:
            from beeagent_module.integrations.beescan.git_exposure import current_policy

            if current_policy(current) != exposure_policy:
                raise PermissionError("assessment_approval_changed")
        if monotonic() >= deadline:
            raise TimeoutError("assessment_timeout")
        return current

    def validate_source():
        current_settings()
        if load_source(storage_dir, source_policy) != observation:
            raise PermissionError("assessment_source_changed")
        for name, raw in source_snapshot.items():
            if _read_run(storage_dir, probe_result["run_id"], name) != raw:
                raise PermissionError("assessment_source_changed")

    try:
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

        if type(http_signals) is not bool or type(git_exposure) is not bool:
            raise ValueError("invalid_signal_selection")
        if git_exposure:
            from beescan.domain.git_exposure import GitExposureResult

            if (
                GitExposureResult is None
                or "exposure_selected" not in AssessmentInput.__dataclass_fields__
            ):
                raise ImportError("Git exposure contract unavailable")
        if http_signals:
            from beescan.domain.http_signals import (
                HstsFact,
                HttpHeaderFacts,
                HttpSignalAssessment,
                NosniffFact,
            )
        probe, detection = _policies(settings)
        policies = [probe, detection]
        if git_exposure:
            from beeagent_module.integrations.beescan.git_exposure import current_policy

            exposure_policy = current_policy(settings)
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
                if getattr(probe, field) != getattr(exposure_policy, field):
                    raise PermissionError("assessment_identity_mismatch")
            policies.append(exposure_policy)
            status["exposure_run_id"] = None
        seconds = probe.time_budget_seconds + detection.time_budget_seconds
        if git_exposure:
            if exposure_policy is None:
                raise PermissionError("git_exposure_disabled")
            seconds += exposure_policy.time_budget_seconds
            if seconds > 60:
                raise PermissionError("assessment_budget_exceeded")
        if datetime.now(UTC).timestamp() + seconds > min(
            policy.expires_at.timestamp() for policy in policies
        ):
            raise PermissionError("assessment_validity_insufficient")
        deadline = monotonic() + seconds
        status["budgets"] = {
            "max_requests": sum(policy.request_budget for policy in policies),
            "max_seconds": seconds,
            "max_memory_mb": max(policy.memory_mb for policy in policies),
            "max_provider_output_bytes": sum(
                policy.output_bytes for policy in policies
            ),
        }

        def detection_settings():
            validate_source()
            return current_settings()

        def start_child(stage, child_id):
            status[stage + "_run_id"] = child_id
            status["phase"] = stage
            _persist(artifacts, "assessment_status.json", status)

        from beeagent_module.integrations.beescan.egress import (
            MANAGED_NET,
            ManagedEgress,
        )

        if probe.network_namespace == MANAGED_NET:
            current_settings()
            from beeagent_module.integrations.beescan.http_runner import (
                verify_resolution,
            )

            verify_resolution(probe)
            egress_session = ManagedEgress(
                probe, artifacts=artifacts, assessment_run_id=run_id, seconds=seconds
            )
            status["egress_artifact"] = "egress_lifecycle.json"
            egress_session.start()
            current_settings()
        probe_records = []
        probe_result = execute_approved_probe(
            settings=current_settings(),
            reload_settings=current_settings,
            storage_dir=storage_dir,
            logger=logger,
            on_complete=probe_records.append,
            on_started=lambda child_id: start_child("probe", child_id),
        )
        status["probe_run_id"] = probe_result["run_id"]
        _expect(
            storage_dir, probe_result["run_id"], "http_probe_status.json", probe_result
        )
        if probe_result["complete"] is not True or probe_result["status"] != "ok":
            probe_state = probe_result["status"]
            if probe_state not in {"refused", "timeout", "error", "incomplete"}:
                probe_state = "error"
            status.update(status=probe_state, reason="probe_did_not_complete")
        else:
            if len(probe_records) != 1:
                raise ValueError("assessment_probe_incomplete")
            observation = probe_records[0]
            if observation.facts.provenance.run_id != probe_result["run_id"]:
                raise ValueError("assessment_probe_provenance_mismatch")
            source_policy = replace(
                detection,
                source_run_id=probe_result["run_id"],
                source_observation_id=observation.observation_id,
            )
            if load_source(storage_dir, source_policy) != observation:
                raise PermissionError("assessment_source_changed")
            source_snapshot = {
                name: _read_run(storage_dir, probe_result["run_id"], name)
                for name in (
                    "http_observation.json",
                    "http_probe_status.json",
                    *(ref + ".json" for ref in observation.evidence_refs),
                )
            }
            if (
                observation.facts.provenance.provider_id != probe.intent().provider_id
                or observation.facts.provenance.provider_version
                != probe.provider_version
            ):
                raise ValueError("assessment_probe_provenance_mismatch")
            probe_state = "complete"
            status.update(
                http_observation_id=observation.observation_id,
                source_observation_id=observation.observation_id,
            )
            validate_source()
            if monotonic() + detection.time_budget_seconds > deadline:
                raise TimeoutError("assessment_timeout")
            records = []
            detection_result = execute_approved_detection(
                settings=current_settings(),
                reload_settings=detection_settings,
                storage_dir=storage_dir,
                logger=logger,
                assessment_source=AssessmentSourceBinding(detection, observation),
                http_signals=http_signals,
                on_complete=lambda outcome, candidates, evidence: records.append(
                    (outcome, candidates, evidence)
                ),
                on_started=lambda child_id: start_child("detection", child_id),
            )
            status["detection_run_id"] = detection_result["run_id"]
            validate_source()
            _expect(
                storage_dir,
                detection_result["run_id"],
                "detection_status.json",
                detection_result,
            )
            if detection_result["complete"] is True and records:
                outcome, candidates, evidence_record = records[0]
                detection_snapshot = {}
                for name, data in (
                    (
                        "detection_intent.json",
                        {"schema_version": 1, **asdict(outcome.intent)},
                    ),
                    (
                        "detection_outcome.json",
                        {"schema_version": 1, **asdict(outcome)},
                    ),
                    (
                        "detection_candidates.json",
                        {
                            "schema_version": 1,
                            "candidates": [
                                asdict(candidate) for candidate in candidates
                            ],
                        },
                    ),
                ):
                    _expect(storage_dir, detection_result["run_id"], name, data)
                    detection_snapshot[name] = _read_run(
                        storage_dir, detection_result["run_id"], name
                    )
                for ref in outcome.evidence_refs:
                    _expect(
                        storage_dir,
                        detection_result["run_id"],
                        ref + ".json",
                        evidence_record,
                    )
                    detection_snapshot[ref + ".json"] = _read_run(
                        storage_dir, detection_result["run_id"], ref + ".json"
                    )
                detection_snapshot["detection_status.json"] = _read_run(
                    storage_dir, detection_result["run_id"], "detection_status.json"
                )
                if http_signals:
                    from beescan.domain.http_signals import (
                        HstsFact,
                        HttpHeaderFacts,
                        HttpSignalAssessment,
                        NosniffFact,
                    )

                    header = evidence_record["capture"]["header_facts"]
                    signal_assessment = HttpSignalAssessment(
                        outcome,
                        HttpHeaderFacts(
                            outcome.intent.mission_id,
                            outcome.intent.target_id,
                            outcome.intent.origin,
                            observation.observation_id,
                            outcome.provenance,
                            outcome.evidence_refs,
                            header["complete"],
                            NosniffFact(header["nosniff"]),
                            HstsFact(header["hsts"]),
                            header["hsts_max_age"],
                        ),
                    )
                detection_state = "complete"
                status.update(status="ok", reason="ok")
            else:
                detection_state = detection_result["status"]
                if detection_state not in {
                    "refused",
                    "timeout",
                    "error",
                    "malformed",
                    "incomplete",
                }:
                    detection_state = "error"
                status.update(
                    status=detection_state, reason="detection_did_not_complete"
                )
        if git_exposure and observation is not None and detection_state == "complete":
            from beeagent_module.integrations.beescan.git_exposure import (
                current_policy,
                execute_git_exposure,
            )

            validate_source()
            if exposure_policy is None:
                raise PermissionError("git_exposure_disabled")
            if monotonic() + exposure_policy.time_budget_seconds > deadline:
                raise TimeoutError("assessment_timeout")
            exposure_status, exposure_result = execute_git_exposure(
                policy=exposure_policy,
                reload_policy=lambda: current_policy(current_settings()),
                observation=observation,
                assessment_run_id=run_id,
                storage_dir=storage_dir,
                logger=logger,
                validate_source=validate_source,
                on_started=lambda child_id: start_child("exposure", child_id),
            )
            status["exposure_run_id"] = exposure_status["run_id"]
            if exposure_result.facts.provenance.run_id != status["exposure_run_id"]:
                raise ValueError("exposure_provenance_mismatch")
            exposure_snapshot = {}
            for name, data in (
                ("git_exposure_status.json", exposure_status),
                (
                    "git_exposure_result.json",
                    {"schema_version": 1, **asdict(exposure_result)},
                ),
                *(
                    (
                        ref + ".json",
                        {"schema_version": 1, **asdict(exposure_result.facts)},
                    )
                    for ref in exposure_result.facts.evidence_refs
                ),
            ):
                _expect(storage_dir, status["exposure_run_id"], name, data)
                exposure_snapshot[name] = _read_run(
                    storage_dir, status["exposure_run_id"], name
                )
            if not exposure_status["complete"]:
                status.update(
                    status=exposure_status["status"], reason="exposure_did_not_complete"
                )
        close_egress()
        current_settings()
        scope = EngagementScope(
            probe.scope_id,
            probe.project_id,
            (probe.target_id,),
            probe.scope_id,
            valid_from=max(policy.valid_from for policy in policies),
            expires_at=min(policy.expires_at for policy in policies),
            approved_methods=tuple(policy.method for policy in policies),
            max_requests=len(policies),
            max_seconds=max(policy.time_budget_seconds for policy in policies),
        )
        signal_options = (
            {"signals_selected": True, "signal_assessment": signal_assessment}
            if http_signals
            else {}
        )
        if git_exposure:
            signal_options.update(
                exposure_selected=True, exposure_result=exposure_result
            )
        report = build_assessment_report(
            AssessmentInput(
                run_id,
                Project(probe.project_id, "Approved assessment"),
                scope,
                Mission(
                    probe.mission_id,
                    probe.project_id,
                    probe.scope_id,
                    ("web.probe", "web.detect.restricted", "web.exposure.git_head")
                    if git_exposure
                    else ("web.probe", "web.detect.restricted"),
                ),
                Target(probe.target_id, probe.project_id, TargetKind.URL, probe.origin),
                StepState(probe_state),
                StepState(detection_state),
                status["probe_run_id"],
                status["detection_run_id"],
                observation,
                outcome,
                candidates,
                **signal_options,
            )
        )
        _write_report(artifacts, "report.md", report.markdown)
        _write_report(artifacts, "report.json", report.canonical_json)
        status.update(
            complete=report.data["complete"],
            result=report.data["result"],
            report_artifacts=["report.md", "report.json"],
        )
    except PermissionError as error:
        from beeagent_module.integrations.beescan.egress import EGRESS_REASONS

        reason = str(error) if str(error) in EGRESS_REASONS else "authorization_refused"
        status.update(status="refused", complete=False, reason=reason)
    except TimeoutError:
        status.update(status="timeout", complete=False, reason="assessment_timeout")
    except ImportError:
        status.update(
            status="refused", complete=False, reason="reporting_contract_unavailable"
        )
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        RecursionError,
        SubprocessError,
    ):
        status.update(
            status="incomplete",
            complete=False,
            reason="execution_or_artifact_incomplete",
        )
    finally:
        try:
            close_egress()
        except OSError, RuntimeError, SubprocessError:
            status.update(
                status="incomplete", complete=False, reason="egress_cleanup_unverified"
            )
    try:
        status["phase"] = "terminal"
        pending = _persist(artifacts, "assessment_status.pending.json", status)
        if status["complete"]:
            if egress_session is not None:
                if (
                    not egress_session.closed
                    or not egress_session.evidence["cleanup_verified"]
                ):
                    raise ValueError("egress_cleanup_unverified")
                _expect(
                    storage_dir,
                    run_id,
                    "egress_lifecycle.json",
                    egress_session.evidence,
                )
            if (
                report is None
                or observation is None
                or outcome is None
                or not detection_snapshot
            ):
                raise ValueError("assessment_incomplete")
            current_settings()
            validate_source()
            for name, raw in detection_snapshot.items():
                if _read_run(storage_dir, status["detection_run_id"], name) != raw:
                    raise ValueError("assessment_artifact_changed")
            if git_exposure:
                if (
                    not exposure_snapshot
                    or exposure_result is None
                    or not exposure_result.facts.complete
                ):
                    raise ValueError("assessment_exposure_incomplete")
                for name, raw in exposure_snapshot.items():
                    if _read_run(storage_dir, status["exposure_run_id"], name) != raw:
                        raise ValueError("assessment_artifact_changed")
            for name, content in (
                ("report.md", report.markdown),
                ("report.json", report.canonical_json),
            ):
                if read_regular(
                    artifacts.artifact_dir() / name, limit=65536
                ) != content.encode("utf-8"):
                    raise OSError("report_incomplete")
        os.replace(pending, artifacts.artifact_dir() / "assessment_status.json")
        descriptor = os.open(artifacts.artifact_dir(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        RecursionError,
    ) as exc:
        status.update(
            status="incomplete", complete=False, reason="terminal_persistence_failed"
        )
        if isinstance(exc, PermissionError):
            status.update(status="refused", reason="authorization_refused")
        elif isinstance(exc, TimeoutError):
            status.update(status="timeout", reason="assessment_timeout")
        try:
            (artifacts.artifact_dir() / "assessment_status.json").unlink(
                missing_ok=True
            )
            _persist(artifacts, "assessment_status.json", status)
        except OSError:
            pass
    logger.info("BeeScan assessment: run_id=%s status=%s", run_id, status["status"])
    return status
