import hashlib
import json
import logging
import os
import random
from pathlib import Path

import pytest

from beeagent_module.integrations.beescan import review
from beeagent_module.integrations.beescan.probe import handle_beescan_cli
from beeagent_module.integrations.beescan.review_source import load_assessment
from tests import test_beescan_assessment as assessment_tests
from tests.test_beescan_assessment import run_assessment, run_git

approved = assessment_tests.approved
assessment = assessment_tests.assessment
git_assessment = assessment_tests.git_assessment


@pytest.fixture
def completed(git_assessment):
    settings, root, calls = git_assessment
    settings["modules"]["registry"][0].update(
        package="beescan.module", entry="BeeScanModule"
    )
    result = run_git(git_assessment, http_signals=True)
    assert result["complete"], result
    protect_storage(root)
    parent = root / "runs" / result["assessment_run_id"] / "module-beescan"
    report = json.loads((parent / "report.json").read_text())
    intake = root / "beescan-review-intake"
    intake.mkdir(mode=0o700)
    return settings, root, calls, result, report


def protect_storage(root):
    for directory in (
        root / "runs",
        *(p for p in (root / "runs").rglob("*") if p.is_dir()),
    ):
        directory.chmod(0o700)


def prepare(completed, *, kind="marker", state="verified"):
    _, root, _, result, report = completed
    finding = next(
        item
        for item in report["findings"]
        if item["finding_id"].startswith("detect-" if kind == "marker" else "git-")
    )
    content = b"Independent local operator observation; fixture evidence only.\n"
    directory = root / "beescan-review-intake"
    evidence = directory / "proof.txt"
    evidence.write_bytes(content)
    evidence.chmod(0o600)
    data = {
        "schema_version": 1,
        "assessment_run_id": result["assessment_run_id"],
        "finding_id": finding["finding_id"],
        "disposition": state,
        "decision_basis": "Private independently documented human decision",
        "independence_attestation": review.ATTESTATION,
        "evidence": [
            {
                "name": "proof.txt",
                "sha256": hashlib.sha256(content).hexdigest(),
                "media_type": "text/plain",
            }
        ],
    }
    write_input(directory, data)
    return data


def write_input(directory, data):
    path = directory / "decision.json"
    path.write_text(json.dumps(data))
    path.chmod(0o600)


def invoke(completed, data):
    settings, root, *_ = completed
    return review.execute_review(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("review-test"),
        assessment_run_id=data["assessment_run_id"],
        finding_id=data["finding_id"],
        input_name="decision.json",
    )


