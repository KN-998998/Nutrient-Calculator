from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_raw_beef_dice_uses_complete_composite_beef_reference():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("", "牛肉粒")

    assert profile is not None
    assert profile.source_food_id == "NZ2024_M1220"
    assert profile.energy_kcal == 179
    assert profile.protein_g == 20
    assert profile.total_fat_g == 11
    assert profile.saturated_fat_g == 3.98
    assert profile.trans_fat_g == 0.27
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 48
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
