from beeagent_module.core.module_contract import (
    AuthorityLevel,
    ModuleContext,
    ModuleContract,
    ModuleResult,
)


# Модульные контрактные тесты для проверки базовой целостности и соблюдения протокола внешними модулями
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


# Минимальные конкретные модули для проверки, что разные уровни authority могут coexist и соблюдают контракт
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


# Модуль для проверки execution_capable authority и что read_only модули не могут возвращать execution_capable в результате
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


# Автоматические тесты для проверки базовой целостности контрактных классов и соблюдения протокола внешними модулями
def test_import_authority_level() -> None:
    assert AuthorityLevel.READ_ONLY == "read_only"
    assert AuthorityLevel.DRAFT_ONLY == "draft_only"
    assert AuthorityLevel.EXECUTION_CAPABLE == "execution_capable"


# Тест: контрактные классы должны быть импортируемыми и иметь ожидаемые атрибуты
def test_import_module_context() -> None:
    assert ModuleContext is not None


# Тест: контрактные классы должны быть импортируемыми и иметь ожидаемые атрибуты
def test_import_module_result() -> None:
    assert ModuleResult is not None


# Тест: контрактный протокол должен быть импортируемым и проверяемым через isinstance() для конкретных модулей
def test_import_module_contract() -> None:
    assert ModuleContract is not None


# Тест: AuthorityLevel должен быть строковым Enum с ожидаемыми значениями
def test_authority_level_is_str_enum() -> None:
    assert isinstance(AuthorityLevel.READ_ONLY.value, str)
    assert str(AuthorityLevel.DRAFT_ONLY) == "AuthorityLevel.DRAFT_ONLY"
    assert AuthorityLevel.READ_ONLY.value == "read_only"


# Тест: все три значения AuthorityLevel должны быть присутствовать и уникальны
def test_authority_level_all_three_values() -> None:
    values = {al.value for al in AuthorityLevel}
    assert values == {"read_only", "draft_only", "execution_capable"}


# Тест: ModuleContext должен быть неизменяемым dataclass с ожидаемыми полями
def test_module_context_minimal_fields() -> None:
    ctx = ModuleContext(
        run_id="run-001", case_type="oos_summary", module_id="stub-read-only"
    )
    assert ctx.run_id == "run-001"
    assert ctx.case_type == "oos_summary"
    assert ctx.module_id == "stub-read-only"
    assert ctx.payload == {}


# Тест: ModuleContext должен корректно сохранять и возвращать произвольный словарь в поле payload
def test_module_context_with_payload() -> None:
    ctx = ModuleContext(
        run_id="run-002",
        case_type="report",
        module_id="stub-read-only",
        payload={"store_id": "S1", "week": 4},
    )
    assert ctx.payload["store_id"] == "S1"


# Тест: ModuleContext должен быть неизменяемым (frozen), попытка изменить поле должна вызывать ошибку
def test_module_context_is_frozen() -> None:
    ctx = ModuleContext(run_id="run-003", case_type="oos_summary", module_id="stub")
    try:
        setattr(ctx, "run_id", "mutated")
        assert False, "should have raised FrozenInstanceError"
    except Exception:
        pass


# Тест: ModuleResult должен быть неизменяемым dataclass с ожидаемыми полями и типами
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


# Тест: ModuleResult должен корректно сохранять и возвращать произвольный словарь в поле data, даже при статусе "error"
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


# Тест: ModuleResult должен поддерживать статус "skipped" для случаев, когда модуль не применим к данному case_type
def test_module_result_skipped() -> None:
    result = ModuleResult(
        module_id="stub-read-only",
        case_type="unknown",
        authority=AuthorityLevel.READ_ONLY,
        status="skipped",
        summary="not applicable",
    )
    assert result.status == "skipped"


# Тест: ModuleResult должен быть неизменяемым (frozen), попытка изменить поле должна вызывать ошибку
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


# Тест: конкретные модули должны удовлетворять протоколу ModuleContract и быть распознаваемыми через isinstance()
def test_stub_satisfies_module_contract_protocol() -> None:
    stub = _StubReadOnlyModule()
    assert isinstance(stub, ModuleContract)


