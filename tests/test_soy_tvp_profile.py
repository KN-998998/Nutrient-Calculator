from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_soy_mince_uses_complete_dry_tvp_reference_estimate():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")

    profile = repository.find("", "素肉碎")

    assert profile is not None
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 329.64
    assert profile.protein_g == 50.33
    assert profile.total_fat_g == 3.17
    assert profile.saturated_fat_g == 0.5
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 25.67
    assert profile.sugars_g == 5.17
    assert profile.sodium_mg == 13.5
    assert "TVP" in profile.source
    assert "干制" in profile.source
    assert "tastesensationltd.com" in profile.source_url
    assert "forestwholefoods.co.uk" in profile.source_url
    assert "nsm.com.au" in profile.source_url
    assert "待復核" in repository.correction_notes["素肉碎"]
