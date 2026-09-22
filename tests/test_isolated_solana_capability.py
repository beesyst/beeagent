from __future__ import annotations

import logging
import signal
import subprocess
from base64 import b64encode
from contextlib import contextmanager

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


def _reference_target_attack_caller() -> ScopedSolanaLifecycleCaller:
    return _caller(case_type="reference_target_attack")


def _reference_target_detection_caller() -> ScopedSolanaLifecycleCaller:
    return _caller(case_type="reference_target_detection")


def _reference_target_containment_caller() -> ScopedSolanaLifecycleCaller:
    return _caller(case_type="reference_target_containment_replay")


def _reference_oracle_caller() -> ScopedSolanaLifecycleCaller:
    return _caller(case_type="reference_oracle_manipulation_replay")


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
            "beedrill",
            "reference_target_containment_replay",
            AuthorityLevel.READ_ONLY,
            logging.getLogger("test"),
        )
        is not None
    )
    assert (
        create_capability_caller(
            "run-1",
            "session-1",
            "beedrill",
            "reference_target_detection",
            AuthorityLevel.READ_ONLY,
            logging.getLogger("test"),
        )
        is not None
    )
    assert (
        create_capability_caller(
            "run-1",
            "session-1",
            "beedrill",
            "reference_target_attack",
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


_REFERENCE_TARGET_ATTACK_EVIDENCE = {
    "target_id": "reference_vault",
    "initial_state_id": "reference_vault_canonical_v1",
    "economic_unit": "lamports",
    "attack_start_slot": 42,
    "attack_transaction_signature": "attack-signature",
    "vault_lamports_before": 1_000_000,
    "vault_lamports_after": 999_900,
    "unsafe_withdraw_count_before": 0,
    "unsafe_withdraw_count_after": 1,
    "gross_loss_lamports": 100,
}

_REFERENCE_TARGET_DETECTION_EVIDENCE = {
    "detector_id": "reference_vault_outflow_monitor",
    "signal_id": "vault_outflow_signal",
    "detection_status": "observed",
    "attack_start_slot": 42,
    "first_detection_slot": 44,
}

_REFERENCE_TARGET_CONTAINMENT_EVIDENCE = {
    "target_id": "reference_vault",
    "initial_state_id": "reference_vault_canonical_v1",
    "economic_unit": "lamports",
    "defense_condition": "fixed",
    "attack_sequence_id": "reference_vault_unsafe_withdraw_twice_v1",
    "initial_vault_lamports": 1_000_000,
    "attack_start_slot": 42,
    "first_attack_signature": "attack-1",
    "first_attack_vault_lamports": 999_900,
    "first_attack_unsafe_withdraw_count": 1,
    "detection_status": "observed",
    "first_detection_slot": 44,
    "containment_status": "succeeded",
    "first_containment_slot": 46,
    "second_attack_status": "rejected",
    "final_vault_lamports": 999_900,
    "final_unsafe_withdraw_count": 1,
    "residual_loss_lamports": 100,
}


def test_reference_target_containment_uses_fixed_scope_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
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
        "_run_reference_target_containment",
        lambda condition: {
            **_REFERENCE_TARGET_CONTAINMENT_EVIDENCE,
            "defense_condition": condition,
        },
    )

    result = _reference_target_containment_caller().call(
        "solana.reference_target_containment",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_vault",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.OK
    assert result.data == _REFERENCE_TARGET_CONTAINMENT_EVIDENCE
    assert process.poll() is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_vault",
            "defense_condition": "other",
        },
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_vault",
            "defense_condition": "fixed",
            "rpc_url": "untrusted",
        },
    ],
)
def test_reference_target_containment_refuses_untrusted_input(
    payload: dict[str, str],
) -> None:
    result = _reference_target_containment_caller().call(
        "solana.reference_target_containment", payload
    )

    assert result.status is CapabilityStatus.REFUSED


