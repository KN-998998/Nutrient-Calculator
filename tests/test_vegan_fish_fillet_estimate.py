from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_vegan_fish_fillet_uses_official_brand_label_average():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find("", "素魚柳")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert all(getattr(profile, field) is not None for field in REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 284
    assert profile.protein_g == 16.75
    assert profile.total_fat_g == 14.2
    assert profile.saturated_fat_g == 6.5
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 22.25
    assert profile.sugars_g == 2.85
    assert profile.sodium_mg == 594.5
    assert "vegefarm.com.tw" in profile.source_url
    assert "vegue.me" in profile.source_url
    assert "松珍" in repository.correction_notes["素魚柳"]
    assert "VEGUE" in repository.correction_notes["素魚柳"]
    assert "待復核" in repository.correction_notes["素魚柳"]
