from __future__ import annotations

import base64
import binascii
import http.client
import importlib.resources
import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, overload

from beesdk.capabilities import CapabilityResult, CapabilityStatus
from beesdk.modules import AuthorityLevel as SDKAuthorityLevel
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import Transaction

from beeagent_module.core.module_contract import AuthorityLevel

_CAPABILITY_NAME = "solana.isolated_lifecycle"
_REFERENCE_TARGET_CAPABILITY_NAME = "solana.reference_target_baseline"
_REFERENCE_TARGET_ATTACK_CAPABILITY_NAME = "solana.reference_target_attack"
_REFERENCE_TARGET_DETECTION_CAPABILITY_NAME = "solana.reference_target_detection"
_REFERENCE_TARGET_CONTAINMENT_CAPABILITY_NAME = "solana.reference_target_containment"
_MODULE_ID = "beedrill"
_CASE_TYPE = "isolated_solana_smoke"
_REFERENCE_TARGET_CASE_TYPE = "reference_target_baseline"
_REFERENCE_TARGET_ATTACK_CASE_TYPE = "reference_target_attack"
_REFERENCE_TARGET_DETECTION_CASE_TYPE = "reference_target_detection"
_REFERENCE_TARGET_CONTAINMENT_CASE_TYPE = "reference_target_containment_replay"
_TARGET_PROFILE = "surfpool_local"
_REFERENCE_TARGET_ID = "reference_vault"
_REFERENCE_TARGET_RESOURCE = "reference_target/reference_vault.json"
_RPC_HOST = "127.0.0.1"
_RPC_PORT = 8899
_STARTUP_TIMEOUT_SECONDS = 12.0
_BUILD_TIMEOUT_SECONDS = 120.0
_DEPLOYMENT_TIMEOUT_SECONDS = 60.0
_RPC_TIMEOUT_SECONDS = 2.0
_SHUTDOWN_TIMEOUT_SECONDS = 10.0

TargetState = tuple[int, int, int, int, int]


@dataclass(frozen=True)
class _PreparedReferenceTarget:
    payer: Keypair
    state: Keypair
    program: Keypair


class _ReferenceTargetFailure(ValueError):
    pass


class _ReferenceTargetTimeout(TimeoutError):
    pass


class _RpcRequestFailure(ValueError):
    def __init__(self, detail: object) -> None:
        super().__init__("fixed local RPC request failed")
        self.detail = detail


class _ConfirmedTransactionFailure(ValueError):
    def __init__(self, detail: object) -> None:
        super().__init__("fixed local transaction failed")
        self.detail = detail


class _TargetInstructionRejected(ValueError):
    pass


