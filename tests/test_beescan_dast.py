import hashlib
import random
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import pytest

from beeagent_module.integrations.beescan.dast import DastPolicy, approval_identity
from beeagent_module.integrations.beescan.dast_runner import (
    traversal_oracle,
    verification_fallback_required,
    verification_match_indexes,
    verification_coverage,
)
from beeagent_module.integrations.beescan.dast_worker import (
    fallback_required,
    verification_targets,
)
from beeagent_module.integrations.beescan.policy import HTTPX_SHA256, ProbePolicy
from tests.test_beescan_detection import approved as approved


@pytest.fixture
def policy(approved):
    original, _, _ = approved
    values = {key: getattr(original, key) for key in ProbePolicy.__dataclass_fields__}
    values.update(
        origin="https://example.test",
        connected_ip="93.184.216.34",
        network_namespace="/beeagent-managed/ns/net",
        user_namespace="/beeagent-managed/ns/user",
        method="http_probe",
        sha256=HTTPX_SHA256,
        provider_version="1.12.0",
    )
    return DastPolicy(
        ProbePolicy(**values),
        True,
        "active_dast",
        (),
        10,
        30,
        "/tmp/pinned.zip",
        "authenticated_discovery",
        1,
    )


def test_explicit_profile_approval_and_legacy_identity(policy):
    legacy = asdict(policy)
    legacy.pop("profile")
    for key in ("valid_from", "expires_at"):
        legacy["transport"].pop(key)
    import json

    assert (
        approval_identity(policy)
        == hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest()
    )
    new = replace(policy, profile="traversal-nonrecursive-v1")
    assert approval_identity(new) != approval_identity(policy)
    config = asdict(new)
    config["entries"] = []
    for key in ("valid_from", "expires_at"):
        config["transport"][key] = config["transport"][key].isoformat()
    assert DastPolicy.from_config(config) == new
    with pytest.raises(ValueError):
        replace(new, entries=("/?file=one",), entry_selection="exact_entry")
    with pytest.raises(ValueError):
        replace(new, profile="foreign")

    class Operator:
        def verify(self):
            return None

    now = datetime.now(UTC)
    with pytest.raises(PermissionError):
        replace(new, approved=False).authorize(Operator(), at=now)
    with pytest.raises(PermissionError):
        replace(
            new, transport=replace(new.transport, expires_at=now + timedelta(seconds=1))
        ).authorize(Operator(), at=now)


@pytest.mark.parametrize(
    "entry", ["/image?filename=one.jpg", "/retrieve?document=two.txt&format=text"]
)
def test_fixed_targets_preserve_source_parameter_and_structure(entry):
    targets = verification_targets(entry)
    assert len(set(targets)) == 5 and targets[0] == entry
    assert all(target.split("?")[0] == entry.split("?")[0] for target in targets)
    assert all("....//" in target for target in targets[1:])
    if "&" in entry:
        assert all(target.endswith("&format=text") for target in targets)


def test_superfluous_decode_targets_preserve_encoded_source_parameter():
    entry = "/image?filename=one.jpg&format=text"
    targets = verification_targets(entry, "superfluous-url-decode")
    assert len(set(targets)) == 5 and targets[0] == entry
    assert all(target.split("?")[0] == "/image" for target in targets)
    assert all("%252f" in target for target in targets[1:])
    assert all(target.endswith("&format=text") for target in targets)
    assert fallback_required((200, 400, 400, 400, 400))
    assert not fallback_required((200, 404, 400, 404, 404))


@pytest.mark.parametrize(
    "entry",
    [
        "/",
        "//foreign/a?x=one",
        "/../a?x=one",
        "/a?x=one&x=two",
        "/a?x=%0d",
        "/a?x=one#fragment",
        "https://foreign/a?x=one",
        "/a?x=one\r\n",
    ],
)
def test_unsafe_verification_targets_refuse(entry):
    with pytest.raises(ValueError):
        verification_targets(entry)


