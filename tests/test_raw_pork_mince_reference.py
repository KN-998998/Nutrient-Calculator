from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_raw_minced_pork_uses_matching_official_reference_pending_purchase_check():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-0416", "免治豬肉")

    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == (178.776291, 20.9, 10.6, 4, 0.07049, 0, 0, 58)
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_food_id == "AFCD3_F007057"
    assert profile.source_url.endswith("/afcd/search/food/F007057")
    assert profile.source_type == "reference_other"

    result = calculate_recipe(
        Recipe("墨西哥肉醬", (IngredientAmount("免治豬肉", 127.575, "HK0-0416"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["protein_g"] == pytest.approx(26.663175)