@dataclass(frozen=True)
class ScopedSolanaLifecycleCaller:
    run_id: str
    session_id: str
    module_id: str
    case_type: str
    authority: AuthorityLevel
    logger: logging.Logger

    def call(
        self,
        capability_name: str,
        payload: Mapping[str, Any],
    ) -> CapabilityResult:
        if not self._is_allowed_scope():
            return self._refused(capability_name, "scope_not_allowed")
        if self.case_type == _REFERENCE_TARGET_CASE_TYPE:
            return self._call_reference_target_baseline(capability_name, payload)
        if self.case_type == _REFERENCE_TARGET_ATTACK_CASE_TYPE:
            return self._call_reference_target_attack(capability_name, payload)
        if self.case_type == _REFERENCE_TARGET_DETECTION_CASE_TYPE:
            return self._call_reference_target_detection(capability_name, payload)
        if self.case_type == _REFERENCE_TARGET_CONTAINMENT_CASE_TYPE:
            return self._call_reference_target_containment(capability_name, payload)
        if capability_name != _CAPABILITY_NAME:
            return self._refused(capability_name, "unknown_capability")
        if not _is_allowed_payload(payload):
            return self._refused(capability_name, "invalid_payload")

        executable = shutil.which("surfpool")
        if executable is None:
            return self._error(capability_name, "executable_unavailable")

        process: subprocess.Popen[bytes] | None = None
        result: CapabilityResult
        try:
            process = _start_offline_surfpool(executable)
            readiness = _wait_for_readiness(process)
            if readiness != "ready":
                if readiness == "timeout":
                    result = self._timeout(capability_name, "readiness_timeout")
                else:
                    result = self._error(capability_name, readiness)
            else:
                _rpc_health()
                result = CapabilityResult(
                    capability_name=capability_name,
                    status=CapabilityStatus.OK,
                    authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
                    summary="Isolated Solana lifecycle completed",
                    data={
                        "lifecycle": "completed",
                        "readiness": "ok",
                        "rpc": "ok",
                        "cleanup": "ok",
                    },
                )
        except TimeoutError:
            result = self._timeout(capability_name, "rpc_timeout")
        except OSError:
            result = self._error(capability_name, "startup_failed")
        except ValueError:
            result = self._error(capability_name, "rpc_error")
        except Exception:
            result = self._error(capability_name, "runtime_error")
        finally:
            if process is not None:
                cleanup = _reap_process(process)
                if cleanup != "ok":
                    self.logger.warning(
                        "isolated Solana cleanup failed: module_id=%s run_id=%s reason=%s",
                        self.module_id,
                        self.run_id,
                        cleanup,
                    )
                    result = self._error(capability_name, f"cleanup_{cleanup}")
        return result

    def _is_allowed_scope(self) -> bool:
        return (
            self.module_id == _MODULE_ID
            and self.case_type
            in {
                _CASE_TYPE,
                _REFERENCE_TARGET_CASE_TYPE,
                _REFERENCE_TARGET_ATTACK_CASE_TYPE,
                _REFERENCE_TARGET_DETECTION_CASE_TYPE,
                _REFERENCE_TARGET_CONTAINMENT_CASE_TYPE,
            }
            and self.authority.value == AuthorityLevel.READ_ONLY.value
        )

    def _call_reference_target_baseline(
        self,
        capability_name: str,
        payload: Mapping[str, Any],
    ) -> CapabilityResult:
        if capability_name != _REFERENCE_TARGET_CAPABILITY_NAME:
            return self._refused(capability_name, "unknown_capability")
        if not _is_allowed_reference_target_payload(payload):
            return self._refused(capability_name, "invalid_payload")
        if not _reference_target_resource_is_valid():
            return self._error(capability_name, "target_resource_unavailable")

        executable = shutil.which("surfpool")
        if executable is None:
            return self._error(capability_name, "executable_unavailable")

        process: subprocess.Popen[bytes] | None = None
        result: CapabilityResult
        try:
            process = _start_reference_target_surfpool(executable)
            readiness = _wait_for_readiness(process)
            if readiness != "ready":
                if readiness == "timeout":
                    result = self._timeout(capability_name, "readiness_timeout")
                else:
                    result = self._error(capability_name, readiness)
            else:
                evidence = _run_reference_target_baseline()
                result = CapabilityResult(
                    capability_name=capability_name,
                    status=CapabilityStatus.OK,
                    authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
                    summary="Reference target baseline completed",
                    data=evidence,
                )
        except _ReferenceTargetTimeout as exc:
            result = self._timeout(capability_name, str(exc))
        except _ReferenceTargetFailure as exc:
            result = self._error(capability_name, str(exc))
        except TimeoutError:
            result = self._timeout(capability_name, "transaction_confirmation_timeout")
        except OSError:
            result = self._error(capability_name, "prepare_failed")
        except ValueError:
            result = self._error(capability_name, "observe_failed")
        except Exception:
            result = self._error(capability_name, "runtime_error")
        finally:
            if process is not None:
                cleanup = _reap_process(process)
                if cleanup != "ok":
                    self.logger.warning(
                        "reference target cleanup failed: module_id=%s run_id=%s reason=%s",
                        self.module_id,
                        self.run_id,
                        cleanup,
                    )
                    result = self._error(capability_name, f"cleanup_{cleanup}")
        return result

    def _call_reference_target_attack(
        self,
        capability_name: str,
        payload: Mapping[str, Any],
    ) -> CapabilityResult:
        if capability_name != _REFERENCE_TARGET_ATTACK_CAPABILITY_NAME:
            return self._refused(capability_name, "unknown_capability")
        if not _is_allowed_reference_target_payload(payload):
            return self._refused(capability_name, "invalid_payload")
        if not _reference_target_resource_is_valid():
            return self._error(capability_name, "target_resource_unavailable")

        executable = shutil.which("surfpool")
        if executable is None:
            return self._error(capability_name, "executable_unavailable")

        process: subprocess.Popen[bytes] | None = None
        result: CapabilityResult
        try:
            process = _start_reference_target_surfpool(executable)
            readiness = _wait_for_readiness(process)
            if readiness != "ready":
                if readiness == "timeout":
                    result = self._timeout(capability_name, "readiness_timeout")
                else:
                    result = self._error(capability_name, readiness)
            else:
                evidence = _run_reference_target_attack()
                result = CapabilityResult(
                    capability_name=capability_name,
                    status=CapabilityStatus.OK,
                    authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
                    summary="Reference target attack completed",
                    data=evidence,
                )
        except _ReferenceTargetTimeout as exc:
            result = self._timeout(capability_name, str(exc))
        except _ReferenceTargetFailure as exc:
            result = self._error(capability_name, str(exc))
        except TimeoutError:
            result = self._timeout(capability_name, "transaction_confirmation_timeout")
        except OSError:
            result = self._error(capability_name, "prepare_failed")
        except ValueError:
            result = self._error(capability_name, "observe_failed")
        except Exception:
            result = self._error(capability_name, "runtime_error")
        finally:
            if process is not None:
                cleanup = _reap_process(process)
                if cleanup != "ok":
                    self.logger.warning(
                        "reference target attack cleanup failed: module_id=%s run_id=%s reason=%s",
                        self.module_id,
                        self.run_id,
                        cleanup,
                    )
                    result = self._error(capability_name, f"cleanup_{cleanup}")
        return result

    def _call_reference_target_detection(
        self,
        capability_name: str,
        payload: Mapping[str, Any],
    ) -> CapabilityResult:
        if capability_name != _REFERENCE_TARGET_DETECTION_CAPABILITY_NAME:
            return self._refused(capability_name, "unknown_capability")
        if not _is_allowed_reference_target_payload(payload):
            return self._refused(capability_name, "invalid_payload")
        if not _reference_target_resource_is_valid():
            return self._error(capability_name, "target_resource_unavailable")

        executable = shutil.which("surfpool")
        if executable is None:
            return self._error(capability_name, "executable_unavailable")

        process: subprocess.Popen[bytes] | None = None
        result: CapabilityResult
        try:
            process = _start_reference_target_surfpool(executable)
            readiness = _wait_for_readiness(process)
            if readiness != "ready":
                if readiness == "timeout":
                    result = self._timeout(capability_name, "readiness_timeout")
                else:
                    result = self._error(capability_name, readiness)
            else:
                evidence = _run_reference_target_detection()
                result = CapabilityResult(
                    capability_name=capability_name,
                    status=CapabilityStatus.OK,
                    authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
                    summary="Reference target detection completed",
                    data=evidence,
                )
        except _ReferenceTargetTimeout as exc:
            result = self._timeout(capability_name, str(exc))
        except _ReferenceTargetFailure as exc:
            result = self._error(capability_name, str(exc))
        except TimeoutError:
            result = self._timeout(capability_name, "transaction_confirmation_timeout")
        except OSError:
            result = self._error(capability_name, "prepare_failed")
        except ValueError:
            result = self._error(capability_name, "detector_observation_failed")
        except Exception:
            result = self._error(capability_name, "runtime_error")
        finally:
            if process is not None:
                cleanup = _reap_process(process)
                if cleanup != "ok":
                    self.logger.warning(
                        "reference target detection cleanup failed: module_id=%s run_id=%s reason=%s",
                        self.module_id,
                        self.run_id,
                        cleanup,
                    )
                    result = self._error(capability_name, f"cleanup_{cleanup}")
        return result

    def _call_reference_target_containment(
        self,
        capability_name: str,
        payload: Mapping[str, Any],
    ) -> CapabilityResult:
        if capability_name != _REFERENCE_TARGET_CONTAINMENT_CAPABILITY_NAME:
            return self._refused(capability_name, "unknown_capability")
        if not _is_allowed_reference_target_containment_payload(payload):
            return self._refused(capability_name, "invalid_payload")
        if not _reference_target_resource_is_valid():
            return self._error(capability_name, "target_resource_unavailable")

        executable = shutil.which("surfpool")
        if executable is None:
            return self._error(capability_name, "executable_unavailable")

        process: subprocess.Popen[bytes] | None = None
        result: CapabilityResult
        try:
            process = _start_reference_target_surfpool(executable)
            readiness = _wait_for_readiness(process)
            if readiness != "ready":
                if readiness == "timeout":
                    result = self._timeout(capability_name, "readiness_timeout")
                else:
                    result = self._error(capability_name, readiness)
            else:
                evidence = _run_reference_target_containment(
                    payload["defense_condition"]
                )
                result = CapabilityResult(
                    capability_name=capability_name,
                    status=CapabilityStatus.OK,
                    authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
                    summary="Reference target containment completed",
                    data=evidence,
                )
        except _ReferenceTargetTimeout as exc:
            result = self._timeout(capability_name, str(exc))
        except _ReferenceTargetFailure as exc:
            result = self._error(capability_name, str(exc))
        except TimeoutError:
            result = self._timeout(capability_name, "transaction_confirmation_timeout")
        except OSError:
            result = self._error(capability_name, "prepare_failed")
        except ValueError:
            result = self._error(capability_name, "containment_observation_failed")
        except Exception:
            result = self._error(capability_name, "runtime_error")
        finally:
            if process is not None:
                cleanup = _reap_process(process)
                if cleanup != "ok":
                    self.logger.warning(
                        "reference target containment cleanup failed: module_id=%s "
                        "run_id=%s reason=%s",
                        self.module_id,
                        self.run_id,
                        cleanup,
                    )
                    result = self._error(capability_name, f"cleanup_{cleanup}")
        return result

    def _refused(self, capability_name: str, reason: str) -> CapabilityResult:
        return CapabilityResult(
            capability_name=capability_name,
            status=CapabilityStatus.REFUSED,
            authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
            summary="Isolated Solana lifecycle request refused",
            diagnostics={"reason": reason},
        )

    def _timeout(self, capability_name: str, reason: str) -> CapabilityResult:
        return CapabilityResult(
            capability_name=capability_name,
            status=CapabilityStatus.TIMEOUT,
            authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
            summary="Isolated Solana lifecycle timed out",
            diagnostics={"reason": reason},
        )

    def _error(self, capability_name: str, reason: str) -> CapabilityResult:
        return CapabilityResult(
            capability_name=capability_name,
            status=CapabilityStatus.ERROR,
            authority=SDKAuthorityLevel.EXECUTION_CAPABLE,
            summary="Isolated Solana lifecycle failed",
            diagnostics={"reason": reason},
        )


