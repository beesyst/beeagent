from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import pytest

from beeagent_module.cases.rop_current_state import (
    BITRIX_RECONCILIATION_FILENAME,
    CURRENT_STATE_FILENAME,
    build_rop_current_state,
    write_current_state,
)
from beeagent_module.core.cli import (
    RopCliError,
    create_rop_parser,
    handle_rop_current,
    handle_rop_reconcile_bitrix,
    handle_rop_run,
)


# null logger для тестов
def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_current_state")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Фикстура: настройки для тестов
def _settings() -> dict:
    return {
        "rop": {
            "dashboard": {
                "default_period": "7d",
                "periods": ["today", "yesterday", "7d", "30d", "365d", "all"],
            }
        }
    }


# Фикстура: создание минимального каталога запуска ROP с базовыми артефактами
@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    rdir = tmp_path / "runs" / "smoke-it27-current"
    rdir.mkdir(parents=True, exist_ok=True)

    normalized = [
        {
            "event_id": "evt-001",
            "source_id": "rop_batch_sample",
            "sender": "client@example.com",
            "subject": "Welding machine inquiry",
        },
        {
            "event_id": "evt-002",
            "source_id": "rop_batch_sample",
            "sender": "lead@example.com",
            "subject": "Need pricing",
        },
    ]
    (rdir / "normalized_events.json").write_text(
        json.dumps(normalized, indent=2), encoding="utf-8"
    )

    classified = [
        {
            "event_id": "evt-001",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "is_fallback": False,
            "reason_code": "new_contact",
        },
        {
            "event_id": "evt-002",
            "case_type": "existing_deal",
            "priority": "low",
            "confidence": 0.85,
            "is_fallback": False,
            "reason_code": "existing_match",
        },
    ]
    (rdir / "classified_events.json").write_text(
        json.dumps(classified, indent=2), encoding="utf-8"
    )

    source_diag = {
        "selection_mode": "single_explicit",
        "aggregate": {
            "source_count": 1,
            "loaded_source_count": 1,
            "degraded_source_count": 0,
        },
        "sources": [
            {
                "source_id": "rop_batch_sample",
                "client_id": "welding",
                "status": "ok",
            }
        ],
    }
    (rdir / "source_diagnostics.json").write_text(
        json.dumps(source_diag, indent=2), encoding="utf-8"
    )

    intake = {
        "selection_mode": "single_explicit",
        "source_count": 1,
        "loaded_source_count": 1,
        "degraded_source_count": 0,
        "loaded_item_count": 2,
        "sources": [
            {
                "source_id": "rop_batch_sample",
                "client_id": "welding",
                "status": "ok",
            }
        ],
    }
    (rdir / "intake_metadata.json").write_text(
        json.dumps(intake, indent=2), encoding="utf-8"
    )

    return rdir


# Добавление Bitrix reconciliation артефакта в каталог запуска
def _add_bitrix_reconciliation(
    run_dir: Path,
    items: list[dict],
    status: str = "ok",
    run_id: str | None = None,
) -> None:
    if run_id is None:
        run_id = run_dir.name

    artifact = {
        "run_id": run_id,
        "status": status,
        "read_only": True,
        "connector": {
            "system": "bitrix",
            "portal_url": "https://test.bitrix24.kz",
            "allowed_methods": ["crm.lead.list"],
        },
        "aggregate": {
            "event_count": len(items),
        },
        "items": items,
        "warnings": [],
    }

    agg = artifact["aggregate"]
    for item in items:
        ms = item.get("bitrix_match_status", "")
        if ms.startswith("matched_"):
            agg["matched_count"] = agg.get("matched_count", 0) + 1
        elif ms == "not_found":
            agg["not_found_count"] = agg.get("not_found_count", 0) + 1
        elif ms == "duplicate_candidate":
            agg["duplicate_candidate_count"] = (
                agg.get("duplicate_candidate_count", 0) + 1
            )
        elif ms == "ambiguous":
            agg["ambiguous_count"] = agg.get("ambiguous_count", 0) + 1
        elif ms in ("connector_degraded", "error"):
            agg["connector_error_count"] = agg.get("connector_error_count", 0) + 1

    (run_dir / BITRIX_RECONCILIATION_FILENAME).write_text(
        json.dumps(artifact, indent=2), encoding="utf-8"
    )


