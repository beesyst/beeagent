import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit

HTTPX_SHA256 = "bb28edc87dfd8b11f25ebb73b325f05424e8ee2dd5c818649f1f7d28da6a32b5"


def target_exclusions(settings):
    config = settings.get("beescan", {}).get("target_policy")
    if (
        type(config) is not dict
        or set(config) != {"excluded_targets"}
        or type(config["excluded_targets"]) is not list
        or len(config["excluded_targets"]) > 512
    ):
        raise RuntimeError("invalid_target_policy")
    result = []
    for value in config["excluded_targets"]:
        if type(value) is not str or not 1 <= len(value) <= 256:
            raise RuntimeError("invalid_target_policy")
        try:
            if "/" in value:
                result.append(("network", ip_network(value, strict=True)))
            else:
                try:
                    result.append(("address", ip_address(value)))
                except ValueError:
                    suffix = value.startswith((".", "*."))
                    host = (
                        value[2:]
                        if value.startswith("*.")
                        else value[1:]
                        if suffix
                        else value
                    )
                    host = host.removesuffix(".").lower()
                    labels = host.split(".")
                    if (
                        len(host) > 253
                        or not host.isascii()
                        or re.fullmatch(r"[0-9]+|0x[0-9a-f]+", labels[-1])
                        or any(
                            not re.fullmatch(
                                r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label
                            )
                            for label in labels
                        )
                        or host.encode("ascii")
                        .decode("idna")
                        .encode("idna")
                        .decode("ascii")
                        != host
                    ):
                        raise ValueError("Invalid excluded hostname")
                    result.append(("suffix" if suffix else "host", host))
        except ValueError, UnicodeError:
            raise RuntimeError("invalid_target_policy") from None
    return tuple(result)


def validate_target_policy_file(settings_path):
    path = Path(settings_path).absolute()
    if path.resolve() != path:
        raise RuntimeError("insecure_target_policy_configuration")
    for item in (path, *path.parents):
        info = item.lstat()
        if (
            info.st_uid not in {0, os.getuid()}
            or info.st_mode & 0o022
            and not (item != path and info.st_mode & stat.S_ISVTX)
            or item == path
            and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)
        ):
            raise RuntimeError("insecure_target_policy_configuration")


def public_destination(value):
    address = ip_address(value)
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_reserved
        and not getattr(address, "ipv4_mapped", None)
        and not getattr(address, "sixtofour", None)
        and not getattr(address, "teredo", None)
        and not (address.version == 6 and address in ip_network("64:ff9b::/96"))
        and not (address.version == 6 and address in ip_network("64:ff9b:1::/48"))
        and str(address) != "168.63.129.16"
    )


def check_web_target(settings, target, *, connected_ip=None):
    from beescan.domain.locators import canonical_locator
    from beescan.domain.models import TargetKind

    from beeagent_module.integrations.beescan.http_runner import resolve_addresses

    exclusions = target_exclusions(settings)
    origin = canonical_locator(TargetKind.URL, target)
    host = urlsplit(origin).hostname
    if host is None:
        raise ValueError("invalid_target")
    for kind, value in exclusions:
        if (
            kind == "host"
            and host == value
            or kind == "suffix"
            and (host == value or host.endswith("." + value))
        ):
            raise PermissionError("target_excluded")
    try:
        literal = ip_address(host)
    except ValueError:
        literal = None
    addresses = {str(literal)} if literal is not None else None
    if addresses is None:
        if host == "localhost" or host.endswith(
            (".localhost", ".local", ".internal", ".home.arpa")
        ):
            raise PermissionError("internal_destination_denied")
        addresses = resolve_addresses(origin)
    if not addresses or len(addresses) > 16:
        raise PermissionError("dns_unverified")
    for raw in addresses:
        address = ip_address(raw)
        for kind, value in exclusions:
            if (
                kind == "address"
                and address == value
                or kind == "network"
                and address.version == value.version
                and address in value
            ):
                raise PermissionError("target_excluded")
        if not public_destination(raw):
            raise PermissionError("internal_destination_denied")
    if connected_ip is not None and connected_ip not in addresses:
        raise PermissionError("dns_changed")
    return origin, connected_ip or min(
        addresses, key=lambda v: (ip_address(v).version, v)
    )


def web_execution_policy(settings, target, case_id, *, connected_ip=None):
    from beeagent_module.integrations.beescan.investigation import InvestigationPolicy
    from beeagent_module.integrations.beescan.providers import provider_root

    origin, address = check_web_target(settings, target, connected_ip=connected_ip)
    now = datetime.now(UTC)
    seconds = settings["beescan"]["investigation"]["timeout_seconds"]
    transport = ProbePolicy(
        os.getuid(),
        case_id,
        case_id,
        case_id,
        case_id,
        origin,
        True,
        False,
        now,
        now + timedelta(seconds=seconds * 2 + 15),
        "http_probe",
        1,
        seconds,
        address,
        not ip_address(address).is_global,
        str(provider_root() / "httpx"),
        HTTPX_SHA256,
        "1.12.0",
        "/beeagent-managed/ns/net",
        "/beeagent-managed/ns/user",
        2048,
        16384,
    )
    return InvestigationPolicy(
        transport, True, True, True, "GET", "numeric_invalid_v1", 3
    )


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
        from beeagent_module.integrations.beescan.egress import namespace_pair

        if not namespace_pair(self.network_namespace, self.user_namespace):
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
    if type(config) is not dict or set(config) - {
        "investigation",
        "dast",
        "target_policy",
    } not in (
        {"probe_enabled", "approval"},
        {"probe_enabled", "approval", "detection_enabled", "detection_approval"},
        {
            "probe_enabled",
            "approval",
            "detection_enabled",
            "detection_approval",
            "git_exposure_enabled",
            "git_exposure_approval",
        },
    ):
        raise RuntimeError("Invalid beescan settings")
    if "target_policy" in config:
        target_exclusions(settings)
    if type(config["probe_enabled"]) is not bool:
        raise RuntimeError("Invalid beescan.probe_enabled")
    from beeagent_module.integrations.beescan.dast import validate_dast_settings

    validate_dast_settings(config, enabled, validate_contracts=validate_contracts)
    from beeagent_module.integrations.beescan.investigation import (
        validate_investigation_settings,
    )

    validate_investigation_settings(settings, validate_contracts=validate_contracts)
    from beeagent_module.integrations.beescan.detection_policy import (
        validate_detection_settings,
    )

    validate_detection_settings(config, enabled, validate_contracts=validate_contracts)
    from beeagent_module.integrations.beescan.git_exposure import (
        validate_git_exposure_settings,
    )

    validate_git_exposure_settings(
        config, enabled, validate_contracts=validate_contracts
    )
    if config["probe_enabled"] and not enabled:
        raise RuntimeError("BeeScan probing requires the enabled module")
    if not validate_contracts:
        if config["approval"] is not None and type(config["approval"]) is not dict:
            raise RuntimeError("Invalid beescan.approval contract")
        if config["probe_enabled"] and config["approval"] is None:
            raise RuntimeError("Invalid beescan.approval contract")
        return
    if config["probe_enabled"] or config["approval"] is not None:
        try:
            ProbePolicy.from_config(config["approval"])
        except ValueError, TypeError, ImportError:
            raise RuntimeError(
                "Invalid or unavailable beescan.approval contract"
            ) from None
