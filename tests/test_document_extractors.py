from __future__ import annotations

from pathlib import Path

import pytest

from beeagent_module.core.document_extractors import (
    is_implemented_extractor,
    validate_selected_extractor,
    worker_converter,
)


def test_xberg_is_reserved_but_not_implemented() -> None:
    assert is_implemented_extractor("docling") is True
    assert is_implemented_extractor("xberg") is False


def test_selected_docling_extractor_is_allowed() -> None:
    validate_selected_extractor("docling")


def test_selected_unimplemented_extractor_fails() -> None:
    with pytest.raises(RuntimeError, match="not implemented"):
        validate_selected_extractor("xberg")


def test_unknown_extractor_fails() -> None:
    with pytest.raises(RuntimeError, match="Unsupported"):
        validate_selected_extractor("unknown")


def test_static_registry_does_not_import_docling() -> None:
    source = __import__("inspect").getsource(
        __import__("beeagent_module.core.document_extractors", fromlist=["*"])
    )
    assert "from docling" not in source
    assert "import docling" not in source


def test_xberg_has_no_dependency_or_runtime_adapter() -> None:
    root = Path(__file__).resolve().parents[1]
    assert "xberg" not in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert "xberg" not in (root / "uv.lock").read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="not implemented"):
        worker_converter("xberg")