# Класс: тесты для build_rop_current_state и write_current_state
class TestBuildRopCurrentState:
    def test_normal_run_without_bitrix(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        state = build_rop_current_state(storage_dir, run_id, _null_logger())

        assert state["run_id"] == run_id
        assert state["status"] == "ok"
        assert state["read_only"] is True
        assert state["client_id"] == "welding"
        assert state["current_alias"] == "latest"
        assert state["source"]["selection_mode"] == "single_explicit"
        assert state["source"]["source_count"] == 1
        assert state["source"]["loaded_source_count"] == 1
        assert state["source"]["degraded_source_count"] == 0

        kpi = state["kpi"]
        assert kpi["events_total"] == 2
        assert kpi["normalized_count"] == 2
        assert kpi["classified_count"] == 2
        assert kpi["high_priority"] == 1
        assert kpi["needs_manual_review"] == 1
        assert kpi["matched_in_bitrix"] == 0
        assert kpi["lost_in_bitrix"] == 0
        assert kpi["unreconciled"] == 2

        queues = state["queues"]
        assert len(queues["unreconciled"]) == 2
        assert len(queues["matched"]) == 0
        assert len(queues["lost_in_bitrix"]) == 0
        assert len(queues["high_priority"]) == 1

        assert len(state["warnings"]) == 0

    def test_with_bitrix_matched(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "matched_lead",
                    "bitrix_entity_id": 1001,
                },
                {
                    "event_id": "evt-002",
                    "bitrix_match_status": "matched_deal",
                    "bitrix_entity_id": 2001,
                },
            ],
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        kpi = state["kpi"]
        assert kpi["matched_in_bitrix"] == 2
        assert kpi["lost_in_bitrix"] == 0
        assert kpi["unreconciled"] == 0

        queues = state["queues"]
        assert len(queues["matched"]) == 2
        assert len(queues["unreconciled"]) == 0

    def test_with_bitrix_not_found(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "not_found",
                },
                {
                    "event_id": "evt-002",
                    "bitrix_match_status": "not_found",
                },
            ],
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        kpi = state["kpi"]
        assert kpi["matched_in_bitrix"] == 0
        assert kpi["lost_in_bitrix"] == 2
        assert kpi["unreconciled"] == 0
        queues = state["queues"]
        assert len(queues["needs_review"]) >= 2

        queues = state["queues"]
        assert len(queues["lost_in_bitrix"]) == 2
        assert len(queues["matched"]) == 0

    def test_with_bitrix_ambiguous(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "ambiguous",
                },
            ],
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        kpi = state["kpi"]
        assert kpi["ambiguous_in_bitrix"] == 1
        assert kpi["lost_in_bitrix"] == 0

        queues = state["queues"]
        assert len(queues["ambiguous"]) == 1
        assert "ambiguous" in queues["ambiguous"][0].get("bitrix_status", "")

    def test_with_bitrix_duplicate_candidate(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "duplicate_candidate",
                },
            ],
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        kpi = state["kpi"]
        assert kpi["ambiguous_in_bitrix"] == 1

        queues = state["queues"]
        assert len(queues["ambiguous"]) == 1
        assert queues["ambiguous"][0]["bitrix_status"] == "duplicate_candidate"

    def test_with_bitrix_connector_degraded(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "connector_degraded",
                },
            ],
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        kpi = state["kpi"]
        assert kpi["lost_in_bitrix"] == 0
        assert kpi["connector_degraded"] == 1

        queues = state["queues"]
        assert len(queues["degraded"]) == 1

    def test_malformed_bitrix_artifact_warning(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        (run_dir / BITRIX_RECONCILIATION_FILENAME).write_text(
            "not valid json", encoding="utf-8"
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        warnings = state["warnings"]
        malformed = [w for w in warnings if w["code"] == "malformed_artifact"]
        assert len(malformed) >= 1
        assert BITRIX_RECONCILIATION_FILENAME in malformed[0]["artifact"]

    def test_stale_bitrix_artifact_warning(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "matched_lead",
                },
            ],
            status="degraded",
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        stale = [w for w in state["warnings"] if w["code"] == "stale_artifact"]
        assert len(stale) >= 1
        assert "degraded" in stale[0]["message"]

    def test_older_bitrix_artifact_warning(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "matched_lead",
                },
            ],
        )

        bitrix_path = run_dir / BITRIX_RECONCILIATION_FILENAME
        classified_path = run_dir / "classified_events.json"
        os.utime(bitrix_path, ns=(1_000_000_000, 1_000_000_000))
        os.utime(classified_path, ns=(2_000_000_000, 2_000_000_000))

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        stale = [w for w in state["warnings"] if w["code"] == "stale_artifact"]
        assert len(stale) >= 1
        assert "older than" in stale[0]["message"]

    def test_source_degraded_kpi(self, run_dir: Path, tmp_path: Path) -> None:
        source_diag_path = run_dir / "source_diagnostics.json"
        source_diag = json.loads(source_diag_path.read_text(encoding="utf-8"))
        source_diag["aggregate"]["degraded_source_count"] = 1
        source_diag_path.write_text(json.dumps(source_diag), encoding="utf-8")

        state = build_rop_current_state(tmp_path, run_dir.name, _null_logger())

        assert state["kpi"]["source_degraded"] == 1

    def test_run_id_mismatch_warning(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        _add_bitrix_reconciliation(
            run_dir,
            items=[
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "matched_lead",
                },
            ],
            run_id="different-run-id",
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        mismatch = [w for w in state["warnings"] if w["code"] == "run_id_mismatch"]
        assert len(mismatch) >= 1
        assert "different-run-id" in mismatch[0]["message"]

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="path traversal"):
            build_rop_current_state(tmp_path, "../../etc/passwd", _null_logger())