def test_reference_target_containment_refuses_invalid_scope() -> None:
    result = _caller(
        module_id="other", case_type="reference_target_containment_replay"
    ).call(
        "solana.reference_target_containment",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_vault",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics == {"reason": "scope_not_allowed"}


def test_reference_target_containment_maps_timeout_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
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
        "_run_reference_target_containment",
        lambda _: (_ for _ in ()).throw(
            solana_capability._ReferenceTargetTimeout("containment_observation_timeout")
        ),
    )

    result = _reference_target_containment_caller().call(
        "solana.reference_target_containment",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_vault",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.TIMEOUT
    assert result.diagnostics == {"reason": "containment_observation_timeout"}
    assert process.poll() is not None


@pytest.mark.parametrize("condition", ["broken", "fixed"])
def test_reference_target_containment_proves_target_effect(
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    monkeypatch.setattr(
        solana_capability, "_prepared_reference_target", prepared_target
    )
    monkeypatch.setattr(
        solana_capability,
        "_run_target_operation",
        lambda _payer, _state, _program, code, *_args, **_kwargs: (
            (1_000_000, 0, 0, 0, 0)
            if code == 0
            else (999_900, 1, int(condition == "broken"), 0, 1)
        ),
    )
    monkeypatch.setattr(
        solana_capability, "_reference_vault_outflow_signal", lambda _: True
    )
    slots = iter([42, 44, 46])
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: next(slots))
    calls = iter(
        [
            ((999_900, 0, 0, 0, 1), "attack-1"),
            ((999_800, 1, 1, 0, 2), "attack-2")
            if condition == "broken"
            else (None, None),
        ]
    )
    monkeypatch.setattr(
        solana_capability,
        "_invoke_and_observe_with_signature",
        lambda *_args, **_kwargs: next(calls),
    )
    monkeypatch.setattr(
        solana_capability,
        "_target_state",
        lambda _: (
            (999_800, 1, 1, 0, 2) if condition == "broken" else (999_900, 1, 0, 0, 1)
        ),
    )

    evidence = solana_capability._run_reference_target_containment(condition)

    assert evidence["detection_status"] == "observed"

    first_detection_slot = evidence["first_detection_slot"]
    attack_start_slot = evidence["attack_start_slot"]

    assert isinstance(first_detection_slot, int)
    assert isinstance(attack_start_slot, int)
    assert first_detection_slot >= attack_start_slot

    assert evidence["residual_loss_lamports"] == (200 if condition == "broken" else 100)
    if condition == "broken":
        assert evidence["containment_status"] == "failed"
        assert evidence["second_attack_status"] == "succeeded"
        assert evidence["first_containment_slot"] is None
    else:
        assert evidence["containment_status"] == "succeeded"
        assert evidence["second_attack_status"] == "rejected"
        assert evidence["first_containment_slot"] == 46


def test_reference_target_attack_uses_fixed_scope_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
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
        "_run_reference_target_attack",
        lambda: _REFERENCE_TARGET_ATTACK_EVIDENCE,
    )

    result = _reference_target_attack_caller().call(
        "solana.reference_target_attack",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.OK
    assert result.data == _REFERENCE_TARGET_ATTACK_EVIDENCE
    assert process.poll() is not None


@pytest.mark.parametrize(
    ("module_id", "case_type", "authority"),
    [
        ("other", "reference_target_attack", AuthorityLevel.READ_ONLY),
        ("beedrill", "other", AuthorityLevel.READ_ONLY),
        ("beedrill", "reference_target_attack", AuthorityLevel.DRAFT_ONLY),
    ],
)
def test_reference_target_attack_refuses_invalid_scope(
    module_id: str,
    case_type: str,
    authority: AuthorityLevel,
) -> None:
    result = _caller(module_id, case_type, authority).call(
        "solana.reference_target_attack",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics == {"reason": "scope_not_allowed"}


@pytest.mark.parametrize(
    ("capability_name", "payload"),
    [
        ("other", {"target_profile": "surfpool_local", "target_id": "reference_vault"}),
        (
            "solana.reference_target_attack",
            {"target_profile": "other", "target_id": "reference_vault"},
        ),
        (
            "solana.reference_target_attack",
            {
                "target_profile": "surfpool_local",
                "target_id": "reference_vault",
                "raw_transaction": "untrusted",
            },
        ),
    ],
)
def test_reference_target_attack_refuses_untrusted_input(
    capability_name: str,
    payload: dict[str, str],
) -> None:
    result = _reference_target_attack_caller().call(capability_name, payload)

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
        "rpc_method",
        "raw_transaction",
        "credential",
    ],
)
def test_reference_target_attack_refuses_all_execution_shaped_fields(
    field: str,
) -> None:
    payload = {"target_profile": "surfpool_local", "target_id": "reference_vault"}
    payload[field] = "untrusted"

    result = _reference_target_attack_caller().call(
        "solana.reference_target_attack", payload
    )

    assert result.status is CapabilityStatus.REFUSED


