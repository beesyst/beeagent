from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import pytest

from beeagent_module.core.cli import (
    RopCliError,
    _apply_source_overrides,
    _tsv_columns,
    create_rop_parser,
    handle_rop_export_review,
    handle_rop_run,
    handle_rop_summary,
)
from beeagent_module.core.settings import load_settings


# Получение пустого логгера, который не выводит сообщения в тестах
def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_cli_rop")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Получение корневой директории проекта для загрузки тестовых данных и настроек
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


# Тесты для ROP CLI команд: проверяют парсинг аргументов, применение переопределений источников, выполнение команд и обработку ошибок
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
        assert args.items_max == 10
        assert args.period == "2026-05"
        assert args.run_id == "test-run-123"

    def test_rop_run_parser_allows_missing_optional_args(self) -> None:
        parser = create_rop_parser()
        args = parser.parse_args(["run"])
        assert args.rop_command == "run"
        assert args.source_id is None
        assert args.items_max is None
        assert args.period is None
        assert args.run_id is None

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


# Тесты для функции применения переопределений источников: проверяют, что правильные источники включаются/настраиваются, а ошибки обрабатываются корректно
class TestSourceOverrides:
    def test_apply_source_overrides_with_source_id(self) -> None:
        settings = load_settings(_project_root() / "config" / "settings.yml")

        for source in settings["rop"]["sources"]:
            if source["source_id"] == "rop_batch_sample":
                source["enabled"] = True

        effective = _apply_source_overrides(
            settings=settings,
            source_id="rop_batch_sample",
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
                items_max=None,
                logger=_null_logger(),
            )
        assert "rop.sources is not configured" in str(exc_info.value)


# Тесты для ROP CLI команд: проверяют парсинг аргументов, применение переопределений источников, выполнение команд и обработку ошибок
class TestRopCliRun:
    def test_rop_run_with_batch_source(self, tmp_path: Path) -> None:
        import argparse

        settings = load_settings(_project_root() / "config" / "settings.yml")

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

        args = argparse.Namespace(
            source_id="rop_batch_sample",
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

    def test_rop_run_exports_review_tsv_by_default(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        settings = load_settings(_project_root() / "config" / "settings.yml")

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

        assert reader.fieldnames == _tsv_columns()
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

    def test_rop_run_missing_source_id_raises_error(self, tmp_path: Path) -> None:
        import argparse

        settings = load_settings(_project_root() / "config" / "settings.yml")

        args = argparse.Namespace(
            source_id="nonexistent_source",
            items_max=None,
            period=None,
            run_id="test-cli-run-missing",
        )

        logger = _null_logger()

        with pytest.raises(RopCliError) as exc_info:
            handle_rop_run(args, settings=settings, logger=logger)
        assert "Source not found" in str(exc_info.value)


# Тесты для ROP CLI summary и export-review команд: проверяют, что команды корректно обрабатывают существующие данные, а также обрабатывают ошибки при отсутствии данных или поддерживаемых форматов
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


# Тесты для ROP CLI export-review команды: проверяют, что команда корректно экспортирует данные в TSV формат для существующих данных, а также обрабатывает ошибки при отсутствии данных или поддерживаемых форматов
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
        assert header.split("\t") == _tsv_columns()

        expected_cols = _tsv_columns()
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
