import hmac
import json
import os
import re
import time
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime

from beeagent_module.integrations.beescan.case_state import digest, save_case
from beeagent_module.integrations.beescan.detection import _persist
from beeagent_module.integrations.beescan.investigation import _json


def _selector(value):
    if (
        type(value) is not str
        or re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,3}", value
        )
        is None
        or len(value) > 128
    ):
        raise ValueError("invalid_proof_selector")


def _field(body, selector):
    value = body
    for part in selector.split("."):
        if type(value) is not dict:
            return None
        value = value.get(part)
    if (
        type(value) not in {str, int, float}
        or type(value) is str
        and not 1 <= len(value) <= 256
    ):
        return None
    return value


def profiles(settings):
    config = settings.get("beescan", {}).get("access_control", {"profiles": []})
    if type(config) is not dict or set(config) != {"profiles"}:
        raise ValueError("invalid_access_control_settings")
    records = config["profiles"]
    if type(records) is not list or len(records) > 16:
        raise ValueError("invalid_access_control_profiles")
    if not records:
        return {}
    from beescan.domain.access_control import (
        read_only_resource,
        validate_resource_locator,
    )
    from beescan.domain.locators import canonical_locator
    from beescan.domain.models import TargetKind, validate_identifier, validate_text

    result = {}
    for profile in records:
        if type(profile) is not dict:
            raise ValueError("invalid_access_control_profile")
        autonomous = profile.get("discovery") is True
        expected = {
            "profile_id",
            "origin",
            "operator_ids",
            "valid_from",
            "expires_at",
            "authorization_reference",
            "principals",
            "resource",
            "relationship",
            "request_budget",
            "seconds",
            "read_only",
            "local_lab",
        }
        if autonomous:
            expected = expected - {"resource", "relationship"} | {
                "discovery",
                "expectation",
                "discovery_budget",
            }
        administrative = (
            autonomous and profile.get("expectation") == "administrative_restricted"
        )
        standalone_administrative = administrative and "principals" not in profile
        if standalone_administrative:
            expected = {
                "profile_id",
                "origin",
                "operator_ids",
                "valid_from",
                "expires_at",
                "authorization_reference",
                "discovery",
                "expectation",
                "discovery_budget",
                "request_budget",
                "seconds",
                "read_only",
                "local_lab",
                "restriction_reference",
                "restricted_resource_type",
                "resource_path",
                "negative_path",
            }
        if administrative:
            expected |= {"restriction_reference", "restricted_resource_type"}
        if set(profile) != expected:
            raise ValueError("invalid_access_control_profile")
        validate_identifier(profile["profile_id"])
        if profile["profile_id"] in result:
            raise ValueError("duplicate_access_control_profile")
        if canonical_locator(TargetKind.URL, profile["origin"]) != profile["origin"]:
            raise ValueError("invalid_access_control_origin")
        validate_identifier(profile["authorization_reference"])
        if (
            type(profile["operator_ids"]) is not list
            or not 1 <= len(profile["operator_ids"]) <= 16
            or len(set(profile["operator_ids"])) != len(profile["operator_ids"])
            or profile["read_only"] is not True
            or type(profile["local_lab"]) is not bool
            or not profile["local_lab"]
            and not profile["origin"].startswith("https://")
            or not autonomous
            and profile["relationship"] not in {"horizontal", "vertical"}
            or type(profile["request_budget"]) is not int
            or not 1 <= profile["request_budget"] <= 64
            or not autonomous
            and profile["request_budget"] != 8
            or type(profile["seconds"]) is not int
            or not 1 <= profile["seconds"] <= 60
        ):
            raise ValueError("invalid_access_control_authority")
        if autonomous and (
            profile["expectation"]
            not in {
                "owned_private",
                "role_restricted",
                "administrative_restricted",
                "public",
                "unknown",
            }
            or type(profile["discovery_budget"]) is not int
            or not 2 <= profile["discovery_budget"] <= 16
            or profile["discovery_budget"] > profile["request_budget"]
        ):
            raise ValueError("invalid_discovery_authority")
        for actor in profile["operator_ids"]:
            validate_identifier(actor)
        start, end = (
            datetime.fromisoformat(profile[k]) for k in ("valid_from", "expires_at")
        )
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("invalid_access_control_validity")
        if standalone_administrative:
            validate_identifier(profile["restriction_reference"])
            validate_text(profile["restricted_resource_type"], 64)
            for key in ("resource_path", "negative_path"):
                validate_resource_locator(profile[key])
                if "?" in profile[key] or not read_only_resource(profile[key]):
                    raise ValueError("invalid_administrative_resource")
            if (
                profile["restriction_reference"] == profile["authorization_reference"]
                or profile["resource_path"] == profile["negative_path"]
                or profile["request_budget"] < 2
            ):
                raise ValueError("independent_administrative_policy_required")
            result[profile["profile_id"]] = deepcopy(profile)
            continue
        principals = profile["principals"]
        if type(principals) is not list or len(principals) != 2:
            raise ValueError("exactly_two_principals_required")
        for principal in principals:
            fields = {
                "principal_id",
                "role",
                "credential_env",
                "account_id",
                "identity_path",
                "identity_field",
                "role_field",
                "baseline_path",
                "object_field",
                "object_id",
            }
            if autonomous:
                fields = {"principal_id", "role", "credential_env", "account_id"}
            if type(principal) is not dict or set(principal) != fields:
                raise ValueError("invalid_test_principal")
            for key in ("principal_id", "role"):
                validate_identifier(principal[key])
            for key in ("account_id",) if autonomous else ("account_id", "object_id"):
                validate_text(principal[key], 256)
            if (
                re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", principal["credential_env"])
                is None
            ):
                raise ValueError("invalid_credential_reference")
            for key in () if autonomous else ("identity_path", "baseline_path"):
                validate_resource_locator(principal[key])
            for key in (
                () if autonomous else ("identity_field", "role_field", "object_field")
            ):
                _selector(principal[key])
        for key in (
            ("principal_id", "credential_env", "account_id")
            if autonomous
            else ("principal_id", "credential_env", "account_id", "object_id")
        ):
            if principals[0][key] == principals[1][key]:
                raise ValueError("independent_principals_required")
        if administrative:
            validate_identifier(profile["restriction_reference"])
            validate_text(profile["restricted_resource_type"], 64)
            if (
                profile["restriction_reference"] == profile["authorization_reference"]
                or principals[0]["role"] == principals[1]["role"]
            ):
                raise ValueError("independent_administrative_policy_required")
        if autonomous:
            result[profile["profile_id"]] = deepcopy(profile)
            continue
        if (principals[0]["role"] == principals[1]["role"]) != (
            profile["relationship"] == "horizontal"
        ):
            raise ValueError("invalid_role_relationship")
        resource = profile["resource"]
        if type(resource) is not dict or set(resource) != {
            "resource_id",
            "path",
            "owner_id",
            "object_field",
            "object_id",
            "private_fields",
            "expected_access",
            "public",
        }:
            raise ValueError("invalid_object_authorization")
        validate_identifier(resource["resource_id"])
        if resource["owner_id"] != principals[0]["principal_id"]:
            raise ValueError("unknown_object_owner")
        validate_resource_locator(resource["path"])
        _selector(resource["object_field"])
        validate_text(resource["object_id"], 256)
        if (
            resource["path"] != principals[0]["baseline_path"]
            or resource["object_id"] != principals[0]["object_id"]
            or resource["object_field"] != principals[0]["object_field"]
            or type(resource["private_fields"]) is not list
            or not 1 <= len(resource["private_fields"]) <= 8
            or len(set(resource["private_fields"])) != len(resource["private_fields"])
            or type(resource["public"]) is not bool
            or resource["expected_access"] not in ([True, False], [True, True], None)
            or resource["expected_access"] is not None
            and any(type(v) is not bool for v in resource["expected_access"])
            or resource["expected_access"] is not None
            and resource["public"] != resource["expected_access"][1]
        ):
            raise ValueError("invalid_private_object_proof")
        for selector in resource["private_fields"]:
            _selector(selector)
            if selector == resource["object_field"]:
                raise ValueError("private_proof_must_exceed_object_identifier")
        result[profile["profile_id"]] = deepcopy(profile)
    return result


