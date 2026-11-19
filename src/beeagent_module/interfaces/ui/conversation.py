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


_STATUS_LABELS = {
    "READY": ("Готово", "Ready"),
    "QUEUED": ("В очереди", "Queued"),
    "RUNNING": ("Выполняется", "Running"),
    "COMPLETED": ("Завершено", "Completed"),
    "PARTIAL": ("Частично", "Partial"),
    "INCONCLUSIVE": ("Недостаточно данных", "Inconclusive"),
    "CANDIDATE": ("Кандидат", "Candidate"),
    "MATCH": ("Совпадение", "Match"),
    "NO_MATCH": ("Совпадений нет", "No match"),
    "ERROR": ("Ошибка", "Error"),
    "REFUSED": ("Отклонено", "Refused"),
    "TIMEOUT": ("Истекло время", "Timed out"),
    "UNAVAILABLE": ("Недоступно", "Unavailable"),
}
_STATUS_TONES = {
    "RUNNING": "blue",
    "COMPLETED": "green",
    "MATCH": "green",
    "NO_MATCH": "green",
    "PARTIAL": "yellow",
    "CANDIDATE": "yellow",
    "INCONCLUSIVE": "yellow",
    "TIMEOUT": "yellow",
    "REFUSED": "red",
    "ERROR": "red",
}


def status_label(status, ru):
    return _STATUS_LABELS.get(status, _STATUS_LABELS["UNAVAILABLE"])[0 if ru else 1]


def results_href(run_id, locale):
    return "/beescan?" + urlencode({"run_id": run_id, "lang": locale, "tab": "results"})


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


def execution_name(item, ru):
    names = {
        "discovery": "Разведка" if ru else "Discovery",
        "investigation": "Исследование" if ru else "Investigation",
        "verification": "Проверка" if ru else "Verification",
    }
    name = names[item["kind"]]
    if item["kind"] == "verification" and item.get("provider"):
        name = (
            item["provider"].upper() if item["provider"] == "zap" else item["provider"]
        )
    return name


def execution_card(item, case_id, segment_id, ru):
    metrics = []
    for key, label in (
        ("checks", "Проверки" if ru else "Checks"),
        ("capture_steps", "Шаги захвата" if ru else "Capture steps"),
        ("requests", "HTTP-запросы" if ru else "HTTP requests"),
    ):
        if item.get(key) is not None:
            metrics.append({"label": label, "value": str(item[key])})
    progress = None
    if item["status"] in {"QUEUED", "RUNNING"}:
        if item.get("checks_total") and 0 <= item["checks"] <= item["checks_total"]:
            progress = {"completed": item["checks"], "total": item["checks_total"]}
        else:
            progress = {"completed": None, "total": None}
    outcome = item.get("outcome")
    tone_status = (
        outcome if item["status"] == "COMPLETED" and outcome else item["status"]
    )
    return {
        "kind": "execution",
        "id": item["id"],
        "sender": "host",
        "name": execution_name(item, ru),
        "text": "",
        "status": status_label(item["status"], ru),
        "timestamp": item.get("started_at", ""),
        "execution": {
            "outcome": status_label(item["outcome"], ru) if item.get("outcome") else "",
            "tone": _STATUS_TONES.get(tone_status, "secondary"),
            "duration_ms": item.get("duration_ms"),
            "progress": progress,
            "metrics": metrics[:2],
            "inspector_href": "/api/beescan/execution?"
            + urlencode(
                {
                    "case_id": case_id,
                    "run_id": segment_id,
                    "execution_id": item["id"],
                    "lang": "ru" if ru else "en",
                }
            ),
        },
    }


