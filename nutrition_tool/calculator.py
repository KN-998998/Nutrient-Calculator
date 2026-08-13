from __future__ import annotations

import math

from .models import (
    IngredientContribution,
    NUTRIENT_FIELDS,
    Recipe,
    RecipeResult,
)
from .repository import NutrientRepository


def _valid_factor(value: float, label: str, allow_over_one: bool = False) -> None:
    maximum = 10.0 if allow_over_one else 1.0
    if not 0 <= value <= maximum:
        raise ValueError(f"{label} 必须在 0 到 {maximum:g} 之间，当前为 {value}")


def calculate_recipe(
    recipe: Recipe,
    repository: NutrientRepository,
    *,
    energy_warning_threshold: float = 0.05,
) -> RecipeResult:
    totals = {field: 0.0 for field in NUTRIENT_FIELDS}
    input_weight = 0.0
    edible_weight = 0.0
    estimated_cooked_weight = 0.0
    contributions: list[IngredientContribution] = []
    unmatched: list[dict[str, object]] = []
    warnings: list[str] = []
    carb_uncertain_names: list[str] = []

    for ingredient in recipe.ingredients:
        if not math.isfinite(ingredient.grams):
            raise ValueError(f"食材 {ingredient.ingredient_name} 的克重必须是有限数值, 当前为 {ingredient.grams!r}")
        if ingredient.grams < 0:
            raise ValueError(f"食材 {ingredient.ingredient_name} 的克重不能为负数")
        input_weight += ingredient.grams
        profile = repository.find(ingredient.ingredient_code, ingredient.ingredient_name)
        if profile is None:
            unmatched.append(
                {
                    "ingredient_code": ingredient.ingredient_code,
                    "ingredient_name": ingredient.ingredient_name,
                    "grams": ingredient.grams,
                    "source_row": ingredient.source_row,
                }
            )
            continue

        edible_fraction = ingredient.edible_fraction if ingredient.edible_fraction is not None else profile.edible_fraction
        yield_factor = ingredient.yield_factor if ingredient.yield_factor is not None else profile.yield_factor
        retention = ingredient.retention_factor if ingredient.retention_factor is not None else profile.retention_factor
        _valid_factor(edible_fraction, "可食率")
        _valid_factor(yield_factor, "熟重得率", allow_over_one=True)
        _valid_factor(retention, "营养保留率")

        edible = ingredient.grams * edible_fraction
        cooked = edible * yield_factor
        nutrients = {
            field: edible / 100.0 * getattr(profile, field) * retention
            for field in NUTRIENT_FIELDS
        }
        edible_weight += edible
        estimated_cooked_weight += cooked
        if profile.carb_uncertain:
            carb_uncertain_names.append(ingredient.ingredient_name)
        for field, value in nutrients.items():
            totals[field] += value
        contributions.append(
            IngredientContribution(
                ingredient_code=ingredient.ingredient_code or profile.ingredient_code,
                ingredient_name=ingredient.ingredient_name,
                source_name=profile.ingredient_name,
                input_weight_g=ingredient.grams,
                edible_weight_g=edible,
                cooked_weight_g=cooked,
                nutrients=nutrients,
                source_row=ingredient.source_row,
            )
        )

    macro_energy = (
        totals["protein_g"] * 4
        + totals["total_fat_g"] * 9
        + totals["available_carbohydrate_g"] * 4
    )
    database_energy = totals["energy_kcal"]
    energy_difference = database_energy - macro_energy
    energy_percent = abs(energy_difference) / database_energy if database_energy else None

    if totals["sugars_g"] > totals["available_carbohydrate_g"] + 1e-9:
        warnings.append("糖高于可利用碳水化合物，请复核食材营养值。")
    if totals["saturated_fat_g"] + totals["trans_fat_g"] > totals["total_fat_g"] + 1e-9:
        warnings.append("饱和脂肪与反式脂肪之和高于总脂肪。")
    if energy_percent is not None and energy_percent > energy_warning_threshold:
        warnings.append(
            f"数据库能量与 4-9-4 宏量能量相差 {energy_percent:.1%}，超过 {energy_warning_threshold:.0%}。"
        )
    if unmatched:
        warnings.append(f"有 {len(unmatched)} 项食材未匹配营养数据库。")
    if carb_uncertain_names:
        warnings.append(
            "以下食材碳水口径待核验(CFC 纤维缺失未换算): " + "、".join(carb_uncertain_names[:5])
            + (" 等" if len(carb_uncertain_names) > 5 else "")
        )

    final_weight = recipe.cooked_weight_g or estimated_cooked_weight
    per_100g = None
    if final_weight > 0:
        per_100g = {field: value / final_weight * 100 for field, value in totals.items()}

    if unmatched:
        status = "incomplete"
    elif warnings:
        status = "review"
    else:
        status = "passed"

    # 有未匹配食材时, 每 100g 结果不可用(分母缺少未匹配食材的熟重)
    if unmatched:
        per_100g = None

    return RecipeResult(
        recipe_name=recipe.recipe_name,
        meal_set=recipe.meal_set,
        service_date=recipe.service_date,
        source_sheet=recipe.source_sheet,
        input_weight_g=input_weight,
        edible_weight_g=edible_weight,
        estimated_cooked_weight_g=estimated_cooked_weight,
        nutrients_per_serving=totals,
        nutrients_per_100g=per_100g,
        macro_energy_kcal=macro_energy,
        energy_difference_kcal=energy_difference,
        energy_difference_percent=energy_percent,
        status=status,
        warnings=warnings,
        unmatched_ingredients=unmatched,
        contributions=contributions,
    )
