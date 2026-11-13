import hashlib
import hmac
import json
import logging
import os
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, overload
from uuid import uuid4

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.runtime_context import RuntimeContext, generate_session_id
from beeagent_module.integrations.beescan.detection import _json
from beeagent_module.integrations.beescan.detection_runner import read_regular
from beeagent_module.integrations.beescan.policy import ProbePolicy
from beeagent_module.integrations.beescan.review_source import (
    AssessmentSnapshot,
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


def _web_review_id(case_id, finding_id):
    return (
        "wr-"
        + hashlib.sha256(_json_text([case_id, finding_id]).encode()).hexdigest()[:48]
    )


def _web_report_id(review_id, revision):
    return (
        "vr-"
        + hashlib.sha256(_json_text([review_id, revision]).encode()).hexdigest()[:48]
    )


def _web_authority(service, settings, actor, *, mutate=False):
    from beeagent_module.integrations.beescan.web import principal

    identity = principal(settings, actor, execute=mutate)
    if mutate:
        config = settings["beescan"]["investigation"]
        if (
            config.get("web", {}).get("enabled") is not True
            or identity not in config["web"]["principal_ids"]
            or not any(
                item.get("id") == "beescan" and item.get("enabled") is True
                for item in settings["modules"]["registry"]
            )
        ):
            raise PermissionError("web_review_authority_required")
    if service.reload_settings() != settings:
        raise PermissionError("web_review_authority_changed")
    return identity


def _source_hashes(snapshot):
    return {
        run + "/" + name: hashlib.sha256(raw).hexdigest()
        for (run, name), raw in sorted(snapshot.files.items())
    }


def _safe_web_text(value, limit):
    from beescan.domain.models import validate_text

    validate_text(value, limit)
    if len(value.encode("utf-8")) > limit or re.search(
        r"authorization\s*:|cookie\s*:|bearer\s+|password\s*[:=]|"
        r"(?:token|secret|api[_-]?key)\s*[:=]|-----BEGIN .*PRIVATE KEY",
        value,
        re.IGNORECASE,
    ):
        raise ValueError("unsafe_review_text")
    return value


def _publish_web_package(service, settings, actor, run_id, binding, outputs, snapshot):
    from beeagent_module.integrations.beescan.web import _sign

    descriptor = runs = run = None
    try:
        root = open_directory(service.storage)
        try:
            runs = open_child(root, "runs")
        finally:
            os.close(root)
        os.mkdir(run_id, 0o700, dir_fd=runs)
        run = open_child(runs, run_id, private=True)
        os.mkdir("module-beescan", 0o700, dir_fd=run)
        descriptor = open_child(run, "module-beescan", private=True)
        api = ArtifactAPI(
            RuntimeContext(
                run_id,
                generate_session_id(),
                "finding_review",
                "beescan",
                AuthorityLevel.DRAFT_ONLY,
            ),
            service.storage,
            service.logger,
        )
        files = {
            name: _write(api, descriptor, name, content)
            for name, content in outputs.items()
        }
        payload = {
            **binding,
            "run_id": run_id,
            "files": {
                name: hashlib.sha256(raw).hexdigest()
                for name, raw in sorted(files.items())
            },
        }
        terminal = {"binding": payload, "signature": _sign(settings, payload)}
        pending = _write(api, descriptor, "receipt.pending.json", _json_text(terminal))
        _web_authority(service, settings, actor, mutate=True)
        snapshot.verify()
        for name, expected in files.items():
            if (
                read_regular(
                    name, limit=131072, dir_fd=descriptor, owner_uid=os.getuid()
                )
                != expected
            ):
                raise ValueError("web_report_readback_failed")
        os.fsync(descriptor)
        os.replace(
            "receipt.pending.json",
            "receipt.json",
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
        )
        os.fsync(descriptor)
        os.fsync(run)
        os.fsync(runs)
        if (
            read_regular(
                "receipt.json", limit=131072, dir_fd=descriptor, owner_uid=os.getuid()
            )
            != pending
        ):
            raise ValueError("web_report_receipt_changed")
        snapshot.verify()
        _web_authority(service, settings, actor, mutate=True)
    except BaseException:
        if descriptor is not None:
            try:
                os.unlink("receipt.json", dir_fd=descriptor)
                os.fsync(descriptor)
            except FileNotFoundError:
                pass
        raise
    finally:
        for fd in (descriptor, run, runs):
            if fd is not None:
                os.close(fd)


def _read_web_package(service, settings, actor, run_id, source, snapshot, kind):
    from beeagent_module.integrations.beescan.web import _sign

    package = AssessmentSnapshot(service.storage)
    receipt = package.json(run_id, "receipt.json")
    binding = receipt.get("binding")
    if (
        set(receipt) != {"binding", "signature"}
        or type(binding) is not dict
        or not hmac.compare_digest(_sign(settings, binding), str(receipt["signature"]))
        or binding.get("run_id") != run_id
        or binding.get("kind") != kind
        or binding.get("principal_id") != _web_authority(service, settings, actor)
        or binding.get("case_id") != source.intent.parent_run_id
        or binding.get("finding_id") != source.finding_id
        or binding.get("source_files") != _source_hashes(snapshot)
        or type(binding.get("files")) is not dict
        or not 1 <= len(binding["files"]) <= 4
    ):
        raise PermissionError("web_report_binding_invalid")
    names = set(binding["files"])
    expected = (
        {"review_record.json", "human_evidence.txt"}
        if kind == "review"
        else {"vulnerability.json", "vulnerability.md", "report_details.json"}
    )
    if kind == "report" and "submission_draft.md" in names:
        expected.add("submission_draft.md")
    if kind == "review" and "human_evidence.txt" not in names:
        expected.remove("human_evidence.txt")
    if names != expected:
        raise ValueError("web_report_artifact_not_allowed")
    for name, sha256 in binding["files"].items():
        if hashlib.sha256(package.read(run_id, name)).hexdigest() != sha256:
            raise ValueError("web_report_artifact_changed")
    package.verify()
    snapshot.verify()
    return binding, package


def _load_web_review(service, settings, actor, source, snapshot):
    from beescan.domain.reviewed_case import DastFindingReview
    from beescan.domain.triage import HostReview, ReviewDisposition

    run_id = _web_review_id(source.intent.parent_run_id, source.finding_id)
    binding, package = _read_web_package(
        service, settings, actor, run_id, source, snapshot, "review"
    )
    record = package.json(run_id, "review_record.json")
    if set(record) != {"host_review", "disposition", "decision_basis", "attestation"}:
        raise ValueError("invalid_web_review_record")
    host = dict(record["host_review"])
    host["decided_at"] = datetime.fromisoformat(host["decided_at"])
    host["independent_evidence_refs"] = tuple(host["independent_evidence_refs"])
    host = HostReview(**host)
    if (
        host.review_id != run_id
        or host.reviewer_id != binding["principal_id"]
        or host.independent_evidence_refs
        != ((run_id + "-e",) if "human_evidence.txt" in binding["files"] else ())
        or record["attestation"]
        != (ATTESTATION if host.independent_evidence_refs else None)
    ):
        raise ValueError("web_review_identity_changed")
    return DastFindingReview(
        source, ReviewDisposition(record["disposition"]), record["decision_basis"], host
    )


def _web_details(raw):
    from dataclasses import fields

    from beescan.domain.reviewed_case import ReportDetails

    if type(raw) is not dict or set(raw) != {
        field.name for field in fields(ReportDetails)
    }:
        raise ValueError("invalid_report_details")
    values = dict(raw)
    for key in ("prerequisites", "reproduction_steps"):
        if type(values[key]) is str:
            values[key] = values[key].splitlines() if values[key] else []
        if type(values[key]) is not list or len(values[key]) > 12:
            raise ValueError("invalid_report_steps")
        values[key] = tuple(_safe_web_text(value, 512) for value in values[key])
    for key in (
        "expected_behavior",
        "observed_behavior",
        "impact",
        "remediation",
        "program_requirements",
    ):
        if values[key] == "":
            values[key] = None
        if values[key] is not None:
            _safe_web_text(values[key], 1024)
    for key in ("reproduction_confirmed", "impact_confirmed", "program_confirmed"):
        if type(values[key]) is str and values[key] in {"true", "false"}:
            values[key] = values[key] == "true"
    return ReportDetails(**values)


def execute_web_review(service, action, payload, actor):
    import fcntl
    from dataclasses import asdict

    from beescan.domain.models import validate_identifier
    from beescan.domain.reviewed_case import (
        DastFindingReview,
        build_vulnerability_report,
    )
    from beescan.domain.triage import HostReview, ReviewDisposition

    from beeagent_module.integrations.beescan.review_source import load_web_dast

    settings = deepcopy(service.reload_settings())
    reviewer = _web_authority(service, settings, actor, mutate=True)
    expected = {"case_id", "finding_id"}
    if action == "beescan_review":
        expected |= {
            "disposition",
            "decision_basis",
            "evidence_text",
            "independence_attestation",
        }
    elif action == "beescan_report_prepare":
        from dataclasses import fields

        from beescan.domain.reviewed_case import ReportDetails

        expected |= {"review_id", *(field.name for field in fields(ReportDetails))}
    else:
        raise ValueError("invalid_review_action")
    if (
        type(payload) is not dict
        or set(payload) != expected
        or len(_json_text(payload).encode()) > 24576
    ):
        raise ValueError("invalid_review_action")
    for key in ("case_id", "finding_id"):
        validate_identifier(payload[key])
    source, snapshot = load_web_dast(
        service, settings, payload["case_id"], payload["finding_id"], actor
    )
    review_id = _web_review_id(payload["case_id"], payload["finding_id"])
    runs = open_directory(service.storage / "runs")
    try:
        fcntl.flock(runs, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _web_authority(service, settings, actor, mutate=True)
        binding = {
            "case_id": payload["case_id"],
            "finding_id": payload["finding_id"],
            "principal_id": reviewer,
            "source_files": _source_hashes(snapshot),
        }
        if action == "beescan_review":
            disposition = ReviewDisposition(payload["disposition"])
            basis = _safe_web_text(payload["decision_basis"], 512)
            evidence = payload["evidence_text"]
            if type(evidence) is not str:
                raise ValueError("invalid_independent_evidence")
            if evidence:
                _safe_web_text(evidence, 4096)
            elif disposition is ReviewDisposition.VERIFIED:
                raise ValueError("independent_evidence_required")
            attestation = ATTESTATION if evidence else None
            if payload["independence_attestation"] not in (
                (ATTESTATION,) if evidence else (None, "", "unconfirmed")
            ):
                raise ValueError("independence_attestation_required")
            try:
                os.stat(review_id, dir_fd=runs, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError("immutable_review_already_exists")
            raw = evidence.encode("utf-8")
            evidence_digest = hashlib.sha256(raw).hexdigest()
            automated = {
                hashlib.sha256(value).hexdigest() for value in snapshot.files.values()
            }
            automated.update(
                value
                for item in source.execution.evidence
                for value in (
                    item.artifact_sha256,
                    item.request_sha256,
                    item.response_sha256,
                )
            )
            if evidence_digest in automated:
                raise ValueError("automated_evidence_reused")
            host = HostReview(
                review_id,
                source.finding_id,
                source.intent.mission.mission_id,
                source.intent.target.target_id,
                reviewer,
                datetime.now(UTC),
                True,
                (review_id + "-e",) if evidence else (),
            )
            review = DastFindingReview(source, disposition, basis, host)
            claim = "he-" + evidence_digest[:48]
            if evidence:
                os.mkdir(claim, mode=0o700, dir_fd=runs)
                claim_fd = open_child(runs, claim, private=True)
                try:
                    os.mkdir("module-beescan", 0o700, dir_fd=claim_fd)
                    os.fsync(claim_fd)
                    os.fsync(runs)
                finally:
                    os.close(claim_fd)
            _publish_web_package(
                service,
                settings,
                actor,
                review_id,
                {**binding, "kind": "review"},
                {
                    **({"human_evidence.txt": evidence} if evidence else {}),
                    "review_record.json": _json_text(
                        {
                            "host_review": {
                                **asdict(host),
                                "decided_at": host.decided_at.isoformat(),
                            },
                            "disposition": review.disposition.value,
                            "decision_basis": basis,
                            "attestation": attestation,
                        }
                    ),
                },
                snapshot,
            )
            _load_web_review(service, settings, actor, source, snapshot)
            result = {"review_id": review_id, "review_disposition": disposition.value}
        else:
            if payload["review_id"] == "":
                try:
                    os.stat(review_id, dir_fd=runs, follow_symlinks=False)
                except FileNotFoundError:
                    review = None
                else:
                    raise ValueError("explicit_existing_review_required")
            elif payload["review_id"] == review_id:
                review = _load_web_review(service, settings, actor, source, snapshot)
            else:
                raise PermissionError("foreign_review_id")
            details = _web_details(
                {
                    key: payload[key]
                    for key in expected - {"case_id", "finding_id", "review_id"}
                }
            )
            report = build_vulnerability_report(source, details, review)
            for revision in range(16):
                run_id = _web_report_id(review_id, revision)
                try:
                    os.stat(run_id, dir_fd=runs, follow_symlinks=False)
                except FileNotFoundError:
                    break
            else:
                raise ValueError("report_revision_limit")
            _publish_web_package(
                service,
                settings,
                actor,
                run_id,
                {
                    **binding,
                    "kind": "report",
                    "review_id": review_id if review else None,
                    "revision": revision,
                    "report_id": report.data["report_id"],
                },
                {
                    "vulnerability.json": report.canonical_json,
                    "vulnerability.md": report.markdown,
                    "report_details.json": _json_text(asdict(details)),
                    **(
                        {"submission_draft.md": report.submission_draft}
                        if report.submission_draft
                        else {}
                    ),
                },
                snapshot,
            )
            _read_web_package(
                service, settings, actor, run_id, source, snapshot, "report"
            )
            result = {
                "report_run_id": run_id,
                "review_id": review_id,
                "report_readiness": report.data["report_readiness"],
                "submission_eligible": report.data["submission_eligible"],
            }
        service.logger.info("BeeScan Web review action completed: action=%s", action)
        return {**result, "run_id": payload["case_id"], "case_id": payload["case_id"]}
    finally:
        os.close(runs)


@overload
def inspect_web_reports(
    service,
    case_id,
    finding_id,
    actor,
    *,
    report_run_id: str | None = None,
    artifact: None = None,
) -> dict[str, Any]: ...


@overload
def inspect_web_reports(
    service,
    case_id,
    finding_id,
    actor,
    *,
    report_run_id: str | None = None,
    artifact: str,
) -> bytes: ...


def inspect_web_reports(
    service, case_id, finding_id, actor, *, report_run_id=None, artifact=None
) -> dict[str, Any] | bytes:
    from beeagent_module.integrations.beescan.review_source import load_web_dast

    settings = deepcopy(service.reload_settings())
    _web_authority(service, settings, actor)
    source, snapshot = load_web_dast(service, settings, case_id, finding_id, actor)
    review_id = _web_review_id(case_id, finding_id)
    result = {"review_id": None, "review_disposition": "candidate", "reports": []}
    try:
        review = _load_web_review(service, settings, actor, source, snapshot)
    except FileNotFoundError:
        if (service.storage / "runs" / review_id).exists():
            raise ValueError("web_review_incomplete") from None
        review = None
    if review is not None:
        result.update(review_id=review_id, review_disposition=review.disposition.value)
        result["evidence_refs"] = sorted(review.host_review.independent_evidence_refs)
    allowed = {
        "json": "vulnerability.json",
        "markdown": "vulnerability.md",
        "draft": "submission_draft.md",
    }
    if artifact is not None and artifact not in allowed:
        raise ValueError("invalid_report_artifact")
    if report_run_id is not None and report_run_id not in {
        _web_report_id(review_id, revision) for revision in range(16)
    }:
        raise PermissionError("foreign_report_id")
    for revision in range(16):
        run_id = _web_report_id(review_id, revision)
        if report_run_id is not None and run_id != report_run_id:
            continue
        try:
            binding, package = _read_web_package(
                service, settings, actor, run_id, source, snapshot, "report"
            )
        except FileNotFoundError as error:
            if error.filename not in {run_id, "module-beescan", "receipt.json"}:
                raise ValueError("web_report_artifact_missing") from None
            if report_run_id is not None:
                raise ValueError("web_report_incomplete") from None
            continue
        if (
            binding.get("review_id") not in ({None, review_id} if review else {None})
            or binding.get("revision") != revision
        ):
            raise ValueError("web_report_revision_changed")
        report = package.json(run_id, "vulnerability.json")
        if report.get("report_id") != binding.get("report_id"):
            raise ValueError("web_report_identity_changed")
        if artifact is not None:
            return package.read(run_id, allowed[artifact])
        result["reports"].append(
            {
                "report_run_id": run_id,
                "report_id": report["report_id"],
                "report_readiness": report["report_readiness"],
                "submission_eligible": report["submission_eligible"],
                "missing_information": report["missing_information"],
                "revision": revision,
            }
        )
    return result