def execution_inspector(item, case_id, segment_id, ru):
    sections = {}
    unavailable = "Недоступно" if ru else "Unavailable"

    def add(section, label, value, **extra):
        if value is not None:
            sections.setdefault(section, []).append(
                {"label": label, "value": str(value), **extra}
            )

    add("overview", "Статус" if ru else "Status", status_label(item["status"], ru))
    tool = execution_name(item, ru)
    add("overview", "Инструмент" if ru else "Tool", tool)
    add(
        "overview",
        "Результат проверки" if ru else "Verification outcome",
        status_label(item["outcome"], ru) if item.get("outcome") else None,
    )
    add(
        "overview",
        "Длительность, с" if ru else "Duration, s",
        f"{item['duration_ms'] / 1000:.2f}".replace(".", "," if ru else ".")
        if item.get("duration_ms") is not None
        else unavailable,
    )
    for key, label in (
        ("started_at", "Начало" if ru else "Started"),
        ("ended_at", "Окончание" if ru else "Ended"),
        ("observed_at", "Запись жизненного цикла" if ru else "Lifecycle record"),
    ):
        if item.get(key):
            value = item[key]
            if key == "observed_at":
                if value == item.get("started_at"):
                    continue
                label += " · " + status_label(item["event_status"], ru)
            add("events", label, value, format="timestamp")
    if not any(item.get(key) for key in ("started_at", "ended_at", "observed_at")):
        add("events", "Время исполнения" if ru else "Execution timestamps", unavailable)
    for step in item.get("steps", []):
        add(
            "events",
            "Захват HTTP" if ru else "HTTP capture",
            step["phase"] + " · " + step["status"],
        )
    add(
        "technical",
        "Код диагностики хоста" if ru else "Host diagnostic code",
        item.get("reason"),
    )
    for key, label in (
        ("requests", "HTTP-запросы" if ru else "HTTP requests"),
        ("checks", "Выполненные проверки" if ru else "Completed checks"),
        ("checks_total", "Всего проверок" if ru else "Total checks"),
    ):
        add("checks", label, item.get(key))
    for code, count in sorted(item.get("response_counts", {}).items()):
        add("checks", f"HTTP {code}", count)
    for key, label in (
        ("provider", "Провайдер" if ru else "Provider"),
        ("provider_version", "Версия провайдера" if ru else "Provider version"),
        ("profile", "Профиль" if ru else "Profile"),
        (
            "request_budget",
            ("Лимит запросов исследования" if ru else "Investigation request budget")
            if item["kind"] == "discovery"
            else ("Лимит запросов" if ru else "Request budget"),
        ),
        ("artifact", "Подписанный артефакт" if ru else "Authenticated artifact"),
    ):
        add("technical", label, item.get(key))
    cleanup = item.get("cleanup")
    if cleanup is not None:
        add(
            "technical",
            "Очистка подтверждена" if ru else "Cleanup verified",
            ("Да" if cleanup else "Нет") if ru else ("Yes" if cleanup else "No"),
        )
    for label, value in (
        ("Кейс" if ru else "Case", case_id),
        ("Запуск исследования" if ru else "Investigation run", segment_id),
        ("Исполнение" if ru else "Execution run", item["run_id"]),
        ("Действие" if ru else "Action", item.get("action_id")),
        ("Исходный запуск" if ru else "Source run", item.get("source_run_id")),
    ):
        add("connections", label, value, copy=True)
    for ref in item.get("evidence_refs", []):
        add("connections", "Доказательство" if ru else "Evidence", ref, copy=True)
    if item.get("artifact"):
        add(
            "connections",
            "Связанные результаты" if ru else "Related results",
            "Review / Report",
            href="/beescan?"
            + urlencode(
                {"run_id": segment_id, "tab": "results", "lang": "ru" if ru else "en"}
            ),
        )
    result = {"id": item["id"], "sections": sections}
    if item.get("controls"):
        roles = {
            "baseline": "Базовый" if ru else "Baseline",
            "negative": "Отрицательный" if ru else "Negative control",
            "comparison": "Сравнение" if ru else "Comparison",
        }
        result["checks_table"] = {
            "columns": [
                "№",
                "Тип" if ru else "Type",
                "HTTP",
                "Сигнал" if ru else "Oracle",
            ],
            "rows": [
                [
                    str(index),
                    roles.get(control.get("role"), unavailable),
                    str(control["status_code"]),
                    ("Есть" if ru else "Positive")
                    if control["oracle"]
                    else ("Нет" if ru else "Negative"),
                ]
                for index, control in enumerate(item["controls"], 1)
            ],
        }
    return result


