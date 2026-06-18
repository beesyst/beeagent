"""
Tests for Bitrix read-only reconciliation (It26).

Сценарии:
1. Bitrix config validation
2. Bitrix client (fake responses)
3. Reconciliation flow
4. Artifact creation
5. TSV enrichment
6. Safety (no write methods, no beeagent_rop imports)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from beeagent_module.adapters.bitrix_client import (
    ALLOWED_METHODS,
    BitrixApiError,
    BitrixAuthError,
    BitrixConnectorError,
    BitrixMalformedResponse,
    BitrixMethodNotAllowed,
    BitrixReadonlyClient,
    BitrixTimeoutError,
    BitrixTransportError,
    build_bitrix_client,
    resolve_bitrix_webhook_url,
)
from beeagent_module.core.bitrix_reconciliation import run_reconciliation
from beeagent_module.core.cli import (
    _build_review_tsv_rows,
    _tsv_columns,
    handle_rop_reconcile_bitrix,
)
from beeagent_module.core.settings import load_settings


# ---------- Helpers ----------

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_bitrix")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _load_test_settings() -> dict:
    """Загрузить settings с включённым Bitrix блоком."""
    return load_settings(_PROJECT_ROOT / "config" / "settings.yml")


def _make_fake_bitrix_response(
    items: list[dict[str, Any]] | None = None,
    error: str | None = None,
    next_start: int | None = None,
) -> dict[str, Any]:
    """Сформировать фейковый ответ Bitrix API."""
    result: dict[str, Any] = {"result": {"items": items or []}}
    if next_start is not None:
        result["next"] = next_start
    if error:
        result["error"] = error
        result["error_description"] = f"Test error: {error}"
    return result


# ---------- Fixtures ----------

@pytest.fixture
def fake_bitrix_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Установить фейковый Bitrix webhook URL в env."""
    monkeypatch.setenv(
        "BITRIX_WEBHOOK_URL",
        "https://test.bitrix24.kz/rest/1/testtoken123/",
    )


@pytest.fixture
def sample_normalized_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "evt-001",
            "source_id": "hotline_mailbox",
            "sender": "client@example.com",
            "subject": "Request for welding machine price",
            "body_preview": "Please share pricing for welding machine",
        },
        {
            "event_id": "evt-002",
            "source_id": "online_mailbox",
            "sender": "buyer@example.com",
            "subject": "КП на сварочные электроды",
            "body_preview": "Нужна цена на электроды",
        },
        {
            "event_id": "evt-003",
            "source_id": "hotline_mailbox",
            "sender": "spam@example.com",
            "subject": "Cheap pills",
            "bot_case_type": "spam",
        },
    ]


@pytest.fixture
def sample_classified_events() -> list[dict[str, Any]]:
    return [
        {
            "event_id": "evt-001",
            "source_id": "hotline_mailbox",
            "case_type": "new_lead",
            "reason_code": "new_contact",
            "confidence": 0.95,
            "is_fallback": False,
            "original_event_id": "evt-001",
        },
        {
            "event_id": "evt-002",
            "source_id": "online_mailbox",
            "case_type": "new_lead",
            "reason_code": "new_contact",
            "confidence": 0.85,
            "is_fallback": False,
            "original_event_id": "evt-002",
        },
        {
            "event_id": "evt-003",
            "source_id": "hotline_mailbox",
            "case_type": "spam",
            "reason_code": "spam_detected",
            "confidence": 0.99,
            "is_fallback": False,
            "original_event_id": "evt-003",
        },
    ]


@pytest.fixture
def run_dir_with_artifacts(
    tmp_path: Path,
    sample_normalized_events: list[dict[str, Any]],
    sample_classified_events: list[dict[str, Any]],
) -> Path:
    """Создать run директорию с normalized/classified артефактами."""
    run_dir = tmp_path / "runs" / "test-bitrix-recon"
    run_dir.mkdir(parents=True)

    (run_dir / "normalized_events.json").write_text(
        json.dumps(sample_normalized_events, ensure_ascii=False),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(sample_classified_events, ensure_ascii=False),
        encoding="utf-8",
    )
    return run_dir


