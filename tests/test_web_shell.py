from __future__ import annotations

import json
import logging
from pathlib import Path

from beeagent_module.web.app import start_web_mode
from beeagent_module.web.routes import handle_request


# Тест: чек рендеринга страниц, обработки данных и безопасности
def _logger() -> logging.Logger:
    logger = logging.getLogger("test_web_shell")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Создание тестовых данных и проверки рендеринга страниц веб-интерфейса
def _make_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "storage"
    (storage_dir / "runs").mkdir(parents=True)
    (storage_dir / "interfaces").mkdir(parents=True)
    return storage_dir


# Создание тестовых артефактов выполнения и проверки рендеринга страниц веб-интерфейса
def _write_run_artifacts(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    module_dir = run_dir / "module-beeagent-rop"
    module_dir.mkdir(parents=True)

    operator_summary = {
        "run_id": run_id,
        "status": "ok",
        "summary": "batch completed",
        "source": {
            "source_id": "hotline_mailbox",
            "source_type": "mailbox_readonly",
            "loaded_item_count": 3,
            "period": "2026-05",
        },
        "classification": {
            "normalized_count": 3,
            "classified_count": 3,
            "classification_failed_count": 0,
        },
    }

    source_diagnostics = {
        "status": "ok",
        "processed_count": 3,
        "reason": None,
    }

    intake_metadata = {
        "source_id": "hotline_mailbox",
        "source_type": "mailbox_readonly",
        "loaded_item_count": 3,
        "items_max": 20,
    }

    normalized_events = [
        {
            "event_id": "evt-1",
            "sender": "first@example.com",
            "subject": "Need price",
            "body_preview": "Need welding consumables",
            "attachments": [
                {
                    "filename": "brief.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 1024,
                    "content": "ATTACHMENT_RAW_CONTENT_SHOULD_NOT_BE_RENDERED",
                },
                {
                    "filename": "original.eml",
                    "content_type": "message/rfc822",
                    "size_bytes": 2048,
                    "content": "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED",
                }
            ],
            "raw_eml": "RAW-EML-CONTENT-SHOULD-NOT-BE-RENDERED",
        },
        {
            "event_id": "evt-2",
            "sender": "second@example.com",
            "subject": "Need logistics",
            "body_preview": "Urgent logistics request",
            "attachments": [],
        },
        {
            "event_id": "evt-3",
            "sender": "third@example.com",
            "subject": "Finance details",
            "body_preview": "Finance follow-up",
            "attachments": [],
        },
    ]

    classified_events = [
        {
            "event_id": "evt-1",
            "original_event_id": "evt-1",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "reason_code": "new_contact",
            "reasoning": "sender is new",
            "is_fallback": False,
        },
        {
            "event_id": "evt-2",
            "original_event_id": "evt-2",
            "case_type": "duplicate",
            "priority": "medium",
            "confidence": 0.81,
            "reason_code": "duplicate_sender",
            "reasoning": "duplicate by sender",
            "is_fallback": True,
        },
        {
            "event_id": "evt-3",
            "original_event_id": "evt-3",
            "case_type": "irrelevant",
            "priority": "low",
            "confidence": 0.7,
            "reason_code": "non_rop_topic",
            "reasoning": "non ROP",
            "is_fallback": False,
        },
    ]

    (run_dir / "operator_summary.json").write_text(
        json.dumps(operator_summary), encoding="utf-8"
    )
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics), encoding="utf-8"
    )
    (run_dir / "intake_metadata.json").write_text(
        json.dumps(intake_metadata), encoding="utf-8"
    )
    (run_dir / "normalized_events.json").write_text(
        json.dumps(normalized_events), encoding="utf-8"
    )
    (run_dir / "classified_events.json").write_text(
        json.dumps(classified_events), encoding="utf-8"
    )
    (run_dir / "rop_review_table.tsv").write_text(
        "event_id\tbot_case_type\nevt-1\tnew_lead\n",
        encoding="utf-8",
    )
    (module_dir / "module_result.json").write_text("{}", encoding="utf-8")
    (module_dir / "rop_summary_result.json").write_text("{}", encoding="utf-8")

    return run_dir


