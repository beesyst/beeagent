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
    if set(query) - {"lang", "run_id", "q", "tab"}:
        raise ValueError("invalid_beescan_query")
    if query.get("tab", "investigation") not in {"investigation", "results"}:
        raise ValueError("invalid_beescan_tab")
    search = query.get("q", "")
    if type(search) is not str or len(search) > 128:
        raise ValueError("invalid_beescan_search")
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
    if selected and not any(row["case_id"] == selected["case_id"] for row in records):
        records.insert(0, selected)
    records = [
        row
        for row in records
        if search.casefold()
        in (
            (row["intake"]["task"] if row["intake"] else row["case_id"])
            + " "
            + row["status"]
        ).casefold()
    ]
    search_empty = bool(search and not records)
    if selected and not any(row["case_id"] == selected["case_id"] for row in records):
        records.insert(0, selected)
    records = records[:25]
    return {
        "search_empty": search_empty,
        "title": labels["title"],
        "labels": labels,
        "selected": selected,
        "records": records,
        "search": search,
        "enabled": enabled,
        "nonce": service.nonce(actor),
        "target": transport.get("origin", ""),
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
        "complete": selected["evidence_authenticated"]
        and selected["status"] not in {"QUEUED", "RUNNING"},
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
    if settings is not None:
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
    return {"title": "Контекст" if ru else "Context", "sections": sections}


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
    history_href = href + (
        "&" + urlencode({"q": model["search"]}) if model["search"] else ""
    )
    if tab == "results":
        context = inspection(
            selected, config, locale, settings=service.reload_settings()
        )
        layout = [
            {
                "type": "quick_links",
                "width": 12,
                "title": labels["cases"],
                "items": [
                    {
                        "label": (
                            row["intake"]["task"] if row["intake"] else row["case_id"]
                        )
                        + " · "
                        + row["status"],
                        "href": history_href
                        + "&"
                        + urlencode({"run_id": row["run_id"]}),
                    }
                    for row in model["records"]
                ],
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
                    "Укажите разрешённый HTTP(S) origin. Другие типы целей пока не поддерживаются."
                    if ru
                    else "Enter an approved HTTP(S) origin. Other target types are not supported yet."
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
                    "title": row["intake"]["task"] if row["intake"] else row["case_id"],
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
