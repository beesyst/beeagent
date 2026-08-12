from __future__ import annotations

import pytest

from beeagent_module.core.authorization import (
    EXTERNAL_PRINCIPAL_SCOPES,
    SCOPE_WILDCARD,
    classify_path,
    home_path,
    is_resource_allowed,
)

_ROP_EVIDENCE = frozenset(
    {
        "operator_summary_json",
        "source_diagnostics_json",
        "classified_events_json",
    }
)


class TestClassifyPath:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/", ("dashboard", None)),
            ("/rop", ("rop", None)),
            ("/rop/events/evt-1", ("rop", None)),
            ("/modules", ("modules", None)),
            ("/runs", ("runs", None)),
            ("/runs/run-1", ("runs", None)),
            ("/runs/run-1/rop", ("runs", None)),
            ("/runs/run-1/artifacts", ("runs", None)),
            (
                "/runs/run-1/artifacts/operator_summary_json",
                ("runs", "operator_summary_json"),
            ),
            ("/api/dashboard", ("dashboard", None)),
            ("/api/rop/dashboard", ("rop", None)),
            ("/api/rop/events/evt-1", ("rop", None)),
            ("/api/modules", ("modules", None)),
            ("/api/runs", ("runs", None)),
            ("/api/runs/run-1", ("runs", None)),
            ("/api/runs/run-1/artifacts", ("runs", None)),
            (
                "/api/runs/run-1/artifacts/classified_events_json",
                ("runs", "classified_events_json"),
            ),
            ("/api/unknown", ("unknown", None)),
            ("/unknown", ("unknown", None)),
            ("/venues/x", ("unknown", None)),
            ("/components", ("unknown", None)),
        ],
    )
    def test_classify(self, path: str, expected: tuple[str, str | None]) -> None:
        assert classify_path(path) == expected


class TestIsResourceAllowed:
    def test_wildcard_allows_everything(self) -> None:
        for path in [
            "/",
            "/rop",
            "/runs",
            "/runs/run-1/artifacts/anything",
            "/modules",
            "/api/dashboard",
            "/api/unknown",
            "/components",
        ]:
            assert is_resource_allowed([SCOPE_WILDCARD], path)

    def test_rop_scope_allows_rop_surfaces(self) -> None:
        assert is_resource_allowed(["rop"], "/rop")
        assert is_resource_allowed(["rop"], "/rop/events/evt-1")
        assert is_resource_allowed(["rop"], "/api/rop/dashboard")
        assert is_resource_allowed(["rop"], "/api/rop/events/evt-1")

    def test_rop_scope_denies_other_surfaces(self) -> None:
        for path in [
            "/",
            "/runs",
            "/runs/run-1",
            "/modules",
            "/api/dashboard",
            "/api/runs",
            "/api/modules",
        ]:
            assert not is_resource_allowed(["rop"], path)

    def test_rop_scope_allows_only_bounded_evidence_artifacts(self) -> None:
        allowed = is_resource_allowed(
            ["rop"],
            "/runs/run-1/artifacts/operator_summary_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=frozenset({"run-1"}),
        )
        assert allowed
        denied = is_resource_allowed(
            ["rop"],
            "/runs/run-1/artifacts/run_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=frozenset({"run-1"}),
        )
        assert not denied
        list_denied = is_resource_allowed(
            ["rop"],
            "/runs/run-1/artifacts",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=frozenset({"run-1"}),
        )
        assert not list_denied

    def test_rop_scope_denies_evidence_without_allowlist(self) -> None:
        assert not is_resource_allowed(
            ["rop"], "/runs/run-1/artifacts/operator_summary_json"
        )

    def test_dashboard_scope_grants_dashboard_only(self) -> None:
        assert is_resource_allowed(["dashboard"], "/")
        assert is_resource_allowed(["dashboard"], "/api/dashboard")
        assert not is_resource_allowed(["dashboard"], "/rop")
        assert not is_resource_allowed(["dashboard"], "/runs")

    def test_runs_scope_grants_runs_and_artifacts(self) -> None:
        assert is_resource_allowed(["runs"], "/runs")
        assert is_resource_allowed(["runs"], "/runs/run-1")
        assert is_resource_allowed(["runs"], "/runs/run-1/artifacts")
        assert is_resource_allowed(["runs"], "/api/runs")
        assert not is_resource_allowed(["runs"], "/")
        assert not is_resource_allowed(["runs"], "/rop")

    def test_modules_scope_grants_modules_only(self) -> None:
        assert is_resource_allowed(["modules"], "/modules")
        assert is_resource_allowed(["modules"], "/api/modules")
        assert not is_resource_allowed(["modules"], "/")

    def test_unknown_surface_default_deny(self) -> None:
        assert not is_resource_allowed(["rop"], "/components")
        assert not is_resource_allowed(["runs"], "/components")
        assert not is_resource_allowed(["dashboard"], "/api/unknown")
        assert not is_resource_allowed(["modules"], "/venues/x")

    def test_empty_scopes_deny_everything(self) -> None:
        for path in ["/", "/rop", "/runs", "/modules"]:
            assert not is_resource_allowed([], path)


