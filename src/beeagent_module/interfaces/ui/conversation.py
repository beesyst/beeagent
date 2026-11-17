from urllib.parse import urlencode

from beeagent_module.integrations.beescan.web import principal

_CONTEXT_LABELS = {
    "target": ("Цель", "Target"),
    "scope": ("Область", "Scope"),
    "authority": ("Разрешение", "Authority reference"),
    "principal": ("Тестовый участник", "Test principal"),
    "observation": ("Наблюдение", "Observation"),
    "mode": ("Уровень", "Effort"),
    "profile": ("Профиль", "Profile"),
    "bearer": ("Bearer", "Bearer"),
    "cookie": ("Cookie", "Cookie"),
}


def presentation(view, locale="en"):
    ru = locale == "ru"
    context = []
    target = view["context"].get("target")
    if target or view["run_count"]:
        context = [
            {
                "id": "status",
                "label": "Статус" if ru else "Status",
                "value": view["status"],
            },
            {
                "id": "total",
                "label": "Всего запусков" if ru else "Total runs",
                "value": str(view["run_count"]),
            },
            {
                "id": "completed",
                "label": "Завершено (последние 25)" if ru else "Completed (latest 25)",
                "value": str(view["summary"]["completed"]),
            },
            {
                "id": "active",
                "label": "Активных запусков" if ru else "Active runs",
                "value": str(view["summary"]["active"]),
            },
        ]
        if target:
            context.insert(
                0,
                {"id": "target", "label": "Цель" if ru else "Target", "value": target},
            )
        for index, run in enumerate(view["summary"]["runs"]):
            href = "/beescan?" + urlencode(
                {"run_id": run["run_id"], "lang": locale, "tab": "results"}
            )
            facts = []
            if run["authenticated"]:
                if type(run.get("requests")) is int:
                    facts.append(
                        ("Запросы: " if ru else "Requests: ") + str(run["requests"])
                    )
                elapsed = run.get("elapsed_seconds")
                if type(elapsed) in {int, float}:
                    facts.append(
                        ("Время, с: " if ru else "Elapsed seconds: ") + f"{elapsed:.2f}"
                    )
                facts.append(
                    ("Находки: " if ru else "Findings: ")
                    + str(run["findings"])
                    + "; CANDIDATE: "
                    + str(run["candidates"])
                )
            else:
                facts.append(
                    "Доказательства ещё не подтверждены."
                    if ru
                    else "Evidence is not yet authenticated."
                )
            context.append(
                {
                    "id": "run-" + str(index),
                    "label": "Результаты · Review / Report / Export"
                    if ru
                    else "Results · Review / Report / Export",
                    "value": run["status"],
                    "detail": " ".join(facts),
                    "href": href,
                }
            )
    for item in context:
        item.setdefault("detail", "")
    return {
        "state": view["status"],
        "messages": [
            {
                "id": message["id"],
                "sender": message["sender"],
                "name": "",
                "text": message["text"],
                "timestamp": message["timestamp"],
                "status": "",
            }
            for message in view["messages"]
        ],
        "values": [],
        "complete": view["status"] not in {"QUEUED", "RUNNING"},
        "context": {
            "title": "Сводка исследования" if ru else "Investigation summary",
            "sections": [
                {"id": "case", "title": "Кейс" if ru else "Case", "items": context}
            ],
        }
        if context
        else None,
    }


def history_actions(host, row, actor, selected_href, new_href, selected_id, ru):
    args = {
        "case_id": row["case_id"],
        "nonce": host.management_nonce(row["case_id"], actor),
    }
    disabled = actor["role"] not in {"operator", "admin"}
    return [
        {
            "action_id": "beescan_rename",
            "label": "Переименовать" if ru else "Rename",
            "disabled": disabled,
            "args": args,
            "fields": [
                {
                    "name": "title",
                    "label": "Название" if ru else "Title",
                    "type": "text",
                    "value": row["display_title"][:160],
                    "max_length": 160,
                    "required": True,
                }
            ],
            "redirect": selected_href,
        },
        {
            "action_id": "beescan_archive",
            "label": "Удалить из списка" if ru else "Remove from list",
            "disabled": disabled or row["status"] in {"QUEUED", "RUNNING"},
            "args": {**args, "confirmation": "ARCHIVE"},
            "confirmation": (
                "Убрать кейс из истории? Подписанные доказательства сохранятся."
            )
            if ru
            else "Remove this Case from history? Signed evidence will be preserved.",
            "fields": [],
            "redirect": new_href if row["case_id"] == selected_id else selected_href,
        },
    ]


