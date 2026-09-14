from __future__ import annotations

import json
import logging
import os
import shutil
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from beeagent_module.cases import rop_dashboard as rop_dashboard_module
from beeagent_module.cases.rop_dashboard import (
    build_rop_dashboard as _build_rop_dashboard,
)
from tests.rop_dashboard_test_support import seed_rop_dashboard_run

TEST_PLAN_LEAD = 20

build_rop_dashboard = partial(_build_rop_dashboard, plan_lead=TEST_PLAN_LEAD)

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_dashboard")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    return seed_rop_dashboard_run(tmp_path)


class TestRopWebProjectionLifecycle:
    def _storage_with_runs(self, source: Path, target: Path, count: int) -> Path:
        storage_dir = target / "storage"
        runs_dir = storage_dir / "runs"
        runs_dir.mkdir(parents=True)
        for index in range(count):
            shutil.copytree(source, runs_dir / f"run-many-{index:03d}")
        return storage_dir

    def test_full_regeneration_reuses_history_for_all_periods(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "many", 12)
        aggregate_calls = 0
        run_enumerations = 0
        original_aggregate = rop_dashboard_module._aggregate_period_events
        original_list_runs = rop_dashboard_module._list_run_ids

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
            prepared_history: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
                prepared_history=prepared_history,
            )

        def counted_list_runs(runs_dir: Path) -> list[str]:
            nonlocal run_enumerations
            run_enumerations += 1
            return original_list_runs(runs_dir)

        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )
        monkeypatch.setattr(rop_dashboard_module, "_list_run_ids", counted_list_runs)

        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )

        assert aggregate_calls == 12
        assert run_enumerations == 1
        assert projection["total_runs"] == 12
        assert len(projection["run_ids"]) == 12
        assert set(projection["dashboards"][projection["run_ids"][0]]) == set(
            rop_dashboard_module.ALLOWED_PERIODS
        )

    def test_full_regeneration_scales_linearly_with_historical_runs(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        small_storage = self._storage_with_runs(run_dir, tmp_path / "small", 8)
        large_storage = self._storage_with_runs(run_dir, tmp_path / "large", 16)
        read_calls = 0
        aggregate_calls = 0
        original_read_dict = rop_dashboard_module._read_json_dict
        original_read_list = rop_dashboard_module._read_json_list
        original_aggregate = rop_dashboard_module._aggregate_period_events

        def counted_read_dict(path: Path) -> dict[str, Any] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_dict(path)

        def counted_read_list(path: Path) -> list[dict[str, Any]] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_list(path)

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
            prepared_history: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
                prepared_history=prepared_history,
            )

        monkeypatch.setattr(rop_dashboard_module, "_read_json_dict", counted_read_dict)
        monkeypatch.setattr(rop_dashboard_module, "_read_json_list", counted_read_list)
        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )

        rop_dashboard_module.build_rop_web_projection(
            small_storage,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        small_reads = read_calls
        rop_dashboard_module.build_rop_web_projection(
            large_storage,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        large_reads = read_calls - small_reads

        assert aggregate_calls == 24
        assert large_reads <= small_reads * 4

    def test_configured_periods_reuse_loaded_projection_artifacts(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "periods", 6)
        read_calls = 0
        aggregate_calls = 0
        original_read_dict = rop_dashboard_module._read_json_dict
        original_read_list = rop_dashboard_module._read_json_list
        original_aggregate = rop_dashboard_module._aggregate_period_events

        def counted_read_dict(path: Path) -> dict[str, Any] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_dict(path)

        def counted_read_list(path: Path) -> list[dict[str, Any]] | None:
            nonlocal read_calls
            read_calls += 1
            return original_read_list(path)

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
            prepared_history: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
                prepared_history=prepared_history,
            )

        monkeypatch.setattr(rop_dashboard_module, "_read_json_dict", counted_read_dict)
        monkeypatch.setattr(rop_dashboard_module, "_read_json_list", counted_read_list)
        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )

        rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            ["all"],
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        one_period_reads = read_calls
        rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        all_period_reads = read_calls - one_period_reads

        assert aggregate_calls == 12
        assert all_period_reads <= one_period_reads + 2

    def test_v2_generation_reuses_period_independent_direct_reads(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "v2-cache", 1)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        interfaces = storage_dir / "interfaces"
        interfaces.mkdir(exist_ok=True)
        (interfaces / "rop_writeback_state.json").write_text(
            json.dumps({"events": {}}), encoding="utf-8"
        )
        from beeagent_module.core import rop_final_decision

        original_read_text = Path.read_text
        original_final_read = rop_final_decision._read_json
        counts = {"writeback": 0, "final_decisions": 0}

        def counted_read_text(
            path: Path,
            encoding: str | None = None,
            errors: str | None = None,
            newline: str | None = None,
        ) -> str:
            if path.name == "rop_writeback_state.json":
                counts["writeback"] += 1
            return original_read_text(
                path,
                encoding=encoding,
                errors=errors,
                newline=newline,
            )

        def counted_final_read(path: Path) -> object:
            if path.name == "rop_final_decisions.json":
                counts["final_decisions"] += 1
            return original_final_read(path)

        monkeypatch.setattr(Path, "read_text", counted_read_text)
        monkeypatch.setattr(rop_final_decision, "_read_json", counted_final_read)
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )

        assert counts == {"writeback": 1, "final_decisions": 1}

    def test_normal_refresh_updates_one_entry_without_catalog_rebuild(
        self, run_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "incremental", 3)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        shutil.copytree(run_dir, storage_dir / "runs" / "run-new")
        aggregate_calls = 0
        original_aggregate = rop_dashboard_module._aggregate_period_events

        def counted_aggregate(
            runs_dir: Path,
            anchor_run_id: str,
            anchor_client_id: str,
            logger: logging.Logger,
            prepared_history: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            nonlocal aggregate_calls
            aggregate_calls += 1
            return original_aggregate(
                runs_dir,
                anchor_run_id,
                anchor_client_id,
                logger,
                prepared_history=prepared_history,
            )

        def fail_catalog_enumeration(*_args: object, **_kwargs: object) -> list[str]:
            raise AssertionError("normal refresh must not rebuild the full catalog")

        monkeypatch.setattr(
            rop_dashboard_module, "_aggregate_period_events", counted_aggregate
        )
        monkeypatch.setattr(
            rop_dashboard_module, "_list_rop_run_ids", fail_catalog_enumeration
        )

        refreshed = rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            "run-new",
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )

        index = rop_dashboard_module.rop_web_projection_index(storage_dir)
        assert refreshed is True
        assert aggregate_calls == 1
        assert index is not None
        assert index["latest_run_id"] == "run-new"
        assert index["total_runs"] == 4
        assert rop_dashboard_module.rop_web_projection_entry_path(
            storage_dir, "run-new"
        ).exists()
        manifest = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
        assert manifest is not None
        assert manifest["run_ids"] == index["run_ids"]
        assert manifest["total_runs"] == index["total_runs"]
        assert (
            rop_dashboard_module.read_rop_web_projection_v2_view(
                storage_dir, manifest, "run-new", "api", "all"
            )
            is not None
        )

    def test_missing_projection_stays_unavailable_until_bootstrap(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "missing", 3)

        refreshed = rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            list(rop_dashboard_module.ALLOWED_PERIODS),
            "run-many-000",
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )

        assert refreshed is False
        assert rop_dashboard_module.rop_web_projection_index(storage_dir) is None

    def test_missing_v2_manifest_prevents_refresh_without_mutation(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "missing-v2", 1)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            ["7d"],
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        index_path = storage_dir / "interfaces" / "rop_web_projection.json"
        before_index = index_path.read_bytes()
        (storage_dir / "interfaces" / "rop_web_projection_v2.json").unlink()

        assert not rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            ["7d"],
            "run-many-000",
            _null_logger(),
            is_new_run=False,
            plan_lead=TEST_PLAN_LEAD,
        )
        assert index_path.read_bytes() == before_index

    @pytest.mark.parametrize(
        "malformed_index",
        (
            {"total_runs": None},
            {"total_runs": True},
            {"total_runs": "3"},
            {"run_ids": []},
            {"run_ids": ["run-many-000"] * 21},
        ),
    )
    def test_malformed_index_prevents_refresh_without_artifact_mutation(
        self,
        run_dir: Path,
        tmp_path: Path,
        malformed_index: dict[str, object],
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "malformed", 1)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            ["7d"],
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        index_path = storage_dir / "interfaces" / "rop_web_projection.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index.update(malformed_index)
        index_path.write_text(json.dumps(index), encoding="utf-8")
        entry_path = rop_dashboard_module.rop_web_projection_entry_path(
            storage_dir, "run-many-000"
        )
        before_index = index_path.read_bytes()
        before_entry = entry_path.read_bytes()

        assert rop_dashboard_module.rop_web_projection_index(storage_dir) is None
        assert (
            rop_dashboard_module.refresh_rop_web_projection(
                storage_dir,
                ["7d"],
                "run-many-000",
                _null_logger(),
                is_new_run=False,
                plan_lead=TEST_PLAN_LEAD,
            )
            is False
        )
        assert index_path.read_bytes() == before_index
        assert entry_path.read_bytes() == before_entry

    def test_existing_run_refresh_preserves_catalog_scalar(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "existing", 3)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            ["7d"],
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        before = rop_dashboard_module.rop_web_projection_index(storage_dir)

        refreshed = rop_dashboard_module.refresh_rop_web_projection(
            storage_dir,
            ["7d"],
            "run-many-000",
            _null_logger(),
            is_new_run=False,
            plan_lead=TEST_PLAN_LEAD,
        )

        after = rop_dashboard_module.rop_web_projection_index(storage_dir)
        assert refreshed is True
        assert before is not None
        assert after is not None
        assert after["run_ids"] == before["run_ids"]
        assert after["total_runs"] == before["total_runs"]

    def test_failed_publication_keeps_previous_index_valid(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "atomic", 1)
        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            ["7d"],
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )
        rop_dashboard_module.write_rop_web_projection(
            storage_dir, projection, _null_logger()
        )
        before = rop_dashboard_module.rop_web_projection_index(storage_dir)

        with pytest.raises(ValueError):
            rop_dashboard_module.write_rop_web_projection(
                storage_dir,
                {
                    "schema_version": 1,
                    "run_ids": ["run-missing"],
                    "total_runs": 1,
                    "dashboards": {},
                },
                _null_logger(),
            )

        assert rop_dashboard_module.rop_web_projection_index(storage_dir) == before

    def test_full_projection_preserves_selected_run_anchor_semantics(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = self._storage_with_runs(run_dir, tmp_path / "anchors", 2)
        first = storage_dir / "runs" / "run-many-000"
        second = storage_dir / "runs" / "run-many-001"

        for path, generated_at, priority, case_type, bitrix_status in (
            (first, "2026-01-01T00:00:00Z", "high", "new_lead", "matched_lead"),
            (second, "2026-01-02T00:00:00Z", "low", "existing_deal", "not_found"),
        ):
            normalized = json.loads((path / "normalized_events.json").read_text())
            normalized[0]["message_id"] = "<tied@example.test>"
            (path / "normalized_events.json").write_text(json.dumps(normalized))
            classified = json.loads((path / "classified_events.json").read_text())
            classified[0]["priority"] = priority
            classified[0]["case_type"] = case_type
            (path / "classified_events.json").write_text(json.dumps(classified))
            reconciliation = json.loads(
                (path / "bitrix_reconciliation.json").read_text()
            )
            reconciliation["items"] = [
                {"event_id": "evt-001", "bitrix_match_status": bitrix_status}
            ]
            (path / "bitrix_reconciliation.json").write_text(json.dumps(reconciliation))
            current_state = json.loads((path / "rop_current_state.json").read_text())
            current_state["generated_at_utc"] = generated_at
            (path / "rop_current_state.json").write_text(json.dumps(current_state))

        projection = rop_dashboard_module.build_rop_web_projection(
            storage_dir,
            ["all"],
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )

        assert projection["run_ids"] == ["run-many-001", "run-many-000"]

        for candidate_run_id in projection["run_ids"]:
            entry = projection["dashboards"][candidate_run_id]["all"]
            direct = build_rop_dashboard(
                storage_dir,
                "all",
                _null_logger(),
                run_id=candidate_run_id,
                aggregate_runs=True,
            )
            assert entry["business_kpi"] == direct["business_kpi"]
            assert entry["queues"] == direct["queues"]
            assert entry["series"] == direct["series"]
            assert entry["evidence_links"] == direct["evidence_links"]
            assert entry["run_id"] == candidate_run_id

        first_entry = projection["dashboards"]["run-many-000"]["all"]
        tied = [
            item
            for item in first_entry["queues"]["high_priority"]
            if item["event_id"] == "evt-001"
        ]
        assert len(tied) == 1
        assert tied[0]["run_id"] == "run-many-000"
        assert tied[0]["priority"] == "high"
        assert tied[0]["case_type"] == "new_lead"

        second_entry = projection["dashboards"]["run-many-001"]["all"]
        lost = [
            item
            for item in second_entry["queues"]["lost_in_bitrix"]
            if item["event_id"] == "evt-001"
        ]
        assert len(lost) == 1
        assert lost[0]["run_id"] == "run-many-001"
        assert lost[0]["priority"] == "low"
        assert lost[0]["case_type"] == "existing_deal"


def test_v2_canonical_queue_rows_keep_same_event_id_sources_isolated() -> None:
    queues = {
        "high_priority": [
            {
                "run_id": "run-1",
                "source_id": "source-a",
                "event_id": "shared",
                "event_instance_id": "instance-a",
            },
            {
                "run_id": "run-1",
                "source_id": "source-b",
                "event_id": "shared",
                "event_instance_id": "instance-b",
            },
        ]
    }
    attention_events = [
        {
            **queues["high_priority"][0],
            "sender": "a@example.com",
            "subject": "Source A",
        },
        {
            **queues["high_priority"][1],
            "sender": "b@example.com",
            "subject": "Source B",
        },
    ]

    rows = rop_dashboard_module._v2_canonical_queue_rows(
        queues,
        attention_events,
        lambda *_args: [dict(item) for item in queues["high_priority"]],
    )

    assert [(row["source_id"], row["sender"], row["subject"]) for row in rows] == [
        ("source-a", "a@example.com", "Source A"),
        ("source-b", "b@example.com", "Source B"),
    ]


def test_v2_overview_action_required_count_is_exact_while_preview_is_bounded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = [
        {
            "run_id": "run-1",
            "source_id": "source-a",
            "event_id": f"event-{number}",
            "event_instance_id": f"instance-{number}",
        }
        for number in range(30)
    ]
    source_data = {
        "business_kpi": {},
        "series": {},
        "queues": {"high_priority": rows, "needs_review": [dict(rows[0])]},
        "attention_events": rows,
        "filter_options": {},
        "thread_summary": {},
        "threads": [],
        "ai_assist_summary": {},
        "ai_assist_events": [],
        "source_health": [],
        "attachment_summary": {},
        "evidence_links": [],
        "delivery_recommendations": {},
        "bitrix": {},
    }
    entry_path = rop_dashboard_module.rop_web_projection_entry_path(tmp_path, "run-1")
    entry_path.parent.mkdir(parents=True)
    entry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": "run-1",
                "dashboards": {"all": {}},
            }
        ),
        encoding="utf-8",
    )

    def source_model(*_args: object, **_kwargs: object) -> dict[str, object]:
        return dict(source_data)

    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.read_model._build_rop_tab_read_model_legacy",
        source_model,
    )
    monkeypatch.setattr(
        "beeagent_module.interfaces.ui.read_model._canonical_queue_rows",
        lambda *_args: [dict(item) for item in rows],
    )

    views = rop_dashboard_module.build_rop_web_projection_v2_views(
        tmp_path, "run-1", ["all"], TEST_PLAN_LEAD
    )

    overview = views["overview.all"]
    assert overview["action_required_count"] == 30


