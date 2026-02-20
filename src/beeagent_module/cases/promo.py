from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from beeagent_module.adapters.factory import get_adapter
from beeagent_module.agents.promo.graph import run_promo_workflow
from beeagent_module.mock.dataset import generate_mock_dataset, save_mock_dataset


# Кейс promo: генерация mock-данных и запуск promo workflow
def run_promo_case(
    settings: dict,
    storage_dir: Path,
    logger: logging.Logger,
    trigger: str = "manual",
) -> dict[str, Any]:
    dataset_id = settings["data"]["mock"].get("dataset_id")

    if not dataset_id:
        mock_cfg = settings["mock"]
        dataset = generate_mock_dataset(
            seed=mock_cfg["seed"],
            weeks=mock_cfg["weeks"],
            stores=mock_cfg["stores"],
            skus=mock_cfg["skus"],
            category=mock_cfg["category"],
        )
        save_mock_dataset(dataset=dataset, storage_dir=storage_dir)
        dataset_id = dataset["meta"]["dataset_id"]

    adapter = get_adapter(
        settings=settings,
        storage_dir=storage_dir,
        dataset_id=dataset_id,
    )

    promo_cfg = settings["promo"]
    result = run_promo_workflow(
        storage_dir=storage_dir,
        adapter=adapter,
        adapter_name=settings["data"]["adapter"],
        promo_cfg=promo_cfg,
        trigger=trigger,
        logger=logger,
    )

    return result