@pytest.mark.parametrize("kind", ["marker", "git"])
@pytest.mark.parametrize("state", ["verified", "rejected", "inconclusive"])
def test_review_real_storage_and_public_equality(completed, monkeypatch, kind, state):
    from beescan.domain.reviewed_case import build_reviewed_case

    data = prepare(completed, kind=kind, state=state)
    settings, root, calls, parent, _ = completed
    if state != "verified":
        data.update(evidence=[], independence_attestation=None)
        write_input(root / "beescan-review-intake", data)
    original = {
        path: path.read_bytes() for path in (root / "runs").rglob("*") if path.is_file()
    }
    source, snapshot = load_assessment(root, parent["assessment_run_id"], settings)
    from beeagent_module.integrations.beescan import detection, git_exposure, probe

    def denied(*args, **kwargs):
        raise AssertionError("network_or_provider_execution")

    monkeypatch.setattr(detection, "run_detection_provider", denied)
    monkeypatch.setattr(probe, "run_provider", denied)
    monkeypatch.setattr(git_exposure, "run_detection_provider", denied)
    import socket
    import subprocess

    monkeypatch.setattr(socket, "socket", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    records = []

    def build(record):
        records.append(record)
        return build_reviewed_case(record)

    monkeypatch.setattr("beescan.domain.reviewed_case.build_reviewed_case", build)
    result = invoke(completed, data)
    assert result["complete"], result
    assert calls == ["probe", "detection", "git"]
    directory = root / "runs" / result["run_id"] / "module-beescan"
    record = json.loads((directory / "review_record.json").read_text())
    assert record["reviewer_id"] == "os-uid-" + str(os.getuid())
    assert record["reviewer_authenticated"] is True
    assert record["decision_basis"] == data["decision_basis"]
    expected = build_reviewed_case(records[0])
    assert records[0].assessment == source
    assert (directory / "case.json").read_bytes() == expected.canonical_json.encode()
    assert (directory / "case.md").read_bytes() == expected.markdown.encode()
    assert (directory / "submission_draft.md").exists() == (state == "verified")
    manifest = json.loads((directory / "evidence_manifest.json").read_text())
    for item in manifest["evidence"]:
        raw = (directory / item["artifact"]).read_bytes()
        assert item["sha256"] == hashlib.sha256(raw).hexdigest()
        assert item["review_id"] == result["run_id"]
    for name, digest in result["artifacts"].items():
        path = directory / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert path.stat().st_mode & 0o077 == 0
    assert directory.stat().st_mode & 0o077 == 0
    assert json.loads((directory / "review_status.json").read_text()) == result
    assert all(path.read_bytes() == raw for path, raw in original.items())
    assert data["decision_basis"] not in (directory / "case.json").read_text()
    assert "proof.txt" not in (directory / "case.json").read_text()
    snapshot.verify()


def test_duplicate_conflict_and_cli(completed, capsys):
    data = prepare(completed)
    settings, root, *_ = completed
    kwargs = dict(
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("cli-review"),
    )
    code = handle_beescan_cli(
        ["review", data["assessment_run_id"], data["finding_id"], "decision.json"],
        **kwargs,
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    original = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    duplicate = invoke(completed, data)
    assert duplicate["reason"] == "review_already_exists_reconciliation_required"
    assert not duplicate["complete"]
    data["disposition"] = "rejected"
    write_input(root / "beescan-review-intake", data)
    assert not invoke(completed, data)["complete"]
    assert all(
        path.read_bytes() == raw
        for path, raw in original.items()
        if path.name != "decision.json"
    )
    assert handle_beescan_cli(["review"], **kwargs) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer_id", "forged"),
        ("reviewer_authenticated", True),
        ("independent_evidence", True),
        ("schema_version", True),
        ("finding_id", "forged"),
        ("assessment_run_id", "other"),
        ("disposition", "pending"),
        ("disposition", "VERIFIED"),
        ("decision_basis", "x" * 513),
        ("decision_basis", ""),
        ("independence_attestation", True),
        ("evidence", []),
    ],
)
def test_invalid_or_forged_input(completed, field, value):
    data = prepare(completed)
    mutated = {**data, field: value}
    write_input(completed[1] / "beescan-review-intake", mutated)
    assert not invoke(completed, data)["complete"]
    assert not list(completed[1].glob("runs/review-*"))


