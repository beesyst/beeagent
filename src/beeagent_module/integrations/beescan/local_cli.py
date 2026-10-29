from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from typing import TYPE_CHECKING

from beeagent_module.core.paths import get_project_root

if TYPE_CHECKING:
    from beeagent_module.integrations.beescan.investigation import InvestigationPolicy

_SEAL = object()


def _identity():
    if os.getuid() != os.geteuid() or os.getgid() != os.getegid():
        raise PermissionError("local_operator_mismatch")
    return os.getpid(), os.getuid(), os.getgid()


@dataclass(frozen=True)
class _LocalOperator:
    identity: tuple
    seal: object

    def verify(self):
        if self.seal is not _SEAL or self.identity != _identity():
            raise PermissionError("local_operator_mismatch")


def _operator_from_entrypoint():
    main = sys.modules.get("__main__")
    entrypoint = get_project_root() / "config/start.py"
    if (
        Path(getattr(main, "__file__", "")).resolve() != entrypoint.resolve()
        or Path(sys.argv[0]).resolve() != entrypoint.resolve()
        or sys.argv[1:2] != ["beescan"]
    ):
        raise PermissionError("local_entrypoint_required")
    return _LocalOperator(_identity(), _SEAL)


@dataclass(frozen=True)
class _LocalRun:
    operator: _LocalOperator
    policy: InvestigationPolicy

    def verify(self, policy):
        self.operator.verify()
        if policy != self.policy:
            raise PermissionError("local_binding_changed")

    def provenance(self):
        transport = self.policy.transport
        return {
            "authority_source": "trusted_local_os_operator",
            "third_party_authorization_verified": False,
            "operator_uid": self.operator.identity[1],
            "operator_gid": self.operator.identity[2],
            "origin": transport.origin,
            "connected_ip": transport.connected_ip,
            "port": transport.port,
            "http_method": self.policy.method,
            "mutation_profile": self.policy.mutation_profile,
            "request_budget": self.policy.request_budget,
        }


def bind_local_run(task, operator, settings, *, run_id):
    from beescan.domain.locators import canonical_locator
    from beescan.domain.models import TargetKind

    from beeagent_module.integrations.beescan.http_runner import resolve_addresses
    from beeagent_module.integrations.beescan.investigation import (
        LAB_NETWORKS,
        InvestigationPolicy,
    )
    from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
    from beeagent_module.integrations.beescan.providers import provider_root

    config = settings["beescan"]["investigation"]
    if (
        config.get("trusted_local_enabled") is not True
        or type(operator) is not _LocalOperator
    ):
        raise PermissionError("local_invocation_refused")
    operator.verify()
    origin = canonical_locator(TargetKind.URL, task.target)
    addresses = resolve_addresses(origin)
    allowed = []
    for value in addresses:
        address = ip_address(value)
        if (
            not address.is_multicast
            and not address.is_unspecified
            and (
                address.is_global or any(address in network for network in LAB_NETWORKS)
            )
        ):
            allowed.append(str(address))
    if not allowed:
        raise PermissionError("local_destination_refused")
    connected_ip = min(allowed, key=lambda value: (ip_address(value).version, value))
    now = datetime.now(UTC)
    seconds = config["timeout_seconds"]
    transport = ProbePolicy(
        operator.identity[1],
        run_id,
        run_id,
        run_id,
        run_id,
        origin,
        True,
        False,
        now,
        now + timedelta(seconds=seconds * 2 + 15),
        "http_probe",
        1,
        seconds,
        connected_ip,
        not ip_address(connected_ip).is_global,
        str(provider_root() / "httpx"),
        HTTPX_SHA256,
        "1.12.0",
        "/beeagent-managed/ns/net",
        "/beeagent-managed/ns/user",
        2048,
        16384,
    )
    policy = InvestigationPolicy(
        transport, True, True, True, "GET", "numeric_invalid_v1", 3
    )
    operator.verify()
    return _LocalRun(operator, policy)


def present_sensitive_value(value, context, policy):
    from beescan.domain.debug_disclosure import SensitiveValue

    if type(value) is not SensitiveValue or type(context) is not _LocalRun:
        raise PermissionError("sensitive_presentation_refused")
    context.verify(policy)
    if not all(os.isatty(descriptor) for descriptor in (0, 1, 2)):
        return False
    terminals = [os.fstat(descriptor) for descriptor in (0, 1, 2)]
    if any(info.st_rdev != terminals[0].st_rdev for info in terminals):
        return False
    descriptor = os.open(
        os.ttyname(0), os.O_WRONLY | os.O_NOCTTY | os.O_CLOEXEC | os.O_NOFOLLOW
    )
    try:
        terminal = os.fstat(descriptor)
        if terminal.st_rdev != terminals[0].st_rdev or terminal.st_uid != os.getuid():
            raise PermissionError("sensitive_terminal_mismatch")
        if os.tcgetpgrp(descriptor) != os.getpgrp():
            raise PermissionError("controlling_terminal_required")
        context.verify(policy)
        raw = (value.reveal_to_host() + "\n").encode("utf-8")
        if os.write(descriptor, raw) != len(raw):
            raise OSError("sensitive_terminal_write_failed")
    finally:
        os.close(descriptor)
    return True
