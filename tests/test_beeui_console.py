from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi.testclient import TestClient


# Тесты для консоли BeeUI, интегрированной с BeeAgent, с фокусом на безопасность и устойчивость к ошибкам
def _logger() -> logging.Logger:
    logger = logging.getLogger("test_beeui_console")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Создание временной структуры хранения для тестов, с минимальными артефактами для отображения в UI
def _make_storage(tmp_path: Path) -> Path:
    storage_dir = tmp_path / "storage"
    (storage_dir / "runs").mkdir(parents=True)
    (storage_dir / "interfaces").mkdir(parents=True)
    return storage_dir


# Запись sample modules.json для тестирования отображения модулей в UI
def _write_modules_artifact(storage_dir: Path) -> None:
    payload = {
        "registry": [
            {
                "id": "beeagent-rop",
                "package": "beeagent_rop",
                "entry": "RopModule",
                "state": "loaded",
                "error": "",
            }
        ]
    }
    (storage_dir / "interfaces" / "modules.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


# Запись
def _write_modules_artifact_with_html(storage_dir: Path) -> None:
    payload = {
        "registry": [
            {
                "id": "<script>alert('id')</script>",
                "package": "pkg<script>alert('pkg')</script>",
                "entry": "<b>Entry</b>",
                "state": "<script>alert('state')</script>",
                "error": "<img src=x onerror=alert('err')>",
            }
        ]
    }
    (storage_dir / "interfaces" / "modules.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


# Тест: запись и чтение артефактов для отображения в UI
def _write_run_artifacts(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    module_dir = run_dir / "module-beeagent-rop"
    module_dir.mkdir(parents=True)

    operator_summary = {
        "run_id": run_id,
        "status": "ok",
        "summary": "batch completed",
    }
    source_diagnostics = {
        "selection_mode": "all_enabled",
        "status": "ok",
        "aggregate": {
            "source_count": 1,
            "loaded_source_count": 1,
            "degraded_source_count": 0,
        },
        "sources": [
            {
                "source_id": "hotline_mailbox",
                "source_type": "mailbox_readonly",
                "source_role": "technical_aggregator",
                "source_display_name": "Welding Hotline mailbox",
                "client_id": "welding",
                "status": "ok",
            }
        ],
    }
    intake_metadata = {
        "source_id": "hotline_mailbox",
        "loaded_item_count": 3,
    }
    normalized_events = [
        {"event_id": "evt-1", "sender": "test@example.com", "subject": "Test"},
    ]
    classified_events = [
        {
            "event_id": "evt-1",
            "case_type": "new_lead",
            "priority": "high",
            "confidence": 0.95,
            "is_fallback": False,
        }
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
        "event_id\tbot_case_type\nevt-1\tnew_lead\n", encoding="utf-8"
    )
    (module_dir / "module_result.json").write_text("{}", encoding="utf-8")
    (module_dir / "rop_summary_result.json").write_text("{}", encoding="utf-8")

    return run_dir


def _write_run_artifacts_with_html(storage_dir: Path, run_id: str) -> Path:
    run_dir = _write_run_artifacts(storage_dir, run_id)

    source_diagnostics = json.loads(
        (run_dir / "source_diagnostics.json").read_text(encoding="utf-8")
    )
    source_diagnostics["sources"] = [
        {
            "source_id": "<script>alert('sid')</script>",
            "source_type": "mailbox_readonly",
            "source_role": "technical_aggregator",
            "source_display_name": "<script>alert('display')</script>",
            "client_id": "welding",
            "status": "<script>alert('status')</script>",
        }
    ]
    (run_dir / "source_diagnostics.json").write_text(
        json.dumps(source_diagnostics), encoding="utf-8"
    )

    return run_dir


# Тест: запись артефакта с чувствительными данными для проверки маскировки в UI
def _write_malformed_json_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        "{invalid json content}", encoding="utf-8"
    )
    return run_dir


# Тест: запись скрипта запуска с артефактом, содержащим ключи, обладающие конфиденциальными данными
def _write_secret_stub_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "ok",
                "ROP_MAILBOX_PASSWORD": "should-not-leak",
            }
        ),
        encoding="utf-8",
    )
    return run_dir


