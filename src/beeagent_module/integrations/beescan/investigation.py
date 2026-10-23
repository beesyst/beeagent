import json
import logging
import math
import os
import re
import stat
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

import yaml

from beeagent_module.core.ai_transport import call_structured_ai
from beeagent_module.core.artifact_api import ArtifactAPI
from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.paths import get_project_root
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)
from beeagent_module.integrations.beescan.policy import ProbePolicy


@dataclass(frozen=True)
class InvestigationPolicy:
    transport: ProbePolicy
    discovery: bool
    baseline: bool
    mutation: bool
    method: str
    mutation_profile: str
    request_budget: int

    @classmethod
    def from_config(cls, config):
        if type(config) is not dict or set(config) != set(cls.__dataclass_fields__):
            raise ValueError("invalid_investigation_approval")
        values = dict(config)
        values["transport"] = ProbePolicy.from_config(values["transport"])
        return cls(**values)

    def __post_init__(self):
        if (
            any(
                type(value) is not bool
                for value in (self.discovery, self.baseline, self.mutation)
            )
            or self.method != "GET"
            or self.mutation_profile != "numeric_invalid_v1"
            or type(self.request_budget) is not int
            or self.request_budget != 3
            or self.transport.network_namespace != "/beeagent-managed/ns/net"
            or self.transport.user_namespace != "/beeagent-managed/ns/user"
        ):
            raise ValueError("invalid_investigation_approval")

    def authorize(self, target, *, at):
        if not all((self.discovery, self.baseline, self.mutation)):
            raise PermissionError("investigation_not_approved")
        if target != self.transport.origin:
            raise PermissionError("target_not_approved")
        self.transport.authorize(
            self.transport.intent(), operator_uid=os.getuid(), at=at
        )


def named_ai_profile(settings, *, require_key=True):
    config = settings["beescan"]["investigation"]
    profile = settings.get("ai", {}).get("profiles", {}).get(config["ai_profile"])
    if type(profile) is not dict:
        raise ValueError("invalid_investigation_ai_profile")
    selected = {}
    for key in ("provider", "model", "api_key_env", "base_url"):
        value = profile.get(key)
        if type(value) is not str or not value.strip() or len(value) > 256:
            raise ValueError("invalid_investigation_ai_profile")
        selected[key] = value
    parsed = urlsplit(selected["base_url"])
    if (
        selected["provider"] not in {"openai_responses", "openai_compatible"}
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port is not None
        and not 1 <= parsed.port <= 65535
        or any(ord(c) < 33 or ord(c) > 126 for c in selected["base_url"])
        or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", selected["api_key_env"])
    ):
        raise ValueError("invalid_investigation_ai_profile")
    if require_key and not os.getenv(selected["api_key_env"], "").strip():
        raise ValueError("investigation_ai_key_missing")
    return selected


def validate_investigation_settings(settings, *, validate_contracts=True):
    beescan = settings.get("beescan", {})
    if "investigation" not in beescan:
        return
    config = beescan["investigation"]
    limits = {
        "task_bytes_max": (128, 16384),
        "task_chars_max": (32, 4000),
        "timeout_seconds": (1, 60),
        "input_chars_max": (512, 16000),
        "output_chars_max": (128, 4000),
        "body_bytes_max": (1024, 16384),
    }
    if (
        type(config) is not dict
        or set(config) - {"local_lab_enabled"}
        != {"enabled", "approval", "ai_profile", *limits}
        or type(config["enabled"]) is not bool
        or type(config.get("local_lab_enabled", False)) is not bool
        or type(config["ai_profile"]) is not str
        or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", config["ai_profile"])
    ):
        raise RuntimeError("Invalid beescan.investigation settings")
    for key, (low, high) in limits.items():
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise RuntimeError("Invalid beescan.investigation limits")
    if config["approval"] is not None and type(config["approval"]) is not dict:
        raise RuntimeError("Invalid beescan.investigation approval")
    if config["enabled"]:
        enabled = any(
            item.get("id") == "beescan" and item.get("enabled") is True
            for item in settings.get("modules", {}).get("registry", [])
        )
        if not enabled or config["approval"] is None:
            raise RuntimeError("BeeScan investigation requires independent approval")
    try:
        named_ai_profile(settings, require_key=config["enabled"])
        if validate_contracts and config["approval"] is not None:
            InvestigationPolicy.from_config(config["approval"])
    except ImportError, KeyError, TypeError, ValueError:
        raise RuntimeError(
            "Invalid beescan.investigation contract or AI profile"
        ) from None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique)
    except ValueError, UnicodeError, RecursionError:
        raise ValueError("invalid_investigation_json") from None


