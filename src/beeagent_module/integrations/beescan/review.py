import hashlib
import json
import logging
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.runtime_context import RuntimeContext, generate_session_id
from beeagent_module.integrations.beescan.detection import _json
from beeagent_module.integrations.beescan.detection_runner import read_regular
from beeagent_module.integrations.beescan.policy import ProbePolicy
from beeagent_module.integrations.beescan.review_source import (
    load_assessment,
    open_child,
    open_directory,
)

ATTESTATION = "I collected this evidence independently of the automated assessment for this finding."


def operator_identity(settings, logger):
    registry = [
        item for item in settings["modules"]["registry"] if item["id"] == "beescan"
    ]
    if ModuleRegistry(registry, logger).get("beescan") is None:
        raise PermissionError("review_module_unavailable")
    policy = ProbePolicy.from_config(settings["beescan"]["approval"])
    if os.getuid() != os.geteuid() or os.getuid() != policy.operator_uid:
        raise PermissionError("review_operator_refused")
    return "os-uid-" + str(os.getuid())


def intake_name(value):
    if type(value) is not str or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}\.txt", value
    ):
        raise ValueError("invalid_evidence_name")
    return value


def parse_review_input(raw, assessment_run_id, finding_id):
    from beescan.domain.models import validate_text
    from beescan.domain.triage import ReviewDisposition

    if type(raw) is not bytes or not 1 <= len(raw) <= 8192:
        raise ValueError("invalid_review_input")
    data = _json(raw)
    if type(data) is not dict or set(data) != {
        "schema_version",
        "assessment_run_id",
        "finding_id",
        "disposition",
        "decision_basis",
        "independence_attestation",
        "evidence",
    }:
        raise ValueError("invalid_review_input")
    if (
        type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or data["assessment_run_id"] != assessment_run_id
        or data["finding_id"] != finding_id
        or type(data["disposition"]) is not str
    ):
        raise ValueError("invalid_review_input")
    disposition = ReviewDisposition(data["disposition"])
    validate_text(data["decision_basis"], 512)
    evidence = data["evidence"]
    if type(evidence) is not list or len(evidence) > 16:
        raise ValueError("invalid_review_evidence")
    if data["independence_attestation"] not in (None, ATTESTATION):
        raise ValueError("invalid_independence_attestation")
    if evidence and data["independence_attestation"] != ATTESTATION:
        raise ValueError("independence_attestation_required")
    if disposition is ReviewDisposition.VERIFIED and not evidence:
        raise ValueError("independent_evidence_required")
    names, digests = set(), set()
    for item in evidence:
        if type(item) is not dict or set(item) != {"name", "sha256", "media_type"}:
            raise ValueError("invalid_review_evidence")
        name = intake_name(item["name"])
        digest = item["sha256"]
        if (
            type(digest) is not str
            or not re.fullmatch("[0-9a-f]{64}", digest)
            or item["media_type"] != "text/plain"
            or name in names
            or digest in digests
        ):
            raise ValueError("invalid_review_evidence")
        names.add(name)
        digests.add(digest)
    return data


def read_intake(storage_dir, input_name, assessment_run_id, finding_id, snapshot):
    from beescan.domain.models import validate_identifier

    validate_identifier(input_name)
    if not input_name.endswith(".json"):
        raise ValueError("invalid_review_input_name")
    descriptor = open_directory(storage_dir)
    try:
        child = open_child(descriptor, "beescan-review-intake", private=True)
        os.close(descriptor)
        descriptor = child
        raw = read_regular(
            input_name, limit=8192, dir_fd=descriptor, owner_uid=os.getuid()
        )
        data = parse_review_input(raw, assessment_run_id, finding_id)
        files = {input_name: raw}
        automated = {
            hashlib.sha256(content).hexdigest() for content in snapshot.files.values()
        }
        total = 0
        for item in data["evidence"]:
            content = read_regular(
                item["name"], limit=65536, dir_fd=descriptor, owner_uid=os.getuid()
            )
            text = content.decode("utf-8")
            total += len(content)
            digest = hashlib.sha256(content).hexdigest()
            if (
                not text.strip()
                or total > 262144
                or any(ord(c) < 32 and c not in "\n\r\t" or ord(c) == 127 for c in text)
                or digest != item["sha256"]
                or digest in automated
            ):
                raise ValueError("invalid_independent_evidence")
            files[item["name"]] = content
        return data, files
    finally:
        os.close(descriptor)