class TestHomePath:
    def test_wildcard_and_dashboard_home_is_root(self) -> None:
        assert home_path([SCOPE_WILDCARD]) == "/"
        assert home_path(["dashboard"]) == "/"

    def test_rop_home(self) -> None:
        assert home_path(["rop"]) == "/rop"
        assert home_path(["rop", "runs"]) == "/rop"

    def test_runs_and_modules_homes(self) -> None:
        assert home_path(["runs"]) == "/runs"
        assert home_path(["modules"]) == "/modules"

    def test_no_home_for_empty(self) -> None:
        assert home_path([]) is None


def test_external_principal_scopes_are_rop_only() -> None:
    assert EXTERNAL_PRINCIPAL_SCOPES == frozenset({"rop"})


class TestRopRunOwnership:
    _ROP_RUNS = frozenset({"run-rop-1", "run-rop-2"})

    def test_wildcard_ignores_run_ownership(self) -> None:
        assert is_resource_allowed(
            [SCOPE_WILDCARD],
            "/rop?run_id=run-non-rop",
        )
        assert is_resource_allowed(
            [SCOPE_WILDCARD],
            "/runs/run-non-rop/artifacts/classified_events_json",
        )

    def test_rop_surface_without_run_id_allowed(self) -> None:
        assert is_resource_allowed(["rop"], "/rop")
        assert is_resource_allowed(["rop"], "/api/rop/dashboard")

    def test_rop_surface_with_known_rop_run_allowed(self) -> None:
        assert is_resource_allowed(
            ["rop"],
            "/rop",
            rop_run_ids=self._ROP_RUNS,
            requested_run_id="run-rop-1",
        )
        assert is_resource_allowed(
            ["rop"],
            "/api/rop/dashboard",
            rop_run_ids=self._ROP_RUNS,
            requested_run_id="run-rop-2",
        )

    def test_rop_surface_with_unknown_run_denied(self) -> None:
        assert not is_resource_allowed(
            ["rop"],
            "/rop",
            rop_run_ids=self._ROP_RUNS,
            requested_run_id="run-non-rop",
        )
        assert not is_resource_allowed(
            ["rop"],
            "/api/rop/dashboard",
            rop_run_ids=self._ROP_RUNS,
            requested_run_id="run-non-rop",
        )

    def test_rop_surface_with_empty_rop_runs_denies_explicit_run(self) -> None:
        assert not is_resource_allowed(
            ["rop"],
            "/rop",
            rop_run_ids=frozenset(),
            requested_run_id="run-rop-1",
        )

    def test_rop_event_detail_with_unknown_run_denied(self) -> None:
        assert not is_resource_allowed(
            ["rop"],
            "/rop/events/evt-1",
            rop_run_ids=self._ROP_RUNS,
            requested_run_id="run-non-rop",
        )
        assert not is_resource_allowed(
            ["rop"],
            "/api/rop/events/evt-1",
            rop_run_ids=self._ROP_RUNS,
            requested_run_id="run-non-rop",
        )

    def test_rop_evidence_requires_known_rop_run(self) -> None:
        allowed = is_resource_allowed(
            ["rop"],
            "/runs/run-rop-1/artifacts/classified_events_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=self._ROP_RUNS,
        )
        assert allowed
        denied_run = is_resource_allowed(
            ["rop"],
            "/runs/run-non-rop/artifacts/classified_events_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=self._ROP_RUNS,
        )
        assert not denied_run
        denied_artifact = is_resource_allowed(
            ["rop"],
            "/runs/run-rop-1/artifacts/run_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=self._ROP_RUNS,
        )
        assert not denied_artifact

    def test_rop_evidence_api_requires_known_rop_run(self) -> None:
        allowed = is_resource_allowed(
            ["rop"],
            "/api/runs/run-rop-1/artifacts/classified_events_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=self._ROP_RUNS,
        )
        assert allowed
        denied = is_resource_allowed(
            ["rop"],
            "/api/runs/run-non-rop/artifacts/classified_events_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
            rop_run_ids=self._ROP_RUNS,
        )
        assert not denied

    def test_rop_evidence_without_rop_runs_denied(self) -> None:
        assert not is_resource_allowed(
            ["rop"],
            "/runs/run-rop-1/artifacts/classified_events_json",
            rop_evidence_artifact_ids=_ROP_EVIDENCE,
        )

    def test_runs_scope_unaffected_by_run_ownership(self) -> None:
        assert is_resource_allowed(
            ["runs"],
            "/runs/run-non-rop/artifacts/run_json",
            rop_run_ids=self._ROP_RUNS,
        )
        assert is_resource_allowed(
            ["runs"],
            "/runs",
            rop_run_ids=self._ROP_RUNS,
        )
