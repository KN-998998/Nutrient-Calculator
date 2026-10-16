from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import CALCULATION_RULE_VERSION, NUTRIENT_FIELDS, RecipeResult


def export_json(results: list[RecipeResult], path: str | Path, digits: int = 4) -> None:
    payload = [result.to_dict(digits=digits) for result in results]
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_summary_csv(results: list[RecipeResult], path: str | Path) -> None:
    headers = [
        "service_date",
        "meal_set",
        "school_stage",
        "recipe_name",
        "status",
        "calculation_rule_version",
        "input_weight_g",
        "edible_weight_g",
        "estimated_cooked_weight_g",
        *NUTRIENT_FIELDS,
        "macro_energy_kcal",
        "energy_difference_percent",
        "unmatched_count",
        "warnings",
    ]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for result in results:
            row = {
                "service_date": result.service_date,
                "meal_set": result.meal_set,
                "school_stage": result.school_stage,
                "recipe_name": result.recipe_name,
                "status": result.status,
                "calculation_rule_version": result.calculation_rule_version or CALCULATION_RULE_VERSION,
                "input_weight_g": result.input_weight_g,
                "edible_weight_g": result.edible_weight_g,
                "estimated_cooked_weight_g": result.estimated_cooked_weight_g,
                "macro_energy_kcal": result.macro_energy_kcal,
                "energy_difference_percent": result.energy_difference_percent,
                "unmatched_count": len(result.unmatched_ingredients),
                "warnings": " | ".join(result.warnings),
                **{
                    field: "" if result.status == "incomplete" else result.nutrients_per_serving.get(field, "")
                    for field in NUTRIENT_FIELDS
                },
            }
            writer.writerow(row)
