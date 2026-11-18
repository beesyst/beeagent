import hmac
import re
import time
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

from beescan.capabilities.catalog import ACCESS_CONTROL_GET, EffortMode
from beescan.domain.access_control import (
    AccessResult,
    read_only_resource,
    validate_resource_locator,
)
from beescan.domain.access_discovery import (
    AccessHypothesis,
    DiscoveredObject,
    discovery_result,
    select_hypothesis,
)

from beeagent_module.integrations.beescan.access_control import (
    _plain,
    execute_access,
    restore,
    select_profile,
)
from beeagent_module.integrations.beescan.case_state import digest, save_case
from beeagent_module.integrations.beescan.dast import _api
from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.integrations.beescan.investigation import _json

EFFORT = {"quick": (2, 2), "standard": (4, 12), "deep": (12, 20)}
IDENTIFIERS = ("id", "account_id", "userId", "sub")
OWNER_FIELDS = ("owner_id", "ownerId", "user_id", "userId")
META_FIELDS = frozenset(
    (
        *IDENTIFIERS,
        *OWNER_FIELDS,
        "owner",
        "role",
        "href",
        "url",
        "links",
        "_links",
        "visibility",
        "type",
        "method",
        "readOnly",
    )
)


def safe_link(origin, current, value):
    if (
        type(value) is not str
        or len(value) > 2048
        or not value.isascii()
        or any(ord(c) < 33 or ord(c) > 126 for c in value)
        or "\\" in value
    ):
        return None
    if any(part in {".", ".."} for part in urlsplit(value).path.split("/")):
        return None
    parsed = urlsplit(urljoin(origin + current, value))
    if parsed.scheme + "://" + parsed.netloc != origin or parsed.fragment:
        return None
    relative = parsed.path + ("?" + parsed.query if parsed.query else "")
    try:
        validate_resource_locator(relative)
    except ValueError:
        return None
    if not read_only_resource(relative):
        return None
    return relative


def diagnostic_relative_url(value):
    parsed = urlsplit(value)
    return parsed.path or "/"


class GetLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.form: tuple[str, list[tuple[str, str]]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        values = dict(attrs)
        if len(self.links) >= 32:
            return
        href = values.get("href")
        if tag == "a" and isinstance(href, str) and href:
            self.links.append(href)
        rel = values.get("rel", "")
        if (
            tag == "link"
            and isinstance(href, str)
            and href
            and isinstance(rel, str)
            and not set(rel.lower().split()).intersection(
                {"stylesheet", "icon", "manifest", "preload"}
            )
        ):
            self.links.append(href)
        if tag == "form":
            method = values.get("method", "get")
            action = values.get("action")
            self.form = (
                (action, [])
                if (
                    isinstance(method, str)
                    and method.lower() == "get"
                    and isinstance(action, str)
                    and action
                )
                else None
            )
        name, value = values.get("name"), values.get("value")
        if (
            tag == "input"
            and self.form is not None
            and isinstance(name, str)
            and name
            and isinstance(value, str)
            and len(self.form[1]) < 8
        ):
            self.form[1].append((name, value))

    def handle_endtag(self, tag):
        if tag == "form" and self.form is not None:
            action, fields = self.form
            self.links.append(
                action + ("&" if "?" in action else "?") + urlencode(fields)
                if fields
                else action
            )
            self.form = None


def observe(body, media, origin, path, principal):
    links, objects, identity = [], [], None
    if media in {"text/html", "application/xhtml+xml"}:
        parser = GetLinks()
        parser.feed(body)
        links = parser.links
    elif media == "application/json":
        data = _json(body)
        if type(data) is dict and type(data.get("paths")) is dict:
            for url, methods in list(data["paths"].items())[:32]:
                if (
                    type(methods) is dict
                    and type(methods.get("get")) is dict
                    and methods["get"].get("x-readOnly") is True
                ):
                    links.append(url)
        visited = 0

        def walk(node, prefix="", depth=0):
            nonlocal identity, visited
            visited += 1
            if visited > 256 or depth > 4 and type(node) in {list, dict}:
                raise ValueError("discovery_structure_limit")
            if type(node) is list:
                if len(node) > 32:
                    raise ValueError("discovery_collection_limit")
                for item in node[:32]:
                    walk(item, prefix, depth + 1)
                return
            if (
                type(node) is not dict
                or node.get("method", "GET") != "GET"
                or node.get("readOnly") is False
            ):
                return
            for key in IDENTIFIERS:
                if (
                    type(node.get(key)) in {str, int}
                    and str(node[key]) == principal["account_id"]
                    and node.get("role") == principal["role"]
                    and prefix
                    in {
                        "",
                        "identity.",
                        "user.",
                        "current_user.",
                        "data.identity.",
                        "data.user.",
                        "data.current_user.",
                    }
                    and not any(name in node for name in (*OWNER_FIELDS, "owner"))
                ):
                    candidate = (path, prefix + key, prefix + "role", node[key])
                    if identity is not None and identity != candidate:
                        raise ValueError("ambiguous_identity_observation")
                    identity = candidate
            href = node.get("href", node.get("url"))
            if type(href) is str:
                links.append(href)
            object_key = next(
                (
                    key
                    for key in ("id", "object_id", "uuid")
                    if type(node.get(key)) in {str, int}
                ),
                None,
            )
            owner = next(
                (
                    node[key]
                    for key in OWNER_FIELDS
                    if type(node.get(key)) in {str, int}
                ),
                None,
            )
            if owner is None and type(node.get("owner")) is dict:
                owner = node["owner"].get("id")
            fields = []

            def scalars(value, parent="", level=0):
                if level > 2 or type(value) is not dict:
                    return
                for name, content in sorted(value.items()):
                    if (
                        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name)
                        or name in META_FIELDS
                        or name == object_key
                    ):
                        continue
                    if re.search(
                        r"password|token|credential|session|auth|csrf|secret_key",
                        name,
                        re.IGNORECASE,
                    ):
                        continue
                    if type(content) in {str, int, float} and (
                        type(content) is not str or 0 < len(content) <= 256
                    ):
                        fields.append(parent + name)
                    elif type(content) is dict:
                        scalars(content, parent + name + ".", level + 1)

            scalars(node)
            if object_key and owner is not None:
                objects.append(
                    {
                        "url": href if type(href) is str else path,
                        "object_key": object_key,
                        "id": node[object_key],
                        "owner": str(owner),
                        "fields": tuple(fields[:8]),
                        "visibility": node.get("visibility", "unspecified"),
                        "type": str(node.get("type", "object"))[:64],
                    }
                )
            for key, content in node.items():
                if type(key) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                    walk(
                        content,
                        prefix + key + ("[]." if type(content) is list else "."),
                        depth + 1,
                    )

        walk(data)
    return (
        identity,
        objects[:32],
        [
            link
            for raw in links[:64]
            if (link := safe_link(origin, path, raw)) is not None
        ],
    )


