from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_raw_clam_missing_fields_use_identified_usda_reference_for_review():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("HK0-2708", "蜆肉")

    assert profile is not None
    assert (profile.energy_kcal, profile.protein_g, profile.total_fat_g, profile.sodium_mg) == (
        47, 7, 1.4, 18.4,
    )
    assert profile.saturated_fat_g == pytest.approx(0.187)
    assert profile.trans_fat_g == pytest.approx(0.015)
    assert profile.available_carbohydrate_g == pytest.approx(3.57)
    assert profile.sugars_g == 0
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "174214" in profile.source_url
    assert "物種" in repository.correction_notes["蜆肉"]

    result = calculate_recipe(Recipe("蜆肉小菜", (IngredientAmount("蜆肉", 100, "HK0-2708"),)), repository)
    assert result.status == "review"
    assert result.nutrients_per_serving["trans_fat_g"] == pytest.approx(0.015)
