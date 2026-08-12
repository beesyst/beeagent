from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from beeagent_module.core.settings import is_valid_https_origin

CONTRACT_VERSION = 1
INSTALL_ARTIFACT_NAME = "bitrix_rop_app.json"
MAX_INSTALL_STATE_BYTES = 8192
MAX_INSTALL_STATE_FIELD_LENGTH = 512
MAX_FORM_VALUE_LENGTH = 2048
MAX_FORM_BODY_BYTES = 8192
MAX_FORM_FIELDS = 64
MAX_TOKEN_LIFETIME_SECONDS = 30 * 86400
EMBEDDED_SESSION_AGE_MAX_SECONDS = 86400
_UNIX_EPOCH_THRESHOLD = 1_000_000_000
MAX_BITRIX_RESPONSE_BYTES = 65536
MAX_BITRIX_USER_ID_LENGTH = 20
BITRIX_PRINCIPAL_PREFIX = "bitrix:"

INSTALL_FORM_KEYS: frozenset[str] = frozenset(
    {
        "PROTOCOL",
        "DOMAIN",
        "LANG",
        "member_id",
        "APP_SID",
        "status",
        "AUTH_ID",
        "AUTH_EXPIRES",
        "REFRESH_ID",
        "PLACEMENT",
        "PLACEMENT_OPTIONS",
    }
)
LAUNCH_FORM_KEYS: frozenset[str] = frozenset(
    {
        "AUTH_ID",
        "AUTH_EXPIRES",
        "DOMAIN",
        "member_id",
        "REFRESH_ID",
        "APP_SID",
        "PROTOCOL",
        "LANG",
        "status",
        "PLACEMENT",
        "PLACEMENT_OPTIONS",
    }
)

_DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")


class BitrixEmbedError(RuntimeError):
    pass


