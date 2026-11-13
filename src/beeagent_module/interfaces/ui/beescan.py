import re
from contextvars import ContextVar
from typing import Any

from beeagent_module.integrations.beescan.web import PROFILES, principal

web_actor: ContextVar[dict[str, Any] | None] = ContextVar(
    "beescan_web_actor", default=None
)


def is_beescan_run(storage, run_id):
    if not isinstance(run_id, str):
        return False
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", run_id) is None:
        return False
    if run_id.startswith(("web-", "dast-", "investigation-", "capture-")):
        return True
    path = storage / "runs" / run_id
    module = path / "module-beescan"
    return path.is_symlink() or module.exists() or module.is_symlink()


def hide_beescan(storage, data):
    if "runs" in data:
        data["runs"] = [
            row
            for row in data["runs"]
            if not is_beescan_run(storage, row.get("run_id"))
        ]
        data["total_runs"] = len(data["runs"])
    if "recent_run_ids" in data:
        hidden = (
            sum(is_beescan_run(storage, p.name) for p in (storage / "runs").iterdir())
            if (storage / "runs").is_dir()
            else 0
        )
        data["total_runs"] -= hidden
        data["recent_run_ids"] = [
            value
            for value in data["recent_run_ids"]
            if not is_beescan_run(storage, value)
        ]
        data["summary"]["total_runs"] = data["total_runs"]
        latest = data.get("latest_run")
        if latest and is_beescan_run(storage, latest.get("run_id")):
            data["latest_run"] = None
            for key in ("latest_run_id", "latest_run_status"):
                data["summary"].pop(key, None)
        if data.get("kpi_items"):
            data["kpi_items"][0]["value"] = data["total_runs"]
    return data


