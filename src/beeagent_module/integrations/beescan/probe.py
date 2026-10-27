import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from subprocess import SubprocessError
from threading import Lock
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from uuid import uuid4

from beesdk.capabilities import CapabilityResult, CapabilityStatus
from beesdk.modules import AuthorityLevel as SDKAuthority

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)
from beeagent_module.integrations.beescan.http_runner import (
    run_provider,
    verify_resolution,
)
from beeagent_module.integrations.beescan.policy import ProbePolicy

if TYPE_CHECKING:
    from beescan.capabilities.http_probe import HttpFacts


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_provider_output")
        result[key] = value
    return result


def parse_http_output(raw, intent, provenance, evidence_refs, *, limit, connected_ip):
    from beescan.capabilities.http_probe import HttpFacts

    if type(raw) is not bytes or not 1 <= len(raw) <= limit:
        raise ValueError("invalid_provider_output")
    try:
        record = json.loads(raw, object_pairs_hook=_unique_object)
        if type(record) is not dict:
            raise ValueError
        allowed = {
            "url",
            "status_code",
            "failed",
            "content_type",
            "method",
            "timestamp",
            "port",
            "input",
            "scheme",
            "host",
            "path",
            "time",
            "a",
            "aaaa",
            "cname",
            "words",
            "lines",
            "content_length",
            "webserver",
            "knowledgebase",
            "tech",
            "location",
            "host_ip",
        }
        if not set(record) <= allowed:
            raise ValueError
        if not {"url", "status_code", "failed"}.issubset(record):
            raise ValueError
        if type(record["url"]) is not str or record["url"] not in {
            intent.origin,
            intent.origin + "/",
        }:
            raise ValueError
        if record["failed"] is not False:
            raise ValueError
        if "method" in record and record["method"] != "HEAD":
            raise ValueError
        if "scheme" in record and record["scheme"] != intent.origin.split(":", 1)[0]:
            raise ValueError
        if "input" in record and (
            type(record["input"]) is not str
            or record["input"] not in {intent.origin, intent.origin + "/"}
        ):
            raise ValueError
        origin = urlsplit(intent.origin)
        port = origin.port or {"http": 80, "https": 443}[origin.scheme]
        hostname = origin.hostname
        if "host" in record and (
            type(record["host"]) is not str or record["host"] != hostname
        ):
            raise ValueError
        if "host_ip" in record and (
            type(record["host_ip"]) is not str or record["host_ip"] != connected_ip
        ):
            raise ValueError
        if "port" in record and (
            type(record["port"]) is not str or record["port"] != str(port)
        ):
            raise ValueError
        if "path" in record and (
            type(record["path"]) is not str or record["path"] != "/"
        ):
            raise ValueError
        content_type = record.get("content_type")
        if content_type is not None:
            if (
                type(content_type) is not str
                or len(content_type) > 256
                or any(ord(c) < 32 or ord(c) == 127 for c in content_type)
            ):
                raise ValueError
            content_type = content_type.split(";", 1)[0].strip().lower()
        return HttpFacts(
            intent.origin,
            True,
            record["status_code"],
            content_type,
            provenance,
            evidence_refs,
            True,
        )
    except ValueError, TypeError, KeyError, RecursionError, UnicodeError:
        raise ValueError("invalid_provider_output") from None


