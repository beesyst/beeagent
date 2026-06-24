from typing import Any, cast

from beeagent_module.core.module_contract import AuthorityLevel
from beeagent_module.core.runtime_context import (
    RuntimeContext,
    generate_run_id,
    generate_session_id,
)


def test_generate_run_id() -> None:
    run_id = generate_run_id()
    assert run_id.startswith("run-")
    assert len(run_id) == 16


def test_generate_run_id_custom_prefix() -> None:
    run_id = generate_run_id(prefix="test")
    assert run_id.startswith("test-")
    assert len(run_id) == 17


def test_generate_session_id() -> None:
    session_id = generate_session_id()
    assert session_id.startswith("session-")
    assert len(session_id) == 20


def test_generate_session_id_custom_prefix() -> None:
    session_id = generate_session_id(prefix="custom")
    assert session_id.startswith("custom-")
    assert len(session_id) == 19


def test_run_id_uniqueness() -> None:
    ids = [generate_run_id() for _ in range(10)]
    assert len(set(ids)) == 10


def test_session_id_uniqueness() -> None:
    ids = [generate_session_id() for _ in range(10)]
    assert len(set(ids)) == 10

    ids = [generate_session_id() for _ in range(10)]
    assert len(set(ids)) == 10


def test_runtime_context_creation() -> None:
    run_id = generate_run_id()
    session_id = generate_session_id()

    ctx = RuntimeContext(
        run_id=run_id,
        session_id=session_id,
        case_type="oos_summary",
        module_id="beeagent-rop",
        authority=AuthorityLevel.READ_ONLY,
        payload={"key": "value"},
    )

    assert ctx.run_id == run_id
    assert ctx.session_id == session_id
    assert ctx.case_type == "oos_summary"
    assert ctx.module_id == "beeagent-rop"
    assert ctx.authority == AuthorityLevel.READ_ONLY
    assert ctx.payload == {"key": "value"}


def test_runtime_context_frozen() -> None:
    ctx = RuntimeContext(
        run_id="run-123",
        session_id="session-456",
        case_type="test_case",
        module_id="test_module",
        authority=AuthorityLevel.DRAFT_ONLY,
    )

    try:
        setattr(ctx, "run_id", "new-run")
        assert False, "RuntimeContext should be immutable"
    except Exception:
        pass


def test_runtime_context_default_payload() -> None:
    ctx = RuntimeContext(
        run_id="run-123",
        session_id="session-456",
        case_type="test",
        module_id="test",
        authority=AuthorityLevel.READ_ONLY,
    )

    assert ctx.payload == {}


def test_runtime_context_invalid_run_id() -> None:
    try:
        RuntimeContext(
            run_id="",
            session_id="session-456",
            case_type="test",
            module_id="test",
            authority=AuthorityLevel.READ_ONLY,
        )
        assert False, "Should reject empty run_id"
    except ValueError as e:
        assert "run_id" in str(e)


def test_runtime_context_invalid_session_id() -> None:
    try:
        RuntimeContext(
            run_id="run-123",
            session_id="",
            case_type="test",
            module_id="test",
            authority=AuthorityLevel.READ_ONLY,
        )
        assert False, "Should reject empty session_id"
    except ValueError as e:
        assert "session_id" in str(e)


def test_runtime_context_invalid_case_type() -> None:
    try:
        RuntimeContext(
            run_id="run-123",
            session_id="session-456",
            case_type="",
            module_id="test",
            authority=AuthorityLevel.READ_ONLY,
        )
        assert False, "Should reject empty case_type"
    except ValueError as e:
        assert "case_type" in str(e)


def test_runtime_context_invalid_module_id() -> None:
    try:
        RuntimeContext(
            run_id="run-123",
            session_id="session-456",
            case_type="test",
            module_id="",
            authority=AuthorityLevel.READ_ONLY,
        )
        assert False, "Should reject empty module_id"
    except ValueError as e:
        assert "module_id" in str(e)


def test_runtime_context_invalid_authority() -> None:
    try:
        RuntimeContext(
            run_id="run-123",
            session_id="session-456",
            case_type="test",
            module_id="test",
            authority=cast(Any, "invalid_authority"),
        )
        assert False, "Should reject invalid authority"
    except ValueError as e:
        assert "authority" in str(e)


def test_runtime_context_invalid_payload() -> None:
    try:
        RuntimeContext(
            run_id="run-123",
            session_id="session-456",
            case_type="test",
            module_id="test",
            authority=AuthorityLevel.READ_ONLY,
            payload=cast(Any, "invalid"),
        )
        assert False, "Should reject non-dict payload"
    except ValueError as e:
        assert "payload" in str(e)


def test_runtime_context_all_authority_levels() -> None:
    for authority in [
        AuthorityLevel.READ_ONLY,
        AuthorityLevel.DRAFT_ONLY,
        AuthorityLevel.EXECUTION_CAPABLE,
    ]:
        ctx = RuntimeContext(
            run_id="run-123",
            session_id="session-456",
            case_type="test",
            module_id="test",
            authority=authority,
        )
        assert ctx.authority == authority