def _workspace_context(service, query, actor):
    from datetime import UTC, datetime

    from beeagent_module.integrations.beescan.investigation import InvestigationPolicy

    settings = service.reload_settings()
    actor_id = principal(settings, actor)
    if set(query) - {"lang", "run_id", "q", "tab", "page", "status", "sort"}:
        raise ValueError("invalid_beescan_query")
    if query.get("tab", "investigation") not in {"investigation", "results"}:
        raise ValueError("invalid_beescan_tab")
    search = query.get("q", "")
    if type(search) is not str or len(search) > 128:
        raise ValueError("invalid_beescan_search")
    page = query.get("page", "1")
    if not isinstance(page, str) or not page.isdecimal() or not 1 <= int(page) <= 10000:
        raise ValueError("invalid_beescan_page")
    status_filter = query.get("status", "")
    if status_filter not in {
        "",
        "QUEUED",
        "RUNNING",
        "CANDIDATE",
        "NO_MATCH",
        "PARTIAL",
        "ERROR",
        "REFUSED",
        "TIMEOUT",
        "INCONCLUSIVE",
        "MATCH",
    }:
        raise ValueError("invalid_beescan_status")
    sort = query.get("sort", "recent")
    if sort not in {"recent", "title"}:
        raise ValueError("invalid_beescan_sort")
    ru = query.get("lang") == "ru"
    labels = {
        "title": ("Исследование BeeScan", "BeeScan investigation"),
        "cases": ("Кейсы", "Cases"),
        "new": ("Новый кейс", "New Case"),
        "search": ("Поиск исследований", "Search Cases"),
        "target": ("Цель", "Target"),
        "task": ("Задача", "Task"),
        "mode": ("Режим", "Effort mode"),
        "start": ("Начать", "Start"),
        "resume": ("Продолжить исходную задачу", "Resume original task"),
        "inspect": ("Обновить / Просмотр", "Refresh / Inspect"),
        "report": ("Отчёт и доказательства", "Report and evidence"),
        "context": ("Контекст исследования", "Case context"),
        "metrics": ("Метрики", "Metrics"),
        "findings": ("Находки", "Findings"),
        "operator": ("Оператор", "Operator"),
        "unavailable": ("Недоступно", "Unavailable"),
        "empty": (
            "Введите цель и задачу для нового исследования.",
            "Enter a Target and Task to start an investigation.",
        ),
        "pending": (
            "Выполняется. Данные обновляются автоматически.",
            "Execution in progress. Saved evidence refreshes automatically.",
        ),
        "failed": (
            "Запрос отклонён или данные недоступны. Обновите страницу.",
            "Request refused or evidence unavailable. Refresh the page.",
        ),
        "disabled": (
            "Выполнение недоступно: проверьте права и текущее разрешение.",
            "Execution unavailable: check permissions and current approval.",
        ),
        "legacy": (
            "Исходная задача не аутентифицирована; автоматическое продолжение недоступно.",
            "Original intake unavailable; automatic Resume is unavailable.",
        ),
        "continuation": (
            "Продолжение использует исходную цель, задачу и режим. Для другой задачи создайте новое исследование.",
            "Resume uses the original Target, Task and mode. Start a new Case for a different objective.",
        ),
    }
    labels = {key: values[0 if ru else 1] for key, values in labels.items()}
    config = settings["beescan"]["investigation"]
    dynamic = "target_policy" in settings["beescan"]
    approval = config.get("approval") or {}
    transport = approval.get("transport", {})
    target_approved = False
    try:
        InvestigationPolicy.from_config(approval).authorize(
            transport.get("origin"), at=datetime.now(UTC)
        )
        target_approved = True
    except PermissionError, ValueError, TypeError, KeyError:
        pass
    if dynamic:
        from beeagent_module.integrations.beescan.policy import target_exclusions

        target_exclusions(settings)
        target_approved = True
        labels["disabled"] = (
            "Выполнение недоступно: проверьте права и runtime."
            if ru
            else "Execution unavailable: check permissions and runtime."
        )
    enabled = False
    try:
        principal(settings, actor, execute=True)
        web = config.get("web", {})
        if (
            web.get("enabled") is True
            and actor_id in web.get("principal_ids", [])
            and target_approved
        ):
            enabled = config.get("enabled") is True and any(
                item.get("id") == "beescan" and item.get("enabled") is True
                for item in settings.get("modules", {}).get("registry", [])
            )
    except PermissionError, ValueError, TypeError, KeyError:
        pass
    selected = service.inspect(query["run_id"], actor) if query.get("run_id") else None
    records = service.history(actor)
    records = [
        row
        for row in records
        if search.casefold()
        in (
            row.get("display_title", row["case_id"])
            + " "
            + row["status"]
            + " "
            + (row["intake"]["target"] if row["intake"] else "")
        ).casefold()
    ]
    if status_filter:
        records = [row for row in records if row["status"] == status_filter]
    if sort == "title":
        records.sort(
            key=lambda row: (
                row.get("display_title", row["case_id"])
            ).casefold()
        )
    search_empty = bool(search and not records)
    total_records = len(records)
    offset = (int(page) - 1) * 25
    records = records[offset : offset + 25]
    return {
        "search_empty": search_empty,
        "title": labels["title"],
        "labels": labels,
        "selected": selected,
        "records": records,
        "page": int(page),
        "total_records": total_records,
        "status_filter": status_filter,
        "sort": sort,
        "search": search,
        "enabled": enabled,
        "nonce": service.nonce(actor),
        "target": "" if dynamic else transport.get("origin", ""),
        "task_chars_max": config["task_chars_max"],
        "modes": list(PROFILES),
        "approval": {
            key: transport.get(key, "unavailable")
            for key in (
                "origin",
                "scope_id",
                "mission_id",
                "target_id",
                "approved",
                "excluded",
                "valid_from",
                "expires_at",
                "time_budget_seconds",
            )
        },
        "ceilings": config.get("adaptive", {}),
        "dast": settings["beescan"].get("dast", {}),
        "target_approved": target_approved,
    }


def presentation(selected, config, locale="en", *, settings=None):
    ru = locale == "ru"
    messages = []
    intake = selected["intake"]
    if intake:
        messages.append(
            {
                "id": selected["case_id"] + ":intake",
                "sender": "operator",
                "name": "Оператор" if ru else "Operator",
                "text": intake["task"],
                "timestamp": "",
                "status": "",
            }
        )
    messages.extend(
        {
            "id": event["id"],
            "sender": "host",
            "name": event["author"],
            "text": event["text"],
            "timestamp": "",
            "status": "",
        }
        for event in selected["events"]
    )
    metrics = selected["metrics"]
    limits = PROFILES[selected["mode"]]
    configured = config.get("adaptive", {}).get("max_requests")
    maximum = (
        min(limits["max_requests"], configured) if type(configured) is int else None
    )
    values = [{"id": "beescan-status", "value": selected["status"]}]
    requests = selected["request_count"]
    if requests is not None:
        values.append(
            {
                "id": "beescan-requests",
                "value": f"{requests} / {maximum}"
                if maximum is not None
                else str(requests),
            }
        )
    if selected["evidence_authenticated"]:
        values.append(
            {"id": "beescan-findings", "value": str(len(selected["findings"]))}
        )
    elapsed = metrics.get("elapsed_seconds")
    if type(elapsed) in {int, float}:
        values.append(
            {"id": "beescan-time", "value": f"{elapsed:.1f} {'с' if ru else 's'}"}
        )
    return {
        "state": selected["status"],
        "context": inspection(selected, config, locale, settings=settings),
        "messages": messages,
        "values": values,
        "complete": selected["status"] in {"ERROR", "REFUSED", "TIMEOUT"}
        or (
            selected["evidence_authenticated"]
            and selected["status"] not in {"QUEUED", "RUNNING"}
        ),
    }


