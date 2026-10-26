from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_black_truffle_oil_uses_traceable_100g_product_label_instead_of_mushroom_profile():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find("", "黑松露油")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 885.2772466539196
    assert profile.protein_g == 0
    assert profile.total_fat_g == 98.3
    assert profile.saturated_fat_g == 13.7
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert profile.sodium_mg == 0
    assert "pns.hk" in profile.source_url
    assert "黑松露味橄欖油" in repository.correction_notes["黑松露油"]
    assert "SOP" in repository.correction_notes["黑松露油"]
