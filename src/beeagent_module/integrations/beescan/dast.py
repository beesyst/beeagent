import fcntl
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import RuntimeContext, generate_session_id
from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.integrations.beescan.policy import ProbePolicy
from beeagent_module.integrations.beescan.review_source import (
    AssessmentSnapshot,
    open_child,
    open_directory,
)


@dataclass(frozen=True)
class DastPolicy:
    transport: ProbePolicy
    approved: bool
    method: str
    entries: tuple[str, ...]
    request_budget: int
    seconds: int
    archive: str
    entry_selection: str = "exact_entry"
    max_candidates: int = 1

    @classmethod
    def from_config(cls, config):
        if (
            type(config) is not dict
            or set(config) - {"entry_selection", "max_candidates", "archive"}
            != set(cls.__dataclass_fields__)
            - {"entry_selection", "max_candidates", "archive"}
            or config.get("entry_selection") == "authenticated_discovery"
            and config.get("max_candidates") != 1
        ):
            raise ValueError("invalid_dast_approval")
        values = dict(config)
        if "archive" not in values:
            from beeagent_module.integrations.beescan.providers import (
                managed_zap_archive,
            )

            values["archive"] = str(managed_zap_archive())
        values["transport"] = ProbePolicy.from_config(values["transport"])
        if type(values["entries"]) is not list:
            raise ValueError("invalid_dast_approval")
        values["entries"] = tuple(values["entries"])
        return cls(**values)

    def __post_init__(self):
        from beescan.domain.models import utc_instant

        if (
            type(self.transport) is not ProbePolicy
            or type(self.approved) is not bool
            or self.method != "active_dast"
            or not self.transport.origin.startswith("https://")
            or self.transport.network_namespace != "/beeagent-managed/ns/net"
            or type(self.entries) is not tuple
            or self.entry_selection not in {"exact_entry", "authenticated_discovery"}
            or type(self.max_candidates) is not int
            or self.max_candidates != 1
            or len(self.entries) != (1 if self.entry_selection == "exact_entry" else 0)
            or type(self.request_budget) is not int
            or not 1 <= self.request_budget <= 100
            or type(self.seconds) is not int
            or not 10 <= self.seconds <= 60
            or type(self.archive) is not str
            or not Path(self.archive).is_absolute()
            or ".." in Path(self.archive).parts
            or len(self.archive) > 256
            or any(ord(c) < 32 for c in self.archive)
        ):
            raise ValueError("invalid_dast_approval")
        utc_instant(self.transport.valid_from)
        utc_instant(self.transport.expires_at)
        for entry in self.entries:
            if (
                type(entry) is not str
                or not 1 <= len(entry) <= 512
                or not entry.startswith("/")
                or entry.startswith("//")
                or re.search(r"[^\x21-\x7e]|\\", entry)
                or urlsplit(entry).fragment
            ):
                raise ValueError("invalid_dast_entry")

    def authorize(self, operator, *, at):
        operator.verify()
        if not self.approved:
            raise PermissionError("active_dast_not_approved")
        self.transport.authorize(
            self.transport.intent(), operator_uid=os.getuid(), at=at
        )
        if at.timestamp() + self.seconds > self.transport.expires_at.timestamp():
            raise PermissionError("active_dast_expired")


def validate_dast_settings(config, enabled, *, validate_contracts=True):
    if "dast" not in config:
        return
    value = config["dast"]
    if (
        type(value) is not dict
        or set(value) != {"enabled", "approval"}
        or type(value["enabled"]) is not bool
        or value["enabled"]
        and not enabled
        or value["approval"] is not None
        and type(value["approval"]) is not dict
    ):
        raise RuntimeError("Invalid beescan.dast settings")
    if validate_contracts and value["approval"] is not None:
        try:
            DastPolicy.from_config(value["approval"])
        except ValueError, TypeError, ImportError, KeyError:
            raise RuntimeError("Invalid beescan.dast approval") from None


def is_dast_task(task):
    return bool(
        re.search(r"\bpath\s+traversal\b|обход\w*\s+каталог", task, re.IGNORECASE)
    )