def _json_text(data):
    return (
        json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        + "\n"
    )


def _write(artifacts, descriptor, name, content):
    encoded = content.encode("utf-8")
    if len(encoded) > 131072:
        raise ValueError("review_artifact_limit")
    descriptor_file = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=descriptor,
    )
    os.close(descriptor_file)
    artifacts.write_text(name, content)
    if (
        read_regular(name, limit=131072, dir_fd=descriptor, owner_uid=os.getuid())
        != encoded
    ):
        raise OSError("review_readback_failed")
    descriptor_file = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor
    )
    try:
        os.fsync(descriptor_file)
    finally:
        os.close(descriptor_file)
    return encoded


def execute_review(
    *,
    settings,
    reload_settings,
    storage_dir: Path,
    logger: logging.Logger,
    assessment_run_id,
    finding_id,
    input_name,
):
    settings = deepcopy(settings)
    status = {
        "schema_version": 1,
        "status": "refused",
        "complete": False,
        "reason": "review_refused",
    }
    descriptor = runs_fd = run_fd = None
    artifacts = None
    try:
        from beescan.capabilities.detection import DetectionCandidate
        from beescan.domain.git_exposure import GitExposureCandidate, GitExposureReview
        from beescan.domain.models import validate_identifier
        from beescan.domain.reviewed_case import ReviewedCaseInput, build_reviewed_case
        from beescan.domain.triage import FindingReview, HostReview, ReviewDisposition

        validate_identifier(assessment_run_id)
        validate_identifier(finding_id)
        reviewer = operator_identity(settings, logger)
        assessment, snapshot = load_assessment(storage_dir, assessment_run_id, settings)
        candidates: list[DetectionCandidate | GitExposureCandidate] = list(
            assessment.candidates
        )
        if assessment.exposure_result and assessment.exposure_result.candidate:
            candidates.append(assessment.exposure_result.candidate)
        selected = [
            candidate
            for candidate in candidates
            if candidate.finding.finding_id == finding_id
        ]
        if len(selected) != 1:
            raise ValueError("review_finding_unavailable")
        candidate = selected[0]
        data, intake = read_intake(
            storage_dir, input_name, assessment_run_id, finding_id, snapshot
        )
        run_id = (
            "review-"
            + hashlib.sha256(
                _json_text([assessment_run_id, finding_id]).encode()
            ).hexdigest()[:48]
        )
        status.update(
            run_id=run_id, assessment_run_id=assessment_run_id, finding_id=finding_id
        )
        root_fd = open_directory(storage_dir)
        try:
            runs_fd = open_child(root_fd, "runs")
        finally:
            os.close(root_fd)
        try:
            os.mkdir(run_id, 0o700, dir_fd=runs_fd)
        except FileExistsError:
            status.update(reason="review_already_exists_reconciliation_required")
            return status
        run_fd = open_child(runs_fd, run_id, private=True)
        os.mkdir("module-beescan", 0o700, dir_fd=run_fd)
        descriptor = open_child(run_fd, "module-beescan", private=True)
        artifacts = ArtifactAPI(
            RuntimeContext(
                run_id,
                generate_session_id(),
                "finding_review",
                "beescan",
                AuthorityLevel.DRAFT_ONLY,
            ),
            storage_dir,
            logger,
        )
        status.update(status="incomplete", reason="review_persistence_incomplete")
        _write(artifacts, descriptor, "review_status.json", _json_text(status))
        files = {}
        evidence = []
        for item in data["evidence"]:
            ref = "human-evidence-" + uuid4().hex
            name = ref + ".txt"
            content = intake[item["name"]]
            files[name] = _write(artifacts, descriptor, name, content.decode("utf-8"))
            evidence.append(
                {
                    "evidence_ref": ref,
                    "artifact": name,
                    "sha256": item["sha256"],
                    "size_bytes": len(content),
                    "media_type": "text/plain",
                    "review_id": run_id,
                    "assessment_run_id": assessment_run_id,
                    "finding_id": finding_id,
                }
            )
        host = HostReview(
            run_id,
            finding_id,
            assessment.mission.mission_id,
            assessment.target.target_id,
            reviewer,
            datetime.now(UTC),
            True,
            tuple(item["evidence_ref"] for item in evidence),
        )
        if isinstance(candidate, DetectionCandidate):
            review = FindingReview(
                candidate,
                ReviewDisposition(data["disposition"]),
                data["decision_basis"],
                host,
            )
        else:
            assert isinstance(candidate, GitExposureCandidate)
            review = GitExposureReview(
                candidate,
                ReviewDisposition(data["disposition"]),
                data["decision_basis"],
                host,
            )
        case = build_reviewed_case(ReviewedCaseInput(assessment, candidate, review))
        record = {
            "schema_version": 1,
            "assessment_run_id": assessment_run_id,
            "finding_id": finding_id,
            "review_id": run_id,
            "reviewer_id": reviewer,
            "reviewer_authenticated": True,
            "decided_at": host.decided_at.isoformat(),
            "disposition": review.disposition.value,
            "decision_basis": review.decision_basis,
            "independence_attestation": data["independence_attestation"],
            "independent_evidence_refs": list(host.independent_evidence_refs),
            "source_artifacts": [
                {
                    "run_id": child,
                    "artifact": name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                for (child, name), raw in sorted(snapshot.files.items())
            ],
        }
        outputs = {
            "review_record.json": _json_text(record),
            "evidence_manifest.json": _json_text(
                {"schema_version": 1, "review_id": run_id, "evidence": evidence}
            ),
            "case.json": case.canonical_json,
            "case.md": case.markdown,
        }
        if case.submission_draft is not None:
            outputs["submission_draft.md"] = case.submission_draft
        for name, content in outputs.items():
            files[name] = _write(artifacts, descriptor, name, content)
        terminal = {
            **status,
            "status": "ok",
            "complete": True,
            "reason": "ok",
            "disposition": review.disposition.value,
            "artifacts": {
                name: hashlib.sha256(raw).hexdigest()
                for name, raw in sorted(files.items())
            },
        }
        pending = _write(
            artifacts, descriptor, "review_status.pending.json", _json_text(terminal)
        )
        os.fsync(descriptor)
        current = reload_settings()
        if operator_identity(current, logger) != reviewer or current != settings:
            raise PermissionError("review_operator_changed")
        for name, expected in files.items():
            if (
                read_regular(
                    name, limit=131072, dir_fd=descriptor, owner_uid=os.getuid()
                )
                != expected
            ):
                raise ValueError("review_artifact_changed")
        if (
            read_intake(
                storage_dir, input_name, assessment_run_id, finding_id, snapshot
            )[1]
            != intake
        ):
            raise ValueError("review_intake_changed")
        snapshot.verify()
        if (
            read_regular(
                "review_status.pending.json",
                limit=131072,
                dir_fd=descriptor,
                owner_uid=os.getuid(),
            )
            != pending
        ):
            raise ValueError("review_terminal_changed")
        os.replace(
            "review_status.pending.json",
            "review_status.json",
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
        )
        os.fsync(descriptor)
        os.fsync(run_fd)
        os.fsync(runs_fd)
        if (
            read_regular(
                "review_status.json",
                limit=131072,
                dir_fd=descriptor,
                owner_uid=os.getuid(),
            )
            != pending
        ):
            raise ValueError("review_terminal_changed")
        for name, expected in files.items():
            if (
                read_regular(
                    name, limit=131072, dir_fd=descriptor, owner_uid=os.getuid()
                )
                != expected
            ):
                raise ValueError("review_artifact_changed")
        if (
            read_intake(
                storage_dir, input_name, assessment_run_id, finding_id, snapshot
            )[1]
            != intake
        ):
            raise ValueError("review_intake_changed")
        snapshot.verify()
        status = terminal
    except ImportError:
        status.update(reason="review_contract_unavailable")
    except PermissionError:
        status.update(reason="review_authority_or_file_refused")
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        RecursionError,
        UnicodeError,
    ):
        status.update(reason="review_input_source_or_persistence_invalid")
    finally:
        if descriptor is not None and not status["complete"]:
            status.update(status="incomplete")
            try:
                os.unlink("review_status.json", dir_fd=descriptor)
                _write(artifacts, descriptor, "review_status.json", _json_text(status))
                os.fsync(descriptor)
            except OSError:
                pass
        for opened in (descriptor, run_fd, runs_fd):
            if opened is not None:
                os.close(opened)
    logger.info(
        "BeeScan review: status=%s reason=%s", status["status"], status["reason"]
    )
    return status