class GovernedHttpCaller:
    def __init__(self, *, policy, reload_policy, run_id, artifacts):
        self.policy = policy
        self.reload_policy = reload_policy
        self.run_id = run_id
        self.artifacts = artifacts
        self.facts: HttpFacts | None = None
        self._lock = Lock()
        self._used = False

    def call(self, capability_name, payload):
        from beescan.capabilities.http_probe import HostProvenance

        from beeagent_module.integrations.beescan.detection import _persist

        status = CapabilityStatus.REFUSED
        reason = "authorization_refused"
        with self._lock:
            if self._used:
                return self._result(status, "request_budget_exceeded")
            self._used = True
        intent = self.policy.intent()
        if (
            capability_name != "web.probe"
            or type(payload) is not dict
            or payload != intent.payload
            or any(type(payload[k]) is not type(v) for k, v in intent.payload.items())
        ):
            return self._result(status, "invalid_payload")
        try:
            self._authorize(intent)
            verify_resolution(self.policy)
            provenance = HostProvenance(
                self.run_id,
                intent.provider_id,
                intent.provider_version,
            )
            raw = run_provider(
                self.policy, reauthorize=lambda: self._authorize(intent, resolve=True)
            )
            ref = "http-evidence-" + uuid4().hex
            facts = parse_http_output(
                raw,
                intent,
                provenance,
                (ref,),
                limit=self.policy.output_bytes,
                connected_ip=self.policy.connected_ip,
            )
            self._authorize(intent)
            self.artifacts.artifact_dir().chmod(0o700)
            _persist(
                self.artifacts, ref + ".json", {"schema_version": 1, **asdict(facts)}
            )
            self.facts = facts
            return CapabilityResult(
                "web.probe",
                CapabilityStatus.OK,
                SDKAuthority.EXECUTION_CAPABLE,
                "HTTP probe completed",
                {"evidence_refs": [ref]},
            )
        except PermissionError as error:
            reason = str(error)
        except TimeoutError:
            status, reason = CapabilityStatus.TIMEOUT, "timeout"
        except OSError, ValueError, RuntimeError, SubprocessError:
            status, reason = CapabilityStatus.ERROR, "execution_incomplete"
        return self._result(status, reason)

    def _authorize(self, intent, *, resolve=False):
        current = self.reload_policy()
        if current != self.policy:
            raise PermissionError("approval_changed")
        current.authorize(intent, operator_uid=os.getuid(), at=datetime.now(UTC))
        if resolve:
            verify_resolution(current)

    def _result(self, status, reason):
        allowed = {
            "authorization_refused",
            "request_budget_exceeded",
            "invalid_payload",
            "approval_changed",
            "dns_changed",
            "dns_unverified",
            "egress_unverified",
            "isolation_unavailable",
            "host_network_denied",
            "provider_integrity",
            "provider_not_static",
            "provider_version_unverified",
            "timeout",
            "execution_incomplete",
            "capability_disabled",
        }
        safe_reason = reason if reason in allowed else "execution_incomplete"
        return CapabilityResult(
            "web.probe",
            status,
            SDKAuthority.EXECUTION_CAPABLE,
            "HTTP probe did not complete",
            diagnostics={"reason": safe_reason},
        )


def execute_approved_probe(
    *,
    settings,
    reload_settings,
    storage_dir: Path,
    logger: logging.Logger,
    on_complete=None,
    on_started=None,
):
    from beescan.capabilities.http_probe import (
        normalize_http_observation,
        normalize_http_probe,
    )

    from beeagent_module.integrations.beescan.detection import _persist

    run_id, session_id = generate_run_id(), generate_session_id()
    artifacts = ArtifactAPI(
        RuntimeContext(
            run_id=run_id,
            session_id=session_id,
            case_type="http_probe",
            module_id="beescan",
            authority=AuthorityLevel.EXECUTION_CAPABLE,
        ),
        storage_dir,
        logger,
    )
    artifacts.artifact_dir().chmod(0o700)
    if on_started is not None:
        on_started(run_id)
    status = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "refused",
        "complete": False,
        "reason": "capability_disabled",
        "evidence_refs": [],
    }
    observation = None
    config = settings.get("beescan", {})
    enabled = any(
        item["id"] == "beescan" and item["enabled"] is True
        for item in settings["modules"]["registry"]
    )
    if enabled and config.get("probe_enabled") is True:
        policy = ProbePolicy.from_config(config["approval"])
        caller = GovernedHttpCaller(
            policy=policy,
            run_id=run_id,
            artifacts=artifacts,
            reload_policy=lambda: _current_policy(reload_settings()),
        )
        intent = policy.intent()
        result = caller.call(intent.capability_name, intent.payload)
        status.update(
            status=result.status.value, reason=result.diagnostics.get("reason", "ok")
        )
        if result.status is CapabilityStatus.OK:
            try:
                facts = caller.facts
                if facts is None:
                    raise ValueError("missing_host_facts")
                outcome = normalize_http_probe(
                    intent, result, provenance=facts.provenance
                )
                observation = normalize_http_observation(intent, outcome, facts)
                _persist(
                    artifacts,
                    "http_observation.json",
                    {"schema_version": 1, **asdict(observation)},
                )
                status.update(
                    complete=True,
                    evidence_refs=list(outcome.evidence_refs),
                    mission_id=intent.mission_id,
                    target_id=intent.target_id,
                    project_id=policy.project_id,
                    scope_id=policy.scope_id,
                    provenance=asdict(facts.provenance),
                )
            except OSError, ValueError:
                status.update(
                    status="error", reason="artifact_incomplete", complete=False
                )
    _persist(artifacts, "http_probe_status.json", status)
    if status["complete"] and observation is not None and on_complete is not None:
        on_complete(observation)
    logger.info(
        "BeeScan HTTP probe: run_id=%s status=%s reason=%s",
        run_id,
        status["status"],
        status["reason"],
    )
    return status


def _current_policy(settings):
    enabled = any(
        item["id"] == "beescan" and item["enabled"] is True
        for item in settings["modules"]["registry"]
    )
    if not enabled or settings.get("beescan", {}).get("probe_enabled") is not True:
        raise PermissionError("capability_disabled")
    return ProbePolicy.from_config(settings["beescan"]["approval"])


