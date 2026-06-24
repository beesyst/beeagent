import json
import logging
from unittest.mock import Mock, patch
from urllib import error

from beeagent_module.core.llm import explain_recommendations


def test_llm_disabled() -> None:
    llm_cfg = {"enabled": False}
    recommendations = [{"sku": "SKU1", "action": "order"}]

    result = explain_recommendations(llm_cfg, recommendations)

    assert result is None


def test_llm_no_api_key() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "MISSING_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    with patch("beeagent_module.core.llm.os.getenv", return_value=""):
        result = explain_recommendations(llm_cfg, recommendations)

    assert result is None


def test_llm_unsupported_provider() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "anthropic",
        "model": "claude-3",
        "api_key_env": "API_KEY",
        "api_url": "https://api.anthropic.com/v1/messages",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-key"):
        result = explain_recommendations(llm_cfg, recommendations)

    assert result is None


def test_llm_successful_request() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [
        {"sku": "SKU1", "action": "order", "quantity": 50},
        {"sku": "SKU2", "action": "check", "reason": "low stock"},
    ]

    mock_response_data = {
        "output_text": "Order 50 units of SKU1. Check SKU2 due to low stock."
    }

    mock_response = Mock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch(
            "beeagent_module.core.llm.request.urlopen", return_value=mock_response
        ) as mock_urlopen:
            with patch("beeagent_module.core.llm.request.Request") as mock_request_cls:
                mock_request = Mock()
                mock_request_cls.return_value = mock_request

                result = explain_recommendations(llm_cfg, recommendations)

                assert mock_request_cls.called
                call_args = mock_request_cls.call_args
                assert call_args[0][0] == "https://api.openai.com/v1/responses"

                payload = json.loads(call_args[1]["data"].decode("utf-8"))
                assert payload["model"] == "gpt-4o-mini"
                assert len(payload["input"]) == 2
                assert payload["input"][0]["role"] == "developer"
                assert payload["input"][1]["role"] == "user"

                headers = call_args[1]["headers"]
                assert headers["Content-Type"] == "application/json"
                assert headers["Authorization"] == "Bearer test-api-key"
                assert call_args[1]["method"] == "POST"
                assert mock_urlopen.call_args[1]["timeout"] == 60

                assert result == "Order 50 units of SKU1. Check SKU2 due to low stock."


def test_llm_empty_choices() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    mock_response_data = {"output_text": ""}

    mock_response = Mock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch(
            "beeagent_module.core.llm.request.urlopen", return_value=mock_response
        ):
            result = explain_recommendations(llm_cfg, recommendations)

    assert result is None


def test_llm_request_exception() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch(
            "beeagent_module.core.llm.request.urlopen",
            side_effect=Exception("Network error"),
        ):
            logger = logging.getLogger("test")
            result = explain_recommendations(llm_cfg, recommendations, logger=logger)

    assert result is None


def test_llm_custom_api_url() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://custom.openai.proxy.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    mock_response_data = {"output_text": "Custom endpoint response"}

    mock_response = Mock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch(
            "beeagent_module.core.llm.request.urlopen", return_value=mock_response
        ):
            with patch("beeagent_module.core.llm.request.Request") as mock_request_cls:
                result = explain_recommendations(llm_cfg, recommendations)
                call_args = mock_request_cls.call_args
                assert call_args[0][0] == "https://custom.openai.proxy.com/v1/responses"
                assert result == "Custom endpoint response"


def test_llm_missing_api_url_returns_none() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch("beeagent_module.core.llm.request.Request") as mock_request_cls:
            result = explain_recommendations(llm_cfg, recommendations)

            assert result is None
            assert mock_request_cls.call_args is None


def test_llm_timeout_retries_then_success() -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]

    mock_response_data = {"output_text": "Recovered after retries"}
    mock_response = Mock()
    mock_response.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_response.__enter__ = Mock(return_value=mock_response)
    mock_response.__exit__ = Mock(return_value=False)

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch(
            "beeagent_module.core.llm.request.urlopen",
            side_effect=[TimeoutError(), TimeoutError(), mock_response],
        ) as mock_urlopen:
            result = explain_recommendations(llm_cfg, recommendations)

    assert result == "Recovered after retries"
    assert mock_urlopen.call_count == 3


def test_llm_timeout_after_retries_returns_none(caplog) -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 1},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]
    logger = logging.getLogger("test_llm_timeout")

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch(
            "beeagent_module.core.llm.request.urlopen", side_effect=TimeoutError()
        ):
            with caplog.at_level(logging.WARNING):
                result = explain_recommendations(
                    llm_cfg, recommendations, logger=logger
                )

    assert result is None
    assert "llm timeout, retry 1/1" in caplog.text
    assert "llm timeout after retries, fallback to rules-only" in caplog.text


def test_llm_http_error_returns_none(caplog) -> None:
    llm_cfg = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "api_url": "https://api.openai.com/v1/responses",
        "prompts_path": "config/prompts.yml",
        "throttling": {"timeout": 60, "retries": 2},
    }
    recommendations = [{"sku": "SKU1", "action": "order"}]
    logger = logging.getLogger("test_llm_http")

    from email.message import Message

    hdrs = Message()

    http_error = error.HTTPError(
        url="https://api.openai.com/v1/responses",
        code=429,
        msg="Too Many Requests",
        hdrs=hdrs,
        fp=None,
    )

    with patch("beeagent_module.core.llm.os.getenv", return_value="test-api-key"):
        with patch("beeagent_module.core.llm.request.urlopen", side_effect=http_error):
            with caplog.at_level(logging.ERROR):
                result = explain_recommendations(
                    llm_cfg, recommendations, logger=logger
                )

    assert result is None
    assert "llm http error status=429" in caplog.text