# Класс: тесты для write_current_state и CLI rop current
class TestWriteCurrentState:
    def test_writes_artifact_and_interfaces(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        write_current_state(storage_dir, run_id, state, _null_logger())

        assert (run_dir / CURRENT_STATE_FILENAME).exists()
        assert (storage_dir / "interfaces" / "rop_current.json").exists()
        assert (storage_dir / "interfaces" / "rop_latest.json").exists()
        assert (storage_dir / "interfaces" / "rop_index.json").exists()

    def test_rop_index_append(self, run_dir: Path, tmp_path: Path) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name
        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        write_current_state(storage_dir, run_id, state, _null_logger())

        run_dir2 = tmp_path / "runs" / "run-002"
        run_dir2.mkdir(parents=True)
        (run_dir2 / "normalized_events.json").write_text("[]", encoding="utf-8")
        (run_dir2 / "classified_events.json").write_text("[]", encoding="utf-8")
        state2 = build_rop_current_state(storage_dir, "run-002", _null_logger())
        write_current_state(storage_dir, "run-002", state2, _null_logger())

        index = json.loads(
            (storage_dir / "interfaces" / "rop_index.json").read_text(encoding="utf-8")
        )
        assert len(index) == 2
        run_ids = [e["run_id"] for e in index]
        assert run_id in run_ids
        assert "run-002" in run_ids

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="path traversal"):
            write_current_state(tmp_path, "../../etc/passwd", {}, _null_logger())


# Класс: тесты для CLI rop current
class TestCliRopCurrent:
    def test_cli_rop_current_parser(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["current", "--run-id", "test-run"])
        assert args.rop_command == "current"
        assert args.run_id == "test-run"

    def test_cli_rop_current_requires_run_id(self) -> None:
        parser = create_rop_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["current"])

    def test_cli_rop_current_prints_output(
        self, run_dir: Path, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id=run_dir.name)
        handle_rop_current(args, settings=_settings(), logger=_null_logger())

        output = capsys.readouterr().out
        assert "ROP current-state built" in output
        assert run_dir.name in output

    def test_cli_rop_current_missing_run_id_raises_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="nonexistent-run")
        with pytest.raises(RopCliError, match="ROP current-state build failed"):
            handle_rop_current(args, settings=_settings(), logger=_null_logger())

    def test_cli_rop_current_path_traversal_raises_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="../../etc/passwd")
        with pytest.raises(RopCliError, match="current-state build failed"):
            handle_rop_current(args, settings=_settings(), logger=_null_logger())