def test_v2_reader_accepts_missing_leaderboard_but_writer_requires_it() -> None:
    overview = {
        "business_kpi": {},
        "series": {},
        "action_required_count": 0,
    }
    api = {
        "business_kpi": {},
        "series": {},
        "queues": {},
        "canonical_queue_rows": [],
    }
    assert rop_dashboard_module._v2_view_payload_valid("overview.7d", overview)
    assert rop_dashboard_module._v2_view_payload_valid("api.7d", api)
    assert not rop_dashboard_module._v2_view_payload_valid(
        "overview.7d", overview, require_current_additions=True
    )
    assert not rop_dashboard_module._v2_view_payload_valid(
        "api.7d", api, require_current_additions=True
    )
    leaderboard = {"month": "2026-09", "items": []}
    overview["team_leaderboard"] = leaderboard
    api["team_leaderboard"] = leaderboard
    assert rop_dashboard_module._v2_view_payload_valid("overview.7d", overview)
    assert rop_dashboard_module._v2_view_payload_valid("api.7d", api)
    assert not rop_dashboard_module._v2_view_payload_valid(
        "overview.7d", overview, require_current_additions=True
    )
    assert not rop_dashboard_module._v2_view_payload_valid(
        "api.7d", api, require_current_additions=True
    )
    leaderboard["monthly_lead_plan"] = TEST_PLAN_LEAD
    assert rop_dashboard_module._v2_view_payload_valid("overview.7d", overview)
    assert rop_dashboard_module._v2_view_payload_valid("api.7d", api)
    leaderboard.pop("monthly_lead_plan")
    leaderboard["plan_lead"] = TEST_PLAN_LEAD
    assert rop_dashboard_module._v2_view_payload_valid(
        "overview.7d", overview, require_current_additions=True
    )
    assert rop_dashboard_module._v2_view_payload_valid(
        "api.7d", api, require_current_additions=True
    )