def test_reference_target_attack_maps_failure_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
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
        "_run_reference_target_attack",
        lambda: (_ for _ in ()).throw(
            solana_capability._ReferenceTargetFailure("attack_transaction_failed")
        ),
    )

    result = _reference_target_attack_caller().call(
        "solana.reference_target_attack",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.diagnostics == {"reason": "attack_transaction_failed"}
    assert process.poll() is not None


def test_reference_target_detection_uses_fixed_scope_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
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
        "_run_reference_target_detection",
        lambda: _REFERENCE_TARGET_DETECTION_EVIDENCE,
    )

    result = _reference_target_detection_caller().call(
        "solana.reference_target_detection",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.OK
    assert result.data == _REFERENCE_TARGET_DETECTION_EVIDENCE
    assert process.poll() is not None


@pytest.mark.parametrize(
    ("capability_name", "payload"),
    [
        ("other", {"target_profile": "surfpool_local", "target_id": "reference_vault"}),
        (
            "solana.reference_target_detection",
            {"target_profile": "other", "target_id": "reference_vault"},
        ),
        (
            "solana.reference_target_detection",
            {
                "target_profile": "surfpool_local",
                "target_id": "reference_vault",
                "rpc_endpoint": "untrusted",
            },
        ),
    ],
)
def test_reference_target_detection_refuses_untrusted_input(
    capability_name: str,
    payload: dict[str, str],
) -> None:
    result = _reference_target_detection_caller().call(capability_name, payload)

    assert result.status is CapabilityStatus.REFUSED


@pytest.mark.parametrize(
    ("module_id", "case_type", "authority"),
    [
        ("other", "reference_target_detection", AuthorityLevel.READ_ONLY),
        ("beedrill", "other", AuthorityLevel.READ_ONLY),
        ("beedrill", "reference_target_detection", AuthorityLevel.DRAFT_ONLY),
    ],
)
def test_reference_target_detection_refuses_invalid_scope(
    module_id: str,
    case_type: str,
    authority: AuthorityLevel,
) -> None:
    result = _caller(module_id, case_type, authority).call(
        "solana.reference_target_detection",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics == {"reason": "scope_not_allowed"}


def test_reference_target_detection_maps_detector_failure_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
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
        "_run_reference_target_detection",
        lambda: (_ for _ in ()).throw(
            solana_capability._ReferenceTargetFailure("detector_observation_failed")
        ),
    )

    error = _reference_target_detection_caller().call(
        "solana.reference_target_detection",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert error.status is CapabilityStatus.ERROR
    assert error.diagnostics == {"reason": "detector_observation_failed"}
    monkeypatch.setattr(
        solana_capability,
        "_run_reference_target_detection",
        lambda: (_ for _ in ()).throw(
            solana_capability._ReferenceTargetTimeout("detector_observation_timeout")
        ),
    )

    timeout = _reference_target_detection_caller().call(
        "solana.reference_target_detection",
        {"target_profile": "surfpool_local", "target_id": "reference_vault"},
    )

    assert timeout.status is CapabilityStatus.TIMEOUT
    assert timeout.diagnostics == {"reason": "detector_observation_timeout"}
    assert process.poll() is not None


def test_reference_target_detection_observes_independently_and_orders_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    observed = iter([False, True])
    monkeypatch.setattr(
        solana_capability, "_prepared_reference_target", prepared_target
    )
    monkeypatch.setattr(
        solana_capability,
        "_run_target_operation",
        lambda *_: (1_000_000, 0, 0, 0, 0),
    )
    monkeypatch.setattr(
        solana_capability,
        "_reference_vault_outflow_signal",
        lambda _: next(observed),
    )
    slots = iter([42, 44])
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: next(slots))
    monkeypatch.setattr(
        solana_capability,
        "_invoke_and_observe_with_signature",
        lambda *_: ((999_900, 0, 0, 0, 1), "attack-signature"),
    )

    assert (
        solana_capability._run_reference_target_detection()
        == _REFERENCE_TARGET_DETECTION_EVIDENCE
    )


def test_reference_target_detection_reports_completed_not_observed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    monkeypatch.setattr(
        solana_capability, "_prepared_reference_target", prepared_target
    )
    monkeypatch.setattr(
        solana_capability,
        "_run_target_operation",
        lambda *_: (1_000_000, 0, 0, 0, 0),
    )
    monkeypatch.setattr(
        solana_capability, "_reference_vault_outflow_signal", lambda _: False
    )
    slots = iter([42, 44])
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: next(slots))
    monkeypatch.setattr(
        solana_capability,
        "_invoke_and_observe_with_signature",
        lambda *_: ((999_900, 0, 0, 0, 1), "attack-signature"),
    )

    assert solana_capability._run_reference_target_detection() == {
        "detector_id": "reference_vault_outflow_monitor",
        "signal_id": "vault_outflow_signal",
        "detection_status": "not_observed",
        "attack_start_slot": 42,
    }


