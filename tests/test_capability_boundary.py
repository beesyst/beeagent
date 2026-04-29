import logging

from beeagent_module.core.capability_contract import CapabilityRequest, CapabilityStatus
from beeagent_module.core.capability_runtime import LocalCapabilityRuntime
from beeagent_module.core.module_contract import AuthorityLevel


# Тест: чек, что при вызове capability не происходит скрытого фоллбек пути к другому capability с более широкими правами
def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_capability_boundary")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Тест: чек, что при вызове capability не происходит скрытого фоллбек пути к другому capability с более широкими правами
def test_capability_success_with_rop_like_name() -> None:
    runtime = LocalCapabilityRuntime(logger=_null_logger())

    def handler(request: CapabilityRequest) -> dict:
        assert request.capability_name == "email.search"
        return {"items": [{"id": "mail-1"}]}

    runtime.register(
        "email.search", handler, required_authority=AuthorityLevel.READ_ONLY
    )

    result = runtime.call(
        CapabilityRequest(
            capability_name="email.search",
            authority=AuthorityLevel.READ_ONLY,
            payload={"query": "invoice"},
            run_id="run-100",
            module_id="beeagent-rop",
            case_type="lead_classification",
        )
    )

    assert result.status == CapabilityStatus.OK
    assert result.data == {"items": [{"id": "mail-1"}]}


# Тест: чек, что при вызове capability с недостаточными правами возвращается отказ без фоллбеков
def test_capability_refused_for_insufficient_authority() -> None:
    runtime = LocalCapabilityRuntime(logger=_null_logger())

    runtime.register(
        "bitrix.find_lead",
        lambda _request: {"lead_id": "L-001"},
        required_authority=AuthorityLevel.DRAFT_ONLY,
    )

    result = runtime.call(
        CapabilityRequest(
            capability_name="bitrix.find_lead",
            authority=AuthorityLevel.READ_ONLY,
            payload={"email": "lead@example.com"},
        )
    )

    assert result.status == CapabilityStatus.REFUSED
    assert result.diagnostics["reason"] == "insufficient_authority"


# Тест: чек, что при вызове capability, который выбрасывает исключение TimeoutError, возвращается статус TIMEOUT
def test_capability_timeout_state() -> None:
    runtime = LocalCapabilityRuntime(logger=_null_logger())

    def timeout_handler(_request: CapabilityRequest) -> dict:
        raise TimeoutError("simulated timeout")

    runtime.register("attachment.extract_text", timeout_handler)

    result = runtime.call(
        CapabilityRequest(
            capability_name="attachment.extract_text",
            authority=AuthorityLevel.READ_ONLY,
            payload={"attachment_id": "A-1"},
        )
    )

    assert result.status == CapabilityStatus.TIMEOUT
    assert result.diagnostics["reason"] == "timeout"


# Тест: чек, что при вызове неизвестного capability возвращается отказ с правильной причиной
def test_capability_refused_unknown_name() -> None:
    runtime = LocalCapabilityRuntime(logger=_null_logger())

    result = runtime.call(
        CapabilityRequest(
            capability_name="parser.lookup_email",
            authority=AuthorityLevel.READ_ONLY,
            payload={"email": "user@example.com"},
        )
    )

    assert result.status == CapabilityStatus.REFUSED
    assert result.diagnostics["reason"] == "unknown_capability"


# Тест: чек, что при вызове отключенного capability возвращается отказ с правильной причиной
def test_capability_refused_when_disabled() -> None:
    runtime = LocalCapabilityRuntime(logger=_null_logger())

    runtime.register(
        "email.read",
        lambda _request: {"body": "hidden"},
        enabled=False,
    )

    result = runtime.call(
        CapabilityRequest(
            capability_name="email.read",
            authority=AuthorityLevel.READ_ONLY,
            payload={"message_id": "M-1"},
        )
    )

    assert result.status == CapabilityStatus.REFUSED
    assert result.diagnostics["reason"] == "capability_disabled"


# Тест: чек, что при вызове capability не происходит скрытого фоллбек пути к другому capability с более широкими правами
def test_no_hidden_fallback_path() -> None:
    runtime = LocalCapabilityRuntime(logger=_null_logger())
    called = {"email_search": 0}

    def email_search(_request: CapabilityRequest) -> dict:
        called["email_search"] += 1
        return {"items": []}

    runtime.register("email.search", email_search)

    result = runtime.call(
        CapabilityRequest(
            capability_name="bitrix.read_timeline",
            authority=AuthorityLevel.READ_ONLY,
            payload={"lead_id": "L-10"},
        )
    )

    assert result.status == CapabilityStatus.REFUSED
    assert result.diagnostics["reason"] == "unknown_capability"
    assert called["email_search"] == 0
