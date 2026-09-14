from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.beeui_console_support import (
    _build_settings,
    _client,
    _logger,
    _make_storage,
    _scoped_auth_client,
    _write_rop_web_projection,
    _write_run_artifacts,
)


def _build_rop_app(storage_dir: Path, settings: dict[str, Any] | None = None):
    from beeagent_module.interfaces.ui.app import build_beeui_app

    return build_beeui_app(
        settings=settings or _build_settings(),
        logger=_logger(),
        storage_dir=storage_dir,
    )


def _write_many_rop_runs(storage_dir: Path, count: int) -> list[str]:
    run_ids: list[str] = []
    for index in range(count):
        run_id = f"run-hist-{index:03d}"
        _write_run_artifacts(storage_dir, run_id)
        run_ids.append(run_id)
    return run_ids


def _set_scoped_auth_env_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEEAGENT_WEB_SESSION_SECRET", "scoped-session-secret")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN1_TOKEN", "admin1-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ADMIN2_TOKEN", "admin2-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROPVIEWER_TOKEN", "ropviewer-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROPADMIN_TOKEN", "ropadmin-test-token")
    monkeypatch.setenv("BEEAGENT_WEB_ROP_TOKEN", "rop-test-token")


def test_rop_page_uses_released_icon_tab_contract(tmp_path: Path) -> None:
    from beeagent_module.interfaces.ui.app import build_beeui_app

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-icons")
    _write_rop_web_projection(storage_dir)
    app = build_beeui_app(
        settings=_build_settings(),
        logger=_logger(),
        storage_dir=storage_dir,
    )
    client = TestClient(app)

    response = client.get("/rop?tab=overview")

    assert response.status_code == 200
    html = response.text
    assert 'data-beeui-page-tabs-progressive="true"' in html
    assert 'data-beeui-page-tab="true"' in html
    assert 'class="nav nav-tabs card-header-tabs nav-fill"' in html
    assert "beeui-tabs-compact" not in html
    assert 'href="/static/vendor/tabler-icons/tabler-icons.min.css?v=3.46.0"' in html
    assert "https://cdn" not in html.lower()
    assert "preview.tabler.io" not in html
    assert (
        client.get("/static/vendor/tabler-icons/tabler-icons.min.css").status_code
        == 200
    )
    assert (
        client.get("/static/vendor/tabler-icons/fonts/tabler-icons.woff2").status_code
        == 200
    )

    expected_icons = {
        "overview": "dashboard",
        "queue": "stack",
        "sources": "database",
        "blacklist": "ban",
    }
    expected_titles = {
        "overview": "Overview",
        "queue": "Queue",
        "sources": "Sources",
        "blacklist": "Blacklist",
    }

    assert len(set(expected_icons.values())) == 4

    for tab_id, icon in expected_icons.items():
        href = f"/rop?tab={tab_id}"
        href_pos = html.index(href)
        anchor_end = html.index("</a>", href_pos)
        anchor_html = html[href_pos:anchor_end]

        assert f'data-beeui-icon="{icon}"' in anchor_html
        assert expected_titles[tab_id] in anchor_html

    russian_html = client.get("/rop?lang=ru&tab=overview").text
    for title in ("Обзор", "Очередь", "Источники", "Чёрный список"):
        assert title in russian_html


