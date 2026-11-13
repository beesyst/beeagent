import fcntl
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import stat
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from itertools import islice

from beeagent_module.integrations.beescan.case_state import digest, load_case
from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.integrations.beescan.investigation import (
    InvestigationPolicy,
    execute_investigation,
    validate_task,
)
from beeagent_module.integrations.beescan.review_source import (
    AssessmentSnapshot,
    open_child,
    open_directory,
)

PROFILES = {
    "quick": {"max_steps": 2, "max_requests": 2, "max_depth": 1},
    "standard": {"max_steps": 8, "max_requests": 10, "max_depth": 3},
    "deep": {"max_steps": 16, "max_requests": 20, "max_depth": 4},
}
_SEAL = object()


def record_failure(storage, logger, run_id, error, phase):
    from beeagent_module.integrations.beescan.assessment import _write_report
    from beeagent_module.integrations.beescan.dast import _api

    category = next(
        (
            name
            for kind, name in (
                (TimeoutError, "deadline"),
                (PermissionError, "authorization"),
                (OSError, "storage"),
                (ValueError, "validation"),
                (RuntimeError, "runtime"),
            )
            if isinstance(error, kind)
        ),
        "unexpected",
    )
    logger.error(
        "BeeScan Web failure: run_id=%s category=%s phase=%s",
        run_id,
        category,
        phase,
    )
    try:
        lines = [
            f"{datetime.now(UTC).isoformat()} run_id={run_id} "
            f"category={category} phase={phase}",
            "Traceback (frames only; exception values and source omitted):",
        ]
        for frame, line in islice(traceback.walk_tb(error.__traceback__), 32):
            filename = os.path.basename(frame.f_code.co_filename)
            filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)[:96]
            function = re.sub(r"[^a-zA-Z0-9_]", "_", frame.f_code.co_name)[:96]
            lines.append(f"  {filename}:{line} in {function}")
        snapshot = AssessmentSnapshot(storage)
        try:
            previous = snapshot.read(run_id, "web_failure.log").decode("utf-8")
        except FileNotFoundError:
            previous = ""
        _write_report(
            _api(storage, run_id, logger),
            "web_failure.log",
            previous[-32768:] + "\n".join(lines) + "\n",
        )
    except Exception:
        logger.error("BeeScan Web diagnostic unavailable: run_id=%s", run_id)


def validate_web_settings(settings):
    config = settings.get("beescan", {}).get("investigation", {})
    if "web" not in config:
        return
    web = config["web"]
    principals = settings.get("web", {}).get("auth", {}).get("principals", [])
    if type(principals) is not list or any(
        type(item) is not dict or type(item.get("id")) is not str for item in principals
    ):
        raise RuntimeError("Invalid Web principals")
    ids = {item["id"] for item in principals}
    if (
        type(web) is not dict
        or set(web) != {"enabled", "principal_ids"}
        or type(web["enabled"]) is not bool
        or type(web["principal_ids"]) is not list
        or any(
            type(value) is not str or value not in ids for value in web["principal_ids"]
        )
        or len(set(web["principal_ids"])) != len(web["principal_ids"])
        or web["enabled"]
        and (
            not web["principal_ids"]
            or settings.get("web", {}).get("auth", {}).get("enabled") is not True
            or config.get("enabled") is not True
            or config.get("approval") is None
            and "target_policy" not in settings.get("beescan", {})
            or not config.get("adaptive", {}).get("max_depth")
        )
    ):
        raise RuntimeError("Invalid beescan.investigation.web settings")
    if "target_policy" in settings.get("beescan", {}):
        from beeagent_module.integrations.beescan.policy import target_exclusions

        target_exclusions(settings)


def principal(settings, actor, *, execute=False):
    if settings.get("web", {}).get("auth", {}).get("enabled") is not True:
        raise PermissionError("web_auth_required")
    if type(actor) is not dict:
        raise PermissionError("web_principal_required")
    records = settings["web"]["auth"]["principals"]
    record = next((p for p in records if p["id"] == actor.get("user_id")), None)
    if record is None or record["role"] != actor.get("role"):
        raise PermissionError("web_principal_changed")
    scopes = set(record["scopes"])
    wildcard = record["role"] == "admin" and scopes == {"*"}
    if not wildcard and "beescan" not in scopes:
        raise PermissionError("beescan_scope_required")
    if execute and (
        record["role"] not in {"operator", "admin"}
        or not wildcard
        and "beescan.investigate" not in scopes
    ):
        raise PermissionError("beescan_execution_required")
    return record["id"]


