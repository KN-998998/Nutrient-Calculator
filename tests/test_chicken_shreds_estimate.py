from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("雞絲", "HK0-2518"),
        ("雞絲", "HK0-3519"),
        ("去皮雞絲", "HK0-2518"),
        ("去皮雞絲", "HK0-1438"),
    ],
)
def test_unspecified_raw_chicken_shreds_use_breast_thigh_average_for_review(name, code):
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(code, name)

    assert profile is not None
    assert profile.energy_kcal == 108.5
    assert profile.protein_g == 19.7
    assert profile.total_fat_g == 3.25
    assert profile.saturated_fat_g == 0.975
    assert profile.trans_fat_g == 0.015
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 98
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "reference_other"
    assert "NZ2024_M10007" in profile.source_food_id
    assert "NZ2024_M10013" in profile.source_food_id
    assert "部位" in repository.correction_notes[normalize_name(name)]

    result = calculate_recipe(
        Recipe("雞絲測試", (IngredientAmount(name, 85.05, code),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_100g is not None