def handle_beescan_cli(
    args, *, settings, reload_settings, storage_dir, logger, local_operator=None
):
    if not args or args[0] == "investigate":
        from beeagent_module.integrations.beescan.investigation import (
            execute_investigation,
            validate_task,
        )

        options = {}
        try:
            if not args:
                if not sys.stdin.isatty():
                    raise ValueError("terminal_required")
                config = settings["beescan"]["investigation"]
                value = {}
                for key, limit in (
                    ("target", 2048),
                    ("task", config["task_chars_max"]),
                ):
                    print(key.capitalize() + ": ", end="", flush=True, file=sys.stderr)
                    line = sys.stdin.readline(limit + 2)
                    if not line or not line.endswith("\n") or len(line[:-1]) > limit:
                        raise ValueError("invalid_terminal_input")
                    value[key] = line[:-1]
                options["task"] = validate_task(value, config)
            elif len(args) == 2 and not args[1].startswith("-"):
                options["task_path"] = args[1]
            else:
                if (
                    len(args) != 5
                    or {args[1], args[3]} != {"--target", "--task"}
                    or args[2].startswith("--")
                    or args[4].startswith("--")
                ):
                    raise ValueError("invalid_arguments")
                value = {args[i][2:]: args[i + 1] for i in (1, 3)}
                options["task"] = validate_task(
                    value, settings["beescan"]["investigation"]
                )
        except KeyboardInterrupt:
            print("BeeScan input cancelled", file=sys.stderr)
            return 130
        except KeyError, OSError, ValueError, ImportError:
            print(
                "Usage: ./start.sh beescan [investigate TASK.json | "
                "investigate --target URL --task TEXT]",
                file=sys.stderr,
            )
            return 2
        if "task" in options:
            options["local_operator"] = local_operator
            options["progress"] = lambda stage: print(
                "BeeScan: " + stage, file=sys.stderr, flush=True
            )
        try:
            result = execute_investigation(
                **options,
                settings=settings,
                reload_settings=reload_settings,
                storage_dir=storage_dir,
                logger=logger,
            )
        except ImportError, OSError, RuntimeError, ValueError:
            logger.error("BeeScan investigation incomplete")
            return 5
        print(json.dumps(result, sort_keys=True))
        if result["complete"] and result["status"] in {"MATCH", "NO_MATCH"}:
            return 0
        return {"REFUSED": 3, "TIMEOUT": 4}.get(result["status"], 5)
    review_invocation = len(args) == 4 and args[0] == "review"
    if not review_invocation and args not in (
        ["bootstrap"],
        ["probe"],
        ["detect"],
        ["assess"],
        ["assess", "--http-signals"],
        ["assess", "--git-exposure"],
        ["assess", "--http-signals", "--git-exposure"],
        ["assess", "--git-exposure", "--http-signals"],
    ):
        print(
            "Usage: ./start.sh beescan {bootstrap|probe|detect|assess [--http-signals] [--git-exposure]|review ASSESSMENT FINDING INPUT.json}"
        )
        return 2
    try:
        registry_config = settings["modules"]["registry"]
        if review_invocation:
            registry_config = [
                item for item in registry_config if item["id"] == "beescan"
            ]
        registry = ModuleRegistry(registry_config, logger)
        if registry.get("beescan") is None:
            print("BeeScan module is disabled or unavailable")
            return 3
        if review_invocation:
            from beeagent_module.integrations.beescan.review import execute_review

            result = execute_review(
                settings=settings,
                reload_settings=reload_settings,
                storage_dir=storage_dir,
                logger=logger,
                assessment_run_id=args[1],
                finding_id=args[2],
                input_name=args[3],
            )
            print(json.dumps(result, sort_keys=True))
            return (
                0 if result["complete"] else 3 if result["status"] == "refused" else 5
            )
        if args == ["bootstrap"]:
            result = execute_module_case(
                registry,
                "beescan",
                "bootstrap_health",
                {},
                storage_dir,
                logger,
            )
            print(result.summary)
            return 0 if result.status == "ok" else 3
        execute = execute_approved_probe
        if args == ["detect"]:
            from beeagent_module.integrations.beescan.detection import (
                execute_approved_detection,
            )

            execute = execute_approved_detection
        elif args[0] == "assess":
            from beeagent_module.integrations.beescan.assessment import (
                execute_approved_assessment,
            )

            execute = execute_approved_assessment
        options = {"http_signals": True} if "--http-signals" in args else {}
        if "--git-exposure" in args:
            options["git_exposure"] = True
        result = execute(
            **options,
            settings=settings,
            reload_settings=reload_settings,
            storage_dir=storage_dir,
            logger=logger,
        )
        print(json.dumps(result, sort_keys=True))
        return {"ok": 0, "matched": 0, "no_match": 0, "refused": 3, "timeout": 4}.get(
            result["status"], 5
        )
    except ImportError, OSError, RuntimeError, ValueError, SubprocessError:
        logger.error("BeeScan invocation incomplete")
        print("BeeScan invocation incomplete; inspect host prerequisites")
        return 5