def create_capability_caller(
    run_id: str,
    session_id: str,
    module_id: str,
    case_type: str,
    authority: AuthorityLevel,
    logger: logging.Logger,
) -> ScopedSolanaLifecycleCaller | None:
    if module_id != _MODULE_ID or case_type not in {
        _CASE_TYPE,
        _REFERENCE_TARGET_CASE_TYPE,
        _REFERENCE_TARGET_ATTACK_CASE_TYPE,
        _REFERENCE_TARGET_DETECTION_CASE_TYPE,
        _REFERENCE_TARGET_CONTAINMENT_CASE_TYPE,
    }:
        return None
    return ScopedSolanaLifecycleCaller(
        run_id=run_id,
        session_id=session_id,
        module_id=module_id,
        case_type=case_type,
        authority=authority,
        logger=logger,
    )


def _is_allowed_payload(payload: Mapping[str, Any]) -> bool:
    return (
        isinstance(payload, Mapping)
        and set(payload) == {"target_profile"}
        and payload.get("target_profile") == _TARGET_PROFILE
    )


def _start_offline_surfpool(executable: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            executable,
            "start",
            "--offline",
            "--no-tui",
            "--no-studio",
            "--ci",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _start_reference_target_surfpool(executable: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            executable,
            "start",
            "--offline",
            "--no-deploy",
            "--no-tui",
            "--no-studio",
            "--ci",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _is_allowed_reference_target_payload(payload: Mapping[str, Any]) -> bool:
    return (
        isinstance(payload, Mapping)
        and set(payload) == {"target_profile", "target_id"}
        and payload.get("target_profile") == _TARGET_PROFILE
        and payload.get("target_id") == _REFERENCE_TARGET_ID
    )


def _is_allowed_reference_target_containment_payload(
    payload: Mapping[str, Any],
) -> bool:
    return (
        isinstance(payload, Mapping)
        and set(payload) == {"target_profile", "target_id", "defense_condition"}
        and payload.get("target_profile") == _TARGET_PROFILE
        and payload.get("target_id") == _REFERENCE_TARGET_ID
        and payload.get("defense_condition") in {"broken", "fixed"}
    )


def _reference_target_resource_is_valid() -> bool:
    try:
        resource_root = importlib.resources.files("beedrill").joinpath(
            "reference_target"
        )
        resource = resource_root.joinpath("reference_vault.json")
        parsed = json.loads(resource.read_text(encoding="utf-8"))
        cargo_toml = resource_root.joinpath("Cargo.toml").read_text(encoding="utf-8")
        source = resource_root.joinpath("src/lib.rs").read_text(encoding="utf-8")
    except (
        ImportError,
        FileNotFoundError,
        IsADirectoryError,
        json.JSONDecodeError,
        ModuleNotFoundError,
    ):
        return False
    return (
        'name = "beedrill-reference-vault"' in cargo_toml
        and bool(source.strip())
        and parsed
        == {
            "resource_id": "beedrill.reference_vault.v1",
            "target_id": _REFERENCE_TARGET_ID,
            "canonical_initial_state": {
                "initial_state_id": "reference_vault_canonical_v1",
                "economic_unit": "lamports",
                "vault_lamports": 1_000_000,
                "normal_operation": "deposit",
                "unsafe_condition": "unchecked_withdraw",
                "detector_signal": "vault_outflow_signal",
                "breaker": "available",
                "containment_configurations": ["valid", "broken"],
            },
        }
    )


@contextmanager
def _prepared_reference_target() -> Iterator[_PreparedReferenceTarget]:
    build_tool = shutil.which("cargo-build-sbf")
    solana = shutil.which("solana")
    if build_tool is None or solana is None:
        raise _ReferenceTargetFailure("preparation_failed")
    resource_root = importlib.resources.files("beedrill").joinpath("reference_target")
    with importlib.resources.as_file(resource_root) as source_root:
        with tempfile.TemporaryDirectory(prefix="beeagent-reference-target-") as temp:
            temporary = Path(temp)
            output = temporary / "deploy"
            _run_target_command(
                [
                    build_tool,
                    "--manifest-path",
                    str(source_root / "Cargo.toml"),
                    "--sbf-out-dir",
                    str(output),
                ],
                "build",
                {**os.environ, "CARGO_TARGET_DIR": str(temporary / "cargo-target")},
            )
            program = output / "beedrill_reference_vault.so"
            if not program.is_file():
                raise _ReferenceTargetFailure("build_failed")
            payer = Keypair()
            program_keypair = Keypair()
            state = Keypair()
            payer_path = temporary / "payer.json"
            program_path = temporary / "program.json"
            payer_path.write_text(json.dumps(list(bytes(payer))), encoding="utf-8")
            program_path.write_text(
                json.dumps(list(bytes(program_keypair))), encoding="utf-8"
            )
            try:
                _rpc_request_airdrop(str(payer.pubkey()))
            except TimeoutError as exc:
                raise _ReferenceTargetTimeout(
                    "transaction_confirmation_timeout"
                ) from exc
            except (OSError, ValueError) as exc:
                raise _ReferenceTargetFailure("preparation_failed") from exc
            _run_target_command(
                [
                    solana,
                    "program",
                    "deploy",
                    "--url",
                    "http://127.0.0.1:8899",
                    "--keypair",
                    str(payer_path),
                    "--program-id",
                    str(program_path),
                    str(program),
                ],
                "deployment",
            )
            try:
                _create_state(payer, state, program_keypair)
            except TimeoutError as exc:
                raise _ReferenceTargetTimeout(
                    "transaction_confirmation_timeout"
                ) from exc
            except (OSError, ValueError) as exc:
                raise _ReferenceTargetFailure(
                    "state_account_preparation_failed"
                ) from exc
            yield _PreparedReferenceTarget(payer, state, program_keypair)


def _run_reference_target_baseline() -> dict[str, str | int]:
    with _prepared_reference_target() as target:
        canonical = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "initialization_failed",
        )
        normal = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            1,
            "normal_invocation_failed",
        )
        _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "reset_reproduction_failed",
        )
        unsafe = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            2,
            "unsafe_invocation_failed",
        )
        _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "reset_reproduction_failed",
        )
        _run_target_operation(
            target.payer,
            target.state,
            target.program,
            3,
            "control_invocation_failed",
        )
        breaker = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            2,
            "control_invocation_failed",
            expect_failure=True,
        )
        _run_target_operation(
            target.payer,
            target.state,
            target.program,
            5,
            "control_invocation_failed",
        )
        broken = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            2,
            "unsafe_invocation_failed",
        )
        reset = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "reset_reproduction_failed",
        )
    if (
        canonical != (1_000_000, 0, 0, 0, 0)
        or normal != (1_000_010, 0, 0, 1, 0)
        or unsafe != (999_900, 0, 0, 0, 1)
        or breaker is not None
        or broken != (999_900, 1, 1, 0, 1)
        or reset != canonical
    ):
        raise ValueError("reference target evidence is inconsistent")
    return {
        "target_id": _REFERENCE_TARGET_ID,
        "initial_state_id": "reference_vault_canonical_v1",
        "economic_unit": "lamports",
        "vault_lamports": canonical[0],
        "normal_operation": "ok",
        "unsafe_condition": "reachable",
        "detector_signal": "vault_outflow_signal",
        "breaker": "available",
        "containment_config": "broken_available",
        "reset": "equivalent",
        "cleanup": "ok",
    }