def test_v2_writer_rejects_malformed_current_leaderboard_before_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    interfaces = tmp_path / "interfaces"
    interfaces.mkdir()
    manifest_path = interfaces / "rop_web_projection_v2.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "generated_at_utc": "2026-01-01T00:00:00Z",
                "generation": "g_existing",
                "latest_run_id": "run-1",
                "run_ids": ["run-1"],
                "total_runs": 1,
                "runs": {
                    "run-1": {
                        "generation": "g_existing",
                        "revision": "r_existing",
                        "view_keys": ["api.7d"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    before = manifest_path.read_bytes()

    def malformed_views(
        storage_dir: Path, run_id: str, periods: list[str], plan_lead: int
    ) -> dict[str, dict[str, object]]:
        views = _v2_views(storage_dir, run_id, periods, plan_lead)
        for view_key, payload in views.items():
            if view_key.startswith(("overview.", "api.")):
                payload.pop("team_leaderboard", None)
        return views

    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", malformed_views
    )

    with pytest.raises(ValueError, match="view payload is malformed"):
        rop_dashboard_module.write_rop_web_projection_v2(
            tmp_path,
            ["run-1"],
            1,
            {"run-1": ["7d"]},
            _null_logger(),
            plan_lead=TEST_PLAN_LEAD,
        )

    assert manifest_path.read_bytes() == before


def _projection_for_runs(run_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "run_ids": run_ids,
        "total_runs": len(run_ids),
        "dashboards": {run_id: {"7d": {"status": "ok"}} for run_id in run_ids},
    }


def _v2_views(
    _storage_dir: Path, _run_id: str, periods: list[str], _plan_lead: int
) -> dict[str, dict[str, object]]:
    payloads: dict[str, dict[str, object]] = {}
    for view_key in rop_dashboard_module._v2_required_view_keys(periods):
        if view_key.startswith("overview."):
            payloads[view_key] = {
                "business_kpi": {},
                "series": {},
                "team_leaderboard": {
                    "month": "2026-09",
                    "plan_lead": TEST_PLAN_LEAD,
                    "items": [],
                },
                "action_required_count": 0,
            }
        elif view_key.startswith("api."):
            payloads[view_key] = {
                "business_kpi": {},
                "series": {},
                "queues": {},
                "canonical_queue_rows": [],
                "team_leaderboard": {
                    "month": "2026-09",
                    "plan_lead": TEST_PLAN_LEAD,
                    "items": [],
                },
            }
        elif view_key == "queue":
            payloads[view_key] = {"queue_rows": [], "filter_options": {}}
        elif view_key == "sources":
            payloads[view_key] = {"source_health": []}
        else:
            payloads[view_key] = {"delivery_recommendations": {}}
    return payloads


def test_v1_projection_gc_keeps_current_and_previous_entries_and_bounds_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "write_rop_web_projection_v2", lambda **_: None
    )
    storage_dir = tmp_path / "storage"
    projection_dir = storage_dir / "interfaces" / "rop_web_projection"
    projection_dir.mkdir(parents=True)
    stale = rop_dashboard_module.rop_web_projection_entry_path(storage_dir, "stale")
    stale.write_text("{}", encoding="utf-8")
    unknown = projection_dir / "operator-note.txt"
    unknown.write_text("keep", encoding="utf-8")
    temporary = projection_dir / "unrelated.json.tmp"
    temporary.write_text("keep", encoding="utf-8")
    target = tmp_path / "symlink-target.json"
    target.write_text("keep", encoding="utf-8")
    symlink = rop_dashboard_module.rop_web_projection_entry_path(storage_dir, "link")
    symlink.symlink_to(target)
    run_artifact = storage_dir / "runs" / "run-1" / "canonical.json"
    attachment = storage_dir / "attachments" / "run-1" / "attachment.bin"
    unrelated = storage_dir / "interfaces" / "other.json"
    for path in (run_artifact, attachment, unrelated):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep", encoding="utf-8")

    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["a", "b"]), _null_logger()
    )
    assert not stale.exists()
    assert symlink.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep"
    assert unknown.exists()
    assert temporary.exists()
    assert all(path.exists() for path in (run_artifact, attachment, unrelated))

    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["c", "b"]), _null_logger()
    )
    assert all(
        rop_dashboard_module.rop_web_projection_entry_path(storage_dir, run_id).exists()
        for run_id in ("a", "b", "c")
    )
    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["d", "c"]), _null_logger()
    )
    assert not rop_dashboard_module.rop_web_projection_entry_path(
        storage_dir, "a"
    ).exists()
    assert all(
        rop_dashboard_module.rop_web_projection_entry_path(storage_dir, run_id).exists()
        for run_id in ("b", "c", "d")
    )

    for number in range(30):
        rop_dashboard_module.write_rop_web_projection(
            storage_dir,
            _projection_for_runs([f"run-{number}", f"run-{number + 1}"]),
            _null_logger(),
        )
    controlled_entries = [
        path
        for path in projection_dir.iterdir()
        if path.is_file()
        and rop_dashboard_module._ROP_WEB_PROJECTION_ENTRY_RE.fullmatch(path.name)
    ]
    assert len(controlled_entries) <= 4


