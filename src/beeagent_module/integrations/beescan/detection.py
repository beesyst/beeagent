import json
import logging
import os
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from subprocess import SubprocessError
from threading import Lock
from uuid import uuid4

from beesdk.capabilities import CapabilityResult, CapabilityStatus
from beesdk.modules import AuthorityLevel as SDKAuthority

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)
from beeagent_module.integrations.beescan.detection_policy import DetectionPolicy
from beeagent_module.integrations.beescan.detection_runner import (
    parse_capture,
    read_regular,
    run_detection_provider,
    safe_response,
)
from beeagent_module.integrations.beescan.http_runner import verify_resolution
from beeagent_module.integrations.beescan.probe import _unique_object


def _json(raw):
    return json.loads(raw, object_pairs_hook=_unique_object)


def load_source(storage_dir, policy):
    from beescan.capabilities.http_probe import (
        HostProvenance,
        HttpFacts,
        HttpObservation,
    )
    from beescan.domain.models import validate_identifier

    descriptor = os.open(
        storage_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        for part in ("runs", policy.source_run_id, "module-beescan"):
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_fd

        def read(name):
            return _json(read_regular(name, limit=32768, dir_fd=descriptor))

        source = read("http_observation.json")
        if type(source) is not dict:
            raise ValueError("invalid_source")
        schema = source.pop("schema_version", None)
        if type(schema) is not int or schema != 1:
            raise ValueError("invalid_source")
        fields = source["facts"]
        fields["provenance"] = HostProvenance(**fields["provenance"])
        if (
            type(fields["evidence_refs"]) is not list
            or type(source["evidence_refs"]) is not list
        ):
            raise ValueError("invalid_source")
        fields["evidence_refs"] = tuple(fields["evidence_refs"])
        source["facts"] = HttpFacts(**fields)
        source["evidence_refs"] = tuple(source["evidence_refs"])
        observation = HttpObservation(**source)
        status = read("http_probe_status.json")
        expected = {
            "schema_version": 1,
            "run_id": policy.source_run_id,
            "status": "ok",
            "complete": True,
            "project_id": policy.project_id,
            "scope_id": policy.scope_id,
            "mission_id": policy.mission_id,
            "target_id": policy.target_id,
            "provenance": asdict(observation.facts.provenance),
            "evidence_refs": list(observation.evidence_refs),
        }
        if type(status) is not dict or any(
            type(status.get(key)) is not type(value) or status[key] != value
            for key, value in expected.items()
        ):
            raise ValueError("invalid_source")
        for ref in observation.evidence_refs:
            validate_identifier(ref)
            if json.dumps(read(ref + ".json"), sort_keys=True) != json.dumps(
                {"schema_version": 1, **asdict(observation.facts)}, sort_keys=True
            ):
                raise ValueError("invalid_source")
        policy.intent(observation, at=datetime.now(UTC))
        return observation
    finally:
        os.close(descriptor)


def parse_detection_output(raw, capture, *, limit):
    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise ValueError("invalid_provider_output")
    try:
        lines = raw.splitlines()
        if not 1 <= len(lines) <= 2:
            raise ValueError
        names = set()
        for line in lines:
            record = _json(line)
            fixed = {
                "template-id": "beescan-http-marker",
                "template-path": "/template.yaml",
                "info": {
                    "name": "BeeScan restricted HTTP marker",
                    "author": ["beesyst"],
                    "tags": None,
                    "severity": "info",
                    "metadata": {"version": "1"},
                },
                "type": "",
                "path": safe_response(capture),
                "matched-at": "/input.txt",
                "matcher-status": True,
            }
            if type(record) is not dict or set(record) != set(fixed) | {
                "matcher-name",
                "timestamp",
            }:
                raise ValueError
            if any(
                type(record[key]) is not type(value) or record[key] != value
                for key, value in fixed.items()
            ):
                raise ValueError
            name = record["matcher-name"]
            if (
                type(name) is not str
                or name not in {"marker", "completed"}
                or name in names
            ):
                raise ValueError
            stamp = record["timestamp"]
            if (
                type(stamp) is not str
                or len(stamp) > 64
                or datetime.fromisoformat(stamp).utcoffset() is None
            ):
                raise ValueError
            names.add(name)
        if "completed" not in names or ("marker" in names) != (
            capture["marker_header"] == "present"
        ):
            raise ValueError
        return "marker" in names
    except ValueError, TypeError, KeyError, RecursionError, UnicodeError:
        raise ValueError("invalid_provider_output") from None


def _persist(artifacts, filename, data):
    path = artifacts.write_json(filename, data)
    path.chmod(0o600)
    expected = json.dumps(data, sort_keys=True)
    if json.dumps(_json(read_regular(path, limit=131072)), sort_keys=True) != expected:
        raise OSError("artifact_incomplete")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    return path


@dataclass(frozen=True)
class AssessmentSourceBinding:
    configured_policy: DetectionPolicy
    observation: object

    def bind(self, current):
        from beescan.capabilities.http_probe import HttpObservation

        if (
            current != self.configured_policy
            or type(self.observation) is not HttpObservation
        ):
            raise PermissionError("approval_or_source_changed")
        return replace(
            current,
            source_run_id=self.observation.facts.provenance.run_id,
            source_observation_id=self.observation.observation_id,
        )


class GovernedDetectionCaller:
    def __init__(
        self,
        *,
        policy,
        reload_policy,
        observation,
        storage_dir,
        run_id,
        artifacts,
        http_signals=False,
    ):
        if type(http_signals) is not bool:
            raise ValueError("invalid_signal_selection")
        self.policy, self.reload_policy = policy, reload_policy
        self.observation, self.storage_dir = observation, storage_dir
        self.run_id, self.artifacts = run_id, artifacts
        self.http_signals = http_signals
        self.facts = None
        self.provenance = None
        self.evidence_record = None
        self._used = False
        self._lock = Lock()

    def _authorize(self, intent):
        current = self.reload_policy()
        if current != self.policy:
            raise PermissionError("approval_or_source_changed")
        current.authorize(
            intent, self.observation, operator_uid=os.getuid(), at=datetime.now(UTC)
        )
        if load_source(self.storage_dir, current) != self.observation:
            raise PermissionError("approval_or_source_changed")
        verify_resolution(current)

    def call(self, capability_name, payload):
        from beescan.capabilities.http_probe import HostProvenance

        status, reason = CapabilityStatus.REFUSED, "authorization_refused"
        with self._lock:
            if self._used:
                return self._failure(status, "request_budget_exceeded")
            self._used = True
        try:
            intent = self.policy.intent(self.observation, at=datetime.now(UTC))
            if (
                capability_name != intent.capability_name
                or type(payload) is not dict
                or payload != intent.payload
                or any(
                    type(payload[key]) is not type(value)
                    for key, value in intent.payload.items()
                )
            ):
                return self._failure(status, "invalid_payload")
            self._authorize(intent)
            options = {"http_signals": True} if self.http_signals else {}
            raw, capture = run_detection_provider(
                self.policy, reauthorize=lambda: self._authorize(intent), **options
            )
            capture = parse_capture(
                json.dumps(capture).encode("ascii"),
                self.policy,
                http_signals=self.http_signals,
            )
            matched = parse_detection_output(
                raw, capture, limit=self.policy.output_bytes
            )
            self._authorize(intent)
            ref = "detection-evidence-" + uuid4().hex
            provenance = HostProvenance(
                self.run_id, intent.provider_id, intent.provider_version
            )
            facts = {
                key: intent.payload[key]
                for key in (
                    "mission_id",
                    "target_id",
                    "origin",
                    "source_observation_id",
                    "template_id",
                    "template_version",
                    "template_sha256",
                )
            }
            facts.update(
                run_id=self.run_id,
                complete=True,
                matches=[
                    {"match_id": "marker", "severity": "info", "evidence_refs": [ref]}
                ]
                if matched
                else [],
            )
            evidence_record = {
                "schema_version": 1,
                "facts": facts,
                "capture": capture,
                "provenance": asdict(provenance),
                "profile": intent.profile,
                "source_run_id": self.policy.source_run_id,
            }
            _persist(self.artifacts, ref + ".json", evidence_record)
            self.evidence_record = evidence_record
            self.facts, self.provenance = facts, provenance
            return CapabilityResult(
                intent.capability_name,
                CapabilityStatus.OK,
                SDKAuthority.EXECUTION_CAPABLE,
                "Restricted detection completed",
                {"evidence_refs": [ref]},
            )
        except PermissionError as error:
            reason = str(error)
        except TimeoutError:
            status, reason = CapabilityStatus.TIMEOUT, "timeout"
        except ValueError, TypeError, KeyError, RecursionError, UnicodeError:
            status, reason = CapabilityStatus.ERROR, "invalid_or_incomplete_output"
        except OSError, RuntimeError, SubprocessError:
            status, reason = CapabilityStatus.ERROR, "execution_incomplete"
        return self._failure(status, reason)

    def _failure(self, status, reason):
        allowed = {
            "authorization_refused",
            "request_budget_exceeded",
            "invalid_payload",
            "approval_or_source_changed",
            "dns_changed",
            "dns_unverified",
            "egress_unverified",
            "isolation_unavailable",
            "host_network_denied",
            "provider_integrity",
            "provider_not_static",
            "provider_version_unverified",
            "template_integrity",
            "redirect_refused",
            "timeout",
            "invalid_or_incomplete_output",
            "execution_incomplete",
            "capability_disabled",
        }
        return CapabilityResult(
            "web.detect.restricted",
            status,
            SDKAuthority.EXECUTION_CAPABLE,
            "Restricted detection did not complete",
            diagnostics={
                "reason": reason if reason in allowed else "execution_incomplete"
            },
        )


def _current_policy(settings):
    enabled = any(
        item["id"] == "beescan" and item["enabled"] is True
        for item in settings["modules"]["registry"]
    )
    if not enabled or settings.get("beescan", {}).get("detection_enabled") is not True:
        raise PermissionError("capability_disabled")
    return DetectionPolicy.from_config(settings["beescan"]["detection_approval"])


def execute_approved_detection(
    *,
    settings,
    reload_settings,
    storage_dir: Path,
    logger: logging.Logger,
    assessment_source=None,
    http_signals=False,
    on_complete=None,
    on_started=None,
):
    run_id = generate_run_id()
    artifacts = ArtifactAPI(
        RuntimeContext(
            run_id=run_id,
            session_id=generate_session_id(),
            case_type="restricted_detection",
            module_id="beescan",
            authority=AuthorityLevel.EXECUTION_CAPABLE,
        ),
        storage_dir,
        logger,
    )
    status = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "incomplete",
        "complete": False,
        "reason": "execution_incomplete",
        "evidence_refs": [],
    }
    artifacts.artifact_dir().chmod(0o700)
    _persist(artifacts, "detection_status.json", status)
    if on_started is not None:
        on_started(run_id)
    outcome = evidence_record = None
    candidates = ()
    try:

        def current_policy(current_settings):
            configured = _current_policy(current_settings)
            return (
                assessment_source.bind(configured) if assessment_source else configured
            )

        policy = current_policy(settings)
        policy.authorize_operator(operator_uid=os.getuid(), at=datetime.now(UTC))
        from beescan.capabilities.detection import (
            correlate_detections,
            normalize_detection,
        )

        observation = load_source(storage_dir, policy)
        if assessment_source and observation != assessment_source.observation:
            raise PermissionError("approval_or_source_changed")
        intent = policy.intent(observation, at=datetime.now(UTC))
        caller = GovernedDetectionCaller(
            policy=policy,
            reload_policy=lambda: current_policy(reload_settings()),
            observation=observation,
            storage_dir=storage_dir,
            run_id=run_id,
            artifacts=artifacts,
            http_signals=http_signals,
        )
        result = caller.call(intent.capability_name, intent.payload)
        status.update(
            status=result.status.value, reason=result.diagnostics.get("reason", "ok")
        )
        if result.status is CapabilityStatus.OK:
            provenance = caller.provenance
            evidence_record = caller.evidence_record
            if provenance is None or evidence_record is None:
                raise ValueError("missing_host_evidence")
            outcome = normalize_detection(
                intent, result, provenance=provenance, facts=caller.facts
            )
            candidates = correlate_detections((outcome,))
            _persist(
                artifacts,
                "detection_intent.json",
                {"schema_version": 1, **asdict(intent)},
            )
            _persist(
                artifacts,
                "detection_outcome.json",
                {"schema_version": 1, **asdict(outcome)},
            )
            _persist(
                artifacts,
                "detection_candidates.json",
                {
                    "schema_version": 1,
                    "candidates": [asdict(candidate) for candidate in candidates],
                },
            )
            status.update(
                status=outcome.status.value,
                complete=outcome.status.value in {"matched", "no_match"},
                evidence_refs=list(outcome.evidence_refs),
                source_run_id=policy.source_run_id,
                source_observation_id=observation.observation_id,
                provenance=asdict(provenance),
            )
    except PermissionError:
        status.update(status="refused", reason="authorization_refused", complete=False)
    except ImportError:
        status.update(
            status="refused", reason="detection_contract_unavailable", complete=False
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
            reason="execution_or_artifact_incomplete",
            complete=False,
            evidence_refs=[],
        )
    pending = _persist(artifacts, "detection_status.pending.json", status)
    os.replace(pending, artifacts.artifact_dir() / "detection_status.json")
    if (
        status["complete"]
        and outcome is not None
        and outcome.status.value in {"matched", "no_match"}
        and evidence_record is not None
        and on_complete is not None
    ):
        on_complete(outcome, candidates, evidence_record)
    logger.info("BeeScan detection: run_id=%s status=%s", run_id, status["status"])
    return status
