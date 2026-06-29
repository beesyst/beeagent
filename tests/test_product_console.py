from __future__ import annotations

from pathlib import Path

from tests.test_beeui_console import _client, _make_storage, _write_run_artifacts


def test_dashboard_renders_language_switcher(tmp_path: Path) -> None:
    client = _client(_make_storage(tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "beeui-language-switcher" in response.text
    assert "RU" in response.text
    assert "EN" in response.text


def test_dashboard_ru_marks_selected_locale_and_preserves_sidebar_lang(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-dashboard-ru-001")
    client = _client(storage_dir)

    response = client.get("/?lang=ru")

    assert response.status_code == 200
    assert "Дашборд BeeAgent" in response.text
    assert "Read-only дашборд оператора" in response.text
    assert "Оператор" in response.text
    assert "Дашборд" in response.text
    assert "РОП" in response.text
    assert "Запуски" in response.text
    assert "Модули" in response.text
    assert "Последний запуск" in response.text
    assert "KPI" in response.text
    assert "Сводка" in response.text
    assert "Технические детали" in response.text
    assert "Открыть запуск" in response.text
    assert '<strong class="beeui-lang-active">RU</strong>' in response.text
    assert 'hreflang="en"' in response.text
    assert '/runs?lang=ru' in response.text
    assert '/rop?lang=ru' in response.text


def test_runs_renders_language_switcher_for_default_and_ru_locale(
    tmp_path: Path,
) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-switcher-001")
    client = _client(storage_dir)

    response_default = client.get("/runs")
    response_ru = client.get("/runs?lang=ru")

    assert response_default.status_code == 200
    assert response_ru.status_code == 200
    assert "beeui-language-switcher" in response_default.text
    assert "beeui-language-switcher" in response_ru.text
    assert "Запуски" in response_ru.text
    assert "История запусков" in response_ru.text
    assert "Список запусков" in response_ru.text
    assert "ID запуска" in response_ru.text
    assert "Статус" in response_ru.text
    assert "Начат" in response_ru.text
    assert "Завершён" in response_ru.text
    assert "Открыть" in response_ru.text
    assert '<strong class="beeui-lang-active">RU</strong>' in response_ru.text
    assert '/runs?lang=ru' in response_ru.text
    assert '/rop?lang=ru' in response_ru.text


def test_run_detail_renders_language_switcher(tmp_path: Path) -> None:
    storage_dir = _make_storage(tmp_path)
    _write_run_artifacts(storage_dir, "run-detail-switcher-001")
    client = _client(storage_dir)

    response = client.get("/runs/run-detail-switcher-001?lang=ru")

    assert response.status_code == 200
    assert "beeui-language-switcher" in response.text
    assert '<strong class="beeui-lang-active">RU</strong>' in response.text
