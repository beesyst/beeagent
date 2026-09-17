from __future__ import annotations

import logging
import signal
import subprocess
from base64 import b64encode

import pytest
from beesdk.capabilities import CapabilityStatus
from solders.keypair import Keypair

import beeagent_module.core.isolated_solana_capability as solana_capability
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


def _reference_target_caller() -> ScopedSolanaLifecycleCaller:
    return _caller(case_type="reference_target_baseline")


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
            "beedrill",
            "reference_target_baseline",
            AuthorityLevel.READ_ONLY,
            logging.getLogger("test"),
        )
        is not None
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
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._run_reference_target_baseline",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected reference call")),
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


@pytest.mark.parametrize(
    ("capability_name", "payload"),
    [
        ("other", {"target_profile": "surfpool_local", "target_id": "reference_vault"}),
        (
            "solana.reference_target_baseline",
            {"target_profile": "other", "target_id": "reference_vault"},
        ),
        (
            "solana.reference_target_baseline",
            {"target_profile": "surfpool_local", "target_id": "other"},
        ),
        (
            "solana.reference_target_baseline",
            {
                "target_profile": "surfpool_local",
                "target_id": "reference_vault",
                "program_path": "untrusted",
            },
        ),
        (
            "solana.reference_target_baseline",
            {
                "target_profile": "surfpool_local",
                "target_id": "reference_vault",
                "rpc_url": "untrusted",
            },
        ),
        (
            "solana.reference_target_baseline",
            {
                "target_profile": "surfpool_local",
                "target_id": "reference_vault",
                "raw_transaction": "untrusted",
            },
        ),
    ],
)
def test_reference_target_caller_refuses_untrusted_input(
    capability_name: str,
    payload: dict[str, str],
) -> None:
    result = _reference_target_caller().call(capability_name, payload)

    assert result.status is CapabilityStatus.REFUSED


@pytest.mark.parametrize(
    "field",
    [
        "executable",
        "command",
        "argv",
        "filesystem",
        "path",
        "program_path",
        "rpc_url",
        "rpc_endpoint",
        "rpc_host",
        "rpc_port",
        "rpc_method",
        "raw_transaction",
        "credential",
    ],
)
def test_reference_target_caller_refuses_all_execution_shaped_fields(
    field: str,
) -> None:
    payload = {"target_profile": "surfpool_local", "target_id": "reference_vault"}
    payload[field] = "untrusted"

    result = _reference_target_caller().call(
        "solana.reference_target_baseline", payload
    )

    assert result.status is CapabilityStatus.REFUSED


@pytest.mark.parametrize(
    ("module_id", "case_type", "authority"),
    [
        ("other", "reference_target_baseline", AuthorityLevel.READ_ONLY),
        ("beedrill", "other", AuthorityLevel.READ_ONLY),
        ("beedrill", "reference_target_baseline", AuthorityLevel.DRAFT_ONLY),
    ],
)
def test_reference_target_caller_refuses_invalid_scope(
    module_id: str,
    case_type: str,
    authority: AuthorityLevel,
) -> None:
    result = _caller(module_id, case_type, authority).call(
        "solana.reference_target_baseline",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics == {"reason": "scope_not_allowed"}


def test_reference_target_caller_rejects_missing_package_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._reference_target_resource_is_valid",
        lambda: False,
    )

    result = _reference_target_caller().call(
        "solana.reference_target_baseline",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.diagnostics == {"reason": "target_resource_unavailable"}


def test_reference_target_caller_returns_bounded_evidence_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process()
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._reference_target_resource_is_valid",
        lambda: True,
    )
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
    monkeypatch.setattr(
        "beeagent_module.core.isolated_solana_capability._run_reference_target_baseline",
        lambda: {
            "target_id": "reference_vault",
            "initial_state_id": "reference_vault_canonical_v1",
            "economic_unit": "lamports",
            "vault_lamports": 1_000_000,
            "normal_operation": "ok",
            "unsafe_condition": "reachable",
            "detector_signal": "vault_outflow_signal",
            "breaker": "available",
            "containment_config": "broken_available",
            "reset": "equivalent",
            "cleanup": "ok",
        },
    )

    result = _reference_target_caller().call(
        "solana.reference_target_baseline",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.OK
    assert result.data["target_id"] == "reference_vault"
    assert result.data["vault_lamports"] == 1_000_000
    assert result.data["unsafe_condition"] == "reachable"
    assert result.data["reset"] == "equivalent"
    assert process.poll() is not None


def test_transaction_confirmation_requires_confirmed_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[object]]] = []

    def rpc_call(method: str, params: list[object]) -> object:
        calls.append((method, params))
        return {"value": [{"err": None, "confirmationStatus": "confirmed"}]}

    monkeypatch.setattr(solana_capability, "_rpc_call", rpc_call)

    solana_capability._confirm_transaction("signature")

    assert calls == [("getSignatureStatuses", [["signature"]])]


