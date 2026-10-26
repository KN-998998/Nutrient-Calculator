from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_sop_rice_vermicelli_has_complete_eight_nutrient_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("", "米線")

    assert profile is not None
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.saturated_fat_g == pytest.approx(0)
    assert profile.trans_fat_g == pytest.approx(0)
    assert profile.sugars_g == pytest.approx(0.89)
    assert "tools.myfooddata.com/nutrition-facts/2667395" in profile.source_url
    assert "tools.myfooddata.com/nutrition-facts/2627855" in profile.source_url
    assert "乾品" in profile.source

    result = calculate_recipe(
        Recipe("米线汤", (IngredientAmount("米線", 100),)), repository,
    )
    assert result.status == "review"
    assert not result.unmatched_ingredients
    assert not set(result.contributions[0].missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)


def test_plain_ho_fun_uses_cooked_drained_rice_stick_not_a_complete_dish():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("", "河粉")

    assert profile is not None
    assert profile.energy_kcal == pytest.approx(119.024857)
    assert profile.protein_g == pytest.approx(2.5)
    assert profile.total_fat_g == pytest.approx(0)
    assert profile.available_carbohydrate_g == pytest.approx(26.1)
    assert profile.sodium_mg == pytest.approx(3)
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert "AFCD3_F006038" == profile.source_food_id