def test_rop_projection_missing_root_index_fails_explicitly(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-missing-index")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "web_projection_unavailable"
    assert "regenerate" in body["error"]["message"]
    assert not (storage_dir / "interfaces" / "rop_web_projection_v2.json").exists()


def test_rop_projection_malformed_root_index_fails_explicitly(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-malformed-index")
    (storage_dir / "interfaces" / "rop_web_projection_v2.json").write_text(
        "{bad json", encoding="utf-8"
    )
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_v2_without_additive_leaderboard_remains_readable(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-old-v2")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    entry = manifest["runs"]["run-old-v2"]
    for view_key in ("overview.today", "overview.7d", "api.7d"):
        path = rop_web_projection_v2_view_path(
            storage_dir,
            entry["generation"],
            "run-old-v2",
            entry["revision"],
            view_key,
        )
        assert path is not None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if view_key == "overview.today":
            payload["payload"].pop("team_leaderboard", None)
        else:
            payload["payload"]["team_leaderboard"] = {"plan_lead": "bad"}
        path.write_text(json.dumps(payload), encoding="utf-8")

    client = TestClient(_build_rop_app(storage_dir))

    assert client.get("/rop?period=7d").status_code == 200
    api = client.get("/api/rop/dashboard?period=7d")
    assert api.status_code == 200
    assert "team_leaderboard" not in api.json()["data"]


@pytest.mark.parametrize(
    "malformed_index",
    (
        {"total_runs": None},
        {"total_runs": True},
        {"total_runs": "1"},
        {"run_ids": ["run-invalid-index"] * 21},
    ),
)
def test_rop_projection_invalid_index_fails_closed_without_read_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    malformed_index: dict[str, object],
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module
    from beeagent_module.cases.rop_dashboard import rop_web_projection_v2_manifest

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-invalid-index")
    _write_rop_web_projection(storage_dir)
    index_path = storage_dir / "interfaces" / "rop_web_projection_v2.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index.update(malformed_index)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    before_index = index_path.read_bytes()

    def fail_historical_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("historical aggregation must not run on GET")

    client = TestClient(_build_rop_app(storage_dir))
    monkeypatch.setattr(
        rop_dashboard_module, "_aggregate_period_events", fail_historical_read
    )
    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", fail_historical_read)

    html = client.get("/rop")
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 503
    assert api.status_code == 503
    assert api.json()["error"]["code"] == "web_projection_unavailable"
    assert index_path.read_bytes() == before_index
    assert rop_web_projection_v2_manifest(storage_dir) is None


def test_rop_projection_missing_selected_run_entry_fails_explicitly(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-missing-entry")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    entry = manifest["runs"]["run-missing-entry"]
    path = rop_web_projection_v2_view_path(
        storage_dir,
        entry["generation"],
        "run-missing-entry",
        entry["revision"],
        "api.7d",
    )
    assert path is not None
    path.unlink()
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-missing-entry")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_wrong_run_entry_fails_explicitly(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-wrong-entry")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-wrong-entry"]
    entry_path = rop_web_projection_v2_view_path(
        storage_dir,
        metadata["generation"],
        "run-wrong-entry",
        metadata["revision"],
        "api.7d",
    )
    assert entry_path is not None
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["run_id"] = "other-run"
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-wrong-entry")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_malformed_view_payload_fails_explicitly(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-malformed-view")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-malformed-view"]
    view_path = rop_web_projection_v2_view_path(
        storage_dir,
        metadata["generation"],
        "run-malformed-view",
        metadata["revision"],
        "api.7d",
    )
    assert view_path is not None
    view = json.loads(view_path.read_text(encoding="utf-8"))
    view["payload"] = {}
    view_path.write_text(json.dumps(view), encoding="utf-8")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-malformed-view")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_missing_period_entry_fails_explicitly(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-missing-period")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-missing-period"]
    entry_path = rop_web_projection_v2_view_path(
        storage_dir,
        metadata["generation"],
        "run-missing-period",
        metadata["revision"],
        "api.7d",
    )
    assert entry_path is not None
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["view_key"] = "api.all"
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-missing-period&period=7d")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_html_overview_uses_bounded_today_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )
    from beeagent_module.interfaces.ui import read_model as read_model_module
    from beeagent_module.interfaces.ui.read_model import build_rop_tab_read_model

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-today-summary")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-today-summary"]

    for period, emails, new_leads in (("7d", 40, 3), ("today", 12, 5)):
        path = rop_web_projection_v2_view_path(
            storage_dir,
            metadata["generation"],
            "run-today-summary",
            metadata["revision"],
            f"overview.{period}",
        )
        assert path is not None
        view = json.loads(path.read_text(encoding="utf-8"))
        view["payload"]["business_kpi"].update(
            {
                "processed_emails": emails,
                "processed_events": emails,
                "new_leads": new_leads,
            }
        )
        path.write_text(json.dumps(view), encoding="utf-8")

    def fail_historical_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("historical aggregation must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", fail_historical_read)
    monkeypatch.setattr(
        rop_dashboard_module,
        "_aggregate_period_events",
        fail_historical_read,
    )
    monkeypatch.setattr(read_model_module, "build_rop_dashboard", fail_historical_read)

    data = build_rop_tab_read_model(
        storage_dir,
        tab="overview",
        period="7d",
        default_period="7d",
        configured_periods=_build_settings()["rop"]["dashboard"]["periods"],
    )
    assert data["business_kpi"]["processed_emails"] == 40
    assert data["business_kpi"]["new_leads"] == 3
    assert data["today_summary"] == {"emails": 12, "new_leads": 5}

    client = _client(storage_dir)
    response = client.get(
        "/rop?tab=overview&run_id=run-today-summary&period=7d&lang=ru"
    )
    api = client.get("/api/rop/dashboard?run_id=run-today-summary&period=7d&lang=ru")

    assert response.status_code == 200
    assert 'aria-label="За сегодня 12 писем, из них 5 новых лидов"' in response.text
    assert "За сегодня 12 писем," in response.text
    assert "из них 5 новых лидов" in response.text
    assert api.status_code == 200
    assert "today_summary" not in api.json()["data"]


