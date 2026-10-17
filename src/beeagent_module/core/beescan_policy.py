import re
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

HTTPX_SHA256 = "bb28edc87dfd8b11f25ebb73b325f05424e8ee2dd5c818649f1f7d28da6a32b5"


@dataclass(frozen=True)
class ProbePolicy:
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

    @classmethod
    def from_config(cls, config: dict) -> ProbePolicy:
        if type(config) is not dict or set(config) != set(cls.__dataclass_fields__):
            raise ValueError("invalid_probe_policy")
        values = dict(config)
        for key in ("valid_from", "expires_at"):
            value = values[key]
            if type(value) is not str:
                raise ValueError("invalid_probe_policy")
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("invalid_probe_policy") from None
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("invalid_probe_policy")
            values[key] = parsed.astimezone(UTC)
        return cls(**values)

    def __post_init__(self) -> None:
        for key in ("project_id", "scope_id", "mission_id", "target_id"):
            value = getattr(self, key)
            if type(value) is not str or not re.fullmatch(
                r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", value
            ):
                raise ValueError("invalid_probe_policy")
        for key in ("approved", "excluded", "allow_private_lab"):
            if type(getattr(self, key)) is not bool:
                raise ValueError("invalid_probe_policy")
        for key, low, high in (
            ("operator_uid", 0, 2**31 - 1),
            ("request_budget", 1, 1),
            ("time_budget_seconds", 1, 60),
            ("memory_mb", 256, 4096),
            ("output_bytes", 1024, 65536),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("invalid_probe_policy")
        if (
            self.method != "http_probe"
            or self.provider_version != "1.12.0"
            or type(self.sha256) is not str
            or not re.fullmatch("[0-9a-f]{64}", self.sha256)
            or self.sha256 != HTTPX_SHA256
            or self.valid_from >= self.expires_at
        ):
            raise ValueError("invalid_probe_policy")
        for value in (self.executable, self.network_namespace, self.user_namespace):
            if (
                type(value) is not str
                or len(value) > 256
                or not Path(value).is_absolute()
                or ".." in Path(value).parts
                or any(ord(c) < 32 for c in value)
            ):
                raise ValueError("invalid_probe_policy")
        match = re.fullmatch(r"/proc/([1-9][0-9]{0,9})/ns/net", self.network_namespace)
        if match is None or self.user_namespace != f"/proc/{match[1]}/ns/user":
            raise ValueError("invalid_probe_policy")
        from beescan.domain.locators import canonical_locator
        from beescan.domain.models import TargetKind

        if (
            type(self.origin) is not str
            or canonical_locator(TargetKind.URL, self.origin) != self.origin
        ):
            raise ValueError("invalid_probe_policy")
        if type(self.connected_ip) is not str:
            raise ValueError("invalid_probe_policy")
        address = ip_address(self.connected_ip)
        if (
            str(address) != self.connected_ip
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ValueError("invalid_probe_policy")
        if not address.is_global and not self.allow_private_lab:
            raise ValueError("private_destination_denied")

    @property
    def port(self) -> int:
        parsed = urlsplit(self.origin)
        return parsed.port or {"http": 80, "https": 443}[parsed.scheme]

    def authorize(self, intent, *, operator_uid: int, at: datetime) -> None:
        if (
            operator_uid != self.operator_uid
            or type(operator_uid) is not int
            or not self.approved
            or self.excluded
            or not self.valid_from <= at < self.expires_at
            or at.timestamp() + self.time_budget_seconds > self.expires_at.timestamp()
            or intent.payload != self.intent().payload
        ):
            raise PermissionError("authorization_refused")

    def intent(self):
        from beescan.capabilities.http_probe import HttpProbeIntent

        return HttpProbeIntent(
            self.mission_id,
            self.target_id,
            self.origin,
            self.request_budget,
            self.time_budget_seconds,
            "projectdiscovery-httpx",
            self.provider_version,
        )


def validate_beescan_settings(settings: dict, *, validate_contracts=True) -> None:
    config = settings.get("beescan")
    enabled = any(
        item.get("id") == "beescan" and item.get("enabled") is True
        for item in settings.get("modules", {}).get("registry", [])
    )
    if config is None and not enabled:
        return
    if type(config) is not dict or set(config) not in (
        {"probe_enabled", "approval"},
        {"probe_enabled", "approval", "detection_enabled", "detection_approval"},
    ):
        raise RuntimeError("Invalid beescan settings")
    if type(config["probe_enabled"]) is not bool:
        raise RuntimeError("Invalid beescan.probe_enabled")
    from beeagent_module.core.beescan_detection_policy import (
        validate_detection_settings,
    )

    validate_detection_settings(config, enabled, validate_contracts=validate_contracts)
    if config["probe_enabled"] and not enabled:
        raise RuntimeError("BeeScan probing requires the enabled module")
    if not validate_contracts:
        if config["approval"] is not None and type(config["approval"]) is not dict:
            raise RuntimeError("Invalid beescan.approval contract")
        if config["probe_enabled"] and config["approval"] is None:
            raise RuntimeError("Invalid beescan.approval contract")
        return
    if config["probe_enabled"]:
        try:
            ProbePolicy.from_config(config["approval"])
        except ValueError, TypeError, ImportError:
            raise RuntimeError(
                "Invalid or unavailable beescan.approval contract"
            ) from None
    elif config["approval"] is not None:
        try:
            ProbePolicy.from_config(config["approval"])
        except ValueError, TypeError, ImportError:
            raise RuntimeError(
                "Invalid or unavailable beescan.approval contract"
            ) from None
