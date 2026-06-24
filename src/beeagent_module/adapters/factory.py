from __future__ import annotations

from pathlib import Path

from beeagent_module.adapters.base import DataAdapter
from beeagent_module.adapters.mock_adapter import MockAdapter


def get_adapter(
    settings: dict,
    storage_dir: Path,
    dataset_id: str | None = None,
) -> DataAdapter:
    adapter_name = settings["data"]["adapter"]

    if adapter_name == "mock":
        resolved_dataset_id = dataset_id or settings.get("data", {}).get(
            "mock", {}
        ).get("dataset_id")
        if not resolved_dataset_id:
            raise RuntimeError("data.mock.dataset_id is required for mock adapter")
        return MockAdapter(storage_dir=storage_dir, dataset_id=resolved_dataset_id)

    raise RuntimeError(f"Unsupported data.adapter: {adapter_name}")