def _current(settings):
    enabled = any(
        item.get("id") == "beescan" and item.get("enabled") is True
        for item in settings.get("modules", {}).get("registry", [])
    )
    config = settings.get("beescan", {})
    validate_dast_settings(config, enabled)
    if (
        not enabled
        or config.get("dast", {}).get("enabled") is not True
        or config.get("dast", {}).get("approval") is None
        or config.get("investigation", {}).get("trusted_local_enabled") is not True
    ):
        raise PermissionError("active_dast_not_approved")
    return DastPolicy.from_config(config["dast"]["approval"])


def _plain(value):
    return json.loads(json.dumps(asdict(value), default=lambda item: item.isoformat()))


def approval_identity(policy):
    binding = _plain(policy)
    for key in ("valid_from", "expires_at"):
        binding["transport"].pop(key)
    if policy.entry_selection == "exact_entry":
        binding.pop("entry_selection")
        binding.pop("max_candidates")
    return hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()


def _api(storage_dir, run_id, logger):
    from beescan.domain.models import validate_identifier

    validate_identifier(run_id)
    descriptor = open_directory(storage_dir)
    try:
        for part in ("runs", run_id, "module-beescan"):
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = open_child(descriptor, part)
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)
    return ArtifactAPI(
        RuntimeContext(
            run_id=run_id,
            session_id=generate_session_id(),
            case_type="web_investigation",
            module_id="beescan",
            authority=AuthorityLevel.EXECUTION_CAPABLE,
        ),
        storage_dir,
        logger,
    )


