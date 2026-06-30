from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from beeagent_module.core.module_contract import (
    AuthorityLevel,
    ModuleContract,
    ModuleResult,
)
from beeagent_module.core.module_registry import ModuleRegistry
from beeagent_module.core.module_runtime import execute_module_case
from beeagent_module.core.settings import load_settings

os.environ.setdefault("BEEAGENT_WEB_SESSION_SECRET", "test-session-secret")
os.environ.setdefault("BEEAGENT_WEB_ADMIN1_TOKEN", "test-admin1-token")
os.environ.setdefault("BEEAGENT_WEB_ADMIN2_TOKEN", "test-admin2-token")


def _null_logger() -> logging.Logger:
    logger = logging.getLogger("test_rop_module_integration_null")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _rop_registry_entry_from_settings() -> dict:
    settings = load_settings(_project_root() / "config" / "settings.yml")
    entries = settings["modules"]["registry"]

    for item in entries:
        if item["id"] == "beeagent-rop":
            assert item["enabled"] is True
            return item

    raise AssertionError("modules.registry must contain enabled beeagent-rop")


def test_rop_registry_entry_loaded_and_marked_valid(tmp_path: Path) -> None:
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    loaded_ids = registry.loaded_ids()
    assert loaded_ids == ["beeagent-rop"]

    module = registry.get("beeagent-rop")
    assert module is not None
    assert isinstance(module, ModuleContract)
    assert "lead_classification" in module.supported_case_types()

    registry.write_diagnostics_artifact(tmp_path)

    diagnostics_path = tmp_path / "interfaces" / "modules.json"
    assert diagnostics_path.exists()

    data = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert data["registry"][0]["id"] == "beeagent-rop"
    assert data["registry"][0]["state"] == "loaded"


def test_execute_module_case_with_rop_writes_module_linked_artifacts(
    tmp_path: Path,
) -> None:
    rop_entry = _rop_registry_entry_from_settings()
    registry = ModuleRegistry(config=[rop_entry], logger=_null_logger())

    run_id = "run-rop-integration"
    session_id = "session-rop-integration"

    result = execute_module_case(
        registry=registry,
        module_id="beeagent-rop",
        case_type="lead_classification",
        payload={
            "source": "email",
            "sender": "lead@example.com",
            "subject": "Need product details",
            "body": "Please call me back about pricing",
        },
        storage_dir=tmp_path,
        logger=_null_logger(),
        run_id=run_id,
        session_id=session_id,
    )

    assert isinstance(result, ModuleResult)
    assert result.module_id == "beeagent-rop"
    assert result.case_type == "lead_classification"
    assert result.authority == AuthorityLevel.READ_ONLY
    assert result.authority.value == "read_only"

    module_dir = tmp_path / "runs" / run_id / "module-beeagent-rop"
    module_result_path = module_dir / "module_result.json"
    case_result_path = module_dir / "lead_classification_result.json"

    assert module_result_path.exists()
    assert case_result_path.exists()

    module_result = json.loads(module_result_path.read_text(encoding="utf-8"))
    assert module_result["run_id"] == run_id
    assert module_result["session_id"] == session_id
    assert module_result["module_id"] == "beeagent-rop"
    assert module_result["case_type"] == "lead_classification"
    assert module_result["authority"] == "read_only"
