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


def coverage_label(family, ru):
    return {
        "information_disclosure": ("Раскрытие информации", "Information disclosure"),
        "path_traversal": ("Обход каталогов", "Path traversal"),
        "access_control": ("Контроль доступа", "Access control"),
    }[family][0 if ru else 1]


def investigation_outcome(run, ru):
    failed = run["status"] in {"ERROR", "REFUSED"}
    completed = run["status"] in {"MATCH", "CANDIDATE", "NO_MATCH"} and run[
        "reason"
    ] in {
        "ok",
        "answer_supported",
        "source_disclosure_supported",
        "authenticated_case_reused",
    }
    investigation = (
        ("выполняется" if ru else "in progress")
        if run["status"] in {"RUNNING", "QUEUED"}
        else ("не завершено из-за ошибки" if ru else "failed")
        if failed
        else ("завершено" if ru else "completed")
        if completed
        else ("частично" if ru else "partial")
    )
    vulnerability = {
        "verified": (
            "подтверждена независимой проверкой",
            "verified by independent review",
        ),
        "candidate": (
            "кандидат; требуется независимая проверка",
            "candidate; independent verification required",
        ),
        "not_established": ("не установлена", "not established"),
    }[run["vulnerability"]][0 if ru else 1]
    return (
        ("Исследование: " if ru else "Investigation: ")
        + investigation
        + "\n"
        + ("Уязвимость: " if ru else "Vulnerability: ")
        + vulnerability
        + "\n"
        + (
            "Завершение лаборатории: неизвестно; независимых доказательств завершения нет."
            if ru
            else "Lab completion: unknown; no independent completion evidence."
        )
    )


def observation_text(item):
    lines = [
        item["endpoint"] + " | " + ", ".join(item["parameters"]),
        item["profile"] + ": " + item["status"] + " / " + item["reason"],
        "Source: " + ", ".join(item["references"]),
        "Evidence: " + item["run_id"] + " / " + item["evidence_ref"],
    ]
    for control in item["controls"]:
        if "index" in control:
            lines.append(
                str(control["index"])
                + " "
                + control["role"]
                + " / "
                + control["technique"]
                + ": HTTP "
                + str(control["status_code"])
                + "; oracle="
                + str(control["oracle"])
            )
        else:
            lines.append(
                control["slot"]
                + ": "
                + ", ".join(
                    key + "=" + str(value)
                    for key, value in control.items()
                    if key not in {"slot", "evidence_ref"}
                )
            )
    if item.get("missing_control_indexes"):
        lines.append("Incomplete controls: " + str(item["missing_control_indexes"]))
    return "\n".join(lines)