class TestCliCurrentStatePostHooks:
    def test_handle_rop_run_updates_current_state_post_hook(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import beeagent_module.core.cli as cli_module

        calls: dict[str, object] = {}
        settings = {
            "rop": {
                "sources": [
                    {
                        "source_id": "rop_batch_sample",
                        "enabled": True,
                    }
                ]
            }
        }

        def fake_run_rop_batch_case(**kwargs: object) -> dict[str, object]:
            calls["run_kwargs"] = kwargs
            return {
                "run_id": "post-hook-run",
                "status": "ok",
                "operator_text": "ok",
            }

        def fake_export_review_tsv_for_run(**kwargs: object) -> Path:
            calls["export_kwargs"] = kwargs
            return tmp_path / "review.tsv"

        def fake_build_rop_current_state(**kwargs: object) -> dict[str, object]:
            calls["build_kwargs"] = kwargs
            return {"run_id": "post-hook-run", "status": "ok"}

        def fake_write_current_state(**kwargs: object) -> None:
            calls["write_kwargs"] = kwargs

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)
        monkeypatch.setattr(
            cli_module,
            "run_rop_batch_case",
            fake_run_rop_batch_case,
        )
        monkeypatch.setattr(
            cli_module,
            "_export_review_tsv_for_run",
            fake_export_review_tsv_for_run,
        )
        monkeypatch.setattr(
            cli_module,
            "build_rop_current_state",
            fake_build_rop_current_state,
        )
        monkeypatch.setattr(
            cli_module,
            "write_current_state",
            fake_write_current_state,
        )

        args = argparse.Namespace(
            source_id="rop_batch_sample",
            all_sources=False,
            items_max=2,
            period=None,
            run_id="post-hook-run",
        )
        handle_rop_run(args, settings=settings, logger=_null_logger())

        build_kwargs = calls["build_kwargs"]
        write_kwargs = calls["write_kwargs"]
        assert isinstance(build_kwargs, dict)
        assert isinstance(write_kwargs, dict)
        assert build_kwargs["run_id"] == "post-hook-run"
        assert write_kwargs["run_id"] == "post-hook-run"

    def test_handle_rop_reconcile_bitrix_updates_current_state_post_hook(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import beeagent_module.cases.rop_bitrix_reconciliation as br_module
        import beeagent_module.core.cli as cli_module

        calls: dict[str, object] = {}

        def fake_run_reconciliation(**kwargs: object) -> dict[str, object]:
            calls["reconcile_kwargs"] = kwargs
            return {
                "status": "ok",
                "aggregate": {"event_count": 1, "matched_count": 1},
            }

        def fake_build_rop_current_state(**kwargs: object) -> dict[str, object]:
            calls["build_kwargs"] = kwargs
            return {"run_id": "reconcile-hook-run", "status": "ok"}

        def fake_write_current_state(**kwargs: object) -> None:
            calls["write_kwargs"] = kwargs

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(br_module, "run_reconciliation", fake_run_reconciliation)
        monkeypatch.setattr(
            cli_module,
            "build_rop_current_state",
            fake_build_rop_current_state,
        )
        monkeypatch.setattr(
            cli_module,
            "write_current_state",
            fake_write_current_state,
        )

        args = argparse.Namespace(run_id="reconcile-hook-run")
        handle_rop_reconcile_bitrix(args, settings={}, logger=_null_logger())

        build_kwargs = calls["build_kwargs"]
        write_kwargs = calls["write_kwargs"]
        assert isinstance(build_kwargs, dict)
        assert isinstance(write_kwargs, dict)
        assert build_kwargs["run_id"] == "reconcile-hook-run"
        assert write_kwargs["run_id"] == "reconcile-hook-run"

    def test_failed_reconcile_bitrix_does_not_write_current_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import beeagent_module.cases.rop_bitrix_reconciliation as br_module
        import beeagent_module.core.cli as cli_module

        calls: dict[str, bool] = {"build": False, "write": False}

        def fake_run_reconciliation(**kwargs: object) -> dict[str, object]:
            raise RuntimeError("connector failed")

        def fake_build_rop_current_state(**kwargs: object) -> dict[str, object]:
            calls["build"] = True
            return {}

        def fake_write_current_state(**kwargs: object) -> None:
            calls["write"] = True

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(br_module, "run_reconciliation", fake_run_reconciliation)
        monkeypatch.setattr(
            cli_module,
            "build_rop_current_state",
            fake_build_rop_current_state,
        )
        monkeypatch.setattr(
            cli_module,
            "write_current_state",
            fake_write_current_state,
        )

        args = argparse.Namespace(run_id="failed-reconcile-run")
        with pytest.raises(RopCliError, match="Bitrix reconciliation failed"):
            handle_rop_reconcile_bitrix(args, settings={}, logger=_null_logger())

        assert calls == {"build": False, "write": False}


# Класс: тесты для проверки, что артефакт current-state не раскрывает raw content или секреты
class TestCurrentStateSecrets:
    def test_no_raw_content_in_current_state(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name

        normalized_path = run_dir / "normalized_events.json"
        events = json.loads(normalized_path.read_text(encoding="utf-8"))
        events.append(
            {
                "event_id": "evt-secret",
                "raw_eml": "Secret email content",
                "attachment_content": "base64encodeddata",
                "password": "super-secret",
            }
        )
        normalized_path.write_text(json.dumps(events, indent=2), encoding="utf-8")

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        state_json = json.dumps(state, indent=2)

        assert "raw_eml" not in state_json
        assert "attachment_content" not in state_json
        assert "super-secret" not in state_json

    def test_no_bitrix_secrets_in_current_state(
        self, run_dir: Path, tmp_path: Path
    ) -> None:
        storage_dir = tmp_path
        run_id = run_dir.name

        artifact = {
            "run_id": run_id,
            "status": "ok",
            "connector": {
                "portal_url": "https://test.bitrix24.kz",
                "auth_source": "env:BITRIX_WEBHOOK_URL",
            },
            "aggregate": {"event_count": 0},
            "items": [],
            "warnings": [],
        }
        (run_dir / BITRIX_RECONCILIATION_FILENAME).write_text(
            json.dumps(artifact, indent=2), encoding="utf-8"
        )

        state = build_rop_current_state(storage_dir, run_id, _null_logger())
        state_json = json.dumps(state, indent=2)

        assert "testtoken123" not in state_json
