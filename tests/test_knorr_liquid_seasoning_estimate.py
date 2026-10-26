from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize("name", ["家樂牌鮮露", "鮮露"])
def test_knorr_hk_label_retains_six_values_and_estimates_missing_fat_parts(name):
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find(name=name)

    assert profile is not None
    values = tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS)
    assert values == pytest.approx((31, 2, 2, 0.201238, 0, 1.3, 1.2, 7800))
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "KNORR_HK_956641" in profile.source_food_id
    assert "USDA_FDC_174277" in profile.source_food_id
    assert "USDA_FDC_174279" in profile.source_food_id
    assert "2×" in repository.correction_notes[normalize_name(name)]

    result = calculate_recipe(Recipe("鮮露小菜", (IngredientAmount(name, 5.67),)), repository)
    assert result.status == "review"
    assert result.nutrients_per_serving["saturated_fat_g"] == pytest.approx(0.201238 * 0.0567)
