import json
import logging

import pytest

from beeagent_module.core.ai_transport import call_structured_ai
from beeagent_module.core.beedrill_ai_assist import _response_format
from beeagent_module.core.rop_ai_adjudicator import _build_openai_response_format
from tests.settings_support import read_test_settings


class _Response:
    def __init__(self, value: dict[str, object]) -> None:
        self._value = value

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._value).encode("utf-8")


def _call(**kwargs: object) -> str | None:
    arguments = {
        "prompt": "facts",
        "provider": "openai_responses",
        "model": "model",
        "api_key": "test-key",
        "base_url": "https://provider.test/v1",
        "timeout_seconds": 20,
        "max_output_tokens": 100,
        "temperature": 0.0,
        "responses_text_format": _response_format(),
        "output_chars_max": 400,
        "logger": logging.getLogger("test"),
    }
    arguments.update(kwargs)
    return call_structured_ai(**arguments)


def test_responses_transport_uses_bounded_schema_request() -> None:
    captured: dict[str, object] = {}

    def opener(req, timeout: int):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Response(
            {"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        )

    assert _call(urlopen=opener) == "{}"
    assert captured["url"] == "https://provider.test/v1/responses"
    assert captured["timeout"] == 20
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload == {
        "model": "model",
        "input": "facts",
        "temperature": 0.0,
        "max_output_tokens": 100,
        "text": {"format": _response_format()},
    }
    assert "max_output_chars" not in payload


def test_openai_compatible_transport_is_bounded() -> None:
    captured: dict[str, object] = {}

    def opener(req, timeout: int):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Response({"choices": [{"message": {"content": "{}"}}]})

    result = call_structured_ai(
        prompt="facts",
        provider="openai_compatible",
        model="model",
        api_key="test-key",
        base_url="https://provider.test/v1",
        timeout_seconds=20,
        max_output_tokens=100,
        temperature=0.0,
        responses_text_format=_response_format(),
        output_chars_max=1,
        logger=logging.getLogger("test"),
        urlopen=opener,
    )

    assert result is None
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["response_format"] == {"type": "json_object"}


def test_transport_rejects_missing_credentials_provider_failure_and_malformed_response() -> (
    None
):
    assert _call(api_key="") is None

    def timeout(*args: object, **kwargs: object):
        raise TimeoutError("timed out")

    assert _call(urlopen=timeout) is None

    def refused(*args: object, **kwargs: object):
        raise RuntimeError("provider refused request")

    assert _call(urlopen=refused) is None
    assert _call(urlopen=lambda *args, **kwargs: _Response({"output": []})) is None


def test_rop_and_beedrill_response_schemas_remain_distinct_and_strict() -> None:
    beedrill = _response_format()
    rop = _build_openai_response_format()

    schema = beedrill["schema"]
    assert isinstance(schema, dict)
    properties = schema["properties"]
    assert isinstance(properties, dict)

    assert schema["additionalProperties"] is False
    assert properties["remediation_unverified"] == {
        "type": "boolean",
        "const": True,
    }
    assert "security_verdict" not in properties
    assert rop["schema"] is not schema
    assert rop["strict"] is True


@pytest.mark.parametrize("global_name", ["openai", "openrouter", "deepseek"])
@pytest.mark.parametrize("mode", ["legacy", "default"])
@pytest.mark.parametrize("override", [None, "openai", "openrouter", "deepseek"])
def test_shared_profile_precedence_without_network(
    isolated_ai_settings, global_name, mode, override
):
    from copy import deepcopy

    from beeagent_module.core.ai_profiles import resolve_ai_profile

    settings = isolated_ai_settings({"ai": {}}, global_name)
    if mode == "default":
        settings["ai"]["default_profile"] = global_name
        for profile in settings["ai"]["profiles"].values():
            profile.pop("enabled")
    before = deepcopy(settings)
    name, profile = resolve_ai_profile(settings, override, require_api_key=True)
    assert name == (override or global_name)
    assert profile["model"] == f"test-{name}-model"
    assert set(profile) == {"provider", "model", "base_url", "api_key_env"}
    assert settings == before


@pytest.mark.parametrize(
    "value", [None, True, 1, [], {}, "", " ", "bad/name", "a" * 65, "x\n"]
)
@pytest.mark.parametrize("selector", ["default", "override", "catalog"])
def test_shared_profile_rejects_malformed_names(isolated_ai_settings, value, selector):
    from beeagent_module.core.ai_profiles import resolve_ai_profile

    settings = isolated_ai_settings({"ai": {}}, "openai")
    override = None
    if selector == "default":
        for profile in settings["ai"]["profiles"].values():
            profile.pop("enabled")
        settings["ai"]["default_profile"] = value
    elif selector == "override":
        if value is None:
            value = "missing"
        override = value
    else:
        if isinstance(value, (list, dict)):
            value = str(value)
        settings["ai"]["profiles"][value] = settings["ai"]["profiles"]["openai"]
    with pytest.raises(RuntimeError):
        resolve_ai_profile(settings, override)


@pytest.mark.parametrize(
    "key,value",
    [
        ("provider", "unknown"),
        ("provider", []),
        ("model", ""),
        ("model", "bad model"),
        ("model", "m\n"),
        ("model", "m" * 257),
        ("model", {}),
        ("api_key_env", ""),
        ("api_key_env", "bad/key"),
        ("api_key_env", "KEY\x00"),
        ("api_key_env", "1_KEY"),
        ("base_url", ""),
        ("base_url", "ftp://provider.test/v1"),
        ("base_url", "https://user:secret@provider.test"),
        ("base_url", "https://provider.test?key=secret"),
        ("base_url", "https://provider.test#secret"),
        ("base_url", "https://provider.test:0/v1"),
        ("base_url", "https://provider.test:99999/v1"),
        ("base_url", "https://provider.test:bad/v1"),
        ("base_url", "https://[broken/v1"),
        ("base_url", "https://bad..host/v1"),
        ("base_url", "https://provider.test/\n"),
        ("base_url", "https://provider.test\\evil/v1"),
        ("base_url", "https:///v1"),
    ],
)
def test_shared_profile_rejects_invalid_transport(isolated_ai_settings, key, value):
    from beeagent_module.core.ai_profiles import resolve_ai_profile

    settings = isolated_ai_settings({"ai": {}}, "openai")
    settings["ai"]["profiles"]["openai"][key] = value
    with pytest.raises(RuntimeError):
        resolve_ai_profile(settings)


@pytest.mark.parametrize("enabled", [False, True])
def test_shared_profile_rejects_mixed_selectors(isolated_ai_settings, enabled):
    from beeagent_module.core.ai_profiles import resolve_ai_profile

    settings = isolated_ai_settings({"ai": {}}, "openrouter")
    settings["ai"]["default_profile"] = "openrouter"
    for profile in settings["ai"]["profiles"].values():
        profile["enabled"] = enabled
    with pytest.raises(RuntimeError, match="Conflicting"):
        resolve_ai_profile(settings, "deepseek")


def test_selected_credentials_only(isolated_ai_settings, monkeypatch):
    from beeagent_module.core.ai_profiles import resolve_ai_profile

    settings = isolated_ai_settings({"ai": {}}, "openrouter")
    monkeypatch.delenv("OPENAI_API_KEY")
    resolve_ai_profile(settings, require_api_key=True)
    resolve_ai_profile(settings, "openai")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        resolve_ai_profile(settings, "openai", require_api_key=True)


@pytest.mark.parametrize("name", ["openai", "openrouter", "deepseek"])
def test_selected_profile_reuses_transport(isolated_ai_settings, name):
    from beeagent_module.core.ai_profiles import resolve_ai_profile

    settings = isolated_ai_settings({"ai": {}}, name)
    _, profile = resolve_ai_profile(settings)
    calls = []

    def opener(req, timeout):
        calls.append((req.full_url, json.loads(req.data)))
        return _Response(
            {"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
            if name == "openai"
            else {"choices": [{"message": {"content": "{}"}}]}
        )

    assert (
        _call(
            provider=profile["provider"],
            model=profile["model"],
            base_url=profile["base_url"],
            urlopen=opener,
        )
        == "{}"
    )
    suffix = "/responses" if name == "openai" else "/chat/completions"
    assert calls[0][0] == profile["base_url"] + suffix
    assert calls[0][1]["model"] == profile["model"]


@pytest.mark.parametrize("rop_override", [None, "openrouter", "openai", "deepseek"])
def test_all_consumers_select_independently(
    isolated_ai_settings, monkeypatch, tmp_path, rop_override
):

    from beeagent_module.core import (
        beedrill_ai_assist,
        rop_ai_adjudicator,
        rop_ai_assist,
    )
    from beeagent_module.integrations.beescan import investigation

    settings = isolated_ai_settings(
        read_test_settings(), "openrouter"
    )
    settings["ai"]["default_profile"] = "openrouter"
    for profile in settings["ai"]["profiles"].values():
        profile.pop("enabled")
    for module in settings["modules"]["registry"]:
        module["enabled"] = True
    if rop_override is not None:
        settings["rop"]["ai_assist"]["ai_profile"] = rop_override
    rop_model = f"test-{rop_override or 'openrouter'}-model"
    settings["beedrill"]["ai_assist"]["ai_profile"] = "openai"
    settings["beescan"]["investigation"]["ai_profile"] = "deepseek"
    calls = []

    def transport(**kwargs):
        calls.append(kwargs)
        schema = kwargs["responses_text_format"]["name"]
        if schema == "beedrill_ai_assist":
            return json.dumps(
                {
                    "explanation": "Bounded facts.",
                    "remediation": [],
                    "remediation_unverified": True,
                }
            )
        if schema == "task_classification":
            return '{"intent":"framework_version_disclosure"}'
        return "malformed output"

    monkeypatch.setattr(rop_ai_adjudicator, "call_structured_ai", transport)
    monkeypatch.setattr(beedrill_ai_assist, "call_structured_ai", transport)
    monkeypatch.setattr(investigation, "call_structured_ai", transport)
    event = {"event_id": "isolated", "case_type": "unknown", "is_fallback": True}
    requests, decisions, results, counts = rop_ai_adjudicator.run_adjudicator_batch(
        [event], settings, logging.getLogger("test")
    )
    assert results[0]["ai_model"] == rop_model
    assert results[0]["final_case_type"] == "unknown"
    legacy_cfg = rop_ai_assist.resolve_ai_profile(
        settings["rop"]["ai_assist"], settings["ai"]
    )
    assert legacy_cfg["model"] == rop_model
    monkeypatch.setattr(rop_ai_assist, "_call_ai_provider", lambda **kwargs: None)
    legacy = rop_ai_assist.run_ai_assist_for_event(
        event, legacy_cfg, None, 0.7, logging.getLogger("test")
    )
    assert legacy["request"]["model"] == rop_model
    drill = beedrill_ai_assist.run_beedrill_ai_assist(
        settings=settings,
        records=[{"explanation_facts": {}, "scenario_id": "test", "run_id": "test"}],
        suite_run_id="suite",
        logger=logging.getLogger("test"),
    )
    assert drill["status"] == "ok"
    assert drill["model"] == "test-openai-model"
    assert (
        investigation.classify_task(
            settings, "Identify framework", logging.getLogger("test")
        )
        == "framework_version_disclosure"
    )
    assert [call["model"] for call in calls] == [
        rop_model,
        "test-openai-model",
        "test-deepseek-model",
    ]
    rop_ai_adjudicator.write_adjudicator_artifacts(
        tmp_path,
        "independent",
        requests,
        decisions,
        results,
        counts,
        logging.getLogger("test"),
    )
    rop_ai_assist.write_ai_assist_artifacts(
        tmp_path,
        "independent",
        [legacy["request"]],
        [legacy["decision"]],
        [legacy["result"]],
        {},
        logging.getLogger("test"),
    )
    (tmp_path / "beedrill_ai_assist.json").write_text(json.dumps(drill))
    serialized = json.dumps([drill, legacy, requests, decisions, results])
    assert "sk-test" not in serialized
    assert "Authorization" not in serialized


def test_investigation_cli_preserves_selected_provenance_on_ai_failure(
    isolated_ai_settings, monkeypatch, tmp_path
):

    from beeagent_module.integrations.beescan import investigation
    from beeagent_module.integrations.beescan.probe import handle_beescan_cli
    from tests.test_beescan_investigation import configure_approved, task_file

    settings = isolated_ai_settings(
        read_test_settings(), "openrouter"
    )
    configure_approved(settings, monkeypatch)
    settings["beescan"]["investigation"]["ai_profile"] = "deepseek"
    monkeypatch.setattr(investigation, "_load_domain", lambda **kw: (None, "a" * 40))
    monkeypatch.setattr(investigation, "call_structured_ai", lambda **kw: "invalid")
    code = handle_beescan_cli(
        ["investigate", str(task_file(tmp_path))],
        settings=settings,
        reload_settings=lambda: settings,
        storage_dir=tmp_path / "storage",
        logger=logging.getLogger("test"),
    )
    assert code == 5
    (result_path,) = (tmp_path / "storage/runs").glob(
        "*/module-beescan/investigation_result.json"
    )
    result = json.loads(result_path.read_text())
    assert result["complete"] is False
    assert result["request_count"] == 0
    assert result["ai_provider"] == "openai_compatible"
    assert result["ai_model"] == "test-deepseek-model"
    assert "sk-test" not in result_path.read_text()
