from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_chestnut_uses_complete_mean_of_two_hong_kong_ready_to_eat_labels():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")

    profile = repository.find("", "板栗")

    assert profile is not None
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 200.36
    assert profile.protein_g == 4.65
    assert profile.total_fat_g == 1.5
    assert profile.saturated_fat_g == 0
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 41.95
    assert profile.sugars_g == 9.55
    assert profile.sodium_mg == 38.5
    assert "四洲熟制甘栗" in profile.source
    assert "有機甘栗仁" in profile.source
    assert "pns.hk" in profile.source_url
    assert "livesmart.com.hk/ZO0831" in profile.source_url
    assert "待復核" in repository.correction_notes["板栗"]
