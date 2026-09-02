from __future__ import annotations

from collections.abc import Collection, Iterable

SCOPE_WILDCARD = "*"

SURFACE_DASHBOARD = "dashboard"
SURFACE_ROP = "rop"
SURFACE_RUNS = "runs"
SURFACE_MODULES = "modules"
SURFACE_UNKNOWN = "unknown"

EXTERNAL_PRINCIPAL_SCOPES = frozenset({SURFACE_ROP})


def _classify_path(path: str) -> tuple[str, str | None]:
    if path == "/":
        return SURFACE_DASHBOARD, None
    if path == "/rop" or path.startswith("/rop/"):
        return SURFACE_ROP, None
    if path == "/modules":
        return SURFACE_MODULES, None
    if path == "/runs" or path.startswith("/runs/"):
        parts = path.split("/")
        if len(parts) >= 4 and parts[3] == "artifacts":
            artifact_id = parts[4] if len(parts) >= 5 else None
            return SURFACE_RUNS, artifact_id
        return SURFACE_RUNS, None
    if path.startswith("/api/"):
        parts = path.split("/")
        api_name = parts[2] if len(parts) > 2 else ""
        if api_name == "dashboard":
            return SURFACE_DASHBOARD, None
        if api_name == "rop":
            return SURFACE_ROP, None
        if api_name == "actions":
            return SURFACE_ROP, None
        if api_name == "modules":
            return SURFACE_MODULES, None
        if api_name == "runs":
            if len(parts) >= 5 and parts[4] == "artifacts":
                artifact_id = parts[5] if len(parts) >= 6 else None
                return SURFACE_RUNS, artifact_id
            return SURFACE_RUNS, None
        return SURFACE_UNKNOWN, None
    return SURFACE_UNKNOWN, None


def _artifact_run_id(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) >= 5 and parts[1] == "runs" and parts[3] == "artifacts":
        return parts[2]
    if (
        len(parts) >= 6
        and parts[1] == "api"
        and parts[2] == "runs"
        and parts[4] == "artifacts"
    ):
        return parts[3]
    return None


def classify_path(path: str) -> tuple[str, str | None]:
    return _classify_path(path)


def is_resource_allowed(
    scopes: Iterable[str],
    path: str,
    *,
    rop_evidence_artifact_ids: Collection[str] | None = None,
    rop_run_ids: Collection[str] | None = None,
    requested_run_id: str | None = None,
) -> bool:
    scope_set = frozenset(scopes)
    if SCOPE_WILDCARD in scope_set:
        return True

    surface, artifact_id = _classify_path(path)
    rop_runs = frozenset(rop_run_ids or ())

    if surface == SURFACE_DASHBOARD:
        return SURFACE_DASHBOARD in scope_set

    if surface == SURFACE_ROP:
        if SURFACE_ROP not in scope_set:
            return False
        return requested_run_id is None or requested_run_id in rop_runs

    if surface == SURFACE_MODULES:
        return SURFACE_MODULES in scope_set

    if surface == SURFACE_RUNS:
        if SURFACE_RUNS in scope_set:
            return True
        if artifact_id is not None and SURFACE_ROP in scope_set:
            evidence = frozenset(rop_evidence_artifact_ids or ())
            return artifact_id in evidence and _artifact_run_id(path) in rop_runs
        return False

    return False


def home_path(scopes: Iterable[str]) -> str | None:
    scope_set = frozenset(scopes)
    if SCOPE_WILDCARD in scope_set or SURFACE_DASHBOARD in scope_set:
        return "/"
    if SURFACE_ROP in scope_set:
        return "/rop"
    if SURFACE_RUNS in scope_set:
        return "/runs"
    if SURFACE_MODULES in scope_set:
        return "/modules"
    return None