def investigation_message(message, ru):
    run = message["investigation"]
    if message.get("type") == "investigation":
        text = investigation_outcome(run, ru)
        if run["status"] == "NO_MATCH":
            text += "\n" + (
                "Отсутствие совпадения не подтверждает безопасность цели."
                if ru
                else "NO_MATCH does not establish target safety."
            )
    else:
        lines = [
            ("Исследую: " if ru else "Investigating: ")
            + (
                run["objective"][:160]
                or ("сохранённую задачу" if ru else "the recorded objective")
            )
        ]
        if run["captured"]:
            lines.append(
                ("Получено ответов: " if ru else "Responses captured: ")
                + str(run["captured"])
                + (
                    ". Источники аутентифицированы."
                    if ru
                    else ". Sources authenticated."
                )
                if run["authenticated"]
                else ("Получено ответов: " if ru else "Responses captured: ")
                + str(run["captured"])
                + (
                    ". Операционный статус; доказательства ещё не аутентифицированы."
                    if ru
                    else ". Operational status; evidence is not yet authenticated."
                )
            )
        elif run["capture_pending"]:
            lines.append(
                "Получение ответа ещё не завершено."
                if ru
                else "Response capture is not complete yet."
            )
        else:
            lines.append(
                "Завершённых HTTP-захватов пока нет."
                if ru
                else "No completed HTTP captures are recorded yet."
            )
        for provider in run["providers"][:3]:
            lines.append(
                ("Выбрана проверка " if ru else "Selected verification ")
                + str(provider["provider"])
                + " / "
                + str(provider["profile"])
                + (
                    " по наблюдаемому GET-источнику: "
                    if ru
                    else " from an observed GET source: "
                )
                + str(provider["status"])
                + "."
            )
        unavailable = [
            item["family"]
            for item in run["coverage"]
            if item["status"]
            in {
                "UNSUPPORTED",
                "NOT_YET_ESTABLISHED",
                "PARTIAL",
                "ERROR",
                "TIMEOUT",
                "REFUSED",
            }
        ]
        if unavailable:
            lines.append(
                (
                    "Покрытие не установлено или неполное: "
                    if ru
                    else "Coverage unavailable or incomplete: "
                )
                + ", ".join(coverage_label(family, ru) for family in unavailable)
                + "."
            )
        if run["status"] in {"RUNNING", "QUEUED"}:
            lines.append(
                "Исследование продолжается в разрешённых пределах."
                if ru
                else "Investigation is continuing within its authorization limits."
            )
        else:
            if not run.get("has_conclusion"):
                lines.append(investigation_outcome(run, ru))
        text = "\n".join(lines)
    failure = run.get("failure")
    if failure:
        if failure["reason"] == "capture_before_request_failed":
            text += "\n" + (
                "Захват завершился до отправки запроса. Проверьте соединение/TLS и защищённую диагностику; точная причина не сохранена."
                if ru
                else "Capture failed before sending a request. Check connectivity/TLS and protected diagnostics; the exact cause was not retained."
            )
        else:
            text += (
                "\n"
                + ("Причина остановки: " if ru else "Stop reason: ")
                + failure["reason"]
                + "."
            )
    if run["status"] not in {"RUNNING", "QUEUED"}:
        text += "\n" + (
            "Далее: просмотрите доказательства и ограничения в результатах."
            if ru
            else "Next: review evidence and limitations in Results."
        )
    return {
        "id": message["id"],
        "sender": message["sender"],
        "name": "BeeScan",
        "text": text[:1500],
        "timestamp": message["timestamp"],
        "status": "",
        "details": (
            run["objective"]
            + "\n"
            + (
                "\n\n".join(
                    observation_text(item) for item in run.get("observations", [])
                )
                or run["details"]
            )
            + ("\n" + message["text"] if message.get("type") == "investigation" else "")
        )[:2400],
        "details_label": "Технические детали" if ru else "Technical details",
        "links": [
            {
                "label": "Доказательства / Review / Report / Export"
                if ru
                else "Evidence / Review / Report / Export",
                "href": "/beescan?"
                + urlencode(
                    {
                        "run_id": message["source"],
                        "tab": "results",
                        "lang": "ru" if ru else "en",
                    }
                ),
            }
        ],
    }


