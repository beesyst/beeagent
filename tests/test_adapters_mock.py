from pathlib import Path

from beeagent_module.adapters.factory import get_adapter
from beeagent_module.adapters.mock_adapter import MockAdapter
from beeagent_module.mock.dataset import generate_mock_dataset, save_mock_dataset


def test_get_adapter_returns_mock_adapter(tmp_path: Path) -> None:
    dataset = generate_mock_dataset(
        seed=42,
        weeks=1,
        stores=1,
        skus=2,
        category="Vitamins",
    )
    dataset_id = dataset["meta"]["dataset_id"]
    save_mock_dataset(dataset, tmp_path)

    settings = {
        "data": {
            "adapter": "mock",
            "mock": {"dataset_id": dataset_id},
        }
    }

    adapter = get_adapter(settings=settings, storage_dir=tmp_path)
    assert isinstance(adapter, MockAdapter)


def test_mock_adapter_reads_catalog_and_stock(tmp_path: Path) -> None:
    dataset = generate_mock_dataset(
        seed=11,
        weeks=1,
        stores=2,
        skus=3,
        category="Vitamins",
    )
    dataset_id = dataset["meta"]["dataset_id"]
    save_mock_dataset(dataset, tmp_path)

    adapter = MockAdapter(storage_dir=tmp_path, dataset_id=dataset_id)

    stores, skus = adapter.get_catalog()
    stock = adapter.get_stock()
    shelf_signals = adapter.get_shelf_signals()
    sales = adapter.get_sales()

    assert len(stores) == 2
    assert len(skus) == 3
    assert len(stock) > 0
    assert len(shelf_signals) > 0
    assert len(sales) > 0
    assert adapter.get_planogram() == []
    assert adapter.get_photosignal() == []