def read_task(path, config):
    path = Path(path)
    if ".." in path.parts or not path.name or len(str(path)) > 4096:
        raise ValueError("unsafe_task_path")
    parts = path.parts[1:] if path.is_absolute() else path.parts
    directory = os.open(
        "/" if path.is_absolute() else ".", os.O_RDONLY | os.O_DIRECTORY
    )
    try:
        for part in parts[:-1]:
            next_directory = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = next_directory
        descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_mode & 0o077
                or before.st_nlink != 1
                or not 1 <= before.st_size <= config["task_bytes_max"]
            ):
                raise ValueError("unsafe_task_file")
            raw = stream.read(config["task_bytes_max"] + 1)
            after = os.fstat(stream.fileno())
            if (
                any(
                    getattr(after, key) != getattr(before, key)
                    for key in (
                        "st_dev",
                        "st_ino",
                        "st_size",
                        "st_uid",
                        "st_mode",
                        "st_nlink",
                        "st_mtime_ns",
                        "st_ctime_ns",
                    )
                )
                or len(raw) != before.st_size
            ):
                raise ValueError("task_file_changed")
    finally:
        os.close(directory)
    value = _json(raw)
    if type(value) is not dict or set(value) != {"target", "task"}:
        raise ValueError("invalid_task_schema")
    if (
        type(value["target"]) is not str
        or len(value["target"]) > 2048
        or type(value["task"]) is not str
        or not value["task"].strip()
        or not 1 <= len(value["task"]) <= config["task_chars_max"]
        or any(ord(c) < 32 or ord(c) == 127 for c in value["task"])
    ):
        raise ValueError("invalid_task_schema")
    return value


def _prompt(settings, name, facts):
    path = get_project_root() / settings["ai"]["prompts"]["path"]
    prompt = yaml.safe_load(path.read_text(encoding="utf-8"))["beescan"][name]
    result = (
        prompt["system"]
        + "\n"
        + prompt["user"].replace(
            "{facts_json}", json.dumps(facts, ensure_ascii=True, sort_keys=True)
        )
    )
    if len(result) > settings["beescan"]["investigation"]["input_chars_max"]:
        raise ValueError("investigation_ai_input_limit")
    return result


def _ai(settings, name, facts, schema, logger, *, deadline=None):
    config = settings["beescan"]["investigation"]
    profile = named_ai_profile(settings)
    private_logger = logging.Logger("beescan.ai.private")
    private_logger.addHandler(logging.NullHandler())
    timeout = config["timeout_seconds"]
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise TimeoutError("investigation_deadline")
    raw = call_structured_ai(
        prompt=_prompt(settings, name, facts),
        provider=profile["provider"],
        model=profile["model"],
        api_key=os.getenv(profile["api_key_env"], ""),
        base_url=profile["base_url"],
        timeout_seconds=timeout,
        max_output_tokens=max(1, config["output_chars_max"] // 4),
        temperature=0.0,
        responses_text_format={
            "type": "json_schema",
            "name": name,
            "strict": True,
            "schema": schema,
        },
        output_chars_max=config["output_chars_max"],
        logger=private_logger,
    )
    if type(raw) is not str or not 1 <= len(raw) <= config["output_chars_max"]:
        logger.warning("BeeScan investigation AI response unavailable")
        raise ValueError("investigation_ai_unavailable")
    return _json(raw)


def classify_task(settings, task, logger, *, deadline=None):
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["intent"],
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "framework_version_disclosure",
                    "unsupported",
                    "ambiguous",
                ],
            }
        },
    }
    plan = _ai(
        settings,
        "task_classification",
        {"task": task},
        schema,
        logger,
        deadline=deadline,
    )
    if type(plan) is not dict or set(plan) != {"intent"}:
        raise ValueError("invalid_investigation_plan")
    if plan["intent"] != "framework_version_disclosure":
        raise ValueError("unsupported_investigation_task")
    return plan["intent"]


