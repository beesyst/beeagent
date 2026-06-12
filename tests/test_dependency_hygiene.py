from __future__ import annotations

import importlib
import warnings


# Соблюдение требований к зависимостям
def test_langchain_core_pydantic_import_has_no_python314_v1_warning() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        importlib.import_module("langchain_core.utils.pydantic")

    messages = [str(item.message) for item in captured]

    assert not any(
        "Core Pydantic V1 functionality isn't compatible with Python 3.14" in message
        for message in messages
    )
