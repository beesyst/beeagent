from __future__ import annotations

import os
import re
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

_PROFILE_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,255}")
_PROVIDERS = frozenset({"openai_responses", "openai_compatible"})
_FIELDS = ("provider", "model", "api_key_env", "base_url")


def _profile_name(value: object) -> str:
    if not isinstance(value, str) or not _PROFILE_NAME.fullmatch(value):
        raise RuntimeError("Invalid AI profile name")
    return value


def _validate_profile(profile: object, *, selected: bool) -> None:
    if not isinstance(profile, dict):
        raise RuntimeError("Invalid ai.profiles entry, expected mapping")
    provider = profile.get("provider")
    if not isinstance(provider, str) or provider not in _PROVIDERS:
        raise RuntimeError("Unsupported AI profile provider")
    for key in _FIELDS[1:]:
        value = profile.get(key)
        if not isinstance(value, str) or len(value) > 256 or selected and not value:
            raise RuntimeError(f"Invalid AI profile {key}")
        if not value:
            continue
        if key == "model" and not _MODEL.fullmatch(value):
            raise RuntimeError("Invalid AI profile model")
        if key == "api_key_env" and not _ENV_NAME.fullmatch(value):
            raise RuntimeError("Invalid AI profile api_key_env")
        if key == "base_url":
            try:
                parsed = urlsplit(value)
                host = parsed.hostname
                valid_host = (
                    bool(host)
                    and len(host) <= 253
                    and all(
                        re.fullmatch(
                            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label
                        )
                        for label in host.split(".")
                    )
                )
                if host and ":" in host:
                    valid_host = ip_address(host).version == 6
                if (
                    parsed.scheme not in {"http", "https"}
                    or not valid_host
                    or parsed.netloc.endswith(":")
                    or parsed.username is not None
                    or parsed.password is not None
                    or "?" in value
                    or "#" in value
                    or "\\" in value
                    or parsed.port is not None
                    and not 1 <= parsed.port <= 65535
                    or any(ord(char) < 33 or ord(char) > 126 for char in value)
                ):
                    raise ValueError
            except ValueError:
                raise RuntimeError("Invalid AI profile base_url") from None


def validate_ai_profiles(settings: dict[str, Any]) -> None:
    ai = settings.get("ai")
    if not isinstance(ai, dict):
        raise RuntimeError("Invalid ai settings, expected mapping")
    profiles = ai.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise RuntimeError("Invalid or missing ai.profiles, expected non-empty mapping")
    explicit = "default_profile" in ai
    for name, profile in profiles.items():
        _profile_name(name)
        _validate_profile(profile, selected=False)
        if "enabled" in profile:
            if type(profile["enabled"]) is not bool:
                raise RuntimeError(f"Invalid ai.profiles.{name}.enabled, expected bool")
            if explicit:
                raise RuntimeError(
                    "Conflicting AI selectors: remove legacy enabled fields"
                )
    if explicit:
        name = _profile_name(ai["default_profile"])
        if name not in profiles:
            raise RuntimeError("Unknown ai.default_profile")
        _validate_profile(profiles[name], selected=True)
    elif sum(profile.get("enabled") is True for profile in profiles.values()) > 1:
        raise RuntimeError("Exactly one ai.profiles.*.enabled must be true")


def resolve_ai_profile(
    settings: dict[str, Any],
    profile_name: str | None = None,
    *,
    require_api_key: bool = False,
) -> tuple[str, dict[str, str]]:
    validate_ai_profiles(settings)
    ai = settings["ai"]
    profiles = ai["profiles"]
    if profile_name is not None:
        name = _profile_name(profile_name)
    elif "default_profile" in ai:
        name = ai["default_profile"]
    else:
        enabled = [
            name for name, value in profiles.items() if value.get("enabled") is True
        ]
        if len(enabled) != 1:
            raise RuntimeError("Exactly one ai.profiles.*.enabled must be true")
        name = enabled[0]
    if name not in profiles:
        raise RuntimeError("Unknown AI profile selection")
    profile = profiles[name]
    _validate_profile(profile, selected=True)
    if require_api_key and not os.getenv(profile["api_key_env"], "").strip():
        raise RuntimeError(f"Missing required env var '{profile['api_key_env']}'")
    return name, {key: profile[key] for key in _FIELDS}
