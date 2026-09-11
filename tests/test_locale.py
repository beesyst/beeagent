from __future__ import annotations

from beeagent_module.interfaces.ui.locale import t


def test_beeagent_locale_labels_cover_run_list_and_needs_review() -> None:
    assert t("BeeAgent Dashboard", "ru") == "Дашборд BeeAgent"
    assert t("Read-only operator dashboard", "ru") == "Read-only дашборд оператора"
    assert t("Runs", "ru") == "Запуски"
    assert t("Run history", "ru") == "История запусков"
    assert t("Needs review", "ru") == "Письма на проверку"
    assert t("Run list", "ru") == "Список запусков"
    assert t("Run ID", "ru") == "ID запуска"
    assert t("Status", "ru") == "Статус"
    assert t("Started", "ru") == "Начат"
    assert t("Completed", "ru") == "Завершён"
    assert t("Open run", "ru") == "Открыть запуск"
    assert t("Adapter-backed product overview", "ru") == "Обзор продуктовой консоли"
    assert t("Adapter-backed run list", "ru") == "Список запусков"


def test_source_mail_server_labels_are_localized() -> None:
    assert t("Mail server", "en") == "Mail server"
    assert t("Mail server", "ru") == "Почтовый сервер"