def execute_discovery(
    service,
    invocation,
    *,
    execution_case_id=None,
    request_limit=None,
    deadline_limit=None,
    continue_after_match=False,
    step_budget=None,
    source_path="/",
    excluded_paths=(),
    excluded_owner_paths=(),
):
    from beeagent_module.integrations.beescan.detection_runner import (
        run_detection_provider,
    )
    from beeagent_module.integrations.beescan.egress import ManagedEgress
    from beeagent_module.integrations.beescan.http_runner import verify_resolution
    from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot
    from beeagent_module.integrations.beescan.web import _key

    profile, credentials = select_profile(
        invocation.settings,
        invocation.profile_id,
        invocation.actor,
        invocation.task.target,
    )
    from beeagent_module.integrations.beescan.investigation import _load_domain

    _load_domain(
        local_lab=profile["local_lab"],
        policy=invocation.policy,
        local_context=invocation,
    )
    config = invocation.settings["beescan"]["investigation"]
    validate_resource_locator(source_path)
    if not read_only_resource(source_path):
        raise PermissionError("discovery_source_refused")
    for paths in (excluded_paths, excluded_owner_paths):
        if type(paths) is not tuple or len(paths) > 256:
            raise ValueError("invalid_discovery_history")
        for path in paths:
            validate_resource_locator(path)
    discovery_limit, total_limit = EFFORT[invocation.mode]
    step_limit = min(
        config["adaptive"]["max_steps"],
        {"quick": 2, "standard": 8, "deep": 16}[invocation.mode],
    )
    if step_budget is not None:
        if type(step_budget) is not int or step_budget < 1:
            raise PermissionError("discovery_step_budget_exhausted")
        step_limit = min(step_limit, step_budget)
    total_limit = min(
        total_limit, profile["request_budget"], config["adaptive"]["max_requests"]
    )
    if request_limit is not None:
        if type(request_limit) is not int or request_limit < 1:
            raise PermissionError("discovery_budget_exhausted")
        total_limit = min(total_limit, request_limit)
    discovery_limit = min(
        discovery_limit, profile["discovery_budget"], total_limit, step_limit
    )
    case_id, transport = (
        execution_case_id or invocation.case_id,
        invocation.policy.transport,
    )
    api, key = _api(service.storage, case_id, service.logger), _key(invocation.settings)
    if execution_case_id is not None:
        invocation.bind(api, case_id)
    started = time.monotonic()
    seconds = min(profile["seconds"], config["timeout_seconds"])
    deadline = started + seconds
    if deadline_limit is not None:
        deadline = min(deadline, deadline_limit)
        seconds = max(1, int(deadline - started))
    bindings = [hmac.digest(key, c.encode(), "sha256").hex() for c in credentials]
    sessions = [
        "session-" + hmac.digest(key, (case_id + b).encode(), "sha256").hex()[:48]
        for b in bindings
    ]
    queue, visited, observations, objects, details, identities, steps = (
        [(0, "/"), (1, "/")],
        set(),
        [],
        [],
        {},
        {},
        [],
    )
    if source_path != "/":
        queue.extend(((0, source_path), (1, source_path)))
    count, exact, failure = 0, True, None
    failure_stage = None
    results, comparisons, decisions = [], [], []
    session = ManagedEgress(
        transport, artifacts=api, assessment_run_id=case_id, seconds=seconds
    )

    def authorize():
        invocation.verify()
        current, values = select_profile(
            service.reload_settings(),
            invocation.profile_id,
            invocation.actor,
            invocation.task.target,
        )
        if current != profile or values != credentials:
            raise PermissionError("discovery_authority_changed")
        if time.monotonic() >= deadline:
            raise TimeoutError("discovery_deadline")
        verify_resolution(transport)

    def progress():
        _persist(
            api,
            "investigation_status.json",
            {
                "run_id": case_id,
                "case_id": case_id,
                "status": "RUNNING",
                "reason": "authenticated_discovery",
                "complete": False,
                "request_count": count,
                "request_count_exact": exact,
            },
        )
        _persist(api, "investigation_steps.json", steps)

    try:
        failure_stage = "authorize"
        authorize()
        failure_stage = "egress_start"
        session.start()
        while queue and count < discovery_limit:
            preferred = next(
                (n for n, entry in enumerate(queue) if entry[0] == count % 2), 0
            )
            index, path = queue.pop(preferred)
            if (index, path) in visited:
                continue
            visited.add((index, path))
            authorize()
            attempted = False
            exact = False
            progress()

            def on_attempt(value):
                nonlocal count, exact, attempted
                attempted = value
                count += int(value is True)
                exact = value is not None
                progress()

            failure_stage = "capture"
            raw = run_detection_provider(
                transport,
                investigation={
                    "relative_url": path,
                    "body_bytes_max": config["body_bytes_max"],
                    "general": True,
                },
                authentication=credentials[index],
                reauthorize=authorize,
                deadline=deadline,
                on_attempt=on_attempt,
            )
            failure_stage = "capture_authorize"
            authorize()
            capture = _json(raw)
            if (
                attempted is not True
                or capture.get("complete") is not True
                or capture.get("origin") != profile["origin"]
                or capture.get("connected_ip") != transport.connected_ip
                or capture.get("port") != transport.port
                or capture.get("relative_url") != path
                or capture.get("method") != "GET"
                or capture.get("request_count") != 1
            ):
                raise ValueError("invalid_discovery_capture")
            if capture.get("status_code") in {401, 403}:
                raise PermissionError("discovery_identity_refused")
            identity, records, links = (
                observe(
                    capture.get("body", ""),
                    capture.get("content_type"),
                    profile["origin"],
                    path,
                    profile["principals"][index],
                )
                if capture.get("status_code") == 200
                else (None, [], [])
            )
            if identity:
                if index in identities and identities[index][3] != identity[3]:
                    raise ValueError("contradictory_identity_source")
                identities.setdefault(index, identity)
            ref = "acd-" + digest([case_id, index, count])[:48]
            response_id = "acr-" + digest([case_id, ref])[:48]
            observations.append(
                {
                    "source_ref": ref,
                    "case_id": case_id,
                    "principal_id": profile["principals"][index]["principal_id"],
                    "session_id": sessions[index],
                    "response_id": response_id,
                    "response_sha256": hmac.digest(key, raw, "sha256").hex(),
                    "request_sha256": hmac.digest(key, path.encode(), "sha256").hex(),
                    "captured_at": datetime.now(UTC).isoformat(),
                    "complete": "body" in capture and "skip_reason" not in capture,
                    "relative_url": diagnostic_relative_url(path),
                    "status_code": capture.get("status_code"),
                    "content_type": str(capture.get("content_type") or "")[:128],
                    "skip_reason": str(capture.get("skip_reason") or "")[:80],
                }
            )
            blocked_links = set()
            for record in records:
                if profile["expectation"] == "administrative_restricted" and (
                    record["type"] != profile["restricted_resource_type"]
                    or record["visibility"] != "private"
                ):
                    continue
                url = safe_link(profile["origin"], path, record["url"])
                if url is None:
                    continue
                principal = profile["principals"][index]
                if record["owner"] != principal["account_id"]:
                    blocked_links.add(url)
                owner_id = (
                    principal["principal_id"]
                    if record["owner"] == principal["account_id"]
                    else None
                )
                object_ref = (
                    "obj-"
                    + hmac.digest(key, str(record["id"]).encode(), "sha256").hex()[:48]
                )
                shape = (
                    "shape-"
                    + digest([record["type"], record["object_key"], record["fields"]])[
                        :48
                    ]
                )
                fact = DiscoveredObject(
                    case_id,
                    principal["principal_id"],
                    sessions[index],
                    ref,
                    response_id,
                    object_ref,
                    url.split("?", 1)[0],
                    shape,
                    owner_id,
                    record["visibility"]
                    if record["visibility"] in {"public", "private", "unspecified"}
                    else "unknown",
                    False,
                    observations[-1]["complete"] and bool(record["fields"]),
                    tuple(name for name, _ in validate_resource_locator(url)[1]),
                )
                entry = (fact.principal_id, fact.relative_url, fact.object_ref)
                if entry not in details:
                    objects.append(fact)
                    details[entry] = {**record, "url": url, "index": index}
            for link in links:
                if (
                    link not in blocked_links
                    and link.split("?", 1)[0] not in excluded_paths
                    and link.split("?", 1)[0] not in excluded_owner_paths
                    and (index, link) not in visited
                    and (index, link) not in queue
                    and len(queue) < 64
                ):
                    queue.append((index, link))
            steps.append(
                {
                    "step": "identity" if identity else "discovery",
                    "status": "authenticated" if identity else "captured",
                    "request_count": 1,
                }
            )
            progress()
        objects = [
            replace(
                item,
                identity_verified=any(
                    p["principal_id"] == item.principal_id and i in identities
                    for i, p in enumerate(profile["principals"])
                ),
            )
            for item in objects
        ]
    except PermissionError:
        failure = "REFUSED"
    except TimeoutError:
        failure = "TIMEOUT"
    except KeyboardInterrupt:
        failure = "REFUSED"
    except OSError, ValueError, TypeError:
        failure = "ERROR"
    finally:
        try:
            session.close()
        except OSError, ValueError, RuntimeError:
            failure = "ERROR"
    snapshot = AssessmentSnapshot(service.storage)
    cleanup = snapshot.json(case_id, "egress_lifecycle.json")
    _persist(api, "discovery_cleanup.json", cleanup)
    if not (
        cleanup.get("state") == "closed"
        and cleanup.get("cleanup_verified") is True
        and cleanup.get("enforcement_verified") is True
        and cleanup.get("assessment_run_id") == case_id
    ):
        failure = "ERROR"
    discovery_count = count
    _persist(
        api,
        "discovery_evidence.json",
        {"observations": observations, "objects": [asdict(o) for o in objects]},
    )
    reason = (
        "authenticated_identity_missing"
        if len(identities) != 2
        else "eligible_owned_resource_missing"
    )
    attempted_hypotheses = []
    while (
        not failure
        and len(identities) == 2
        and count + 8 <= total_limit
        and len(observations) + len(comparisons) < step_limit
    ):
        hypothesis, reason = select_hypothesis(
            tuple(
                item
                for item in objects
                if item.principal_id != profile["principals"][0]["principal_id"]
                or item.relative_url not in excluded_owner_paths
            ),
            case_id=case_id,
            expectation=profile["expectation"],
            expectation_ref=profile.get(
                "restriction_reference", profile["authorization_reference"]
            ),
            attempted=tuple(attempted_hypotheses),
            effort_mode=EffortMode(invocation.mode),
            available_profiles=(ACCESS_CONTROL_GET,),
            principal_ids=tuple(p["principal_id"] for p in profile["principals"]),
        )
        if hypothesis is None:
            break
        attempted_hypotheses.append(hypothesis.identity)
        a, b = (
            details[(o.principal_id, o.relative_url, o.object_ref)]
            for o in (hypothesis.owner, hypothesis.baseline)
        )
        derived = deepcopy(profile)
        derived.pop("discovery")
        derived["principals"] = []
        for detail in (a, b):
            index = detail["index"]
            identity_path, identity_field, role_field, observed_account = identities[
                index
            ]
            derived["principals"].append(
                {
                    **profile["principals"][index],
                    "account_id": observed_account,
                    "identity_path": identity_path,
                    "identity_field": identity_field,
                    "role_field": role_field,
                    "baseline_path": detail["url"],
                    "object_field": detail["object_key"],
                    "object_id": detail["id"],
                }
            )
        derived["relationship"] = (
            "administrative"
            if hypothesis.expectation == "administrative_restricted"
            else "horizontal"
            if derived["principals"][0]["role"] == derived["principals"][1]["role"]
            else "vertical"
        )
        derived["resource"] = {
            "resource_id": hypothesis.identity,
            "path": a["url"],
            "owner_id": hypothesis.owner.principal_id,
            "object_field": a["object_key"],
            "object_id": a["id"],
            "private_fields": list(a["fields"]),
            "expected_access": [True, hypothesis.public],
            "public": hypothesis.public,
        }
        name = "access-comparison-" + str(len(comparisons)) + ".json"
        steps.append(
            {"step": "hypothesis", "status": "authenticated", "request_count": 0}
        )
        outcome = execute_access(
            service,
            invocation,
            discovered_profile=derived,
            record_name=name,
            finalize=False,
            deadline_limit=deadline,
            progress_base=count,
            progress_steps=steps,
            execution_case_id=case_id,
        )
        cleanup = AssessmentSnapshot(service.storage).json(
            case_id, "egress_lifecycle.json"
        )
        _persist(api, name.replace("comparison", "cleanup"), cleanup)
        count += outcome["execution"].request_count
        exact = exact and outcome["execution"].request_count_exact
        results.append(outcome["result"])
        comparisons.append(name)
        decisions.append(asdict(hypothesis))
        steps.extend(outcome["steps"])
        if results[-1].status in {"REFUSED", "ERROR", "TIMEOUT"} or (
            not continue_after_match and results[-1].status == "CANDIDATE"
        ):
            break
    unresolved = any(o.owner_id is None or o.visibility == "unknown" for o in objects)
    remaining, _ = select_hypothesis(
        tuple(
            item
            for item in objects
            if item.principal_id != profile["principals"][0]["principal_id"]
            or item.relative_url not in excluded_owner_paths
        ),
        case_id=case_id,
        expectation=profile["expectation"],
        expectation_ref=profile.get(
            "restriction_reference", profile["authorization_reference"]
        ),
        attempted=tuple(attempted_hypotheses),
        effort_mode=EffortMode(invocation.mode),
        available_profiles=(ACCESS_CONTROL_GET,),
        principal_ids=tuple(p["principal_id"] for p in profile["principals"]),
    )
    result = (
        AccessResult(
            failure,
            "authenticated_discovery_" + (failure_stage or "unknown") + "_failed",
        )
        if failure
        else discovery_result(
            tuple(results),
            exhausted=not queue and remaining is None,
            unresolved=unresolved,
        )
    )
    if not results and not failure:
        result = AccessResult(
            "PARTIAL",
            "authorization_expectation_required"
            if profile["expectation"] == "unknown"
            else "verification_budget_insufficient"
            if len(identities) == 2 and remaining
            else reason,
        )
    metrics = {
        "request_count": count,
        "request_count_exact": exact,
        "elapsed_seconds": time.monotonic() - started,
        "ai_calls": 0,
        "tokens": None,
        "cost": None,
        "usage_status": "unavailable",
    }
    state = {
        "schema_version": 6,
        "case_id": case_id,
        "segments": [case_id],
        "pending": False,
        "terminal": True,
        "status": result.status,
        "reason": result.reason,
        "profile_id": profile["profile_id"],
        "profile_sha256": digest(profile),
        "credential_bindings": bindings,
        "metrics": metrics,
        "comparisons": comparisons,
        "hypotheses": decisions,
        "expectation": profile["expectation"],
        "authorization_reference": profile.get(
            "restriction_reference", profile["authorization_reference"]
        ),
        "frontier_exhausted": not queue and remaining is None,
        "unresolved": unresolved,
        "failure": failure,
        "failure_stage": failure_stage,
        "discovery_request_count": discovery_count,
        "discovery_source": source_path,
        "excluded_owner_paths": list(excluded_owner_paths),
        "budgets": {
            "max_requests": total_limit,
            "discovery_requests": discovery_limit,
            "max_seconds": seconds,
            "max_steps": step_limit,
        },
    }
    _persist(api, "investigation_result.json", _plain(result))
    _persist(api, "investigation_steps.json", steps)
    _persist(
        api,
        "investigation_status.json",
        {
            "run_id": case_id,
            "case_id": case_id,
            "status": result.status,
            "reason": result.reason,
            "complete": result.status in {"CANDIDATE", "NO_MATCH"},
            "request_count": count,
            "request_count_exact": exact,
            "metrics": metrics,
            "evidence_refs": [o["source_ref"] for o in observations],
        },
    )
    _persist(api, "report.json", _plain(result))
    from beeagent_module.integrations.beescan.assessment import _write_report

    _write_report(
        api,
        "report.md",
        "# Access investigation\n\n" + result.status + "\n\n" + result.reason + "\n",
    )
    save_case(api, state)
    credentials.clear()
    details.clear()
    return {"case_id": case_id, "status": result.status}


