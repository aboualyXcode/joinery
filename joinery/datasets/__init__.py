"""Sample datasets: definitions, generation, image building and dialect export."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache

from .generators import analytics, bank, joinlab, pipeline, shop
from .model import Column, Dataset, Index, Table

BUILDERS: dict[str, Callable[[], Dataset]] = {
    "shop": shop.build,
    "bank": bank.build,
    "analytics": analytics.build,
    "pipeline": pipeline.build,
    "joinlab": joinlab.build,
}


def dataset_ids() -> list[str]:
    return list(BUILDERS)


@cache
def get_dataset(dataset_id: str) -> Dataset:
    try:
        builder = BUILDERS[dataset_id]
    except KeyError:
        raise KeyError(f"unknown dataset: {dataset_id}") from None
    return builder()


__all__ = ["BUILDERS", "Column", "Dataset", "Index", "Table", "dataset_ids", "get_dataset"]