def validate_access_settings(settings, *, validate_contracts=True):
    try:
        if not validate_contracts:
            config = settings.get("beescan", {}).get("access_control", {"profiles": []})
            if (
                type(config) is not dict
                or set(config) != {"profiles"}
                or type(config["profiles"]) is not list
                or len(config["profiles"]) > 16
            ):
                raise ValueError("invalid_access_control_settings")
            return
        profiles(settings)
    except ValueError, TypeError, KeyError, AttributeError:
        raise RuntimeError("Invalid beescan.access_control settings") from None


def select_profile(settings, profile_id, actor, origin):
    if type(profile_id) is not str or profile_id not in profiles(settings):
        raise PermissionError("test_profile_unavailable")
    profile = profiles(settings)[profile_id]
    now = datetime.now(UTC)
    if (
        actor["user_id"] not in profile["operator_ids"]
        or origin != profile["origin"]
        or not datetime.fromisoformat(profile["valid_from"]) <= now
        or now.timestamp() + profile["seconds"]
        > datetime.fromisoformat(profile["expires_at"]).timestamp()
    ):
        raise PermissionError("test_profile_authority_refused")
    credentials = [os.getenv(p["credential_env"], "") for p in profile["principals"]]
    if any(
        not 1 <= len(c) <= 4096 or any(ord(v) < 33 or ord(v) > 126 for v in c)
        for c in credentials
    ):
        raise PermissionError("test_credentials_unavailable")
    if hmac.compare_digest(*credentials):
        raise PermissionError("duplicate_test_sessions")
    return profile, credentials