def _run_reference_target_attack() -> dict[str, str | int]:
    with _prepared_reference_target() as target:
        before = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "initialization_failed",
        )
        try:
            attack_start_slot = _read_slot()
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("state_observation_timeout") from exc
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("state_observation_failed") from exc
        try:
            after, signature = _invoke_and_observe_with_signature(
                target.payer,
                target.state,
                target.program,
                2,
            )
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("transaction_confirmation_timeout") from exc
        except _ReferenceTargetFailure:
            raise
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("attack_transaction_failed") from exc
    if (
        before != (1_000_000, 0, 0, 0, 0)
        or after is None
        or signature is None
        or after != (999_900, 0, 0, 0, 1)
    ):
        raise _ReferenceTargetFailure("attack_evidence_inconsistent")
    return {
        "target_id": _REFERENCE_TARGET_ID,
        "initial_state_id": "reference_vault_canonical_v1",
        "economic_unit": "lamports",
        "attack_start_slot": attack_start_slot,
        "attack_transaction_signature": signature,
        "vault_lamports_before": before[0],
        "vault_lamports_after": after[0],
        "unsafe_withdraw_count_before": before[4],
        "unsafe_withdraw_count_after": after[4],
        "gross_loss_lamports": before[0] - after[0],
    }


def _run_reference_target_detection() -> dict[str, str | int]:
    with _prepared_reference_target() as target:
        initial = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "initialization_failed",
        )
        try:
            monitor_started_with_signal = _reference_vault_outflow_signal(target.state)
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("detector_observation_timeout") from exc
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("detector_observation_failed") from exc
        if initial != (1_000_000, 0, 0, 0, 0) or monitor_started_with_signal:
            raise _ReferenceTargetFailure("detector_initial_state_inconsistent")
        try:
            attack_start_slot = _read_slot()
            attack_state, _ = _invoke_and_observe_with_signature(
                target.payer,
                target.state,
                target.program,
                2,
            )
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("transaction_confirmation_timeout") from exc
        except _ReferenceTargetFailure:
            raise
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("attack_transaction_failed") from exc
        if attack_state != (999_900, 0, 0, 0, 1):
            raise _ReferenceTargetFailure("attack_evidence_inconsistent")
        try:
            detected = _reference_vault_outflow_signal(target.state)
            observation_slot = _read_slot()
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("detector_observation_timeout") from exc
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("detector_observation_failed") from exc
    evidence: dict[str, str | int] = {
        "detector_id": "reference_vault_outflow_monitor",
        "signal_id": "vault_outflow_signal",
        "detection_status": "observed" if detected else "not_observed",
        "attack_start_slot": attack_start_slot,
    }
    if detected:
        if observation_slot < attack_start_slot:
            raise _ReferenceTargetFailure("detector_timing_inconsistent")
        evidence["first_detection_slot"] = observation_slot
    return evidence