def test_v1_projection_gc_failure_preserves_published_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "write_rop_web_projection_v2", lambda **_: None
    )
    storage_dir = tmp_path / "storage"
    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["old"]), _null_logger()
    )
    stale = rop_dashboard_module.rop_web_projection_entry_path(storage_dir, "stale")
    stale.write_text("{}", encoding="utf-8")
    original_unlink = Path.unlink

    def failing_unlink(path: Path, missing_ok: bool = False) -> None:
        if path == stale:
            raise OSError("simulated cleanup failure")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    rop_dashboard_module.write_rop_web_projection(
        storage_dir, _projection_for_runs(["new"]), _null_logger()
    )

    index = rop_dashboard_module.rop_web_projection_index(storage_dir)
    assert index is not None
    assert index["run_ids"] == ["new"]
    assert stale.exists()


def test_v2_projection_gc_keeps_current_previous_and_safe_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", _v2_views
    )
    storage_dir = tmp_path / "storage"
    logger = _null_logger()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir, ["run-a"], 1, {"run-a": ["7d"]}, logger, plan_lead=TEST_PLAN_LEAD
    )
    first = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert first is not None
    first_generation = first["runs"]["run-a"]["generation"]
    root = storage_dir / "interfaces" / "rop_web_projection_v2"
    stale = root / ("g_" + "0" * 32)
    stale.mkdir()
    invalid = root / "not-a-generation"
    invalid.mkdir()
    target = tmp_path / "symlink-generation-target"
    target.mkdir()
    symlink = root / ("g_" + "f" * 32)
    symlink.symlink_to(target, target_is_directory=True)

    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir,
        ["run-b", "run-a"],
        2,
        {"run-b": ["7d"]},
        logger,
        plan_lead=TEST_PLAN_LEAD,
    )
    second = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert second is not None
    second_generation = second["runs"]["run-b"]["generation"]
    assert not stale.exists()
    assert invalid.is_dir()
    assert symlink.is_symlink()
    assert target.is_dir()
    assert {entry["generation"] for entry in second["runs"].values()} == {
        first_generation,
        second_generation,
    }

    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir,
        ["run-c", "run-b"],
        3,
        {"run-c": ["7d"]},
        logger,
        plan_lead=TEST_PLAN_LEAD,
    )
    third = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert third is not None
    assert (root / first_generation).is_dir()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir,
        ["run-d", "run-c"],
        4,
        {"run-d": ["7d"]},
        logger,
        plan_lead=TEST_PLAN_LEAD,
    )
    fourth = rop_dashboard_module.rop_web_projection_v2_manifest(storage_dir)
    assert fourth is not None
    assert not (root / first_generation).exists()
    for run_id in fourth["run_ids"]:
        assert (
            rop_dashboard_module.read_rop_web_projection_v2_view(
                storage_dir, fourth, run_id, "api", "7d"
            )
            is not None
        )

    for number in range(20):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir,
            ["run-d"],
            4,
            {"run-d": ["7d"]},
            logger,
            plan_lead=TEST_PLAN_LEAD,
        )
    generations = [
        path
        for path in root.iterdir()
        if not path.is_symlink()
        and path.is_dir()
        and rop_dashboard_module._projection_revision(path.name) is not None
    ]
    assert len(generations) <= 2