def explain_result(settings, facts, logger, *, deadline=None):
    allowed = {"status", "framework", "version", "evidence_refs", "disposition"}
    if type(facts) is not dict or set(facts) != allowed:
        raise ValueError("invalid_explanation_facts")
    if (
        type(facts["status"]) is not str
        or facts["status"]
        not in {"match", "no_match", "inconclusive", "refused", "timeout", "error"}
        or type(facts["evidence_refs"]) is not list
        or len(facts["evidence_refs"]) > 12
        or any(
            type(ref) is not str
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", ref) is None
            for ref in facts["evidence_refs"]
        )
    ):
        raise ValueError("invalid_explanation_facts")
    if facts["status"] == "match":
        if (
            type(facts["framework"]) is not str
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9 -]{0,63}", facts["framework"]) is None
            or type(facts["version"]) is not str
            or re.fullmatch(r"[0-9][A-Za-z0-9.-]{0,31}", facts["version"]) is None
            or facts["disposition"] != "candidate"
            or not facts["evidence_refs"]
        ):
            raise ValueError("invalid_explanation_facts")
        expected = (
            f"The response disclosed {facts['framework']} {facts['version']}; "
            "this is a candidate observation requiring independent human verification."
        )
    else:
        if any(
            facts[key] is not None for key in ("framework", "version", "disposition")
        ):
            raise ValueError("invalid_explanation_facts")
        expected = (
            "No framework version disclosure was established "
            "from the bounded response evidence."
        )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["facts", "explanation"],
        "properties": {
            "facts": {
                "type": "object",
                "additionalProperties": False,
                "required": sorted(allowed),
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": [
                            "match",
                            "no_match",
                            "inconclusive",
                            "refused",
                            "timeout",
                            "error",
                        ],
                    },
                    "framework": {"type": ["string", "null"], "maxLength": 64},
                    "version": {"type": ["string", "null"], "maxLength": 32},
                    "disposition": {
                        "type": ["string", "null"],
                        "enum": ["candidate", None],
                    },
                    "evidence_refs": {
                        "type": "array",
                        "maxItems": 12,
                        "items": {
                            "type": "string",
                            "maxLength": 64,
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$",
                        },
                    },
                },
            },
            "explanation": {"type": "string", "enum": [expected]},
        },
    }
    response = _ai(
        settings,
        "result_explanation",
        {
            "facts": facts,
            "allowed_explanation": expected,
        },
        schema,
        logger,
        deadline=deadline,
    )
    if (
        type(response) is not dict
        or set(response) != {"facts", "explanation"}
        or response["facts"] != facts
        or response["explanation"] != expected
        or type(response["explanation"]) is not str
        or not 1 <= len(response["explanation"]) <= 1000
        or any(ord(c) < 32 or ord(c) == 127 for c in response["explanation"])
    ):
        raise ValueError("invalid_investigation_explanation")
    return {"authoritative": False, "explanation": response["explanation"]}


def _validate_request_pair(baseline, mutation):
    first, second = urlsplit(baseline.relative_url), urlsplit(mutation.relative_url)
    before = parse_qsl(first.query, strict_parsing=True, keep_blank_values=True)
    after = parse_qsl(second.query, strict_parsing=True, keep_blank_values=True)
    changes = [(old, new) for old, new in zip(before, after) if old != new]
    if (
        first.path != second.path
        or first.scheme
        or first.netloc
        or first.fragment
        or second.scheme
        or second.netloc
        or second.fragment
        or not before
        or len(before) != len(after)
        or len({key for key, _ in before}) != len(before)
        or len(changes) != 1
        or changes[0][0][0] != changes[0][1][0]
        or re.fullmatch(r"[0-9]{1,18}", changes[0][0][1]) is None
        or changes[0][1][1] != "invalid"
    ):
        raise PermissionError("invalid_investigation_mutation")


class _CaptureHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag == "a":
            hrefs = [value for name, value in attrs if name == "href"]
            if len(hrefs) > 1:
                raise ValueError("ambiguous_discovery_link")
            if hrefs:
                value = hrefs[0]
                if type(value) is not str or not 1 <= len(value) <= 512:
                    raise ValueError("invalid_discovery_link")
                self.links.append(value)
                if len(self.links) > 64:
                    raise ValueError("discovery_link_limit")
        if tag in {"p", "div", "pre", "br", "h1", "h2", "h3", "li"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "pre", "h1", "h2", "h3", "li"}:
            self.text.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def capture_to_facts(
    selected,
    captured,
    *,
    policy,
    domain,
    provider_id,
    provider_version,
    response_id,
    evidence_ref,
    elapsed_seconds,
    body_bytes_max,
):
    from beescan.capabilities.http_probe import HostProvenance

    expected = {
        "origin": policy.transport.origin,
        "connected_ip": policy.transport.connected_ip,
        "port": policy.transport.port,
        "method": "GET",
        "relative_url": selected.relative_url,
        "request_count": 1,
        "complete": True,
    }
    if (
        type(captured) is not dict
        or set(captured) != {*expected, "status_code", "content_type", "body"}
        or any(
            type(captured[key]) is not type(value) or captured[key] != value
            for key, value in expected.items()
        )
        or selected.origin != policy.transport.origin
        or type(body_bytes_max) is not int
        or not 1024 <= body_bytes_max <= 16384
        or type(captured["body"]) is not str
        or len(captured["body"].encode("utf-8")) > body_bytes_max
    ):
        raise ValueError("invalid_investigation_capture")
    links, excerpt = (), ""
    if captured["content_type"] in {"text/html", "application/xhtml+xml"}:
        parser = _CaptureHTML()
        parser.feed(captured["body"])
        parser.close()
        if selected.stage == "discovery":
            links = tuple(parser.links)
        if selected.stage == "mutation":
            excerpt = "".join(parser.text)
    elif selected.stage == "mutation":
        excerpt = captured["body"]
    if len(excerpt) > 16384:
        raise ValueError("investigation_excerpt_limit")
    return domain.WebResponseFacts(
        request=selected,
        provenance=HostProvenance(selected.child_run_id, provider_id, provider_version),
        response_id=response_id,
        evidence_refs=(evidence_ref,),
        status_code=captured["status_code"],
        content_type=captured["content_type"],
        complete=True,
        elapsed_seconds=elapsed_seconds,
        excerpt=excerpt,
        links=links,
    )