def _run_reference_target_containment(
    defense_condition: object,
) -> dict[str, str | int | None]:
    if not isinstance(defense_condition, str) or defense_condition not in {
        "broken",
        "fixed",
    }:
        raise _ReferenceTargetFailure("invalid_defense_condition")
    with _prepared_reference_target() as target:
        initial = _run_target_operation(
            target.payer,
            target.state,
            target.program,
            0,
            "initialization_failed",
        )
        if initial != (1_000_000, 0, 0, 0, 0):
            raise _ReferenceTargetFailure("canonical_state_inconsistent")
        try:
            attack_start_slot = _read_slot()
            first_attack, first_signature = _invoke_and_observe_with_signature(
                target.payer,
                target.state,
                target.program,
                2,
            )
            detected = _reference_vault_outflow_signal(target.state)
            first_detection_slot = _read_slot()
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("transaction_confirmation_timeout") from exc
        except _ReferenceTargetFailure:
            raise
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("attack_or_detection_failed") from exc
        if (
            first_attack is None
            or first_attack != (999_900, 0, 0, 0, 1)
            or first_signature is None
            or not detected
            or first_detection_slot < attack_start_slot
        ):
            raise _ReferenceTargetFailure("attack_or_detection_evidence_inconsistent")
        _run_target_operation(
            target.payer,
            target.state,
            target.program,
            3,
            "control_invocation_failed",
        )
        _run_target_operation(
            target.payer,
            target.state,
            target.program,
            5 if defense_condition == "broken" else 6,
            "control_invocation_failed",
        )
        try:
            control_slot = _read_slot()
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("containment_observation_timeout") from exc
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("containment_observation_failed") from exc
        if control_slot < first_detection_slot:
            raise _ReferenceTargetFailure("containment_timing_inconsistent")
        try:
            second_attack, second_signature = _invoke_and_observe_with_signature(
                target.payer,
                target.state,
                target.program,
                2,
                expect_failure=defense_condition == "fixed",
            )
            final = _target_state(target.state)
        except TimeoutError as exc:
            raise _ReferenceTargetTimeout("transaction_confirmation_timeout") from exc
        except _ReferenceTargetFailure:
            raise
        except (OSError, ValueError) as exc:
            raise _ReferenceTargetFailure("second_attack_observation_failed") from exc
    if defense_condition == "broken":
        if (
            second_attack != (999_800, 1, 1, 0, 2)
            or second_signature is None
            or final != second_attack
        ):
            raise _ReferenceTargetFailure("failed_containment_evidence_inconsistent")
        containment_status = "failed"
        containment_slot: int | None = None
        second_attack_status = "succeeded"
    else:
        if (
            second_attack is not None
            or second_signature is not None
            or final != (999_900, 1, 0, 0, 1)
        ):
            raise _ReferenceTargetFailure(
                "successful_containment_evidence_inconsistent"
            )
        containment_status = "succeeded"
        containment_slot = control_slot
        second_attack_status = "rejected"
    return {
        "target_id": _REFERENCE_TARGET_ID,
        "initial_state_id": "reference_vault_canonical_v1",
        "economic_unit": "lamports",
        "defense_condition": defense_condition,
        "attack_sequence_id": "reference_vault_unsafe_withdraw_twice_v1",
        "initial_vault_lamports": initial[0],
        "attack_start_slot": attack_start_slot,
        "first_attack_signature": first_signature,
        "first_attack_vault_lamports": first_attack[0],
        "first_attack_unsafe_withdraw_count": first_attack[4],
        "detection_status": "observed",
        "first_detection_slot": first_detection_slot,
        "containment_status": containment_status,
        "first_containment_slot": containment_slot,
        "second_attack_status": second_attack_status,
        "final_vault_lamports": final[0],
        "final_unsafe_withdraw_count": final[4],
        "residual_loss_lamports": initial[0] - final[0],
    }


