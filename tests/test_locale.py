from __future__ import annotations

from beeagent_module.interfaces.ui.locale import (
    format_rop_email_count,
    format_rop_lead_count,
    format_rop_month,
    rop_initials,
    t,
)


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


def test_team_leaderboard_locale_helpers_are_os_locale_independent() -> None:
    assert t("Team leaderboard", "en") == "Team leaderboard"
    assert t("Team leaderboard", "ru") == "Рейтинг команды"
    assert format_rop_month("2026-09", "en") == "September 2026"
    assert format_rop_month("2026-09", "ru") == "Сентябрь 2026"
    assert format_rop_email_count(1, "en") == "1 email"
    assert format_rop_email_count(22, "ru") == "22 письма"
    assert [
        format_rop_lead_count(value, "ru") for value in (1, 2, 5, 11, 21, 22, 25)
    ] == [
        "1 лид",
        "2 лида",
        "5 лидов",
        "11 лидов",
        "21 лид",
        "22 лида",
        "25 лидов",
    ]
    assert format_rop_lead_count(1, "en") == "1 lead"
    assert format_rop_lead_count(2, "en") == "2 leads"
    assert t("of plan", "ru") == "от плана"
    assert t("of plan", "en") == "of plan"
    assert rop_initials("Куаныш Тилесбаев") == "КТ"
    assert rop_initials("123") == "?"