@pytest.mark.parametrize(
    "fault",
    [
        "symlink",
        "directory",
        "permissions",
        "unreadable",
        "oversize",
        "digest",
        "hardlink",
        "traversal",
        "binary",
        "duplicate",
        "automated",
        "cross_assessment",
    ],
)
def test_unsafe_evidence(completed, fault):
    data = prepare(completed)
    directory = completed[1] / "beescan-review-intake"
    path = directory / "proof.txt"
    if fault == "symlink":
        path.unlink()
        path.symlink_to("decision.json")
    elif fault == "directory":
        path.unlink()
        path.mkdir()
    elif fault == "permissions":
        path.chmod(0o644)
    elif fault == "unreadable":
        path.chmod(0o000)
    elif fault == "oversize":
        path.write_bytes(b"x" * 65537)
    elif fault == "digest":
        path.write_bytes(b"changed")
    elif fault == "hardlink":
        os.link(path, directory / "linked.txt")
    elif fault == "traversal":
        data["evidence"][0]["name"] = "../proof.txt"
    elif fault == "binary":
        path.write_bytes(b"\x00binary")
        data["evidence"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif fault == "duplicate":
        data["evidence"] *= 2
    elif fault == "cross_assessment":
        data["assessment_run_id"] = "other-assessment"
    else:
        original = next(
            completed[1].glob("runs/*/module-beescan/detection-evidence-*.json")
        )
        path.write_bytes(original.read_bytes())
        data["evidence"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_input(directory, data)
    expected = {**data, "assessment_run_id": completed[3]["assessment_run_id"]}
    assert not invoke(completed, expected)["complete"]


@pytest.mark.parametrize(
    "name",
    [
        "report.md",
        "report.json",
        "assessment_status.json",
        "http_observation.json",
        "http_probe_status.json",
        "detection_candidates.json",
        "detection_intent.json",
        "detection_outcome.json",
        "detection_status.json",
        "git_exposure_result.json",
        "git_exposure_status.json",
    ],
)
def test_corrupt_source(completed, name):
    data = prepare(completed)
    _, snapshot = load_assessment(
        completed[1], completed[3]["assessment_run_id"], completed[0]
    )
    run_id, artifact = next(key for key in snapshot.files if key[1] == name)
    path = completed[1] / "runs" / run_id / "module-beescan" / artifact
    path.write_text("{}")
    assert not invoke(completed, data)["complete"]


@pytest.mark.parametrize(
    "fault",
    ["source", "intake", "output", "write", "fsync", "replace", "readback", "identity"],
)
def test_interrupted_persistence_is_incomplete(completed, monkeypatch, fault):
    data = prepare(completed)
    original = review._write
    injected = False

    def write(artifacts, descriptor, name, content):
        nonlocal injected
        result = original(artifacts, descriptor, name, content)
        if name == "review_status.pending.json":
            injected = True
            if fault == "source":
                next(completed[1].glob("runs/*/module-beescan/report.md")).write_text(
                    "changed"
                )
            elif fault == "intake":
                (completed[1] / "beescan-review-intake/proof.txt").write_text("changed")
            elif fault == "output":
                (artifacts.artifact_dir() / "case.json").write_text("{}")
            elif fault == "write":
                raise OSError("injected_write")
            elif fault == "fsync":
                monkeypatch.setattr(
                    os,
                    "fsync",
                    lambda fd: (_ for _ in ()).throw(OSError("injected_fsync")),
                )
            elif fault == "replace":
                monkeypatch.setattr(
                    os,
                    "replace",
                    lambda *a, **k: (_ for _ in ()).throw(OSError("injected_replace")),
                )
            elif fault == "readback":
                (artifacts.artifact_dir() / name).write_text("{}")
            elif fault == "identity":
                completed[0]["beescan"]["approval"]["operator_uid"] += 1
        return result

    monkeypatch.setattr(review, "_write", write)
    status = invoke(completed, data)
    assert injected
    assert not status["complete"], status
    path = (
        completed[1] / "runs" / status["run_id"] / "module-beescan/review_status.json"
    )
    assert not path.exists() or json.loads(path.read_text())["complete"] is False
    assert not invoke(completed, data)["complete"]


def test_review_disabled_and_operator_refused(completed, monkeypatch):
    data = prepare(completed)
    completed[0]["modules"]["registry"][0]["enabled"] = False
    assert not invoke(completed, data)["complete"]
    assert not list(completed[1].glob("runs/review-*"))
    completed[0]["modules"]["registry"][0]["enabled"] = True
    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 1)
    assert not invoke(completed, data)["complete"]


def test_expired_scan_authority_still_allows_review(completed):
    data = prepare(completed)
    for key in ("approval", "detection_approval", "git_exposure_approval"):
        completed[0]["beescan"][key].update(
            valid_from="2020-01-01T00:00:00+00:00",
            expires_at="2020-01-02T00:00:00+00:00",
        )
    assert invoke(completed, data)["complete"]


def test_marker_legacy_assessment(assessment):
    settings, root, _ = assessment
    settings["modules"]["registry"][0].update(
        package="beescan.module", entry="BeeScanModule"
    )
    status = run_assessment(assessment)
    assert status["complete"]
    protect_storage(root)
    parent = root / "runs" / status["assessment_run_id"] / "module-beescan"
    report = json.loads((parent / "report.json").read_text())
    (root / "beescan-review-intake").mkdir(mode=0o700)
    completed = (*assessment, status, report)
    assert invoke(completed, prepare(completed))["complete"]


def test_strict_parser_seeded_bytes(completed):
    data = prepare(completed)
    generator = random.Random(319)
    for _ in range(1000):
        raw = generator.randbytes(generator.randrange(0, 8500))
        with pytest.raises((ValueError, UnicodeError)):
            review.parse_review_input(
                raw, data["assessment_run_id"], data["finding_id"]
            )
    raw = (
        json.dumps(data)
        .replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
        .encode()
    )
    with pytest.raises(ValueError):
        review.parse_review_input(raw, data["assessment_run_id"], data["finding_id"])


def test_review_launcher_skips_bootstrap_and_downloads(tmp_path):
    import subprocess

    root = Path(__file__).resolve().parents[1]
    launcher = tmp_path / "start.sh"
    launcher.write_bytes((root / "start.sh").read_bytes())
    result = subprocess.run(
        ["bash", str(launcher), "beescan", "review"], cwd=tmp_path, capture_output=True
    )
    assert result.returncode == 3
    assert b"already installed" in result.stderr
    binary = tmp_path / ".venv/bin/python3"
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    binary.chmod(0o700)
    result = subprocess.run(
        [
            "bash",
            str(launcher),
            "beescan",
            "review",
            "assessment",
            "finding",
            "decision.json",
        ],
        cwd=tmp_path,
        capture_output=True,
    )
    assert result.returncode == 0
    assert result.stdout.decode().splitlines() == [
        "config/start.py",
        "beescan",
        "review",
        "assessment",
        "finding",
        "decision.json",
    ]
    assert not (tmp_path / ".env").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "source_symlink",
        "source_permissions",
        "intake_symlink",
        "intake_permissions",
        "input_oversize",
        "unknown_finding",
        "unknown_assessment",
    ],
)
def test_review_paths_and_selection(completed, fault):
    data = prepare(completed)
    root = completed[1]
    if fault in {"missing", "source_symlink", "source_permissions"}:
        path = (
            root
            / "runs"
            / completed[3]["assessment_run_id"]
            / "module-beescan/report.json"
        )
        if fault == "source_permissions":
            path.chmod(0o666)
        elif fault == "source_symlink":
            original = path.with_name("saved.json")
            path.rename(original)
            path.symlink_to(original.name)
        else:
            path.unlink()
    elif fault == "intake_symlink":
        path = root / "beescan-review-intake"
        path.rename(root / "old-intake")
        path.symlink_to("old-intake", target_is_directory=True)
    elif fault == "intake_permissions":
        (root / "beescan-review-intake").chmod(0o777)
    elif fault == "input_oversize":
        (root / "beescan-review-intake/decision.json").write_bytes(b"x" * 8193)
    elif fault == "unknown_finding":
        data["finding_id"] = "missing-finding"
        write_input(root / "beescan-review-intake", data)
    else:
        data["assessment_run_id"] = "missing-assessment"
        write_input(root / "beescan-review-intake", data)
    assert not invoke(completed, data)["complete"]


