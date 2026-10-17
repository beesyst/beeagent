import json
import logging
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from subprocess import SubprocessError
from time import monotonic

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.beescan_detection import (
    AssessmentSourceBinding,
    _json,
    _persist,
    execute_approved_detection,
    load_source,
)
from beeagent_module.core.beescan_detection import (
    _current_policy as detection_policy,
)
from beeagent_module.core.beescan_detection_runner import read_regular
from beeagent_module.core.beescan_probe import (
    _current_policy as probe_policy,
)
from beeagent_module.core.beescan_probe import (
    execute_approved_probe,
)
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
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

    def current_settings():
        current = reload_settings()
        if _policies(current) != (probe, detection):
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

        if type(http_signals) is not bool:
            raise ValueError("invalid_signal_selection")
        if http_signals:
            from beescan.domain.http_signals import (
                HstsFact,
                HttpHeaderFacts,
                HttpSignalAssessment,
                NosniffFact,
            )
        probe, detection = _policies(settings)
        seconds = probe.time_budget_seconds + detection.time_budget_seconds
        if datetime.now(UTC).timestamp() + seconds > min(
            probe.expires_at.timestamp(), detection.expires_at.timestamp()
        ):
            raise PermissionError("assessment_validity_insufficient")
        deadline = monotonic() + seconds
        status["budgets"] = {
            "max_requests": probe.request_budget + detection.request_budget,
            "max_seconds": seconds,
            "max_memory_mb": max(probe.memory_mb, detection.memory_mb),
            "max_provider_output_bytes": probe.output_bytes + detection.output_bytes,
        }

        def detection_settings():
            validate_source()
            return current_settings()

        def start_child(stage, child_id):
            status[stage + "_run_id"] = child_id
            status["phase"] = stage
            _persist(artifacts, "assessment_status.json", status)

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
        current_settings()
        scope = EngagementScope(
            probe.scope_id,
            probe.project_id,
            (probe.target_id,),
            probe.scope_id,
            valid_from=max(probe.valid_from, detection.valid_from),
            expires_at=min(probe.expires_at, detection.expires_at),
            approved_methods=(probe.method, detection.method),
            max_requests=2,
            max_seconds=max(probe.time_budget_seconds, detection.time_budget_seconds),
        )
        signal_options = (
            {"signals_selected": True, "signal_assessment": signal_assessment}
            if http_signals
            else {}
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
                    ("web.probe", "web.detect.restricted"),
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
    except PermissionError:
        status.update(status="refused", complete=False, reason="authorization_refused")
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
    try:
        status["phase"] = "terminal"
        pending = _persist(artifacts, "assessment_status.pending.json", status)
        if status["complete"]:
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
