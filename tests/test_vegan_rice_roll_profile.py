from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_vegan_rice_roll_uses_retailer_published_brand_label_and_flags_sku_uncertainty():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find("", "健康飯卷")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 153.5
    assert profile.protein_g == 4.8
    assert profile.total_fat_g == 2.15
    assert profile.saturated_fat_g == 0.4
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 30.05
    assert profile.sugars_g == 3.85
    assert profile.sodium_mg == 330.5
    assert "vegue.me/product?pid_for_show=4811" in profile.source_url
    note = repository.correction_notes["健康飯卷"]
    assert "弘陽" in note and "115g" in note
    assert "SOP未提供實際品牌/口味" in note