def test_transaction_confirmation_rejects_failed_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solana_capability,
        "_rpc_call",
        lambda _method, _params: {
            "value": [{"err": {"InstructionError": [0, "Custom"]}}]
        },
    )

    with pytest.raises(ValueError, match="transaction failed"):
        solana_capability._confirm_transaction("signature")


def test_transaction_confirmation_has_a_bounded_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(solana_capability, "_STARTUP_TIMEOUT_SECONDS", 0)

    with pytest.raises(TimeoutError, match="confirmation timed out"):
        solana_capability._confirm_transaction("signature")


def test_target_observation_decodes_the_complete_fixed_state_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_bytes = (
        bytes([1, 1])
        + (999_900).to_bytes(8, "little")
        + (0).to_bytes(4, "little")
        + (1).to_bytes(4, "little")
    )
    monkeypatch.setattr(
        solana_capability, "_send_transaction", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        solana_capability,
        "_rpc_call",
        lambda method, _params: (
            {"value": {"data": [b64encode(state_bytes).decode("ascii"), "base64"]}}
            if method == "getAccountInfo"
            else pytest.fail(f"unexpected RPC method: {method}")
        ),
    )

    observed = solana_capability._invoke_and_observe(Keypair(), Keypair(), Keypair(), 2)

    assert observed == (999_900, 1, 1, 0, 1)


def test_target_breaker_requires_a_confirmed_transaction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solana_capability,
        "_send_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            solana_capability._TargetInstructionRejected("target instruction rejected")
        ),
    )

    observed = solana_capability._invoke_and_observe(
        Keypair(), Keypair(), Keypair(), 2, expect_failure=True
    )

    assert observed is None


def test_target_breaker_does_not_accept_a_generic_rpc_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solana_capability,
        "_send_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("fixed local RPC request failed")
        ),
    )

    with pytest.raises(ValueError, match="RPC request failed"):
        solana_capability._invoke_and_observe(
            Keypair(), Keypair(), Keypair(), 2, expect_failure=True
        )


def test_target_breaker_propagates_transaction_confirmation_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solana_capability,
        "_send_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TimeoutError("confirmation timed out")
        ),
    )

    with pytest.raises(TimeoutError, match="confirmation timed out"):
        solana_capability._invoke_and_observe(
            Keypair(), Keypair(), Keypair(), 2, expect_failure=True
        )


@pytest.mark.parametrize(
    ("exception", "status", "reason"),
    [
        (
            solana_capability._ReferenceTargetFailure("preparation_failed"),
            CapabilityStatus.ERROR,
            "preparation_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure("deployment_failed"),
            CapabilityStatus.ERROR,
            "deployment_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure(
                "state_account_preparation_failed"
            ),
            CapabilityStatus.ERROR,
            "state_account_preparation_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure("initialization_failed"),
            CapabilityStatus.ERROR,
            "initialization_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure("state_observation_failed"),
            CapabilityStatus.ERROR,
            "state_observation_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure("reset_reproduction_failed"),
            CapabilityStatus.ERROR,
            "reset_reproduction_failed",
        ),
        (
            solana_capability._ReferenceTargetTimeout("deployment_timeout"),
            CapabilityStatus.TIMEOUT,
            "deployment_timeout",
        ),
    ],
)
def test_reference_target_phase_failure_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    status: CapabilityStatus,
    reason: str,
) -> None:
    process = _Process()
    monkeypatch.setattr(
        solana_capability, "_reference_target_resource_is_valid", lambda: True
    )
    monkeypatch.setattr(solana_capability.shutil, "which", lambda _: "/host/surfpool")
    monkeypatch.setattr(
        solana_capability.subprocess,
        "Popen",
        lambda *_args, **_kwargs: process,
    )
    monkeypatch.setattr(solana_capability, "_wait_for_readiness", lambda _: "ready")
    monkeypatch.setattr(
        solana_capability,
        "_run_reference_target_baseline",
        lambda: (_ for _ in ()).throw(exception),
    )

    result = _reference_target_caller().call(
        "solana.reference_target_baseline",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is status
    assert result.diagnostics == {"reason": reason}
    assert process.poll() is not None