def presentation(view, locale="en"):
    ru = locale == "ru"
    context = []
    severity = []
    latest = view.get("latest_investigation")
    target = view["context"].get("target")
    summary = view["summary"]
    unavailable = "Недоступно" if ru else "Unavailable"
    results = results_href(latest["run_id"], locale) if latest else None

    def metric(identity, label, value, href=None):
        item = {"id": identity, "label": label, "value": str(value), "detail": ""}
        if href:
            item["href"] = href
        context.append(item)

    if target:
        metric("target", "Цель" if ru else "Target", target, results)
    if latest:
        metric(
            "status",
            "Статус кейса" if ru else "Case status",
            status_label(view["status"], ru),
            results,
        )
        for key, label in (
            ("execution_count", "Исполнения" if ru else "Executions"),
            ("request_count", "HTTP-запросы" if ru else "HTTP requests"),
            ("execution_errors", "Ошибки исполнения" if ru else "Execution errors"),
        ):
            value = summary.get(key)
            if key != "request_count" or value is not None:
                metric(key, label, value if value is not None else unavailable, results)
        findings = summary.get("findings", [])
        if latest["authenticated"] and summary.get("findings_complete"):
            verified = sum(
                item.get("review_disposition") == "verified" for item in findings
            )
            candidates = sum(
                item.get("review_disposition") in (None, "candidate")
                for item in findings
            )
            metric(
                "candidates", "Кандидаты" if ru else "Candidates", candidates, results
            )
            metric(
                "verified",
                "Подтверждённые" if ru else "Verified findings",
                verified,
                results,
            )
            for level, tone in (("high", "red"), ("medium", "yellow"), ("low", "blue")):
                matching = [item for item in findings if item.get("severity") == level]
                entry = {
                    "id": level,
                    "label": level.title(),
                    "value": str(len(matching)),
                    "detail": "",
                    "tone": tone,
                }
                entry["href"] = (
                    results_href(view["case_id"], locale)
                    + "&"
                    + urlencode({"severity": level})
                )
                severity.append(entry)
        else:
            metric("findings", "Находки" if ru else "Findings", unavailable, results)
        reasons = {
            "case_archived": ("Кейс в архиве.", "The case is archived."),
            "operator_required": (
                "Требуется роль оператора.",
                "An operator role is required.",
            ),
            "investigation_active": (
                "Дождитесь завершения текущего исследования.",
                "Wait for the current investigation to finish.",
            ),
            "no_authenticated_source": (
                "Для продолжения нет подтверждённого источника.",
                "Continuing requires an authenticated source.",
            ),
            "target_context_changed": (
                "Цель изменилась. Продолжение недоступно.",
                "The target changed. Continuing is unavailable.",
            ),
            "source_bound_continuation_unavailable": (
                "Продолжение с сохранёнными доказательствами недоступно.",
                "Resuming with saved evidence is unavailable.",
            ),
        }
        reason_code = view.get("next_action_reason")
        reason = reasons.get(reason_code)
        if reason:
            metric(
                "next", "Следующий шаг" if ru else "Next step", reason[0 if ru else 1]
            )
    messages = []
    for message in view["messages"]:
        if message.get("executions"):
            messages.extend(
                execution_card(item, view["case_id"], message["source"], ru)
                for item in message["executions"]
            )
        if message.get("investigation"):
            run = message["investigation"]
            terminal = run["status"] not in {"QUEUED", "RUNNING"}
            if message.get("type") == "run" and (
                run.get("has_conclusion") or not terminal
            ):
                continue
            outcome = (
                {
                    "verified": (
                        "Есть подтверждённая находка",
                        "Contains a verified finding",
                    ),
                    "candidate": ("Требуется проверка находки", "Finding needs review"),
                    "not_established": (
                        "Уязвимость не подтверждена",
                        "Vulnerability not verified",
                    ),
                }[run["vulnerability"]][0 if ru else 1]
                if terminal and run["authenticated"]
                else ""
            )
            messages.append(
                {
                    "kind": "result",
                    "id": "result-" + message["source"],
                    "sender": "host",
                    "name": "Итог" if ru else "Result",
                    "status": status_label(run["status"], ru),
                    "text": "",
                    "timestamp": message["timestamp"],
                    "result": {
                        "tone": _STATUS_TONES.get(run["status"], "secondary"),
                        "outcome": outcome,
                        "href": results_href(message["source"], locale),
                    },
                }
            )
        elif not message.get("executions"):
            messages.append(
                {key: message[key] for key in ("id", "sender", "text", "timestamp")}
                | {"name": "", "status": ""}
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
            "title": "Сводка" if ru else "Summary",
            "sections": [{"id": "case", "title": "", "items": context}]
            + (
                [
                    {
                        "id": "findings",
                        "title": "Находки" if ru else "Findings",
                        "inline": True,
                        "items": severity,
                    }
                ]
                if severity
                else []
            ),
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
                        "message_page": view["message_offset"] // 8,
                        "lang": locale,
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