def _reference_vault_outflow_signal(state: Keypair) -> bool:
    data = _read_target_state(state)
    return int.from_bytes(data[14:18], "little") > 0


def _run_target_command(
    command: list[str], phase: str, environment: dict[str, str] | None = None
) -> None:
    try:
        subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            env=environment,
            timeout=(
                _BUILD_TIMEOUT_SECONDS
                if phase == "build"
                else _DEPLOYMENT_TIMEOUT_SECONDS
                if phase == "deployment"
                else _STARTUP_TIMEOUT_SECONDS
            ),
        )
    except subprocess.TimeoutExpired as exc:
        raise _ReferenceTargetTimeout(f"{phase}_timeout") from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _ReferenceTargetFailure(f"{phase}_failed") from exc


@overload
def _run_target_operation(
    payer: Keypair,
    state: Keypair,
    program: Keypair,
    code: int,
    failure_reason: str,
    expect_failure: Literal[False] = False,
) -> TargetState: ...


@overload
def _run_target_operation(
    payer: Keypair,
    state: Keypair,
    program: Keypair,
    code: int,
    failure_reason: str,
    expect_failure: Literal[True],
) -> None: ...


def _run_target_operation(
    payer: Keypair,
    state: Keypair,
    program: Keypair,
    code: int,
    failure_reason: str,
    expect_failure: bool = False,
) -> TargetState | None:
    try:
        return _invoke_and_observe(payer, state, program, code, expect_failure)
    except TimeoutError as exc:
        raise _ReferenceTargetTimeout("transaction_confirmation_timeout") from exc
    except _ReferenceTargetFailure:
        raise
    except (OSError, ValueError) as exc:
        raise _ReferenceTargetFailure(failure_reason) from exc


