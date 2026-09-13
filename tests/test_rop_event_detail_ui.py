from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any
import pytest

from tests.beeui_console_support import (
    _build_settings,
    _client,
    _make_storage,
    _write_rop_event_detail_artifacts,
)


def _find_section_items(page: dict[str, Any], title: str) -> list[dict[str, Any]]:
    for sec in page.get("sections", []):
        if sec.get("title") == title:
            return sec.get("items", [])
    return []


def _item_by_label(items: list[dict[str, Any]], label: str) -> dict[str, Any]:
    for item in items:
        if item.get("label") == label:
            return item
    return {}


def test_rop_event_detail_html_route_returns_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-rop-detail-html")
    client = _client(storage_dir)

    response = client.get("/rop/events/evt-1?run_id=run-rop-detail-html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Event Detail" in response.text
    assert "Need welding quote" in response.text
    assert "client@example.com" in response.text
    assert "Please send pricing for welding equipment." in response.text
    assert "RAW-EML-CONTENT" not in response.text
    assert "RAW-ATTACHMENT-CONTENT" not in response.text


def test_api_rop_event_detail_route_remains_json(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-rop-detail-api")
    client = _client(storage_dir)

    response = client.get("/api/rop/events/evt-1?run_id=run-rop-detail-api")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    assert data["data"]["message"]["subject"] == "Need welding quote"
    assert data["data"]["source"] == {
        "source_id": "hotline_mailbox",
        "source_type": "mailbox_readonly",
        "source_role": "technical_aggregator",
        "source_display_name": "Welding Hotline mailbox",
        "client_id": "welding",
    }


def test_rop_event_detail_source_is_composed_into_message(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-source-message")

    page = build_rop_event_detail_page_model(
        storage_dir,
        "run-detail-source-message",
        "evt-1",
    )

    assert "Source" not in [section["title"] for section in page["sections"]]
    message = next(
        section for section in page["sections"] if section["title"] == "Message"
    )
    assert [item["label"] for item in message["items"]] == [
        "Subject",
        "Sender",
        "Source",
        "Body preview",
        "Date",
    ]
    assert message["items"][2]["value"] == "hotline_mailbox"
    body_preview = message["items"][3]
    assert body_preview["modal_trigger_label"] == "Show message"
    assert body_preview["modal_title"] == "Message"
    assert body_preview["modal_fields"] == [
        {"label": "From", "value": "client@example.com"},
        {"label": "Subject", "value": "Need welding quote"},
        {
            "label": "Message text",
            "value": "Please send pricing for welding equipment.",
            "multiline": True,
        },
        {"label": "Date", "value": ""},
    ]
    assert "Client" not in [item["label"] for item in message["items"]]
    assert "Source type" not in [item["label"] for item in message["items"]]
    assert "Source role" not in [item["label"] for item in message["items"]]

    client = _client(storage_dir)
    response_en = client.get(
        "/rop/events/evt-1?run_id=run-detail-source-message&lang=en"
    )
    response_ru = client.get(
        "/rop/events/evt-1?run_id=run-detail-source-message&lang=ru"
    )
    assert response_en.status_code == 200
    assert "Message" in response_en.text
    assert "Source" in response_en.text
    assert "Show message" in response_en.text
    assert "Message text" in response_en.text
    assert "modal-dialog-centered" in response_en.text
    assert "Send Message" not in response_en.text
    assert "Save changes" not in response_en.text
    assert response_ru.status_code == 200
    assert "Письмо" in response_ru.text
    assert "Источник" in response_ru.text
    assert "Показать письмо" in response_ru.text
    assert "Текст письма" in response_ru.text
    assert "hotline_mailbox" in response_ru.text


def test_rop_event_detail_synthetic_reason_contract_is_read_only(
    tmp_path: Path,
) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-contract")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0]["reason_code"] = "new_lead_request_signal"
    classified_path.write_text(json.dumps(classified), encoding="utf-8")
    raw_reason = "<script>provider_reason()</script>"
    adjudicator = {
        "results": [
            {
                "event_id": "evt-1",
                "ai_used": True,
                "ai_status": "manual_review_degrade",
                "ai_confidence": 0.9,
                "ai_reason": raw_reason,
                "ai_reason_code": "conflicting_business_signals",
                "ai_evidence_codes": [
                    "low_signal",
                    "not_allowed",
                    7,
                    "supplier_outreach",
                    "marketing_conflict",
                    "spam_rfq_conflict",
                ],
                "merge_reason": "ai_output_conflict_manual_review",
                "final_case_type": "new_lead",
                "final_recommended_queue": "manual_review",
                "final_correct_action": "manual_review",
            }
        ]
    }
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(adjudicator), encoding="utf-8"
    )
    final_decisions = build_final_decisions(classified, adjudicator)
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(final_decisions), encoding="utf-8"
    )
    legacy_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-legacy")
    (legacy_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_status": "manual_review_degrade",
                        "ai_reason": "legacy raw reason",
                        "merge_reason": "ai_output_conflict_manual_review",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    legacy_classified = json.loads(
        (legacy_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    legacy_adjudicator = json.loads(
        (legacy_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
    )
    legacy_final = build_final_decisions(legacy_classified, legacy_adjudicator)
    legacy_final["events"][0].pop("attention_reason_code")
    legacy_final["events"][0].pop("attention_evidence_codes")
    (legacy_dir / "rop_final_decisions.json").write_text(
        json.dumps(legacy_final), encoding="utf-8"
    )
    unknown_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-unknown")
    (unknown_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_reason_code": "<script>unknown()</script>",
                        "ai_evidence_codes": ["<script>unknown()</script>"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    unknown_final = {
        "summary": {
            "total_events": 1,
            "decision_source_counts": {"legacy": 1},
            "attention_count": 1,
        },
        "events": [
            {
                "event_id": "evt-1",
                "final_case_type": "new_lead",
                "final_case_subtype": None,
                "final_queue": "manual_review",
                "final_action": "manual_review",
                "final_decision_source": "legacy",
                "final_confidence": 0.0,
                "needs_attention": True,
                "attention_reason": "legacy raw attention",
                "attention_reason_code": "unknown_final_attention_code",
                "automation_allowed": False,
                "bitrix_write_allowed": False,
            }
        ],
    }
    (unknown_dir / "rop_final_decisions.json").write_text(
        json.dumps(unknown_final), encoding="utf-8"
    )
    empty_dir = _write_rop_event_detail_artifacts(storage_dir, "run-reason-empty")
    (empty_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_status": "manual_review_degrade",
                        "ai_reason_code": "",
                        "merge_reason": "ai_output_conflict_manual_review",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    empty_classified = json.loads(
        (empty_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    empty_adjudicator = json.loads(
        (empty_dir / "rop_ai_adjudicator_results.json").read_text(encoding="utf-8")
    )
    (empty_dir / "rop_final_decisions.json").write_text(
        json.dumps(build_final_decisions(empty_classified, empty_adjudicator)),
        encoding="utf-8",
    )
    legacy_status_dir = _write_rop_event_detail_artifacts(
        storage_dir,
        "run-reason-legacy-status",
    )
    legacy_status_adjudicator = {
        "results": [
            {
                "event_id": "evt-1",
                "ai_status": "manual_review_degrade",
                "ai_reason": "legacy status raw reason",
            }
        ]
    }
    (legacy_status_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(legacy_status_adjudicator), encoding="utf-8"
    )
    legacy_status_classified = json.loads(
        (legacy_status_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    legacy_status_final = build_final_decisions(
        legacy_status_classified,
        legacy_status_adjudicator,
    )
    legacy_status_final["events"][0].pop("attention_reason_code")
    legacy_status_final["events"][0].pop("attention_evidence_codes")
    (legacy_status_dir / "rop_final_decisions.json").write_text(
        json.dumps(legacy_status_final), encoding="utf-8"
    )
    paths = [
        run_dir / "normalized_events.json",
        run_dir / "classified_events.json",
        run_dir / "rop_ai_adjudicator_results.json",
        run_dir / "rop_final_decisions.json",
        legacy_dir / "rop_ai_adjudicator_results.json",
        legacy_dir / "rop_final_decisions.json",
        unknown_dir / "rop_ai_adjudicator_results.json",
        unknown_dir / "rop_final_decisions.json",
        empty_dir / "rop_ai_adjudicator_results.json",
        empty_dir / "rop_final_decisions.json",
        legacy_status_dir / "rop_ai_adjudicator_results.json",
        legacy_status_dir / "rop_final_decisions.json",
    ]
    before = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }
    client = _client(storage_dir)

    ru_html = client.get("/rop/events/evt-1?run_id=run-reason-contract&lang=ru")
    en_html = client.get("/rop/events/evt-1?run_id=run-reason-contract&lang=en")
    invalid_html = client.get("/rop/events/evt-1?run_id=run-reason-contract&lang=bad")
    ru_api = client.get("/api/rop/events/evt-1?run_id=run-reason-contract&lang=ru")
    legacy_api = client.get("/api/rop/events/evt-1?run_id=run-reason-legacy&lang=ru")
    legacy_api_en = client.get("/api/rop/events/evt-1?run_id=run-reason-legacy&lang=en")
    unknown_api = client.get("/api/rop/events/evt-1?run_id=run-reason-unknown&lang=ru")
    unknown_api_en = client.get(
        "/api/rop/events/evt-1?run_id=run-reason-unknown&lang=en"
    )
    empty_data = build_rop_event_detail_read_model(
        storage_dir,
        "run-reason-empty",
        "evt-1",
        lang="en",
    )
    unknown_html_ru = client.get("/rop/events/evt-1?run_id=run-reason-unknown&lang=ru")
    unknown_html_en = client.get("/rop/events/evt-1?run_id=run-reason-unknown&lang=en")
    legacy_status_ru = client.get(
        "/api/rop/events/evt-1?run_id=run-reason-legacy-status&lang=ru"
    )
    legacy_status_en = client.get(
        "/api/rop/events/evt-1?run_id=run-reason-legacy-status&lang=en"
    )
    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-reason-contract", "evt-1", lang="ru"
    )
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-reason-contract", "evt-1", lang="en"
    )
    legacy_page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-reason-legacy", "evt-1", lang="ru"
    )
    legacy_page_en = build_rop_event_detail_page_model(
        storage_dir, "run-reason-legacy", "evt-1", lang="en"
    )

    assert ru_html.status_code == 200
    assert en_html.status_code == 200
    assert invalid_html.status_code == 200
    assert "Проверка AI" in ru_html.text
    assert "AI adjudicator reason" in en_html.text
    assert "AI adjudicator reason" in invalid_html.text
    assert (
        _item_by_label(
            _find_section_items(page_ru, "Базовая классификация"), "Причина"
        )["value"]
        == "Новый лид: обнаружен сигнал запроса или RFQ"
    )
    assert (
        _item_by_label(_find_section_items(page_ru, "Проверка AI"), "Причина")["value"]
        == "Обнаружены противоречивые бизнес-сигналы"
    )
    assert (
        _item_by_label(
            _find_section_items(page_ru, "Итоговое решение"), "Причина внимания"
        )
        == {}
    )
    assert (
        _item_by_label(_find_section_items(page_en, "Basic classification"), "Reason")[
            "value"
        ]
        == "New lead: request or RFQ signal detected"
    )
    assert raw_reason not in ru_html.text
    assert "&lt;script&gt;provider_reason()&lt;/script&gt;" in ru_html.text
    data = ru_api.json()["data"]
    assert data["ai_adjudicator"]["ai_adjudicator_reason"] == raw_reason
    assert (
        data["final_decision"]["attention_reason"] == "ai_output_conflict_manual_review"
    )
    assert data["final_decision"]["attention_reason_code"] == (
        "ai_output_conflict_manual_review"
    )
    assert [
        item["code"] for item in data["ai_adjudicator"]["ai_adjudicator_evidence_codes"]
    ] == [
        "low_signal",
        "supplier_outreach",
        "marketing_conflict",
    ]
    assert not any(
        "attention reason code" in warning.lower()
        or "код причины внимания" in warning.lower()
        for warning in data["warnings"]
    )
    assert len(data["ai_adjudicator"]["ai_adjudicator_evidence_codes"]) <= 5
    assert "ai_evidence_codes exceeded maximum; truncated" in data["warnings"]
    assert "unknown ai evidence code ignored" in data["warnings"]
    assert "not_allowed" not in data["warnings"]
    assert not any(
        "ai_reason_code" in warning for warning in legacy_api.json()["data"]["warnings"]
    )
    assert not any("ai_reason_code" in warning for warning in empty_data["warnings"])
    assert empty_data["ai_adjudicator"]["ai_adjudicator_reason_display"] == (
        "AI output conflicted with signals; manual review required"
    )
    assert (
        "Старый формат итогового решения: код причины внимания отсутствует. "
        "Показано совместимое объяснение; данные не изменялись."
    ) in legacy_api.json()["data"]["warnings"]
    legacy_data = legacy_api.json()["data"]
    assert legacy_data["final_decision"]["attention_reason"] == (
        "ai_output_conflict_manual_review"
    )
    assert legacy_data["final_decision"]["attention_reason_display"] == (
        "Результат ИИ противоречит сигналам; требуется ручная проверка"
    )
    assert (
        legacy_api_en.json()["data"]["final_decision"]["attention_reason_display"]
        == "AI output conflicted with signals; manual review required"
    )
    assert (
        "Legacy final-decision format: the attention reason code is missing. "
        "A compatible explanation is shown; no data was modified."
    ) in legacy_api_en.json()["data"]["warnings"]
    assert (
        _item_by_label(
            _find_section_items(legacy_page_ru, "Итоговое решение"),
            "Причина внимания",
        )
        == {}
    )
    assert (
        _item_by_label(
            _find_section_items(legacy_page_en, "Final decision"), "Attention reason"
        )
        == {}
    )
    assert any(
        "unknown ai_reason_code" in warning
        for warning in unknown_api.json()["data"]["warnings"]
    )
    assert unknown_html_ru.status_code == 200
    assert unknown_html_en.status_code == 200
    unknown_data = unknown_api.json()["data"]
    assert unknown_data["final_decision"]["attention_reason_code"] == (
        "unknown_final_attention_code"
    )
    assert "Неизвестный код причины" in unknown_html_ru.text
    assert "Unknown reason code" in unknown_html_en.text
    assert (
        "Код причины внимания неизвестен. Показано безопасное совместимое объяснение."
    ) in unknown_data["warnings"]
    assert (
        "The attention reason code is unknown. A safe compatible explanation is shown."
    ) in unknown_api_en.json()["data"]["warnings"]
    assert "unknown attention_reason_code" not in unknown_html_ru.text
    assert "unknown attention_reason_code" not in unknown_html_en.text
    assert legacy_status_ru.status_code == 200
    assert legacy_status_en.status_code == 200
    assert (
        legacy_status_ru.json()["data"]["ai_adjudicator"][
            "ai_adjudicator_reason_display"
        ]
        == "ИИ-арбитр направил событие на ручную проверку"
    )
    assert (
        legacy_status_en.json()["data"]["ai_adjudicator"][
            "ai_adjudicator_reason_display"
        ]
        == "AI adjudicator routed the event to manual review"
    )
    assert not any(
        "ai_reason_code" in warning
        for warning in legacy_status_ru.json()["data"]["warnings"]
    )
    client.close()
    after = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }
    assert after == before


def test_rop_event_detail_ru_localizes_ui8_labels(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-ru-ui8")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_used": True,
                        "ai_status": "manual_review_degrade",
                        "ai_confidence": 0.3,
                        "ai_reason": "review needed",
                        "final_case_type": "new_lead",
                        "final_recommended_queue": "manual_review",
                        "final_correct_action": "manual_review",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get("/rop/events/evt-1?run_id=run-detail-ru-ui8&lang=ru")

    assert response.status_code == 200
    for label in (
        "Статус",
        "Уверенность",
        "Причина",
        "Тип",
        "Основа решения",
    ):
        assert label in response.text
    for label in (
        "AI арбитр использован",
        "Статус AI арбитра",
        "Уверенность AI арбитра",
        "Причина AI арбитра",
        "Предложенный AI тип",
        "Предложенная AI очередь",
        "Предложенное AI действие",
    ):
        assert label not in response.text
    assert "Причина внимания" not in response.text
    assert "Очередь" not in response.text
    assert "Итоговое действие" not in response.text
    assert "Требует внимания" not in response.text
    assert "AI adjudicator status" not in response.text
    assert "AI proposed queue" not in response.text
    assert "Attention reason" not in response.text
    client.close()


def test_rop_event_detail_shows_blacklist_override_reason_in_ru(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-blacklist")
    for artifact_name in ("normalized_events.json", "classified_events.json"):
        artifact_path = run_dir / artifact_name
        events = json.loads(artifact_path.read_text(encoding="utf-8"))
        events[0]["event_instance_id"] = "event-000001"
        artifact_path.write_text(json.dumps(events), encoding="utf-8")
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_events": 1,
                    "decision_source_counts": {"policy_override": 1},
                    "attention_count": 0,
                },
                "events": [
                    {
                        "event_id": "evt-1",
                        "event_instance_id": "event-000001",
                        "final_case_type": "irrelevant",
                        "final_case_subtype": None,
                        "final_queue": "irrelevant",
                        "final_action": "no_action",
                        "final_decision_source": "policy_override",
                        "final_confidence": 1.0,
                        "needs_attention": False,
                        "attention_reason": None,
                        "automation_allowed": False,
                        "bitrix_write_allowed": False,
                        "policy_override_reason": "sender_blacklisted",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    page = build_rop_event_detail_page_model(
        storage_dir,
        "run-detail-blacklist",
        "evt-1",
        event_instance_id="event-000001",
        lang="ru",
    )
    items = _find_section_items(page, "Итоговое решение")

    assert _item_by_label(items, "Причина изменения классификации")["value"] == (
        "Отправитель в чёрном списке"
    )


def test_rop_event_detail_without_attention_omits_attention_reason(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(
        storage_dir,
        "run-detail-no-attention",
    )
    before = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-no-attention",
        "evt-1",
        lang="ru",
    )
    page = build_rop_event_detail_page_model(
        storage_dir,
        "run-detail-no-attention",
        "evt-1",
        lang="ru",
    )
    after = {
        path: (sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert data["final_decision"]["needs_attention"] is False
    assert data["final_decision"]["attention_reason_code"] is None
    assert data["final_decision"]["attention_reason_display"] is None
    assert not any(
        "attention reason code" in warning.lower()
        or "код причины внимания" in warning.lower()
        for warning in data["warnings"]
    )
    final_items = _find_section_items(page, "Итоговое решение")
    assert _item_by_label(final_items, "Причина внимания") == {}
    assert after == before


def test_rop_event_detail_builds_deterministic_final_decision_and_evidence(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-final")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps({"results": []}), encoding="utf-8"
    )
    (run_dir / "rop_final_decisions.json").write_text(json.dumps({}), encoding="utf-8")

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-final", "evt-1")

    final_decision = data["final_decision"]
    assert final_decision["event_id"] == "evt-1"
    assert final_decision["final_decision_source"] == "deterministic"
    availability = {
        item["artifact_id"]: item["available"] for item in data["evidence_links"]
    }
    assert availability["rop_ai_adjudicator_results_json"] is True
    assert availability["rop_final_decisions_json"] is True


def test_rop_event_detail_exposes_deterministic_and_conversation_sections(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-conv")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0].update(
        {
            "deterministic_case_type": "new_lead",
            "deterministic_case_subtype": "new_lead_rfq",
            "deterministic_recommended_queue": "sales",
            "deterministic_correct_action": "review_new_lead",
            "deterministic_confidence": 0.88,
            "deterministic_reason_code": "new_lead_request_signal",
        }
    )
    classified_path.write_text(json.dumps(classified), encoding="utf-8")

    state = {
        "events": {
            "welding|hotline_mailbox|msg-a|": {
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "client_id": "welding",
                "source_id": "hotline_mailbox",
                "message_id": "msg-a",
                "in_reply_to": "",
                "references": "",
                "sender_email": "client@example.com",
                "subject": "Need welding quote",
                "case_type": "new_lead",
                "outcome": "create_lead",
                "status": "created",
                "target_entity_type": "lead",
                "target_entity_id": 1001,
                "target_provenance": "beeagent_created",
                "last_run_id": "run-detail-conv",
                "created_at_utc": "2026-08-01T10:00:00Z",
            },
            "welding|other_mailbox|msg-b|": {
                "event_id": "evt-2",
                "event_instance_id": "event-000001",
                "client_id": "welding",
                "source_id": "other_mailbox",
                "message_id": "msg-b",
                "in_reply_to": "msg-a",
                "references": "msg-a",
                "sender_email": "client@example.com",
                "subject": "Re: Need welding quote",
                "case_type": "existing_deal",
                "outcome": "attach_existing",
                "status": "attached",
                "target_entity_type": "lead",
                "target_entity_id": 1001,
                "target_provenance": "thread_resolved",
                "last_run_id": "run-other",
                "created_at_utc": "2026-08-02T10:00:00Z",
            },
        }
    }
    (storage_dir / "interfaces").mkdir(parents=True, exist_ok=True)
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-conv", "evt-1", event_instance_id="event-000001"
    )

    deterministic = data["deterministic"]
    assert deterministic["available"] is True
    assert deterministic["case_type"] == "new_lead"
    assert deterministic["recommended_queue"] == "sales"
    assert deterministic["correct_action"] == "review_new_lead"
    assert deterministic["confidence"] == 0.88
    assert deterministic["reason_code"] == "new_lead_request_signal"

    conversation = data["conversation"]
    assert conversation["available"] is True
    assert conversation["client_id"] == "welding"
    events = {item["event_id"]: item for item in conversation["events"]}
    assert events["evt-1"]["source_id"] == "hotline_mailbox"
    assert events["evt-2"]["source_id"] == "other_mailbox"
    assert events["evt-2"]["role"] == "reply"
    assert events["evt-2"]["writeback"]["outcome"] == "attach_existing"


def test_rop_event_detail_trusted_attach_projects_operational_final(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-op")
    state = {
        "events": {
            "welding|hotline_mailbox|msg-a|": {
                "event_id": "evt-1",
                "event_instance_id": "",
                "client_id": "welding",
                "source_id": "hotline_mailbox",
                "message_id": "msg-a",
                "in_reply_to": "msg-root",
                "references": "msg-root",
                "sender_email": "client@example.com",
                "subject": "Re: Need welding quote",
                "case_type": "existing_deal",
                "semantic_case_type": "new_lead",
                "outcome": "attach_existing",
                "status": "attached",
                "target_entity_type": "lead",
                "target_entity_id": 1001,
                "target_provenance": "thread_resolved",
                "last_run_id": "run-detail-op",
                "created_at_utc": "2026-08-02T10:00:00Z",
            },
        }
    }
    (storage_dir / "interfaces").mkdir(parents=True, exist_ok=True)
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    (storage_dir / "runs" / "run-detail-op" / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "bitrix_match_status": "duplicate_candidate",
                        "candidate_count": 3,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (storage_dir / "runs" / "run-detail-op" / "attachment_extraction.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "filename": "brief.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 128,
                        "storage_status": "stored",
                        "reason_code": "local_extraction_preview",
                        "analysis_status": "ok",
                    },
                    {
                        "event_id": "evt-1",
                        "filename": "scan.png",
                        "content_type": "image/png",
                        "size_bytes": 256,
                        "storage_status": "stored",
                        "reason_code": "docling_extraction_failed",
                        "analysis_status": "failed",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-op", "evt-1")

    final_decision = data["final_decision"]
    assert final_decision["final_case_type"] == "existing_deal"
    assert final_decision["semantic_case_type"] == "new_lead"
    conversation = data["conversation"]
    conv_event = next(
        item for item in conversation["events"] if item["event_id"] == "evt-1"
    )
    assert conv_event["case_type"] == "existing_deal"
    assert conv_event["semantic_case_type"] == "new_lead"
    assert data["bitrix"]["bitrix_status"] == "matched_lead"
    assert data["bitrix"]["reconciliation_status"] == "duplicate_candidate"
    assert data["bitrix"]["entity_type"] == "lead"
    assert data["bitrix"]["entity_id"] == 1001
    page = build_rop_event_detail_page_model(storage_dir, "run-detail-op", "evt-1")
    bitrix_section = next(
        section
        for section in page["sections"]
        if section.get("title") == "Bitrix evidence"
    )
    bitrix_labels = [item["label"] for item in bitrix_section["items"]]
    assert "Match quality" not in bitrix_labels
    assert "Candidate count" in bitrix_labels
    assert "Entity type" in bitrix_labels
    assert "Entity ID" in bitrix_labels
    timeline_section = next(
        section
        for section in page["sections"]
        if section.get("title") == "Conversation timeline"
    )
    assert [column["key"] for column in timeline_section["columns"][:2]] == [
        "subject",
        "sender",
    ]
    assert timeline_section["columns"][0]["cell"] == "link"
    assert {column["key"] for column in timeline_section["columns"]}.isdisjoint(
        {"source_id", "run_id"}
    )
    timeline_subject = timeline_section["rows"][0]["subject"]
    assert timeline_subject["label"] == "Re: Need welding quote"
    assert timeline_subject["href"] == "/rop/events/evt-1?run_id=run-detail-op"
    page_ru = build_rop_event_detail_page_model(
        storage_dir,
        "run-detail-op",
        "evt-1",
        lang="ru",
    )
    timeline_ru = next(
        section
        for section in page_ru["sections"]
        if section.get("title") == "Хронология переписки"
    )
    assert timeline_ru["rows"][0]["role"] == "Ответ"
    attachments_ru = next(
        section
        for section in page_ru["sections"]
        if section.get("title") == "Прикреплённые вложения"
    )
    assert [column["label"] for column in attachments_ru["columns"]] == [
        "Имя файла",
        "Тип содержимого",
        "Размер",
        "Статус хранения",
        "Результат обработки",
        "Статус анализа",
    ]
    attachment_row = attachments_ru["rows"][0]
    assert attachment_row["content_type"] == "Документ PDF"
    assert attachment_row["storage_status"] == "Сохранено"
    assert attachment_row["reason_code"] == "Текст извлечён локально"
    assert attachment_row["analysis_status"] == "Обработано"
    failed_attachment_row = attachments_ru["rows"][1]
    assert failed_attachment_row["analysis_status"] == "Ошибка обработки"


def test_rop_event_detail_independent_event_keeps_semantic_final(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-ind")

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-ind", "evt-1")

    final_decision = data["final_decision"]
    assert final_decision["final_case_type"] == "new_lead"
    assert "semantic_case_type" not in final_decision


def test_rop_event_detail_deterministic_shows_original_not_current(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-det-split")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0]["case_type"] = "existing_deal"
    classified[0]["recommended_queue"] = "procurement"
    classified[0]["correct_action"] = "check_bitrix"
    classified[0]["reason_code"] = "post_ai_reason"
    classified[0].update(
        {
            "deterministic_case_type": "new_lead",
            "deterministic_case_subtype": "new_lead_rfq",
            "deterministic_recommended_queue": "sales",
            "deterministic_correct_action": "review_new_lead",
            "deterministic_confidence": 0.9,
            "deterministic_reason_code": "new_lead_request_signal",
        }
    )
    classified_path.write_text(json.dumps(classified), encoding="utf-8")

    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-det-split", "evt-1"
    )
    deterministic = data["deterministic"]
    assert deterministic["available"] is True
    assert deterministic["case_type"] == "new_lead"
    assert deterministic["recommended_queue"] == "sales"
    assert deterministic["correct_action"] == "review_new_lead"
    assert deterministic["reason_code"] == "new_lead_request_signal"
    assert deterministic["case_type"] != "existing_deal"
    assert deterministic["recommended_queue"] != "procurement"
    assert deterministic["correct_action"] != "check_bitrix"


def test_rop_event_detail_without_deterministic_evidence_is_not_available(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-no-det")
    data = build_rop_event_detail_read_model(storage_dir, "run-detail-no-det", "evt-1")
    deterministic = data["deterministic"]
    assert deterministic == {"available": False}
    assert "case_type" not in deterministic
    assert "recommended_queue" not in deterministic
    assert "correct_action" not in deterministic
    assert "reason_code" not in deterministic


def test_rop_event_detail_deterministic_ai_and_final_are_separate(
    tmp_path: Path,
) -> None:
    from beeagent_module.core.rop_final_decision import build_final_decisions
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-det-ai-final")
    classified_path = run_dir / "classified_events.json"
    classified = json.loads(classified_path.read_text(encoding="utf-8"))
    classified[0]["event_instance_id"] = "event-000001"
    classified[0].update(
        {
            "deterministic_case_type": "new_lead",
            "deterministic_case_subtype": "new_lead_rfq",
            "deterministic_recommended_queue": "sales",
            "deterministic_correct_action": "review_new_lead",
            "deterministic_confidence": 0.7,
            "deterministic_reason_code": "new_lead_request_signal",
        }
    )
    classified_path.write_text(json.dumps(classified), encoding="utf-8")

    adjudicator = {
        "results": [
            {
                "event_id": "evt-1",
                "event_instance_id": "event-000001",
                "ai_used": True,
                "ai_status": "ok",
                "ai_confidence": 0.92,
                "ai_reason": "AI proposal reason",
                "ai_reason_code": "customer_request_detected",
                "ai_evidence_codes": ["low_signal"],
                "merge_reason": "validated_ai_adjudicator_output",
                "final_case_type": "new_lead",
                "final_recommended_queue": "sales",
                "final_correct_action": "review_new_lead",
            }
        ]
    }
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(adjudicator), encoding="utf-8"
    )
    final_decisions = build_final_decisions(classified, adjudicator)
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(final_decisions), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-det-ai-final",
        "evt-1",
        event_instance_id="event-000001",
    )
    deterministic = data["deterministic"]
    ai_adjudicator = data["ai_adjudicator"]
    final_decision = data["final_decision"]
    assert deterministic["available"] is True
    assert deterministic["case_type"] == "new_lead"
    assert ai_adjudicator["ai_adjudicator_used"] is True
    assert ai_adjudicator["ai_adjudicator_status"] == "ok"
    assert final_decision["final_case_type"] == "new_lead"
    assert final_decision["final_decision_source"] == "ai_adjudicator"


def test_rop_event_detail_new_lead_and_bitrix_candidate_are_distinct(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-dup-cand")
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "bitrix_match_status": "duplicate_candidate",
                        "bitrix_match_quality": "duplicate",
                        "candidate_count": 2,
                        "safe_to_use_as_target": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-dup-cand",
        "evt-1",
        event_instance_id="",
    )
    final_decision = data["final_decision"]
    bitrix = data["bitrix"]
    assert final_decision["final_case_type"] == "new_lead"
    assert bitrix["available"] is True
    assert bitrix["bitrix_status"] == "duplicate_candidate"
    assert bitrix["candidate_count"] == 2
    assert bitrix["bitrix_status"] != final_decision["final_case_type"]


def test_rop_event_detail_exposes_recipient_routing_section(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-routing")
    (run_dir / "rop_recipient_routing.json").write_text(
        json.dumps(
            {
                "run_id": "run-detail-routing",
                "status": "ok",
                "read_only": True,
                "draft_only": True,
                "directory": {"status": "loaded", "reason": None},
                "items": [
                    {
                        "event_id": "evt-1",
                        "event_instance_id": "event-000001",
                        "source_id": "hotline_mailbox",
                        "recipient": "boss@welding.kz",
                        "recipient_candidates": ["boss@welding.kz"],
                        "recipient_evidence_source": "to",
                        "recipient_status": "resolved",
                        "responsible": {
                            "status": "matched",
                            "user_id": 12,
                            "name": "Ivan Petrov",
                            "email": "boss@welding.kz",
                            "reason": None,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-routing", "evt-1")
    routing = data["recipient_routing"]
    assert routing["available"] is True
    assert routing["recipient"] == "boss@welding.kz"
    assert routing["recipient_evidence_source"] == "to"
    assert routing["recipient_status"] == "resolved"
    assert routing["proposed_responsible_user_id"] == 12
    assert routing["proposed_responsible_name"] == "Ivan Petrov"
    assert routing["responsible_status"] == "matched"
    availability = {
        item["artifact_id"]: item["available"] for item in data["evidence_links"]
    }
    assert availability["rop_recipient_routing_json"] is True

    page = build_rop_event_detail_page_model(storage_dir, "run-detail-routing", "evt-1")
    section_titles = [section.get("title") for section in page["sections"]]
    assert "Recipient routing" in section_titles
    assert section_titles.index("Recipient routing") == (
        section_titles.index("Bitrix evidence") + 1
    )
    routing_section = next(
        section
        for section in page["sections"]
        if section.get("title") == "Recipient routing"
    )
    assert [item["label"] for item in routing_section["items"]] == [
        "Recipient",
        "Responsible",
        "Responsible status",
    ]
    assert routing_section["items"][-1]["value"] == "Found"
    page_ru = build_rop_event_detail_page_model(
        storage_dir,
        "run-detail-routing",
        "evt-1",
        lang="ru",
    )
    routing_section_ru = next(
        section
        for section in page_ru["sections"]
        if section.get("title") == "Маршрутизация получателя"
    )
    assert [item["label"] for item in routing_section_ru["items"]] == [
        "Получатель",
        "Ответственный",
        "Статус ответственного",
    ]
    assert routing_section_ru["items"][-1]["value"] == "Найден"


def test_rop_event_detail_message_body_uses_modal_text(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-message-modal")

    page = build_rop_event_detail_page_model(
        storage_dir, "run-detail-message-modal", "evt-1"
    )
    message_section = next(
        section for section in page["sections"] if section.get("title") == "Message"
    )
    assert [item["label"] for item in message_section["items"]] == [
        "Subject",
        "Sender",
        "Source",
        "Body preview",
        "Date",
    ]
    body_preview = next(
        item for item in message_section["items"] if item["label"] == "Body preview"
    )
    assert body_preview["variant"] == "modal_text"


def test_rop_event_detail_recipient_routing_absent_is_safe(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-detail-no-routing")
    data = build_rop_event_detail_read_model(
        storage_dir, "run-detail-no-routing", "evt-1"
    )
    assert data["recipient_routing"]["available"] is False


def test_event_detail_joins_occurrence_evidence_by_event_instance_id(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-occurrence")
    event_id = "evt-shared"
    instances = ("event-000001", "event-000002")
    (run_dir / "normalized_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": event_id,
                    "event_instance_id": instance_id,
                    "source_id": "hotline_mailbox",
                    "subject": instance_id,
                }
                for instance_id in instances
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(
            [
                {
                    "event_id": event_id,
                    "event_instance_id": instance_id,
                    "case_type": "new_lead",
                }
                for instance_id in instances
            ]
        ),
        encoding="utf-8",
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": event_id,
                        "event_instance_id": instance_id,
                        "bitrix_match_status": f"matched_{index}",
                    }
                    for index, instance_id in enumerate(instances, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "rop_recipient_routing.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": event_id,
                        "event_instance_id": instance_id,
                        "recipient": f"recipient{index}@welding.kz",
                        "recipient_status": "resolved",
                        "responsible": {
                            "status": "matched",
                            "user_id": index,
                        },
                    }
                    for index, instance_id in enumerate(instances, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )

    data = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-occurrence",
        event_id,
        event_instance_id="event-000002",
    )

    assert data["bitrix"]["bitrix_status"] == "matched_2"
    assert data["recipient_routing"]["recipient"] == "recipient2@welding.kz"
    assert data["recipient_routing"]["proposed_responsible_user_id"] == 2


def test_rop_event_detail_exposes_duplicate_evidence(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-dup")
    classified = [
        {
            "event_id": "evt-1",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "client@example.com",
            "subject": "Need welding quote",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.99,
            "reason_code": "duplicate_candidate_confirmed",
            "recommended_queue": "manual_review",
            "correct_action": "review",
            "should_rop_see": True,
            "is_fallback": False,
            "base_classification": {
                "case_type": "new_lead",
                "priority": "high",
                "reason_code": "new_lead_request_signal",
                "confidence": 0.9,
                "reasoning": "base",
                "is_fallback": False,
                "case_subtype": "rfq",
                "recommended_queue": "sales",
                "should_rop_see": True,
                "correct_action": "review_new_lead",
            },
            "duplicate": {
                "is_duplicate": True,
                "confidence": 0.99,
                "reason_code": "exact_email_body_match",
                "reason_path": ["sender_email_exact", "body_exact"],
                "reasoning": "exact duplicate matched",
                "candidate": {
                    "existing_lead_id": "evt-original",
                    "event_id": "evt-original",
                    "similarity_score": 0.99,
                    "matched_fields": ["sender_email", "body"],
                    "reason_code": "exact_email_body_match",
                    "reason_path": ["sender_email_exact", "body_exact"],
                    "reasoning": "exact duplicate matched",
                },
                "candidates": [],
                "is_fallback": False,
            },
        }
    ]
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )

    data = build_rop_event_detail_read_model(storage_dir, "run-detail-dup", "evt-1")

    classification = data["classification"]
    assert classification["case_type"] == "duplicate"
    assert classification["base_case_type"] == "new_lead"
    duplicate = classification["duplicate"]
    assert duplicate["is_duplicate"] is True
    assert duplicate["candidate_event_id"] == "evt-original"
    assert duplicate["existing_lead_id"] == "evt-original"
    assert duplicate["confidence"] == 0.99
    assert duplicate["reason_code"] == "exact_email_body_match"
    assert duplicate["reason_path"] == ["sender_email_exact", "body_exact"]
    assert duplicate["matched_fields"] == ["sender_email", "body"]
    assert duplicate["similarity_score"] == 0.99
    assert classification["reason_display"] is not None

    page = build_rop_event_detail_page_model(storage_dir, "run-detail-dup", "evt-1")
    items = _find_section_items(page, "Basic classification")
    assert _item_by_label(items, "Base case type")["value"] == "New lead"
    assert _item_by_label(items, "Duplicate candidate event")["value"] == "evt-original"
    assert _item_by_label(items, "Duplicate confidence")["value"] == 0.99

    client = _client(storage_dir)
    response = client.get("/rop/events/evt-1?run_id=run-detail-dup")

    assert response.status_code == 200
    assert "evt-original" in response.text
    assert "exact duplicate matched" in response.text


def test_final_decision_get_routes_do_not_change_storage(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-final-read-only")
    before = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    client = _client(storage_dir)

    dashboard = client.get("/api/rop/dashboard?run_id=run-final-read-only")
    detail = client.get("/api/rop/events/evt-1?run_id=run-final-read-only")

    assert dashboard.status_code == 200
    assert detail.status_code == 200
    after = {
        path.relative_to(run_dir): path.read_bytes()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not (run_dir / "rop_final_decisions.json").exists()


def test_rop_event_detail_sections_and_back_link_round_trip(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-state")
    (run_dir / "mail_thread_context.json").write_text(
        json.dumps({"contexts": [{"event_id": "evt-1", "thread_id": "thread-1"}]}),
        encoding="utf-8",
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps({"items": [{"event_id": "evt-1", "status": "matched"}]}),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get(
        "/rop/events/evt-1?run_id=run-detail-state&period=all&lang=ru&"
        "priority=high&page=2&page_size=50&sort=sender&order=asc"
    )

    assert response.status_code == 200
    assert "Thread context" not in response.text
    assert "Контекст цепочки" not in response.text
    assert (
        "Bitrix evidence" in response.text
        or "Доказательства из Битрикс" in response.text
    )
    assert "Action draft" not in response.text
    assert "Черновик действия" not in response.text
    assert "Evidence artifacts" not in response.text
    assert "Артефакты доказательств" not in response.text
    assert "run_id=run-detail-state" in response.text
    assert "page_size=50" in response.text


def test_event_detail_routes_return_client_error_statuses(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-event-errors")
    client = _client(storage_dir)

    invalid_query = client.get("/rop/events/evt-1?run_id=run-event-errors&sort=sender")
    invalid_run = client.get("/rop/events/evt-1?run_id=../outside")
    missing = client.get("/rop/events/missing?run_id=run-event-errors")
    valid = client.get("/rop/events/evt-1?run_id=run-event-errors")
    api_valid = client.get("/api/rop/events/evt-1?run_id=run-event-errors")
    api_invalid_run = client.get("/api/rop/events/evt-1?run_id=../outside")
    api_invalid_sort = client.get(
        "/api/rop/events/evt-1?run_id=run-event-errors&sort=sender"
    )
    api_missing = client.get("/api/rop/events/missing?run_id=run-event-errors")

    assert invalid_query.status_code == 400
    assert invalid_run.status_code == 400
    assert missing.status_code == 404
    assert valid.status_code == 200
    assert api_valid.status_code == 200
    assert api_invalid_run.status_code == 400
    assert api_invalid_sort.status_code == 400
    assert api_missing.status_code == 404
    assert "Traceback" not in invalid_query.text
    assert str(storage_dir) not in invalid_query.text
    assert "RAW-EML-CONTENT" not in invalid_query.text


@pytest.mark.parametrize(
    ("lang", "section_title", "hidden_label"),
    [
        ("en", "Basic classification", "Should ROP see"),
        ("ru", "Базовая классификация", "Должен увидеть РОП"),
    ],
)
def test_rop_event_detail_hides_internal_should_rop_see_field(
    tmp_path: Path,
    lang: str,
    section_title: str,
    hidden_label: str,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-should-rop-see-hidden")

    page = build_rop_event_detail_page_model(
        storage_dir,
        "run-should-rop-see-hidden",
        "evt-1",
        lang=lang,
    )

    items = _find_section_items(page, section_title)
    assert hidden_label not in [item["label"] for item in items]


def test_rop_event_detail_page_model_hides_ai_assist_block(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-ai-hidden")
    (run_dir / "rop_ai_assist_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_assist_status": "ok",
                        "ai_assist_used": True,
                        "ai_assist_confidence": 0.95,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-ai-hidden", "evt-1", lang="en"
    )
    assert "AI Assist" not in [section["title"] for section in page["sections"]]


def test_rop_event_detail_page_model_adjudicator_used_none(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-adj-none")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "event_id": "evt-1",
                        "ai_used": None,
                        "ai_status": "ok",
                        "final_case_type": "new_lead",
                        "final_recommended_queue": "",
                        "final_correct_action": "",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-adj-none", "evt-1", lang="en"
    )
    adj_items = _find_section_items(page, "AI review")
    assert _item_by_label(adj_items, "AI adjudicator status")["value"] == (
        "AI review completed"
    )
    assert "AI adjudicator used" not in [item["label"] for item in adj_items]


def test_rop_event_detail_page_model_priority_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    for priority, expected_tone in [
        ("low", "muted"),
        ("medium", "warning"),
        ("high", "danger"),
        ("critical", "danger"),
        ("unknown_val", "muted"),
    ]:
        run_id = f"run-prio-{priority}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        classified[0]["priority"] = priority
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        cls_items = _find_section_items(page, "Basic classification")
        prio_item = _item_by_label(cls_items, "Priority")
        assert prio_item["tone"] == expected_tone, (
            f"priority={priority!r} expected tone={expected_tone!r} "
            f"got={prio_item['tone']!r}"
        )
        assert prio_item["variant"] == "badge"


def test_rop_event_detail_page_model_adjudicator_status_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    test_cases = [
        ("ok", "success", "Проверка AI завершена"),
        ("not_eligible", "muted", "Проверка AI не требуется"),
        ("low_confidence_preserve", "warning", "Низкая уверенность AI"),
        ("manual_review_degrade", "warning", "Требуется ручная проверка"),
        ("deterministic_preserved", "warning", "Сохранена базовая классификация"),
        ("duplicate_unresolved", "warning", "Дубликат требует проверки"),
        ("degraded", "danger", "AI недоступен"),
        ("invalid", "danger", "Некорректный ответ AI"),
        ("invalid_output", "danger", "Некорректный ответ AI"),
        ("provider_unavailable", "danger", "AI недоступен"),
        ("module_contract_unavailable", "danger", "AI недоступен"),
        ("unknown_status", "default", "unknown_status"),
        ("", "default", ""),
    ]
    for status, expected_tone, expected_ru_label in test_cases:
        run_id = f"run-adj-status-{status.replace('_', '-')}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        (run_dir / "rop_ai_adjudicator_results.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "event_id": "evt-1",
                            "ai_used": True,
                            "ai_status": status,
                            "ai_confidence": 0.5,
                            "ai_reason": "test",
                            "final_case_type": "new_lead",
                            "final_recommended_queue": "manual_review",
                            "final_correct_action": "manual_review",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        adj_items = _find_section_items(page, "AI review")
        status_item = _item_by_label(adj_items, "AI adjudicator status")
        assert status_item["tone"] == expected_tone, (
            f"status={status!r} expected tone={expected_tone!r} "
            f"got={status_item['tone']!r}"
        )
        assert status_item["variant"] == "badge"
        page_ru = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="ru"
        )
        adj_items_ru = _find_section_items(page_ru, "Проверка AI")
        assert _item_by_label(adj_items_ru, "Статус")["value"] == expected_ru_label


def test_rop_event_detail_page_model_hides_queue_and_action_fields(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    for action in ["manual_review", "ignore", "high_priority", "sales", ""]:
        run_id = f"run-qa-{action.replace('_', '-')}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        classified = json.loads(
            (run_dir / "classified_events.json").read_text(encoding="utf-8")
        )
        classified[0]["correct_action"] = action
        classified[0]["recommended_queue"] = action
        classified[0]["deterministic_correct_action"] = action
        classified[0]["deterministic_recommended_queue"] = action
        (run_dir / "classified_events.json").write_text(
            json.dumps(classified), encoding="utf-8"
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        cls_items = _find_section_items(page, "Basic classification")
        labels = [item["label"] for item in cls_items]
        assert "Recommended action" not in labels
        assert "Recommended queue" not in labels


def test_rop_event_detail_page_model_recommended_action_label(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-rec-act-label")
    page_en = build_rop_event_detail_page_model(
        storage_dir, "run-rec-act-label", "evt-1", lang="en"
    )
    cls_items_en = _find_section_items(page_en, "Basic classification")
    labels_en = [i["label"] for i in cls_items_en]
    assert "Recommended action" not in labels_en
    assert "Recommended queue" not in labels_en
    assert "Correct action" not in labels_en

    page_ru = build_rop_event_detail_page_model(
        storage_dir, "run-rec-act-label", "evt-1", lang="ru"
    )
    cls_items_ru = _find_section_items(page_ru, t("Basic classification", "ru"))
    labels_ru = [i["label"] for i in cls_items_ru]
    assert "Рекомендуемое действие" not in labels_ru
    assert "Рекомендуемая очередь" not in labels_ru
    assert "Верное действие" not in labels_ru


def test_rop_event_detail_page_model_final_decision_badge_tones(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-fd-tones")
    (run_dir / "rop_ai_adjudicator_results.json").write_text(
        json.dumps({"results": []}), encoding="utf-8"
    )
    (run_dir / "rop_final_decisions.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_events": 1,
                    "decision_source_counts": {"ai_adjudicator": 1},
                    "attention_count": 1,
                },
                "events": [
                    {
                        "event_id": "evt-1",
                        "final_case_type": "new_lead",
                        "final_case_subtype": None,
                        "final_queue": "manual_review",
                        "final_action": "manual_review",
                        "final_decision_source": "ai_adjudicator",
                        "final_confidence": 0.85,
                        "needs_attention": True,
                        "attention_reason": "conflict",
                        "automation_allowed": False,
                        "bitrix_write_allowed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-fd-tones", "evt-1", lang="en"
    )
    fd_items = _find_section_items(page, "Final decision")
    labels = [item["label"] for item in fd_items]
    assert "Automation allowed" not in labels
    assert "Bitrix write allowed" not in labels
    assert "Final action" not in labels
    assert "Needs attention" not in labels

    fd_type = _item_by_label(fd_items, "Final case type")
    assert fd_type["variant"] == "badge"
    assert fd_type["tone"] == "default"

    basis = _item_by_label(fd_items, "Decision basis")
    assert basis["value"] == "AI"
    assert basis["variant"] == "badge"
    assert [item["label"] for item in fd_items[:3]] == [
        "Final case type",
        "Decision basis",
        "Final confidence",
    ]

    assert "Final queue" not in labels

    assert "Decision source" not in labels


def test_rop_event_detail_page_model_adjudicator_used_tone(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    for used, expected_tone in [(True, "default"), (False, "muted")]:
        run_id = f"run-adj-used-{used}"
        run_dir = _write_rop_event_detail_artifacts(storage_dir, run_id)
        (run_dir / "rop_ai_adjudicator_results.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "event_id": "evt-1",
                            "ai_used": used,
                            "ai_status": "ok",
                            "ai_confidence": 0.5,
                            "ai_reason": "test",
                            "final_case_type": "new_lead",
                            "final_recommended_queue": "manual_review",
                            "final_correct_action": "manual_review",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        page = build_rop_event_detail_page_model(
            storage_dir, run_id, "evt-1", lang="en"
        )
        adj_items = _find_section_items(page, "AI review")
        labels = [item["label"] for item in adj_items]
        assert ("AI proposed case type" in labels) is used
        if used:
            assert labels[:4] == [
                "AI proposed case type",
                "AI adjudicator status",
                "AI adjudicator reason",
                "AI adjudicator confidence",
            ]


def test_rop_event_detail_page_model_case_type_default_badge(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-ct-badge")
    page = build_rop_event_detail_page_model(
        storage_dir, "run-ct-badge", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Basic classification")
    ct = _item_by_label(cls_items, "Case type")
    assert ct["variant"] == "badge"
    assert ct["tone"] == "default"
    assert [item["label"] for item in cls_items[:5]] == [
        "Case type",
        "Subtype",
        "Reason",
        "Confidence",
        "Priority",
    ]


def test_rop_event_detail_api_booleans_remain_raw(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_rop_event_detail_artifacts(storage_dir, "run-api-bool")
    client = _client(storage_dir)

    response = client.get("/api/rop/events/evt-1?run_id=run-api-bool")

    assert response.status_code == 200
    data = response.json()["data"]
    cls = data["classification"]
    assert cls["should_rop_see"] is True
    assert cls["correct_action"] == "review"
    assert "recommended_queue" in cls
    assert "Recommended action" not in json.dumps(data)


def test_rop_event_detail_page_model_unknown_values_degrades_safely(
    tmp_path: Path,
) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-unknown-safe")
    classified = json.loads(
        (run_dir / "classified_events.json").read_text(encoding="utf-8")
    )
    classified[0]["priority"] = "bogus_value"
    classified[0]["correct_action"] = "bogus_action"
    classified[0]["recommended_queue"] = "bogus_queue"
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-unknown-safe", "evt-1", lang="en"
    )
    cls_items = _find_section_items(page, "Basic classification")
    prio = _item_by_label(cls_items, "Priority")
    assert prio["tone"] == "muted"
    assert prio["variant"] == "badge"
    labels = [item["label"] for item in cls_items]
    assert "Recommended queue" not in labels
    assert "Recommended action" not in labels


def test_event_detail_uses_canonical_date_and_bitrix_status_fields(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-canonical-detail")
    normalized = json.loads(
        (run_dir / "normalized_events.json").read_text(encoding="utf-8")
    )
    normalized[0]["received_at"] = "2026-01-15T14:30:00Z"
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "bitrix_match_status": "matched_lead",
                        "bitrix_entity_type": "lead",
                        "bitrix_entity_id": 199324,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    client = _client(storage_dir)

    response = client.get("/rop/events/evt-1?run_id=run-canonical-detail")

    assert response.status_code == 200
    assert "15.01.2026, 14:30" in response.text
    assert "Matched in Bitrix" in response.text
    assert "Entity type" in response.text
    assert "199324" in response.text
    assert 'href="/rop/bitrix/lead/199324?run_id=run-canonical-detail"' in response.text


def test_rop_bitrix_entity_redirect_uses_configured_portal(tmp_path: Path) -> None:
    settings = _build_settings()
    settings["bitrix"] = {"embedded_app": {"portal_origin": "https://my.welding.kz"}}
    client = _client(_make_storage(tmp_path), settings)

    response = client.get("/rop/bitrix/lead/199324", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://my.welding.kz/crm/lead/details/199324/"
    )


@pytest.mark.parametrize(
    ("writeback_status", "attachment_status", "remote_entity_id", "label"),
    [
        ("created", "not_required", 200001, "Lead created in Bitrix"),
        ("recovered", "failed", 200002, "Lead recovered in Bitrix"),
    ],
)
def test_event_detail_uses_confirmed_create_lead_from_writeback(
    tmp_path: Path,
    writeback_status: str,
    attachment_status: str,
    remote_entity_id: int,
    label: str,
) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(
        storage_dir, "run-writeback-entity-fallback"
    )
    (run_dir / "bitrix_reconciliation.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "event_id": "evt-1",
                        "bitrix_match_status": "not_found",
                        "bitrix_entity_type": "lead",
                        "bitrix_entity_id": 199324,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(
            {
                "events": {
                    "evt-1": {
                        "event_id": "evt-1",
                        "last_run_id": "run-writeback-entity-fallback",
                        "source_id": "hotline_mailbox",
                        "outcome": "create_lead",
                        "status": writeback_status,
                        "remote_entity_id": remote_entity_id,
                        "email_attachment_status": attachment_status,
                        "target_entity_type": "",
                        "target_entity_id": None,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_page_model,
        build_rop_event_detail_read_model,
    )

    detail = build_rop_event_detail_read_model(
        storage_dir, "run-writeback-entity-fallback", "evt-1"
    )
    page = build_rop_event_detail_page_model(
        storage_dir, "run-writeback-entity-fallback", "evt-1"
    )

    assert detail["bitrix"]["bitrix_status"] == (
        "lead_recovered" if writeback_status == "recovered" else "lead_created"
    )
    assert detail["bitrix"]["entity_type"] == "lead"
    assert detail["bitrix"]["entity_id"] == remote_entity_id
    assert (
        label
        == _item_by_label(
            _find_section_items(page, "Bitrix evidence"), "Bitrix status"
        )["value"]
    )
    assert (
        _item_by_label(_find_section_items(page, "Bitrix evidence"), "Entity ID")[
            "href"
        ]
        == f"/rop/bitrix/lead/{remote_entity_id}"
    )


def test_event_detail_attachments_selected_by_event_instance_id(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.rop_event_detail import (
        build_rop_event_detail_read_model,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_rop_event_detail_artifacts(storage_dir, "run-detail-att-inst")
    event_id = "evt-att-inst"
    normalized = [
        {
            "event_id": event_id,
            "event_instance_id": "event-000001",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": "Occurrence 1",
            "body_preview": "Need welding wire quote",
            "received_at": "2026-08-01T10:00:00Z",
            "attachments": [
                {
                    "filename": "first.txt",
                    "content_type": "text/plain",
                    "size_bytes": 32,
                }
            ],
        },
        {
            "event_id": event_id,
            "event_instance_id": "event-000002",
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": "Occurrence 2",
            "body_preview": "Need welding wire quote",
            "received_at": "2026-08-02T10:00:00Z",
            "attachments": [
                {
                    "filename": "second.txt",
                    "content_type": "text/plain",
                    "size_bytes": 32,
                }
            ],
        },
    ]
    classified = [
        {
            "event_id": event_id,
            "event_instance_id": item["event_instance_id"],
            "source_id": "hotline_mailbox",
            "client_id": "welding",
            "sender": "buyer@example.com",
            "subject": item["subject"],
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.99,
            "reason_code": "duplicate_candidate_confirmed",
            "is_fallback": False,
            "base_classification": {"case_type": "new_lead"},
            "duplicate": {
                "is_duplicate": True,
                "confidence": 0.99,
                "reason_code": "exact_message_id_match",
                "candidate": {"event_id": event_id},
            },
        }
        for item in normalized
    ]
    attachment_extraction = {
        "run_id": "run-detail-att-inst",
        "status": "ok",
        "aggregate": {
            "event_count": 2,
            "attachment_count": 2,
            "preview_available_count": 2,
            "metadata_only_count": 0,
            "refused_count": 0,
            "unsupported_count": 0,
            "failed_count": 0,
        },
        "items": [
            {
                "event_id": event_id,
                "event_instance_id": "event-000001",
                "source_id": "hotline_mailbox",
                "attachment_id": "evt-att-inst-att-0",
                "filename": "first.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "text_preview": "first preview",
            },
            {
                "event_id": event_id,
                "event_instance_id": "event-000002",
                "source_id": "hotline_mailbox",
                "attachment_id": "evt-att-inst-att-1",
                "filename": "second.txt",
                "extraction_status": "preview",
                "preview_available": True,
                "text_preview": "second preview",
            },
        ],
    }
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified), encoding="utf-8"
    )
    (run_dir / "attachment_extraction.json").write_text(
        json.dumps(attachment_extraction), encoding="utf-8"
    )

    data_first = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-att-inst",
        event_id,
        event_instance_id="event-000001",
    )
    data_second = build_rop_event_detail_read_model(
        storage_dir,
        "run-detail-att-inst",
        event_id,
        event_instance_id="event-000002",
    )

    assert [att["filename"] for att in data_first["attachments"]] == ["first.txt"]
    assert [att["filename"] for att in data_second["attachments"]] == ["second.txt"]

    client = _client(storage_dir)
    response = client.get(
        f"/api/rop/events/{event_id}?run_id=run-detail-att-inst&event_instance_id=event-000001"
    )
    assert response.status_code == 200
    assert [att["filename"] for att in response.json()["data"]["attachments"]] == [
        "first.txt"
    ]
    response = client.get(
        f"/api/rop/events/{event_id}?run_id=run-detail-att-inst&event_instance_id=event-000002"
    )
    assert response.status_code == 200
    assert [att["filename"] for att in response.json()["data"]["attachments"]] == [
        "second.txt"
    ]