def workspace(host, query, actor):
    if set(query) - {
        "run_id",
        "lang",
        "q",
        "tab",
        "page",
        "message_page",
        "run_page",
        "status",
        "sort",
    }:
        raise ValueError("invalid_conversation_query")
    if query.get("tab", "investigation") not in {"investigation", "results"}:
        raise ValueError("invalid_conversation_tab")
    if query.get("sort", "recent") not in {"recent", "title"}:
        raise ValueError("invalid_conversation_sort")
    settings = host.reload_settings()
    principal(settings, actor)
    can_ask = actor["role"] in {"operator", "admin"}
    ru = query.get("lang") == "ru"
    locale = "ru" if ru else "en"
    field_labels = {key: pair[0 if ru else 1] for key, pair in _CONTEXT_LABELS.items()}
    case_id = query.get("run_id")
    message_page = query.get("message_page")
    if message_page is not None and (
        not message_page.isdecimal() or len(message_page) > 6
    ):
        raise ValueError("invalid_message_page")
    run_page = query.get("run_page")
    if run_page is not None and (not run_page.isdecimal() or len(run_page) > 6):
        raise ValueError("invalid_run_page")
    view = (
        host.conversations.view(
            case_id,
            actor,
            offset=int(message_page) * 8 if message_page is not None else None,
            run_offset=int(run_page) * 25 if run_page is not None else None,
        )
        if case_id
        else None
    )
    records = host.history(actor)
    search = query.get("q", "")
    if type(search) is not str or len(search) > 128:
        raise ValueError("invalid_conversation_search")
    records = [
        row for row in records if search.casefold() in row["display_title"].casefold()
    ]
    if query.get("sort") == "title":
        records.sort(key=lambda row: row["display_title"].casefold())
    status = query.get("status", "")
    if status not in {
        "",
        "READY",
        "QUEUED",
        "RUNNING",
        "CANDIDATE",
        "MATCH",
        "NO_MATCH",
        "PARTIAL",
        "ERROR",
        "REFUSED",
        "TIMEOUT",
        "INCONCLUSIVE",
    }:
        raise ValueError("invalid_conversation_status")
    if status:
        records = [row for row in records if row["status"] == status]
    page = query.get("page", "1")
    if not page.isdecimal() or not 1 <= int(page) <= 10000:
        raise ValueError("invalid_history_page")
    total = len(records)
    records = records[(int(page) - 1) * 25 : int(page) * 25]
    href = "/beescan?" + urlencode({"lang": locale})
    selected_href = href + "&" + urlencode({"run_id": case_id}) if case_id else href
    args = {"nonce": host.nonce(actor)}
    if view:
        args.update(case_id=case_id, revision=str(view["revision"]))
        args["nonce"] = host.conversations.nonce(actor, case_id, view["revision"])
    navigate = {"href": href, "param": "run_id", "result_key": "case_id"}

    def field(name, label, kind="text", value="", options=None, required=True):
        result = {
            "name": name,
            "label": label,
            "type": kind,
            "value": value,
            "max_length": 2048,
            "required": required,
        }
        if options:
            result["options"] = [
                {"value": key, "label": label} for key, label in options
            ]
        return result

    def action(identity, label, fields=None, extra=None):
        return {
            "action_id": identity,
            "label": label,
            "disabled": not can_ask,
            "args": {**args, **(extra or {})},
            "fields": fields or [],
            "navigate": navigate,
        }

    context = view["context"] if view else {}
    session_states = view["session_states"] if view is not None else {}
    profiles = [
        (p["profile_id"], p["profile_id"])
        for p in settings["beescan"].get("access_control", {}).get("profiles", [])
        if actor["user_id"] in p["operator_ids"]
    ]
    menu = [
        {
            "id": "target",
            "label": "Добавить цель" if ru else "Add Target",
            "kind": "form",
            "action": action(
                "beescan_context",
                "Сохранить цель" if ru else "Save Target",
                [
                    field(
                        "value",
                        field_labels["target"],
                        "url",
                        context.get("target", ""),
                    )
                ],
                {"key": "target"},
            ),
        },
        {
            "id": "access",
            "label": "Тестовый доступ" if ru else "Test access",
            "kind": "form",
            "action": action(
                "beescan_access",
                "Сохранить доступ" if ru else "Save test access",
                [
                    field(
                        "principal",
                        field_labels["principal"],
                        value=context.get("principal", ""),
                        required=False,
                    ),
                    field(
                        "profile",
                        field_labels["profile"],
                        "select",
                        context.get("profile", ""),
                        [("", "Без профиля" if ru else "No profile"), *profiles],
                        required=False,
                    ),
                    field(
                        "kind",
                        "Сессия" if ru else "Session",
                        "select",
                        "none",
                        [
                            ("none", "Без сессии" if ru else "No session"),
                            ("bearer", "Bearer"),
                            ("cookie", "Cookie"),
                        ],
                    ),
                    field(
                        "secret",
                        "Значение сессии" if ru else "Session value",
                        "secret",
                        required=False,
                    ),
                ],
            ),
        },
        {
            "id": "attachments",
            "label": "Добавить файл" if ru else "Add file",
            "kind": "file",
            "action": action("beescan_attach", "Загрузить" if ru else "Upload"),
        },
    ]
    if "target_policy" not in settings["beescan"] and not context.get("scope"):
        menu.insert(
            1,
            {
                "id": "authorization",
                "label": "Разрешение на тестирование"
                if ru
                else "Testing authorization",
                "kind": "form",
                "action": action(
                    "beescan_authorization",
                    "Сохранить разрешение" if ru else "Save authorization",
                    [
                        field("scope", field_labels["scope"]),
                        field("authority", field_labels["authority"]),
                    ],
                ),
            },
        )
    chips = [
        {
            "id": key,
            "label": field_labels[key]
            + ": "
            + (
                (
                    ("Готово" if ru else "Ready")
                    if session_states.get(key)
                    else ("Введите повторно" if ru else "Re-enter")
                )
                if key in {"bearer", "cookie"}
                else value[:100]
            ),
            "remove": action(
                "beescan_context",
                ("Удалить " if ru else "Remove ") + field_labels[key],
                extra={"key": key, "value": ""},
            ),
            "edit": (
                next(item["action"] for item in menu if item["id"] == "access")
                if key in {"profile", "principal", "bearer", "cookie"}
                else action(
                    "beescan_context",
                    ("Изменить " if ru else "Edit ") + field_labels[key],
                    [
                        field(
                            "value",
                            field_labels[key],
                            "url" if key == "target" else "textarea",
                            value=value,
                        )
                    ],
                    {"key": key},
                )
            ),
        }
        for key, value in context.items()
        if key not in {"mode", "scope", "authority"}
    ]
    if view:
        chips.extend(
            {
                "id": item["storage_run"],
                "label": ("Файлы: " if ru else "Files: ") + str(len(item["items"])),
                "remove": action(
                    "beescan_attachment_remove",
                    "Удалить файлы" if ru else "Remove files",
                    extra={"storage_run": item["storage_run"]},
                ),
            }
            for item in view["attachments"]
            if not item.get("removed")
        )
    normalized = presentation(view, locale) if view else None
    mode_field = field(
        "mode",
        "Уровень" if ru else "Effort",
        "select",
        context.get("mode", "quick"),
        [(mode, mode.title()) for mode in ("quick", "standard", "deep")],
    )
    target_notice = ""
    if context.get("target"):
        from ipaddress import ip_address
        from urllib.parse import urlsplit

        from beeagent_module.integrations.beescan.policy import (
            check_target_exclusions,
            public_destination,
        )

        hostname = urlsplit(context["target"]).hostname
        restricted = hostname == "localhost" or hostname.endswith(
            (".local", ".localhost", ".internal", ".home.arpa")
        )
        try:
            restricted = restricted or not public_destination(str(ip_address(hostname)))
        except ValueError:
            pass
        if "target_policy" in settings["beescan"]:
            try:
                check_target_exclusions(settings, context["target"])
            except PermissionError:
                restricted = True
        if (
            restricted
            and settings["beescan"]["investigation"].get("local_lab_enabled") is True
        ):
            approval = settings["beescan"]["investigation"].get("approval") or {}
            if approval.get("transport", {}).get("origin") == context["target"]:
                restricted = False
        if restricted:
            target_notice = (
                "Цель сохранена как данные; HTTP-проверка запрещена политикой хоста."
                if ru
                else (
                    "Target saved as data; HTTP investigation is "
                    "prohibited by host policy."
                )
            )
    mode_field["widget"] = "dropdown"
    layout = [
        {
            "type": "chat_workspace",
            "id": "beescan",
            "width": 12,
            "title": view["display_title"]
            if view
            else ("Новый кейс" if ru else "New Case"),
            "state": view["status"] if view else "READY",
            "new_href": href,
            "labels": {
                "history": "Кейсы" if ru else "Cases",
                "new": "Новый кейс" if ru else "New Case",
                "search": "Поиск" if ru else "Search",
                "failed": "Действие отклонено. Обновите страницу и повторите."
                if ru
                else "Action refused. Refresh and retry.",
                "pending": "Ожидание" if ru else "Pending",
                "conversation": "Диалог" if ru else "Conversation",
                "context": "Сводка" if ru else "Summary",
                "close": "Закрыть" if ru else "Close",
            },
            "errors": {
                "invalid_target": (
                    "Укажите HTTP(S) origin без пути, параметров или данных доступа."
                )
                if ru
                else "Enter an HTTP(S) origin without a path, query or credentials.",
                "case_conflict": (
                    "Кейс изменён. Закройте форму и обновите страницу перед повтором."
                )
                if ru
                else "The Case changed. Close this form and refresh before retrying.",
                "action_expired": "Срок действия формы истёк. Обновите страницу."
                if ru
                else "This form expired. Refresh the page.",
                "context_required": (
                    "Сначала добавьте цель и разрешённый контекст через +."
                )
                if ru
                else "First add a Target and approved context using +.",
                "target_execution_denied": (
                    "Цель сохранена как данные. HTTP-проверка "
                    "запрещена текущей политикой хоста."
                )
                if ru
                else (
                    "Target saved as data. HTTP investigation is "
                    "prohibited by current host policy."
                ),
            },
            "empty_message": "Задайте вопрос об информационной безопасности."
            if ru
            else "Ask a security question.",
            "search": {
                "href": "/beescan",
                "name": "q",
                "value": search,
                "hidden": {"lang": locale},
            },
            "history": [
                {
                    "id": row["case_id"],
                    "title": row["display_title"][:256],
                    "href": href + "&" + urlencode({"run_id": row["case_id"]}),
                    "active": row["case_id"] == case_id,
                    "status": row["status"],
                    "actions": history_actions(
                        host, row, actor, selected_href, href, case_id, ru
                    ),
                }
                for row in records
            ],
            "messages": normalized["messages"] if normalized else [],
            "context": normalized["context"] if normalized else None,
            "message_style": "conversation",
            "composer": {
                "variant": "compact",
                "submit_on_enter": True,
                "action_id": "beescan_send",
                "label": "Отправить" if ru else "Send",
                "disabled": not can_ask,
                "args": args,
                "fields": [
                    field("message", "Сообщение" if ru else "Message", "textarea"),
                    mode_field,
                ],
                "menu": {
                    "label": "Добавить контекст" if ru else "Add context",
                    "items": menu,
                },
                "chips": chips,
                "navigate": navigate,
                "hint": target_notice
                or (
                    (
                        "Исследование недоступно; вопросы доступны."
                        if ru
                        else "Investigation unavailable; Ask remains available."
                    )
                    if settings["beescan"]["investigation"].get("enabled") is not True
                    else ""
                ),
            },
            "refresh": {
                "href": "/api/beescan/status?" + urlencode({"run_id": case_id}),
                "interval_ms": 3000,
                "max_attempts": 300,
            }
            if view and view["status"] in {"QUEUED", "RUNNING"}
            else None,
        }
    ]
    links = []
    if view:
        links.extend(
            {
                "label": ("Запуск " if ru else "Run ") + str(index + 1),
                "href": "/beescan?"
                + urlencode(
                    {"run_id": item["run_id"], "lang": locale, "tab": "results"}
                ),
            }
            for index, item in enumerate(view["runs"][-25:])
        )
        run_page_number = view["run_offset"] // 25
        if run_page_number > 0:
            links.append(
                {
                    "label": "Предыдущие запуски" if ru else "Earlier runs",
                    "href": selected_href
                    + "&"
                    + urlencode({"run_page": run_page_number - 1}),
                }
            )
        if view["run_offset"] + 25 < view["run_count"]:
            links.append(
                {
                    "label": "Следующие запуски" if ru else "Later runs",
                    "href": selected_href
                    + "&"
                    + urlencode({"run_page": run_page_number + 1}),
                }
            )
        current = view["message_offset"] // 8
        if current > 0:
            links.append(
                {
                    "label": "Предыдущие сообщения" if ru else "Earlier messages",
                    "href": selected_href
                    + "&"
                    + urlencode({"message_page": current - 1}),
                }
            )
        if view["message_offset"] + 8 < view["message_count"]:
            links.append(
                {
                    "label": "Следующие сообщения" if ru else "Later messages",
                    "href": selected_href
                    + "&"
                    + urlencode({"message_page": current + 1}),
                }
            )
    if int(page) > 1:
        links.append(
            {
                "label": "Предыдущие кейсы" if ru else "Previous Cases",
                "href": href + "&" + urlencode({"page": int(page) - 1, "q": search}),
            }
        )
    if int(page) * 25 < total:
        links.append(
            {
                "label": "Следующие кейсы" if ru else "Next Cases",
                "href": href + "&" + urlencode({"page": int(page) + 1, "q": search}),
            }
        )
    if links:
        layout.append(
            {
                "type": "quick_links",
                "width": 12,
                "title": "История" if ru else "History",
                "items": links,
            }
        )
    return {"layout": layout}
