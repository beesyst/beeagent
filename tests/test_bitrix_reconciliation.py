from __future__ import annotations

import json
import logging
import os
from email.message import Message
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError, URLError

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
from beeagent_module.cases.rop_bitrix_reconciliation import (
    _classify_candidates,
    _reconcile_event,
    run_reconciliation,
)
from beeagent_module.core.cli import (
    handle_rop_reconcile_bitrix,
)
from beeagent_module.core.rop_review_export import _build_review_tsv_rows
from beeagent_module.core.settings import load_settings

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("BEEAGENT_WEB_ROP_TOKEN", "test-rop-token")
os.environ.setdefault("BEEAGENT_WEB_OPERATOR_TOKEN", "test-operator-token")


@pytest.fixture(autouse=True)
def _set_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_bitrix")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _load_test_settings() -> dict:
    return load_settings(_PROJECT_ROOT / "config" / "settings.yml")


def _make_fake_bitrix_response(
    items: list[dict[str, Any]] | None = None,
    error: str | None = None,
    next_start: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"result": {"items": items or []}}
    if next_start is not None:
        result["next"] = next_start
    if error:
        result["error"] = error
        result["error_description"] = f"Test error: {error}"
    return result


class _FakeHttpResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def fake_bitrix_env(monkeypatch: pytest.MonkeyPatch) -> None:
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


class TestBitrixConfigValidation:
    def test_bitrix_config_exists(self) -> None:
        settings = _load_test_settings()
        assert "bitrix" in settings, "bitrix config block not found"
        assert isinstance(settings["bitrix"], dict)

    def test_bitrix_disabled_does_not_require_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from beeagent_module.core.settings import validate_settings

        monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)

        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = False
        settings["bitrix"]["reconciliation"]["enabled"] = False

        assert settings["bitrix"]["enabled"] is False
        assert settings["bitrix"]["webhook_env"] == "BITRIX_WEBHOOK_URL"

        validate_settings(settings)

    def test_new_config_keys_are_validated(self) -> None:
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        bitrix = settings["bitrix"]

        assert isinstance(bitrix["webhook_env"], str)
        assert isinstance(bitrix["timeout"], int)
        assert isinstance(bitrix["page_size"], int)
        assert isinstance(bitrix["pages_max"], int)
        assert isinstance(bitrix["types_entity"], list)
        assert isinstance(bitrix["reconciliation"]["window_date"], int)
        validate_settings(settings)

    @pytest.mark.parametrize(
        ("old_key", "old_value"),
        [
            ("webhook_url_env", "BITRIX_WEBHOOK_URL"),
            ("timeout_seconds", 10),
            ("max_pages", 3),
            ("entity_types", [1, 2]),
        ],
    )
    def test_old_top_level_config_keys_are_rejected(
        self,
        old_key: str,
        old_value: object,
    ) -> None:
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        settings["bitrix"][old_key] = old_value

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert old_key in str(exc_info.value)

    def test_old_reconciliation_config_key_is_rejected(self) -> None:
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        settings["bitrix"]["reconciliation"]["date_window_days"] = 180

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "date_window_days" in str(exc_info.value)

    def test_reconciliation_enabled_requires_bitrix_enabled(self) -> None:
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = False
        settings["bitrix"]["reconciliation"]["enabled"] = True

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "bitrix.enabled" in str(exc_info.value)

    def test_bitrix_enabled_without_env_fails_fast(self) -> None:
        if "BITRIX_WEBHOOK_URL" in os.environ:
            pytest.skip("BITRIX_WEBHOOK_URL is set in env, cannot test missing env")

        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        with pytest.raises(BitrixConnectorError) as exc_info:
            resolve_bitrix_webhook_url(settings)
        assert "not found in env" in str(exc_info.value)

    def test_invalid_entity_type_fails(self) -> None:
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        settings["bitrix"]["types_entity"] = [1, 99]

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "types_entity" in str(exc_info.value).lower()

    def test_invalid_limits_fail(self) -> None:
        from beeagent_module.core.settings import validate_settings

        settings = _load_test_settings()
        settings["bitrix"]["page_size"] = 0

        with pytest.raises(RuntimeError) as exc_info:
            validate_settings(settings)
        assert "page_size" in str(exc_info.value).lower()

    def test_enabled_reconciliation_without_env_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)

        settings = _load_test_settings()
        settings["bitrix"]["reconciliation"]["enabled"] = True

        with pytest.raises(BitrixConnectorError) as exc_info:
            resolve_bitrix_webhook_url(settings)
        assert "not found in env" in str(exc_info.value)