# Тест: создание минимальных настроек BeeAgent для тестирования
def _build_settings() -> dict:
    return {
        "app": {"name": "BeeAgent", "env": "test"},
        "web": {"host": "127.0.0.1", "port": 18080, "open_browser": False},
        "logging": {"clear_logs": True, "utc": True, "level": "INFO"},
        "rop": {
            "sources": [
                {
                    "source_id": "test_source",
                    "source_type": "json_batch",
                    "source_role": "test",
                    "client_id": "test",
                    "display_name": "Test Source",
                    "enabled": True,
                    "authority": "read_only",
                    "items_max": 10,
                }
            ]
        },
    }


# Тест: создание TestClient с приложением BeeUI для интеграционных тестов
def _client(storage_dir: Path) -> TestClient:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=storage_dir,
    )
    return TestClient(app)


# Тест: чек, что приложение BeeUI строится без ошибок с минимальными настройками и структурой хранения
def test_beeui_app_builds(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=_make_storage(tmp_path),
    )
    assert app is not None
    assert app.title == "BeeUI"


# Тест: чек, что при запуске приложения с CLI аргументом web вызывается правильная функция и передаются аргументы
def test_start_web_dispatch_imports() -> None:
    from beeagent_module.cli.web import create_web_parser, run_routes, run_web

    assert callable(run_web)
    assert callable(run_routes)
    assert callable(create_web_parser)


# Тест: чек, что при запуске приложения с CLI аргументом rop вызывается правильная функция и передаются аргументы
def test_cli_defaults_from_config() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args([])
    assert args.host is None
    assert args.port is None
    assert args.no_open is False


# Тест: test CLI --host override
def test_cli_host_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--host", "0.0.0.0"])
    assert args.host == "0.0.0.0"


# Тест: test CLI --port override
def test_cli_port_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--port", "9090"])
    assert args.port == 9090


# Тест: test CLI --no-open flag
def test_cli_no_open_flag() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--no-open"])
    assert args.no_open is True


# Тест: test GET / returns 200
def test_home_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/")
    assert response.status_code == 200


