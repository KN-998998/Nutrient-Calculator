from __future__ import annotations

import math

from .models import (
    IngredientContribution,
    NUTRIENT_FIELDS,
    REQUIRED_NUTRIENT_FIELDS,
    CALCULATION_RULE_VERSION,
    Recipe,
    RecipeResult,
)
from .repository import (
    NutrientRepository,
    source_label,
    source_match_tier,
    source_requires_review,
)


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
    abnormal_oil_names: list[str] = []
    non_hk_source_names: list[str] = []
    manual_source_names: list[str] = []  # 手工/品牌标签录入 → 必须人工复核
    manual_estimate_names: list[str] = []
    brand_label_names: list[str] = []
    missing_nutrient_names: list[str] = []
    estimated_weight_names: list[str] = []

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

        profile_text = " ".join((ingredient.ingredient_name, profile.ingredient_name, *profile.aliases))
        if ingredient.grams > 50 and any(token in profile_text for token in ("油", "麻油", "牛油")):
            abnormal_oil_names.append(f"{ingredient.ingredient_name} ({ingredient.grams:g}g)")

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
        match_tier = source_match_tier(profile)
        profile_source_label = source_label(profile)
        requires_source_review = source_requires_review(profile)
        if requires_source_review:
            non_hk_source_names.append(
                f"{ingredient.ingredient_name}→{profile.ingredient_name}（{profile_source_label}）"
            )
        if "人工补录" in profile.source:
            manual_source_names.append(
                f"{ingredient.ingredient_name}→{profile.ingredient_name}"
            )
        if profile.source_type == "manual_estimate":
            manual_estimate_names.append(ingredient.ingredient_name)
        elif profile.source_type in {"manual_brand_label", "official_brand_label"}:
            brand_label_names.append(ingredient.ingredient_name)
        required_missing = tuple(f for f in profile.missing_nutrients if f in REQUIRED_NUTRIENT_FIELDS)
        if required_missing:
            missing_nutrient_names.append(
                f"{ingredient.ingredient_name}({','.join(required_missing)})"
            )
        if ingredient.weight_is_estimated:
            detail = ingredient.weight_estimate_note or "按件数暂估"
            estimated_weight_names.append(
                f"{ingredient.ingredient_name} {ingredient.grams:g}g（{detail}）"
            )
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
                source_type=profile.source_type,
                source_food_id=profile.source_food_id,
                source=profile.source,
                source_url=profile.source_url,
                match_tier=match_tier,
                source_label=profile_source_label,
                requires_review=requires_source_review,
                missing_nutrients=profile.missing_nutrients,
                weight_is_estimated=ingredient.weight_is_estimated,
                weight_estimate_note=ingredient.weight_estimate_note,
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
    if abnormal_oil_names:
        warnings.append(
            "單項食用油克重超過50g，請核對SOP是否把批量用油誤作每人用量: "
            + "、".join(abnormal_oil_names[:5])
            + (" 等" if len(abnormal_oil_names) > 5 else "")
        )
    if carb_uncertain_names:
        warnings.append(
            "以下食材碳水口径待核验(CFC 纤维缺失未换算): " + "、".join(carb_uncertain_names[:5])
            + (" 等" if len(carb_uncertain_names) > 5 else "")
        )
    if non_hk_source_names:
        warnings.append(
            "香港 CFS/FRL 未命中，以下食材使用非香港后备数据，必须由营养师复核："
            + "、".join(non_hk_source_names[:8])
            + (" 等" if len(non_hk_source_names) > 8 else "")
        )
    if manual_source_names:
        warnings.append(
            "以下食材来自人工补录/品牌营养标签，须核对产品规格后确认："
            + "、".join(manual_source_names[:8])
            + (" 等" if len(manual_source_names) > 8 else "")
        )
    if manual_estimate_names:
        warnings.append(
            "以下食材仅使用通用估算/参考值，不能视为品牌标签的最终值："
            + "、".join(manual_estimate_names[:8])
            + (" 等" if len(manual_estimate_names) > 8 else "")
        )
    if brand_label_names:
        warnings.append(
            "以下食材使用品牌营养标签，提交前请核对 SOP 中的品牌、规格和标签日期："
            + "、".join(brand_label_names[:8])
            + (" 等" if len(brand_label_names) > 8 else "")
        )
    if missing_nutrient_names:
        warnings.append(
            "以下食材未报告的营养项暂按0计入本次计算；0不代表检测或标签确认的零值，待营养师或1+7标签对齐："
            + "、".join(missing_nutrient_names[:8])
            + (" 等" if len(missing_nutrient_names) > 8 else "")
        )
    if estimated_weight_names:
        warnings.append(
            "以下克重按明确件数和暂定单重估算，已计入本次结果；取得实称或供应规格后需替换："
            + "、".join(estimated_weight_names[:8])
            + (" 等" if len(estimated_weight_names) > 8 else "")
        )
    if recipe.parse_warnings:
        warnings.append(
            "SOP 解析不完整，以下原料未能纳入计算："
            + "；".join(recipe.parse_warnings[:5])
            + (" 等" if len(recipe.parse_warnings) > 5 else "")
        )

    final_weight = recipe.cooked_weight_g or estimated_cooked_weight
    per_100g = None
    if final_weight > 0:
        per_100g = {field: value / final_weight * 100 for field, value in totals.items()}

    if unmatched or recipe.parse_warnings:
        status = "incomplete"
    elif warnings or missing_nutrient_names or carb_uncertain_names or estimated_weight_names:
        status = "review"
    else:
        status = "passed"

    # 未匹配或解析不完整的菜品不发布每100g结果；review 暂算值可以供复核。
    if status == "incomplete":
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
        school_stage=recipe.school_stage,
        calculation_standard=recipe.calculation_standard,
        calculation_rule_version=CALCULATION_RULE_VERSION,
    )
