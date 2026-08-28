from __future__ import annotations

from collections.abc import Callable
from typing import Any

DOCLING_EXTRACTOR = "docling"
XBERG_EXTRACTOR = "xberg"
_IMPLEMENTED_EXTRACTORS = frozenset({DOCLING_EXTRACTOR})
_KNOWN_EXTRACTORS = frozenset({DOCLING_EXTRACTOR, XBERG_EXTRACTOR})


def known_extractor_ids() -> frozenset[str]:
    return _KNOWN_EXTRACTORS


def is_implemented_extractor(extractor_id: str) -> bool:
    return extractor_id in _IMPLEMENTED_EXTRACTORS


def validate_selected_extractor(extractor_id: str) -> None:
    if extractor_id not in _KNOWN_EXTRACTORS:
        raise RuntimeError(f"Unsupported document extractor '{extractor_id}'")
    if not is_implemented_extractor(extractor_id):
        raise RuntimeError(f"document extractor '{extractor_id}' is not implemented")


def worker_converter(extractor_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    if extractor_id != DOCLING_EXTRACTOR:
        raise RuntimeError(f"document extractor '{extractor_id}' is not implemented")
    from beeagent_module.core.docling_reader import convert_blob_item

    return convert_blob_item