def test_reference_target_detection_preserves_semantics_for_fresh_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    observed = iter([False, True, False, True])
    slots = iter([42, 44, 52, 54])
    monkeypatch.setattr(
        solana_capability, "_prepared_reference_target", prepared_target
    )
    monkeypatch.setattr(
        solana_capability,
        "_run_target_operation",
        lambda *_: (1_000_000, 0, 0, 0, 0),
    )
    monkeypatch.setattr(
        solana_capability,
        "_reference_vault_outflow_signal",
        lambda _: next(observed),
    )
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: next(slots))
    monkeypatch.setattr(
        solana_capability,
        "_invoke_and_observe_with_signature",
        lambda *_: ((999_900, 0, 0, 0, 1), "attack-signature"),
    )

    first = solana_capability._run_reference_target_detection()
    second = solana_capability._run_reference_target_detection()

    for evidence in (first, second):
        assert evidence["detector_id"] == "reference_vault_outflow_monitor"
        assert evidence["signal_id"] == "vault_outflow_signal"
        assert evidence["detection_status"] == "observed"

        first_detection_slot = evidence["first_detection_slot"]
        attack_start_slot = evidence["attack_start_slot"]

        assert isinstance(first_detection_slot, int)
        assert isinstance(attack_start_slot, int)
        assert first_detection_slot >= attack_start_slot


def test_reference_target_attack_reports_deterministic_economic_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    before = (1_000_000, 0, 0, 0, 0)
    after = (999_900, 0, 0, 0, 1)
    monkeypatch.setattr(
        solana_capability,
        "_prepared_reference_target",
        prepared_target,
    )
    monkeypatch.setattr(solana_capability, "_run_target_operation", lambda *_: before)
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: 42)
    monkeypatch.setattr(
        solana_capability,
        "_invoke_and_observe_with_signature",
        lambda *_: (after, "attack-signature"),
    )

    assert (
        solana_capability._run_reference_target_attack()
        == _REFERENCE_TARGET_ATTACK_EVIDENCE
    )


def test_reference_target_attack_rejects_inconsistent_economic_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    monkeypatch.setattr(
        solana_capability,
        "_prepared_reference_target",
        prepared_target,
    )
    monkeypatch.setattr(
        solana_capability,
        "_run_target_operation",
        lambda *_: (1_000_000, 0, 0, 0, 0),
    )
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: 42)
    monkeypatch.setattr(
        solana_capability,
        "_invoke_and_observe_with_signature",
        lambda *_: ((999_901, 0, 0, 0, 1), "attack-signature"),
    )

    with pytest.raises(
        solana_capability._ReferenceTargetFailure,
        match="attack_evidence_inconsistent",
    ):
        solana_capability._run_reference_target_attack()


@pytest.mark.parametrize("slot", [True, -1, "42"])
def test_attack_slot_requires_non_negative_integer(
    monkeypatch: pytest.MonkeyPatch,
    slot: object,
) -> None:
    monkeypatch.setattr(solana_capability, "_rpc_call", lambda *_: slot)

    with pytest.raises(ValueError, match="slot response"):
        solana_capability._read_slot()


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