def presentation(view, locale="en"):
    ru = locale == "ru"
    context = []
    target = view["context"].get("target")
    latest = view.get("latest_investigation")
    if target or view["run_count"]:
        if target:
            context.append(
                {"id": "target", "label": "Цель" if ru else "Target", "value": target}
            )
        context.append(
            {
                "id": "status",
                "label": "Текущая активность" if ru else "Current activity",
                "value": view["status"],
            }
        )
    if latest:
        context.extend(
            [
                {
                    "id": "objective",
                    "label": "Задача исследования" if ru else "Investigation objective",
                    "value": latest["objective"],
                },
                {
                    "id": "surfaces",
                    "label": "Наблюдаемые поверхности" if ru else "Observed surfaces",
                    "value": ("Ответов: " if ru else "Responses: ")
                    + str(latest["captured"]),
                },
                {
                    "id": "outcome",
                    "label": "Результат последнего запуска"
                    if ru
                    else "Latest run outcome",
                    "value": investigation_outcome(latest, ru),
                },
            ]
        )
        for index, item in enumerate(latest["coverage"]):
            context.append(
                {
                    "id": "coverage-" + str(index),
                    "label": coverage_label(item["family"], ru),
                    "value": item["status"],
                    "detail": (
                        "Статус покрытия; UNSUPPORTED не является доказательством."
                        if ru
                        else "Coverage status; UNSUPPORTED is not evidence."
                    ),
                }
            )
        for index, item in enumerate(latest.get("observations", [])):
            context.append(
                {
                    "id": "observation-" + str(index),
                    "label": "Доказательства проверки"
                    if ru
                    else "Verification evidence",
                    "value": item["endpoint"] + " / " + item["profile"],
                    "detail": observation_text(item),
                }
            )
        for finding in view["summary"].get("findings", latest["findings"])[:16]:
            context.append(
                {
                    "id": finding["finding_id"],
                    "label": "Находка" if ru else "Finding",
                    "value": finding["title"],
                    "detail": finding.get("review_disposition", "candidate"),
                    "href": "/beescan?"
                    + urlencode(
                        {
                            "run_id": finding.get("run_id", latest["run_id"]),
                            "lang": locale,
                            "tab": "results",
                        }
                    ),
                }
            )
        context.append(
            {
                "id": "next",
                "label": "Следующий шаг" if ru else "Next step",
                "value": (
                    "Продолжение проверки недоступно: "
                    if ru
                    else "Next verification unavailable: "
                )
                + view.get(
                    "next_action_reason", "source_bound_continuation_unavailable"
                )
                + (
                    ". Новый повтор требует нового захвата и бюджета."
                    if ru
                    else ". A fresh retry requires new captures and a new budget."
                ),
            }
        )
        context.append(
            {
                "id": "technical",
                "label": "Технические детали" if ru else "Technical details",
                "value": "Открыть" if ru else "Expand",
                "detail": latest["details"],
            }
        )
    for index, run in enumerate(view["summary"]["runs"]):
        detail = ""
        if run["authenticated"]:
            detail = (
                ("Запросы: " if ru else "Requests: ")
                + str(run.get("requests"))
                + ("; кандидаты: " if ru else "; candidates: ")
                + str(run.get("candidates", 0))
            )
        context.append(
            {
                "id": "run-" + str(index),
                "label": "Исторический запуск" if ru else "Historical run",
                "value": run["status"],
                "detail": detail,
                "href": "/beescan?"
                + urlencode(
                    {"run_id": run["run_id"], "lang": locale, "tab": "results"}
                ),
            }
        )
    for item in context:
        item.setdefault("detail", "")
    messages = []
    for message in view["messages"]:
        if message.get("investigation"):
            messages.append(investigation_message(message, ru))
        else:
            messages.append(
                {key: message[key] for key in ("id", "sender", "text", "timestamp")}
                | {"name": "", "status": ""}
            )
    if (
        view.get("retry_actions")
        and view["message_offset"] + 8 >= view["message_count"]
    ):
        messages.append(
            {
                "id": "next-" + view["case_id"],
                "sender": "host",
                "name": "BeeScan",
                "timestamp": "",
                "status": "",
                "text": "Доступен новый полный повтор с новым захватом и бюджетом. Это отдельное исследование, не Resume и не следующая проверка по доказательству."
                if ru
                else "A fresh full retry starts a separate investigation with new captures and a new budget. It is not Resume or an evidence-bound next verification.",
                "actions": [
                    {
                        "action_id": "beescan_investigate",
                        "label": "Новый полный повтор"
                        if ru
                        else "Start fresh full retry",
                        "disabled": False,
                        "args": args,
                        "fields": [],
                        "navigate": {
                            "href": "/beescan?" + urlencode({"lang": locale}),
                            "param": "run_id",
                            "result_key": "case_id",
                        },
                    }
                    for args in view["retry_actions"][:1]
                ],
            }
        )
    current = view["message_offset"] // 8
    links = []
    for number, label in (
        (0, "К началу" if ru else "First messages"),
        (current - 1, "Раньше" if ru else "Earlier"),
        (current + 1, "Далее" if ru else "Later"),
        ((view["message_count"] - 1) // 8, "Последние" if ru else "Latest"),
    ):
        if 0 <= number <= (view["message_count"] - 1) // 8 and number != current:
            href = "/beescan?" + urlencode(
                {"run_id": view["case_id"], "lang": locale, "message_page": number}
            )
            if not any(item["href"] == href for item in links):
                links.append({"label": label, "href": href})
    if links:
        messages.append(
            {
                "id": "conversation-pages",
                "sender": "host",
                "name": "",
                "timestamp": "",
                "status": "",
                "text": "Содержимое кейса" if ru else "Case conversation",
                "links": links,
            }
        )
    return {
        "state": view["status"],
        "messages": messages,
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
    records = records[(int(page) - 1) * 23 : int(page) * 23]
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
                "href": "/api/beescan/status?"
                + urlencode(
                    {
                        "run_id": case_id,
                        **(
                            {"message_page": message_page}
                            if message_page is not None
                            else {}
                        ),
                    }
                ),
                "interval_ms": 3000,
                "max_attempts": 300,
            }
            if view and view["status"] in {"QUEUED", "RUNNING"}
            else None,
        }
    ]
    if int(page) > 1:
        layout[0]["history"].insert(
            0,
            {
                "id": "history-previous",
                "title": "Предыдущие кейсы" if ru else "Earlier Cases",
                "href": href + "&" + urlencode({"page": int(page) - 1, "q": search}),
                "active": False,
                "status": "",
                "actions": [],
            },
        )
    if int(page) * 23 < total:
        layout[0]["history"].append(
            {
                "id": "history-next",
                "title": "Следующие кейсы" if ru else "More Cases",
                "href": href + "&" + urlencode({"page": int(page) + 1, "q": search}),
                "active": False,
                "status": "",
                "actions": [],
            }
        )
    return {"layout": layout}