def _restore(snapshot, run_id):
    from beescan.capabilities.dast import (
        DastEvidence,
        DastExecution,
        DastIntent,
        ExecutionState,
        ScannerMatch,
        ScannerOutcome,
        build_dast_report,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    raw = snapshot.json(run_id, "dast_handoff.json")
    if set(raw) != {"intent", "execution", "outcome"}:
        raise ValueError("invalid_dast_checkpoint")
    intent = dict(raw["intent"])
    intent["project"] = Project(**intent["project"])
    target = dict(intent["target"])
    target["kind"] = TargetKind(target["kind"])
    intent["target"] = Target(**target)
    scope = dict(intent["scope"])
    for key in ("target_ids", "excluded_target_ids", "approved_methods"):
        scope[key] = tuple(scope[key])
    for key in ("valid_from", "expires_at"):
        scope[key] = datetime.fromisoformat(scope[key])
    intent["scope"] = EngagementScope(**scope)
    mission = dict(intent["mission"])
    mission["capability_ids"] = tuple(mission["capability_ids"])
    intent["mission"] = Mission(**mission)
    for key in ("rule_ids", "check_ids"):
        intent[key] = tuple(intent[key])
    intent["started_at"] = datetime.fromisoformat(intent["started_at"])
    intent = DastIntent(**intent)
    execution = dict(raw["execution"])
    execution["state"] = ExecutionState(execution["state"])
    execution["ended_at"] = datetime.fromisoformat(execution["ended_at"])
    for key in ("rule_ids", "covered_checks"):
        execution[key] = tuple(execution[key])
    execution["evidence"] = tuple(
        DastEvidence(**item) for item in execution["evidence"]
    )
    execution = DastExecution(**execution)
    outcome = dict(raw["outcome"])
    outcome["rule_ids"] = tuple(outcome["rule_ids"])
    outcome["matches"] = tuple(
        ScannerMatch(
            item["rule_id"], item["check_id"], DastEvidence(**item["evidence"])
        )
        for item in outcome["matches"]
    )
    outcome = ScannerOutcome(**outcome)
    records = snapshot.json(run_id, "dast_evidence.json")
    if (
        set(records) != {"schema_version", "run_id", "intent_id", "requests"}
        or records["schema_version"] != 1
        or records["run_id"] != run_id
        or records["intent_id"] != intent.identity
        or type(records["requests"]) is not list
        or len(records["requests"]) > execution.request_count
    ):
        raise ValueError("invalid_dast_evidence")
    for item in records["requests"]:
        if (
            type(item) is not dict
            or set(item) != {"request_sha256", "response_sha256", "status_code"}
            or type(item["status_code"]) is not int
            or not 100 <= item["status_code"] <= 599
            or any(
                type(item[key]) is not str
                or re.fullmatch(r"[0-9a-f]{64}", item[key]) is None
                for key in ("request_sha256", "response_sha256")
            )
        ):
            raise ValueError("invalid_dast_evidence")
    content = snapshot.read(run_id, "dast_evidence.json")
    for evidence in execution.evidence:
        if evidence.artifact_sha256 != hashlib.sha256(content).hexdigest() or not any(
            item["request_sha256"] == evidence.request_sha256
            and item["response_sha256"] == evidence.response_sha256
            for item in records["requests"]
        ):
            raise ValueError("dast_evidence_changed")
    lifecycle = snapshot.json(run_id, "egress_lifecycle.json")
    if (
        lifecycle.get("cleanup_verified") is not True
        or lifecycle.get("state") != "closed"
    ):
        raise ValueError("dast_cleanup_unverified")
    report = build_dast_report(intent, execution, outcome)
    if (
        snapshot.read(run_id, "report.json") != report.canonical_json.encode()
        or snapshot.read(run_id, "report.md") != report.markdown.encode()
    ):
        raise ValueError("dast_report_changed")
    return intent, execution, outcome, report


def load_dast_case(state, snapshot, case_id):
    from beescan.domain.models import validate_identifier

    if (
        set(state)
        != {
            "schema_version",
            "case_id",
            "origin",
            "operator_uid",
            "segments",
            "pending",
            "status",
            "approval_identity",
        }
        or state["schema_version"] != 3
        or state["case_id"] != case_id
        or type(state["operator_uid"]) is not int
        or state["operator_uid"] != os.getuid()
        or state["pending"] is not False
        or type(state["approval_identity"]) is not str
        or re.fullmatch(r"[0-9a-f]{64}", state["approval_identity"]) is None
        or type(state["segments"]) is not list
        or not 1 <= len(state["segments"]) <= 8
        or len(set(state["segments"])) != len(state["segments"])
    ):
        raise ValueError("invalid_dast_case")
    report = None
    for run_id in state["segments"]:
        validate_identifier(run_id)
        intent, _execution, _outcome, report = _restore(snapshot, run_id)
        if intent.parent_run_id != case_id or intent.target.locator != state["origin"]:
            raise ValueError("dast_case_identity")
    if report is None or state["status"] != report.data["status"]:
        raise ValueError("dast_case_status")
    snapshot.verify()
    return state, snapshot


def execute_dast_investigation(
    *,
    task,
    settings,
    reload_settings,
    storage_dir,
    logger,
    local_operator,
    resume_case_id=None,
    _assessment=None,
    _candidate_handoff=None,
    **_options,
):
    from beescan.capabilities.dast import (
        DastEvidence,
        DastExecution,
        DastIntent,
        ExecutionState,
        ScannerMatch,
        ScannerOutcome,
        build_dast_report,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    from beeagent_module.integrations.beescan.case_state import load_case, save_case
    from beeagent_module.integrations.beescan.dast_runner import run_zap
    from beeagent_module.integrations.beescan.local_cli import _LocalOperator

    status = {
        "status": "REFUSED",
        "complete": False,
        "reason": "active_dast_not_approved",
        "request_count": 0,
    }
    if type(local_operator) is not _LocalOperator or (
        _assessment is None and not is_dast_task(task.task)
    ):
        return status
    policy = _current(settings)
    policy.authorize(local_operator, at=datetime.now(UTC))
    if task.target.rstrip("/") != policy.transport.origin:
        return status
    if (policy.entry_selection == "authenticated_discovery") != (
        _assessment is not None
    ):
        return status
    entries = policy.entries
    request_budget, seconds = policy.request_budget, policy.seconds
    if _assessment is not None:
        from beeagent_module.integrations.beescan.discovery_dast import (
            SelectedAssessment,
        )

        if type(_assessment) is not SelectedAssessment or resume_case_id is not None:
            raise PermissionError("invalid_discovered_assessment")
        _assessment.verify(policy)
        entries = (_assessment.entry.reveal_to_host(),)
        request_budget = min(request_budget, _assessment.request_budget)
        seconds = min(seconds, _assessment.seconds)
    run_id = "dast-" + uuid4().hex
    case_id = (
        _assessment.action.case_id
        if _assessment is not None
        else resume_case_id or "dast-case-" + uuid4().hex
    )
    case_api = _api(storage_dir, case_id, logger)
    lock = (
        os.open(case_api.artifact_dir(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if _assessment is None
        else None
    )
    snapshot = AssessmentSnapshot(storage_dir)
    identity = approval_identity(policy)
    segments = []
    try:
        if lock is not None:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if resume_case_id:
            previous, snapshot = load_case(storage_dir, case_id)
            if (
                previous["schema_version"] != 3
                or previous["origin"] != policy.transport.origin
                or previous["approval_identity"] != identity
            ):
                raise PermissionError("dast_case_identity")
            segments = previous["segments"]
            if previous["status"] in {"CANDIDATE", "NO_MATCH"}:
                return {
                    **status,
                    "status": previous["status"],
                    "complete": True,
                    "reason": "authenticated_case_reused",
                    "case_id": case_id,
                    "run_id": segments[-1],
                }
            if len(segments) >= 8:
                raise PermissionError("dast_case_budget")
        artifacts = _api(storage_dir, run_id, logger)
        transport = policy.transport
        started = datetime.now(UTC)
        check_id = "check-" + hashlib.sha256(entries[0].encode()).hexdigest()[:48]
        intent = DastIntent(
            Project(transport.project_id, "Approved DAST assessment"),
            Target(
                transport.target_id,
                transport.project_id,
                TargetKind.URL,
                transport.origin,
            ),
            EngagementScope(
                transport.scope_id,
                transport.project_id,
                (transport.target_id,),
                "host-active-dast-approval",
                valid_from=transport.valid_from,
                expires_at=transport.expires_at,
                approved_methods=("active_dast",),
                max_requests=policy.request_budget,
                max_seconds=policy.seconds,
            ),
            Mission(
                transport.mission_id,
                transport.project_id,
                transport.scope_id,
                ("web.dast",),
            ),
            case_id,
            run_id,
            "zap",
            "2.17.0",
            "rule6-v1",
            ("6",),
            (check_id,),
            request_budget,
            seconds,
            started,
        )

        def authorize():
            if reload_settings() != settings or _current(settings) != policy:
                raise PermissionError("approval_changed")
            policy.authorize(local_operator, at=datetime.now(UTC))
            intent.validate_at(datetime.now(UTC))
            snapshot.verify()
            if _assessment is not None:
                _assessment.verify(policy)

        authorize()
        state = {
            "schema_version": 3,
            "case_id": case_id,
            "origin": transport.origin,
            "operator_uid": os.getuid(),
            "segments": [*segments, run_id],
            "pending": True,
            "status": "PARTIAL",
            "approval_identity": identity,
        }
        if resume_case_id:
            snapshot.files.pop((case_id, "case.json"))
        if _assessment is None:
            save_case(case_api, state)
        failed_state = None
        reason = "ok"
        candidate_target = None
        try:
            raw, records, count = run_zap(
                transport,
                origin=transport.origin,
                entries=entries,
                archive=Path(policy.archive),
                artifacts=artifacts,
                run_id=run_id,
                request_budget=request_budget,
                seconds=seconds,
                authorize=authorize,
            )
            if raw["alerts"]:
                candidate_target = raw["alerts"][0]["target"]
            authorize()
        except (
            KeyboardInterrupt,
            TimeoutError,
            OSError,
            ValueError,
            RuntimeError,
        ) as error:
            terminal = artifacts.read_json("dast_execution_status.json")
            if (
                type(terminal) is not dict
                or terminal.get("cleanup_verified") is not True
            ):
                raise RuntimeError("dast_cleanup_unverified") from None
            failed_state = (
                ExecutionState.CANCELLED
                if isinstance(error, KeyboardInterrupt)
                else ExecutionState.TIMEOUT
                if isinstance(error, TimeoutError)
                else ExecutionState.ERROR
            )
            reason = failed_state.value
            raw = {"alerts": [], "host_complete": False}
            records, count = (), terminal["request_count"]
        snapshot.verify()
        safe = {
            "schema_version": 1,
            "run_id": run_id,
            "intent_id": intent.identity,
            "requests": list(records),
        }
        _persist(artifacts, "dast_evidence.json", safe)
        if AssessmentSnapshot(storage_dir).json(run_id, "dast_evidence.json") != safe:
            raise ValueError("dast_evidence_readback")
        digest = hashlib.sha256(
            AssessmentSnapshot(storage_dir).read(run_id, "dast_evidence.json")
        ).hexdigest()
        requested = {
            (item["request_sha256"], item["response_sha256"]) for item in raw["alerts"]
        }
        selected = {}
        for item in records:
            key = (item["request_sha256"], item["response_sha256"])
            if key in requested or not selected:
                selected.setdefault(key, item)
        evidence = tuple(
            DastEvidence(
                "dast-ev-" + str(index),
                digest,
                item["request_sha256"],
                item["response_sha256"],
            )
            for index, item in enumerate(selected.values())
        )
        matches = []
        for alert in raw["alerts"]:
            bound = next(
                item
                for item in evidence
                if item.request_sha256 == alert["request_sha256"]
                and item.response_sha256 == alert["response_sha256"]
            )
            if not matches:
                matches.append(ScannerMatch("6", check_id, bound))
        lifecycle = artifacts.read_json("egress_lifecycle.json")
        if type(lifecycle) is not dict:
            raise ValueError("dast_cleanup_unverified")
        execution = DastExecution(
            intent.identity,
            run_id,
            "zap",
            "2.17.0",
            "rule6-v1",
            ("6",),
            failed_state
            or (
                ExecutionState.COMPLETE
                if raw["host_complete"]
                else ExecutionState.BUDGET
            ),
            (check_id,) if matches else (),
            evidence,
            count,
            lifecycle.get("cleanup_verified") is True,
            datetime.now(UTC),
        )
        outcome = ScannerOutcome(
            intent.identity, run_id, "zap", "2.17.0", "rule6-v1", ("6",), tuple(matches)
        )
        report = build_dast_report(intent, execution, outcome)
        _persist(
            artifacts,
            "dast_handoff.json",
            {
                "intent": _plain(intent),
                "execution": _plain(execution),
                "outcome": _plain(outcome),
            },
        )
        for name, content in (
            ("report.json", report.canonical_json),
            ("report.md", report.markdown),
        ):
            path = artifacts.write_text(name, content)
            path.chmod(0o600)
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        checked = AssessmentSnapshot(storage_dir)
        _restore(checked, run_id)
        if failed_state is None:
            authorize()
        else:
            snapshot.verify()
        state.update(pending=False, status=report.data["status"])
        if _assessment is None:
            save_case(case_api, state)
            load_case(storage_dir, case_id)
        status.update(
            status=report.data["status"],
            complete=report.data["status"] in {"CANDIDATE", "NO_MATCH"},
            reason=reason,
            run_id=run_id,
            case_id=case_id,
            request_count=count,
            report_location=str(artifacts.artifact_dir() / "report.md"),
        )
        if (
            candidate_target is not None
            and report.data["status"] == "CANDIDATE"
            and reason == "ok"
            and execution.cleanup_verified
        ):
            authorize()
            if _candidate_handoff is not None:
                _candidate_handoff(candidate_target)
                status["reproduction"] = "PENDING_PARENT_PUBLICATION"
        _persist(artifacts, "investigation_status.json", status)
        return status
    finally:
        if lock is not None:
            os.close(lock)