def test_target_breaker_records_a_confirmed_unexpected_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_state = (999_900, 0, 0, 0, 1)
    monkeypatch.setattr(
        solana_capability, "_send_transaction", lambda *_args, **_kwargs: "signature"
    )
    monkeypatch.setattr(solana_capability, "_target_state", lambda _: expected_state)

    assert solana_capability._invoke_and_observe_with_signature(
        Keypair(), Keypair(), Keypair(), 2, expect_failure=True
    ) == (expected_state, "signature")


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


_REFERENCE_ORACLE_EVIDENCE = {
    "target_id": "reference_oracle_market",
    "initial_state_id": "reference_oracle_market_canonical_v1",
    "economic_unit": "micro_usdc",
    "defense_condition": "fixed",
    "attack_sequence_id": "reference_oracle_manipulation_borrow_twice_v1",
    "canonical_oracle_price_micro_usd": 1_000_000,
    "manipulated_oracle_price_micro_usd": 2_000_000,
    "collateral_units": 100,
    "ltv_bps": 5_000,
    "canonical_debt_limit_micro_usdc": 50_000_000,
    "initial_debt_micro_usdc": 50_000_000,
    "initial_reserve_micro_usdc": 100_000_000,
    "attack_start_slot": 42,
    "oracle_manipulation_signature": "oracle-signature",
    "first_borrow_signature": "borrow-signature",
    "first_borrow_debt_micro_usdc": 75_000_000,
    "first_borrow_reserve_micro_usdc": 75_000_000,
    "detector_id": "reference_oracle_deviation_monitor",
    "signal_id": "oracle_price_deviation_signal",
    "detection_status": "observed",
    "first_detection_slot": 44,
    "containment_status": "succeeded",
    "first_containment_slot": 46,
    "containment_state": "borrowing_blocked",
    "second_borrow_status": "rejected",
    "final_debt_micro_usdc": 75_000_000,
    "final_reserve_micro_usdc": 75_000_000,
    "residual_loss_micro_usdc": 25_000_000,
}


def test_reference_oracle_caller_is_created_only_for_approved_case() -> None:
    assert (
        create_capability_caller(
            "run-1",
            "session-1",
            "beedrill",
            "reference_oracle_manipulation_replay",
            AuthorityLevel.READ_ONLY,
            logging.getLogger("test"),
        )
        is not None
    )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "target_profile": "other",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
        },
        {
            "target_profile": "surfpool_local",
            "target_id": "other",
            "defense_condition": "fixed",
        },
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "other",
        },
        {"target_profile": "surfpool_local", "target_id": "reference_oracle_market"},
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
            "price": 2_000_000,
        },
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
            "borrow": 25_000_000,
        },
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
            "rpc_method": "untrusted",
        },
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
            "argv": "untrusted",
        },
    ],
)
def test_reference_oracle_caller_refuses_untrusted_intent(
    payload: dict[str, object],
) -> None:
    result = _reference_oracle_caller().call(
        "solana.reference_oracle_manipulation", payload
    )

    assert result.status is CapabilityStatus.REFUSED


