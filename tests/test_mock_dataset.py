import json
from pathlib import Path

from beeagent_module.domain.models import RunMeta, SalesRow, ShelfSignal, StockRow
from beeagent_module.mock.dataset import (
    generate_mock_dataset,
    load_mock_dataset,
    save_mock_dataset,
)


def test_generate_mock_dataset_is_deterministic() -> None:
    dataset_a = generate_mock_dataset(
        seed=42,
        weeks=4,
        stores=2,
        skus=3,
        category="Vitamins",
    )
    dataset_b = generate_mock_dataset(
        seed=42,
        weeks=4,
        stores=2,
        skus=3,
        category="Vitamins",
    )

    assert dataset_a == dataset_b


def test_save_and_load_mock_dataset(tmp_path: Path) -> None:
    dataset = generate_mock_dataset(
        seed=11,
        weeks=2,
        stores=2,
        skus=2,
        category="Cosmetics",
    )

    dataset_path = save_mock_dataset(dataset=dataset, storage_dir=tmp_path)

    assert dataset_path == (
        tmp_path / "mock" / "seed-11-w2-s2-k2-cosmetics" / "dataset.json"
    )
    assert dataset_path.exists()

    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    assert "meta" in raw
    assert "stores" in raw
    assert "shelf_signals" in raw

    loaded = load_mock_dataset(dataset_path)

    assert isinstance(loaded["meta"], RunMeta)
    assert isinstance(loaded["sales"][0], SalesRow)
    assert isinstance(loaded["stock"][0], StockRow)
    assert isinstance(loaded["shelf_signals"][0], ShelfSignal)


def test_forced_anomalies_exist() -> None:
    dataset = generate_mock_dataset(
        seed=7,
        weeks=3,
        stores=2,
        skus=2,
        category="Vitamins",
    )

    stock_index = {
        (row["date"], row["store_id"], row["sku_id"]): row["stock_on_hand"]
        for row in dataset["stock"]
    }

    anomalies = [
        signal
        for signal in dataset["shelf_signals"]
        if signal["seen_on_shelf"] is False
        and stock_index[(signal["date"], signal["store_id"], signal["sku_id"])] > 0
    ]

    assert 2 <= len(anomalies) <= 5
