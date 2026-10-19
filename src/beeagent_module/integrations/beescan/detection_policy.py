import re
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

NUCLEI_VERSION = "3.11.1"
NUCLEI_SHA256 = "c49588140f357cbdddd5436dec11201953a4c5390faeec90777f9ee2cfd70251"
TEMPLATE_SHA256 = "51bab1f02a5553709d4684c83e81e371cc935f07f2a1c6edd554cffc19027597"


@dataclass(frozen=True)
class DetectionPolicy:
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
    request_budget: int
    time_budget_seconds: int
    connected_ip: str
    allow_private_lab: bool
    executable: str
    sha256: str
    provider_version: str
    network_namespace: str
    user_namespace: str
    memory_mb: int
    output_bytes: int
    source_run_id: str
    source_observation_id: str
    provider_id: str
    profile: str
    template_id: str
    template_version: str
    template_path: str
    template_sha256: str

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict or set(config) != set(cls.__dataclass_fields__):
            raise ValueError("invalid_detection_policy")
        values = dict(config)
        for key in ("valid_from", "expires_at"):
            if type(values[key]) is not str:
                raise ValueError("invalid_detection_policy")
            try:
                values[key] = datetime.fromisoformat(values[key])
            except ValueError:
                raise ValueError("invalid_detection_policy") from None
        return cls(**values)

    def __post_init__(self):
        from beescan.domain.locators import canonical_locator
        from beescan.domain.models import TargetKind, utc_instant, validate_identifier

        for key in (
            "project_id",
            "scope_id",
            "mission_id",
            "target_id",
            "source_run_id",
            "source_observation_id",
        ):
            validate_identifier(getattr(self, key))
        for key in ("approved", "excluded", "allow_private_lab"):
            if type(getattr(self, key)) is not bool:
                raise ValueError("invalid_detection_policy")
        for key, low, high in (
            ("operator_uid", 0, 2**31 - 1),
            ("request_budget", 1, 1),
            ("time_budget_seconds", 1, 60),
            ("memory_mb", 2048, 4096),
            ("output_bytes", 1024, 16384),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid_detection_policy")
        for key in ("valid_from", "expires_at"):
            object.__setattr__(self, key, utc_instant(getattr(self, key)))
        if self.valid_from >= self.expires_at:
            raise ValueError("invalid_detection_policy")
        expected = {
            "method": "restricted_detection",
            "provider_id": "nuclei",
            "provider_version": NUCLEI_VERSION,
            "sha256": NUCLEI_SHA256,
            "profile": "http-marker-v1",
            "template_id": "beescan-http-marker",
            "template_version": "1",
            "template_sha256": TEMPLATE_SHA256,
        }
        if any(
            type(getattr(self, key)) is not str or getattr(self, key) != value
            for key, value in expected.items()
        ):
            raise ValueError("invalid_detection_policy")
        for value in (
            self.executable,
            self.template_path,
            self.network_namespace,
            self.user_namespace,
        ):
            if (
                type(value) is not str
                or len(value) > 256
                or not Path(value).is_absolute()
                or ".." in Path(value).parts
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError("invalid_detection_policy")
        match = re.fullmatch(r"/proc/([1-9][0-9]{0,9})/ns/net", self.network_namespace)
        if match is None or self.user_namespace != f"/proc/{match[1]}/ns/user":
            raise ValueError("invalid_detection_policy")
        if (
            type(self.origin) is not str
            or canonical_locator(TargetKind.URL, self.origin) != self.origin
        ):
            raise ValueError("invalid_detection_policy")
        if type(self.connected_ip) is not str:
            raise ValueError("invalid_detection_policy")
        address = ip_address(self.connected_ip)
        if (
            str(address) != self.connected_ip
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValueError("invalid_detection_policy")
        if not address.is_global and not self.allow_private_lab:
            raise ValueError("private_destination_denied")

    @property
    def port(self):
        origin = urlsplit(self.origin)
        return origin.port or {"http": 80, "https": 443}[origin.scheme]

    def intent(self, observation, *, at):
        from beescan.capabilities.catalog import (
            Capability,
            ToolCatalog,
            ToolDefinition,
            ToolInstallation,
            ToolPolicy,
        )
        from beescan.capabilities.detection import DetectionTemplate, prepare_detection
        from beescan.domain.models import (
            EngagementScope,
            Mission,
            MissionSpec,
            Project,
            Target,
            TargetKind,
        )

        if (
            observation.observation_id != self.source_observation_id
            or observation.facts.provenance.run_id != self.source_run_id
        ):
            raise PermissionError("source_observation_mismatch")
        return prepare_detection(
            Project(self.project_id, "Approved detection"),
            (Target(self.target_id, self.project_id, TargetKind.URL, self.origin),),
            EngagementScope(
                self.scope_id,
                self.project_id,
                (self.target_id,),
                "host-detection-approval",
                valid_from=self.valid_from,
                expires_at=self.expires_at,
                approved_methods=(self.method,),
                max_requests=self.request_budget,
                max_seconds=self.time_budget_seconds,
            ),
            Mission(
                self.mission_id,
                self.project_id,
                self.scope_id,
                ("web.detect.restricted",),
            ),
            MissionSpec(
                self.mission_id,
                self.target_id,
                "web.detect.restricted",
                self.method,
                self.request_budget,
                self.time_budget_seconds,
            ),
            at=at,
            observation=observation,
            template=DetectionTemplate(
                self.template_id, self.template_version, self.template_sha256
            ),
            catalog=ToolCatalog(
                (Capability("web.detect.restricted", "Restricted detection"),),
                (
                    ToolDefinition(
                        "nuclei", ("web.detect.restricted",), self.provider_version
                    ),
                ),
            ),
            installation=ToolInstallation("nuclei", True, self.provider_version),
            policy=ToolPolicy("nuclei", True, True),
        )

    def authorize_operator(self, *, operator_uid, at):
        if (
            type(operator_uid) is not int
            or operator_uid != self.operator_uid
            or not self.approved
            or self.excluded
            or not self.valid_from <= at < self.expires_at
            or at.timestamp() + self.time_budget_seconds > self.expires_at.timestamp()
        ):
            raise PermissionError("authorization_refused")

    def authorize(self, intent, observation, *, operator_uid, at):
        self.authorize_operator(operator_uid=operator_uid, at=at)
        if intent != self.intent(observation, at=at):
            raise PermissionError("authorization_refused")


def validate_detection_settings(config, module_enabled, *, validate_contracts=True):
    keys = {"detection_enabled", "detection_approval"}
    if not keys & config.keys():
        return
    if not keys <= config.keys() or type(config["detection_enabled"]) is not bool:
        raise RuntimeError("Invalid beescan detection settings")
    if config["detection_enabled"] and not module_enabled:
        raise RuntimeError("BeeScan detection requires the enabled module")
    if not validate_contracts:
        approval = config["detection_approval"]
        if approval is not None and type(approval) is not dict:
            raise RuntimeError("Invalid beescan.detection_approval contract")
        if config["detection_enabled"] and approval is None:
            raise RuntimeError("Invalid beescan.detection_approval contract")
        return
    if config["detection_enabled"] or config["detection_approval"] is not None:
        try:
            from beescan.capabilities.detection import DetectionIntent

            if DetectionIntent is None:
                raise ImportError
            DetectionPolicy.from_config(config["detection_approval"])
        except ImportError, ValueError, TypeError:
            raise RuntimeError(
                "Invalid or unavailable beescan.detection_approval contract"
            ) from None
