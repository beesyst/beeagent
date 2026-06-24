from beeagent_module.core.module_contract import (
    AuthorityLevel,
    ModuleContext,
    ModuleContract,
    ModuleResult,
)


class _StubReadOnlyModule:
    @property
    def module_id(self) -> str:
        return "stub-read-only"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.READ_ONLY

    def supported_case_types(self) -> list[str]:
        return ["oos_summary", "report"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        if context.case_type not in self.supported_case_types():
            return ModuleResult(
                module_id=self.module_id,
                case_type=context.case_type,
                authority=self.authority,
                status="skipped",
                summary=f"case_type '{context.case_type}' is not supported by {self.module_id}",
            )
        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="ok",
            summary="stub read-only result",
            data={"count": 1},
        )


class _StubDraftModule:
    @property
    def module_id(self) -> str:
        return "stub-draft"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.DRAFT_ONLY

    def supported_case_types(self) -> list[str]:
        return ["lead_classification"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="ok",
            summary="draft produced",
        )


class _StubExecutionModule:
    @property
    def module_id(self) -> str:
        return "stub-exec"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.EXECUTION_CAPABLE

    def supported_case_types(self) -> list[str]:
        return ["send_notification"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="ok",
            summary="action executed",
        )


def test_import_authority_level() -> None:
    assert AuthorityLevel.READ_ONLY == "read_only"
    assert AuthorityLevel.DRAFT_ONLY == "draft_only"
    assert AuthorityLevel.EXECUTION_CAPABLE == "execution_capable"


def test_import_module_context() -> None:
    assert ModuleContext is not None


def test_import_module_result() -> None:
    assert ModuleResult is not None


def test_import_module_contract() -> None:
    assert ModuleContract is not None


def test_authority_level_is_str_enum() -> None:
    assert isinstance(AuthorityLevel.READ_ONLY.value, str)
    assert str(AuthorityLevel.DRAFT_ONLY) == "AuthorityLevel.DRAFT_ONLY"
    assert AuthorityLevel.READ_ONLY.value == "read_only"


def test_authority_level_all_three_values() -> None:
    values = {al.value for al in AuthorityLevel}
    assert values == {"read_only", "draft_only", "execution_capable"}


def test_module_context_minimal_fields() -> None:
    ctx = ModuleContext(
        run_id="run-001", case_type="oos_summary", module_id="stub-read-only"
    )
    assert ctx.run_id == "run-001"
    assert ctx.case_type == "oos_summary"
    assert ctx.module_id == "stub-read-only"
    assert ctx.payload == {}


def test_module_context_with_payload() -> None:
    ctx = ModuleContext(
        run_id="run-002",
        case_type="report",
        module_id="stub-read-only",
        payload={"store_id": "S1", "week": 4},
    )
    assert ctx.payload["store_id"] == "S1"


def test_module_context_is_frozen() -> None:
    ctx = ModuleContext(run_id="run-003", case_type="oos_summary", module_id="stub")
    try:
        setattr(ctx, "run_id", "mutated")
        assert False, "should have raised FrozenInstanceError"
    except Exception:
        pass


def test_module_result_ok() -> None:
    result = ModuleResult(
        module_id="stub-read-only",
        case_type="oos_summary",
        authority=AuthorityLevel.READ_ONLY,
        status="ok",
        summary="all good",
        data={"count": 5},
    )
    assert result.status == "ok"
    assert result.authority == AuthorityLevel.READ_ONLY
    assert result.data["count"] == 5


def test_module_result_error() -> None:
    result = ModuleResult(
        module_id="stub-read-only",
        case_type="oos_summary",
        authority=AuthorityLevel.READ_ONLY,
        status="error",
        summary="something went wrong",
    )
    assert result.status == "error"
    assert result.data == {}


def test_module_result_skipped() -> None:
    result = ModuleResult(
        module_id="stub-read-only",
        case_type="unknown",
        authority=AuthorityLevel.READ_ONLY,
        status="skipped",
        summary="not applicable",
    )
    assert result.status == "skipped"


def test_module_result_is_frozen() -> None:
    result = ModuleResult(
        module_id="m",
        case_type="c",
        authority=AuthorityLevel.READ_ONLY,
        status="ok",
        summary="s",
    )
    try:
        setattr(result, "status", "mutated")
        assert False, "should have raised FrozenInstanceError"
    except Exception:
        pass


def test_stub_satisfies_module_contract_protocol() -> None:
    stub = _StubReadOnlyModule()
    assert isinstance(stub, ModuleContract)


def test_stub_draft_satisfies_protocol() -> None:
    assert isinstance(_StubDraftModule(), ModuleContract)


def test_stub_exec_satisfies_protocol() -> None:
    assert isinstance(_StubExecutionModule(), ModuleContract)


def test_module_id_property() -> None:
    stub = _StubReadOnlyModule()
    assert stub.module_id == "stub-read-only"


def test_authority_property_read_only() -> None:
    stub = _StubReadOnlyModule()
    assert stub.authority == AuthorityLevel.READ_ONLY


def test_authority_property_draft_only() -> None:
    stub = _StubDraftModule()
    assert stub.authority == AuthorityLevel.DRAFT_ONLY


def test_authority_property_execution_capable() -> None:
    stub = _StubExecutionModule()
    assert stub.authority == AuthorityLevel.EXECUTION_CAPABLE


def test_supported_case_types_returns_list() -> None:
    stub = _StubReadOnlyModule()
    result = stub.supported_case_types()
    assert isinstance(result, list)
    assert len(result) > 0


def test_supported_case_types_all_strings() -> None:
    stub = _StubReadOnlyModule()
    for ct in stub.supported_case_types():
        assert isinstance(ct, str)


def test_handle_returns_module_result() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-010", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert isinstance(result, ModuleResult)


def test_handle_ok_for_supported_case_type() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-011", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.status == "ok"
    assert result.module_id == "stub-read-only"
    assert result.case_type == "oos_summary"
    assert result.authority == AuthorityLevel.READ_ONLY


def test_handle_skipped_for_unsupported_case_type() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-012", case_type="unknown_case", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.status == "skipped"
    assert result.module_id == "stub-read-only"


def test_handle_preserves_authority_in_result() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-013", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.authority == stub.authority


def test_handle_draft_module() -> None:
    stub = _StubDraftModule()
    ctx = ModuleContext(
        run_id="run-020", case_type="lead_classification", module_id="stub-draft"
    )
    result = stub.handle(ctx)
    assert result.status == "ok"
    assert result.authority == AuthorityLevel.DRAFT_ONLY


def test_handle_execution_module() -> None:
    stub = _StubExecutionModule()
    ctx = ModuleContext(
        run_id="run-030", case_type="send_notification", module_id="stub-exec"
    )
    result = stub.handle(ctx)
    assert result.status == "ok"
    assert result.authority == AuthorityLevel.EXECUTION_CAPABLE


def test_read_only_module_does_not_return_execution_capable_authority() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-014", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.authority != AuthorityLevel.EXECUTION_CAPABLE


def test_handle_result_summary_is_non_empty_string() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-015", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert isinstance(result.summary, str)
    assert len(result.summary) > 0


def test_handle_result_data_is_dict() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-016", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert isinstance(result.data, dict)