# Декодирование HTTP-ответа для проверки рендеринга страниц веб-интерфейса
def _decode(response) -> str:
    return response.body.decode("utf-8")


# Тест: при отсутствии запусков должна отображаться соответствующая информация
def test_runs_route_with_empty_storage(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)

    response = handle_request("GET", "/runs", storage_dir=storage_dir, logger=_logger())

    assert response.status == 200
    html = _decode(response)
    assert "No runs found" in html


# Тест: при наличии одного запуска должна отображаться информация о нем и ссылки на детали
def test_runs_route_with_one_run(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-001")

    response = handle_request("GET", "/runs", storage_dir=storage_dir, logger=_logger())

    assert response.status == 200
    html = _decode(response)
    assert "run-001" in html
    assert '<a href="/runs/run-001">overview</a>' in html
    assert '<a href="/runs/run-001/rop">rop dashboard</a>' in html


# Тест: при запросе страницы обзора запуска должна отображаться информация из operator_summary и source_diagnostics
def test_run_overview_valid_summary(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-002")

    response = handle_request(
        "GET",
        "/runs/run-002",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    assert response.status == 200
    html = _decode(response)
    assert "Run overview: run-002" in html
    assert "operator_summary" in html
    assert "source_diagnostics" in html


# Тест: при наличии operator_summary с некорректным JSON должна отображаться информация об ошибке
def test_run_overview_missing_and_malformed_artifact(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = storage_dir / "runs" / "run-003"
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text("{broken", encoding="utf-8")

    response = handle_request(
        "GET",
        "/runs/run-003",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    assert response.status == 200
    html = _decode(response)
    assert "Data issues detected" in html
    assert "operator_summary:malformed" in html


# Тест: при наличии всех артефактов обзора запуска должна отображаться информация из operator_summary, source_diagnostics, normalized_events, classified_events и rop_review_table
def test_rop_dashboard_metrics_and_table(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-004")

    response = handle_request(
        "GET",
        "/runs/run-004/rop",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    assert response.status == 200
    html = _decode(response)
    assert "ROP dashboard: run-004" in html
    assert "case_type distribution" in html
    assert "priority distribution" in html
    assert "reason_code distribution" in html
    assert "evt-1" in html
    assert "new_lead" in html


# Тест: при фильтрации по case_type должна отображаться только соответствующая подгруппа событий
def test_rop_dashboard_filter_case_type(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-005")

    response = handle_request(
        "GET",
        "/runs/run-005/rop?case_type=duplicate",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    html = _decode(response)
    assert response.status == 200
    assert "evt-2" in html
    assert "evt-1" not in html


# Тест: при фильтрации по priority должна отображаться только соответствующая подгруппа событий
def test_rop_dashboard_filter_priority(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-006")

    response = handle_request(
        "GET",
        "/runs/run-006/rop?priority=low",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    html = _decode(response)
    assert response.status == 200
    assert "evt-3" in html
    assert "evt-1" not in html


# Тест: при фильтрации по is_fallback должна отображаться только соответствующая подгруппа событий
def test_rop_dashboard_filter_fallback(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-007")

    response = handle_request(
        "GET",
        "/runs/run-007/rop?fallback=true",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    html = _decode(response)
    assert response.status == 200
    assert "evt-2" in html
    assert "evt-1" not in html


# Тест: при фильтрации по reason_code должна отображаться только соответствующая подгруппа событий
def test_rop_dashboard_filter_reason_code(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-008")

    response = handle_request(
        "GET",
        "/runs/run-008/rop?reason_code=new_contact",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    html = _decode(response)
    assert response.status == 200
    assert "evt-1" in html
    assert "evt-2" not in html


# Тест: при отсутствии артефактов обзора запуска должна отображаться соответствующая информация
def test_tsv_link_visibility(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-009")

    response = handle_request(
        "GET",
        "/runs/run-009/rop",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    html = _decode(response)
    assert response.status == 200
    assert "/runs/run-009/tsv" in html


# Тест: при запросе страницы обзора запуска должна отображаться информация из operator_summary и source_diagnostics
def test_path_traversal_attempt_in_run_id_blocked(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)

    response = handle_request(
        "GET",
        "/runs/../etc/passwd/rop",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    assert response.status == 400


# Тест: при запросе страницы обзора запуска должна отображаться информация из operator_summary и source_diagnostics
def test_no_raw_eml_or_attachment_content_in_rendered_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-010")

    response = handle_request(
        "GET",
        "/runs/run-010/rop",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    html = _decode(response)
    assert response.status == 200
    assert "original.eml" not in html
    assert "message/rfc822" not in html
    assert "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED" not in html
    assert "RAW-EML-CONTENT-SHOULD-NOT-BE-RENDERED" not in html
    assert "ATTACHMENT_RAW_CONTENT_SHOULD_NOT_BE_RENDERED" not in html


# Тест: sanitized artifact normalized_events.json не должен содержать .eml и raw email payload
def test_normalized_events_artifact_is_sanitized(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir=storage_dir, run_id="run-011")

    response = handle_request(
        "GET",
        "/runs/run-011/artifact/normalized_events.json",
        storage_dir=storage_dir,
        logger=_logger(),
    )

    assert response.status == 200
    text = _decode(response)
    assert "brief.pdf" in text
    assert "application/pdf" in text
    assert "original.eml" not in text
    assert "message/rfc822" not in text
    assert "RAW-EMAIL-ATTACHMENT-SHOULD-NOT-BE-RENDERED" not in text
    assert '"raw_eml"' not in text
    assert '"content"' not in text


# Тест: open_browser=false не должен открывать браузер и сервер должен использовать host/port из settings
def test_start_web_mode_no_browser_open_and_binds_host_port(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self) -> None:
            self.served = False
            self.closed = False

        def serve_forever(self) -> None:
            self.served = True

        def server_close(self) -> None:
            self.closed = True

    fake_server = FakeServer()

    def fake_http_server(address, handler):
        captured["address"] = address
        captured["handler"] = handler
        return fake_server

    open_calls: list[str] = []

    def fake_open(url: str) -> bool:
        open_calls.append(url)
        return True

    monkeypatch.setattr("beeagent_module.web.app.ThreadingHTTPServer", fake_http_server)
    monkeypatch.setattr("beeagent_module.web.app.webbrowser.open", fake_open)
    monkeypatch.setattr("beeagent_module.web.app.get_storage_dir", lambda: tmp_path)

    start_web_mode(
        settings={
            "web": {"host": "127.0.0.1", "port": 19080, "open_browser": False}
        },
        logger=_logger(),
    )

    assert captured["address"] == ("127.0.0.1", 19080)
    assert open_calls == []
    assert fake_server.served is True
    assert fake_server.closed is True


# Тест: open_browser=true должен вызывать webbrowser.open с URL веб-интерфейса
def test_start_web_mode_opens_browser_when_enabled(tmp_path: Path, monkeypatch) -> None:
    class FakeServer:
        def serve_forever(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    open_calls: list[str] = []

    def fake_open(url: str) -> bool:
        open_calls.append(url)
        return True

    monkeypatch.setattr(
        "beeagent_module.web.app.ThreadingHTTPServer",
        lambda address, handler: FakeServer(),
    )
    monkeypatch.setattr("beeagent_module.web.app.webbrowser.open", fake_open)
    monkeypatch.setattr("beeagent_module.web.app.get_storage_dir", lambda: tmp_path)

    start_web_mode(
        settings={
            "web": {"host": "127.0.0.1", "port": 18081, "open_browser": True}
        },
        logger=_logger(),
    )

    assert open_calls == ["http://127.0.0.1:18081/"]
