import json
import logging

from beeagent_module.core.ai_transport import call_structured_ai
from beeagent_module.core.beedrill_ai_assist import _response_format
from beeagent_module.core.rop_ai_adjudicator import _build_openai_response_format


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
