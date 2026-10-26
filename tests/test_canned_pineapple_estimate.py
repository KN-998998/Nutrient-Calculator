from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_sop_canned_pineapple_uses_drained_canned_reference_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for code, name in (("HK0-3361", "菠蘿粒"), ("HK0-3361", "菠蘿粒（新豐）[大罐裝]")):
        profile = repository.find(code, name)
        assert profile is not None
        assert profile.energy_kcal == 58.078394
        assert profile.protein_g == 0
        assert profile.total_fat_g == 0
        assert profile.saturated_fat_g == 0
        assert profile.trans_fat_g == 0
        assert profile.available_carbohydrate_g == 14.2
        assert profile.sugars_g == 14.2
        assert profile.sodium_mg == 1
        assert profile.source_type == "reference_other"
        assert "AFCD3_F006708" in profile.source_food_id
        assert "AFCD3_F006712" in profile.source_food_id
        assert not set(profile.missing_nutrients) & {
            "energy_kcal", "protein_g", "total_fat_g", "saturated_fat_g",
            "trans_fat_g", "available_carbohydrate_g", "sugars_g", "sodium_mg",
        }

        result = calculate_recipe(
            Recipe("罐頭菠蘿小菜", (IngredientAmount(name, 28.35, code),)), repository
        )
        assert result.status == "review"
        assert result.nutrients_per_serving["sugars_g"] == pytest.approx(14.2 * 0.2835)
