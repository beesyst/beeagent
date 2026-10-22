import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
from subprocess import SubprocessError
from uuid import uuid4

from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)
from beeagent_module.integrations.beescan.detection import _json, _persist
from beeagent_module.integrations.beescan.detection_runner import run_detection_provider
from beeagent_module.integrations.beescan.http_runner import verify_resolution


@dataclass(frozen=True)
class GitExposurePolicy:
    operator_uid: int
    project_id: str
    scope_id: str
    mission_id: str
    target_id: str
    origin: str
    approved: bool
    excluded: bool
    valid_from: datetime
    expires_at: datetime
    method: str
    http_method: str
    path: str
    request_budget: int
    time_budget_seconds: int
    connected_ip: str
    allow_private_lab: bool
    network_namespace: str
    user_namespace: str
    memory_mb: int
    output_bytes: int

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict or set(config) != set(cls.__dataclass_fields__):
            raise ValueError("invalid_git_exposure_approval")
        values = dict(config)
        for key in ("valid_from", "expires_at"):
            if type(values[key]) is not str:
                raise ValueError("invalid_git_exposure_approval")
            values[key] = datetime.fromisoformat(values[key])
        return cls(**values)

    def __post_init__(self):
        from beescan.domain.locators import canonical_locator
        from beescan.domain.models import TargetKind, utc_instant, validate_identifier

        for key in ("project_id", "scope_id", "mission_id", "target_id"):
            validate_identifier(getattr(self, key))
        for key in ("approved", "excluded", "allow_private_lab"):
            if type(getattr(self, key)) is not bool:
                raise ValueError("invalid_git_exposure_approval")
        for key, low, high in (
            ("operator_uid", 0, 2**31 - 1),
            ("request_budget", 1, 1),
            ("time_budget_seconds", 1, 60),
            ("memory_mb", 256, 4096),
            ("output_bytes", 1024, 4096),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid_git_exposure_approval")
        for key in ("valid_from", "expires_at"):
            object.__setattr__(self, key, utc_instant(getattr(self, key)))
        if (
            self.valid_from >= self.expires_at
            or self.method != "git_head_exposure"
            or self.http_method != "GET"
            or self.path != "/.git/HEAD"
            or type(self.origin) is not str
            or canonical_locator(TargetKind.URL, self.origin) != self.origin
        ):
            raise ValueError("invalid_git_exposure_approval")
        if (
            type(self.network_namespace) is not str
            or type(self.user_namespace) is not str
        ):
            raise ValueError("invalid_git_exposure_approval")
        from beeagent_module.integrations.beescan.egress import namespace_pair

        if not namespace_pair(self.network_namespace, self.user_namespace):
            raise ValueError("invalid_git_exposure_approval")
        if type(self.connected_ip) is not str:
            raise ValueError("invalid_git_exposure_approval")
        address = ip_address(self.connected_ip)
        if (
            str(address) != self.connected_ip
            or address.is_multicast
            or address.is_unspecified
            or (not address.is_global and not self.allow_private_lab)
        ):
            raise ValueError("invalid_git_exposure_destination")

    @property
    def port(self):
        from urllib.parse import urlsplit

        origin = urlsplit(self.origin)
        return origin.port or {"http": 80, "https": 443}[origin.scheme]

    def authorize(self):
        now = datetime.now(UTC)
        if (
            self.operator_uid != os.getuid()
            or not self.approved
            or self.excluded
            or not self.valid_from <= now < self.expires_at
            or now.timestamp() + self.time_budget_seconds > self.expires_at.timestamp()
        ):
            raise PermissionError("git_exposure_authorization_refused")

    def intent(self, observation):
        from beescan.domain.git_exposure import prepare_git_exposure
        from beescan.domain.models import (
            EngagementScope,
            Mission,
            MissionSpec,
            Project,
            Target,
            TargetKind,
        )

        self.authorize()
        return prepare_git_exposure(
            Project(self.project_id, "Approved exposure assessment"),
            (Target(self.target_id, self.project_id, TargetKind.URL, self.origin),),
            EngagementScope(
                self.scope_id,
                self.project_id,
                (self.target_id,),
                "host-git-approval",
                valid_from=self.valid_from,
                expires_at=self.expires_at,
                approved_methods=(self.method,),
                max_requests=1,
                max_seconds=self.time_budget_seconds,
            ),
            Mission(
                self.mission_id,
                self.project_id,
                self.scope_id,
                ("web.exposure.git_head",),
            ),
            MissionSpec(
                self.mission_id,
                self.target_id,
                "web.exposure.git_head",
                self.method,
                1,
                self.time_budget_seconds,
            ),
            at=datetime.now(UTC),
            observation=observation,
            provider_id="host-git-head",
            provider_version="1",
        )


def current_policy(settings):
    config = settings.get("beescan", {})
    enabled = any(
        item.get("id") == "beescan" and item.get("enabled") is True
        for item in settings.get("modules", {}).get("registry", [])
    )
    if not enabled or config.get("git_exposure_enabled") is not True:
        raise PermissionError("git_exposure_disabled")
    policy = GitExposurePolicy.from_config(config.get("git_exposure_approval"))
    policy.authorize()
    return policy


def validate_git_exposure_settings(config, module_enabled, *, validate_contracts=True):
    keys = {"git_exposure_enabled", "git_exposure_approval"}
    if not keys & config.keys():
        return
    if not keys <= config.keys() or type(config["git_exposure_enabled"]) is not bool:
        raise RuntimeError("Invalid beescan Git exposure settings")
    if config["git_exposure_enabled"] and not module_enabled:
        raise RuntimeError("BeeScan Git exposure requires the enabled module")
    approval = config["git_exposure_approval"]
    if approval is None:
        if config["git_exposure_enabled"]:
            raise RuntimeError("Git exposure requires separate approval")
        return
    if type(approval) is not dict:
        raise RuntimeError("Invalid Git exposure approval")
    if validate_contracts:
        try:
            from beescan.domain.git_exposure import GitExposureResult

            if GitExposureResult is None:
                raise ImportError
            GitExposurePolicy.from_config(approval)
        except ImportError, ValueError, TypeError:
            raise RuntimeError("Invalid or unavailable Git exposure contract") from None


def parse_git_capture(raw, policy):
    if type(raw) is not bytes or not 1 <= len(raw) <= policy.output_bytes:
        raise ValueError("invalid_git_capture")
    data = _json(raw)
    fixed = {
        "origin": policy.origin,
        "connected_ip": policy.connected_ip,
        "port": policy.port,
        "method": "GET",
        "path": "/.git/HEAD",
        "request_count": 1,
        "complete": True,
    }
    if type(data) is not dict or set(data) != set(fixed) | {"signature", "status_code"}:
        raise ValueError("invalid_git_capture")
    if any(
        type(data[key]) is not type(value) or data[key] != value
        for key, value in fixed.items()
    ):
        raise ValueError("invalid_git_capture")
    status = data["status_code"]
    signature = data["signature"]
    if (
        type(status) is not int
        or not 200 <= status <= 599
        or 300 <= status < 400
        or (
            signature is not None
            and (
                type(signature) is not str
                or signature not in {"symbolic", "detached"}
                or status != 200
            )
        )
    ):
        raise ValueError("invalid_git_capture")
    return data


def execute_git_exposure(
    *,
    policy,
    reload_policy,
    observation,
    assessment_run_id,
    storage_dir,
    logger,
    validate_source,
    on_started,
):
    from beescan.capabilities.http_probe import HostProvenance
    from beescan.domain.git_exposure import (
        GitExposureResult,
        GitExposureState,
        GitHeadFacts,
    )

    run_id = generate_run_id()
    artifacts = ArtifactAPI(
        RuntimeContext(
            run_id=run_id,
            session_id=generate_session_id(),
            case_type="git_head_exposure",
            module_id="beescan",
            authority=AuthorityLevel.EXECUTION_CAPABLE,
        ),
        storage_dir,
        logger,
    )
    artifacts.artifact_dir().chmod(0o700)
    status = {
        "schema_version": 1,
        "run_id": run_id,
        "assessment_run_id": assessment_run_id,
        "status": "incomplete",
        "complete": False,
        "evidence_refs": [],
        "source_run_id": observation.facts.provenance.run_id,
        "source_observation_id": observation.observation_id,
    }
    _persist(artifacts, "git_exposure_status.json", status)
    on_started(run_id)
    intent = policy.intent(observation)

    def authorize():
        if reload_policy() != policy:
            raise PermissionError("git_exposure_approval_changed")
        policy.authorize()
        validate_source()
        verify_resolution(policy)

    refs, signature, code = (), None, None
    state = GitExposureState.INCOMPLETE
    try:
        authorize()
        raw = run_detection_provider(policy, reauthorize=authorize, git_exposure=True)
        capture = parse_git_capture(raw, policy)
        authorize()
        ref = "git-evidence-" + uuid4().hex
        refs, signature, code = (ref,), capture["signature"], capture["status_code"]
        state = GitExposureState.POSITIVE if signature else GitExposureState.NO_MATCH
    except PermissionError:
        state = GitExposureState.REFUSED
    except TimeoutError:
        state = GitExposureState.TIMEOUT
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        RecursionError,
        UnicodeError,
        SubprocessError,
    ):
        state = GitExposureState.ERROR
    complete = state in {GitExposureState.POSITIVE, GitExposureState.NO_MATCH}
    facts = GitHeadFacts(
        intent.mission_id,
        intent.target_id,
        intent.origin,
        observation.observation_id,
        assessment_run_id,
        HostProvenance(run_id, intent.provider_id, intent.provider_version),
        refs,
        state,
        code,
        signature,
        complete,
    )
    result = GitExposureResult(intent, facts)
    if complete:
        if not refs:
            raise ValueError("missing_git_exposure_evidence")
        _persist(artifacts, refs[0] + ".json", {"schema_version": 1, **asdict(facts)})
    _persist(
        artifacts, "git_exposure_result.json", {"schema_version": 1, **asdict(result)}
    )
    status.update(status=state.value, complete=complete, evidence_refs=list(refs))
    _persist(artifacts, "git_exposure_status.json", status)
    logger.info("BeeScan Git exposure: run_id=%s status=%s", run_id, state.value)
    return status, result