def select_administrative_profile(settings, profile_id, actor, origin):
    profile = profiles(settings).get(profile_id)
    now = datetime.now(UTC)
    if (
        profile is None
        or "principals" in profile
        or actor["user_id"] not in profile["operator_ids"]
        or origin != profile["origin"]
        or not datetime.fromisoformat(profile["valid_from"]) <= now
        or now.timestamp() + profile["seconds"]
        > datetime.fromisoformat(profile["expires_at"]).timestamp()
    ):
        raise PermissionError("administrative_profile_authority_refused")
    return profile


def execute_administrative_access(
    service, invocation, source, *, execution_case_id, action_id
):
    from beescan.domain.access_control import (
        AdministrativeEvidence,
        AdministrativeExecution,
        AdministrativeIntent,
        evaluate_administrative_access,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    from beeagent_module.integrations.beescan.dast import _api
    from beeagent_module.integrations.beescan.detection_runner import (
        run_detection_provider,
    )
    from beeagent_module.integrations.beescan.egress import ManagedEgress
    from beeagent_module.integrations.beescan.http_runner import verify_resolution
    from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot
    from beeagent_module.integrations.beescan.web import _key

    profile = select_administrative_profile(
        invocation.settings,
        invocation.profile_id,
        invocation.actor,
        invocation.task.target,
    )
    transport, config = (
        invocation.policy.transport,
        invocation.settings["beescan"]["investigation"],
    )
    snapshot = AssessmentSnapshot(service.storage)
    source_record = snapshot.json(source.source_run_id, "source.json")
    if (
        source_record.get("request_id") != source.request_id
        or source_record.get("response_id") != source.response_id
        or source_record["facts"]["request"].get("target_id") != transport.target_id
        or not source.evidence_refs
    ):
        raise PermissionError("administrative_source_changed")
    api = _api(service.storage, execution_case_id, service.logger)
    invocation.bind(api, execution_case_id)
    seconds = min(profile["seconds"], config["timeout_seconds"])
    intent = AdministrativeIntent(
        invocation.case_id,
        Project(transport.project_id, "Authorized administrative assessment"),
        EngagementScope(
            transport.scope_id,
            transport.project_id,
            (transport.target_id,),
            profile["authorization_reference"],
            valid_from=datetime.fromisoformat(profile["valid_from"]),
            expires_at=datetime.fromisoformat(profile["expires_at"]),
            approved_methods=("GET",),
            max_requests=3,
            max_seconds=seconds,
        ),
        Mission(
            transport.mission_id,
            transport.project_id,
            transport.scope_id,
            ("web.access_control",),
        ),
        Target(
            transport.target_id, transport.project_id, TargetKind.URL, profile["origin"]
        ),
        source.request_id,
        source.response_id,
        source.evidence_refs[0],
        profile["resource_path"],
        profile["profile_id"],
        profile["restriction_reference"],
    )
    started, count, exact, evidence = time.monotonic(), 0, True, []
    session = ManagedEgress(
        transport, artifacts=api, assessment_run_id=execution_case_id, seconds=seconds
    )

    def authorize():
        invocation.verify()
        if (
            select_administrative_profile(
                service.reload_settings(),
                invocation.profile_id,
                invocation.actor,
                invocation.task.target,
            )
            != profile
        ):
            raise PermissionError("administrative_policy_changed")
        verify_resolution(transport)

    source_at = datetime.now(UTC)
    evidence.append(
        AdministrativeEvidence(
            intent.identity,
            "source",
            source.request_id,
            source.response_id,
            source.evidence_refs[0],
            digest(source_record["facts"]["request"]),
            digest(source_record["facts"]),
            source_at,
            True,
            False,
            True,
        )
    )
    try:
        authorize()
        session.start()
        invocation.observe_execution(
            execution_case_id,
            "verification",
            "RUNNING",
            action_id=action_id,
            profile=profile["profile_id"],
        )
        for slot, path in (
            ("anonymous", profile["resource_path"]),
            ("negative", profile["negative_path"]),
        ):
            authorize()
            attempted = None

            def on_attempt(value):
                nonlocal count, exact, attempted
                attempted = value
                count += int(value is True)
                exact = value is not None

            raw = run_detection_provider(
                transport,
                reauthorize=authorize,
                investigation={
                    "relative_url": path,
                    "body_bytes_max": config["body_bytes_max"],
                    "general": True,
                },
                on_attempt=on_attempt,
                deadline=started + seconds,
                authentication=None,
            )
            capture = _json(raw)
            if (
                attempted is not True
                or capture.get("request_count") != 1
                or capture.get("relative_url") != path
                or capture.get("method") != "GET"
                or capture.get("origin") != profile["origin"]
                or capture.get("connected_ip") != transport.connected_ip
            ):
                raise ValueError("invalid_administrative_capture")
            denied = (
                capture.get("status_code") in {401, 403, 404}
                or 300 <= capture.get("status_code", 0) < 400
            )
            equivalent = False
            now = datetime.now(UTC)
            request_id = "aaq-" + digest([intent.identity, slot, path])[:48]
            response_id = "aar-" + digest([request_id, count])[:48]
            ref = "aae-" + digest([execution_case_id, response_id])[:48]
            record = {
                "intent_id": intent.identity,
                "slot": slot,
                "request_id": request_id,
                "response_id": response_id,
                "evidence_ref": ref,
                "request_sha256": digest([request_id, path]),
                "response_sha256": hmac.digest(
                    _key(invocation.settings), raw, "sha256"
                ).hex(),
                "captured_at": now.isoformat(),
                "complete": capture.get("complete") is True
                and "skip_reason" not in capture,
                "denied": denied,
                "equivalent": equivalent,
            }
            _persist(api, ref + ".json", record)
            evidence.append(AdministrativeEvidence(**{**record, "captured_at": now}))
    finally:
        session.close()
    lifecycle = AssessmentSnapshot(service.storage).json(
        execution_case_id, "egress_lifecycle.json"
    )
    execution = AdministrativeExecution(
        tuple(evidence),
        datetime.now(UTC),
        count,
        exact,
        lifecycle.get("cleanup_verified") is True
        and lifecycle.get("enforcement_verified") is True,
        True,
    )
    result = evaluate_administrative_access(intent, execution)
    _persist(
        api,
        "administrative_comparison.json",
        {
            "intent": _plain(intent),
            "execution": _plain(execution),
            "source_sha256": digest(source_record),
            "profile_sha256": digest(profile),
        },
    )
    _persist(api, "investigation_result.json", _plain(result))
    save_case(
        api,
        {
            "schema_version": 8,
            "case_id": execution_case_id,
            "parent_case_id": invocation.case_id,
            "action_id": action_id,
            "source": _plain(source),
            "profile_id": profile["profile_id"],
            "profile_sha256": digest(profile),
            "source_sha256": digest(source_record),
            "request_count": count,
            "request_count_exact": exact,
            "status": result.status,
            "reason": result.reason,
            "evidence_refs": list(item.evidence_ref for item in evidence),
        },
    )
    invocation.observe_execution(
        execution_case_id,
        "verification",
        "COMPLETED" if result.status in {"CANDIDATE", "NO_MATCH"} else result.status,
    )
    return {
        "intent": intent,
        "execution": execution,
        "result": result,
        "request_count": count,
        "evidence_refs": tuple(item.evidence_ref for item in evidence),
    }


def _plain(value):
    return json.loads(json.dumps(asdict(value), default=lambda v: v.isoformat()))


def load_administrative_case(state, snapshot, case_id):
    required = {
        "schema_version",
        "case_id",
        "parent_case_id",
        "action_id",
        "source",
        "profile_id",
        "profile_sha256",
        "source_sha256",
        "request_count",
        "request_count_exact",
        "status",
        "reason",
        "evidence_refs",
    }
    if (
        set(state) != required
        or state["case_id"] != case_id
        or state["request_count"] != 2
        or state["request_count_exact"] is not True
    ):
        raise ValueError("invalid_administrative_case")
    comparison = snapshot.json(case_id, "administrative_comparison.json")
    result = snapshot.json(case_id, "investigation_result.json")
    if (
        comparison.get("source_sha256") != state["source_sha256"]
        or comparison.get("profile_sha256") != state["profile_sha256"]
        or comparison.get("intent", {}).get("profile_id") != state["profile_id"]
        or comparison.get("execution", {}).get("source_reused") is not True
        or comparison.get("execution", {}).get("request_count") != 2
        or result.get("status") != state["status"]
        or tuple(state["evidence_refs"])
        != tuple(
            item["evidence_ref"]
            for item in comparison.get("execution", {}).get("evidence", [])
        )
    ):
        raise ValueError("administrative_case_changed")
    snapshot.verify()
    return state, snapshot


def restore(record):
    from beescan.domain.access_control import (
        AccessEvidence,
        AccessExecution,
        AccessIntent,
        PrincipalBinding,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    if type(record) is not dict or set(record) != {"intent", "execution"}:
        raise ValueError("invalid_access_control_record")
    raw = deepcopy(record["intent"])
    scope = raw["scope"]
    for key in ("target_ids", "excluded_target_ids", "approved_methods"):
        scope[key] = tuple(scope[key])
    for key in ("valid_from", "expires_at"):
        scope[key] = datetime.fromisoformat(scope[key])
    raw["project"] = Project(**raw["project"])
    raw["scope"] = EngagementScope(**scope)
    raw["mission"]["capability_ids"] = tuple(raw["mission"]["capability_ids"])
    raw["mission"] = Mission(**raw["mission"])
    raw["target"]["kind"] = TargetKind(raw["target"]["kind"])
    raw["target"] = Target(**raw["target"])
    raw["principals"] = tuple(PrincipalBinding(**p) for p in raw["principals"])
    if raw["expected_access"] is not None:
        raw["expected_access"] = tuple(raw["expected_access"])
    intent = AccessIntent(**raw)
    raw = deepcopy(record["execution"])
    raw["ended_at"] = datetime.fromisoformat(raw["ended_at"])
    raw["evidence"] = tuple(
        AccessEvidence(**{**e, "captured_at": datetime.fromisoformat(e["captured_at"])})
        for e in raw["evidence"]
    )
    return intent, AccessExecution(**raw)


def load_access_case(state, snapshot, case_id):
    from beescan.domain.access_control import evaluate_access

    if (
        set(state)
        != {
            "schema_version",
            "case_id",
            "segments",
            "pending",
            "terminal",
            "status",
            "reason",
            "profile_id",
            "profile_sha256",
            "credential_bindings",
            "metrics",
        }
        or state["case_id"] != case_id
        or state["segments"] != [case_id]
        or state["pending"] is not False
        or state["terminal"] is not True
    ):
        raise ValueError("invalid_access_control_checkpoint")
    record = snapshot.json(case_id, "access_control.json")
    intent, execution = restore(record)
    result = evaluate_access(intent, execution)
    if (
        intent.parent_run_id != case_id
        or state["status"] != result.status
        or state["reason"] != result.reason
    ):
        raise ValueError("access_control_checkpoint_changed")
    for evidence in execution.evidence:
        stored = snapshot.json(case_id, evidence.evidence_ref + ".json")
        if digest(stored) != evidence.artifact_sha256:
            raise ValueError("access_control_evidence_changed")
        expected = _plain(evidence)
        expected.pop("artifact_sha256")
        if stored != expected:
            raise ValueError("access_control_evidence_substitution")
    lifecycle = snapshot.json(case_id, "egress_lifecycle.json")
    if execution.cleanup_verified != (
        lifecycle.get("state") == "closed"
        and lifecycle.get("cleanup_verified") is True
        and lifecycle.get("enforcement_verified") is True
        and lifecycle.get("assessment_run_id") == case_id
    ):
        raise ValueError("access_control_cleanup_changed")
    status = snapshot.json(case_id, "investigation_status.json")
    if (
        status["status"] != result.status
        or status["request_count"] != execution.request_count
        or status["request_count_exact"] != execution.request_count_exact
    ):
        raise ValueError("access_control_accounting_changed")
    expected_result = _plain(result)
    if snapshot.json(case_id, "investigation_result.json") != expected_result:
        raise ValueError("access_control_result_changed")
    snapshot.verify()
    return state, snapshot


def execute_access(
    service,
    invocation,
    *,
    discovered_profile=None,
    record_name="access_control.json",
    finalize=True,
    deadline_limit=None,
    progress_base=0,
    progress_steps=(),
    execution_case_id=None,
):
    from beescan.domain.access_control import (
        SLOTS,
        AccessAction,
        AccessEvidence,
        AccessExecution,
        AccessIntent,
        PrincipalBinding,
        evaluate_access,
    )
    from beescan.domain.models import (
        EngagementScope,
        Mission,
        Project,
        Target,
        TargetKind,
    )

    from beeagent_module.integrations.beescan.assessment import _write_report
    from beeagent_module.integrations.beescan.dast import _api
    from beeagent_module.integrations.beescan.detection_runner import (
        run_detection_provider,
    )
    from beeagent_module.integrations.beescan.egress import ManagedEgress
    from beeagent_module.integrations.beescan.http_runner import verify_resolution
    from beeagent_module.integrations.beescan.review_source import AssessmentSnapshot
    from beeagent_module.integrations.beescan.web import _key

    authority_profile, credentials = select_profile(
        invocation.settings,
        invocation.profile_id,
        invocation.actor,
        invocation.task.target,
    )
    profile = (
        discovered_profile if discovered_profile is not None else authority_profile
    )
    if authority_profile.get("discovery") and discovered_profile is None:
        raise ValueError("authenticated_discovery_required")
    from beeagent_module.integrations.beescan.investigation import _load_domain

    _load_domain(
        local_lab=profile["local_lab"],
        policy=invocation.policy,
        local_context=invocation,
    )
    case_id = execution_case_id or invocation.case_id
    transport = invocation.policy.transport
    api = _api(service.storage, case_id, service.logger)
    key = _key(invocation.settings)
    bindings = [hmac.digest(key, c.encode(), "sha256").hex() for c in credentials]
    principal_list = [
        PrincipalBinding(
            p["principal_id"],
            p["role"],
            "session-" + hmac.digest(key, (case_id + b).encode(), "sha256").hex()[:48],
        )
        for p, b in zip(profile["principals"], bindings)
    ]
    principals = (principal_list[0], principal_list[1])
    resource = profile["resource"]
    config = invocation.settings["beescan"]["investigation"]
    seconds = min(profile["seconds"], config["timeout_seconds"])
    intent = AccessIntent(
        case_id,
        Project(transport.project_id, "Authorized access-control assessment"),
        EngagementScope(
            transport.scope_id,
            transport.project_id,
            (transport.target_id,),
            profile["authorization_reference"],
            valid_from=datetime.fromisoformat(profile["valid_from"]),
            expires_at=datetime.fromisoformat(profile["expires_at"]),
            approved_methods=("GET",),
            max_requests=8,
            max_seconds=seconds,
        ),
        Mission(
            transport.mission_id,
            transport.project_id,
            transport.scope_id,
            ("web.access_control",),
        ),
        Target(
            transport.target_id, transport.project_id, TargetKind.URL, profile["origin"]
        ),
        principals,
        resource["resource_id"],
        resource["path"].split("?", 1)[0],
        resource["owner_id"],
        tuple(resource["expected_access"])
        if resource["expected_access"] is not None
        else None,
        profile["relationship"],
        resource["public"],
        profile["restriction_reference"]
        if profile["relationship"] == "administrative"
        else None,
    )
    count, exact = 0, True
    failure = None
    evidence, steps = [], []
    started = time.monotonic()
    deadline = started + seconds
    if deadline_limit is not None:
        deadline = min(deadline, deadline_limit)
    session = ManagedEgress(
        transport, artifacts=api, assessment_run_id=case_id, seconds=seconds
    )
    owner_proof = None
    baseline_distinct = False

    def authorize():
        invocation.verify()
        current, values = select_profile(
            service.reload_settings(),
            invocation.profile_id,
            invocation.actor,
            invocation.task.target,
        )
        if current != authority_profile or values != credentials:
            raise PermissionError("test_principal_authority_changed")
        if time.monotonic() >= deadline:
            raise TimeoutError("comparison_deadline")
        verify_resolution(transport)

    def persist_progress(status="RUNNING"):
        _persist(
            api,
            "investigation_status.json",
            {
                "run_id": case_id,
                "case_id": case_id,
                "status": status,
                "complete": False,
                "reason": "comparison_pending",
                "request_count": progress_base + count,
                "request_count_exact": exact,
            },
        )
        _persist(api, "investigation_steps.json", [*progress_steps, *steps])

    try:
        authorize()
        session.start()
        if finalize:
            invocation.observe_execution(
                case_id, "verification", "RUNNING", profile=invocation.profile_id
            )
        for slot in SLOTS:
            authorize()
            action = None
            if slot == "cross":
                if (
                    owner_proof is None
                    or not baseline_distinct
                    or resource["expected_access"] is None
                ):
                    break
                action = AccessAction(intent, evidence[2])
            index = 0 if slot in {"identity_a", "owner", "identity_a_end"} else 1
            principal = profile["principals"][index]
            identity = slot.startswith("identity_")
            path = (
                principal["identity_path"]
                if identity
                else principal["baseline_path"]
                if slot == "principal_baseline"
                else resource["path"]
            )
            anonymous = slot == "anonymous"
            attempted = None
            exact = False
            persist_progress()

            def on_attempt(value):
                nonlocal count, exact, attempted
                attempted = value
                count += int(value is True)
                exact = value is not None
                persist_progress()

            raw = run_detection_provider(
                transport,
                reauthorize=authorize,
                investigation={
                    "relative_url": path,
                    "body_bytes_max": config["body_bytes_max"],
                    "general": True,
                },
                on_attempt=on_attempt,
                deadline=deadline,
                authentication=None if anonymous else credentials[index],
            )
            authorize()
            capture = _json(raw)
            if (
                attempted is not True
                or capture.get("origin") != profile["origin"]
                or capture.get("connected_ip") != transport.connected_ip
                or capture.get("port") != transport.port
                or capture.get("method") != "GET"
                or capture.get("relative_url") != path
                or capture.get("request_count") != 1
                or capture.get("complete") is not True
            ):
                raise ValueError("invalid_authenticated_capture")
            body = (
                _json(capture["body"])
                if capture.get("content_type") == "application/json"
                and "body" in capture
                else {}
            )
            authenticated = not anonymous
            object_bound = private_match = False
            denied = capture["status_code"] in {403, 404} or (
                anonymous and capture["status_code"] == 401
            )
            if identity:
                authenticated = (
                    capture["status_code"] == 200
                    and _field(body, principal["identity_field"])
                    == principal["account_id"]
                    and _field(body, principal["role_field"]) == principal["role"]
                )
                if not authenticated:
                    raise PermissionError("principal_identity_unverified")
            elif slot in {"owner", "principal_baseline", "cross", "anonymous"} and (
                capture["status_code"] == 200 or slot in {"cross", "anonymous"}
            ):
                object_id = (
                    principal["object_id"]
                    if slot == "principal_baseline"
                    else resource["object_id"]
                )
                selector = (
                    principal["object_field"]
                    if slot == "principal_baseline"
                    else resource["object_field"]
                )
                object_bound = _field(body, selector) == object_id
                proof = tuple(
                    _field(body, field) for field in resource["private_fields"]
                )
                valid = object_bound and all(v is not None for v in proof)
                if slot == "owner":
                    owner_proof = proof if valid else None
                    private_match = valid
                elif slot == "principal_baseline":
                    baseline_distinct = (
                        valid and owner_proof is not None and proof != owner_proof
                    )
                    object_bound = object_bound and baseline_distinct
                else:
                    private_match = valid and baseline_distinct and owner_proof == proof
                    if private_match:
                        denied = False
            request_id = (
                action.request_id
                if action
                else "acq-" + digest([intent.identity, slot, path])[:48]
            )
            response_id = "acs-" + digest([request_id, count])[:48]
            ref = "ace-" + digest([response_id, case_id])[:48]
            captured_at = datetime.now(UTC)
            fields = dict(
                intent_id=intent.identity,
                slot=slot,
                principal_id="anonymous"
                if anonymous
                else principals[index].principal_id,
                session_id="anonymous" if anonymous else principals[index].session_id,
                resource_id=intent.resource_id,
                request_id=request_id,
                response_id=response_id,
                evidence_ref=ref,
                request_sha256=digest([request_id, path]),
                response_sha256=hmac.digest(key, raw, "sha256").hex(),
                captured_at=captured_at.isoformat(),
                authenticated=authenticated,
                object_bound=object_bound,
                private_match=private_match,
                denied=denied,
                complete=capture.get("content_type") == "application/json"
                and "body" in capture
                and "skip_reason" not in capture,
                source_request_id=action.source.request_id if action else None,
                source_response_id=action.source.response_id if action else None,
            )
            _persist(api, ref + ".json", fields)
            evidence.append(
                AccessEvidence(
                    **{
                        **fields,
                        "captured_at": captured_at,
                        "artifact_sha256": digest(fields),
                    }
                )
            )
            steps.append(
                {
                    "step": (
                        "identity"
                        if identity
                        else "comparison"
                        if slot == "cross"
                        else "baseline"
                    )
                    if discovered_profile is not None
                    else "baseline",
                    "status": "authenticated",
                    "request_count": 1,
                }
            )
            del raw, capture, body
            persist_progress()
    except KeyboardInterrupt:
        failure = "REFUSED"
    except PermissionError as error:
        from beeagent_module.integrations.beescan.web import record_failure

        record_failure(
            service.storage, service.logger, case_id, error, "access_comparison"
        )
        failure = "REFUSED"
    except TimeoutError:
        failure = "TIMEOUT"
    except (OSError, ValueError) as error:
        from beeagent_module.integrations.beescan.web import record_failure

        record_failure(
            service.storage, service.logger, case_id, error, "access_comparison"
        )
        failure = "ERROR"
    finally:
        owner_proof = None
        credentials.clear()
        try:
            session.close()
        except OSError, ValueError, RuntimeError:
            failure = "ERROR"
    lifecycle = AssessmentSnapshot(service.storage).json(
        case_id, "egress_lifecycle.json"
    )
    cleanup = (
        lifecycle.get("state") == "closed"
        and lifecycle.get("cleanup_verified") is True
        and lifecycle.get("enforcement_verified") is True
    )
    execution = AccessExecution(
        tuple(evidence), datetime.now(UTC), count, exact, cleanup, failure
    )
    result = evaluate_access(intent, execution)
    _persist(
        api,
        record_name,
        {"intent": _plain(intent), "execution": _plain(execution)},
    )
    if not finalize:
        return {
            "intent": intent,
            "execution": execution,
            "result": result,
            "steps": steps,
        }
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
        "schema_version": 5,
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
            "evidence_refs": [e.evidence_ref for e in evidence],
        },
    )
    _persist(api, "report.json", _plain(result))
    _write_report(
        api,
        "report.md",
        "# Access-control assessment\n\n"
        + result.status
        + "\n\n"
        + result.reason
        + "\n",
    )
    save_case(api, state)
    if finalize:
        invocation.observe_execution(
            case_id,
            "verification",
            "COMPLETED"
            if result.status in {"CANDIDATE", "NO_MATCH"}
            else result.status,
        )
    return {"case_id": case_id, "status": result.status}
