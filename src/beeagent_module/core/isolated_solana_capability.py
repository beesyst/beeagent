from __future__ import annotations

import http.client
import json
import logging
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from beesdk.capabilities import CapabilityResult, CapabilityStatus
from beesdk.modules import AuthorityLevel as SDKAuthorityLevel

from beeagent_module.core.module_contract import AuthorityLevel

_CAPABILITY_NAME = "solana.isolated_lifecycle"
_MODULE_ID = "beedrill"
_CASE_TYPE = "isolated_solana_smoke"
_TARGET_PROFILE = "surfpool_local"
_RPC_HOST = "127.0.0.1"
_RPC_PORT = 8899
_STARTUP_TIMEOUT_SECONDS = 12.0
_RPC_TIMEOUT_SECONDS = 2.0
_SHUTDOWN_TIMEOUT_SECONDS = 10.0


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
        if (
            self.module_id != _MODULE_ID
            or self.case_type != _CASE_TYPE
            or self.authority.value != AuthorityLevel.READ_ONLY.value
        ):
            return self._refused(capability_name, "scope_not_allowed")
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
            process = subprocess.Popen(
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
    if module_id != _MODULE_ID or case_type != _CASE_TYPE:
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
