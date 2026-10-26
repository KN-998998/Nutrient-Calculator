from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_giant_tree_honey_syrup_uses_matching_retail_label_and_marks_derivations():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find("", "(大膠桶)百花蜜糖(巨樹牌)")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 330
    assert profile.protein_g == 0
    assert profile.total_fat_g == 0
    assert profile.saturated_fat_g == 0
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 82.5
    assert profile.sugars_g == 71.1
    assert profile.sodium_mg == 0
    assert "orientalmart.co.uk" in profile.source_url
    note = repository.correction_notes["大膠桶百花蜜糖巨樹牌"]
    assert "330" in note and "71.1" in note
    assert "反式脂肪" in note and "推算" in note
    assert "待復核" in note
