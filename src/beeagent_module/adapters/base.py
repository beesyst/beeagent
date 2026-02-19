from __future__ import annotations

from typing import Any, Protocol

from beeagent_module.domain.models import SKU, SalesRow, ShelfSignal, StockRow, Store


# Базовый интерфейс адаптера данных для кейса OOS
class DataAdapter(Protocol):
    def get_catalog(self) -> tuple[list[Store], list[SKU]]: ...

    def get_stock(self) -> list[StockRow]: ...

    def get_shelf_signals(self) -> list[ShelfSignal]: ...

    def get_sales(self) -> list[SalesRow]: ...

    def get_planogram(self) -> list[Any]: ...

    def get_photosignal(self) -> list[Any]: ...