def inspection(selected, config, locale="en", *, settings=None):
    from datetime import UTC, datetime

    from beeagent_module.integrations.beescan.investigation import InvestigationPolicy

    ru = locale == "ru"
    unavailable = "Недоступно" if ru else "Unavailable"

    def item(identity, label, value, detail=""):
        return {
            "id": identity,
            "label": label,
            "value": str(value) if value is not None else unavailable,
            "detail": detail,
        }

    approval = config.get("approval") or {}
    transport = approval.get("transport", {})
    approved = False
    try:
        InvestigationPolicy.from_config(approval).authorize(
            transport.get("origin"), at=datetime.now(UTC)
        )
        approved = True
    except PermissionError, ValueError, TypeError, KeyError:
        pass
    intake = selected.get("intake") if selected else None
    sections = [
        {
            "id": "authorization",
            "title": "Цель и разрешение" if ru else "Target and approval",
            "items": [
                item(
                    "target",
                    "Цель кейса" if ru else "Case Target",
                    intake["target"]
                    if intake
                    else (None if selected else transport.get("origin")),
                ),
                item(
                    "scope",
                    "Текущая область" if ru else "Current Scope",
                    transport.get("scope_id"),
                    str(transport.get("origin", unavailable)),
                ),
                item(
                    "approval",
                    "Текущее разрешение" if ru else "Current approval",
                    ("Да" if ru else "Yes") if approved else ("Нет" if ru else "No"),
                    str(transport.get("valid_from", unavailable))
                    + " — "
                    + str(transport.get("expires_at", unavailable)),
                ),
            ],
        }
    ]
    dynamic = settings is not None and "target_policy" in settings.get("beescan", {})
    if dynamic:
        sections[0] = {
            "id": "execution",
            "title": "Выполнение" if ru else "Execution",
            "items": [
                item(
                    "target",
                    "Цель кейса" if ru else "Case Target",
                    intake["target"] if intake else None,
                ),
                item(
                    "execution-status",
                    "Состояние" if ru else "State",
                    selected["status"]
                    if selected
                    else ("Готово к запуску" if ru else "Ready for intake"),
                    selected.get("reason") or "" if selected else "",
                ),
                item(
                    "execution-policy",
                    "Управление" if ru else "Execution policy",
                    "Серверная политика" if ru else "Server managed",
                ),
            ],
        }
    if settings is not None and not dynamic:
        import os

        from beeagent_module.integrations.beescan.dast import _current

        dast_approved = False
        profile = ""
        try:
            active = _current(settings)
            now = datetime.now(UTC)
            active.transport.authorize(
                active.transport.intent(), operator_uid=os.getuid(), at=now
            )
            dast_approved = (
                active.approved
                and active.transport.origin == transport.get("origin")
                and now.timestamp() + active.seconds
                <= active.transport.expires_at.timestamp()
            )
            profile = active.profile
        except PermissionError, ValueError, TypeError, KeyError, OSError:
            pass
        sections[0]["items"].append(
            item(
                "dast",
                "Независимое разрешение DAST" if ru else "Independent DAST approval",
                ("Да" if ru else "Yes") if dast_approved else ("Нет" if ru else "No"),
                profile,
            )
        )
    if not selected:
        return {"title": "Контекст" if ru else "Context", "sections": sections}
    sections.insert(
        0,
        {
            "id": "case",
            "title": "Кейс" if ru else "Case",
            "items": [
                item("case", "Case", selected["case_id"]),
                item(
                    "status",
                    "Статус" if ru else "Status",
                    selected["status"],
                    selected.get("reason") or "",
                ),
                item("mode", "Режим" if ru else "Mode", selected["mode"].title()),
            ],
        },
    )
    sections.extend(
        [
            {
                "id": "steps",
                "title": "Шаги" if ru else "Steps",
                "items": [
                    item(
                        "step-" + str(index),
                        str(index + 1) + ". " + step["step"],
                        step["status"],
                        step["tool"]
                        + " · "
                        + ("Запросы: " if ru else "Requests: ")
                        + str(step["request_count"]),
                    )
                    for index, step in enumerate(selected["steps"][-64:])
                ]
                or [item("steps-empty", "Шаги" if ru else "Steps", unavailable)],
            },
            {
                "id": "findings",
                "title": "Находки / Кандидаты" if ru else "Findings / Candidates",
                "items": [
                    item(
                        finding["finding_id"],
                        finding["title"],
                        finding["status"],
                        finding["finding_id"],
                    )
                    for finding in selected["findings"]
                ]
                or [
                    item(
                        "findings-empty",
                        "Находки" if ru else "Findings",
                        "0" if selected["evidence_authenticated"] else unavailable,
                    )
                ],
            },
            {
                "id": "metrics",
                "title": "Метрики" if ru else "Metrics",
                "items": [
                    item(
                        "requests",
                        "Запросы" if ru else "Requests",
                        selected["request_count"],
                    ),
                    item(
                        "elapsed",
                        "Время, с" if ru else "Elapsed, s",
                        selected["metrics"].get("elapsed_seconds"),
                    ),
                    item(
                        "completed",
                        "Завершено шагов" if ru else "Completed steps",
                        selected["completed_steps"],
                    ),
                    *[
                        item(key, label, selected["metrics"].get(key))
                        for key, label in (
                            ("ai_calls", "AI-вызовы" if ru else "AI calls"),
                            ("tokens", "Токены" if ru else "Tokens"),
                            ("cost", "Стоимость" if ru else "Cost"),
                        )
                    ],
                ],
            },
            {
                "id": "report",
                "title": "Отчёт и доказательства" if ru else "Report and evidence",
                "items": [
                    item(
                        "result",
                        "Результат" if ru else "Result",
                        selected["report"]["answer"] or selected["report"]["reason"],
                        " ".join(selected["report"]["limitations"]),
                    ),
                    item(
                        "evidence",
                        "Доказательства" if ru else "Evidence",
                        ", ".join(selected["evidence_refs"]) or unavailable,
                    ),
                ],
            },
        ]
    )
    from urllib.parse import urlsplit

    advanced = "\n".join(
        section["title"] + ": " + "; ".join(
            entry["label"] + " = " + entry["value"]
            for entry in section["items"]
        )
        for section in sections
    )[:4096]
    return {
        "title": "Контекст" if ru else "Context",
        "sections": [{
            "id": "summary",
            "title": "Сводка" if ru else "Summary",
            "items": [
                item("target", "Цель" if ru else "Target", urlsplit(intake["target"]).netloc if intake else unavailable),
                item("status", "Статус" if ru else "Status", selected["status"], selected.get("reason") or ""),
                item("operation", "Действие" if ru else "Operation", selected["steps"][-1]["step"] if selected["steps"] else unavailable),
                item("requests", "Запросы" if ru else "Requests", selected["request_count"]),
                item("findings", "Находки" if ru else "Findings", len(selected["findings"])),
                item("report", "Отчёт" if ru else "Report", selected.get("report_readiness", unavailable)),
                item("advanced", "Подробности" if ru else "Details", "Технические сведения" if ru else "Technical details", advanced),
            ],
        }],
    }