def _key(settings):
    name = settings["web"]["auth"]["session_secret_env"]
    key = os.getenv(name, "")
    if not key:
        raise PermissionError("web_signing_key_unavailable")
    return hmac.digest(key.encode(), b"beeagent-beescan-web-v1", "sha256")


def _sign(settings, value):
    return hmac.digest(_key(settings), digest(value).encode(), "sha256").hex()


def _read_owned(storage, settings, run_id, actor):
    record = AssessmentSnapshot(storage).json(run_id, "web_owner.json")
    if set(record) != {"binding", "signature"}:
        raise PermissionError("web_ownership_invalid")
    binding = record["binding"]
    if (
        type(binding) is not dict
        or not hmac.compare_digest(_sign(settings, binding), str(record["signature"]))
        or binding.get("run_id") != run_id
        or binding.get("principal_id") != principal(settings, actor)
    ):
        raise PermissionError("web_ownership_refused")
    return binding


class _WebInvocation:
    def __init__(self, service, actor, task, mode, run_id, case_id, seal):
        self.service = service
        self.actor = dict(actor)
        self.task = task
        self.mode = mode
        self.run_id = run_id
        self.case_id = case_id
        self.seal = seal
        self.settings = deepcopy(service.reload_settings())
        self.created_at = datetime.now(UTC).isoformat()
        self._verify_authority()
        self.dynamic = "target_policy" in self.settings["beescan"]
        if self.dynamic:
            from beeagent_module.integrations.beescan.policy import web_execution_policy

            bound = None
            if case_id != run_id:
                owned = _read_owned(service.storage, self.settings, case_id, self.actor)
                bound = owned.get("destination_ip")
                if bound is None:
                    state, snapshot = load_case(service.storage, case_id)
                    bound = state.get("discovery", state).get("connected_ip")
                    snapshot.verify()
            self.policy = web_execution_policy(
                self.settings, task.target, case_id, connected_ip=bound
            )
        else:
            self.policy = InvestigationPolicy.from_config(
                self.settings["beescan"]["investigation"]["approval"]
            )
        self.verify()

    def _verify_authority(self):
        if self.seal is not _SEAL or self.service.reload_settings() != self.settings:
            raise PermissionError("web_authority_changed")
        actor_id = principal(self.settings, self.actor, execute=True)
        config = self.settings["beescan"]["investigation"]
        web = config.get("web", {})
        if (
            web.get("enabled") is not True
            or actor_id not in web.get("principal_ids", [])
            or config.get("enabled") is not True
            or not any(
                p.get("id") == "beescan" and p.get("enabled") is True
                for p in self.settings.get("modules", {}).get("registry", [])
            )
        ):
            raise PermissionError("web_investigation_not_approved")

    def verify(self, policy=None):
        self._verify_authority()
        if policy is not None and policy != self.policy:
            raise PermissionError("web_investigation_not_approved")
        self.policy.authorize(self.task.target, at=datetime.now(UTC))
        if self.dynamic:
            from beeagent_module.integrations.beescan.policy import check_web_target

            check_web_target(
                self.settings,
                self.task.target,
                connected_ip=self.policy.transport.connected_ip,
            )

    def effective_settings(self):
        self.verify()
        result = deepcopy(self.settings)
        if self.dynamic:
            from beeagent_module.integrations.beescan.dast import _plain

            config = result["beescan"]["investigation"]
            config["approval"] = _plain(self.policy)
            active = result["beescan"].get("dast", {})
            if active.get("enabled") is True and self.task.target.startswith("https:"):
                active["approval"] = {
                    "transport": _plain(self.policy)["transport"],
                    "approved": True,
                    "method": "active_dast",
                    "entries": [],
                    "entry_selection": "authenticated_discovery",
                    "max_candidates": 1,
                    "profile": "traversal-nonrecursive-v1",
                    "request_budget": 10,
                    "seconds": min(55, max(10, config["timeout_seconds"])),
                }
        limits = result["beescan"]["investigation"]["adaptive"]
        for key, maximum in PROFILES[self.mode].items():
            limits[key] = min(limits[key], maximum)
        return result

    def provenance(self):
        return {
            "authority_source": "authenticated_web_principal",
            "principal_id": self.actor["user_id"],
            "third_party_authorization_verified": False,
            "origin": self.policy.transport.origin,
            "scope_id": self.policy.transport.scope_id,
            "mode": self.mode,
        }

    def bind(self, api, run_id):
        self.verify()
        binding = {
            "run_id": run_id,
            "case_id": self.case_id,
            "principal_id": self.actor["user_id"],
            "task_sha256": digest(self.task.task),
            "target": self.task.target,
            "mode": self.mode,
            "authority_sha256": digest(self.settings["beescan"]),
        }
        if self.dynamic:
            binding["destination_ip"] = self.policy.transport.connected_ip
        path = api.artifact_dir() / "web_owner.json"
        if path.exists():
            old = _read_owned(self.service.storage, self.settings, run_id, self.actor)
            if "created_at" in old:
                binding["created_at"] = old["created_at"]
            if "destination_ip" not in old:
                binding.pop("destination_ip", None)
            if old != binding:
                raise PermissionError("web_binding_changed")
        else:
            binding["created_at"] = self.created_at
            _persist(
                api,
                "web_owner.json",
                {"binding": binding, "signature": _sign(self.settings, binding)},
            )


