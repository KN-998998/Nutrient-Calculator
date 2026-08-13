from __future__ import annotations

import csv
from pathlib import Path

from .models import NUTRIENT_FIELDS, Recipe


NUTRIENT_DATABASE_HEADERS = [
    "ingredient_code",
    "ingredient_name",
    "aliases",
    *NUTRIENT_FIELDS,
    "edible_fraction",
    "yield_factor",
    "retention_factor",
    "source",
    "source_food_id",
]


def write_database_template(recipes: list[Recipe], path: str | Path) -> int:
    unique: dict[tuple[str, str], dict[str, object]] = {}
    for recipe in recipes:
        for item in recipe.ingredients:
            key = (item.ingredient_code.upper(), item.ingredient_name)
            unique.setdefault(
                key,
                {
                    "ingredient_code": item.ingredient_code,
                    "ingredient_name": item.ingredient_name,
                    "aliases": "",
                    **{field: "" for field in NUTRIENT_FIELDS},
                    "edible_fraction": 1,
                    "yield_factor": 1,
                    "retention_factor": 1,
                    "source": "香港食安中心/供应商标签/实验室",
                    "source_food_id": "",
                },
            )
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=NUTRIENT_DATABASE_HEADERS)
        writer.writeheader()
        writer.writerows(unique.values())
    return len(unique)