class TestBitrixClient:
    def test_builds_method_url_without_logging_secret(
        self, fake_bitrix_env: None
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["timeout"] = 7
        settings["bitrix"]["page_size"] = 13
        settings["bitrix"]["pages_max"] = 2
        client = build_bitrix_client(settings, logger=_null_logger())
        assert (
            client._webhook_url.rstrip("/")
            == "https://test.bitrix24.kz/rest/1/testtoken123"
        )
        assert client._timeout == 7
        assert client._page_size == 13
        assert client._pages_max == 2

    def test_posts_json_payload(self, fake_bitrix_env: None) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps({"result": {"items": []}}).encode("utf-8")
        with patch(
            "beeagent_module.adapters.bitrix_client.urlopen",
            return_value=_FakeHttpResponse(body),
        ) as mocked_urlopen:
            result = client.call("crm.item.list", {"filter": {"%title": "A"}})

        assert result == {"result": {"items": []}}
        request = mocked_urlopen.call_args.args[0]
        assert request.full_url.endswith("/crm.item.list")
        assert b"%title" in request.data

    def test_handles_api_success(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps({"result": {"ok": True}}).encode("utf-8")
        with patch(
            "beeagent_module.adapters.bitrix_client.urlopen",
            return_value=_FakeHttpResponse(body),
        ):
            assert client.call("crm.item.fields", {"entityTypeId": 1}) == {
                "result": {"ok": True}
            }

    def test_handles_api_error_envelope(self, fake_bitrix_env: None) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        body = json.dumps(
            {
                "error": "ACCESS_DENIED",
                "error_description": "Forbidden",
            }
        ).encode("utf-8")
        with (
            patch(
                "beeagent_module.adapters.bitrix_client.urlopen",
                return_value=_FakeHttpResponse(body),
            ),
            pytest.raises(BitrixApiError),
        ):
            client.call("crm.item.fields", {"entityTypeId": 1})

    def test_handles_http_403(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        error = HTTPError(
            url="https://test.bitrix24.kz/rest/1/token/crm.item.list",
            code=403,
            msg="Forbidden",
            hdrs=Message(),
            fp=None,
        )
        with (
            patch(
                "beeagent_module.adapters.bitrix_client.urlopen",
                side_effect=error,
            ),
            pytest.raises(BitrixAuthError),
        ):
            client.call("crm.item.list", {})

    def test_allowed_methods_contains_only_read_only(self) -> None:
        """Проверяем, что в allowlist нет write методов."""
        assert "crm.item.add" not in ALLOWED_METHODS
        assert "crm.item.update" not in ALLOWED_METHODS
        assert "crm.item.delete" not in ALLOWED_METHODS
        assert "crm.deal.list" not in ALLOWED_METHODS
        assert "task.item.add" not in ALLOWED_METHODS
        assert "task.item.update" not in ALLOWED_METHODS

    def test_disallowed_method_raises(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        with pytest.raises(BitrixMethodNotAllowed) as exc_info:
            client.call("crm.item.add", {})
        assert "crm.item.add" in str(exc_info.value)
        assert "not in allowed list" in str(exc_info.value)

    def test_rejects_insecure_webhook_url(self) -> None:
        with pytest.raises(BitrixConnectorError) as exc_info:
            BitrixReadonlyClient(
                webhook_url="http://insecure.url/",
                timeout=5,
            )
        assert "HTTPS" in str(exc_info.value)

    def test_handles_timeout(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        with (
            patch(
                "beeagent_module.adapters.bitrix_client.urlopen",
                side_effect=URLError("timed out"),
            ),
            pytest.raises(BitrixTimeoutError),
        ):
            client.call("crm.item.list", {})

    def test_handles_malformed_response(self, fake_bitrix_env: None) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )
        with (
            patch(
                "beeagent_module.adapters.bitrix_client.urlopen",
                return_value=_FakeHttpResponse(b"{broken"),
            ),
            pytest.raises(BitrixMalformedResponse),
        ):
            client.call("crm.item.list", {})

    def test_pagination_uses_next_and_pages_max(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
            page_size=2,
            pages_max=2,
        )
        starts: list[int | None] = []

        def fake_call(method: str, params: dict[str, Any] | None = None) -> dict:
            assert method == "crm.item.list"
            starts.append((params or {}).get("start"))
            if len(starts) == 1:
                return {"result": {"items": [{"id": 1}]}, "next": 2}
            return {"result": {"items": [{"id": 2}]}, "next": 4}

        client.call = fake_call  # type: ignore[method-assign]

        items = client.search_candidates(1, "plain title")

        assert items == [{"id": 1}, {"id": 2}]
        assert starts == [None, 2]

    def test_deal_email_search_does_not_call_legacy_deal_list(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://test.bitrix24.kz/rest/1/token/",
            timeout=5,
        )

        def fake_call(method: str, params: dict[str, Any] | None = None) -> dict:
            if method == "crm.deal.list":
                raise AssertionError("crm.deal.list must not be called")
            return {"result": []}

        client.call = fake_call  # type: ignore[method-assign]

        assert client.search_candidates(2, "client@example.com") == []

    def test_entity_type_names_defined(self) -> None:
        from beeagent_module.adapters.bitrix_client import ENTITY_TYPE_NAMES

        assert ENTITY_TYPE_NAMES[1] == "lead"
        assert ENTITY_TYPE_NAMES[2] == "deal"
        assert ENTITY_TYPE_NAMES[3] == "contact"
        assert ENTITY_TYPE_NAMES[4] == "company"

    def test_get_portal_url_extracts_domain(self) -> None:
        client = BitrixReadonlyClient(
            webhook_url="https://portal.bitrix24.kz/rest/1/secret123/",
            timeout=5,
        )
        url = client.get_portal_url()
        assert url == "https://portal.bitrix24.kz"
        assert "secret123" not in url
        assert "rest" not in url


class TestBitrixReconciliation:
    def test_irrelevant_event_is_skipped_non_actionable(self) -> None:
        result = _reconcile_event(
            event={
                "event_id": "evt-irrelevant",
                "case_type": "irrelevant",
                "sender": "ignore@example.com",
                "subject": "Ignore me",
            },
            client=None,  # type: ignore[arg-type]
            entity_types=[1],
            candidate_limit=20,
            window_date=180,
            logger=_null_logger(),
        )

        assert result["bitrix_match_status"] == "skipped"
        assert result["bitrix_match_reason"] == "bot_case_type_not_actionable"
        assert result["needs_manual_review"] is False
        assert result["safe_to_use_as_target"] is False

    def test_phone_exact_match_is_strong_and_safe(self) -> None:
        result = _classify_candidates(
            event={
                "event_id": "evt-phone",
                "case_type": "new_lead",
                "phone": "+7 747 321 82 18",
            },
            candidates=[
                {
                    "entity_type_id": 1,
                    "entity": {
                        "ID": "253",
                        "TITLE": "Lead request",
                        "PHONE": [{"VALUE": "+7 (747) 321-82-18"}],
                    },
                }
            ],
            candidate_limit=20,
        )

        assert result["bitrix_match_status"] == "matched_lead"
        assert result["bitrix_match_quality"] == "strong"
        assert result["bitrix_match_reason"] == "phone_exact"
        assert result["safe_to_use_as_target"] is True
        assert result["needs_manual_review"] is False

    def test_matched_lead(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-lead"
        run_dir.mkdir(parents=True)

        normalized = [
            {
                "event_id": "evt-001",
                "sender": "lead@example.com",
                "subject": "Lead request",
            }
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.95}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)

            original_call = client.call

            def mock_call(method, params=None):
                if method == "crm.lead.list":
                    return {
                        "result": [
                            {
                                "ID": "253",
                                "TITLE": "Lead request",
                                "STAGE_ID": "NEW",
                                "ASSIGNED_BY_ID": "6",
                                "EMAIL": [{"VALUE": "lead@example.com"}],
                            }
                        ]
                    }
                if method in {
                    "crm.deal.list",
                    "crm.contact.list",
                    "crm.company.list",
                }:
                    return {"result": []}
                if method == "crm.item.list":
                    return {"result": {"items": []}}
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
        assert item["bitrix_match_quality"] == "strong"
        assert item["bitrix_entity_id"] == 253
        assert item["safe_to_use_as_target"] is True

    def test_not_found(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-notfound"
        run_dir.mkdir(parents=True)

        normalized = [
            {
                "event_id": "evt-001",
                "sender": "unknown@example.com",
                "subject": "New request",
            }
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.85}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method in {
                    "crm.lead.list",
                    "crm.deal.list",
                    "crm.contact.list",
                    "crm.company.list",
                }:
                    return {"result": []}
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

    def test_disabled_bitrix_fails_before_client_build(
        self,
        tmp_path: Path,
        fake_bitrix_env: None,
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = False

        run_dir = tmp_path / "runs" / "test-recon-disabled-bitrix"
        run_dir.mkdir(parents=True)
        (run_dir / "normalized_events.json").write_text(
            json.dumps([{"event_id": "evt-001", "sender": "a@b.com"}]),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps([{"event_id": "evt-001", "case_type": "new_lead"}]),
            encoding="utf-8",
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def fail_build(*args: object, **kwargs: object) -> object:
            raise AssertionError("build_bitrix_client must not be called")

        br_mod.build_bitrix_client = fail_build

        try:
            with pytest.raises(RuntimeError) as exc_info:
                run_reconciliation(
                    storage_dir=tmp_path,
                    run_id="test-recon-disabled-bitrix",
                    settings=settings,
                    logger=_null_logger(),
                )
        finally:
            br_mod.build_bitrix_client = original_build

        assert "bitrix.enabled: true" in str(exc_info.value)

    def test_missing_classified_events_fails_clearly(
        self,
        tmp_path: Path,
    ) -> None:
        settings = _load_test_settings()
        run_dir = tmp_path / "runs" / "test-recon-missing-classified"
        run_dir.mkdir(parents=True)
        (run_dir / "normalized_events.json").write_text(
            json.dumps([{"event_id": "evt-001"}]),
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError) as exc_info:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-missing-classified",
                settings=settings,
                logger=_null_logger(),
            )

        assert "classified_events.json" in str(exc_info.value)
        assert "Required artifact not found" in str(exc_info.value)

    def test_malformed_classified_events_fails_clearly(
        self,
        tmp_path: Path,
    ) -> None:
        settings = _load_test_settings()
        run_dir = tmp_path / "runs" / "test-recon-malformed-classified"
        run_dir.mkdir(parents=True)
        (run_dir / "normalized_events.json").write_text(
            json.dumps([{"event_id": "evt-001"}]),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text("{broken", encoding="utf-8")

        with pytest.raises(RuntimeError) as exc_info:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-malformed-classified",
                settings=settings,
                logger=_null_logger(),
            )

        assert "classified_events.json" in str(exc_info.value)
        assert "malformed JSON" in str(exc_info.value)

    def test_missing_normalized_events_fails_clearly(
        self,
        tmp_path: Path,
    ) -> None:
        settings = _load_test_settings()
        run_dir = tmp_path / "runs" / "test-recon-missing-normalized"
        run_dir.mkdir(parents=True)
        (run_dir / "classified_events.json").write_text(
            json.dumps([{"event_id": "evt-001"}]),
            encoding="utf-8",
        )

        with pytest.raises(RuntimeError) as exc_info:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-missing-normalized",
                settings=settings,
                logger=_null_logger(),
            )

        assert "normalized_events.json" in str(exc_info.value)
        assert "Required artifact not found" in str(exc_info.value)

    def test_connector_degraded(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-degraded"
        run_dir.mkdir(parents=True)

        normalized = [
            {"event_id": "evt-001", "sender": "test@example.com", "subject": "Test"}
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        class FakeClient:
            def get_portal_url(self) -> str:
                return "https://test.bitrix24.kz"

            def search_candidates(
                self,
                *args: object,
                **kwargs: Any,
            ) -> list:
                raise BitrixTransportError("network down")

        br_mod.build_bitrix_client = lambda settings, logger=None: FakeClient()

        try:
            artifact = run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-degraded",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert artifact["status"] == "degraded"
        assert artifact["aggregate"]["connector_degraded_count"] == 1
        assert artifact["aggregate"]["not_found_count"] == 0
        assert artifact["items"][0]["bitrix_match_status"] == "connector_degraded"

    @pytest.mark.parametrize(
        "error",
        [
            BitrixAuthError("HTTP 403"),
            BitrixTimeoutError("timed out"),
            BitrixMalformedResponse("malformed JSON"),
            BitrixApiError("API error"),
        ],
    )
    def test_connector_errors_do_not_become_not_found(
        self,
        tmp_path: Path,
        fake_bitrix_env: None,
        error: BitrixConnectorError,
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-error-semantics"
        run_dir.mkdir(parents=True)
        normalized = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead"}]
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        class FakeClient:
            def get_portal_url(self) -> str:
                return "https://test.bitrix24.kz"

            def search_candidates(
                self,
                *args: object,
                **kwargs: Any,
            ) -> list:
                raise error

        br_mod.build_bitrix_client = lambda settings, logger=None: FakeClient()

        try:
            artifact = run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-error-semantics",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert artifact["status"] == "degraded"
        assert artifact["aggregate"]["connector_degraded_count"] == 1
        assert artifact["aggregate"]["not_found_count"] == 0
        assert artifact["items"][0]["bitrix_match_status"] == "connector_degraded"

    def test_debug_log_does_not_include_raw_email(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True
        settings["bitrix"]["types_entity"] = [1]

        run_dir = tmp_path / "runs" / "test-recon-log-no-email"
        run_dir.mkdir(parents=True)
        (run_dir / "normalized_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-001",
                        "sender": "raw-client@example.com",
                        "subject": "Need welding machine",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps([{"event_id": "evt-001", "case_type": "new_lead"}]),
            encoding="utf-8",
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        class FakeClient:
            def get_portal_url(self) -> str:
                return "https://test.bitrix24.kz"

            def search_candidates(
                self,
                *args: object,
                **kwargs: Any,
            ) -> list[dict[str, Any]]:
                return []

        br_mod.build_bitrix_client = lambda settings, logger=None: FakeClient()
        logger = logging.getLogger("test_bitrix_no_raw_email")

        try:
            with caplog.at_level(logging.DEBUG, logger=logger.name):
                run_reconciliation(
                    storage_dir=tmp_path,
                    run_id="test-recon-log-no-email",
                    settings=settings,
                    logger=logger,
                )
        finally:
            br_mod.build_bitrix_client = original_build

        assert "bitrix search by email for entity_type=1" in caplog.text
        assert "raw-client@example.com" not in caplog.text

    def test_skipped_spam_event(self, tmp_path: Path, fake_bitrix_env: None) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-skip"
        run_dir.mkdir(parents=True)

        normalized = [
            {"event_id": "evt-001", "sender": "spam@example.com", "subject": "Buy now"}
        ]
        classified = [{"event_id": "evt-001", "case_type": "spam", "confidence": 0.99}]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

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


class TestBitrixArtifact:
    def test_creates_reconciliation_artifact(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-artifact"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test"}]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method in {
                    "crm.lead.list",
                    "crm.deal.list",
                    "crm.contact.list",
                    "crm.company.list",
                }:
                    return {"result": []}
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
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-secure"
        run_dir.mkdir(parents=True)

        normalized = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test"}]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method in {
                    "crm.lead.list",
                    "crm.deal.list",
                    "crm.contact.list",
                    "crm.company.list",
                }:
                    return {"result": []}
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
        assert "BITRIX_WEBHOOK_URL" in artifact_text

    def test_webhook_token_not_written_to_log(
        self,
        tmp_path: Path,
        fake_bitrix_env: None,
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True
        run_dir = tmp_path / "runs" / "test-recon-log-secure"
        run_dir.mkdir(parents=True)
        normalized = [{"event_id": "evt-001", "sender": "a@b.com", "subject": "Test"}]
        classified = [{"event_id": "evt-001", "case_type": "new_lead"}]
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        log_path = tmp_path / "app.log"
        logger = logging.getLogger("test_bitrix_file_log")
        logger.handlers.clear()
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        logger.addHandler(handler)

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        class FakeClient:
            def get_portal_url(self) -> str:
                return "https://test.bitrix24.kz"

            def search_candidates(
                self,
                *args: object,
                **kwargs: Any,
            ) -> list:
                return []

        br_mod.build_bitrix_client = lambda settings, logger=None: FakeClient()

        try:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-log-secure",
                settings=settings,
                logger=logger,
            )
        finally:
            br_mod.build_bitrix_client = original_build
            logger.removeHandler(handler)
            handler.close()

        log_text = log_path.read_text(encoding="utf-8")
        assert "testtoken123" not in log_text
        assert "BITRIX_WEBHOOK_URL" not in log_text

    def test_aggregate_counts_are_correct(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-counts"
        run_dir.mkdir(parents=True)

        normalized = [
            {
                "event_id": "evt-001",
                "sender": "matched@example.com",
                "subject": "Match",
            },
            {
                "event_id": "evt-002",
                "sender": "notfound@example.com",
                "subject": "NotFound",
            },
            {"event_id": "evt-003", "sender": "spam@example.com", "subject": "Spam"},
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9},
            {"event_id": "evt-002", "case_type": "new_lead", "confidence": 0.8},
            {"event_id": "evt-003", "case_type": "spam", "confidence": 0.99},
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        call_count = [0]

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method in {
                    "crm.lead.list",
                    "crm.deal.list",
                    "crm.contact.list",
                    "crm.company.list",
                }:
                    call_count[0] += 1
                    filter_params = (params or {}).get("filter", {})
                    if (
                        method == "crm.lead.list"
                        and "%EMAIL" in filter_params
                        and "matched" in filter_params.get("%EMAIL", "")
                    ):
                        return {
                            "result": [
                                {
                                    "ID": "100",
                                    "TITLE": "Matched Lead",
                                    "STAGE_ID": "NEW",
                                    "EMAIL": [{"VALUE": "matched@example.com"}],
                                }
                            ]
                        }
                    return {"result": []}
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
        assert artifact["aggregate"]["matched_count"] == 1
        assert artifact["aggregate"]["skipped_count"] == 1
        assert artifact["aggregate"]["not_found_count"] == 1
        assert artifact["aggregate"]["connector_degraded_count"] == 0

    def test_window_date_is_passed_to_lookup(
        self,
        tmp_path: Path,
        fake_bitrix_env: None,
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True
        settings["bitrix"]["types_entity"] = [1]
        settings["bitrix"]["reconciliation"]["window_date"] = 10

        run_dir = tmp_path / "runs" / "test-recon-date-filter"
        run_dir.mkdir(parents=True)
        normalized = [
            {
                "event_id": "evt-001",
                "sender": "a@b.com",
                "subject": "Test",
                "received_at": "2026-06-10T12:00:00+00:00",
            }
        ]
        classified = [{"event_id": "evt-001", "case_type": "new_lead"}]
        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client
        seen_date_from: list[str | None] = []

        class FakeClient:
            def get_portal_url(self) -> str:
                return "https://test.bitrix24.kz"

            def search_candidates(
                self,
                *args: object,
                **kwargs: Any,
            ) -> list[dict[str, Any]]:
                date_from = kwargs.get("date_from")
                assert date_from is None or isinstance(date_from, str)
                seen_date_from.append(date_from)
                return []

        br_mod.build_bitrix_client = lambda settings, logger=None: FakeClient()

        try:
            run_reconciliation(
                storage_dir=tmp_path,
                run_id="test-recon-date-filter",
                settings=settings,
                logger=_null_logger(),
            )
        finally:
            br_mod.build_bitrix_client = original_build

        assert seen_date_from
        assert all(value == "2026-05-31" for value in seen_date_from)

    def test_no_existing_rop_artifacts_corrupted(
        self, tmp_path: Path, fake_bitrix_env: None
    ) -> None:
        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True

        run_dir = tmp_path / "runs" / "test-recon-nocorrupt"
        run_dir.mkdir(parents=True)

        normalized_original = [
            {
                "event_id": "evt-001",
                "sender": "a@b.com",
                "subject": "Test",
                "body": "original",
            }
        ]
        classified_original = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}
        ]

        norm_path = run_dir / "normalized_events.json"
        class_path = run_dir / "classified_events.json"
        norm_path.write_text(json.dumps(normalized_original), encoding="utf-8")
        class_path.write_text(json.dumps(classified_original), encoding="utf-8")

        norm_mtime = norm_path.stat().st_mtime
        class_mtime = class_path.stat().st_mtime

        import beeagent_module.cases.rop_bitrix_reconciliation as br_mod

        original_build = br_mod.build_bitrix_client

        def mock_build_client(settings, logger=None):
            client = original_build(settings, logger=logger)
            original_call = client.call

            def mock_call(method, params=None):
                if method in {
                    "crm.lead.list",
                    "crm.deal.list",
                    "crm.contact.list",
                    "crm.company.list",
                }:
                    return {"result": []}
                if method == "crm.item.list":
                    return {"result": {"items": []}}
                return original_call(method, params)

            client.call = mock_call
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

        assert norm_path.stat().st_mtime == norm_mtime
        assert class_path.stat().st_mtime == class_mtime
        assert json.loads(norm_path.read_text(encoding="utf-8")) == normalized_original


class TestBitrixTsvEnrichment:
    def test_export_review_fills_bitrix_columns_when_artifact_exists(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "test-tsv-bitrix"
        run_dir.mkdir(parents=True)

        normalized = [
            {"event_id": "evt-001", "sender": "lead@example.com", "subject": "Lead"}
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.95}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

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
            normalized,
            classified,
            reconciliation_data=reconciliation_data,
        )

        assert len(tsv_rows) == 1
        row = tsv_rows[0]
        assert row["bitrix_match_status"] == "matched_lead"
        assert row["bitrix_match_quality"] == ""
        assert row["bitrix_confidence"] == "0.95"
        assert row["needs_manual_review"] == "false"
        assert row["safe_to_use_as_target"] == ""

    def test_tsv_remains_valid_when_reconciliation_missing(
        self, tmp_path: Path
    ) -> None:
        run_dir = tmp_path / "runs" / "test-tsv-norecon"
        run_dir.mkdir(parents=True)

        normalized = [
            {"event_id": "evt-001", "sender": "test@example.com", "subject": "Test"}
        ]
        classified = [
            {"event_id": "evt-001", "case_type": "new_lead", "confidence": 0.9}
        ]

        (run_dir / "normalized_events.json").write_text(
            json.dumps(normalized), encoding="utf-8"
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )

        tsv_rows = _build_review_tsv_rows(normalized, classified)

        assert len(tsv_rows) == 1
        row = tsv_rows[0]
        assert row["bitrix_match_status"] == ""
        assert row["bitrix_match_quality"] == ""
        assert row["bitrix_confidence"] == ""
        assert row["needs_manual_review"] == ""
        assert row["safe_to_use_as_target"] == ""


class TestBitrixSafety:
    def test_no_write_methods_in_allowed(self) -> None:
        for method in ALLOWED_METHODS:
            assert method.startswith("crm.")
            assert "add" not in method.split(".")
            assert "update" not in method.split(".")
            assert "delete" not in method.split(".")

    def test_no_beeagent_rop_imports_in_connector(self) -> None:
        import ast

        connector_path = (
            _PROJECT_ROOT / "src" / "beeagent_module" / "adapters" / "bitrix_client.py"
        )
        reconciliation_path = (
            _PROJECT_ROOT
            / "src"
            / "beeagent_module"
            / "cases"
            / "rop_bitrix_reconciliation.py"
        )

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

    def test_core_bitrix_reconciliation_file_removed(self) -> None:
        old_path = (
            _PROJECT_ROOT
            / "src"
            / "beeagent_module"
            / "core"
            / "bitrix_reconciliation.py"
        )
        assert not old_path.exists()


class TestBitrixCliHandler:
    def test_reconcile_bitrix_disabled_config_fails_without_completed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.setenv(
            "BITRIX_WEBHOOK_URL",
            "https://test.bitrix24.kz/rest/1/testtoken123/",
        )

        run_dir = tmp_path / "runs" / "disabled-config-run"
        run_dir.mkdir(parents=True)
        (run_dir / "normalized_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-001",
                        "sender": "a@b.com",
                        "subject": "Test",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps([{"event_id": "evt-001", "case_type": "new_lead"}]),
            encoding="utf-8",
        )

        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = False
        args = argparse.Namespace(run_id="disabled-config-run")

        with pytest.raises(Exception) as exc_info:
            handle_rop_reconcile_bitrix(
                args,
                settings=settings,
                logger=_null_logger(),
            )

        captured = capsys.readouterr()
        assert "bitrix.enabled: true" in str(exc_info.value)
        assert "completed" not in captured.out.lower()

    def test_reconcile_bitrix_missing_env_fails_without_completed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)
        monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)

        run_dir = tmp_path / "runs" / "missing-env-run"
        run_dir.mkdir(parents=True)
        (run_dir / "normalized_events.json").write_text(
            json.dumps(
                [
                    {
                        "event_id": "evt-001",
                        "sender": "a@b.com",
                        "subject": "Test",
                    }
                ]
            ),
            encoding="utf-8",
        )
        (run_dir / "classified_events.json").write_text(
            json.dumps([{"event_id": "evt-001", "case_type": "new_lead"}]),
            encoding="utf-8",
        )

        settings = _load_test_settings()
        settings["bitrix"]["enabled"] = True
        args = argparse.Namespace(run_id="missing-env-run")

        with pytest.raises(Exception) as exc_info:
            handle_rop_reconcile_bitrix(args, settings=settings, logger=_null_logger())

        captured = capsys.readouterr()
        assert "BITRIX_WEBHOOK_URL" in str(exc_info.value)
        assert "completed" not in captured.out.lower()

    def test_reconcile_bitrix_missing_run_dir_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import argparse

        import beeagent_module.core.cli as cli_module

        monkeypatch.setattr(cli_module, "get_storage_dir", lambda: tmp_path)

        settings = _load_test_settings()
        args = argparse.Namespace(run_id="nonexistent-run")

        with pytest.raises(Exception) as exc_info:
            handle_rop_reconcile_bitrix(args, settings=settings, logger=_null_logger())
        assert any(
            msg in str(exc_info.value).lower() for msg in ["not found", "failed"]
        )
