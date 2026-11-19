import fcntl
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import UTC, datetime
from urllib.parse import urlsplit

from beeagent_module.integrations.beescan.case_state import digest
from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.integrations.beescan.policy import (
    ProbePolicy,
    check_target_exclusions,
)
from beeagent_module.integrations.beescan.review_source import (
    AssessmentSnapshot,
    open_child,
    open_directory,
)
from beeagent_module.integrations.beescan.web import (
    PROFILES,
    _read_owned,
    _sign,
    principal,
    require_web_execution_authority,
)

active_session: ContextVar[Callable[[ProbePolicy], tuple[str, str] | None] | None] = (
    ContextVar("beescan_conversation_session", default=None)
)

_CONTEXT = {
    "target",
    "scope",
    "authority",
    "profile",
    "principal",
    "observation",
    "mode",
}


def investigation_guidance(reason, ru):
    messages = {
        "test_principal_selection_required": (
            "Для IDOR/BOLA нужен утверждённый профиль двух тестовых участников: + → Тестовый доступ.",
            "IDOR/BOLA requires an approved two-principal test profile: + → Test access.",
        ),
        "session_capability_unavailable": (
            "Текущая сессия не поддерживает запрошенную проверку. Запустите поддерживаемое Discovery без сессии или настройте утверждённый тестовый доступ.",
            "The current session does not support the requested verification. Run supported Discovery without a session or configure approved test access.",
        ),
        "web_dast_profile_unsupported": (
            "Запрошенная активная проверка не поддерживается для текущей цели или режима. Discovery можно запустить отдельной задачей.",
            "The requested active verification is unsupported for the current Target or mode. Discovery can be run as a separate task.",
        ),
        "active_dast_not_approved": (
            "Запрошенная активная проверка не разрешена текущей политикой. Discovery можно запустить отдельной задачей.",
            "The requested active verification is not approved by current policy. Discovery can be run as a separate task.",
        ),
        "context_authority_changed": (
            "Разрешение для цели изменилось. Сохраните Target заново и повторите задачу.",
            "Target authorization changed. Save the Target again and retry the task.",
        ),
        "web_investigation_not_approved": (
            "Web-исследование не разрешено для текущего оператора или runtime.",
            "Web investigation is not approved for the current operator or runtime.",
        ),
    }
    value = messages.get(reason)
    if value is not None:
        return value[0 if ru else 1]
    return (
        "Запрос отклонён. Проверьте разрешение цели и поддерживаемую проверку."
        if ru
        else "Request refused. Check Target authorization and supported verification."
    )


def text(value, maximum=4096):
    if (
        type(value) is not str
        or not 1 <= len(value.strip()) <= maximum
        or any(ord(c) < 32 and c not in "\n\t" for c in value)
        or "\x7f" in value
    ):
        raise ValueError("invalid_conversation_text")
    return value.strip()


def origin(value):
    value = text(value, 2048)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("exact_origin_required") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
        or port is not None
        and not 1 <= port <= 65535
    ):
        raise ValueError("exact_origin_required")
    return parsed.scheme + "://" + parsed.netloc.lower()


