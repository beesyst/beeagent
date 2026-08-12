from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path

import pytest

from beeagent_module.core.cli import (
    RopCliError,
    _apply_source_overrides,
    _validate_mailbox_env_for_sources,
    create_rop_parser,
    handle_rop_dashboard,
    handle_rop_evaluate_review,
    handle_rop_export_review,
    handle_rop_mvp_pack,
    handle_rop_run,
    handle_rop_summary,
)
from beeagent_module.core.rop_review_export import review_tsv_columns
from beeagent_module.core.settings import load_settings

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")
os.environ.setdefault("BEEAGENT_WEB_OPERATOR_TOKEN", "test-operator-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_cli_rop")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


class TestRopCliArgumentParser:
    def test_create_parser_returns_parser(self) -> None:
        parser = create_rop_parser()
        assert parser is not None
        assert parser.prog == "start.py rop"

    def test_rop_run_parser_accepts_valid_args(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(
            [
                "run",
                "--source-id",
                "rop_batch_sample",
                "--items-max",
                "10",
                "--period",
                "2026-05",
                "--run-id",
                "test-run-123",
            ]
        )
        assert args.rop_command == "run"
        assert args.source_id == "rop_batch_sample"
        assert args.all_sources is False
        assert args.items_max == 10
        assert args.period == "2026-05"
        assert args.run_id == "test-run-123"

    def test_rop_run_parser_allows_missing_optional_args(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["run"])
        assert args.rop_command == "run"
        assert args.source_id is None
        assert args.all_sources is False
        assert args.items_max is None
        assert args.period is None
        assert args.run_id is None

    def test_rop_run_parser_accepts_all_sources_flag(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["run", "--all-sources"])
        assert args.rop_command == "run"
        assert args.source_id is None
        assert args.all_sources is True

    def test_rop_poll_parser_defaults_rebaseline_false(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["poll"])
        assert args.rop_command == "poll"
        assert args.rebaseline is False

    def test_rop_poll_parser_accepts_rebaseline_flag(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["poll", "--rebaseline"])
        assert args.rop_command == "poll"
        assert args.rebaseline is True

    def test_rop_summary_parser_requires_run_id(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["summary", "--run-id", "test-run-123"])
        assert args.rop_command == "summary"
        assert args.run_id == "test-run-123"

    def test_rop_export_review_parser_requires_run_id(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["export-review", "--run-id", "test-run-123"])
        assert args.rop_command == "export-review"
        assert args.run_id == "test-run-123"

    def test_rop_export_review_parser_accepts_format(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(
            ["export-review", "--run-id", "test-run-123", "--format", "tsv"]
        )
        assert args.format == "tsv"

    def test_rop_dashboard_period_defaults_to_config_at_handler(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["dashboard", "--run-id", "test-run-123"])
        assert args.rop_command == "dashboard"
        assert args.period is None
        assert args.run_id == "test-run-123"

    def test_rop_dashboard_rejects_period_not_configured(self) -> None:
        import argparse

        settings = load_settings(_project_root() / "config" / "settings.yml")
        args = argparse.Namespace(period="14d", run_id="test-run-123")

        with pytest.raises(RopCliError, match="Invalid period"):
            handle_rop_dashboard(args, settings=settings, logger=_null_logger())

    def test_rop_mvp_pack_rejects_period_not_configured(self) -> None:
        import argparse

        settings = load_settings(_project_root() / "config" / "settings.yml")
        args = argparse.Namespace(period="14d", run_id="test-run-123")

        with pytest.raises(RopCliError, match="Invalid period"):
            handle_rop_mvp_pack(args, settings=settings, logger=_null_logger())

    def test_cli_load_settings_honors_adjudicator_env_kill_switch(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "disabled")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        settings = load_settings(_project_root() / "config" / "settings.yml")

        assert settings["rop"]["ai_assist"]["enabled"] is True
        assert settings["rop"]["ai_assist"]["adjudicator"]["enabled"] is False


class TestSourceOverrides:
    def test_apply_source_overrides_with_source_id(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")

        for source in settings["rop"]["sources"]:
            if source["source_id"] == "rop_batch_sample":
                source["enabled"] = True

        effective = _apply_source_overrides(
            settings=settings,
            source_id="rop_batch_sample",
            all_sources=False,
            items_max=5,
            logger=_null_logger(),
        )

        sources = effective["rop"]["sources"]
        batch_source = next(
            (s for s in sources if s["source_id"] == "rop_batch_sample"), None
        )

        assert batch_source is not None
        assert batch_source["enabled"] is True
        assert batch_source["items_max"] == 5

        for source in sources:
            if source["source_id"] != "rop_batch_sample":
                assert source["enabled"] is False

    def test_apply_source_overrides_nonexistent_source_raises_error(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")

        with pytest.raises(RopCliError) as exc_info:
            _apply_source_overrides(
                settings=settings,
                source_id="nonexistent_source",
                all_sources=False,
                items_max=None,
                logger=_null_logger(),
            )
        assert "Source not found" in str(exc_info.value)

    def test_apply_source_overrides_empty_sources_raises_error(self) -> None:
        settings = {"rop": {"sources": []}}

        with pytest.raises(RopCliError) as exc_info:
            _apply_source_overrides(
                settings=settings,
                source_id=None,
                all_sources=False,
                items_max=None,
                logger=_null_logger(),
            )
        assert "rop.sources is not configured" in str(exc_info.value)

    def test_apply_source_overrides_all_sources_requires_enabled(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")
        for source in settings["rop"]["sources"]:
            source["enabled"] = False

        with pytest.raises(RopCliError) as exc_info:
            _apply_source_overrides(
                settings=settings,
                source_id=None,
                all_sources=True,
                items_max=3,
                logger=_null_logger(),
            )
        assert "No enabled sources found" in str(exc_info.value)


class TestRopCliRun:
    def test_rop_run_with_batch_source(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = load_settings(_project_root() / "config" / "settings.yml")
        monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "false")

        batch_data = {
            "period": "2026-05",
            "items": [
                {
                    "event_id": "evt-001",
                    "case_type": "new_lead",
                    "priority": "high",
                    "confidence": 0.95,
                    "is_fallback": False,
                    "reason_code": "new_contact",
                }
            ],
        }

        batch_file = tmp_path / "test_batch.json"
        batch_file.write_text(json.dumps(batch_data), encoding="utf-8")

        settings["rop"]["sources"][0]["batch"]["path"] = str(batch_file)
        settings["rop"]["sources"][0]["enabled"] = True

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)

        args = argparse.Namespace(
            source_id="rop_batch_sample",
            all_sources=False,
            items_max=2,
            period="2026-05",
            run_id="test-cli-run-batch",
        )

        logger = _null_logger()

        try:
            handle_rop_run(args, settings=settings, logger=logger)
        except Exception as exc:
            assert (
                "run_id" in str(exc)
                or "module" in str(exc).lower()
                or "beeagent-rop" in str(exc)
            )

        run_dir = tmp_path / "runs" / "test-cli-run-batch"
        assert run_dir.is_dir()
        project_run_dir = (
            Path(__file__).resolve().parents[1]
            / "storage"
            / "runs"
            / "test-cli-run-batch"
        )
        assert not project_run_dir.exists()

    def test_rop_run_exports_review_tsv_by_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = load_settings(_project_root() / "config" / "settings.yml")
        monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "false")

        for source in settings["rop"]["sources"]:
            if source["source_id"] == "rop_batch_sample":
                source["enabled"] = True
                source["batch"]["path"] = str(tmp_path / "test_batch.json")

        batch_data = {
            "items": [
                {
                    "event_id": "evt-001",
                    "source": "email",
                    "sender": "lead@example.com",
                    "subject": "Need product details",
                    "body": "Please share pricing and delivery terms.",
                }
            ]
        }
        (tmp_path / "test_batch.json").write_text(
            json.dumps(batch_data),
            encoding="utf-8",
        )

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)

        args = argparse.Namespace(
            source_id="rop_batch_sample",
            all_sources=False,
            items_max=1,
            period="2026-05",
            run_id="test-cli-run-review-tsv",
        )

        handle_rop_run(args, settings=settings, logger=_null_logger())

        run_dir = tmp_path / "runs" / "test-cli-run-review-tsv"
        tsv_path = run_dir / "rop_review_table.tsv"
        classified_path = run_dir / "classified_events.json"

        assert tsv_path.exists()

        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        assert reader.fieldnames == review_tsv_columns()
        assert len(rows) == 1

        classified_events = json.loads(classified_path.read_text(encoding="utf-8"))
        assert len(classified_events) == 1

        row = rows[0]
        classified = classified_events[0]

        assert row["event_id"] == classified["event_id"]
        assert row["bot_case_type"] == classified["case_type"]
        assert row["bot_reason_code"] == classified["reason_code"]
        assert row["bot_confidence"] == str(classified["confidence"])
        assert row["bot_is_fallback"] == str(classified["is_fallback"]).lower()

        output = capsys.readouterr().out
        assert "Review TSV exported:" in output
        assert "Paste this TSV into Google Sheets for human review." in output
        assert tsv_path.as_posix() in output

    def test_rop_run_all_sources_partial_degradation_keeps_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = load_settings(_project_root() / "config" / "settings.yml")
        monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "false")

        good_batch_path = tmp_path / "good_batch.json"
        good_batch_path.write_text(
            json.dumps(
                {
                    "period": "2026-05",
                    "items": [
                        {
                            "event_id": "evt-good-001",
                            "sender": "good@example.com",
                            "subject": "Good source event",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        settings["rop"]["sources"] = [
            {
                "source_id": "good_source",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Good Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 10,
                "batch": {
                    "path": str(good_batch_path),
                    "period": "2026-05",
                },
            },
            {
                "source_id": "broken_source",
                "source_type": "json_batch",
                "source_role": "batch_sample",
                "client_id": "welding",
                "display_name": "Broken Source",
                "enabled": True,
                "authority": "read_only",
                "items_max": 10,
                "batch": {
                    "path": "storage/mock/missing.json",
                    "period": "2026-05",
                },
            },
        ]

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)

        args = argparse.Namespace(
            source_id=None,
            all_sources=True,
            items_max=5,
            period="2026-05",
            run_id="test-cli-run-all-sources",
        )

        handle_rop_run(args, settings=settings, logger=_null_logger())

        run_dir = tmp_path / "runs" / "test-cli-run-all-sources"
        source_diag = json.loads(
            (run_dir / "source_diagnostics.json").read_text(encoding="utf-8")
        )
        intake_meta = json.loads(
            (run_dir / "intake_metadata.json").read_text(encoding="utf-8")
        )

        assert source_diag["selection_mode"] == "all_enabled"
        assert source_diag["aggregate"]["source_count"] == 2
        assert source_diag["aggregate"]["loaded_source_count"] == 1
        assert source_diag["aggregate"]["degraded_source_count"] == 1
        assert source_diag["reason"] == "partial_degradation"
        assert len(source_diag["sources"]) == 2

        assert intake_meta["selection_mode"] == "all_enabled"
        assert intake_meta["source_count"] == 2
        assert intake_meta["loaded_source_count"] == 1
        assert intake_meta["degraded_source_count"] == 1

    def test_rop_run_degraded_without_normalized_raises_primary_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = load_settings(_project_root() / "config" / "settings.yml")
        monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "false")
        for source in settings["rop"]["sources"]:
            if source["source_id"] == "rop_batch_sample":
                source["enabled"] = True

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)
        monkeypatch.setattr(
            cli_module,
            "run_rop_batch_case",
            lambda **kwargs: {
                "run_id": "test-cli-run-degraded",
                "status": "degraded",
                "module_status": "error",
                "summary": "source loading degraded",
                "source": {"reason": "source_not_loaded"},
                "operator_text": "ROP operator run v0",
            },
        )

        args = argparse.Namespace(
            source_id="rop_batch_sample",
            all_sources=False,
            items_max=1,
            period="2026-05",
            run_id="test-cli-run-degraded",
        )

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_run(args, settings=settings, logger=_null_logger())

        msg = str(exc_info.value)
        assert "status=degraded" in msg
        assert "module_status=error" in msg
        assert "source_not_loaded" in msg
        assert "normalized_events.json not found" not in msg

    def test_rop_run_missing_source_id_raises_error(self, tmp_path: Path) -> None:
        import argparse

        settings = load_settings(_project_root() / "config" / "settings.yml")

        args = argparse.Namespace(
            source_id="nonexistent_source",
            all_sources=False,
            items_max=None,
            period=None,
            run_id="test-cli-run-missing",
        )

        logger = _null_logger()

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_run(args, settings=settings, logger=logger)
        assert "Source not found" in str(exc_info.value)


class TestRopCliSummary:
    def test_rop_summary_with_existing_summary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        run_dir = tmp_path / "runs" / "test-summary-run"
        run_dir.mkdir(parents=True)

        summary_data = {
            "run_id": "test-summary-run",
            "module_id": "beeagent-rop",
            "case_type": "rop_summary",
            "status": "ok",
            "module_status": "ok",
            "summary": "ROP summary test",
            "source": {
                "source_id": "rop_batch_sample",
                "source_type": "json_batch",
                "loaded_item_count": 2,
                "period": "2026-05",
            },
            "classification": {
                "normalized_count": 2,
                "classified_count": 2,
                "classification_failed_count": 0,
            },
            "artifact_refs": ["runs/test-summary-run/operator_summary.json"],
        }

        summary_path = run_dir / "operator_summary.json"
        summary_path.write_text(json.dumps(summary_data), encoding="utf-8")

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-summary-run")
        logger = _null_logger()

        handle_rop_summary(args, logger=logger)

    def test_rop_summary_missing_artifact_raises_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="nonexistent-run")
        logger = _null_logger()

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_summary(args, logger=logger)
        assert "operator_summary.json not found" in str(exc_info.value)


class TestRopCliExportReview:
    def test_rop_export_review_generates_tsv(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        run_dir = tmp_path / "runs" / "test-export-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "rop_batch_sample",
                "sender": "test@example.com",
                "subject": "Test email",
                "body_preview": "Test body",
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "rop_batch_sample",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"

        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-export-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        assert tsv_path.exists()

        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        assert row["event_id"] == "evt-001"
        assert row["sender"] == "test@example.com"
        assert row["bot_case_type"] == "new_lead"

        header = tsv_path.read_text(encoding="utf-8").splitlines()[0]
        assert "\t" in header
        assert "," not in header
        assert header.split("\t") == review_tsv_columns()

        expected_cols = review_tsv_columns()
        assert set(row.keys()) == set(expected_cols)

    def test_apply_source_overrides_disabled_source_raises_error(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")

        for source in settings["rop"]["sources"]:
            if source["source_id"] == "rop_batch_sample":
                source["enabled"] = False

        with pytest.raises(RopCliError) as exc_info:
            _apply_source_overrides(
                settings=settings,
                source_id="rop_batch_sample",
                all_sources=False,
                items_max=5,
                logger=_null_logger(),
            )

        assert "Source is disabled" in str(exc_info.value)

    def test_rop_export_review_missing_normalized_raises_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="nonexistent-run", format="tsv")
        logger = _null_logger()

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_export_review(args, logger=logger)
        assert "normalized_events.json not found" in str(exc_info.value)

    def test_rop_export_review_unsupported_format_raises_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        run_dir = tmp_path / "runs" / "test-export-run"
        run_dir.mkdir(parents=True)

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps([]))
        classified_path.write_text(json.dumps([]))

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-export-run", format="json")
        logger = _null_logger()

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_export_review(args, logger=logger)
        assert "Unsupported format" in str(exc_info.value)

    def test_rop_run_period_override_applies_to_operator_summary(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = load_settings(_project_root() / "config" / "settings.yml")
        monkeypatch.setenv("BEEAGENT_ROP_AI_ADJUDICATOR_ENABLED", "false")

        for source in settings["rop"]["sources"]:
            if source["source_id"] == "rop_batch_sample":
                source["enabled"] = True
                source["batch"]["path"] = str(tmp_path / "test_batch.json")

        batch_data = {
            "items": [
                {
                    "event_id": "evt-001",
                    "case_type": "new_lead",
                    "priority": "high",
                    "confidence": 0.95,
                }
            ]
        }
        (tmp_path / "test_batch.json").write_text(
            json.dumps(batch_data),
            encoding="utf-8",
        )

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)

        args = argparse.Namespace(
            source_id="rop_batch_sample",
            all_sources=False,
            items_max=1,
            period="2026-05",
            run_id="test-period-override",
        )

        handle_rop_run(args, settings=settings, logger=_null_logger())

        operator_summary_path = (
            tmp_path / "runs" / "test-period-override" / "operator_summary.json"
        )
        assert operator_summary_path.exists()

        data = json.loads(operator_summary_path.read_text(encoding="utf-8"))
        assert data["source"]["period"] == "2026-05"


class TestRopTsvEnriched:
    def test_tsv_columns_order_has_67_fields(self) -> None:
        columns = review_tsv_columns()
        assert len(columns) == 67
        expected_order = [
            "event_id",
            "source_id",
            "source_type",
            "source_role",
            "source_display_name",
            "client_id",
            "sender",
            "subject",
            "clean_subject",
            "transport_labels",
            "spam_label_present",
            "reply_label_present",
            "forwarded_wrapper",
            "form_email",
            "original_sender",
            "original_sender_email",
            "original_recipient",
            "original_message_date",
            "date_source",
            "x_email_id",
            "body_short",
            "attachments",
            "bot_case_type",
            "bot_case_subtype",
            "bot_recommended_queue",
            "bot_should_rop_see",
            "bot_correct_action",
            "bot_reason_code",
            "bot_priority",
            "bot_confidence",
            "bot_is_fallback",
            "bot_reasoning",
            "bitrix_match_status",
            "bitrix_match_quality",
            "bitrix_confidence",
            "needs_manual_review",
            "safe_to_use_as_target",
            "recommended_action",
            "recommended_next_step",
            "action_queue",
            "action_draft_id",
            "human_case_type",
            "human_case_subtype",
            "human_recommended_queue",
            "human_should_rop_see",
            "human_correct_action",
            "bitrix_status",
            "notes",
            "bitrix_lead_id",
            "bitrix_deal_id",
            "bitrix_responsible",
            "is_duplicate",
            "duplicate_of",
            "ai_used",
            "ai_provider",
            "ai_model",
            "ai_status",
            "ai_confidence",
            "ai_reason",
            "ai_risk_flags",
            "ai_error",
            "deterministic_case_type",
            "deterministic_case_subtype",
            "deterministic_recommended_queue",
            "deterministic_correct_action",
            "deterministic_confidence",
            "deterministic_reason_code",
        ]
        assert columns == expected_order

    def test_tsv_ai_columns_come_from_results_artifact_and_keep_deterministic_snapshot(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-ai-tsv-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": "Test body",
            }
        ]
        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "case_subtype": "tender",
                "recommended_queue": "tender",
                "should_rop_see": True,
                "correct_action": "review_tender",
                "reason_code": "deterministic_fallback",
                "confidence": 0.95,
                "is_fallback": False,
                "deterministic_case_type": "unknown",
                "deterministic_case_subtype": None,
                "deterministic_recommended_queue": "manual_review",
                "deterministic_correct_action": "manual_review",
                "deterministic_confidence": 0.2,
                "deterministic_reason_code": "deterministic_fallback",
                "original_event_id": "evt-001",
            }
        ]
        adjudicator_results = {
            "results": [
                {
                    "event_id": "evt-001",
                    "ai_used": True,
                    "ai_provider": "openai_responses",
                    "ai_model": "gpt-5.4-mini",
                    "ai_status": "ok",
                    "ai_confidence": 0.91,
                    "ai_reason": "Clear RFQ content",
                    "ai_risk_flags": ["marketing_conflict"],
                    "ai_error": "",
                    "deterministic_case_type": "unknown",
                    "deterministic_case_subtype": None,
                    "deterministic_recommended_queue": "manual_review",
                    "deterministic_correct_action": "manual_review",
                    "deterministic_confidence": 0.2,
                    "deterministic_reason_code": "deterministic_fallback",
                    "final_case_type": "new_lead",
                    "final_case_subtype": "tender",
                    "final_recommended_queue": "tender",
                    "final_correct_action": "review_tender",
                    "final_should_rop_see": True,
                    "merge_reason": "validated_ai_adjudicator_output",
                    "errors": [],
                }
            ]
        }

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized_events),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified_events),
            encoding="utf-8",
        )
        (run_dir / "rop_ai_adjudicator_results.json").write_text(
            json.dumps(adjudicator_results),
            encoding="utf-8",
        )

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-ai-tsv-run", format="tsv")
        handle_rop_export_review(args, logger=_null_logger())

        with (run_dir / "rop_review_table.tsv").open("r", encoding="utf-8") as file:
            row = next(csv.DictReader(file, delimiter="\t"))

        assert row["bot_case_type"] == "new_lead"
        assert row["ai_used"] == "true"
        assert row["ai_provider"] == "openai_responses"
        assert row["ai_model"] == "gpt-5.4-mini"
        assert row["ai_status"] == "ok"
        assert row["ai_confidence"] == "0.91"
        assert row["ai_reason"] == "Clear RFQ content"
        assert row["ai_risk_flags"] == "marketing_conflict"
        assert row["deterministic_case_type"] == "unknown"
        assert row["deterministic_recommended_queue"] == "manual_review"
        assert row["deterministic_reason_code"] == "deterministic_fallback"

    def test_tsv_body_short_is_bounded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-body-short-run"
        run_dir.mkdir(parents=True)

        long_body = "x" * 1000
        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": long_body,
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-body-short-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        assert len(rows) == 1
        row = rows[0]
        body_short = row["body_short"]
        assert len(body_short) <= 500

    def test_tsv_attachment_summary_sanitizes_tabs_newlines(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-attachment-sanitize-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": "Test",
                "attachments": [
                    {
                        "filename": "bad\tname.pdf",
                        "content_type": "application/pdf\nunsafe",
                        "size_bytes": 1024,
                    }
                ],
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized_events),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified_events),
            encoding="utf-8",
        )

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-attachment-sanitize-run", format="tsv")
        handle_rop_export_review(args, logger=_null_logger())

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            row = next(reader)

        attachments = row["attachments"]

        assert "\t" not in attachments
        assert "\n" not in attachments
        assert "\r" not in attachments
        assert "bad name.pdf" in attachments
        assert "application/pdf unsafe" in attachments

    def test_tsv_duplicate_false_is_exported_as_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-duplicate-false-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": "Test body",
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "is_duplicate": False,
                "duplicate_of": "",
                "original_event_id": "evt-001",
            }
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized_events),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified_events),
            encoding="utf-8",
        )

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-duplicate-false-run", format="tsv")
        handle_rop_export_review(args, logger=_null_logger())

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            row = next(reader)

        assert row["is_duplicate"] == "false"
        assert row["duplicate_of"] == ""

    def test_tsv_body_short_sanitized_no_tabs_newlines(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-sanitize-run"
        run_dir.mkdir(parents=True)

        body_with_tabs_newlines = "Line 1\nLine 2\tTabbed\nLine 3"
        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": body_with_tabs_newlines,
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-sanitize-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        row = rows[0]
        body_short = row["body_short"]
        assert "\t" not in body_short
        assert "\n" not in body_short
        assert "\r" not in body_short

    def test_tsv_attachment_metadata_only(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-attachments-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test with attachments",
                "body": "Test",
                "attachments": [
                    {
                        "filename": "document.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 1024,
                    },
                    {
                        "filename": "image.jpg",
                        "content_type": "image/jpeg",
                        "size_bytes": 2048,
                    },
                ],
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-attachments-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        row = rows[0]
        attachments = row["attachments"]

        assert "document.pdf" in attachments
        assert "application/pdf" in attachments
        assert "1024" in attachments
        assert "image.jpg" in attachments
        assert "image/jpeg" in attachments
        assert "2048" in attachments

        assert attachments.count(";") == 1

    def test_tsv_bot_priority_and_reasoning_exported(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-priority-reasoning-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": "Test body",
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "priority": "high",
                "reasoning": "Lead from trusted domain with purchase intent",
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-priority-reasoning-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        row = rows[0]
        assert row["bot_priority"] == "high"
        assert "purchase intent" in row["bot_reasoning"]

    def test_tsv_missing_optional_fields_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-missing-fields-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-missing-fields-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        row = rows[0]

        assert row["body_short"] == ""
        assert row["attachments"] == ""
        assert row["bot_priority"] == ""
        assert row["bot_reasoning"] == ""
        assert row["human_case_type"] == ""
        assert row["human_case_subtype"] == ""
        assert row["human_recommended_queue"] == ""
        assert row["human_should_rop_see"] == ""
        assert row["human_correct_action"] == ""
        assert row["bitrix_status"] == ""
        assert row["bitrix_lead_id"] == ""
        assert row["bitrix_deal_id"] == ""
        assert row["bitrix_responsible"] == ""
        assert row["is_duplicate"] == ""
        assert row["duplicate_of"] == ""
        assert row["notes"] == ""

    def test_tsv_bitrix_placeholders_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-bitrix-placeholders-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": "Test",
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-bitrix-placeholders-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        with tsv_path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        row = rows[0]

        assert row["bitrix_lead_id"] == ""
        assert row["bitrix_deal_id"] == ""
        assert row["bitrix_responsible"] == ""
        assert row["is_duplicate"] == ""
        assert row["duplicate_of"] == ""

    def test_tsv_no_raw_eml_no_attachment_content(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        run_dir = tmp_path / "runs" / "test-no-eml-content-run"
        run_dir.mkdir(parents=True)

        normalized_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "sender": "test@example.com",
                "subject": "Test",
                "body": "Test",
                "raw_eml": "From: test@example.com\nTo: recipient@example.com\n\nBody",
                "attachments": [
                    {
                        "filename": "secret.txt",
                        "content": "This should not be exported",
                        "content_type": "text/plain",
                        "size_bytes": 100,
                    }
                ],
            }
        ]

        classified_events = [
            {
                "event_id": "evt-001",
                "source_id": "test",
                "case_type": "new_lead",
                "reason_code": "new_contact",
                "confidence": 0.95,
                "is_fallback": False,
                "original_event_id": "evt-001",
            }
        ]

        normalized_path = run_dir / "normalized_events.json"
        classified_path = run_dir / "classified_events.json"
        normalized_path.write_text(json.dumps(normalized_events), encoding="utf-8")
        classified_path.write_text(json.dumps(classified_events), encoding="utf-8")

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        args = argparse.Namespace(run_id="test-no-eml-content-run", format="tsv")
        logger = _null_logger()

        handle_rop_export_review(args, logger=logger)

        tsv_path = run_dir / "rop_review_table.tsv"
        tsv_content = tsv_path.read_text(encoding="utf-8")

        assert "raw_eml" not in tsv_content
        assert "From: test@example.com" not in tsv_content
        assert "This should not be exported" not in tsv_content
        assert "secret.txt (text/plain, 100)" in tsv_content


class TestRopEvaluateReview:
    def test_rejects_invalid_run_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: Path("/tmp"))

        args = argparse.Namespace(run_id="../etc/passwd", tsv=None)

        with pytest.raises(RopCliError, match="Invalid run_id"):
            handle_rop_evaluate_review(args, logger=_null_logger())

    def test_rejects_path_traversal_with_valid_charset(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: Path("/tmp"))

        args = argparse.Namespace(run_id="safe..unsafe", tsv=None)

        with pytest.raises(RopCliError, match="Invalid run_id"):
            handle_rop_evaluate_review(args, logger=_null_logger())


class TestMailboxEnvValidation:
    def _mailbox_settings(self) -> dict:
        return {
            "rop": {
                "sources": [
                    {
                        "source_id": "hotline_mailbox",
                        "source_type": "mailbox_readonly",
                        "source_role": "technical_aggregator",
                        "client_id": "welding",
                        "display_name": "Welding Hotline mailbox",
                        "enabled": True,
                        "authority": "read_only",
                        "items_max": 20,
                        "mailbox": {
                            "host": "mail.example.com",
                            "port": 993,
                            "use_ssl": True,
                            "folder": "welding",
                            "username_env": "ROP_MAILBOX_USERNAME",
                            "password_env": "ROP_MAILBOX_PASSWORD",
                        },
                    },
                ],
            },
        }

    def _sample_settings(self) -> dict:
        return {
            "rop": {
                "sources": [
                    {
                        "source_id": "rop_batch_sample",
                        "source_type": "json_batch",
                        "source_role": "batch_sample",
                        "client_id": "welding",
                        "display_name": "Sample",
                        "enabled": True,
                        "authority": "read_only",
                        "items_max": 10,
                        "batch": {
                            "path": "storage/mock/test.json",
                            "period": "2026-05",
                        },
                    },
                ],
            },
        }

    def test_missing_mailbox_credentials_fail_before_pipeline_and_list_env_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "")
        monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "")

        settings = self._mailbox_settings()

        with pytest.raises(RopCliError) as exc_info:
            _validate_mailbox_env_for_sources(settings)

        msg = str(exc_info.value)
        assert "Missing required env for ROP source hotline_mailbox" in msg
        assert "ROP_MAILBOX_USERNAME" in msg
        assert "ROP_MAILBOX_PASSWORD" in msg
        assert "Add values to .env and retry." in msg

    def test_missing_mailbox_credentials_do_not_produce_normalized_events_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = self._mailbox_settings()

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setattr(cli_module, "get_project_root", lambda: tmp_path)
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "")
        monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "")
        monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "test-session")
        monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "test-token1")
        monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "test-token2")

        args = argparse.Namespace(
            source_id="hotline_mailbox",
            all_sources=False,
            items_max=10,
            period=None,
            run_id="test-missing-creds",
        )

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_run(args, settings=settings, logger=_null_logger())

        msg = str(exc_info.value)
        assert "Missing required env for ROP source hotline_mailbox" in msg
        assert "ROP_MAILBOX_USERNAME" in msg
        assert "ROP_MAILBOX_PASSWORD" in msg
        assert "Add values to .env and retry." in msg
        assert "normalized_events.json not found" not in msg
        assert "ROP run completed but review TSV export failed" not in msg

    def test_valid_mailbox_env_passes_validation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ROP_MAILBOX_USERNAME", "user")
        monkeypatch.setenv("ROP_MAILBOX_PASSWORD", "pass")

        _validate_mailbox_env_for_sources(self._mailbox_settings())

    def test_sample_source_does_not_require_mailbox_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ROP_MAILBOX_USERNAME", raising=False)
        monkeypatch.delenv("ROP_MAILBOX_PASSWORD", raising=False)

        _validate_mailbox_env_for_sources(self._sample_settings())