def test_v2_interrupted_publication_cleans_only_own_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", _v2_views
    )
    storage_dir = tmp_path / "storage"
    logger = _null_logger()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir, ["run-a"], 1, {"run-a": ["7d"]}, logger, plan_lead=TEST_PLAN_LEAD
    )
    manifest_path = storage_dir / "interfaces" / "rop_web_projection_v2.json"
    before = manifest_path.read_bytes()
    root = storage_dir / "interfaces" / "rop_web_projection_v2"
    previous_generations = {path.name for path in root.iterdir() if path.is_dir()}
    original_write_text = Path.write_text

    def interrupted_write(
        path: Path,
        data: str,
        encoding: str | None = None,
    ) -> int:
        if path.parents[2].name.startswith(".g_"):
            raise OSError("simulated interrupted generation write")
        return original_write_text(path, data, encoding=encoding)

    monkeypatch.setattr(Path, "write_text", interrupted_write)
    with pytest.raises(OSError, match="interrupted"):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir,
            ["run-b"],
            2,
            {"run-b": ["7d"]},
            logger,
            plan_lead=TEST_PLAN_LEAD,
        )
    assert manifest_path.read_bytes() == before
    assert {
        path.name for path in root.iterdir() if path.is_dir()
    } == previous_generations
    assert not any(path.name.startswith(".g_") for path in root.iterdir())