class Conversations:
    def __init__(self, host):
        self.host = host
        self.secrets = {}
        self.pending = {}
        self.running = set()

    def nonce(self, actor, case_id, revision):
        self.owned(case_id, actor)
        token = self.host.nonce(actor)
        signature = _sign(
            self.host.reload_settings(),
            [actor["user_id"], case_id, str(revision), token],
        )
        return token + "." + signature

    def verify_nonce(self, payload, actor):
        token = payload.get("nonce")
        if type(token) is not str or token.count(".") != 3:
            raise PermissionError("conversation_nonce_required")
        token, signature = token.rsplit(".", 1)
        expected = _sign(
            self.host.reload_settings(),
            [actor["user_id"], payload.get("case_id"), payload.get("revision"), token],
        )
        if not hmac.compare_digest(expected, signature):
            raise PermissionError("conversation_nonce_binding_changed")
        self.host._run_id(actor, token)
        return token

    def create(self, payload, actor, *, initial_action=None):
        expected = ({"nonce", "message"}, {"nonce", "message", "mode"})
        if initial_action == "beescan_context":
            expected = ({"nonce", "key", "value"},)
            if payload.get("key") not in {"target", "observation"}:
                raise ValueError("target_context_required")
            if payload["key"] == "target":
                origin(payload.get("value"))
            else:
                text(self.redact(text(payload.get("value"), 2048), actor), 2048)
        elif initial_action == "beescan_attach":
            expected = ({"nonce"},)
        if type(payload) is not dict or set(payload) not in expected:
            raise ValueError("invalid_conversation_create")
        if "mode" in payload and (
            type(payload["mode"]) is not str or payload["mode"] not in PROFILES
        ):
            raise ValueError("unsupported_mode")
        settings = self.host.reload_settings()
        owner = principal(settings, actor)
        if actor["role"] not in {"operator", "admin"}:
            raise PermissionError("conversation_operator_required")
        message = (
            text(self.redact(text(payload["message"], 2048), actor), 2048)
            if "message" in payload
            else None
        )
        case_id = "web-chat-" + self.host._run_id(actor, payload["nonce"])[4:]
        self.host.storage.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = open_directory(self.host.storage)
        try:
            try:
                os.mkdir("runs", 0o700, dir_fd=root)
            except FileExistsError:
                pass
            runs = open_child(root, "runs")
        finally:
            os.close(root)
        try:
            os.mkdir(case_id, 0o700, dir_fd=runs)
            case = open_child(runs, case_id, private=True)
            try:
                os.mkdir("module-beescan", 0o700, dir_fd=case)
            finally:
                os.close(case)
            from beeagent_module.integrations.beescan.dast import _api

            api = _api(self.host.storage, case_id, self.host.logger)
            binding = {
                "run_id": case_id,
                "case_id": case_id,
                "principal_id": owner,
                "kind": "conversation",
                "created_at": datetime.now(UTC).isoformat(),
            }
            _persist(
                api,
                "web_owner.json",
                {"binding": binding, "signature": _sign(settings, binding)},
            )
            os.fsync(runs)
        finally:
            os.close(runs)
        with self.lock(case_id, actor):
            state = self.read(case_id, actor)
            if "mode" in payload:
                self.append(
                    state, "context", {"mode": payload["mode"]}, payload["nonce"], actor
                )
            if initial_action == "beescan_context":
                self.context(
                    state, {**payload, "case_id": case_id, "revision": "0"}, actor
                )
            elif message is not None:
                if initial_action == "beescan_send":
                    token = self.nonce(actor, case_id, state["revision"])
                    self.send(
                        state,
                        {
                            "case_id": case_id,
                            "revision": str(state["revision"]),
                            "nonce": token,
                            "message": message,
                            "mode": payload.get("mode", "quick"),
                        },
                        actor,
                    )
                else:
                    self.ask(state, message, payload["nonce"], actor)
        return {"case_id": case_id, "run_id": case_id}

    @contextmanager
    def lock(self, case_id, actor, *, wait=False):
        self.owned(case_id, actor)
        directory = open_directory(
            self.host.storage / "runs" / case_id / "module-beescan"
        )
        try:
            fcntl.flock(directory, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            yield
        finally:
            os.close(directory)

    def owned(self, case_id, actor):
        if (
            type(case_id) is not str
            or re.fullmatch(r"web-chat-[0-9a-f]{48}", case_id) is None
        ):
            raise ValueError("invalid_conversation_id")
        binding = _read_owned(
            self.host.storage, self.host.reload_settings(), case_id, actor
        )
        if binding.get("kind") != "conversation":
            raise PermissionError("conversation_owner_required")
        return binding

    def read(self, case_id, actor):
        self.owned(case_id, actor)
        state = {
            "case_id": case_id,
            "revision": 0,
            "context_revision": 0,
            "context": {},
            "messages": [],
            "sequence": [],
            "runs": [],
            "nonces": set(),
            "previous": None,
            "attachments": [],
        }
        directory = open_directory(
            self.host.storage / "runs" / case_id / "module-beescan"
        )
        try:
            names = sorted(
                name
                for name in os.listdir(directory)
                if name.startswith("conversation-")
            )
        finally:
            os.close(directory)
        if len(names) > 10000:
            raise ValueError("conversation_record_limit")
        snapshot = AssessmentSnapshot(self.host.storage)
        settings = self.host.reload_settings()
        for index, name in enumerate(names, 1):
            if name != f"conversation-{index:08d}.json":
                raise PermissionError("conversation_sequence_invalid")
            record = snapshot.json(case_id, name)
            value = record.get("value")
            if (
                type(value) is not dict
                or record.get("signature") != _sign(settings, value)
                or value.get("case_id") != case_id
                or value.get("revision") != index
                or value.get("previous") != state["previous"]
                or value.get("actor") != actor["user_id"]
            ):
                raise PermissionError("conversation_record_changed")
            state["revision"] = index
            state["previous"] = digest(record)
            state["nonces"].add(value["nonce"])
            kind, data = value["kind"], value["data"]
            if kind in {"message", "run"}:
                state["sequence"].append(
                    {"kind": kind, "data": data, "timestamp": value["timestamp"]}
                )
            if kind == "message":
                state["messages"].append(data)
            elif kind == "context":
                state["context"] = data
                state["context_revision"] += 1
            elif kind == "run":
                state["runs"].append(data)
            elif kind == "attachment":
                state["attachments"].append(data)
                state["context_revision"] += 1
            elif kind == "attachment_remove":
                state["context_revision"] += 1
                for item in state["attachments"]:
                    if item["storage_run"] == data["storage_run"]:
                        item["removed"] = True
            else:
                raise ValueError("invalid_conversation_record")
        if names:
            head = snapshot.json(case_id, "conversation_head.json")
            expected = {
                "revision": state["revision"],
                "previous": state["previous"],
                "case_id": case_id,
            }
            if head.get("value") != expected or head.get("signature") != _sign(
                settings, expected
            ):
                raise PermissionError("conversation_head_changed")
        else:
            try:
                snapshot.read(case_id, "conversation_head.json")
            except FileNotFoundError:
                pass
            else:
                raise PermissionError("conversation_records_missing")
        snapshot.verify()
        return state

    def append(self, state, kind, data, nonce, actor):
        from beeagent_module.integrations.beescan.dast import _api

        if state["revision"] >= 10000:
            raise ValueError("conversation_record_limit")
        settings = self.host.reload_settings()
        self.owned(state["case_id"], actor)
        value = {
            "schema_version": 1,
            "case_id": state["case_id"],
            "revision": state["revision"] + 1,
            "previous": state["previous"],
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor["user_id"],
            "kind": kind,
            "nonce": digest(nonce),
            "data": data,
        }
        record = {"value": value, "signature": _sign(settings, value)}
        if len(json.dumps(record).encode()) > 65536:
            raise ValueError("conversation_record_limit")
        api = _api(self.host.storage, state["case_id"], self.host.logger)
        name = f"conversation-{value['revision']:08d}.json"
        if (api.artifact_dir() / name).exists():
            raise PermissionError("conversation_revision_conflict")
        _persist(api, name, record)
        checked = AssessmentSnapshot(self.host.storage).json(state["case_id"], name)
        if checked != record:
            raise OSError("conversation_readback_failed")
        head = {
            "revision": state["revision"] + 1,
            "previous": digest(record),
            "case_id": state["case_id"],
        }
        _persist(
            api,
            "conversation_head.json",
            {"value": head, "signature": _sign(settings, head)},
        )
        state["revision"] += 1
        state["previous"] = digest(record)
        state["nonces"].add(digest(nonce))
        if kind == "message":
            state["messages"].append(data)
        elif kind == "context":
            state["context"] = data
            state["context_revision"] += 1
        elif kind == "run":
            state["runs"].append(data)
        if kind in {"message", "run"}:
            state["sequence"].append(
                {"kind": kind, "data": data, "timestamp": value["timestamp"]}
            )

    def redact(self, value, actor=None):
        redactions = set()
        for binding in list(self.secrets.values()):
            if actor is None or binding["operator"] != actor["user_id"]:
                continue
            redactions.add(binding["value"])
            if binding["kind"] == "cookie":
                redactions.update(
                    pair.partition("=")[2].strip()
                    for pair in binding["value"].split(";")
                )
        for secret in sorted(redactions, key=len, reverse=True):
            if secret:
                value = value.replace(secret, "\ufffc")
        value = value.replace("\ufffc", "[redacted]")
        value = re.sub(
            r"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", value
        )
        return re.sub(
            r"(?im)\b(?:authorization|cookie|password|api[_-]?key|"
            r"access[_-]?token|session[_-]?secret)[ \t]*[:=][^\r\n]+",
            "[redacted]",
            value,
        )

    def ask(self, state, message, nonce, actor):
        if state["revision"] + 2 > 10000:
            raise ValueError("conversation_record_limit")
        self.append(
            state,
            "message",
            {
                "id": secrets.token_hex(16),
                "sender": "operator",
                "text": message,
                "timestamp": datetime.now(UTC).isoformat(),
                "type": "question",
                "trust": "untrusted_operator_note",
                "source": None,
            },
            nonce,
            actor,
        )
        try:
            from beeagent_module.integrations.beescan.investigation import _ai, _prompt

            history = []
            size = 0
            for item in reversed(state["messages"]):
                if size >= 6000 or len(history) >= 12:
                    break
                content = self.redact(item["text"], actor)[: 6000 - size]
                history.append({"sender": item["sender"], "text": content})
                size += len(content)
            facts = []
            for run in state["runs"][-3:]:
                try:
                    view = self.host.inspect(run["run_id"], actor)
                except OSError, ValueError, RuntimeError, KeyError, TypeError:
                    continue
                if view.get("evidence_authenticated"):
                    facts.append(
                        {
                            "source_run": view["run_id"],
                            "status": view["status"],
                            "request_count": view["request_count"],
                            "finding_count": len(view["findings"]),
                        }
                    )
            settings = self.host.reload_settings()
            facts = {
                "conversation": list(reversed(history)),
                "approved_case_facts": facts,
            }
            while True:
                try:
                    _prompt(settings, "conversation_ask", facts)
                    break
                except ValueError as error:
                    if str(error) != "investigation_ai_input_limit":
                        raise
                    longest = max(
                        history, key=lambda item: len(json.dumps(item["text"]))
                    )
                    if len(longest["text"]) <= 1:
                        raise
                    longest["text"] = longest["text"][
                        : max(1, len(longest["text"]) // 2)
                    ]
            answer = _ai(
                settings,
                "conversation_ask",
                facts,
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["answer"],
                    "properties": {"answer": {"type": "string"}},
                },
                self.host.logger,
            )
            if type(answer) is not dict or set(answer) != {"answer"}:
                raise ValueError("investigation_ai_invalid_response")
            answer = text(self.redact(text(answer["answer"], 4096), actor), 4096)
            sender, kind = "assistant", "answer"
        except (
            ImportError,
            OSError,
            RuntimeError,
            TimeoutError,
            ValueError,
        ) as failure:
            reason = str(failure)
            if reason in {
                "invalid_investigation_ai_profile",
                "investigation_ai_key_missing",
                "investigation_ai_configuration",
            }:
                category = "configuration"
                answer = (
                    "AI не настроен. Вопрос сохранён; обратитесь к оператору системы."
                    if re.search("[А-Яа-я]", message)
                    else (
                        "AI is not configured. Your question is saved; "
                        "contact the system operator."
                    )
                )
            elif reason == "investigation_ai_refused":
                category = "refused"
                answer = (
                    "AI-провайдер отклонил запрос. Вопрос сохранён."
                    if re.search("[А-Яа-я]", message)
                    else "The AI provider refused this request. Your question is saved."
                )
            else:
                category = (
                    "output_limit"
                    if reason == "investigation_ai_output_limit"
                    else "invalid_response"
                    if reason
                    in {
                        "investigation_ai_invalid_response",
                        "invalid_conversation_text",
                    }
                    else "temporary"
                )
                answer = (
                    "Ответ AI временно недоступен. Вопрос сохранён; попробуйте ещё раз."
                    if re.search("[А-Яа-я]", message)
                    else (
                        "AI response temporarily unavailable. Your "
                        "question is saved; please retry."
                    )
                )
            self.host.logger.warning("Conversation Ask failed: category=%s", category)
            sender, kind = "host", "unavailable"
        self.append(
            state,
            "message",
            {
                "id": secrets.token_hex(16),
                "sender": sender,
                "text": answer,
                "timestamp": datetime.now(UTC).isoformat(),
                "type": kind,
                "source": "configured_ai" if sender == "assistant" else None,
            },
            nonce,
            actor,
        )

    def execute(self, action, payload, actor):
        principal(self.host.reload_settings(), actor)
        if actor["role"] not in {"operator", "admin"}:
            raise PermissionError("conversation_operator_required")
        if action == "beescan_conversation_create":
            return self.create(payload, actor)
        if type(payload) is dict and "case_id" not in payload:
            if action in {"beescan_context", "beescan_send"}:
                return self.create(payload, actor, initial_action=action)
            raise ValueError("target_context_required")
        if type(payload) is not dict or not {"case_id", "revision", "nonce"} <= set(
            payload
        ):
            raise ValueError("invalid_conversation_action")
        case_id = payload["case_id"]
        self.verify_nonce(payload, actor)
        with self.lock(case_id, actor):
            state = self.read(case_id, actor)
            if (
                str(state["revision"]) != payload["revision"]
                or digest(payload["nonce"]) in state["nonces"]
            ):
                raise PermissionError("conversation_replay_or_conflict")
            if self.host.case_metadata(case_id, actor).get("archived"):
                raise PermissionError("case_archived")
            if action == "beescan_send":
                self.send(state, payload, actor)
            elif action == "beescan_access":
                self.access(state, payload, actor)
            elif action == "beescan_authorization":
                if set(payload) != {
                    "case_id",
                    "revision",
                    "nonce",
                    "scope",
                    "authority",
                }:
                    raise ValueError("invalid_authorization")
                context = {
                    **state["context"],
                    **{key: text(payload[key], 2048) for key in ("scope", "authority")},
                }
                for kind in ("bearer", "cookie"):
                    self.secrets.pop(context.pop(kind, None), None)
                self.append(state, "context", context, payload["nonce"], actor)
            elif action == "beescan_ask":
                expected = {"case_id", "revision", "nonce", "message"}
                if set(payload) not in (expected, expected | {"mode"}):
                    raise ValueError("invalid_ask")
                message = text(self.redact(text(payload["message"], 2048), actor), 2048)
                if "mode" in payload:
                    if (
                        type(payload["mode"]) is not str
                        or payload["mode"] not in PROFILES
                    ):
                        raise ValueError("unsupported_mode")
                    if payload["mode"] != state["context"].get("mode"):
                        if state["revision"] + 3 > 10000:
                            raise ValueError("conversation_record_limit")
                        context = {**state["context"], "mode": payload["mode"]}
                        self.append(state, "context", context, payload["nonce"], actor)
                self.ask(
                    state,
                    message,
                    payload["nonce"],
                    actor,
                )
            elif action == "beescan_context":
                self.context(state, payload, actor)
            elif action == "beescan_session":
                self.session(state, payload, actor)
            elif action == "beescan_attachment_remove":
                if set(payload) != {
                    "case_id",
                    "revision",
                    "nonce",
                    "storage_run",
                } or not any(
                    item["storage_run"] == payload["storage_run"]
                    and not item.get("removed")
                    for item in state["attachments"]
                ):
                    raise ValueError("invalid_attachment_reference")
                self.append(
                    state,
                    "attachment_remove",
                    {"storage_run": payload["storage_run"]},
                    payload["nonce"],
                    actor,
                )
            elif action == "beescan_investigate":
                self.investigate(state, payload, actor)
            else:
                raise ValueError("unsupported_conversation_action")
        return {"case_id": case_id, "run_id": case_id}

    def context(self, state, payload, actor):
        if set(payload) != {"case_id", "revision", "nonce", "key", "value"}:
            raise ValueError("invalid_context")
        key, value = payload["key"], payload["value"]
        if (
            type(key) is not str
            or key not in _CONTEXT
            and key not in {"bearer", "cookie"}
        ):
            raise ValueError("invalid_context_key")
        context = deepcopy(state["context"])
        if value == "":
            reference = context.pop(key, None)
            if key in {"bearer", "cookie"}:
                self.secrets.pop(reference, None)
        else:
            if key in {"bearer", "cookie"}:
                raise ValueError("protected_secret_input_required")
            value = text(self.redact(text(value, 2048), actor), 2048)
            if key == "target":
                value = origin(value)
            if key == "mode" and value not in PROFILES:
                raise ValueError("unsupported_mode")
            if key == "profile":
                from beeagent_module.integrations.beescan.access_control import (
                    profiles,
                    select_administrative_profile,
                    select_profile,
                )

                settings = self.host.reload_settings()
                selector = (
                    select_administrative_profile
                    if "principals" not in profiles(settings).get(value, {})
                    else select_profile
                )
                selector(settings, value, actor, context.get("target"))
            context[key] = value
            if key == "target":
                settings = self.host.reload_settings()
                if "target_policy" in settings["beescan"]:
                    context["scope"] = state["case_id"]
                    context["authority"] = state["case_id"]
                else:
                    from beeagent_module.integrations.beescan.investigation import (
                        InvestigationPolicy,
                    )

                    policy = InvestigationPolicy.from_config(
                        settings["beescan"]["investigation"]["approval"]
                    )
                    context.pop("scope", None)
                    context.pop("authority", None)
                    try:
                        policy.authorize(value, at=datetime.now(UTC))
                    except ValueError, PermissionError:
                        pass
                    else:
                        context["scope"] = policy.transport.scope_id
                        context["authority"] = policy.transport.mission_id
        if key in {"target", "scope", "authority", "principal"}:
            for kind in ("bearer", "cookie"):
                self.secrets.pop(context.pop(kind, None), None)
        self.append(state, "context", context, payload["nonce"], actor)

    def session(self, state, payload, actor):
        if set(payload) != {"case_id", "revision", "nonce", "kind", "secret"}:
            raise ValueError("invalid_session")
        kind = payload["kind"]
        raw = payload["secret"]
        if type(raw) is not str or any(ord(c) < 32 or ord(c) > 126 for c in raw):
            raise ValueError("invalid_session_value")
        value = text(raw, 4096)
        if value != raw:
            raise ValueError("invalid_session_value")
        context = deepcopy(state["context"])
        if kind not in {"bearer", "cookie"} or not all(
            context.get(k) for k in ("target", "scope", "authority", "principal")
        ):
            raise PermissionError("session_context_required")
        if (
            any(ord(c) < 32 or ord(c) > 126 for c in value)
            or kind == "bearer"
            and " " in value
        ):
            raise ValueError("invalid_session_value")
        if kind == "cookie":
            pairs = value.split(";")
            names = []
            for pair in pairs:
                match = re.fullmatch(
                    r"\s*([A-Za-z0-9_-]{1,80})=([\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]{1,2048})\s*",
                    pair,
                )
                if match is None:
                    raise ValueError("invalid_cookie")
                names.append(match[1])
            if len(set(names)) != len(names) or len(names) > 16:
                raise ValueError("duplicate_cookie")
        existing = context.get(kind)
        if (
            existing in self.secrets
            and self.secrets[existing]["expires"] > time.monotonic()
        ):
            raise PermissionError("duplicate_session_binding")
        for reference in list(self.secrets):
            if self.secrets[reference]["expires"] <= time.monotonic():
                self.secrets.pop(reference)
        if len(self.secrets) >= 128:
            raise PermissionError("session_capacity_exceeded")
        reference = secrets.token_hex(24)
        self.secrets[reference] = {
            "value": value,
            "kind": kind,
            "case_id": state["case_id"],
            "operator": actor["user_id"],
            "origin": context["target"],
            "context": digest(
                {k: context[k] for k in ("target", "scope", "authority", "principal")}
            ),
            "expires": time.monotonic() + 600,
        }
        context[kind] = reference
        try:
            self.append(state, "context", context, payload["nonce"], actor)
        except BaseException:
            self.secrets.pop(reference, None)
            raise

    def access(self, state, payload, actor):
        if set(payload) != {
            "case_id",
            "revision",
            "nonce",
            "principal",
            "profile",
            "kind",
            "secret",
        }:
            raise ValueError("invalid_test_access")
        if payload["kind"] not in {"none", "bearer", "cookie"}:
            raise ValueError("invalid_session_kind")
        context = deepcopy(state["context"])
        if not context.get("target"):
            raise PermissionError("target_context_required")
        for key in ("principal", "profile"):
            value = payload[key]
            if value:
                context[key] = text(self.redact(text(value, 2048), actor), 2048)
            else:
                context.pop(key, None)
        if context.get("profile"):
            from beeagent_module.integrations.beescan.access_control import (
                profiles,
                select_administrative_profile,
                select_profile,
            )

            settings = self.host.reload_settings()
            selector = (
                select_administrative_profile
                if "principals" not in profiles(settings).get(context["profile"], {})
                else select_profile
            )
            selector(settings, context["profile"], actor, context["target"])
        if payload["kind"] != "none" and context.get("profile"):
            raise PermissionError("ambiguous_test_access")
        if payload["kind"] == "none" and payload["secret"]:
            raise ValueError("session_kind_required")
        old_context = state["context"]
        for key in ("bearer", "cookie"):
            context.pop(key, None)
        state["context"] = context
        try:
            if payload["kind"] != "none":
                self.session(
                    state,
                    {
                        key: payload[key]
                        for key in ("case_id", "revision", "nonce", "kind", "secret")
                    },
                    actor,
                )
            else:
                self.append(state, "context", context, payload["nonce"], actor)
        except BaseException:
            state["context"] = old_context
            raise
        for key in ("bearer", "cookie"):
            self.secrets.pop(old_context.get(key), None)

    def send(self, state, payload, actor):
        expected = {"case_id", "revision", "nonce", "message", "mode"}
        if set(payload) != expected or payload["mode"] not in PROFILES:
            raise ValueError("invalid_conversation_send")
        message = text(self.redact(text(payload["message"], 2048), actor), 2048)
        if state["revision"] + 4 > 10000:
            raise ValueError("conversation_record_limit")
        if payload["mode"] != state["context"].get("mode"):
            self.append(
                state,
                "context",
                {**state["context"], "mode": payload["mode"]},
                payload["nonce"],
                actor,
            )
        active = re.match(
            r"(?i)^(?:please\s+)?(?:check|scan|assess|investigate|test|inspect|проверь(?:те)?|исследуй(?:те)?|просканируй(?:те)?|проведи|проведите|найди|найдите|проверить|исследовать)\b",
            message,
        )
        if not active:
            self.ask(state, message, payload["nonce"], actor)
            return
        intent = "Ambiguous/Unsupported"
        try:
            from beeagent_module.integrations.beescan.investigation import _ai

            result = _ai(
                self.host.reload_settings(),
                "conversation_intent",
                {"message": message},
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["intent"],
                    "properties": {
                        "intent": {
                            "type": "string",
                            "enum": ["Ask", "Investigate", "Ambiguous/Unsupported"],
                        }
                    },
                },
                self.host.logger,
            )
            if (
                type(result) is dict
                and set(result) == {"intent"}
                and result["intent"] in {"Ask", "Investigate", "Ambiguous/Unsupported"}
            ):
                intent = result["intent"]
        except ImportError, OSError, RuntimeError, TimeoutError, ValueError:
            intent = "Ambiguous/Unsupported"
        if intent != "Investigate":
            self.ask(state, message, payload["nonce"], actor)
            return
        ru = bool(re.search("[А-Яа-я]", message))
        context = state["context"]
        guidance = None
        if not context.get("target"):
            guidance = (
                "Добавьте цель через + → Добавить цель."
                if ru
                else "Add a Target using + → Add Target."
            )
        elif not all(context.get(key) for key in ("scope", "authority")):
            guidance = (
                (
                    "Требуется разрешение текущей политики хоста: "
                    "+ → Разрешение на тестирование."
                )
                if ru
                else (
                    "Current host-policy authorization is "
                    "required: + → Testing authorization."
                )
            )
        else:
            from beeagent_module.integrations.beescan.web import _requires_test_profile

            if _requires_test_profile(message) and not context.get("profile"):
                guidance = (
                    (
                        "Для IDOR/BOLA нужен утверждённый профиль "
                        "двух тестовых участников: + → Тестовый доступ."
                    )
                    if ru
                    else (
                        "IDOR/BOLA requires an approved two-principal "
                        "test profile: + → Test access."
                    )
                )
            elif any(
                key in context and not self.session_available(context[key])
                for key in ("bearer", "cookie")
            ):
                guidance = (
                    "Введите тестовую сессию повторно: + → Тестовый доступ."
                    if ru
                    else "Re-enter the test session using + → Test access."
                )
        self.append(
            state,
            "message",
            {
                "id": secrets.token_hex(16),
                "sender": "operator",
                "text": message,
                "timestamp": datetime.now(UTC).isoformat(),
                "type": "investigation_request",
                "source": None,
            },
            payload["nonce"],
            actor,
        )
        if guidance is None:
            try:
                self.investigate(
                    state,
                    {
                        key: payload[key]
                        for key in ("case_id", "revision", "nonce", "mode")
                    }
                    | {"task": message},
                    actor,
                    conversational=True,
                )
                return
            except (PermissionError, ValueError, RuntimeError) as failure:
                if str(failure) in {
                    "internal_destination_denied",
                    "target_excluded",
                    "target_not_approved",
                }:
                    guidance = (
                        (
                            "Цель сохранена как данные, но HTTP-проверка "
                            "запрещена текущей политикой хоста."
                        )
                        if ru
                        else (
                            "Target is saved as data, but HTTP investigation "
                            "is prohibited by current host policy."
                        )
                    )
                else:
                    guidance = investigation_guidance(str(failure), ru)
        self.append(
            state,
            "message",
            {
                "id": secrets.token_hex(16),
                "sender": "host",
                "text": guidance,
                "timestamp": datetime.now(UTC).isoformat(),
                "type": "refused",
                "source": None,
            },
            payload["nonce"],
            actor,
        )

    def investigate(self, state, payload, actor, *, conversational=False):
        expected = {"case_id", "revision", "nonce", "task", "mode"}
        if "source_run_id" in payload and not conversational:
            expected.add("source_run_id")
        if not conversational:
            expected.add("confirmation")
        if (
            set(payload) != expected
            or not conversational
            and payload.get("confirmation") != "INVESTIGATE"
        ):
            raise PermissionError("explicit_investigation_required")
        if "source_run_id" in payload:
            view = self.view(state["case_id"], actor)
            if not any(
                item["source_run_id"] == payload["source_run_id"]
                and item["task"] == payload["task"]
                for item in view["retry_actions"]
            ):
                raise PermissionError("investigation_action_source_changed")
        settings = self.host.reload_settings()
        principal(settings, actor, execute=True)
        if type(payload["mode"]) is not str or payload["mode"] not in PROFILES:
            raise ValueError("unsupported_mode")
        task = self.redact(
            text(
                payload["task"], settings["beescan"]["investigation"]["task_chars_max"]
            ),
            actor,
        )
        for run in state["runs"]:
            try:
                if self.host.inspect(run["run_id"], actor)["status"] in {
                    "QUEUED",
                    "RUNNING",
                }:
                    raise PermissionError("conversation_investigation_active")
            except FileNotFoundError:
                pass
        context = state["context"]
        if not all(context.get(k) for k in ("target", "scope", "authority")):
            raise PermissionError("approved_context_required")
        from beeagent_module.integrations.beescan.investigation import (
            InvestigationPolicy,
        )
        from beeagent_module.integrations.beescan.policy import web_execution_policy

        policy = (
            web_execution_policy(settings, context["target"], state["case_id"])
            if "target_policy" in settings["beescan"]
            else InvestigationPolicy.from_config(
                settings["beescan"]["investigation"]["approval"]
            )
        )
        policy.authorize(context["target"], at=datetime.now(UTC))
        if (
            context["scope"] != policy.transport.scope_id
            or context["authority"] != policy.transport.mission_id
        ):
            raise PermissionError("context_authority_changed")
        sessions = [key for key in ("bearer", "cookie") if key in context]
        if sessions:
            from beeagent_module.integrations.beescan.dast import is_dast_task

            if len(sessions) != 1 or context.get("profile") or is_dast_task(task):
                raise PermissionError("session_capability_unavailable")
            self.credential(state["case_id"], context, actor, policy.transport)

        child_payload = {
            "target": context["target"],
            "task": task,
            "mode": payload["mode"],
            "nonce": self.verify_nonce(payload, actor),
        }
        if context.get("profile"):
            child_payload["test_profile_id"] = context["profile"]
        if not conversational:
            self.append(
                state,
                "message",
                {
                    "id": secrets.token_hex(16),
                    "sender": "operator",
                    "text": task,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "type": "investigation_request",
                    "source": payload.get("source_run_id"),
                },
                payload["nonce"],
                actor,
            )
        planned_id = self.host._run_id(actor, child_payload["nonce"])
        attachments = deepcopy(
            [item for item in state["attachments"] if not item.get("removed")]
        )
        self.pending[planned_id] = (
            state["case_id"],
            deepcopy(context),
            dict(actor),
            attachments,
        )
        try:
            result = self.host.start("beescan_start", child_payload, actor)
            if result.get("status") not in {"QUEUED", "REFUSED"}:
                self.pending.pop(planned_id, None)
                raise RuntimeError("web_execution_unavailable")
            if result["status"] == "REFUSED":
                self.pending.pop(planned_id, None)
        except BaseException:
            self.pending.pop(planned_id, None)
            raise
        self.append(
            state,
            "run",
            {
                "run_id": planned_id,
                "context_revision": state["context_revision"],
                "context": deepcopy(context),
                "attachments": attachments,
                "authority_sha256": digest(settings["beescan"]),
            },
            payload["nonce"],
            actor,
        )

    def view(self, case_id, actor, *, offset=None, run_offset=None):
        from beeagent_module.integrations.beescan.executions import records_for_run

        state = self.read(case_id, actor)
        if run_offset is None:
            run_offset = max(0, (len(state["runs"]) - 1) // 25 * 25)
        if type(run_offset) is not int or not 0 <= run_offset <= len(state["runs"]):
            raise ValueError("invalid_run_page")
        metadata = self.host.case_metadata(case_id, actor)
        status = "READY"
        if state["runs"]:
            try:
                status = self.host.inspect(state["runs"][-1]["run_id"], actor)["status"]
            except FileNotFoundError:
                status = "ERROR"
            if state["runs"][-1]["run_id"] in self.running:
                status = "RUNNING"
        summary = {"runs": [], "completed": 0, "active": 0, "findings": []}
        timeline = []
        run_views = {}
        execution_views = {}
        for run in state["runs"][-25:]:
            try:
                child = self.host.inspect(run["run_id"], actor, latest=False)
            except OSError, ValueError, RuntimeError, KeyError, TypeError:
                continue
            run_views[run["run_id"]] = child
            try:
                execution_views[run["run_id"]] = records_for_run(
                    self.host, case_id, run, actor
                )
            except OSError, ValueError:
                pass
            active = run["run_id"] in self.running or child["status"] in {
                "RUNNING",
                "QUEUED",
            }
            summary["active"] += int(active)
            summary["completed"] += int(not active)
            item = {
                "run_id": run["run_id"],
                "status": "RUNNING" if active else child["status"],
                "authenticated": child.get("evidence_authenticated") is True,
            }
            if item["authenticated"]:
                for finding in child.get("findings", []):
                    if (
                        type(finding.get("finding_id")) is not str
                        or type(finding.get("title")) is not str
                    ):
                        continue
                    if len(summary["findings"]) < 16 and not any(
                        entry["finding_id"] == finding["finding_id"]
                        for entry in summary["findings"]
                    ):
                        summary["findings"].append(
                            {
                                **finding,
                                "run_id": run["run_id"],
                                "review_disposition": child.get(
                                    "finding_reviews", {}
                                ).get(finding["finding_id"], "candidate"),
                            }
                        )
                item["requests"] = child.get("request_count")
                item["request_count_exact"] = child.get("request_count_exact") is True
                item["elapsed_seconds"] = child.get("metrics", {}).get(
                    "elapsed_seconds"
                )
                item["findings"] = len(child.get("findings", []))
                item["candidates"] = sum(
                    finding.get("status") == "candidate"
                    for finding in child.get("findings", [])
                )
            summary["runs"].append(item)
        if len(summary["runs"]) == len(state["runs"]):
            summary["findings_complete"] = len(summary["findings"]) < 16 and all(
                item["authenticated"] for item in summary["runs"]
            )
            if len(execution_views) == len(state["runs"]) and all(
                execution_views.values()
            ):
                stages = [
                    item
                    for executions in execution_views.values()
                    for item in executions
                    if item["kind"] in {"discovery", "verification"}
                ]
                summary["execution_count"] = len(stages)
                summary["execution_errors"] = sum(
                    item["status"] in {"ERROR", "TIMEOUT", "REFUSED"} for item in stages
                )
            if all(
                item.get("request_count_exact") and type(item.get("requests")) is int
                for item in summary["runs"]
            ):
                summary["request_count"] = sum(
                    item["requests"] for item in summary["runs"]
                )
        from beeagent_module.integrations.beescan.progress import conversation_run

        records = state["sequence"]
        if offset is None:
            offset = max(0, (len(records) - 1) // 8 * 8)
        if type(offset) is not int or not 0 <= offset <= len(records):
            raise ValueError("invalid_message_page")
        messages = []
        for record in records[offset : offset + 8]:
            item = record["data"]
            child_id = (
                item["run_id"]
                if record["kind"] == "run"
                else item.get("source")
                if item.get("type") == "investigation"
                else None
            )
            child = None
            if child_id:
                child = run_views.get(child_id)
                if child is None:
                    child = self.host.inspect(child_id, actor, latest=False)
                    run_views[child_id] = child
            if record["kind"] == "run":
                message = {
                    "id": "run-" + item["run_id"],
                    "sender": "host",
                    "text": "",
                    "timestamp": record["timestamp"],
                    "type": "run",
                    "source": item["run_id"],
                }
                try:
                    if child_id not in execution_views:
                        execution_views[child_id] = records_for_run(
                            self.host, case_id, item, actor
                        )
                    message["executions"] = execution_views[child_id]
                except FileNotFoundError:
                    pass
            else:
                message = dict(item)
            if child is not None:
                message["investigation"] = conversation_run(
                    child, active=child_id in self.running
                )
                message["investigation"]["has_conclusion"] = any(
                    entry.get("type") == "investigation"
                    and entry.get("source") == child_id
                    for entry in state["messages"]
                )
            messages.append(message)
        latest_view = (
            run_views.get(state["runs"][-1]["run_id"]) if state["runs"] else None
        )
        latest_run = (
            conversation_run(
                latest_view, active=state["runs"][-1]["run_id"] in self.running
            )
            if latest_view
            else None
        )
        timeline = latest_view.get("timeline", []) if latest_view else []
        retry_actions = []
        context = state["context"]
        if (
            latest_run
            and latest_run["source_available"]
            and status not in {"RUNNING", "QUEUED"}
            and latest_run["target"] == context.get("target")
            and all(context.get(key) for key in ("target", "scope", "authority"))
            and actor["role"] in {"operator", "admin"}
            and not metadata.get("archived", False)
        ):
            settings = self.host.reload_settings()
            try:
                require_web_execution_authority(settings, actor)
                if "target_policy" in settings["beescan"]:
                    check_target_exclusions(settings, context["target"])
                else:
                    from beeagent_module.integrations.beescan.investigation import (
                        InvestigationPolicy,
                    )

                    policy = InvestigationPolicy.from_config(
                        settings["beescan"]["investigation"].get("approval")
                    )
                    policy.authorize(context["target"], at=datetime.now(UTC))
                    if (
                        context["scope"] != policy.transport.scope_id
                        or context["authority"] != policy.transport.mission_id
                    ):
                        raise PermissionError("context_authority_changed")
            except PermissionError, ValueError:
                pass
            else:
                retry_actions.append(
                    {
                        "source_run_id": latest_run["run_id"],
                        "task": "Assess web security (fresh full retry)",
                        "case_id": case_id,
                        "revision": str(state["revision"]),
                        "nonce": self.nonce(actor, case_id, state["revision"]),
                        "mode": state["context"].get("mode", "quick"),
                        "confirmation": "INVESTIGATE",
                    }
                )
        return {
            "case_id": case_id,
            "run_id": case_id,
            "conversation": True,
            "revision": state["revision"],
            "context_revision": state["context_revision"],
            "context": state["context"],
            "session_states": {
                kind: self.session_available(state["context"].get(kind))
                for kind in ("bearer", "cookie")
            },
            "messages": messages,
            "timeline": timeline,
            "latest_investigation": latest_run,
            "next_actions": [],
            "next_action_reason": "case_archived"
            if metadata.get("archived", False)
            else "operator_required"
            if actor["role"] not in {"operator", "admin"}
            else "investigation_active"
            if status in {"RUNNING", "QUEUED"}
            else "no_authenticated_source"
            if not latest_run or not latest_run["source_available"]
            else "target_context_changed"
            if latest_run["target"] != state["context"].get("target")
            else "source_bound_continuation_unavailable",
            "retry_actions": retry_actions,
            "runs": [
                {
                    "run_id": item["run_id"],
                    "context_revision": item["context_revision"],
                    "snapshot_sha256": digest(item),
                }
                for item in state["runs"][run_offset : run_offset + 25]
            ],
            "run_offset": run_offset,
            "run_count": len(state["runs"]),
            "summary": summary,
            "attachments": state["attachments"],
            "message_count": len(records),
            "status": status,
            "message_offset": offset,
            "mode": state["context"].get("mode", "quick"),
            "display_title": metadata.get("title")
            or (state["messages"][0]["text"][:100] if state["messages"] else case_id),
            "intake": None,
            "findings": [],
            "archived": metadata.get("archived", False),
        }

    def execution(self, case_id, run_id, execution_id, actor):
        from beeagent_module.integrations.beescan.executions import records_for_run

        state = self.read(case_id, actor)
        run = next((item for item in state["runs"] if item["run_id"] == run_id), None)
        if run is not None:
            for item in records_for_run(self.host, case_id, run, actor):
                if item["id"] == execution_id:
                    return item
        raise PermissionError("execution_reference_refused")

    def credential(
        self, case_id, context, actor, policy: ProbePolicy
    ) -> tuple[str, str] | None:
        self.owned(case_id, actor)
        kinds = [key for key in ("bearer", "cookie") if key in context]
        if not kinds:
            return None
        if len(kinds) != 1:
            raise PermissionError("ambiguous_session")
        kind = kinds[0]
        binding = self.secrets.get(context[kind])
        expected = {
            k: context[k] for k in ("target", "scope", "authority", "principal")
        }
        if (
            not binding
            or binding["expires"] <= time.monotonic()
            or binding["case_id"] != case_id
            or binding["operator"] != actor["user_id"]
            or binding["origin"] != policy.origin
            or binding["context"] != digest(expected)
            or context["scope"] != policy.scope_id
            or context["authority"] != policy.mission_id
        ):
            raise PermissionError("session_reprovision_required")
        return kind, binding["value"]

    def resolver(
        self, invocation
    ) -> Callable[[ProbePolicy], tuple[str, str] | None] | None:
        binding = self.pending.pop(invocation.run_id, None)
        if binding is None:
            return None
        invocation.conversation_binding = binding
        self.running.add(invocation.run_id)
        case_id, context, actor = binding[:3]
        if not any(kind in context for kind in ("bearer", "cookie")):
            return None

        def resolve(policy):
            invocation.verify()
            return self.credential(case_id, context, actor, policy)

        return resolve

    def upload(self, payload, files, actor):
        from beeagent_module.core.attachment_store import (
            persist_run_attachments,
            read_attachment_blob,
        )
        from beeagent_module.integrations.beescan.conversation_inputs import (
            validate_attachment,
        )

        if (
            type(payload) is not dict
            or set(payload) not in ({"case_id", "revision", "nonce"}, {"nonce"})
            or type(files) is not list
            or not 1 <= len(files) <= 8
        ):
            raise ValueError("invalid_attachment_intake")
        principal(self.host.reload_settings(), actor)
        if actor["role"] not in {"operator", "admin"}:
            raise PermissionError("conversation_operator_required")
        if set(payload) == {"nonce"}:
            for item in files:
                validate_attachment(item, lambda value: self.redact(value, actor))
            created = self.create(payload, actor, initial_action="beescan_attach")
            case_id = created["case_id"]
            payload = {
                "case_id": case_id,
                "revision": "0",
                "nonce": self.nonce(actor, case_id, 0),
            }
        self.verify_nonce(payload, actor)
        with self.lock(payload["case_id"], actor):
            state = self.read(payload["case_id"], actor)
            if (
                str(state["revision"]) != payload["revision"]
                or digest(payload["nonce"]) in state["nonces"]
            ):
                raise PermissionError("conversation_replay_or_conflict")
            if state["revision"] >= 10000:
                raise ValueError("conversation_record_limit")
            count = sum(len(item["items"]) for item in state["attachments"])
            size = sum(item["input_bytes"] for item in state["attachments"])
            incoming = sum(len(item["content"]) for item in files)
            if count + len(files) > 8 or size + incoming > 16 * 1024 * 1024:
                raise ValueError("case_attachment_limit")
            validated = [
                validate_attachment(item, lambda value: self.redact(value, actor))
                for item in files
            ]
            storage_run = "web-upload-" + secrets.token_hex(20)
            directory = open_directory(self.host.storage)
            try:
                try:
                    os.mkdir("attachments", 0o700, dir_fd=directory)
                except FileExistsError:
                    pass
                attachments = open_child(directory, "attachments", private=True)
                try:
                    os.mkdir(storage_run, 0o700, dir_fd=attachments)
                finally:
                    os.close(attachments)
            finally:
                os.close(directory)
            manifest = persist_run_attachments(
                self.host.storage,
                storage_run,
                [{"event_id": "observation", "_raw_attachments": validated}],
                {
                    "storage": {
                        "enabled": True,
                        "file_max": 2097152,
                        "message_max": 16777216,
                        "files_message_max": 8,
                    }
                },
                self.host.logger,
            )
            if manifest["aggregate"]["stored_count"] != len(validated):
                raise OSError("attachment_publication_incomplete")
            for item, expected in zip(manifest["items"], validated, strict=True):
                actual = read_attachment_blob(
                    self.host.storage, storage_run, item["attachment_id"]
                )
                if actual is None or actual[0] != expected["payload"]:
                    raise OSError("attachment_readback_failed")
            self.append(
                state,
                "attachment",
                {
                    "storage_run": storage_run,
                    "input_bytes": incoming,
                    "items": [
                        {
                            k: item[k]
                            for k in (
                                "attachment_id",
                                "filename",
                                "content_type",
                                "size_bytes",
                                "sha256",
                            )
                        }
                        for item in manifest["items"]
                    ],
                    "trust": "untrusted_observation",
                    "ai_visible": False,
                },
                payload["nonce"],
                actor,
            )
        return {"case_id": state["case_id"], "run_id": state["case_id"]}

    def finish(self, invocation):
        binding = getattr(invocation, "conversation_binding", None)
        if binding is None:
            return
        case_id, _context, actor = binding[:3]
        with self.lock(case_id, actor, wait=True):
            state = self.read(case_id, actor)
            nonce = "completion:" + invocation.run_id
            if digest(nonce) in state["nonces"]:
                return
            result = self.host.inspect(invocation.run_id, actor)
            self.append(
                state,
                "message",
                {
                    "id": secrets.token_hex(16),
                    "sender": "host",
                    "text": "Investigation "
                    + invocation.run_id
                    + ": "
                    + result["status"]
                    + "; requests: "
                    + str(result.get("request_count")),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "type": "investigation",
                    "source": invocation.run_id,
                },
                nonce,
                actor,
            )

    def session_available(self, reference):
        binding = self.secrets.get(reference)
        return bool(binding and binding["expires"] > time.monotonic())