def _rpc_request_airdrop(address: str) -> None:
    _confirm_transaction(_rpc_call("requestAirdrop", [address, 10_000_000_000]))


def _create_state(payer: Keypair, state: Keypair, program: Keypair) -> None:
    lamports = _rpc_call("getMinimumBalanceForRentExemption", [18])
    if not isinstance(lamports, int) or lamports < 1:
        raise ValueError("fixed local rent exemption value is invalid")
    instruction = create_account(
        CreateAccountParams(
            from_pubkey=payer.pubkey(),
            to_pubkey=state.pubkey(),
            lamports=lamports,
            space=18,
            owner=program.pubkey(),
        )
    )
    _send_transaction(payer, [payer, state], instruction)


def _invoke_and_observe(
    payer: Keypair,
    state: Keypair,
    program: Keypair,
    code: int,
    expect_failure: bool = False,
) -> TargetState | None:
    observed_state, _ = _invoke_and_observe_with_signature(
        payer,
        state,
        program,
        code,
        expect_failure,
    )
    return observed_state


def _invoke_and_observe_with_signature(
    payer: Keypair,
    state: Keypair,
    program: Keypair,
    code: int,
    expect_failure: bool = False,
) -> tuple[TargetState | None, str | None]:
    instruction = Instruction(
        program.pubkey(), bytes([code]), [AccountMeta(state.pubkey(), False, True)]
    )
    try:
        signature = _send_transaction(
            payer,
            [payer],
            instruction,
            allow_target_instruction_rejection=expect_failure,
        )
    except _TargetInstructionRejected:
        if expect_failure:
            return None, None
        raise
    if expect_failure:
        raise ValueError("breaker did not refuse unsafe instruction")
    return _target_state(state), signature


def _target_state(state: Keypair) -> TargetState:
    data = _read_target_state(state)
    return (
        int.from_bytes(data[2:10], "little"),
        data[0],
        data[1],
        int.from_bytes(data[10:14], "little"),
        int.from_bytes(data[14:18], "little"),
    )


def _read_target_state(state: Keypair) -> bytes:
    try:
        result = _rpc_call(
            "getAccountInfo", [str(state.pubkey()), {"encoding": "base64"}]
        )
        if not isinstance(result, Mapping):
            raise ValueError("fixed local account response is invalid")
        value = result.get("value")
        if not isinstance(value, Mapping):
            raise ValueError("fixed local account response is invalid")
        encoded_data = value.get("data")
        if (
            not isinstance(encoded_data, list)
            or not encoded_data
            or not isinstance(encoded_data[0], str)
        ):
            raise ValueError("fixed local account response is invalid")
        data = base64.b64decode(encoded_data[0], validate=True)
    except (binascii.Error, TypeError, ValueError) as exc:
        raise _ReferenceTargetFailure("state_observation_failed") from exc
    if len(data) != 18:
        raise _ReferenceTargetFailure("state_observation_failed")
    return data


