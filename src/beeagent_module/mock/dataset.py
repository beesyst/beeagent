import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

from beeagent_module.domain.models import (
    SKU,
    RunMeta,
    SalesRow,
    ShelfSignal,
    StockRow,
    Store,
)
from beeagent_module.domain.serialization import model_to_dict


# Генерация мокового набора данных
def generate_mock_dataset(
    seed: int,
    weeks: int,
    stores: int,
    skus: int,
    category: str,
) -> dict:
    if weeks <= 0:
        raise ValueError("weeks must be > 0")
    if stores <= 0:
        raise ValueError("stores must be > 0")
    if skus <= 0:
        raise ValueError("skus must be > 0")

    rng = random.Random(seed)
    dataset_id = _build_dataset_id(seed, weeks, stores, skus, category)
    created_at = _build_created_at(seed, weeks, stores, skus)

    store_rows = [
        Store(store_id=f"STORE-{index:03d}", name=f"Store {index}")
        for index in range(1, stores + 1)
    ]

    sku_rows = []
    for index in range(1, skus + 1):
        price = round(rng.uniform(5.0, 40.0), 2)
        margin = round(rng.uniform(0.1, 0.5), 3)
        sku_rows.append(
            SKU(
                sku_id=f"SKU-{index:04d}",
                name=f"{category.title()} SKU {index}",
                category=category,
                price=price,
                margin=margin,
            )
        )

    sales_rows: list[SalesRow] = []
    stock_rows: list[StockRow] = []
    shelf_rows: list[ShelfSignal] = []

    dates = _date_series(weeks)
    for date in dates:
        for store_row in store_rows:
            for sku_row in sku_rows:
                units = rng.randint(0, 9)
                stock_on_hand = rng.randint(0, 20)
                seen_on_shelf = True

                sales_rows.append(
                    SalesRow(
                        date=date,
                        store_id=store_row.store_id,
                        sku_id=sku_row.sku_id,
                        units=units,
                    )
                )
                stock_rows.append(
                    StockRow(
                        date=date,
                        store_id=store_row.store_id,
                        sku_id=sku_row.sku_id,
                        stock_on_hand=stock_on_hand,
                    )
                )
                shelf_rows.append(
                    ShelfSignal(
                        date=date,
                        store_id=store_row.store_id,
                        sku_id=sku_row.sku_id,
                        seen_on_shelf=seen_on_shelf,
                    )
                )

    _force_anomalies(rng, stock_rows, shelf_rows)

    meta = {
        "dataset_id": dataset_id,
        "seed": seed,
        "created_at": created_at,
        "params": {
            "weeks": weeks,
            "stores": stores,
            "skus": skus,
            "category": category,
        },
    }

    return {
        "meta": meta,
        "stores": model_to_dict(store_rows),
        "skus": model_to_dict(sku_rows),
        "sales": model_to_dict(sales_rows),
        "stock": model_to_dict(stock_rows),
        "shelf_signals": model_to_dict(shelf_rows),
    }


# Сохранение мокового набора данных в файл JSON
def save_mock_dataset(dataset: dict, storage_dir: Path) -> Path:
    dataset_id = dataset.get("meta", {}).get("dataset_id")
    if not dataset_id:
        raise RuntimeError("dataset.meta.dataset_id is required")

    dataset_path = storage_dir / "mock" / dataset_id / "dataset.json"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dataset_path


# Загрузка мокового набора данных из файла JSON
def load_mock_dataset(dataset_path: Path) -> dict:
    if not dataset_path.exists():
        raise RuntimeError(f"Dataset file not found: {dataset_path}")

    raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    raw_meta = raw_dataset["meta"]

    return {
        "meta": RunMeta(
            run_id=f"run-{raw_meta['dataset_id']}",
            created_at=raw_meta["created_at"],
            dataset_id=raw_meta["dataset_id"],
            seed=int(raw_meta["seed"]),
        ),
        "stores": [Store(**item) for item in raw_dataset["stores"]],
        "skus": [SKU(**item) for item in raw_dataset["skus"]],
        "sales": [SalesRow(**item) for item in raw_dataset["sales"]],
        "stock": [StockRow(**item) for item in raw_dataset["stock"]],
        "shelf_signals": [ShelfSignal(**item) for item in raw_dataset["shelf_signals"]],
    }


# Генерация идентификатора набора данных
def _build_dataset_id(
    seed: int, weeks: int, stores: int, skus: int, category: str
) -> str:
    safe_category = category.strip().lower().replace(" ", "-")
    return f"seed-{seed}-w{weeks}-s{stores}-k{skus}-{safe_category}"


# Генерация времени создания набора данных
def _build_created_at(seed: int, weeks: int, stores: int, skus: int) -> str:
    seconds = abs(seed * 97 + weeks * 13 + stores * 7 + skus * 3)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return (base + timedelta(seconds=seconds)).isoformat()


# Генерация серии дат для набора данных
def _date_series(weeks: int) -> list[str]:
    total_days = weeks * 7
    start = datetime(2025, 1, 1, tzinfo=UTC)
    return [
        (start + timedelta(days=offset)).date().isoformat()
        for offset in range(total_days)
    ]


# Принудительное добавление аномалий в набор данных
def _force_anomalies(
    rng: random.Random,
    stock_rows: list[StockRow],
    shelf_rows: list[ShelfSignal],
) -> None:
    if not stock_rows:
        return

    anomalies_count = rng.randint(2, 5)
    selected_indexes = rng.sample(
        range(len(stock_rows)),
        k=min(anomalies_count, len(stock_rows)),
    )

    for index in selected_indexes:
        stock = stock_rows[index]
        if stock.stock_on_hand <= 0:
            stock_rows[index] = StockRow(
                date=stock.date,
                store_id=stock.store_id,
                sku_id=stock.sku_id,
                stock_on_hand=1,
            )

        shelf = shelf_rows[index]
        shelf_rows[index] = ShelfSignal(
            date=shelf.date,
            store_id=shelf.store_id,
            sku_id=shelf.sku_id,
            seen_on_shelf=False,
        )