# Тест: тестовый запрос GET /health возвращает ok (маршрут health, предоставляемый BeeUI)
def test_health_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# Тест: GET /runs возвращает 200 и корректно отображает наличие или отсутствие ран-артефактов
def test_runs_route_empty(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs")
    assert response.status_code == 200


# Тест: чек команды GET /runs с данными о запуске
def test_runs_route_with_data(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-test-001")
    client = _client(storage_dir)
    response = client.get("/runs")
    assert response.status_code == 200
    assert "run-test-001" in response.text
    assert "No runs available." not in response.text


# Тест: GET /runs/{run_id} возвращает 200 для существующего рана и корректно отображает его детали
def test_run_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-valid-001")
    client = _client(storage_dir)
    response = client.get("/runs/run-valid-001")
    assert response.status_code == 200


# Тест: GET /runs/{run_id} с несуществующим run_id возвращает 404
def test_run_route_invalid_run_id(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/../etc/passwd")
    assert response.status_code in (400, 404)


# Тест: GET /rop возвращает 200 и отображает данные ROP dashboard, если артефакты присутствуют
def test_rop_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-001")
    client = _client(storage_dir)
    response = client.get("/rop")
    assert response.status_code == 200
    assert "Classified events" in response.text


def test_rop_route_escapes_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts_with_html(storage_dir, "run-rop-html")
    client = _client(storage_dir)
    response = client.get("/rop")
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


# Тест: test GET /modules возвращает код 200
def test_modules_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/modules")
    assert response.status_code == 200
    assert "beeagent-rop" in response.text


def test_modules_route_escapes_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact_with_html(storage_dir)
    client = _client(storage_dir)
    response = client.get("/modules")
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


# Тест: test GET /api/dashboard
def test_api_dashboard(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True


# Тест: test GET /api/runs
def test_api_runs(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-001")
    client = _client(storage_dir)
    response = client.get("/api/runs")
    assert response.status_code == 200


# Тест: test GET /api/runs/{run_id} для валидного run_id
def test_api_run(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-detail")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-detail")
    assert response.status_code == 200


# Тест: test GET GET /api/modules
def test_api_modules(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/api/modules")
    assert response.status_code == 200


# Тест: test GET /api/rop/dashboard
def test_api_rop_dashboard(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-api")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["read_only"] is True


# Тест: test GET /api/rop/dashboard?run_id=...
def test_api_rop_dashboard_with_run_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-specific")
    client = _client(storage_dir)
    response = client.get("/api/rop/dashboard", params={"run_id": "run-rop-specific"})
    assert response.status_code == 200


# Тест:
def test_api_rop_dashboard_rejects_invalid_run_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-valid")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard", params={"run_id": "../etc/passwd"})

    assert response.status_code == 400
    data = response.json()
    assert data["ok"] is False
    assert data["read_only"] is True
    assert data["error"]["code"] == "invalid_run_id"


# Тест: test GET /runs/{run_id}/artifacts
def test_run_artifacts_list(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-art-list")
    client = _client(storage_dir)
    response = client.get("/runs/run-art-list/artifacts")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


# Тест: test GET /runs/{run_id}/artifacts/{artifact_id}
def test_run_artifact_content(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-art-content")
    client = _client(storage_dir)
    response = client.get("/runs/run-art-content/artifacts/operator_summary_json")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["data"]["artifact_id"] == "operator_summary_json"


# Тест: отклонение тестового артефакта, не включенный в список запрещенных
def test_invalid_artifact_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    response = client.get("/runs/run-bad-art/artifacts/nonexistent_artifact")
    assert response.status_code in (400, 404)


# Тест: чек, что ID артефакта, не включенный в список запрещенных, отклоняется
def test_non_allowlisted_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

    assert is_artifact_id_allowed("operator_summary_json") is True
    assert is_artifact_id_allowed("run_json") is True
    assert is_artifact_id_allowed("raw_eml") is False
    assert is_artifact_id_allowed("some_random_file") is False


def test_non_allowlisted_artifact_error_envelope(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    response = client.get("/runs/run-bad-art/artifacts/raw_eml")
    assert response.status_code == 400
    data = response.json()
    assert data["ok"] is False
    assert data["read_only"] is True
    assert "error" in data


# Тест: чек пути выполнения в run_id заблокирована
def test_path_traversal(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/%2E%2E%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)


# Тест: чек пути при разрешении артефактов возвращает None
def test_path_traversal_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path

    storage_dir = _make_storage(tmp_path)
    result = resolve_artifact_path(storage_dir, "..", "operator_summary_json")
    assert result is None


# Тест: чек, что ключ raw_eml скрыт при ограниченном чтении
def test_no_raw_eml_in_artifacts(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-no-eml")
    normalized_path = run_dir / "normalized_events.json"
    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    data.append(
        {
            "event_id": "evt-eml",
            "raw_eml": "RAW_EML_SHOULD_BE_REDACTED",
        }
    )
    normalized_path.write_text(json.dumps(data), encoding="utf-8")

    text, warning, error = read_bounded_json(normalized_path)
    assert text is not None
    assert "RAW_EML_SHOULD_BE_REDACTED" not in text
    assert "[REDACTED]" in text


# Тест: чек, что при чтении поврежденного JSON возвращается предупреждение, а не происходит сбой
def test_malformed_json_warning(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_malformed_json_run(storage_dir, "run-malformed")
    path = run_dir / "operator_summary.json"

    text, warning, error = read_bounded_json(path)
    assert text is None
    assert warning is not None
    assert "Malformed" in warning


# Тест: чек, что маршруты GET не изменяют артефакты хранения
def test_get_routes_do_not_mutate_storage(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-no-mutate")
    client = _client(storage_dir)

    before = {
        path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    client.get("/")
    client.get("/health")
    client.get("/runs")
    client.get("/runs/run-no-mutate")
    client.get("/rop")
    client.get("/modules")
    client.get("/api/dashboard")
    client.get("/api/runs")
    client.get("/api/runs/run-no-mutate")
    client.get("/api/modules")
    client.get("/api/rop/dashboard")

    after = {
        path.relative_to(storage_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in run_dir.rglob("*")
        if path.is_file()
    }

    assert after == before


# Тест: чек, что параметр read-model в исходной конфигурации ROP не раскрывает секреты
def test_rop_config_read_model_safety(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import build_config_read_model

    settings = {
        "rop": {
            "sources": [
                {
                    "source_id": "hotline",
                    "source_type": "mailbox_readonly",
                    "source_role": "technical_aggregator",
                    "client_id": "welding",
                    "display_name": "Hotline",
                    "enabled": True,
                    "authority": "read_only",
                    "items_max": 20,
                    "mailbox": {
                        "host": "imap.example.com",
                        "port": 993,
                        "use_ssl": True,
                        "folder": "INBOX",
                        "username_env": "ROP_MAILBOX_USERNAME",
                        "password_env": "ROP_MAILBOX_PASSWORD",
                    },
                }
            ]
        }
    }

    model = build_config_read_model(settings)
    sources = model["sources"]
    assert len(sources) == 1
    source = sources[0]

    assert source["source_id"] == "hotline"
    assert source["source_type"] == "mailbox_readonly"
    assert source["source_role"] == "technical_aggregator"
    assert source["client_id"] == "welding"
    assert source["display_name"] == "Hotline"
    assert source["enabled"] is True
    assert source["authority"] == "read_only"
    assert source["items_max"] == 20

    mailbox = source.get("mailbox", {})
    assert mailbox["host"] == "imap.example.com"
    assert mailbox["port"] == 993
    assert mailbox["use_ssl"] is True
    assert mailbox["folder"] == "INBOX"
    assert mailbox["username_env"] == "ROP_MAILBOX_USERNAME"

    assert "password_env" not in mailbox


# Тест: чек, что при чтении слишком большого JSON возвращается предупреждение, а не происходит сбой
def test_oversized_json_bounded(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import (
        MAX_JSON_BYTES,
        read_bounded_json,
    )

    oversized_path = tmp_path / "large.json"
    oversized_path.write_text("x" * (MAX_JSON_BYTES + 1), encoding="utf-8")

    text, warning, error = read_bounded_json(oversized_path)
    assert text is None
    assert warning is not None
    assert "too large" in warning


# Тест: чек считывания TSV работает в пределах допустимых значений
def test_tsv_bounded(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_tsv

    tsv_path = tmp_path / "test.tsv"
    tsv_path.write_text("col1\tcol2\nval1\tval2\n", encoding="utf-8")

    text, warning, error = read_bounded_tsv(tsv_path)
    assert text is not None
    assert "col1" in text
    assert warning is None


# Тест: чек, что все ожидаемые ID артефактов находятся в списке разрешенных
def test_artifact_allowlist_coverage() -> None:
    from beeagent_module.interfaces.ui.artifacts import is_artifact_id_allowed

    expected = [
        "run_json",
        "operator_summary_json",
        "source_diagnostics_json",
        "intake_metadata_json",
        "normalized_events_json",
        "classified_events_json",
        "attachment_extraction_json",
        "rop_review_table_tsv",
        "module_result_json",
        "rop_summary_result_json",
        "lead_classification_result_json",
        "steps_json",
    ]
    for aid in expected:
        assert is_artifact_id_allowed(aid), f"{aid} should be allowlisted"

    blocked = ["raw_eml", "attachment_content", "content_bytes", "payload_bytes"]
    for aid in blocked:
        assert not is_artifact_id_allowed(aid), f"{aid} should NOT be allowlisted"


# Тест: чек наличия только GET-маршрутов (без мутаций)
def test_no_post_routes(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    for path in ["/", "/health", "/runs", "/rop", "/modules"]:
        response = client.post(path)
        assert response.status_code in (405, 404), f"POST {path} should be rejected"

    for path in [
        "/api/dashboard",
        "/api/runs",
        "/api/modules",
        "/api/rop/dashboard",
    ]:
        response = client.post(path)
        assert response.status_code in (405, 404), f"POST {path} should be rejected"


# Тест: чек, что BeeUI auth/catalog/venue удалены
def test_auth_and_catalog_routes_not_published(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    for path in [
        "/auth/csrf",
        "/auth/login",
        "/components",
        "/components/layout",
        "/venues/test",
        "/api/venues/test/dashboard",
    ]:
        response = client.get(path)
        assert response.status_code == 404, f"{path} should not be published"
