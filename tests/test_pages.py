from __future__ import annotations

from pathlib import Path

from tests.test_beeui_console import _client, _make_storage, _write_run_artifacts


def test_adapter_custom_page_renders_language_switcher(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-rop-switcher-001")
    client = _client(storage_dir)

    response = client.get("/rop?lang=ru")

    assert response.status_code == 200
    assert "beeui-language-switcher" in response.text
    assert '<strong class="beeui-lang-active">RU</strong>' in response.text


def test_configured_adapter_page_renders_language_switcher(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-modules-switcher-001")
    client = _client(storage_dir)

    response = client.get("/modules?lang=ru")

    assert response.status_code == 200
    assert "beeui-language-switcher" in response.text
    assert '<strong class="beeui-lang-active">RU</strong>' in response.text


def test_component_catalog_routes_render_language_switcher(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    index_response = client.get("/components?lang=ru")
    page_response = client.get("/components/interface?lang=ru")

    assert index_response.status_code == 200
    assert page_response.status_code == 200
    assert "beeui-language-switcher" in index_response.text
    assert "beeui-language-switcher" in page_response.text
    assert '<strong class="beeui-lang-active">RU</strong>' in index_response.text
    assert '<strong class="beeui-lang-active">RU</strong>' in page_response.text