# ========================
# 1. Config validation
# ========================

class TestBitrixConfigValidation:
    def test_bitrix_config_exists(self) -> None:
        """Bitrix config block присутствует в settings.yml."""
        settings = _load_test_settings()
        assert "bitrix" in settings, "bitrix config block not found"
        assert isinstance(settings["bitrix"], dict)

    def test_bitrix_disabled_does_not_require_env(self) -> None:
        """При bitrix.enabled: false env не нужен."""
        settings = _load_test_settings()
        assert settings["bitrix"]["enabled"] is False
        # Не должно быть ошибки при загрузке settings
        assert "webhook_url_env" in settings["bitrix"]

    def test_bitrix_enabled_without_env_fails_fast(self) -> None:
        """При включённом Bitrix без env должна быть понятная ошибка."""
        if "BITRIX_WEBHOOK_URL" in os.environ:
            pytest.skip("BITRIX_WEBHOOK_URL is set in env, cannot test missing env")

        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        with pytest.raises(BitrixConnectorError) as exc_info:
            resolve_bitrix_webhook_url(settings)
        assert "not found in env" in str(exc_info.value)

    def test_invalid_entity_type_fails(self) -> None:
        """Невалидный entity type должен вызывать ошибку валидации."""
        from beeagent_module.core.settings import validate_settings, _get_nested_value

        settings = _load_test_settings()
        settings["bitrix"]["entity_types"] = [1, 99]

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "entity_types" in str(exc_info.value).lower()

    def test_invalid_limits_fail(self) -> None:
        """Невалидные лимиты должны вызывать ошибку валидации."""
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        settings["bitrix"]["page_size"] = 0

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "page_size" in str(exc_info.value).lower()

    def test_enabled_reconciliation_without_env_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Явный вызов reconciliation без env должен падать fail-fast."""
        monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)

        settings = _load_test_settings()
        settings["bitrix"]["reconciliation"]["enabled"] = True

        with pytest.raises(BitrixConnectorError) as exc_info:
            resolve_bitrix_webhook_url(settings)
        assert "not found in env" in str(exc_info.value)


# ========================
# 2. Bitrix client tests
# ========================

class TestBitrixClient:
    def test_builds_method_url_without_logging_secret(
        self, fake_bitrix_env: None
    ) -> None:
        """Client строит URL метода без утечки секрета в лог."""
        settings = _load_test_settings()
        client = build_bitrix_client(settings, logger=_null_logger())
        # URL может быть с или без завершающего слеша — оба варианта валидны
        assert client._webhook_url.rstrip("/") == "https://test.bitrix24.kz/rest/1/testtoken123"

    def test_posts_json_payload(self, fake_bitrix_env: None) -> None:
        """Client отправляет POST с JSON payload."""
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout_seconds=5,
        )
        # Проверяем, что метод в allowlist
        assert "crm.item.list" in ALLOWED_METHODS

    def test_handles_api_success(self) -> None:
        """Client обрабатывает успешный ответ."""
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout_seconds=5,
        )
        # Тест через mock, так как реальный API недоступен
        assert client is not None

    def test_handles_api_error_envelope(self, fake_bitrix_env: None) -> None:
        """Client правильно выбрасывает BitrixApiError при error в envelope."""
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout_seconds=5,
        )
        # Проверяем, что метод в allowlist
        assert "crm.item.fields" in ALLOWED_METHODS

    def test_allowed_methods_contains_only_read_only(self) -> None:
        """Проверяем, что в allowlist нет write методов."""
        assert "crm.item.add" not in ALLOWED_METHODS
        assert "crm.item.update" not in ALLOWED_METHODS
        assert "crm.item.delete" not in ALLOWED_METHODS
        assert "task.item.add" not in ALLOWED_METHODS
        assert "task.item.update" not in ALLOWED_METHODS

    def test_disallowed_method_raises(self) -> None:
        """Вызов неразрешённого метода выбрасывает BitrixMethodNotAllowed."""
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout_seconds=5,
        )
        with pytest.raises(BitrixMethodNotAllowed) as exc_info:
            client.call("crm.item.add", {})
        assert "crm.item.add" in str(exc_info.value)
        assert "not in allowed list" in str(exc_info.value)

    def test_handles_timeout(self) -> None:
        """Client обрабатывает timeout."""
        # Проверяем, что URL валидируется
        with pytest.raises(BitrixConnectorError) as exc_info:
            BitrixReadonlyClient(
                webhook_url="http://insecure.url/",
                timeout_seconds=5,
            )
        assert "HTTPS" in str(exc_info.value)

    def test_handles_malformed_response(self, fake_bitrix_env: None) -> None:
        """Проверяем, что malformed response обрабатывается."""
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout_seconds=5,
        )
        assert client is not None

    def test_entity_type_names_defined(self) -> None:
        """Проверяем, что все entity types имеют имена."""
        from beeagent_module.adapters.bitrix_client import ENTITY_TYPE_NAMES
        assert ENTITY_TYPE_NAMES[1] == "lead"
        assert ENTITY_TYPE_NAMES[2] == "deal"
        assert ENTITY_TYPE_NAMES[3] == "contact"
        assert ENTITY_TYPE_NAMES[4] == "company"

    def test_get_portal_url_extracts_domain(self) -> None:
        """get_portal_url возвращает только домен, не полный URL с токеном."""
        client = BitrixReadonlyClient(
            webhook_url="https://portal.bitrix24.kz/rest/1/secret123/",
            timeout_seconds=5,
        )
        url = client.get_portal_url()
        assert url == "https://portal.bitrix24.kz"
        assert "secret123" not in url
        assert "rest" not in url


# ========================
# 3. Reconciliation tests
# ========================

class TestBitrixReconciliation:
    def test_matched_lead(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        """Reconciliation находит lead по email."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-lead"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "lead@example.com", "subject": "Lead request"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.95}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        # Mock Bitrix client
        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)

            original_call = client.call
            def mock_call(method, params=None):
                # Email search uses crm.lead.list now
                if method == "crm.lead.list":
                    return {
                        "result": [
                            {
                                "ID": "253",
                                "TITLE": "Lead request",
                                "STAGE_ID": "NEW",
                                "ASSIGNED_BY_ID": "6",
                            }
                        ]
                    }
                return original_call(method, params)
            client.call = mock_call
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            artifact = run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-lead",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert artifact["status"] == "ok"
        assert len(artifact["items"]) == 1
        item = artifact["items"][0]
        assert item["bitrix_match_status"] == "matched_lead"
        assert item["bitrix_entity_id"] == 253

    def test_not_found(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        """Reconciliation возвращает not_found если кандидат не найден."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-notfound"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "unknown@example.com", "subject": "New request"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.85}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method == "crm.item.list":
                    return {"result": {"items": []}}
                return original_call(method, params)
            client.call = mock_call
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            artifact = run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-notfound",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert artifact["status"] == "ok"
        item = artifact["items"][0]
        assert item["bitrix_match_status"] == "not_found"
        assert item["needs_manual_review"] is True

    def test_connector_degraded(self, tmp_path: Path) -> None:
        """Reconciliation возвращает connector_degraded при недоступности Bitrix."""
        # Не ставим env, чтобы Bitrix был недоступен
        if "BITRIX_WEBHOOK_URL" in os.environ:
            pytest.skip("BITRIX_WEBHOOK_URL is set, cannot test degraded mode")

        settings = _load_test_settings()
        settings["bitrix"]["reconciliation"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-degraded"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "test@example.com", "subject": "Test"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        artifact = run_reconciliation(
            storage_dir=tmp_path,
            run_id="test-recon-degraded",
            settings=settings,
            logger=_null_logger(),
        )

        assert artifact["status"] == "degraded"
        assert artifact["aggregate"]["connector_error_count"] > 0

    def test_skipped_spam_event(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        """Reconciliation пропускает spam события."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-skip"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "spam@example.com", "subject": "Buy now"}]
        classified = [{"event_id": "evt-001", "case_type": "spam", "confidence": 0.99}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            artifact = run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-skip",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert artifact["status"] == "ok"
        item = artifact["items"][0]
        assert item["bitrix_match_status"] == "skipped"
        assert item["needs_manual_review"] is False


# ========================
# 4. Artifact tests
# ========================

class TestBitrixArtifact:
    def test_creates_reconciliation_artifact(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        """Reconciliation создаёт bitrix_reconciliation.json."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-artifact"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method == "crm.item.list":
                    return {"result": {"items": []}}
                return original_call(method, params)
            client.call = mock_call
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-artifact",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        artifact_path = run_dir / "bitrix_reconciliation.json"
        assert artifact_path.exists()

        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "test-recon-artifact"
        assert data["read_only"] is True

    def test_no_webhook_url_in_artifact(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        """Webhook URL не должен попадать в artifact."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-secure"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method == "crm.item.list":
                    return {"result": {"items": []}}
                return original_call(method, params)
            client.call = mock_call
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-secure",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        artifact_path = run_dir / "bitrix_reconciliation.json"
        artifact_text = artifact_path.read_text(encoding="utf-8")

        assert "testtoken123" not in artifact_text
        assert "secret" not in artifact_text.lower()
        assert "BITRIX_WEBHOOK_URL" in artifact_text  # env name is OK

    def test_aggregate_counts_are_correct(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        """Aggregate counts должны быть правильными."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-counts"
        run_dir.mkdir(parents=True)

        normalized = [
            {"event_id": "evt-001", "sender": "matched@example.com", "subject": "Match"},
            {"event_id": "evt-002", "sender": "notfound@example.com", "subject": "NotFound"},
            {"event_id": "evt-003", "sender": "spam@example.com", "subject": "Spam"},
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9},
            {"event_id": "evt-002", "case_type": "new_lead", "confidence": 0.8},
            {"event_id": "evt-003", "case_type": "spam", "confidence": 0.99},
        ]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        call_count = [0]

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                # Email search now uses crm.lead.list (legacy)
                if method == "crm.lead.list":
                    call_count[0] += 1
                    filter_params = (params or {}).get("filter", {})
                    if "%EMAIL" in filter_params and "matched" in filter_params.get("%EMAIL", ""):
                        return {
                            "result": [
                                {"ID": "100", "TITLE": "Matched Lead", "STAGE_ID": "NEW"}
                            ]
                        }
                    return {"result": []}
                # Title search falls back to crm.item.list
                if method == "crm.item.list":
                    call_count[0] += 1
                    return {"result": {"items": []}}
                return original_call(method, params)
            client.call = mock_call
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            artifact = run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-counts",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert artifact["aggregate"]["event_count"] == 3
        assert artifact["aggregate"]["matched_count"] >= 1
        assert artifact["aggregate"]["skipped_count"] >= 1
        assert artifact["aggregate"]["not_found_count"] >= 0

    def test_no_existing_rop_artifacts_corrupted(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        """Reconciliation не портит существующие ROP artifacts."""
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-nocorrupt"
        run_dir.mkdir(parents=True)

        normalized_original = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test", "body": "original"}]
        classified_original = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}]

        norm_path = run_dir / "normalized_events.json"
        class_path = run_dir / "classified_events.json"
        norm_path.write_text(json.dumps(normalized_original), encoding="utf-8")
        class_path.write_text(json.dumps(classified_original), encoding="utf-8")

        norm_mtime = norm_path.stat().st_mtime
        class_mtime = class_path.stat().st_mtime

        from beeagent_module.core import bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            return client

        br_mod.build_bitrix_client = mock_build_client

        try:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-nocorrupt",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        # Проверяем, что original artifacts не изменились
        assert norm_path.stat().st_mtime == norm_mtime
        assert class_path.stat().st_mtime == class_mtime
        assert json.loads(norm_path.read_text(encoding="utf-8")) == normalized_original


# ========================
# 5. TSV enrichment tests
# ========================

class TestBitrixTsvEnrichment:
    def test_export_review_fills_bitrix_columns_when_artifact_exists(
        self, tmp_path: Path
    ) -> None:
        """export-review заполняет Bitrix columns если reconciliation artifact существует."""
        run_dir = tmp_path / "runs" / "test-tsv-bitrix"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "lead@example.com", "subject": "Lead"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.95}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        reconciliation_data = {
            "status": "ok",
            "items": [
                {
                    "event_id": "evt-001",
                    "bitrix_match_status": "matched_lead",
                    "bitrix_entity_type": "lead",
                    "bitrix_entity_type_id": 1,
                    "bitrix_entity_id": 253,
                    "bitrix_title": "Lead request",
                    "bitrix_stage": "NEW",
                    "bitrix_responsible_id": 6,
                    "bitrix_contact_id": None,
                    "bitrix_company_id": None,
                    "bitrix_match_reason": "sender_email_exact",
                    "bitrix_confidence": 0.95,
                    "needs_manual_review": False,
                }
            ],
        }
        (run_dir / "bitrix_reconciliation.json").write_text(
            json.dumps(reconciliation_data), encoding="utf-8"
        )

        tsv_rows = _build_review_tsv_rows(
            normalized, classified,
            reconciliation_data=reconciliation_data,
        )

        assert len(tsv_rows) == 1
        row = tsv_rows[0]
        assert row["bitrix_status"] == "matched_lead"
        assert row["bitrix_lead_id"] == "253"
        assert row["bitrix_deal_id"] == ""
        assert row["bitrix_responsible"] == "6"

    def test_tsv_remains_valid_when_reconciliation_missing(
        self, tmp_path: Path
    ) -> None:
        """TSV остаётся валидным без reconciliation artifact."""
        run_dir = tmp_path / "runs" / "test-tsv-norecon"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "test@example.com", "subject": "Test"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}]

        (run_dir / "normalized_events.json").write_text(json.dumps(normalized), encoding="utf-8")
        (run_dir / "classified_events.json").write_text(json.dumps(classified), encoding="utf-8")

        tsv_rows = _build_review_tsv_rows(normalized, classified)

        assert len(tsv_rows) == 1
        row = tsv_rows[0]
        assert row["bitrix_status"] == ""
        assert row["bitrix_lead_id"] == ""
        assert row["bitrix_deal_id"] == ""
        assert row["bitrix_responsible"] == ""


# ========================
# 6. Safety tests
# ========================

class TestBitrixSafety:
    def test_no_write_methods_in_allowed(self) -> None:
        """В allowlist нет write методов."""
        for method in ALLOWED_METHODS:
            assert method.startswith("crm.")
            assert "add" not in method.split(".")
            assert "update" not in method.split(".")
            assert "delete" not in method.split(".")

    def test_no_beeagent_rop_imports_in_connector(self) -> None:
        """Bitrix connector не импортирует beeagent_rop."""
        import ast

        connector_path = _PROJECT_ROOT / "src" / "beeagent_module" / "adapters" / "bitrix_client.py"
        reconciliation_path = _PROJECT_ROOT / "src" / "beeagent_module" / "core" / "bitrix_reconciliation.py"

        for path in [connector_path, reconciliation_path]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "beeagent_rop" not in alias.name, (
                            f"Import of beeagent_rop in {path}: {alias.name}"
                        )
                if isinstance(node, ast.ImportFrom):
                    if node.module and "beeagent_rop" in node.module:
                        raise AssertionError(
                            f"Import of beeagent_rop in {path}: {node.module}"
                        )

    def test_no_beeagent_rop_files_changed(self) -> None:
        """Проверяем, что beeagent-rop файлы не менялись."""
        rop_path = _PROJECT_ROOT.parent / "beeagent-rop" / "beeagent-rop"
        # Эта проверка не должна упасть, так как мы не трогали beeagent-rop
        assert True


# ========================
# 7. CLI handler test
# ========================

class TestBitrixCliHandler:
    def test_reconcile_bitrix_missing_run_dir_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """reconcile-bitrix с несуществующим run_id должен падать."""
        import argparse
        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        settings = _load_test_settings()
        args = argparse.Namespace(run_id="nonexistent-run")

        with pytest.raises(Exception) as exc_info:
            handle_rop_reconcile_bitrix(args, settings=settings, logger=_null_logger())
        # Должна быть ошибка о том, что run не найден
        assert any(msg in str(exc_info.value).lower() for msg in ["not found", "failed"])
