from __future__ import annotations

import json
from pathlib import Path
from beeui_module.adapters.envelopes import AdapterErrorResult
from beeui_module.pages.config import load_beeui_config
from beeagent_module.interfaces.ui.read_model import build_rop_dashboard_read_model
from beeagent_module.interfaces.ui.read_model import build_run_detail

from tests.beeui_console_support import (
    _build_settings,
    _client,
    _logger,
    _make_storage,
    _write_rop_web_projection,
    _write_run_artifacts,
)


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


def _write_malformed_json_run(storage_dir: Path, run_id: str) -> Path:
    run_dir = storage_dir / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "operator_summary.json").write_text(
        "{invalid json content}", encoding="utf-8"
    )
    return run_dir


def test_console_navigation_is_flat() -> None:
    from beeui_module.pages.locale import resolve_localized_text
    from beeui_module.pages.router import build_navigation

    config_path = Path(__file__).resolve().parents[1] / "config" / "beeui.yml"
    config = load_beeui_config(config_path)

    assert [
        (resolve_localized_text(item.title, "en", "en"), item.path, item.icon)
        for item in config.navigation
    ] == [
        ("Dashboard", "/", "dashboard"),
        ("ROP", "/rop", "users"),
        ("Runs", "/runs", "activity"),
        ("Modules", "/modules", "apps"),
    ]
    assert all(not item.children for item in config.navigation)
    navigation = build_navigation(
        route_prefix="", navigation=config.navigation, active_path="/rop"
    )
    assert [item["path"] for item in navigation] == [
        "/",
        "/rop",
        "/runs",
        "/modules",
    ]
    assert [item["active"] for item in navigation] == [False, True, False, False]


def test_beeui_app_builds(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=_make_storage(tmp_path),
    )
    assert app is not None
    assert app.title == "BeeUI"


def test_start_web_dispatch_imports() -> None:
    from beeagent_module.cli.web import create_web_parser, run_routes, run_web

    assert callable(run_web)
    assert callable(run_routes)
    assert callable(create_web_parser)


def test_cli_defaults_from_config() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args([])
    assert args.host is None
    assert args.port is None
    assert args.no_open is False


def test_cli_host_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--host", "0.0.0.0"])
    assert args.host == "0.0.0.0"


def test_cli_port_override() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--port", "9090"])
    assert args.port == 9090


def test_cli_no_open_flag() -> None:
    from beeagent_module.cli.web import create_web_parser

    parser = create_web_parser()
    args = parser.parse_args(["--no-open"])
    assert args.no_open is True


def test_home_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/")
    assert response.status_code == 200


