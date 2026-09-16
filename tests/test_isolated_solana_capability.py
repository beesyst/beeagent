from __future__ import annotations

import logging
import signal
import subprocess

import pytest
from beesdk.capabilities import CapabilityStatus

from beeagent_module.core.isolated_solana_capability import (
    ScopedSolanaLifecycleCaller,
    create_capability_caller,
)
from beeagent_module.core.module_contract import AuthorityLevel


def _caller(
    module_id: str = "beedrill",
    case_type: str = "isolated_solana_smoke",
    authority: AuthorityLevel = AuthorityLevel.READ_ONLY,
) -> ScopedSolanaLifecycleCaller:
    logger = logging.getLogger("test_isolated_solana_capability")
    logger.addHandler(logging.NullHandler())
    return ScopedSolanaLifecycleCaller(
        run_id="run-1",
        session_id="session-1",
        module_id=module_id,
        case_type=case_type,
        authority=authority,
        logger=logger,
    )


class _Process:
    def __init__(self, force_cleanup: bool = False) -> None:
        self.exit_code: int | None = None
        self.force_cleanup = force_cleanup
        self.interrupted = False
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.exit_code

    def terminate(self) -> None:
        self.terminated = True

    def send_signal(self, signal_number: int) -> None:
        assert signal_number == signal.SIGINT
        self.interrupted = True
        if not self.force_cleanup:
            self.exit_code = 0

    def kill(self) -> None:
        self.killed = True
        self.exit_code = -9

    def wait(self, timeout: float) -> int:
        if self.force_cleanup and not self.killed:
            raise subprocess.TimeoutExpired("surfpool", timeout)
        self.exit_code = 0
        return self.exit_code


def test_caller_is_created_only_for_the_approved_module_case() -> None:
    assert (
        create_capability_caller(
            "run-1",
            "session-1",
            "beedrill",
            "integration_smoke",
            AuthorityLevel.READ_ONLY,
            logging.getLogger("test"),
        )
        is None
    )
    assert (
        create_capability_caller(
            "run-1",
            "session-1",
            "other",
            "isolated_solana_smoke",
            AuthorityLevel.READ_ONLY,
            logging.getLogger("test"),
        )
        is None
    )


@pytest.mark.parametrize(
    ("module_id", "case_type", "authority"),
    [
        ("other", "isolated_solana_smoke", AuthorityLevel.READ_ONLY),
        ("beedrill", "other", AuthorityLevel.READ_ONLY),
        ("beedrill", "isolated_solana_smoke", AuthorityLevel.DRAFT_ONLY),
    ],
)
def test_caller_refuses_scope_that_cannot_receive_the_capability(
    module_id: str,
    case_type: str,
    authority: AuthorityLevel,
) -> None:
    result = _caller(module_id, case_type, authority).call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics == {"reason": "scope_not_allowed"}


@pytest.mark.parametrize(
    ("capability_name", "payload"),
    [
        ("other", {"target_profile": "surfpool_local"}),
        ("solana.isolated_lifecycle", {"target_profile": "other"}),
        (
            "solana.isolated_lifecycle",
            {"target_profile": "surfpool_local", "executable": "untrusted"},
        ),
        ("solana.isolated_lifecycle", {}),
    ],
)
def test_caller_refuses_unknown_or_execution_shaped_input(
    capability_name: str,
    payload: dict[str, str],
) -> None:
    result = _caller().call(capability_name, payload)

    assert result.status is CapabilityStatus.REFUSED


def test_caller_fails_explicitly_when_surfpool_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.shutil.which", lambda _: None
    )

    result = _caller().call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.diagnostics == {"reason": "executable_unavailable"}


def test_successful_lifecycle_uses_fixed_offline_host_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process()
    received: dict[str, object] = {}

    def fake_popen(args: list[str], **kwargs: object) -> _Process:
        received["args"] = args
        received["kwargs"] = kwargs
        return process

    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.shutil.which",
        lambda _: "/host/surfpool",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.subprocess.Popen", fake_popen
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._wait_for_readiness",
        lambda _: "ready",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._rpc_health", lambda: None
    )

    result = _caller().call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.status is CapabilityStatus.OK
    assert result.authority.value == "execution_capable"
    assert result.data == {
        "lifecycle": "completed",
        "readiness": "ok",
        "rpc": "ok",
        "cleanup": "ok",
    }
    assert received["args"] == [
        "/host/surfpool",
        "start",
        "--offline",
        "--no-tui",
        "--no-studio",
        "--ci",
    ]
    assert process.interrupted
    assert not process.terminated
    assert not process.killed


def test_startup_failure_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_popen(*_args: object, **_kwargs: object) -> _Process:
        raise OSError("startup failed")

    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.shutil.which",
        lambda _: "/host/surfpool",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.subprocess.Popen", fail_popen
    )

    result = _caller().call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.authority.value == "execution_capable"
    assert result.diagnostics == {"reason": "startup_failed"}


@pytest.mark.parametrize(
    ("readiness", "expected"),
    [("early_process_exit", "early_process_exit"), ("timeout", "readiness_timeout")],
)
def test_readiness_failures_are_explicit_and_reaped(
    monkeypatch: pytest.MonkeyPatch,
    readiness: str,
    expected: str,
) -> None:
    process = _Process()
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.shutil.which",
        lambda _: "/host/surfpool",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._wait_for_readiness",
        lambda _: readiness,
    )

    result = _caller().call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.diagnostics == {"reason": expected}
    assert result.authority.value == "execution_capable"
    assert process.poll() is not None


@pytest.mark.parametrize(
    ("exception", "reason", "status"),
    [
        (TimeoutError(), "rpc_timeout", CapabilityStatus.TIMEOUT),
        (ValueError(), "rpc_error", CapabilityStatus.ERROR),
    ],
)
def test_rpc_failures_are_explicit_and_reaped(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    reason: str,
    status: CapabilityStatus,
) -> None:
    process = _Process()
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.shutil.which",
        lambda _: "/host/surfpool",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._wait_for_readiness",
        lambda _: "ready",
    )

    def fail_rpc() -> None:
        raise exception

    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._rpc_health", fail_rpc
    )

    result = _caller().call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.status is status
    assert result.authority.value == "execution_capable"
    assert result.diagnostics == {"reason": reason}
    assert process.poll() is not None


def test_forced_cleanup_is_reported_after_reaping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process(force_cleanup=True)
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.shutil.which",
        lambda _: "/host/surfpool",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability.subprocess.Popen",
        lambda *_args, **_kwargs: process,
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._wait_for_readiness",
        lambda _: "ready",
    )
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._rpc_health", lambda: None
    )

    result = _caller().call(
        "solana.isolated_lifecycle", {"target_profile": "surfpool_local"}
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.authority.value == "execution_capable"
    assert result.diagnostics == {"reason": "cleanup_forced"}
    assert process.killed
    assert process.poll() is not None