def collect_investigation(
    intent,
    *,
    policy,
    domain,
    capture,
    reload_policy,
    persist_source,
    verify_source,
    clock=lambda: datetime.now(UTC),
    monotonic=time.monotonic,
):
    deadline = monotonic() + policy.transport.time_budget_seconds
    sources = []
    request_count = 0

    def checkpoint():
        if monotonic() >= deadline:
            raise TimeoutError("investigation_deadline")
        current = reload_policy()
        if current != policy:
            raise PermissionError("approval_changed")
        policy.authorize(intent.origin, at=clock())
        intent.validate_at(clock())

    def request(selected):
        nonlocal request_count
        checkpoint()
        if (
            len(sources) >= policy.request_budget
            or selected.http_method != policy.method
            or selected.origin != policy.transport.origin
            or selected.mission_id != policy.transport.mission_id
            or selected.target_id != policy.transport.target_id
            or selected.run_id != intent.run_id
        ):
            raise PermissionError("investigation_request_refused")
        facts, actual_count = capture(selected, reauthorize=checkpoint)
        if type(actual_count) is not int or actual_count != 1:
            raise ValueError("invalid_investigation_request_count")
        request_count += actual_count
        if (
            facts.request != selected
            or facts.provenance.run_id != selected.child_run_id
        ):
            raise ValueError("invalid_investigation_source")
        persist_source(facts)
        sources.append(facts)
        if verify_source(facts) is not True:
            raise ValueError("unauthenticated_investigation_source")
        checkpoint()
        return facts

    discovery = request(intent.discovery)
    selection = domain.select_investigation(intent, discovery, at=clock())
    baseline = mutation = None
    if selection.status is None:
        _validate_request_pair(selection.baseline, selection.mutation)
        baseline = request(selection.baseline)
        if baseline.complete and baseline.status_code == 200:
            mutation = request(selection.mutation)
    checkpoint()
    for facts in sources:
        if verify_source(facts) is not True:
            raise ValueError("investigation_source_changed")
    result = domain.analyze_investigation(selection, baseline, mutation, at=clock())
    return result, tuple(sources), request_count