def workspace(service, query, actor):
    from urllib.parse import urlencode

    model = _workspace_context(service, query, actor)
    selected = model["selected"]
    labels = model["labels"]
    locale = "ru" if query.get("lang") == "ru" else "en"
    ru = locale == "ru"
    config = service.reload_settings()["beescan"]["investigation"]
    tab = query.get("tab", "investigation")
    href = "/beescan?" + urlencode({"lang": locale, "tab": tab})
    history_href = href + "&" + urlencode({
        "q": model["search"],
        "status": model["status_filter"],
        "sort": model["sort"],
        "page": model["page"],
    })
    if tab == "results":
        table_query = {
            "lang": locale,
            "tab": "results",
            **({"q": model["search"]} if model["search"] else {}),
            **({"status": model["status_filter"]} if model["status_filter"] else {}),
            **({"sort": model["sort"]} if model["sort"] != "recent" else {}),
        }
        table_href = "/beescan?" + urlencode(table_query)
        pages = max(1, (model["total_records"] + 24) // 25)
        context = inspection(
            selected, config, locale, settings=service.reload_settings()
        )
        layout = [
            {
                "type": "data_table",
                "width": 12,
                "id": "beescan-cases",
                "title": labels["cases"],
                "mobile": "md",
                "toolbar": {
                    "hidden": {"lang": locale, "tab": "results"},
                    "fields": [
                        {"name": "q", "type": "text", "label": labels["search"], "value": model["search"]},
                        {
                            "name": "status",
                            "type": "select",
                            "label": "Статус" if ru else "Status",
                            "value": model["status_filter"],
                            "options": [
                                {"value": "", "label": "Все" if ru else "All"},
                                *[{"value": value, "label": value} for value in ("CANDIDATE", "NO_MATCH", "MATCH", "PARTIAL", "ERROR", "REFUSED", "TIMEOUT", "INCONCLUSIVE")],
                            ],
                        },
                        {
                            "name": "sort",
                            "type": "select",
                            "label": "Сортировка" if ru else "Sort",
                            "value": model["sort"],
                            "options": [
                                {"value": "recent", "label": "Сначала новые" if ru else "Recent first"},
                                {"value": "title", "label": "Название" if ru else "Title"},
                            ],
                        },
                    ],
                    "apply": {"label": "Применить" if ru else "Apply", "href": "/beescan"},
                },
                "columns": [
                    {"key": "title", "label": "Название" if ru else "Case title", "cell": "text"},
                    {"key": "target", "label": labels["target"], "cell": "text"},
                    {"key": "created", "label": "Дата" if ru else "Created", "cell": "text"},
                    {"key": "mode", "label": labels["mode"], "cell": "text"},
                    {"key": "status", "label": "Статус" if ru else "Status", "cell": "text"},
                    {"key": "findings", "label": "Находки" if ru else "Findings", "cell": "text"},
                    {"key": "report", "label": "Отчёт" if ru else "Report", "cell": "text"},
                    {"key": "actions", "label": "", "cell": "actions"},
                ],
                "rows": [
                    {
                        "title": {"label": row.get("display_title", row["case_id"])},
                        "created": {"label": row.get("created_at", "—")},
                        "target": {"label": row["intake"]["target"] if row["intake"] else "—"},
                        "mode": {"label": row["mode"].title()},
                        "status": {"label": row["status"]},
                        "findings": {"label": str(len(row["findings"]))},
                        "report": {"label": row.get("report_readiness", "unavailable")},
                        "actions": [
                            {
                                "href": table_href + "&" + urlencode({"run_id": row["run_id"], "page": model["page"]}),
                                "label": "Подробнее" if ru else "Details",
                            }
                            ,{
                                "action_id": "beescan_rename",
                                "label": "Переименовать" if ru else "Rename",
                                "flow": "direct_execute",
                                "args": {"case_id": row["case_id"]},
                                "fields": [{"name": "title", "label": "Название" if ru else "Title", "type": "text", "required": True, "max_length": 160, "value": row.get("display_title", row["case_id"])[:160]}],
                            },
                            {
                                "action_id": "beescan_archive",
                                "label": "Архивировать" if ru else "Archive",
                                "flow": "direct_execute",
                                "confirmation": "Archive Case?",
                                "args": {"case_id": row["case_id"]},
                                "fields": [{"name": "confirmation", "label": "Введите ARCHIVE" if ru else "Type ARCHIVE", "type": "text", "required": True, "value": ""}],
                            },
                        ],
                    }
                    for row in model["records"]
                ],
                "pagination": {
                    "label": "Страницы" if ru else "Pages",
                    "pages": [
                        {
                            "number": number,
                            "label": str(number),
                            "href": table_href + "&" + urlencode({"page": number}),
                            "active": number == model["page"],
                        }
                        for number in range(1, pages + 1)
                    ],
                },
            }
        ]
        if not selected:
            layout.append(
                {
                    "type": "state_grid",
                    "width": 12,
                    "title": "Результаты" if ru else "Results",
                    "items": [
                        {
                            "label": labels["cases"],
                            "value": "Выберите кейс для просмотра результатов."
                            if ru
                            else "Select a Case to inspect saved results.",
                        }
                    ],
                }
            )
        else:
            layout.extend(
                {
                    "type": "state_grid",
                    "width": 6,
                    "title": section["title"],
                    "items": [
                        {
                            "label": item["label"],
                            "value": item["value"]
                            + (" · " + item["detail"] if item["detail"] else ""),
                        }
                        for item in section["items"]
                    ],
                }
                for section in context["sections"]
            )
        layout.extend(review_workspace(service, selected, actor, locale))
        return {"layout": layout}
    layout = []
    normalized = (
        presentation(selected, config, locale, settings=service.reload_settings())
        if selected
        else None
    )
    intake = selected["intake"] if selected else None
    disabled = not model["enabled"] or bool(
        selected and (not intake or not selected["evidence_authenticated"])
    )
    fields = []
    args = {"nonce": model["nonce"]}
    if selected:
        args.update(
            {key: intake[key] if intake else "" for key in ("target", "task", "mode")}
        )
        args["case_id"] = selected["case_id"]
    else:
        fields = [
            {
                "name": "target",
                "label": labels["target"],
                "type": "target",
                "required": True,
                "value": model["target"],
                "max_length": 2048,
                "protocols": ["http", "https"],
                "origin_only": True,
                "invalid_message": (
                    "Укажите публичный HTTP(S) origin. Другие типы целей пока не поддерживаются."
                    if ru
                    else "Enter a public HTTP(S) origin. Other target types are not supported yet."
                ),
            },
            {
                "name": "mode",
                "label": labels["mode"],
                "type": "segmented",
                "required": True,
                "value": "quick",
                "options": [
                    {"value": mode, "label": mode.title()} for mode in model["modes"]
                ],
            },
            {
                "name": "task",
                "label": labels["task"],
                "type": "textarea",
                "required": True,
                "value": "",
                "max_length": model["task_chars_max"],
                "invalid_message": "Введите задачу." if ru else "Enter a Task.",
            },
        ]
    fields.sort(key=lambda field: {"task": 0, "target": 1, "mode": 2}[field["name"]])
    hint = labels["continuation"] if selected else ""
    if not model["enabled"]:
        hint = labels["disabled"] + " " + hint
    if selected and not intake:
        hint = labels["legacy"] + " " + hint
    layout.append(
        {
            "type": "chat_workspace",
            "id": "beescan",
            "width": 12,
            "title": (intake["task"][:100] + " · " + selected["mode"].title())
            if intake
            else labels["new"],
            "state": selected["status"] if selected else "",
            "labels": {
                "history": labels["cases"],
                "new": labels["new"],
                "search": labels["search"],
                "failed": labels["failed"],
                "pending": labels["pending"],
                "conversation": "Диалог" if ru else "Conversation",
                "context": labels["context"],
                "close": "Закрыть" if ru else "Close",
            },
            "new_href": href,
            "empty_message": labels["empty"],
            "history_notice": ("Кейсы не найдены." if ru else "No matching Cases.")
            if model["search_empty"] or not model["records"]
            else "",
            "search": {
                "href": "/beescan",
                "name": "q",
                "value": model["search"],
                "hidden": {
                    "lang": locale,
                    "tab": tab,
                    **({"run_id": selected["case_id"]} if selected else {}),
                },
            },
            "history": [
                {
                    "id": row["case_id"],
                    "title": row.get("display_title", row["case_id"]),
                    "href": history_href + "&" + urlencode({"run_id": row["run_id"]}),
                    "active": bool(selected and selected["case_id"] == row["case_id"]),
                    "status": row["status"],
                }
                for row in model["records"]
            ],
            "messages": normalized["messages"] if normalized else [],
            "context": inspection(
                selected, config, locale, settings=service.reload_settings()
            ),
            "composer": {
                "action_id": "beescan_resume" if selected else "beescan_start",
                "label": labels["resume"] if selected else labels["start"],
                "args": args,
                "fields": fields,
                "variant": "compact",
                "submit_on_enter": True,
                "menu": {
                    "label": "Другие действия" if ru else "More actions",
                    "items": [
                        "Добавить фото и файлы" if ru else "Add photo/files",
                        "Импорт" if ru else "Import",
                        "Экспорт" if ru else "Export",
                    ],
                },
                "hint": hint,
                "disabled": disabled,
                "navigate": {
                    "href": history_href,
                    "param": "run_id",
                    "result_key": "run_id",
                },
            },
            "refresh": {
                "href": "/api/beescan/status?"
                + urlencode({"run_id": selected["run_id"]}),
                "interval_ms": 3000,
                "max_attempts": 300,
            }
            if selected and normalized is not None and not normalized["complete"]
            else None,
        }
    )
    return {"layout": layout}


def review_workspace(service, selected, actor, locale):
    from urllib.parse import urlencode

    from beeagent_module.integrations.beescan.review import (
        ATTESTATION,
        _web_authority,
        inspect_web_reports,
    )

    if (
        not selected
        or not selected["evidence_authenticated"]
        or selected["case_status"] != "CANDIDATE"
    ):
        return []
    ru = locale == "ru"
    mutable = True
    try:
        _web_authority(service, service.reload_settings(), actor, mutate=True)
    except PermissionError:
        mutable = False
    translated = {
        "Finding": "Находка",
        "Review": "Проверка",
        "Readiness": "Готовность",
        "Submission eligible": "Готов к ручной отправке",
        "Missing information": "Недостающие данные",
        "Evidence": "Доказательства",
        "Target": "Цель",
        "Endpoint": "Endpoint",
        "Parameters": "Параметры",
        "Prerequisites": "Предусловия",
        "Reproduction": "Воспроизведение",
        "Expected": "Ожидаемое поведение",
        "Observed": "Наблюдаемое поведение",
        "Impact": "Влияние",
        "Program requirements": "Требования программы",
        "Remediation": "Рекомендации",
    }
    rows, links, previews = [], [], []
    for finding in selected["findings"]:
        status = inspect_web_reports(
            service, selected["case_id"], finding["finding_id"], actor
        )
        args = {"case_id": selected["case_id"], "finding_id": finding["finding_id"]}
        actions = []
        if mutable and status["review_id"] is None:
            actions.append(
                {
                    "action_id": "beescan_review",
                    "label": "Проверить" if ru else "Review",
                    "flow": "direct_execute",
                    "args": args,
                    "fields": [
                        {
                            "name": "disposition",
                            "label": "Решение" if ru else "Disposition",
                            "type": "radio",
                            "required": True,
                            "value": "inconclusive",
                            "options": [
                                {"value": value, "label": value.upper()}
                                for value in ("inconclusive", "rejected", "verified")
                            ],
                        },
                        {
                            "name": "decision_basis",
                            "label": "Основание решения" if ru else "Decision basis",
                            "type": "text",
                            "required": True,
                            "max_length": 512,
                            "value": "",
                        },
                        {
                            "name": "evidence_text",
                            "label": "Независимые доказательства без секретов"
                            if ru
                            else "Independent evidence without secrets",
                            "type": "text",
                            "required": False,
                            "max_length": 4096,
                            "value": "",
                        },
                        {
                            "name": "independence_attestation",
                            "label": "Подтверждение независимости"
                            if ru
                            else "Independence attestation",
                            "type": "radio",
                            "required": True,
                            "value": "unconfirmed",
                            "options": [
                                {
                                    "value": "unconfirmed",
                                    "label": "Не подтверждено" if ru else "Unconfirmed",
                                },
                                {
                                    "value": ATTESTATION,
                                    "label": "Я собрал доказательства независимо от автоматического исследования для этой находки."
                                    if ru
                                    else ATTESTATION,
                                },
                            ],
                        },
                    ],
                }
            )
        if mutable:
            fields = [
                {
                    "name": key,
                    "label": translated.get(label, label) if ru else label,
                    "type": "text",
                    "required": False,
                    "max_length": maximum,
                    "value": "",
                }
                for key, label, maximum in (
                    ("prerequisites", "Предусловия" if ru else "Prerequisites", 6144),
                    (
                        "reproduction_steps",
                        "Шаг воспроизведения" if ru else "Reproduction step",
                        6144,
                    ),
                    (
                        "expected_behavior",
                        "Ожидаемое поведение" if ru else "Expected behavior",
                        1024,
                    ),
                    (
                        "observed_behavior",
                        "Наблюдаемое поведение" if ru else "Observed behavior",
                        1024,
                    ),
                    (
                        "impact",
                        "Подтверждённое влияние" if ru else "Supported impact",
                        1024,
                    ),
                    ("remediation", "Рекомендации" if ru else "Remediation", 1024),
                    (
                        "program_requirements",
                        "Требования программы" if ru else "Program requirements",
                        1024,
                    ),
                )
            ]
            fields.extend(
                {
                    "name": key,
                    "label": translated.get(label, label) if ru else label,
                    "type": "radio",
                    "required": True,
                    "value": "false",
                    "options": [
                        {
                            "value": "false",
                            "label": "Не подтверждено" if ru else "Unconfirmed",
                        },
                        {
                            "value": "true",
                            "label": "Подтверждаю" if ru else "I confirm",
                        },
                    ],
                }
                for key, label in (
                    (
                        "reproduction_confirmed",
                        "Воспроизведение" if ru else "Reproduction",
                    ),
                    ("impact_confirmed", "Влияние" if ru else "Impact"),
                    (
                        "program_confirmed",
                        "Правила программы" if ru else "Program rules",
                    ),
                )
            )
            actions.append(
                {
                    "action_id": "beescan_report_prepare",
                    "flow": "direct_execute",
                    "label": "Подготовить отчёт" if ru else "Prepare report",
                    "args": {**args, "review_id": status["review_id"] or ""},
                    "fields": fields,
                }
            )
        latest = status["reports"][-1] if status["reports"] else None
        rows.append(
            {
                "finding": {"label": finding["finding_id"]},
                "review": {"label": status["review_disposition"]},
                "readiness": {
                    "label": latest["report_readiness"] if latest else "unavailable"
                },
                "eligible": {
                    "label": str(latest["submission_eligible"]) if latest else "False"
                },
                "missing": {
                    "label": ", ".join(latest["missing_information"])
                    if latest
                    else "reproduction, impact, program_requirements"
                },
                "evidence": {"label": ", ".join(status.get("evidence_refs", []))},
                "actions": actions,
            }
        )
        if latest:
            import json

            report_data = json.loads(
                inspect_web_reports(
                    service,
                    selected["case_id"],
                    finding["finding_id"],
                    actor,
                    report_run_id=latest["report_run_id"],
                    artifact="json",
                )
            )
            assertions = report_data["operator_assertions"]
            previews.append(
                {
                    "type": "state_grid",
                    "width": 12,
                    "title": "Предпросмотр отчёта" if ru else "Report preview",
                    "items": [
                        {
                            "label": translated.get(label, label) if ru else label,
                            "value": value or ("Недоступно" if ru else "Unavailable"),
                        }
                        for label, value in (
                            ("Target", report_data["origin"]),
                            ("Endpoint", report_data["endpoint_path"]),
                            ("Parameters", ", ".join(report_data["parameter_names"])),
                            ("Prerequisites", "; ".join(assertions["prerequisites"])),
                            (
                                "Reproduction",
                                "; ".join(assertions["reproduction_steps"]),
                            ),
                            ("Expected", assertions["expected_behavior"]),
                            ("Observed", assertions["observed_behavior"]),
                            ("Impact", assertions["impact"]),
                            (
                                "Program requirements",
                                assertions["program_requirements"],
                            ),
                            ("Remediation", assertions["remediation"]),
                        )
                    ],
                }
            )
        for report in status["reports"]:
            for output in (
                "json",
                "markdown",
                *(("draft",) if report["submission_eligible"] else ()),
            ):
                links.append(
                    {
                        "label": str(report["revision"] + 1) + " · " + output.upper(),
                        "href": "/api/beescan/report?"
                        + urlencode(
                            {
                                **args,
                                "report_run_id": report["report_run_id"],
                                "format": output,
                                "download": "true",
                            }
                        ),
                    }
                )
    if not rows:
        return []
    layout = [
        {
            "type": "data_table",
            "width": 12,
            "id": "beescan-reviews",
            "title": "Независимая проверка и отчёты"
            if ru
            else "Independent review and reports",
            "columns": [
                {
                    "key": key,
                    "label": translated.get(label, label) if ru else label,
                    "cell": "actions" if key == "actions" else "text",
                }
                for key, label in (
                    ("finding", "Finding"),
                    ("review", "Review"),
                    ("readiness", "Readiness"),
                    ("eligible", "Submission eligible"),
                    ("missing", "Missing information"),
                    ("evidence", "Evidence"),
                    ("actions", ""),
                )
            ],
            "rows": rows,
        }
    ]
    layout.extend(previews)
    if links:
        layout.append(
            {
                "type": "quick_links",
                "width": 12,
                "title": "Скачать отчёты" if ru else "Download reports",
                "items": links,
            }
        )
    return layout