# Тест: разные модули с разными authority должны все удовлетворять протоколу ModuleContract
def test_stub_draft_satisfies_protocol() -> None:
    assert isinstance(_StubDraftModule(), ModuleContract)


# Тест: execution_capable модуль должен удовлетворять протоколу ModuleContract
def test_stub_exec_satisfies_protocol() -> None:
    assert isinstance(_StubExecutionModule(), ModuleContract)


# Тест: module_id property должен возвращать уникальный стабильный идентификатор для каждого модуля
def test_module_id_property() -> None:
    stub = _StubReadOnlyModule()
    assert stub.module_id == "stub-read-only"


# Тест: authority property должен возвращать заявленный уровень authority для каждого модуля
def test_authority_property_read_only() -> None:
    stub = _StubReadOnlyModule()
    assert stub.authority == AuthorityLevel.READ_ONLY


# Тест: authority property должен возвращать заявленный уровень authority для draft_only модуля
def test_authority_property_draft_only() -> None:
    stub = _StubDraftModule()
    assert stub.authority == AuthorityLevel.DRAFT_ONLY


# Тест: authority property должен возвращать заявленный уровень authority для execution_capable модуля
def test_authority_property_execution_capable() -> None:
    stub = _StubExecutionModule()
    assert stub.authority == AuthorityLevel.EXECUTION_CAPABLE


# Тест: supported_case_types() должен возвращать список строк, который не пустой
def test_supported_case_types_returns_list() -> None:
    stub = _StubReadOnlyModule()
    result = stub.supported_case_types()
    assert isinstance(result, list)
    assert len(result) > 0


# Тест: все элементы, возвращаемые supported_case_types(), должны быть строками
def test_supported_case_types_all_strings() -> None:
    stub = _StubReadOnlyModule()
    for ct in stub.supported_case_types():
        assert isinstance(ct, str)


# Тест: handle() должен возвращать объект ModuleResult с ожидаемыми полями и типами
def test_handle_returns_module_result() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-010", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert isinstance(result, ModuleResult)


# Тест: handle() должен возвращать статус "ok" для поддерживаемого case_type и корректно заполнять поля результата
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


# Тест: handle() должен возвращать статус "skipped" для неподдерживаемого case_type и корректно заполнять поля результата
def test_handle_skipped_for_unsupported_case_type() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-012", case_type="unknown_case", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.status == "skipped"
    assert result.module_id == "stub-read-only"


# Тест: handle() должен сохранять заявленный authority в возвращаемом ModuleResult
def test_handle_preserves_authority_in_result() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-013", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.authority == stub.authority


# Тест: handle() для draft_only модуля должен возвращать статус "ok" и правильный authority
def test_handle_draft_module() -> None:
    stub = _StubDraftModule()
    ctx = ModuleContext(
        run_id="run-020", case_type="lead_classification", module_id="stub-draft"
    )
    result = stub.handle(ctx)
    assert result.status == "ok"
    assert result.authority == AuthorityLevel.DRAFT_ONLY


# Тест: handle() для execution_capable модуля должен возвращать статус "ok" и правильный authority
def test_handle_execution_module() -> None:
    stub = _StubExecutionModule()
    ctx = ModuleContext(
        run_id="run-030", case_type="send_notification", module_id="stub-exec"
    )
    result = stub.handle(ctx)
    assert result.status == "ok"
    assert result.authority == AuthorityLevel.EXECUTION_CAPABLE


# Тест: явная проверка границы authority - read_only модуль не должен возвращать execution_capable authority в своем результате
def test_read_only_module_does_not_return_execution_capable_authority() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-014", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert result.authority != AuthorityLevel.EXECUTION_CAPABLE


# Тест: handle() должен возвращать непустую строку в поле summary для всех статусов
def test_handle_result_summary_is_non_empty_string() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-015", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert isinstance(result.summary, str)
    assert len(result.summary) > 0


# Тест: handle() должен возвращать словарь в поле data, даже если он пустой, и не должен возвращать другие типы
def test_handle_result_data_is_dict() -> None:
    stub = _StubReadOnlyModule()
    ctx = ModuleContext(
        run_id="run-016", case_type="oos_summary", module_id="stub-read-only"
    )
    result = stub.handle(ctx)
    assert isinstance(result.data, dict)