def load_discovery_case(state, snapshot, case_id):
    if (
        state.get("case_id") != case_id
        or state.get("segments") != [case_id]
        or state.get("pending") is not False
        or state.get("terminal") is not True
        or type(state.get("comparisons")) is not list
        or len(state["comparisons"]) > 8
        or len(state["hypotheses"]) != len(state["comparisons"])
    ):
        raise ValueError("invalid_discovery_checkpoint")
    data = snapshot.json(case_id, "discovery_evidence.json")

    def object_record(raw):
        return DiscoveredObject(
            **{**raw, "parameter_names": tuple(raw["parameter_names"])}
        )

    objects = tuple(object_record(o) for o in data["objects"])
    if len(objects) > 64 or any(o.case_id != case_id for o in objects):
        raise ValueError("foreign_discovery_object")
    sources = {o["source_ref"]: o for o in data["observations"]}
    if len(sources) != len(data["observations"]) or len(sources) > 16:
        raise ValueError("invalid_discovery_sources")
    for obj in objects:
        source = sources[obj.source_ref]
        if (
            source["case_id"],
            source["principal_id"],
            source["session_id"],
            source["response_id"],
        ) != (case_id, obj.principal_id, obj.session_id, obj.response_id):
            raise ValueError("discovery_source_substitution")
    discovery_count = state["discovery_request_count"]
    budgets = state["budgets"]
    if (
        type(discovery_count) is not int
        or not len(sources) <= discovery_count <= len(sources) + 1
        or not discovery_count
        <= budgets["discovery_requests"]
        <= budgets["max_requests"]
        <= 64
    ):
        raise ValueError("invalid_discovery_accounting")
    outcomes, count = [], discovery_count
    cleanup = snapshot.json(case_id, "discovery_cleanup.json")
    if (
        cleanup.get("cleanup_verified") is not True
        or cleanup.get("enforcement_verified") is not True
    ):
        if state["status"] in {"CANDIDATE", "NO_MATCH"}:
            raise ValueError("discovery_cleanup_unverified")
    for index, name in enumerate(state["comparisons"]):
        if name != "access-comparison-" + str(index) + ".json":
            raise ValueError("invalid_comparison_reference")
        intent, execution = restore(snapshot.json(case_id, name))
        hypothesis = AccessHypothesis(
            **{
                **state["hypotheses"][index],
                "owner": object_record(state["hypotheses"][index]["owner"]),
                "baseline": object_record(state["hypotheses"][index]["baseline"]),
            }
        )
        if (
            hypothesis.owner not in objects
            or hypothesis.baseline not in objects
            or intent.parent_run_id != case_id
            or intent.resource_id != hypothesis.identity
            or intent.endpoint_path != hypothesis.owner.relative_url
            or intent.owner_id != hypothesis.owner.principal_id
            or intent.public != hypothesis.public
            or hypothesis.expectation != state["expectation"]
            or hypothesis.expectation_ref != state["authorization_reference"]
        ):
            raise ValueError("discovery_hypothesis_substitution")
        for evidence in execution.evidence:
            stored = snapshot.json(case_id, evidence.evidence_ref + ".json")
            expected = _plain(evidence)
            expected.pop("artifact_sha256")
            if stored != expected or digest(stored) != evidence.artifact_sha256:
                raise ValueError("access_control_evidence_changed")
        lifecycle = snapshot.json(case_id, name.replace("comparison", "cleanup"))
        if execution.cleanup_verified != (
            lifecycle.get("cleanup_verified") is True
            and lifecycle.get("enforcement_verified") is True
            and lifecycle.get("state") == "closed"
        ):
            raise ValueError("comparison_cleanup_changed")
        from beescan.domain.access_control import evaluate_access

        outcomes.append(evaluate_access(intent, execution))
        count += execution.request_count
    result = snapshot.json(case_id, "investigation_result.json")
    expected = discovery_result(
        tuple(outcomes),
        exhausted=state["frontier_exhausted"],
        unresolved=state["unresolved"],
    )
    if outcomes and not state["failure"] and result != _plain(expected):
        raise ValueError("discovery_result_changed")
    status = snapshot.json(case_id, "investigation_status.json")
    if (
        result["status"] != state["status"]
        or result["reason"] != state["reason"]
        or status["status"] != state["status"]
        or status["request_count"] != state["metrics"]["request_count"]
        or status["request_count"] != count
        or count > budgets["max_requests"]
    ):
        raise ValueError("discovery_accounting_changed")
    snapshot.verify()
    return state, snapshot
