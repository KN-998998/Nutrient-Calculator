from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


NUTRIENT_FIELDS = (
    "energy_kcal",
    "protein_g",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "available_carbohydrate_g",
    "sugars_g",
    "sodium_mg",
    "dietary_fibre_g",
)

# 香港营养标签的八项；纤维保留为辅助数据，不单独阻断八项计算。
REQUIRED_NUTRIENT_FIELDS = NUTRIENT_FIELDS[:8]
CALCULATION_RULE_VERSION = "nutrition.rules.v1"


@dataclass(frozen=True)
class NutrientProfile:
    """每 100 克可食用部分的营养值。"""

    ingredient_code: str = ""
    ingredient_name: str = ""
    aliases: tuple[str, ...] = ()
    energy_kcal: float = 0.0
    protein_g: float = 0.0
    total_fat_g: float = 0.0
    saturated_fat_g: float = 0.0
    trans_fat_g: float = 0.0
    available_carbohydrate_g: float = 0.0
    sugars_g: float = 0.0
    sodium_mg: float = 0.0
    dietary_fibre_g: float = 0.0
    edible_fraction: float = 1.0
    yield_factor: float = 1.0
    retention_factor: float = 1.0
    source: str = ""
    source_food_id: str = ""
    carb_uncertain: bool = False  # True = 碳水口径待核验(如 CFC 纤维缺失未换算)
    source_type: str = "unknown"
    source_url: str = ""
    source_date: str = ""
    missing_nutrients: tuple[str, ...] = ()
    is_zero_nutrient: bool = False


@dataclass(frozen=True)
class IngredientAmount:
    ingredient_name: str
    grams: float
    ingredient_code: str = ""
    component_name: str = ""
    edible_fraction: float | None = None
    yield_factor: float | None = None
    retention_factor: float | None = None
    source_row: int | None = None
    weight_is_estimated: bool = False
    weight_estimate_note: str = ""


@dataclass(frozen=True)
class Recipe:
    recipe_name: str
    ingredients: tuple[IngredientAmount, ...]
    meal_set: str = ""
    school_stage: str = ""
    service_date: str = ""
    cooked_weight_g: float | None = None
    source_sheet: str = ""
    calculation_standard: str = "hong_kong"
    parse_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class IngredientContribution:
    ingredient_code: str
    ingredient_name: str
    source_name: str
    input_weight_g: float
    edible_weight_g: float
    cooked_weight_g: float
    nutrients: dict[str, float]
    source_row: int | None = None
    source_type: str = "unknown"
    source_food_id: str = ""
    source: str = ""
    source_url: str = ""
    match_tier: str = "unknown"
    source_label: str = "來源待確認"
    requires_review: bool = True
    missing_nutrients: tuple[str, ...] = ()
    weight_is_estimated: bool = False
    weight_estimate_note: str = ""


@dataclass
class RecipeResult:
    recipe_name: str
    meal_set: str
    service_date: str
    source_sheet: str
    input_weight_g: float
    edible_weight_g: float
    estimated_cooked_weight_g: float
    nutrients_per_serving: dict[str, float]
    nutrients_per_100g: dict[str, float] | None
    macro_energy_kcal: float
    energy_difference_kcal: float
    energy_difference_percent: float | None
    status: str
    warnings: list[str] = field(default_factory=list)
    input_errors: list[str] = field(default_factory=list)
    unmatched_ingredients: list[dict[str, Any]] = field(default_factory=list)
    contributions: list[IngredientContribution] = field(default_factory=list)
    school_stage: str = ""
    calculation_standard: str = "hong_kong"
    calculation_rule_version: str = CALCULATION_RULE_VERSION

    def to_dict(self, digits: int | None = 4) -> dict[str, Any]:
        data = asdict(self)
        if digits is None:
            return data

        def rounded(value: Any) -> Any:
            if isinstance(value, float):
                return round(value, digits)
            if isinstance(value, dict):
                return {key: rounded(item) for key, item in value.items()}
            if isinstance(value, list):
                return [rounded(item) for item in value]
            return value

        return rounded(data)