def test_v2_manifest_failure_cleans_unpublished_final_without_masking_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        rop_dashboard_module, "build_rop_web_projection_v2_views", _v2_views
    )
    storage_dir = tmp_path / "storage"
    logger = _null_logger()
    rop_dashboard_module.write_rop_web_projection_v2(
        storage_dir, ["run-a"], 1, {"run-a": ["7d"]}, logger, plan_lead=TEST_PLAN_LEAD
    )
    manifest_path = storage_dir / "interfaces" / "rop_web_projection_v2.json"
    before = manifest_path.read_bytes()
    root = storage_dir / "interfaces" / "rop_web_projection_v2"
    existing = {path.name for path in root.iterdir() if path.is_dir()}
    original_replace = rop_dashboard_module.os.replace
    original_rmtree = rop_dashboard_module.shutil.rmtree

    def failing_manifest_replace(source: Path, target: Path) -> None:
        if source.name == "rop_web_projection_v2.json.tmp":
            raise OSError("simulated manifest replacement failure")
        original_replace(source, target)

    monkeypatch.setattr(rop_dashboard_module.os, "replace", failing_manifest_replace)
    with pytest.raises(OSError, match="manifest replacement"):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir,
            ["run-b"],
            2,
            {"run-b": ["7d"]},
            logger,
            plan_lead=TEST_PLAN_LEAD,
        )
    assert manifest_path.read_bytes() == before
    assert {path.name for path in root.iterdir() if path.is_dir()} == existing

    def failing_rmtree(path: Path) -> None:
        if path.name not in existing:
            raise OSError("simulated cleanup failure")
        original_rmtree(path)

    monkeypatch.setattr(rop_dashboard_module.shutil, "rmtree", failing_rmtree)
    with pytest.raises(OSError, match="manifest replacement"):
        rop_dashboard_module.write_rop_web_projection_v2(
            storage_dir,
            ["run-c"],
            3,
            {"run-c": ["7d"]},
            logger,
            plan_lead=TEST_PLAN_LEAD,
        )