def test_failure_after_terminal_rename_rolls_back(completed, monkeypatch):
    data = prepare(completed)
    original = os.replace

    def replace(*args, **kwargs):
        original(*args, **kwargs)
        (completed[1] / "beescan-review-intake/proof.txt").write_text(
            "changed after rename"
        )

    monkeypatch.setattr(os, "replace", replace)
    result = invoke(completed, data)
    assert result["complete"] is False
    path = (
        completed[1] / "runs" / result["run_id"] / "module-beescan/review_status.json"
    )
    assert json.loads(path.read_text())["complete"] is False


def test_review_does_not_load_other_module_entries(completed, monkeypatch, capsys):
    import importlib

    data = prepare(completed)
    settings, root, *_ = completed
    settings["modules"]["registry"].append(
        {
            "id": "other",
            "enabled": True,
            "package": "forbidden_provider",
            "entry": "Module",
        }
    )
    original = importlib.import_module

    def load(name, *args, **kwargs):
        if name == "forbidden_provider":
            raise AssertionError("unrelated_module_execution")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", load)
    assert (
        handle_beescan_cli(
            ["review", data["assessment_run_id"], data["finding_id"], "decision.json"],
            settings=settings,
            reload_settings=lambda: settings,
            storage_dir=root,
            logger=logging.getLogger("review-only-module"),
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["complete"]


def test_reconstructed_parent_budget_mismatch_refuses(completed):
    data = prepare(completed)
    path = (
        completed[1]
        / "runs"
        / data["assessment_run_id"]
        / "module-beescan/assessment_status.json"
    )
    record = json.loads(path.read_text())
    record["budgets"]["max_requests"] += 1
    path.write_text(json.dumps(record))
    assert not invoke(completed, data)["complete"]


def test_git_provenance_cannot_name_a_different_child(completed):
    from dataclasses import asdict, replace

    from beescan.domain.reporting import build_assessment_report

    data = prepare(completed, kind="git")
    settings, root, _, parent, _ = completed
    assessment, _ = load_assessment(root, data["assessment_run_id"], settings)
    exposure = assessment.exposure_result
    assert exposure is not None
    exposure = replace(
        exposure,
        facts=replace(
            exposure.facts,
            provenance=replace(exposure.facts.provenance, run_id="forged-child"),
        ),
    )
    assessment = replace(assessment, exposure_result=exposure)
    child = root / "runs" / parent["exposure_run_id"] / "module-beescan"
    (child / "git_exposure_result.json").write_text(
        json.dumps({"schema_version": 1, **asdict(exposure)})
    )
    for ref in exposure.facts.evidence_refs:
        (child / (ref + ".json")).write_text(
            json.dumps({"schema_version": 1, **asdict(exposure.facts)})
        )
    report = build_assessment_report(assessment)
    directory = root / "runs" / data["assessment_run_id"] / "module-beescan"
    (directory / "report.json").write_text(report.canonical_json)
    (directory / "report.md").write_text(report.markdown)
    assert not invoke(completed, data)["complete"]


@pytest.mark.parametrize("name", ["http_observation.json", "git_exposure_result.json"])
@pytest.mark.parametrize("value", [None, False, 17, "invalid", []])
def test_non_object_source_records_refuse_without_traceback(
    completed, capsys, name, value
):
    data = prepare(completed)
    _, snapshot = load_assessment(completed[1], data["assessment_run_id"], completed[0])
    child, artifact = next(key for key in snapshot.files if key[1] == name)
    path = completed[1] / "runs" / child / "module-beescan" / artifact
    if name == "git_exposure_result.json":
        record = json.loads(path.read_text())
        record["facts"] = value
    else:
        record = value
    path.write_text(json.dumps(record))
    settings, root, *_ = completed
    code = handle_beescan_cli(
        ["review", data["assessment_run_id"], data["finding_id"], "decision.json"],
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=root,
        logger=logging.getLogger("malformed-source"),
    )
    assert code == 3
    assert json.loads(capsys.readouterr().out)["complete"] is False
    assert not list(root.glob("runs/review-*"))