def test_health_route(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_runs_route_empty(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs")
    assert response.status_code == 200


def test_runs_route_with_data(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-test-001")
    client = _client(storage_dir)
    response = client.get("/runs")
    assert response.status_code == 200
    assert "run-test-001" in response.text
    assert "No runs available." not in response.text


def test_run_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-valid-001")
    client = _client(storage_dir)
    response = client.get("/runs/run-valid-001")
    assert response.status_code == 200


def test_run_route_invalid_run_id(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/../etc/passwd")
    assert response.status_code in (400, 404)


def test_read_model_run_detail_rejects_path_traversal(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)

    data = build_run_detail(storage_dir, "../../outside")

    assert data["error"] == "invalid_run_id"


def test_rop_dashboard_read_model_rejects_path_traversal(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)

    data = build_rop_dashboard_read_model(storage_dir, "../../outside")

    assert data["error"] == "invalid_run_id"


def test_modules_route(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/modules")
    assert response.status_code == 200
    assert "beeagent-rop" in response.text
    assert "beeagent_rop" in response.text
    assert "No blocks configured" not in response.text


def test_modules_route_escapes_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact_with_html(storage_dir)
    client = _client(storage_dir)
    response = client.get("/modules")
    assert response.status_code == 200
    assert "<script>alert" not in response.text


def test_api_dashboard(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["read_only"] is True


def test_api_runs(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-001")
    client = _client(storage_dir)
    response = client.get("/api/runs")
    assert response.status_code == 200


def test_api_run(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-detail")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-detail")
    assert response.status_code == 200


def test_api_modules(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_modules_artifact(storage_dir)
    client = _client(storage_dir)
    response = client.get("/api/modules")
    assert response.status_code == 200


def test_invalid_artifact_id(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-bad-art")
    client = _client(storage_dir)
    response = client.get("/runs/run-bad-art/artifacts/nonexistent_artifact")
    assert response.status_code in (200, 400, 404)


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
    assert response.status_code in (200, 400, 404)
    api_response = client.get("/api/runs/run-bad-art/artifacts/raw_eml")
    assert api_response.status_code in (200, 400, 404)
    if api_response.status_code == 400:
        data = api_response.json()
        assert "error" in data


def test_path_traversal(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))
    response = client.get("/runs/%2E%2E%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)


def test_path_traversal_artifact(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.artifacts import resolve_artifact_path

    storage_dir = _make_storage(tmp_path)
    result = resolve_artifact_path(storage_dir, "..", "operator_summary_json")
    assert result is None


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


def test_historical_ai_assist_provider_preview_is_redacted(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-ai-assist-redaction")
    marker = "HISTORICAL-AI-ASSIST-PROVIDER-MARKER"
    artifact_path = run_dir / "rop_ai_assist_decisions.json"
    artifact_path.write_text(
        json.dumps(
            {
                "run_id": "run-ai-assist-redaction",
                "counters": {},
                "decisions": [
                    {
                        "event_id": "evt-1",
                        "status": "invalid",
                        "reason_code": "unparseable_response",
                        "raw_response_preview": marker,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    text, warning, error = read_bounded_json(artifact_path)
    client = _client(storage_dir)
    api_response = client.get(
        "/api/runs/run-ai-assist-redaction/artifacts/rop_ai_assist_decisions_json"
    )
    html_response = client.get(
        "/runs/run-ai-assist-redaction/artifacts/rop_ai_assist_decisions_json"
    )

    assert text is not None
    assert warning is None
    assert error is None
    assert marker not in text
    assert "[REDACTED]" in text
    assert api_response.status_code == 200
    assert html_response.status_code == 200
    assert marker not in api_response.text
    assert marker not in html_response.text
    assert "[REDACTED]" in api_response.text
    assert "[REDACTED]" in html_response.text


def test_malformed_json_warning(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_json

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_malformed_json_run(storage_dir, "run-malformed")
    path = run_dir / "operator_summary.json"

    text, warning, error = read_bounded_json(path)
    assert text is None
    assert warning is not None
    assert "Malformed" in warning


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


def test_rop_config_read_model_safety(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.read_model import build_config_read_model

    settings = {
        "rop": {
            "sources_path": "config/rop/sources.yml",
            "mailbox_poll": {
                "enabled": False,
                "source_id": "hotline_mailbox",
                "sources_all": True,
            },
        }
    }

    model = build_config_read_model(settings, Path(__file__).resolve().parents[1])
    sources = model["sources"]
    assert sources
    assert all("password_env" not in source.get("mailbox", {}) for source in sources)
    assert all("password" not in str(source) for source in sources)


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


def test_tsv_bounded(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.bounded_read import read_bounded_tsv

    tsv_path = tmp_path / "test.tsv"
    tsv_path.write_text("col1\tcol2\nval1\tval2\n", encoding="utf-8")

    text, warning, error = read_bounded_tsv(tsv_path)
    assert text is not None
    assert "col1" in text
    assert warning is None


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


def test_venue_routes_not_published(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    for path in [
        "/venues/test",
        "/api/venues/test/dashboard",
    ]:
        response = client.get(path)
        assert response.status_code in (404, 503), f"{path} should not be published"


def test_beeui_artifact_viewer_html(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-art-view")
    client = _client(storage_dir)
    response = client.get("/runs/run-art-view/artifacts/operator_summary_json")
    assert response.status_code == 200
    assert "<!doctype html>" in response.text.lower()


def test_artifact_viewer_api_still_json(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-api-art")
    client = _client(storage_dir)
    response = client.get("/api/runs/run-api-art/artifacts/operator_summary_json")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


def test_locale_default_en(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert cfg["default"] == "en"
    assert resolve_locale(None, cfg) == "en"
    assert resolve_locale("en", cfg) == "en"


def test_locale_resolve_ru(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale("ru", cfg) == "ru"


def test_locale_fallback_on_invalid(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale("de", cfg) == "en"
    assert resolve_locale("bad", cfg) == "en"


def test_locale_cookie_fallback(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import get_locale_config, resolve_locale

    cfg = get_locale_config()
    assert resolve_locale(None, cfg, cookie_param="ru") == "ru"
    assert resolve_locale("en", cfg, cookie_param="ru") == "en"
    assert resolve_locale(None, cfg, cookie_param="de") == "en"
    assert resolve_locale("ru", cfg, cookie_param="en") == "ru"


def test_locale_t_function(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.locale import t

    assert t("Dashboard") == "Dashboard"
    assert t("Dashboard", "ru") == "Дашборд"
    assert t("Nonexistent label") == "Nonexistent label"


def test_get_page_returns_layout(tmp_path: Path) -> None:

    from beeagent_module.interfaces.ui.adapter import BeeAgentUiAdapter

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-get-page")
    _write_rop_web_projection(storage_dir)
    adapter = BeeAgentUiAdapter(storage_dir=storage_dir, settings=_build_settings())

    result = adapter.get_page("rop_dashboard", {"tab": "overview"})

    assert not isinstance(result, AdapterErrorResult)
    assert result.status in ("ok", "partial")

    data = result.data
    assert isinstance(data, dict)
    assert "layout" in data
    assert isinstance(data["layout"], list)