@pytest.mark.parametrize(
    ("module_id", "case_type", "authority"),
    [
        ("other", "reference_oracle_manipulation_replay", AuthorityLevel.READ_ONLY),
        ("beedrill", "other", AuthorityLevel.READ_ONLY),
        ("beedrill", "reference_oracle_manipulation_replay", AuthorityLevel.DRAFT_ONLY),
    ],
)
def test_reference_oracle_caller_refuses_invalid_scope(
    module_id: str, case_type: str, authority: AuthorityLevel
) -> None:
    result = _caller(module_id, case_type, authority).call(
        "solana.reference_oracle_manipulation",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.REFUSED
    assert result.diagnostics == {"reason": "scope_not_allowed"}


def test_reference_oracle_resource_is_the_fixed_package_target() -> None:
    assert solana_capability._reference_oracle_resource_is_valid()


def test_reference_oracle_caller_rejects_missing_package_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        solana_capability, "_reference_oracle_resource_is_valid", lambda: False
    )

    result = _reference_oracle_caller().call(
        "solana.reference_oracle_manipulation",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.diagnostics == {"reason": "target_resource_unavailable"}


def test_reference_oracle_caller_returns_bounded_evidence_and_reaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process()
    monkeypatch.setattr(
        solana_capability, "_reference_oracle_resource_is_valid", lambda: True
    )
    monkeypatch.setattr(solana_capability.shutil, "which", lambda _: "/host/surfpool")
    monkeypatch.setattr(
        solana_capability.subprocess, "Popen", lambda *_args, **_kwargs: process
    )
    monkeypatch.setattr(solana_capability, "_wait_for_readiness", lambda _: "ready")
    monkeypatch.setattr(
        solana_capability,
        "_run_reference_oracle_manipulation",
        lambda condition: {
            **_REFERENCE_ORACLE_EVIDENCE,
            "defense_condition": condition,
        },
    )

    result = _reference_oracle_caller().call(
        "solana.reference_oracle_manipulation",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.OK
    assert result.data == _REFERENCE_ORACLE_EVIDENCE
    assert process.poll() is not None


@pytest.mark.parametrize("condition", ["broken", "fixed"])
def test_reference_oracle_replay_proves_target_effect(
    monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    @contextmanager
    def prepared_target():
        yield solana_capability._PreparedReferenceTarget(
            Keypair(), Keypair(), Keypair()
        )

    monkeypatch.setattr(
        solana_capability, "_prepared_reference_oracle_market", prepared_target
    )
    events: list[str | int] = []
    control_codes: list[int] = []

    def run_operation(_payer, _state, _program, code, *_):
        events.append(code)
        control_codes.append(code)
        return (
            (False, 1_000_000, 50_000_000, 100_000_000)
            if code == 0
            else (False, 2_000_000, 75_000_000, 75_000_000)
            if code == 4
            else (True, 2_000_000, 75_000_000, 75_000_000)
        )

    monkeypatch.setattr(
        solana_capability, "_run_reference_oracle_operation", run_operation
    )
    calls = iter(
        [
            ((False, 2_000_000, 50_000_000, 100_000_000), "oracle-signature"),
            ((False, 2_000_000, 75_000_000, 75_000_000), "borrow-signature"),
            ((False, 2_000_000, 100_000_000, 50_000_000), "second-borrow")
            if condition == "broken"
            else (None, None),
        ]
    )
    monkeypatch.setattr(
        solana_capability,
        "_invoke_reference_oracle_with_signature",
        lambda *_args, **_kwargs: next(calls),
    )
    monkeypatch.setattr(
        solana_capability,
        "_reference_oracle_deviation_signal",
        lambda _: events.append("detection") or True,
    )
    slots = iter([42, 44, 46])
    monkeypatch.setattr(solana_capability, "_read_slot", lambda: next(slots))
    monkeypatch.setattr(
        solana_capability,
        "_reference_oracle_state",
        lambda _: (
            (False, 2_000_000, 100_000_000, 50_000_000)
            if condition == "broken"
            else (True, 2_000_000, 75_000_000, 75_000_000)
        ),
    )

    evidence = solana_capability._run_reference_oracle_manipulation(condition)

    attack_start_slot = evidence["attack_start_slot"]
    first_detection_slot = evidence["first_detection_slot"]

    assert isinstance(attack_start_slot, int)
    assert isinstance(first_detection_slot, int)
    assert attack_start_slot <= first_detection_slot

    assert control_codes == [0, 4 if condition == "broken" else 3]
    assert events == [0, "detection", 4 if condition == "broken" else 3]
    assert evidence["first_borrow_debt_micro_usdc"] == 75_000_000
    assert evidence["first_borrow_reserve_micro_usdc"] == 75_000_000
    if condition == "broken":
        assert evidence["containment_status"] == "failed"
        assert evidence["second_borrow_status"] == "succeeded"
        assert evidence["first_containment_slot"] is None
        assert evidence["final_debt_micro_usdc"] == 100_000_000
        assert evidence["final_reserve_micro_usdc"] == 50_000_000
    else:
        assert evidence["containment_status"] == "succeeded"
        assert evidence["second_borrow_status"] == "rejected"
        assert evidence["first_containment_slot"] == 46
        assert evidence["final_debt_micro_usdc"] == 75_000_000
        assert evidence["final_reserve_micro_usdc"] == 75_000_000


def test_reference_oracle_only_accepts_confirmed_target_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payer, state, program = Keypair(), Keypair(), Keypair()
    monkeypatch.setattr(
        solana_capability,
        "_send_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            solana_capability._RpcRequestFailure({"unavailable": "network"})
        ),
    )

    with pytest.raises(solana_capability._RpcRequestFailure):
        solana_capability._invoke_reference_oracle_with_signature(
            payer, state, program, 2, expect_failure=True
        )

    monkeypatch.setattr(
        solana_capability,
        "_send_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            solana_capability._TargetInstructionRejected("target rejection")
        ),
    )
    assert solana_capability._invoke_reference_oracle_with_signature(
        payer, state, program, 2, expect_failure=True
    ) == (None, None)


def test_reference_oracle_records_a_confirmed_unexpected_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_state = (True, 2_000_000, 75_000_000, 75_000_000)
    monkeypatch.setattr(
        solana_capability, "_send_transaction", lambda *_args, **_kwargs: "signature"
    )
    monkeypatch.setattr(
        solana_capability, "_reference_oracle_state", lambda _: expected_state
    )

    assert solana_capability._invoke_reference_oracle_with_signature(
        Keypair(), Keypair(), Keypair(), 2, expect_failure=True
    ) == (expected_state, "signature")


@pytest.mark.parametrize(
    ("exception", "status", "reason"),
    [
        (
            solana_capability._ReferenceTargetFailure("preparation_failed"),
            CapabilityStatus.ERROR,
            "preparation_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure("build_failed"),
            CapabilityStatus.ERROR,
            "build_failed",
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
            solana_capability._ReferenceTargetFailure("attack_or_detection_failed"),
            CapabilityStatus.ERROR,
            "attack_or_detection_failed",
        ),
        (
            solana_capability._ReferenceTargetFailure(
                "second_borrow_observation_failed"
            ),
            CapabilityStatus.ERROR,
            "second_borrow_observation_failed",
        ),
        (
            solana_capability._ReferenceTargetTimeout("deployment_timeout"),
            CapabilityStatus.TIMEOUT,
            "deployment_timeout",
        ),
    ],
)
def test_reference_oracle_phase_failures_are_explicit_and_reaped(
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    status: CapabilityStatus,
    reason: str,
) -> None:
    process = _Process()
    monkeypatch.setattr(
        solana_capability, "_reference_oracle_resource_is_valid", lambda: True
    )
    monkeypatch.setattr(solana_capability.shutil, "which", lambda _: "/host/surfpool")
    monkeypatch.setattr(
        solana_capability.subprocess, "Popen", lambda *_args, **_kwargs: process
    )
    monkeypatch.setattr(solana_capability, "_wait_for_readiness", lambda _: "ready")
    monkeypatch.setattr(
        solana_capability,
        "_run_reference_oracle_manipulation",
        lambda _: (_ for _ in ()).throw(exception),
    )

    result = _reference_oracle_caller().call(
        "solana.reference_oracle_manipulation",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
        },
    )

    assert result.status is status
    assert result.diagnostics == {"reason": reason}
    assert process.poll() is not None


def test_reference_oracle_forced_cleanup_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _Process(force_cleanup=True)
    monkeypatch.setattr(
        solana_capability, "_reference_oracle_resource_is_valid", lambda: True
    )
    monkeypatch.setattr(solana_capability.shutil, "which", lambda _: "/host/surfpool")
    monkeypatch.setattr(
        solana_capability.subprocess, "Popen", lambda *_args, **_kwargs: process
    )
    monkeypatch.setattr(solana_capability, "_wait_for_readiness", lambda _: "ready")
    monkeypatch.setattr(
        solana_capability,
        "_run_reference_oracle_manipulation",
        lambda _: _REFERENCE_ORACLE_EVIDENCE,
    )

    result = _reference_oracle_caller().call(
        "solana.reference_oracle_manipulation",
        {
            "target_profile": "surfpool_local",
            "target_id": "reference_oracle_market",
            "defense_condition": "fixed",
        },
    )

    assert result.status is CapabilityStatus.ERROR
    assert result.diagnostics == {"reason": "cleanup_forced"}
    assert process.killed