def test_host_oracle_rejects_reflection_html_and_bounded_fuzz():
    proof = b"root:x:0:0:root:/root:/bin/bash\n"
    assert traversal_oracle(proof)
    for body in (
        b"200 OK",
        b"passwd",
        b"....//etc/passwd",
        b"<pre>" + proof + b"</pre>",
        b"reflected " + proof,
        proof * 257,
        b"root:x:1:1:root:/root:/bin/bash\n",
    ):
        assert not traversal_oracle(body)
    generator = random.Random(359)
    for _ in range(1000):
        assert not traversal_oracle(generator.randbytes(generator.randrange(256)))


def test_host_coverage_requires_baseline_negative_controls_and_exact_facts():
    targets = verification_targets("/read?document=one")
    facts = [
        {
            "request_sha256": hashlib.sha256(target.encode()).hexdigest(),
            "response_sha256": "a" * 64,
            "status_code": 200 if index == 0 else 404,
            "oracle": False,
        }
        for index, target in enumerate(targets)
    ]
    assert verification_coverage(facts)
    positive = [dict(item) for item in facts]
    positive[2].update(status_code=200, oracle=True)
    assert verification_coverage(positive)
    for index in (0, 1, 3):
        altered = [dict(item) for item in positive]
        altered[index].update(status_code=200, oracle=True)
        assert not verification_coverage(altered)
    for malformed in (
        facts[:-1],
        facts + facts[:1],
        [facts[0]] * 5,
        [{**item, "body": "untrusted"} for item in facts],
    ):
        assert not verification_coverage(malformed)


def test_positive_verification_with_http_400_controls():
    statuses = (200, 400, 400, 400, 200)
    facts = [
        {
            "request_sha256": hashlib.sha256(f"probe-{index}".encode()).hexdigest(),
            "response_sha256": "a" * 64,
            "status_code": status,
            "oracle": index == 4,
        }
        for index, status in enumerate(statuses)
    ]

    assert verification_coverage(facts)

    negative = [dict(item) for item in facts]
    negative[4]["oracle"] = False
    assert not verification_coverage(negative)

    for index in (0, 1, 3):
        altered = [dict(item) for item in facts]
        altered[index]["oracle"] = True
        assert not verification_coverage(altered)

    for status in (403, 500):
        altered = [dict(item) for item in facts]
        altered[1]["status_code"] = status
        assert not verification_coverage(altered)


def test_positive_target_without_oracle_is_not_complete_negative():
    facts = [
        {
            "request_sha256": hashlib.sha256(f"probe-{index}".encode()).hexdigest(),
            "response_sha256": "a" * 64,
            "status_code": 200 if index in {0, 2} else 404,
            "oracle": False,
        }
        for index in range(5)
    ]

    assert not verification_coverage(facts)


def test_superfluous_decode_fallback_requires_ambiguous_primary_controls():
    primary = [
        {
            "request_sha256": hashlib.sha256(f"first-{index}".encode()).hexdigest(),
            "response_sha256": "a" * 64,
            "status_code": 200 if index == 0 else 400,
            "oracle": False,
        }
        for index in range(5)
    ]
    fallback = [
        {
            "request_sha256": hashlib.sha256(f"second-{index}".encode()).hexdigest(),
            "response_sha256": "b" * 64,
            "status_code": 200 if index in {0, 2} else 404,
            "oracle": index == 2,
        }
        for index in range(5)
    ]
    assert verification_fallback_required(primary)
    facts = primary + fallback[1:]
    assert verification_coverage(facts)
    assert verification_match_indexes(facts) == (6,)
    assert not verification_coverage(fallback + fallback)
    assert not verification_coverage(
        primary + [{**item, "oracle": True} for item in fallback[1:]]
    )


def test_incomplete_verification_evidence_cannot_be_covered():
    assert verification_coverage([]) is False
    assert verification_coverage(
        [
            {
                "request_sha256": "a" * 64,
                "response_sha256": "b" * 64,
                "status_code": 200,
                "oracle": False,
            }
        ]
    ) is False