def _send_transaction(
    payer: Keypair,
    signers: list[Keypair],
    instruction: Instruction,
    allow_target_instruction_rejection: bool = False,
) -> str:
    result = _rpc_call("getLatestBlockhash", [])
    if not isinstance(result, Mapping):
        raise ValueError("fixed local blockhash response is invalid")
    value = result.get("value")
    if not isinstance(value, Mapping):
        raise ValueError("fixed local blockhash response is invalid")
    blockhash = value.get("blockhash")
    if not isinstance(blockhash, str):
        raise ValueError("fixed local blockhash response is invalid")
    blockhash = Hash.from_string(blockhash)
    transaction = Transaction.new_signed_with_payer(
        [instruction], payer.pubkey(), signers, blockhash
    )
    try:
        signature = _rpc_call(
            "sendTransaction",
            [
                base64.b64encode(bytes(transaction)).decode("ascii"),
                {"encoding": "base64"},
            ],
        )
        _confirm_transaction(signature)
    except (_ConfirmedTransactionFailure, _RpcRequestFailure) as exc:
        if allow_target_instruction_rejection and _is_instruction_rejection(exc.detail):
            raise _TargetInstructionRejected(
                "fixed target instruction rejected"
            ) from exc
        raise
    if not isinstance(signature, str):
        raise ValueError("fixed local transaction signature is invalid")
    return signature


def _read_slot() -> int:
    slot = _rpc_call("getSlot", [])
    if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
        raise ValueError("fixed local slot response is invalid")
    return slot


def _is_instruction_rejection(detail: object) -> bool:
    if not isinstance(detail, Mapping):
        return False
    error = detail.get("err")
    if error is None:
        data = detail.get("data")
        error = data.get("err") if isinstance(data, Mapping) else None
    return isinstance(error, Mapping) and "InstructionError" in error


def _confirm_transaction(signature: object) -> None:
    if not isinstance(signature, str):
        raise ValueError("fixed local transaction signature is invalid")
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        statuses = _rpc_call("getSignatureStatuses", [[signature]])
        if not isinstance(statuses, Mapping):
            raise ValueError("fixed local transaction status is invalid")
        values = statuses.get("value")
        if not isinstance(values, list) or len(values) != 1:
            raise ValueError("fixed local transaction status is invalid")
        status = values[0]
        if status is not None:
            if not isinstance(status, Mapping):
                raise ValueError("fixed local transaction status is invalid")
            if status.get("err") is not None:
                raise _ConfirmedTransactionFailure(status)
            if status.get("confirmationStatus") in {"confirmed", "finalized"}:
                return
        time.sleep(0.1)
    raise TimeoutError("fixed local transaction confirmation timed out")


def _rpc_call(method: str, params: list[object]) -> object:
    connection = http.client.HTTPConnection(
        _RPC_HOST, _RPC_PORT, timeout=_RPC_TIMEOUT_SECONDS
    )
    try:
        connection.request(
            "POST",
            "/",
            body=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise _RpcRequestFailure(None) from exc
    if not isinstance(payload, Mapping):
        raise _RpcRequestFailure(None)
    if response.status != 200 or "error" in payload:
        raise _RpcRequestFailure(payload.get("error"))
    if "result" not in payload:
        raise _RpcRequestFailure(None)
    return payload["result"]


def _wait_for_readiness(process: subprocess.Popen[bytes]) -> str:
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return "early_process_exit"
        try:
            _rpc_health()
            return "ready"
        except TimeoutError, ValueError:
            time.sleep(0.1)
    return "timeout"


def _rpc_health() -> None:
    connection = http.client.HTTPConnection(
        _RPC_HOST,
        _RPC_PORT,
        timeout=_RPC_TIMEOUT_SECONDS,
    )
    try:
        connection.request(
            "POST",
            "/",
            body=json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "getHealth", "params": []}
            ),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        body = response.read()
    except TimeoutError:
        raise
    except (OSError, http.client.HTTPException) as exc:
        raise ValueError("RPC connection failed") from exc
    finally:
        connection.close()
    if response.status != 200:
        raise ValueError("RPC returned an unexpected status")
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("RPC returned invalid JSON") from exc
    if result.get("result") != "ok":
        raise ValueError("RPC health check failed")


def _reap_process(process: subprocess.Popen[bytes]) -> str:
    if process.poll() is not None:
        return "ok"
    try:
        process.send_signal(signal.SIGINT)
    except OSError:
        pass
    try:
        process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        return "ok"
    except OSError, subprocess.TimeoutExpired:
        pass
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
        return "ok"
    except OSError, subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
            return "forced"
        except OSError, subprocess.TimeoutExpired:
            return "reap_failed"