class WebInvestigations:
    def __init__(self, storage, settings, reload_settings):
        self.storage = storage
        self.settings = settings
        self.reload_settings = reload_settings
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="beescan-web"
        )
        self.logger = logging.getLogger(__name__)

    def nonce(self, actor):
        actor_id = principal(self.settings, actor)
        value = f"{int(time.time())}.{secrets.token_hex(16)}"
        return value + "." + _sign(self.settings, [actor_id, value])

    def _run_id(self, actor, nonce):
        if type(nonce) is not str or not re.fullmatch(
            r"[0-9]{10}\.[0-9a-f]{32}\.[0-9a-f]{64}", nonce
        ):
            raise ValueError("invalid_web_nonce")
        timestamp, random, signature = nonce.split(".")
        if not 0 <= time.time() - int(timestamp) <= 600 or not hmac.compare_digest(
            signature,
            _sign(self.settings, [actor["user_id"], timestamp + "." + random]),
        ):
            raise PermissionError("web_nonce_refused")
        return "web-" + hashlib.sha256(nonce.encode()).hexdigest()[:48]

    def start(self, action, payload, actor):
        current = self.reload_settings()
        principal(current, actor, execute=True)
        expected = {"target", "task", "mode", "nonce"}
        if action == "beescan_resume":
            expected.add("case_id")
        if (
            action not in {"beescan_start", "beescan_resume"}
            or type(payload) is not dict
            or set(payload) != expected
            or type(payload["mode"]) is not str
            or payload["mode"] not in PROFILES
        ):
            raise ValueError("invalid_web_action")
        task = validate_task(
            {key: payload[key] for key in ("target", "task")},
            current["beescan"]["investigation"],
        )
        if "target_policy" in current["beescan"]:
            from beescan.domain.locators import canonical_locator
            from beescan.domain.models import TargetKind

            from beeagent_module.integrations.beescan.investigation import (
                InvestigationTask,
            )

            task = InvestigationTask(
                canonical_locator(TargetKind.URL, task.target), task.task
            )
        run_id = self._run_id(actor, payload["nonce"])
        case_id = payload.get("case_id", run_id)
        try:
            invocation = _WebInvocation(
                self, actor, task, payload["mode"], run_id, case_id, _SEAL
            )
            from beeagent_module.integrations.beescan.dast import _current, is_dast_task

            if is_dast_task(task.task):
                if invocation.dynamic and not task.target.startswith("https:"):
                    raise PermissionError("web_dast_profile_unsupported")
                active = _current(
                    invocation.effective_settings(), web_invocation=invocation
                )
                active.authorize(invocation, at=datetime.now(UTC))
                if (
                    active.entry_selection != "authenticated_discovery"
                    or active.profile == "traversal-nonrecursive-v1"
                    and payload["mode"] == "quick"
                ):
                    raise PermissionError("web_dast_profile_unsupported")
        except PermissionError as error:
            if "target_policy" not in current["beescan"] or str(error) not in {
                "target_excluded",
                "internal_destination_denied",
                "dns_changed",
                "dns_unverified",
                "web_dast_profile_unsupported",
                "active_dast_not_approved",
            }:
                raise
            return self._refuse(
                current, actor, task, payload["mode"], run_id, str(error)
            )
        prior = None
        reused = None
        if action == "beescan_resume":
            prior = _read_owned(self.storage, current, case_id, actor)
            if any(
                prior[key] != value
                for key, value in {
                    "task_sha256": digest(task.task),
                    "target": task.target,
                    "mode": payload["mode"],
                    "authority_sha256": digest(current["beescan"]),
                }.items()
            ):
                raise PermissionError("web_resume_identity_changed")
            state, snapshot = load_case(self.storage, case_id)
            receipt = snapshot.json(case_id, "web_receipt.json")
            if receipt != self._receipt(snapshot, current):
                raise PermissionError("web_checkpoint_changed")
            snapshot.verify()
            if state["pending"]:
                raise PermissionError("web_checkpoint_pending")
            if state.get("terminal") or state["status"] in {"CANDIDATE", "NO_MATCH"}:
                discovery = state.get("discovery", state)
                reused = {
                    "case_id": case_id,
                    "run_id": discovery["segments"][-1],
                    "status": state["status"],
                    "reused": True,
                }
        self.storage.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = open_directory(self.storage)
        try:
            try:
                os.mkdir("runs", mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            runs = open_child(descriptor, "runs")
        finally:
            os.close(descriptor)
        try:
            fcntl.flock(runs, fcntl.LOCK_EX | fcntl.LOCK_NB)
            invocation.verify()
            os.mkdir(run_id, mode=0o700, dir_fd=runs)
            from beeagent_module.integrations.beescan.dast import _api

            api = _api(self.storage, run_id, self.logger)
            invocation.bind(api, run_id)
            if prior is None:
                intake = {
                    "case_id": case_id,
                    "target": task.target,
                    "task": task.task,
                    "mode": payload["mode"],
                }
                _persist(
                    api,
                    "web_intake.json",
                    {
                        "intake": intake,
                        "signature": _sign(current, intake),
                    },
                )
            _persist(
                api,
                "investigation_status.json",
                {
                    "run_id": run_id,
                    "case_id": case_id,
                    "status": reused["status"] if reused else "QUEUED",
                    "complete": bool(
                        reused
                        and reused["status"] in {"MATCH", "CANDIDATE", "NO_MATCH"}
                    ),
                    "request_count": 0,
                    "reason": (
                        "authenticated_case_reused" if reused else "execution_pending"
                    ),
                },
            )
            descriptor = open_directory(api.artifact_dir())
            try:
                os.fsync(descriptor)
                os.fsync(runs)
            finally:
                os.close(descriptor)
            if reused:
                os.close(runs)
                return reused
            self.executor.submit(self._execute, invocation, prior, runs)
        except BaseException:
            os.close(runs)
            raise
        return {"case_id": case_id, "run_id": run_id, "status": "QUEUED"}

    def _refuse(self, settings, actor, task, mode, run_id, reason):
        from beeagent_module.integrations.beescan.dast import _api

        principal_id = principal(settings, actor, execute=True)
        if self.reload_settings() != settings:
            raise PermissionError("web_authority_changed")
        self.storage.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = open_directory(self.storage)
        try:
            try:
                os.mkdir("runs", 0o700, dir_fd=root)
            except FileExistsError:
                pass
            runs = open_child(root, "runs")
        finally:
            os.close(root)
        try:
            fcntl.flock(runs, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.mkdir(run_id, 0o700, dir_fd=runs)
            api = _api(self.storage, run_id, self.logger)
            binding = {
                "run_id": run_id,
                "case_id": run_id,
                "created_at": datetime.now(UTC).isoformat(),
                "principal_id": principal_id,
                "task_sha256": digest(task.task),
                "target": task.target,
                "mode": mode,
                "authority_sha256": digest(settings["beescan"]),
            }
            intake = {
                "case_id": run_id,
                "target": task.target,
                "task": task.task,
                "mode": mode,
            }
            _persist(
                api,
                "web_owner.json",
                {"binding": binding, "signature": _sign(settings, binding)},
            )
            _persist(
                api,
                "web_intake.json",
                {"intake": intake, "signature": _sign(settings, intake)},
            )
            _persist(
                api,
                "investigation_status.json",
                {
                    "run_id": run_id,
                    "case_id": run_id,
                    "status": "REFUSED",
                    "complete": False,
                    "request_count": 0,
                    "request_count_exact": True,
                    "reason": reason,
                },
            )
            os.fsync(runs)
        finally:
            os.close(runs)
        return {"case_id": run_id, "run_id": run_id, "status": "REFUSED"}

    def _receipt(self, snapshot, settings):
        cases = [key for key in snapshot.files if key[1] == "case.json"]
        if len(cases) != 1:
            raise ValueError("invalid_web_case_receipt")
        state = snapshot.json(*cases[0])["state"]
        for run_id in state.get("discovery", state)["segments"]:
            for name in (
                "investigation_status.json",
                "investigation_result.json",
                "investigation_steps.json",
                "report.json",
                "report.md",
            ):
                snapshot.read(run_id, name)
        values = {
            run + "/" + name: hashlib.sha256(raw).hexdigest()
            for (run, name), raw in snapshot.files.items()
            if name != "web_receipt.json"
        }
        return {"files": values, "signature": _sign(settings, values)}

    def _execute(self, invocation, prior, lock):
        phase = "execution"
        try:
            result = execute_investigation(
                task=invocation.task,
                web_invocation=invocation,
                settings=invocation.effective_settings(),
                reload_settings=invocation.effective_settings,
                storage_dir=self.storage,
                logger=self.logger,
                general=True,
                resume_case_id=invocation.case_id if prior else None,
            )
            if result.get("case_id"):
                phase = "case_authentication"
                _, snapshot = load_case(self.storage, invocation.case_id)
                from beeagent_module.integrations.beescan.dast import _api

                api = _api(self.storage, invocation.case_id, self.logger)
                phase = "receipt_publication"
                _persist(
                    api,
                    "web_receipt.json",
                    self._receipt(snapshot, invocation.settings),
                )
            self.logger.info("BeeScan Web completed: run_id=%s", invocation.run_id)
        except Exception as error:
            record_failure(self.storage, self.logger, invocation.run_id, error, phase)
            try:
                from beeagent_module.integrations.beescan.dast import _api

                snapshot = AssessmentSnapshot(self.storage)
                try:
                    published = snapshot.json(
                        invocation.run_id, "investigation_status.json"
                    )
                except FileNotFoundError:
                    published = {}
                if published.get("status") in {"ERROR", "REFUSED", "TIMEOUT"}:
                    snapshot.verify()
                    return
                if published.get("status") not in {None, "QUEUED", "RUNNING"}:
                    try:
                        state, source = load_case(self.storage, invocation.case_id)
                        source.verify()
                        snapshot.verify()
                        if state["status"] == published["status"]:
                            return
                    except OSError, ValueError, RuntimeError:
                        pass
                count = published.get("request_count")
                if type(count) is not int or not 0 <= count <= 256:
                    count = None
                api = _api(self.storage, invocation.run_id, self.logger)
                _persist(
                    api,
                    "investigation_status.json",
                    {
                        "run_id": invocation.run_id,
                        "case_id": invocation.case_id,
                        "status": "ERROR",
                        "reason": "web_execution_incomplete",
                        "complete": False,
                        "request_count": count,
                        "request_count_exact": False,
                    },
                )
            except OSError, ValueError:
                self.logger.error("BeeScan Web publication failed")
        finally:
            os.close(lock)

    def inspect(self, run_id, actor, *, latest=True, summary=False):
        for _ in range(2):
            try:
                return self._inspect(run_id, actor, latest=latest, **({"summary": True} if summary else {}))
            except ValueError as exc:
                if str(exc) not in {"assessment_source_changed", "web_status_changed"}:
                    raise
        return self._inspect(run_id, actor, latest=latest, **({"summary": True} if summary else {}))

    def _inspect(self, run_id, actor, *, latest=True, summary=False):
        current = self.reload_settings()
        owned = _read_owned(self.storage, current, run_id, actor)
        snapshot = AssessmentSnapshot(self.storage)
        status = snapshot.json(run_id, "investigation_status.json")
        if summary:
            metadata = self.case_metadata(owned["case_id"], actor)
            try:
                intake_record = snapshot.json(owned["case_id"], "web_intake.json")
                intake = intake_record["intake"]
                if intake_record.get("signature") != _sign(current, intake):
                    raise PermissionError("web_intake_changed")
            except FileNotFoundError:
                intake = None
            findings = []
            try:
                receipt = snapshot.json(owned["case_id"], "web_receipt.json")
                if receipt.get("signature") != _sign(current, receipt["files"]):
                    raise PermissionError("web_checkpoint_changed")
                result = snapshot.json(run_id, "investigation_result.json")
                for name in ("investigation_status.json", "investigation_result.json"):
                    if receipt["files"].get(run_id + "/" + name) != hashlib.sha256(snapshot.read(run_id, name)).hexdigest():
                        raise PermissionError("web_checkpoint_changed")
                findings = result.get("findings", [])[:16]
            except FileNotFoundError:
                pass
            snapshot.verify()
            return {
                "case_id": owned["case_id"], "run_id": run_id,
                "status": status["status"], "mode": owned["mode"],
                "intake": intake, "findings": findings,
                "display_title": metadata.get("title") or (intake["task"] if intake else owned["case_id"]),
                "archived": metadata.get("archived", False),
                "created_at": owned.get("created_at"),
                "report_readiness": "unavailable",
            }
        if status.get("status") not in {
            "QUEUED",
            "RUNNING",
            "REFUSED",
            "PARTIAL",
            "ERROR",
            "TIMEOUT",
            "INCONCLUSIVE",
            "MATCH",
            "CANDIDATE",
            "NO_MATCH",
        }:
            raise ValueError("invalid_web_status")
        if status.get("reason") is not None and (
            type(status["reason"]) is not str
            or re.fullmatch(r"[a-z_]{1,80}", status["reason"]) is None
        ):
            raise ValueError("invalid_web_reason")
        if (
            status.get("request_count") is not None
            and (
                type(status["request_count"]) is not int
                or not 0 <= status["request_count"] <= 256
            )
            or type(status.get("complete")) is not bool
            or status.get("request_count_exact") is not None
            and type(status["request_count_exact"]) is not bool
        ):
            raise ValueError("invalid_web_accounting")
        keys = {"status", "complete", "reason", "request_count", "request_count_exact"}
        data = {key: status.get(key) for key in keys}
        data.update(run_id=run_id, case_id=owned["case_id"], mode=owned["mode"])
        metrics = status.get("metrics", {})
        if type(metrics) is not dict:
            raise ValueError("invalid_web_metrics")
        data["metrics"] = {
            key: metrics.get(key)
            for key in (
                "request_count",
                "request_count_exact",
                "elapsed_seconds",
                "ai_calls",
                "tokens",
                "cost",
                "usage_status",
            )
        }
        for value in data["metrics"].values():
            if value is None or type(value) is bool:
                continue
            if type(value) is int or type(value) is float:
                if not math.isfinite(value) or value < 0:
                    raise ValueError("invalid_web_metrics")
            elif value != "unavailable":
                raise ValueError("invalid_web_metrics")
        refs = status.get("evidence_refs", [])
        if type(refs) is not list or len(refs) > 64:
            raise ValueError("invalid_web_evidence")
        data["evidence_refs"] = refs
        if any(
            type(ref) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", ref) is None
            for ref in data["evidence_refs"]
        ):
            raise ValueError("invalid_web_evidence")
        authenticated = False
        state = None
        case_snapshot = None
        try:
            state, case_snapshot = load_case(self.storage, owned["case_id"])
            receipt = case_snapshot.json(owned["case_id"], "web_receipt.json")
            authenticated = receipt == self._receipt(case_snapshot, current)
            data["case_status"] = state["status"]
        except OSError, ValueError:
            data["case_status"] = "unavailable"
        if (
            not authenticated
            and (
                self.storage
                / "runs"
                / owned["case_id"]
                / "module-beescan"
                / "web_receipt.json"
            ).exists()
        ):
            active = False
            descriptor = open_directory(self.storage / "runs")
            try:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
                except BlockingIOError:
                    active = True
            finally:
                os.close(descriptor)
            if not active or run_id == owned["case_id"]:
                raise PermissionError("web_checkpoint_changed")
        data["evidence_authenticated"] = authenticated
        if authenticated and state is not None and latest:
            last_run = state.get("discovery", state)["segments"][-1]
            if last_run != run_id:
                return self.inspect(last_run, actor)
        if authenticated and case_snapshot is not None:
            if case_snapshot.json(run_id, "investigation_status.json") != status:
                raise ValueError("web_status_changed")
            snapshot = case_snapshot
        try:
            result = snapshot.json(run_id, "investigation_result.json")
        except OSError, ValueError:
            result = {}
        if type(result.get("findings", [])) is not list:
            raise ValueError("invalid_web_findings")
        data["findings"] = [
            {
                "finding_id": finding["finding_id"],
                "status": finding["status"],
                "title": "External DAST candidate",
            }
            for finding in (result.get("findings", [])[:16] if authenticated else [])
            if type(finding) is dict
            and finding.get("status") == "candidate"
            and type(finding.get("finding_id")) is str
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", finding["finding_id"])
        ]
        data["report"] = {
            "status": data["status"],
            "reason": data.get("reason"),
            "disposition": (
                "CANDIDATE"
                if authenticated and result.get("disposition") == "CANDIDATE"
                else None
            ),
            "answer": result.get("answer")
            if authenticated
            and result.get("answer")
            in {
                "Requested field established from authenticated source; "
                "value redacted.",
                "Authenticated source/configuration resource observed.",
            }
            else None,
            "limitations": [
                "Only bounded same-origin resources were inspected; "
                "absence of disclosure does not establish target safety.",
                "Sensitive values are transient; "
                "candidates require independent human verification.",
            ],
        }
        try:
            steps = json.loads(snapshot.read(run_id, "investigation_steps.json"))
        except OSError, ValueError:
            steps = []
        if type(steps) is not list or len(steps) > 64:
            raise ValueError("invalid_web_steps")
        data["steps"] = [
            {key: step.get(key) for key in ("step", "status", "request_count")}
            for step in steps[:64]
            if type(step) is dict
        ]
        if any(
            step["step"]
            not in {"discovery", "resource", "baseline", "mutation", "diagnostic"}
            or step["status"]
            not in {"incomplete", "captured", "authenticated", "skipped"}
            or step["request_count"] not in {None, 0, 1}
            for step in data["steps"]
        ):
            raise ValueError("invalid_web_steps")
        for step in data["steps"]:
            step["tool"] = "host-web-capture"
        assessment = status.get("assessment") if authenticated else None
        if assessment is not None:
            if (
                type(assessment) is not dict
                or assessment.get("status")
                not in {"CANDIDATE", "NO_MATCH", "PARTIAL", "ERROR"}
                or type(assessment.get("request_count")) is not int
                or not 0 <= assessment["request_count"] <= 100
            ):
                raise ValueError("invalid_web_assessment")
            data["steps"].append(
                {
                    "step": "active_dast",
                    "tool": "zap",
                    "status": assessment["status"],
                    "request_count": assessment["request_count"],
                }
            )
        data["intake"] = None
        intake_snapshot = AssessmentSnapshot(self.storage)
        try:
            record = intake_snapshot.json(owned["case_id"], "web_intake.json")
        except FileNotFoundError:
            record = None
        if record is not None:
            intake = record.get("intake")
            if (
                type(intake) is not dict
                or set(record) != {"intake", "signature"}
                or set(intake) != {"case_id", "target", "task", "mode"}
                or record["signature"] != _sign(current, intake)
                or intake["case_id"] != owned["case_id"]
                or intake["target"] != owned["target"]
                or intake["mode"] != owned["mode"]
                or digest(intake["task"]) != owned["task_sha256"]
            ):
                raise PermissionError("web_intake_changed")
            validate_task(
                {key: intake[key] for key in ("target", "task")},
                current["beescan"]["investigation"],
            )
            intake_snapshot.verify()
            data["intake"] = intake
        data["events"] = []
        data["completed_steps"] = None
        if latest:
            segments = (
                state.get("discovery", state)["segments"]
                if authenticated and state is not None
                else [run_id]
            )
            completed = 0
            for segment in segments:
                view = self.inspect(segment, actor, latest=False)
                for index, step in enumerate(view["steps"]):
                    completed += step["status"] in {
                        "authenticated",
                        "CANDIDATE",
                        "NO_MATCH",
                    }
                    data["events"].append(
                        {
                            "id": segment + ":step:" + str(index),
                            "author": "BeeAgent",
                            "text": (
                                f"{step['tool']} / {step['step']}: {step['status']}"
                                f"; requests: {step['request_count']}"
                            ),
                        }
                    )
                data["events"].append(
                    {
                        "id": segment + ":status",
                        "author": "BeeAgent",
                        "text": view["status"] + " / " + str(view["reason"]),
                    }
                )
            data["events"] = data["events"][-64:]
            data["events"].extend(
                {
                    "id": "finding:" + finding["finding_id"],
                    "author": "BeeScan",
                    "text": finding["title"] + " / " + finding["status"],
                }
                for finding in data["findings"]
            )
            data["completed_steps"] = completed
        metadata = self.case_metadata(owned["case_id"], actor)
        data["display_title"] = metadata.get("title") or (
            data["intake"]["task"] if data["intake"] else owned["case_id"]
        )
        data["archived"] = metadata.get("archived", False)
        data["report_readiness"] = "unavailable"
        if authenticated and data["findings"]:
            from beeagent_module.integrations.beescan.review import inspect_web_reports

            readiness = []
            for finding in data["findings"]:
                report_status = inspect_web_reports(self, owned["case_id"], finding["finding_id"], actor)
                readiness.append(report_status["reports"][-1]["report_readiness"] if report_status["reports"] else "review_required")
            data["report_readiness"] = ", ".join(sorted(set(readiness)))
        encoded = json.dumps(data, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise ValueError("web_projection_limit")
        snapshot.verify()
        return data

    def history(self, actor):
        principal(self.reload_settings(), actor)
        root = self.storage / "runs"
        if not root.exists():
            return []
        result = []
        seen = set()
        def recency(path):
            try:
                info = path.stat(follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    return (-1, path.name)
                return (info.st_mtime_ns, path.name)
            except OSError:
                return (-1, path.name)

        for path in sorted(
            (path for path in root.iterdir() if path.name.startswith("web-")),
            key=recency,
            reverse=True,
        ):
            try:
                binding = _read_owned(
                    self.storage, self.reload_settings(), path.name, actor
                )
                if binding["case_id"] != path.name:
                    continue
                view = self.inspect(binding["case_id"], actor, summary=True)
                if view["case_id"] in seen:
                    continue
                seen.add(view["case_id"])
                if view.get("archived"):
                    continue
                view.setdefault("created_at", binding.get("created_at"))
                result.append(view)
            except OSError, ValueError, TypeError, KeyError:
                continue
        return sorted(result, key=lambda row: (row.get("created_at") or "", row["case_id"]), reverse=True)

    def case_metadata(self, case_id, actor):
        current = self.reload_settings()
        _read_owned(self.storage, current, case_id, actor)
        try:
            record = AssessmentSnapshot(self.storage).json(case_id, "web_metadata.json")
        except FileNotFoundError:
            return {}
        value = record.get("value")
        if (
            type(value) is not dict
            or set(value) != {"case_id", "title", "archived"}
            or value["case_id"] != case_id
            or type(value["title"]) is not str
            or len(value["title"]) > 160
            or type(value["archived"]) is not bool
            or record.get("signature") != _sign(current, value)
        ):
            raise PermissionError("web_metadata_changed")
        return value

    def manage(self, action, payload, actor):
        current = self.reload_settings()
        principal(current, actor, execute=True)
        expected = {"case_id", "title"} if action == "beescan_rename" else {"case_id", "confirmation"}
        if action not in {"beescan_rename", "beescan_archive"} or type(payload) is not dict or set(payload) != expected:
            raise ValueError("invalid_case_management")
        case_id = payload["case_id"]
        root = open_directory(self.storage / "runs")
        try:
            fcntl.flock(root, fcntl.LOCK_EX | fcntl.LOCK_NB)
            view = self.inspect(case_id, actor)
            if view["status"] in {"QUEUED", "RUNNING"}:
                raise PermissionError("case_active")
            metadata = self.case_metadata(case_id, actor)
            title = payload.get("title", metadata.get("title", ""))
            if type(title) is not str or not title.strip() and action == "beescan_rename" or len(title) > 160 or any(ord(c) < 32 for c in title):
                raise ValueError("invalid_case_title")
            if action == "beescan_archive" and payload["confirmation"] != "ARCHIVE":
                raise PermissionError("archive_confirmation_required")
            value = {"case_id": case_id, "title": title.strip(), "archived": action == "beescan_archive" or metadata.get("archived", False)}
            self._publish_metadata(case_id, {"value": value, "signature": _sign(current, value)})
            return {"case_id": case_id, "archived": value["archived"]}
        finally:
            os.close(root)

    def _publish_metadata(self, case_id, record):
        from beeagent_module.integrations.beescan.detection_runner import read_regular

        directory = open_directory(self.storage / "runs" / case_id / "module-beescan")
        temporary = "web-metadata-" + secrets.token_hex(16) + ".pending"
        try:
            try:
                previous = os.stat("web_metadata.json", dir_fd=directory, follow_symlinks=False)
                if not stat.S_ISREG(previous.st_mode) or previous.st_nlink != 1 or previous.st_uid != os.getuid():
                    raise PermissionError("unsafe_web_metadata")
            except FileNotFoundError:
                pass
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(json.dumps(record, sort_keys=True).encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, "web_metadata.json", src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
            if json.loads(read_regular("web_metadata.json", limit=131072, dir_fd=directory, owner_uid=os.getuid())) != record:
                raise OSError("web_metadata_readback_failed")
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
