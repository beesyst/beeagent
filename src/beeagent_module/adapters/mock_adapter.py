from __future__ import annotations

from pathlib import Path
from typing import Any

from beeagent_module.domain.models import (
    SKU,
    RunMeta,
    SalesRow,
    ShelfSignal,
    StockRow,
    Store,
)
from beeagent_module.mock.dataset import load_mock_dataset


class MockAdapter:
    def __init__(self, storage_dir: Path, dataset_id: str) -> None:
        self._storage_dir = storage_dir
        self._dataset_id = dataset_id
        self._loaded: dict[str, Any] | None = None

    @property
    def dataset_id(self) -> str:
        return self._dataset_id

    def _dataset_path(self) -> Path:
        return self._storage_dir / "mock" / self._dataset_id / "dataset.json"

    def _load(self) -> dict[str, Any]:
        if self._loaded is None:
            self._loaded = load_mock_dataset(self._dataset_path())
        return self._loaded

    def get_catalog(self) -> tuple[list[Store], list[SKU]]:
        loaded = self._load()
        return loaded.get("stores", []), loaded.get("skus", [])

    def get_meta(self) -> RunMeta:
        loaded = self._load()
        return loaded["meta"]

    def get_stock(self) -> list[StockRow]:
        loaded = self._load()
        return loaded.get("stock", [])

    def get_shelf_signals(self) -> list[ShelfSignal]:
        loaded = self._load()
        return loaded.get("shelf_signals", [])

    def get_sales(self) -> list[SalesRow]:
        loaded = self._load()
        return loaded.get("sales", [])

    def get_planogram(self) -> list[Any]:
        return []

    def get_photosignal(self) -> list[Any]:
        return []