def _load_domain(*, local_lab=False, policy=None):
    import importlib
    import importlib.metadata
    import tomllib

    project_file = (get_project_root() / "pyproject.toml").resolve()
    project = tomllib.loads(project_file.read_text())
    source = project.get("tool", {}).get("uv", {}).get("sources", {}).get("beescan", {})
    if local_lab is True:
        if (
            type(policy) is not InvestigationPolicy
            or not policy.transport.allow_private_lab
        ):
            raise PermissionError("local_laboratory_not_approved")
        policy.authorize(policy.transport.origin, at=datetime.now(UTC))
        address = ip_address(policy.transport.connected_ip)
        if not any(
            address in ip_network(network)
            for network in (
                "127.0.0.0/8",
                "::1/128",
                "10.0.0.0/8",
                "172.16.0.0/12",
                "192.168.0.0/16",
                "fc00::/7",
                "192.0.2.0/24",
                "198.51.100.0/24",
                "203.0.113.0/24",
                "2001:db8::/32",
            )
        ):
            raise PermissionError("local_laboratory_target_required")
        expected = Path("/home/bee/Pro/beescan")
        if (
            source != {"path": "../beescan", "editable": True}
            or (project_file.parent / source["path"]).resolve() != expected
        ):
            raise ImportError("local_editable_dependency_unavailable")
        distribution = importlib.metadata.distribution("beescan")
        direct = _json(distribution.read_text("direct_url.json") or "{}")
        if (
            type(direct) is not dict
            or set(direct) != {"url", "dir_info"}
            or direct["dir_info"] != {"editable": True}
            or type(direct["url"]) is not str
        ):
            raise ImportError("local_editable_dependency_unavailable")
        installed = urlsplit(direct["url"])
        if (
            installed.scheme != "file"
            or installed.netloc
            or installed.query
            or installed.fragment
            or not Path(unquote(installed.path)).is_absolute()
            or Path(unquote(installed.path)).resolve() != expected
        ):
            raise ImportError("local_editable_dependency_unavailable")
        for name in (
            "beescan",
            "beescan.domain.models",
            "beescan.domain.scope",
            "beescan.capabilities.http_probe",
            "beescan.domain.web_investigation",
        ):
            module = importlib.import_module(name)
            suffix = name.replace(".", "/") + (
                "/__init__.py" if name == "beescan" else ".py"
            )
            module_file = getattr(module, "__file__", None)
            if (
                not isinstance(module_file, str)
                or not module_file
                or Path(module_file).resolve() != expected / "src" / suffix
            ):
                raise ImportError("local_editable_dependency_unavailable")
        return module, "editable:" + str(expected)
    git_url = "https://github.com/beesyst/beescan.git"
    if (
        type(source) is not dict
        or source.get("git") != git_url
        or "path" in source
        or "editable" in source
    ):
        raise ImportError("reviewed_it10_revision_unavailable")
    try:
        lock = tomllib.loads((project_file.parent / "uv.lock").read_text())
        packages = lock.get("package")
        if type(packages) is not list:
            raise ImportError("reviewed_it10_revision_unavailable")
        locked = [
            package
            for package in packages
            if type(package) is dict and package.get("name") == "beescan"
        ]
        if len(locked) != 1:
            raise ImportError("reviewed_it10_revision_unavailable")
        package = locked[0]
        locked_source = package.get("source")
        version = package.get("version")
        requirement = (
            project.get("project", {}).get("optional-dependencies", {}).get("beescan")
        )
        if (
            type(locked_source) is not dict
            or set(locked_source) != {"git"}
            or type(locked_source["git"]) is not str
            or type(version) is not str
            or not version
            or requirement != [f"beescan=={version}"]
        ):
            raise ImportError("reviewed_it10_revision_unavailable")
        match = re.fullmatch(
            re.escape(git_url) + r"#([0-9a-f]{40})", locked_source["git"]
        )
        if match is None:
            raise ImportError("reviewed_it10_revision_unavailable")
        revision = match.group(1)
        distribution = importlib.metadata.distribution("beescan")
        direct = _json(distribution.read_text("direct_url.json") or "{}")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ImportError("reviewed_it10_revision_unavailable") from exc
    if (
        distribution.version != version
        or type(direct) is not dict
        or direct.get("url") != git_url
        or "dir_info" in direct
        or "archive_info" in direct
        or type(direct.get("vcs_info")) is not dict
        or direct["vcs_info"].get("vcs") != "git"
        or direct["vcs_info"].get("commit_id") != revision
    ):
        raise ImportError("reviewed_it10_revision_unavailable")
    domain = importlib.import_module("beescan.domain.web_investigation")
    expected = distribution.locate_file("beescan/domain/web_investigation.py")
    module_file = getattr(domain, "__file__", None)
    if (
        not isinstance(module_file, str)
        or not module_file
        or Path(module_file).resolve() != Path(str(expected)).resolve()
    ):
        raise ImportError("reviewed_it10_revision_unavailable")
    return domain, revision


def _prepare_intent(domain, policy, run_id):
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        MissionSpec,
        Project,
        Target,
        TargetKind,
    )

    transport = policy.transport
    return domain.prepare_investigation(
        Project(transport.project_id, "Approved web investigation"),
        (
            Target(
                transport.target_id,
                transport.project_id,
                TargetKind.URL,
                transport.origin,
            ),
        ),
        EngagementScope(
            transport.scope_id,
            transport.project_id,
            (transport.target_id,),
            transport.scope_id,
            valid_from=transport.valid_from,
            expires_at=transport.expires_at,
            approved_methods=(domain.METHOD,),
            max_requests=3,
            max_seconds=transport.time_budget_seconds,
        ),
        Mission(
            transport.mission_id,
            transport.project_id,
            transport.scope_id,
            (domain.CAPABILITY,),
        ),
        MissionSpec(
            transport.mission_id,
            transport.target_id,
            domain.CAPABILITY,
            domain.METHOD,
            3,
            transport.time_budget_seconds,
        ),
        at=datetime.now(UTC),
        run_id=run_id,
        provider_id="host-web-capture",
        provider_version="1",
    )