def test_rop_projection_get_never_falls_back_to_run_enumeration(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-a")
    _write_run_artifacts(storage_dir, "run-b")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-a"]
    path = rop_web_projection_v2_view_path(
        storage_dir, metadata["generation"], "run-a", metadata["revision"], "api.7d"
    )
    assert path is not None
    path.unlink()
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard?run_id=run-a")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_projection_get_never_regenerates_or_writes(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-no-write")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    assert not (storage_dir / "interfaces" / "rop_web_projection_v2.json").exists()
    assert not (storage_dir / "interfaces" / "rop_web_projection_v2").exists()


def test_rop_projection_error_is_stable_api_error(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-stable-error")
    client = TestClient(_build_rop_app(storage_dir))

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "web_projection_unavailable"
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]


def test_rop_available_runs_and_total_runs_from_bounded_catalog(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-cat-a")
    _write_run_artifacts(storage_dir, "run-cat-b")
    _write_run_artifacts(storage_dir, "run-cat-c")
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-cat-b")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert set(payload["available_runs"]) == {"run-cat-a", "run-cat-b", "run-cat-c"}
    assert payload["kpis"]["total_runs"] == 3


def test_rop_web_read_consumes_only_projection_artifacts(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-read-a")
    _write_run_artifacts(storage_dir, "run-read-b")
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-read-b"]
    entry_path = rop_web_projection_v2_view_path(
        storage_dir,
        metadata["generation"],
        "run-read-b",
        metadata["revision"],
        "api.all",
    )
    assert entry_path is not None
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    entry["payload"]["queues"] = {
        "high_priority": [
            {
                "event_id": "evt-proj",
                "source_id": "hotline_mailbox",
                "sender": "proj@example.com",
                "subject": "Projection row",
                "case_type": "new_lead",
                "priority": "high",
                "run_id": "run-read-b",
            }
        ]
    }
    entry_path.write_text(json.dumps(entry), encoding="utf-8")
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-read-b&period=all")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["queues"]["high_priority"][0]["event_id"] == "evt-proj"
    assert set(payload["available_runs"]) == {"run-read-a", "run-read-b"}


def test_rop_trusted_attach_existing_overlay_in_tab_path(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-attach")
    classified = json.loads((run_dir / "classified_events.json").read_text())
    classified[0].update(
        {
            "event_id": "evt-attach",
            "event_instance_id": "inst-1",
            "source_id": "hotline_mailbox",
            "sender": "client@example.com",
            "subject": "Attach existing",
        }
    )
    (run_dir / "classified_events.json").write_text(json.dumps(classified))
    (storage_dir / "interfaces" / "rop_writeback_state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "events": {
                    "welding|hotline_mailbox|evt-attach|inst-1": {
                        "event_id": "evt-attach",
                        "event_instance_id": "inst-1",
                        "source_id": "hotline_mailbox",
                        "outcome": "attach_existing",
                        "target_provenance": "thread_resolved",
                        "last_run_id": "run-attach",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard?run_id=run-attach&period=all&tab=queue")

    assert response.status_code == 200
    row = response.json()["data"]["queue_rows"][0]
    assert row["event_id"] == "evt-attach"
    assert row["case_type"] == "existing_deal"
    assert row["bot_case_type"] == "existing_deal"
    assert row["semantic_case_type"] == "new_lead"


def test_rop_auth_get_no_historical_scan_with_many_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, 40)
    _write_rop_web_projection(storage_dir)
    client = _scoped_auth_client(storage_dir)
    self_login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert self_login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop", follow_redirects=False)
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 200
    assert api.status_code == 200
    payload = api.json()["data"]
    assert len(payload["available_runs"]) <= 20
    assert payload["total_runs"] == 40


def test_rop_auth_explicit_old_run_id_outside_bounded_catalog_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, 40)
    _write_rop_web_projection(storage_dir)
    client = _scoped_auth_client(storage_dir)
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    old_run_id = "run-hist-000"
    html = client.get(f"/rop?run_id={old_run_id}", follow_redirects=False)
    api = client.get(f"/api/rop/dashboard?run_id={old_run_id}")

    assert html.status_code == 403
    assert api.status_code == 403


def test_rop_auth_unknown_run_id_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-known")
    _write_rop_web_projection(storage_dir)
    client = _scoped_auth_client(storage_dir)
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop?run_id=run-unknown", follow_redirects=False)
    api = client.get("/api/rop/dashboard?run_id=run-unknown")

    assert html.status_code == 403
    assert api.status_code == 403


def test_rop_auth_missing_projection_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-no-proj")
    client = _scoped_auth_client(storage_dir)
    (storage_dir / "interfaces" / "rop_web_projection_v2.json").unlink()
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop", follow_redirects=False)
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 503
    assert api.status_code == 503
    assert api.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_auth_malformed_projection_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from beeagent_module.cases import rop_dashboard as rop_dashboard_module

    _set_scoped_auth_env_for_test(monkeypatch)
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-malformed-proj")
    client = _scoped_auth_client(storage_dir)
    (storage_dir / "interfaces" / "rop_web_projection_v2.json").write_text(
        "{bad json}", encoding="utf-8"
    )
    login = client.post(
        "/auth/login",
        data={"user_id": "ropviewer", "token": "ropviewer-test-token"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 200)

    def _explode(*_args: object, **_kwargs: object):
        raise RuntimeError("historical scan must not run on GET")

    monkeypatch.setattr(rop_dashboard_module, "_list_rop_run_ids", _explode)

    html = client.get("/rop", follow_redirects=False)
    api = client.get("/api/rop/dashboard")

    assert html.status_code == 503
    assert api.status_code == 503
    assert api.json()["error"]["code"] == "web_projection_unavailable"


def test_rop_available_runs_bounded_and_total_runs_scalar(tmp_path: Path) -> None:
    from beeagent_module.cases.rop_dashboard import ROP_WEB_PROJECTION_RUNS_MAX

    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, ROP_WEB_PROJECTION_RUNS_MAX + 10)
    _write_rop_web_projection(storage_dir)
    client = _client(storage_dir)

    response = client.get("/api/rop/dashboard")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload["available_runs"]) == ROP_WEB_PROJECTION_RUNS_MAX
    assert payload["total_runs"] == ROP_WEB_PROJECTION_RUNS_MAX + 10
    assert payload["kpis"]["total_runs"] == ROP_WEB_PROJECTION_RUNS_MAX + 10


def test_rop_projection_index_has_bounded_catalog_and_scalar_total(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        ROP_WEB_PROJECTION_RUNS_MAX,
        rop_web_projection_index,
    )

    storage_dir = _make_storage(tmp_path)
    _write_many_rop_runs(storage_dir, ROP_WEB_PROJECTION_RUNS_MAX + 5)
    _write_rop_web_projection(storage_dir)

    index = rop_web_projection_index(storage_dir)

    assert index is not None
    assert len(index["run_ids"]) == ROP_WEB_PROJECTION_RUNS_MAX
    assert index["total_runs"] == ROP_WEB_PROJECTION_RUNS_MAX + 5
    assert index["latest_run_id"] == index["run_ids"][0]


def test_api_v2_uses_all_view_for_date_range_and_preserves_request_state(
    tmp_path: Path,
) -> None:
    from beeagent_module.cases.rop_dashboard import (
        rop_web_projection_v2_manifest,
        rop_web_projection_v2_view_path,
    )

    storage_dir = _make_storage(tmp_path)
    run_dir = _write_run_artifacts(storage_dir, "run-api-date-range")
    classified = json.loads((run_dir / "classified_events.json").read_text())
    classified.append(
        {
            "event_id": "evt-explicit-range",
            "event_instance_id": "instance-explicit-range",
            "source_id": "hotline_mailbox",
            "sender": "range@example.com",
            "subject": "Explicit date range",
            "case_type": "new_lead",
            "priority": "high",
            "event_date": "2020-01-15T12:00:00Z",
        }
    )
    (run_dir / "classified_events.json").write_text(json.dumps(classified))
    _write_rop_web_projection(storage_dir)
    manifest = rop_web_projection_v2_manifest(storage_dir)
    assert manifest is not None
    metadata = manifest["runs"]["run-api-date-range"]
    api_view_path = rop_web_projection_v2_view_path(
        storage_dir,
        metadata["generation"],
        "run-api-date-range",
        metadata["revision"],
        "api.all",
    )
    assert api_view_path is not None
    api_snapshot = json.loads(api_view_path.read_text())
    assert not {
        "filter_params",
        "page",
        "page_size",
        "pagination",
        "sort",
        "order",
        "queue_rows",
    }.intersection(api_snapshot["payload"])

    client = _client(storage_dir)
    response = client.get(
        "/api/rop/dashboard?run_id=run-api-date-range&date_from=2020-01-01&"
        "date_to=2020-01-31&page=1&page_size=50&sort=sender&order=asc"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["filter_params"] == {
        "date_from": "2020-01-01",
        "date_to": "2020-01-31",
    }
    assert data["page"] == 1
    assert data["page_size"] == 50
    assert data["sort"] == "sender"
    assert data["order"] == "asc"
    assert "evt-explicit-range" in {row["event_id"] for row in data["queue_rows"]}