class BitrixLaunchError(BitrixEmbedError):
    def __init__(
        self,
        message: str,
        reason: str = "verification_failed",
        bitrix_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.bitrix_error = bitrix_error


@dataclass(frozen=True)
class InstallState:
    portal_origin: str
    portal_domain: str
    member_id: str
    installed_at: str
    contract_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "portal_origin": self.portal_origin,
            "portal_domain": self.portal_domain,
            "member_id": self.member_id,
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InstallState:
        contract_version = data.get("contract_version")
        portal_origin = data.get("portal_origin")
        portal_domain = data.get("portal_domain")
        member_id = data.get("member_id")
        installed_at = data.get("installed_at")

        if (
            not isinstance(contract_version, int)
            or contract_version != CONTRACT_VERSION
        ):
            raise BitrixEmbedError("Unsupported installation state contract version")
        if not isinstance(portal_origin, str) or not is_valid_https_origin(
            portal_origin
        ):
            raise BitrixEmbedError("Invalid installation state portal origin")
        if len(portal_origin) > MAX_INSTALL_STATE_FIELD_LENGTH:
            raise BitrixEmbedError("Invalid installation state portal origin")
        if not isinstance(portal_domain, str) or not portal_domain.strip():
            raise BitrixEmbedError("Invalid installation state portal domain")
        if len(portal_domain) > MAX_INSTALL_STATE_FIELD_LENGTH:
            raise BitrixEmbedError("Invalid installation state portal domain")
        if portal_domain != portal_origin.removeprefix("https://"):
            raise BitrixEmbedError("Invalid installation state portal domain")
        if not isinstance(member_id, str) or not member_id.strip():
            raise BitrixEmbedError("Invalid installation state member id")
        if len(member_id) > MAX_INSTALL_STATE_FIELD_LENGTH:
            raise BitrixEmbedError("Invalid installation state member id")
        if not isinstance(installed_at, str) or not installed_at.strip():
            raise BitrixEmbedError("Invalid installation state timestamp")
        if len(installed_at) > MAX_INSTALL_STATE_FIELD_LENGTH:
            raise BitrixEmbedError("Invalid installation state timestamp")

        return cls(
            portal_origin=portal_origin,
            portal_domain=portal_domain,
            member_id=member_id,
            installed_at=installed_at,
            contract_version=contract_version,
        )


def normalize_domain(raw: str) -> str:
    if not isinstance(raw, str):
        raise BitrixEmbedError("Invalid portal domain")
    domain = raw.strip().lower()
    if domain.startswith("https://"):
        domain = domain[len("https://") :]
    elif domain.startswith("http://"):
        raise BitrixEmbedError("Invalid portal domain")
    domain = domain.rstrip("/")
    if not domain or not _DOMAIN_RE.fullmatch(domain):
        raise BitrixEmbedError("Invalid portal domain")
    return domain


def build_portal_origin(raw_domain: str) -> str:
    domain = normalize_domain(raw_domain)
    return f"https://{domain}"


def _parse_bounded_form(
    form: Mapping[str, Any],
    allowed_keys: frozenset[str],
) -> dict[str, str]:
    if len(form) > MAX_FORM_FIELDS:
        raise BitrixEmbedError("Too many form fields")
    values: dict[str, str] = {}
    for key in allowed_keys:
        if key not in form:
            continue
        value = form[key]
        if not isinstance(value, str):
            raise BitrixEmbedError(f"Invalid form field: {key}")
        if len(value) > MAX_FORM_VALUE_LENGTH:
            raise BitrixEmbedError(f"Form field too long: {key}")
        values[key] = value
    return values


def parse_install_form(form: Mapping[str, Any]) -> dict[str, str]:
    values = _parse_bounded_form(form, INSTALL_FORM_KEYS)
    if not values.get("member_id"):
        raise BitrixEmbedError("Missing required install field: member_id")
    protocol = values.get("PROTOCOL", "")
    if protocol and protocol not in ("https", "1"):
        raise BitrixEmbedError("Invalid install protocol")
    return values


def parse_launch_form(form: Mapping[str, Any]) -> dict[str, str]:
    values = _parse_bounded_form(form, LAUNCH_FORM_KEYS)
    missing = [
        key for key in ("AUTH_ID", "AUTH_EXPIRES", "member_id") if not values.get(key)
    ]
    if missing:
        raise BitrixEmbedError("Missing required launch fields: " + ", ".join(missing))
    return values


def validate_launch_auth_expires(raw: str) -> None:
    if not raw.isdigit() or len(raw) > 12:
        raise BitrixLaunchError("Invalid launch token expiry")
    value = int(raw)
    now = int(time.time())
    if value < _UNIX_EPOCH_THRESHOLD:
        if value <= 0 or value > MAX_TOKEN_LIFETIME_SECONDS:
            raise BitrixLaunchError("Invalid launch token expiry")
        return
    expires = value
    if expires <= now:
        raise BitrixLaunchError("Launch token has expired")
    if expires - now > MAX_TOKEN_LIFETIME_SECONDS:
        raise BitrixLaunchError("Invalid launch token expiry")


def _is_active_user(active: Any) -> bool:
    if active is True:
        return True
    if isinstance(active, str):
        return active.strip().upper() in {"Y", "TRUE", "1"}
    if isinstance(active, int):
        return active == 1
    return False


def _http_error_code(exc: HTTPError) -> str | None:
    try:
        raw = exc.read(4096)
    except Exception:
        return None
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError, UnicodeDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    code = data.get("error")
    if isinstance(code, str) and code:
        return code[:80]
    return None


def verify_bitrix_current_user(
    portal_origin: str,
    auth_id: str,
    timeout: int,
) -> dict[str, Any]:
    url = f"{portal_origin}/rest/user.current"
    payload = urlencode({"auth": auth_id}).encode("utf-8")
    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BITRIX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        error_code = _http_error_code(exc)
        if exc.code in (401, 403):
            raise BitrixLaunchError(
                "Bitrix rejected the launch token",
                reason="token_rejected",
                bitrix_error=error_code,
            )
        raise BitrixLaunchError(
            "Bitrix user verification failed",
            reason="http_error",
            bitrix_error=error_code,
        )
    except URLError as exc:
        if "timed out" in str(exc).lower():
            raise BitrixLaunchError(
                "Bitrix user verification timed out",
                reason="timeout",
            )
        raise BitrixLaunchError(
            "Bitrix user verification failed",
            reason="transport",
        )
    except OSError:
        raise BitrixLaunchError(
            "Bitrix user verification failed",
            reason="transport",
        )

    if len(raw) > MAX_BITRIX_RESPONSE_BYTES:
        raise BitrixLaunchError(
            "Bitrix returned oversized user response",
            reason="response_too_large",
        )

    try:
        data: Any = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError, UnicodeDecodeError:
        raise BitrixLaunchError(
            "Bitrix returned malformed user response",
            reason="malformed_response",
        )

    if not isinstance(data, dict):
        raise BitrixLaunchError(
            "Bitrix returned malformed user response",
            reason="malformed_response",
        )
    if "error" in data:
        error_code = data.get("error")
        if not isinstance(error_code, str):
            error_code = None
        elif len(error_code) > 80:
            error_code = error_code[:80]
        raise BitrixLaunchError(
            "Bitrix rejected the launch token",
            reason="bitrix_error",
            bitrix_error=error_code,
        )

    result = data.get("result")
    if not isinstance(result, dict):
        raise BitrixLaunchError(
            "Bitrix returned malformed user response",
            reason="malformed_response",
        )

    user_id = result.get("ID")
    if isinstance(user_id, bool):
        raise BitrixLaunchError(
            "Bitrix returned malformed user response",
            reason="malformed_response",
        )

    user_id_text = str(user_id).strip() if user_id is not None else ""
    if (
        not user_id_text
        or len(user_id_text) > MAX_BITRIX_USER_ID_LENGTH
        or not user_id_text.isdigit()
    ):
        raise BitrixLaunchError(
            "Bitrix returned malformed user response",
            reason="malformed_response",
        )

    if not _is_active_user(result.get("ACTIVE")):
        raise BitrixLaunchError(
            "Bitrix user is not active",
            reason="inactive_user",
        )

    verified_user = dict(result)
    verified_user["ID"] = user_id_text
    return verified_user


def principal_user_id(user: dict[str, Any]) -> str:
    user_id = user.get("ID")
    if (
        not isinstance(user_id, str)
        or not user_id
        or len(user_id) > MAX_BITRIX_USER_ID_LENGTH
        or not user_id.isdigit()
    ):
        raise BitrixLaunchError("Invalid principal user id")
    return f"{BITRIX_PRINCIPAL_PREFIX}{user_id}"


def is_bitrix_principal_user_id(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith(BITRIX_PRINCIPAL_PREFIX):
        return False
    user_id = value.removeprefix(BITRIX_PRINCIPAL_PREFIX)
    return (
        bool(user_id)
        and len(user_id) <= MAX_BITRIX_USER_ID_LENGTH
        and user_id.isdigit()
    )


def install_state_path(storage_dir: Path) -> Path:
    return Path(storage_dir) / "interfaces" / INSTALL_ARTIFACT_NAME


def load_install_state(storage_dir: Path) -> InstallState | None:
    path = install_state_path(storage_dir)
    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_INSTALL_STATE_BYTES + 1)
        if len(raw) > MAX_INSTALL_STATE_BYTES:
            raise BitrixEmbedError("Installation state is oversized")
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise BitrixEmbedError("Installation state is malformed") from exc
    if not isinstance(data, dict):
        raise BitrixEmbedError("Installation state is malformed")
    return InstallState.from_dict(data)


def create_install_state(storage_dir: Path, state: InstallState) -> bool:
    path = install_state_path(storage_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError:
        return False
    return True