def execute_investigation(*, task_path, settings, reload_settings, storage_dir, logger):
    from beeagent_module.integrations.beescan.assessment import _write_report
    from beeagent_module.integrations.beescan.detection import _persist
    from beeagent_module.integrations.beescan.detection_runner import (
        run_detection_provider,
    )
    from beeagent_module.integrations.beescan.egress import ManagedEgress, checkpoint
    from beeagent_module.integrations.beescan.http_runner import verify_resolution
    from beeagent_module.integrations.beescan.review_source import (
        AssessmentSnapshot,
        open_child,
        open_directory,
    )

    settings = deepcopy(settings)
    run_id, session_id = generate_run_id("investigation"), generate_session_id()

    def api(child_run_id):
        Path(storage_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = open_directory(storage_dir)
        try:
            for part in ("runs", child_run_id, "module-beescan"):
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                child = open_child(descriptor, part)
                os.close(descriptor)
                descriptor = child
        finally:
            os.close(descriptor)
        result = ArtifactAPI(
            RuntimeContext(
                run_id=child_run_id,
                session_id=session_id,
                case_type="web_investigation",
                module_id="beescan",
                authority=AuthorityLevel.EXECUTION_CAPABLE,
            ),
            storage_dir,
            logger,
        )
        result.artifact_dir().chmod(0o700)
        return result

    artifacts = api(run_id)
    status = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "REFUSED",
        "complete": False,
        "reason": "capability_disabled",
        "request_count": 0,
        "request_count_exact": True,
        "capture_launch_count": 0,
        "evidence_refs": [],
        "integration_status": "BLOCKED",
    }
    _persist(artifacts, "investigation_status.json", status)
    config = settings.get("beescan", {}).get("investigation", {})
    steps, source_manifest, records = [], [], {}
    snapshot = AssessmentSnapshot(storage_dir)
    session = policy = intent = None
    analysis = explanation = None
    started = time.monotonic()
    deadline = None

    def authorize(*, resolve=False):
        current_policy = policy
        if current_policy is None:
            raise PermissionError("investigation_not_approved")
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("investigation_deadline")
        if reload_settings() != settings:
            raise PermissionError("approval_changed")
        current_policy.authorize(current_policy.transport.origin, at=datetime.now(UTC))
        if intent is not None:
            intent.validate_at(datetime.now(UTC))
        snapshot.verify()
        if resolve:
            verify_resolution(current_policy.transport)
        if session is not None and not session.closed:
            checkpoint(current_policy.transport)
        return current_policy

    def persist_source(facts):
        record, child = records[facts.response_id]
        _persist(child, "source.json", record)
        child_status = {
            "schema_version": 1,
            "parent_run_id": run_id,
            "integration_status": status["integration_status"],
            "dependency_revision": status["dependency_revision"],
            "run_id": facts.request.child_run_id,
            "request_id": facts.request.request_id,
            "response_id": facts.response_id,
            "complete": True,
            "request_count": 1,
            "evidence_refs": list(facts.evidence_refs),
        }
        _persist(child, "capture_status.json", child_status)
        if (
            snapshot.json(facts.request.child_run_id, "source.json")
            != _json(json.dumps(record))
            or snapshot.json(facts.request.child_run_id, "capture_status.json")
            != child_status
        ):
            raise ValueError("source_readback_failed")
        source_manifest.append(
            {
                "run_id": facts.request.child_run_id,
                "request_id": facts.request.request_id,
                "response_id": facts.response_id,
                "evidence_refs": list(facts.evidence_refs),
                "artifact": "source.json",
            }
        )
        _persist(
            artifacts,
            "investigation_sources.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "sources": source_manifest,
            },
        )
        if AssessmentSnapshot(storage_dir).json(
            run_id, "investigation_sources.json"
        ) != {
            "schema_version": 1,
            "run_id": run_id,
            "sources": source_manifest,
        }:
            raise OSError("manifest_readback_failed")
        steps[-1]["status"] = "authenticated"
        _persist(artifacts, "investigation_steps.json", steps)

    def verify_source(facts):
        record, _ = records[facts.response_id]
        snapshot.verify()
        return snapshot.json(facts.request.child_run_id, "source.json") == _json(
            json.dumps(record)
        )

    def capture(selected, *, reauthorize):
        current_policy = authorize(resolve=True)
        current_intent = intent
        if current_intent is None:
            raise PermissionError("investigation_not_approved")
        if status["capture_launch_count"] >= 3:
            raise PermissionError("request_budget_exceeded")
        status["capture_launch_count"] += 1
        child = api(selected.child_run_id)
        attempted = False
        step = {
            "step": selected.stage,
            "run_id": selected.child_run_id,
            "request_id": selected.request_id,
            "status": "incomplete",
        }
        steps.append(step)
        _persist(artifacts, "investigation_steps.json", steps)
        count_was_exact = status["request_count_exact"]
        status["request_count_exact"] = False
        child_status = {
            "schema_version": 1,
            "parent_run_id": run_id,
            "run_id": selected.child_run_id,
            "request_id": selected.request_id,
            "complete": False,
            "request_count": 0,
            "request_count_exact": False,
        }
        _persist(child, "capture_status.json", child_status)
        _persist(artifacts, "investigation_status.json", status)

        def on_attempt(value):
            nonlocal attempted
            attempted = value is True
            status["request_count"] += int(attempted)
            status["request_count_exact"] = count_was_exact and value is not None
            child_status.update(
                request_count=int(attempted), request_count_exact=value is not None
            )
            step.update(
                request_count=int(attempted), request_count_exact=value is not None
            )
            _persist(child, "capture_status.json", child_status)
            _persist(artifacts, "investigation_steps.json", steps)
            _persist(artifacts, "investigation_status.json", status)

        begin = time.monotonic()
        raw = run_detection_provider(
            current_policy.transport,
            reauthorize=lambda: (reauthorize(), authorize(resolve=True)),
            investigation={
                "relative_url": selected.relative_url,
                "body_bytes_max": config["body_bytes_max"],
            },
            on_attempt=on_attempt,
            deadline=deadline,
        )
        if not attempted or not status["request_count_exact"]:
            raise ValueError("request_count_unverified")
        authorize()
        captured = _json(raw)
        response_id = generate_run_id("response")
        evidence_ref = generate_run_id("web-source")
        facts = capture_to_facts(
            selected,
            captured,
            policy=current_policy,
            domain=domain,
            provider_id=current_intent.provider_id,
            provider_version=current_intent.provider_version,
            response_id=response_id,
            evidence_ref=evidence_ref,
            elapsed_seconds=int(time.monotonic() - begin),
            body_bytes_max=config["body_bytes_max"],
        )
        record = {
            "schema_version": 1,
            "parent_run_id": run_id,
            "integration_status": status["integration_status"],
            "dependency_revision": status["dependency_revision"],
            "run_id": selected.child_run_id,
            "request_id": selected.request_id,
            "response_id": response_id,
            "facts": asdict(facts),
            "capture": captured,
        }
        records[response_id] = record, child
        step.update(response_id=response_id, status="captured")
        return facts, 1

    def close_egress():
        if session is None:
            return
        session.close()
        evidence = snapshot.json(run_id, "egress_lifecycle.json")
        if (
            not session.closed
            or evidence != session.evidence
            or evidence.get("assessment_run_id") != run_id
            or evidence.get("state") != "closed"
            or evidence.get("cleanup_verified") is not True
            or evidence.get("enforcement_verified") is not True
            or any(
                process is None or process.poll() is None
                for process in (session.helper, session.supervisor)
            )
        ):
            raise RuntimeError("cleanup_unverified")
        snapshot.verify()

    try:
        if config.get("enabled") is True:
            validate_investigation_settings(settings)
            task = read_task(task_path, config)
            policy = InvestigationPolicy.from_config(config["approval"])
            deadline = started + policy.transport.time_budget_seconds
            authorize()
            try:
                domain, revision = _load_domain(
                    local_lab=config.get("local_lab_enabled", False),
                    policy=policy,
                )
            except ImportError:
                status["reason"] = (
                    "local_editable_dependency_unavailable"
                    if config.get("local_lab_enabled", False)
                    else "reviewed_it10_revision_unavailable"
                )
            else:
                status.update(
                    integration_status="COMPLETE"
                    if re.fullmatch(r"[0-9a-f]{40}", revision)
                    else "LABORATORY_ONLY",
                    dependency_revision=revision,
                    reason="execution_incomplete",
                    status="ERROR",
                )
                authorize()
                classify_task(settings, task["task"], logger, deadline=deadline)
                authorize()
                intent = _prepare_intent(domain, policy, run_id)
                authorize(resolve=True)
                session = ManagedEgress(
                    policy.transport,
                    artifacts=artifacts,
                    assessment_run_id=run_id,
                    seconds=max(1, math.ceil(deadline - time.monotonic())),
                )
                session.start()
                authorize(resolve=True)
                analysis, _sources, count = collect_investigation(
                    intent,
                    policy=policy,
                    domain=domain,
                    capture=capture,
                    reload_policy=authorize,
                    persist_source=persist_source,
                    verify_source=verify_source,
                )
                if analysis is None:
                    raise ValueError("investigation_analysis_unavailable")
                if (
                    count != status["request_count"]
                    or not status["request_count_exact"]
                ):
                    raise ValueError("request_count_unverified")
                close_egress()
                authorize()
                normalized = {
                    "status": analysis.status.value,
                    "framework": analysis.framework,
                    "version": analysis.version,
                    "evidence_refs": list(analysis.evidence_refs),
                    "disposition": "candidate"
                    if analysis.candidate is not None
                    else None,
                }
                explanation = explain_result(
                    settings, normalized, logger, deadline=deadline
                )
                authorize()
                status.update(
                    status=analysis.status.value.upper(),
                    reason="ok",
                    complete=analysis.status.value in {"match", "no_match"},
                    evidence_refs=list(analysis.evidence_refs),
                )
    except KeyboardInterrupt:
        status.update(status="INCONCLUSIVE", reason="cancelled", complete=False)
    except TimeoutError:
        status.update(status="TIMEOUT", reason="investigation_deadline", complete=False)
    except PermissionError:
        status.update(status="REFUSED", reason="authorization_refused", complete=False)
    except OSError, ValueError, RuntimeError, ImportError:
        status.update(status="ERROR", reason="execution_incomplete", complete=False)
    finally:
        if session is not None:
            try:
                close_egress()
            except OSError, ValueError, RuntimeError:
                status.update(
                    status="ERROR", reason="cleanup_unverified", complete=False
                )

    def publish():
        accepted = analysis if status["reason"] == "ok" else None
        result = {
            **status,
            "framework": accepted.framework if accepted is not None else None,
            "version": accepted.version if accepted is not None else None,
            "findings": [asdict(accepted.candidate)]
            if accepted is not None and accepted.candidate
            else [],
            "explanation": explanation if accepted is not None else None,
        }
        report = accepted.report() if accepted is not None else None
        _persist(artifacts, "investigation_steps.json", steps)
        _persist(artifacts, "investigation_result.json", result)
        if report is not None:
            _write_report(artifacts, "report.json", report.canonical_json)
            _write_report(artifacts, "report.md", report.markdown)
        else:
            _persist(artifacts, "report.json", result)
            _write_report(
                artifacts,
                "report.md",
                "# Web investigation\n\nStatus: "
                + status["status"]
                + "\n\nReason: "
                + status["reason"]
                + "\n",
            )
        output = AssessmentSnapshot(storage_dir)
        for name in (
            "investigation_steps.json",
            "investigation_result.json",
            "report.json",
            "report.md",
        ):
            output.read(run_id, name)
        if (
            _json(output.read(run_id, "investigation_steps.json")) != steps
            or output.json(run_id, "investigation_result.json")
            != _json(json.dumps(result))
            or output.json(run_id, "report.json")
            != (report.data if report is not None else _json(json.dumps(result)))
            or report is not None
            and output.read(run_id, "report.md") != report.markdown.encode()
        ):
            raise OSError("result_readback_failed")
        if accepted is not None:
            if output.json(run_id, "investigation_sources.json") != {
                "schema_version": 1,
                "run_id": run_id,
                "sources": source_manifest,
            }:
                raise OSError("manifest_readback_failed")
            authorize()
        _persist(artifacts, "investigation_status.pending.json", status)
        output.verify()
        if accepted is not None:
            authorize()
        os.replace(
            artifacts.artifact_dir() / "investigation_status.pending.json",
            artifacts.artifact_dir() / "investigation_status.json",
        )
        descriptor = os.open(artifacts.artifact_dir(), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if output.json(run_id, "investigation_status.json") != status:
            raise OSError("terminal_readback_failed")
        output.verify()
        if accepted is not None:
            authorize()

    try:
        publish()
    except OSError, ValueError, RuntimeError, KeyboardInterrupt:
        status.update(
            status="ERROR",
            reason="artifact_incomplete",
            complete=False,
            evidence_refs=[],
        )
        _persist(artifacts, "investigation_status.json", status)
        publish()
    logger.info(
        "BeeScan investigation: run_id=%s status=%s reason=%s requests=%s",
        run_id,
        status["status"],
        status["reason"],
        status["request_count"],
    )
    return status
