from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path

from beeagent_module.cases.rop_operator import run_rop_operator_case
from beeagent_module.core.module_contract import (
    AuthorityLevel,
    ModuleContext,
    ModuleResult,
)
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.settings import load_settings


# Тесты для ROP оператора, который запускает модульные кейсы и собирает результаты в едином формате
def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_cases_rop_operator")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


# Вспомогательные функции для тестов ROP оператора
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


# Вспомогательная функция для сбора референсов на артефакты, созданные модульными кейсами, для включения их в summary оператора
def _demo_payload() -> dict[str, str]:
    return {
        "source": "email",
        "sender": "lead@example.com",
        "subject": "Need product details",
        "body": "Please share pricing and delivery terms.",
    }


# Вспомогательная функция для получения конфигурации ROP оператора из settings.yml
def _rop_registry_entry_from_settings() -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    entries = settings["modules"]["registry"]

    for item in entries:
        if item["id"] == "beeagent-rop":
            assert item["enabled"] is True
            return item

    raise AssertionError("modules.registry must contain enabled beeagent-rop")


# Вспомогательные функции для тестов ROP оператора
def _make_fake_package(
    name: str,
    entry_attr: str,
    entry_value: object,
) -> types.ModuleType:
    pkg = types.ModuleType(name)
    setattr(pkg, entry_attr, entry_value)
    sys.modules[name] = pkg
    return pkg


# Вспомогательная функция для удаления фейкового пакета из sys.modules после теста
def _remove_fake_package(name: str) -> None:
    sys.modules.pop(name, None)


# Тест: успешный запуск ROP оператора с установленным модулем и проверка результатов
def test_rop_operator_flow_success_with_installed_module(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    result = run_rop_operator_case(
        settings=settings,
        storage_dir=tmp_path,
        logger=_null_logger(),
        registry=registry,
        payload=_demo_payload(),
        run_id="run-rop-operator-success",
        session_id="session-rop-operator-success",
    )

    assert result["run_id"] == "run-rop-operator-success"
    assert result["module_id"] == "beeagent-rop"
    assert result["case_type"] == "lead_classification"
    assert result["status"] == "ok"
    assert result["module_status"] == "ok"

    run_dir = tmp_path / "runs" / "run-rop-operator-success"
    operator_summary_path = run_dir / "operator_summary.json"
    module_result_path = run_dir / "module-beeagent-rop" / "module_result.json"

    assert operator_summary_path.exists()
    assert module_result_path.exists()

    operator_summary = json.loads(operator_summary_path.read_text(encoding="utf-8"))
    assert operator_summary["status"] == "ok"
    assert (
        "runs/run-rop-operator-success/module-beeagent-rop/module_result.json"
        in operator_summary["artifact_refs"]
    )
    assert (
        "runs/run-rop-operator-success/operator_summary.json"
        in operator_summary["artifact_refs"]
    )


# Тест: запуск ROP оператора без установленного модуля и проверка, что статус оператора становится degraded с ошибкой в summary
def test_rop_operator_flow_degraded_when_module_missing(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    registry = ModuleRegistry(config=[], logger=_null_logger())

    result = run_rop_operator_case(
        settings=settings,
        storage_dir=tmp_path,
        logger=_null_logger(),
        registry=registry,
        payload=_demo_payload(),
        run_id="run-rop-operator-missing",
        session_id="session-rop-operator-missing",
    )

    assert result["run_id"] == "run-rop-operator-missing"
    assert result["status"] == "degraded"
    assert result["module_status"] == "error"
    assert "Module is not loaded or unknown" in result["summary"]

    operator_summary_path = (
        tmp_path / "runs" / "run-rop-operator-missing" / "operator_summary.json"
    )
    assert operator_summary_path.exists()


# Тест: запуск ROP оператора с модулем, который возвращает статус не ok, и проверка, что статус оператора становится degraded
class _StubNonOkModule:
    @property
    def module_id(self) -> str:
        return "stub-non-ok"

    @property
    def authority(self) -> AuthorityLevel:
        return AuthorityLevel.READ_ONLY

    def supported_case_types(self) -> list[str]:
        return ["lead_classification"]

    def handle(self, context: ModuleContext) -> ModuleResult:
        return ModuleResult(
            module_id=self.module_id,
            case_type=context.case_type,
            authority=self.authority,
            status="not_implemented",
            summary="stub non-ok for degraded operator flow",
            data={},
        )


# Тест: запуск ROP оператора с модулем, который возвращает статус не ok, и проверка, что статус оператора становится degraded
def test_rop_operator_flow_degraded_for_non_ok_module_status(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")

    pkg_name = "_test_stub_non_ok_pkg"
    entry_name = "StubNonOkModule"
    _make_fake_package(pkg_name, entry_name, _StubNonOkModule)

    try:
        registry = ModuleRegistry(
            config=[
                {
                    "id": "stub-non-ok",
                    "package": pkg_name,
                    "entry": entry_name,
                    "enabled": True,
                }
            ],
            logger=_null_logger(),
        )

        result = run_rop_operator_case(
            settings=settings,
            storage_dir=tmp_path,
            logger=_null_logger(),
            registry=registry,
            module_id="stub-non-ok",
            payload=_demo_payload(),
            run_id="run-rop-operator-non-ok",
            session_id="session-rop-operator-non-ok",
        )

        assert result["status"] == "degraded"
        assert result["module_status"] == "not_implemented"

        module_result_path = (
            tmp_path
            / "runs"
            / "run-rop-operator-non-ok"
            / "module-stub-non-ok"
            / "module_result.json"
        )
        assert module_result_path.exists()
    finally:
        _remove_fake_package(pkg_name)


# Тест: запуск ROP оператора без payload и проверка, что возникает RuntimeError с сообщением о необходимости payload
def test_rop_operator_raises_when_payload_is_none(tmp_path: Path) -> None:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    registry = ModuleRegistry(config=[], logger=_null_logger())

    try:
        run_rop_operator_case(
            settings=settings,
            storage_dir=tmp_path,
            logger=_null_logger(),
            registry=registry,
            payload=None,
            run_id="run-rop-operator-no-payload",
            session_id="session-rop-operator-no-payload",
        )
        raise AssertionError("RuntimeError expected for missing payload")
    except RuntimeError as exc:
        assert str(exc) == "ROP operator payload is required"
