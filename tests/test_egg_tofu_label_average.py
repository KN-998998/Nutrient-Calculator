import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_egg_tofu_uses_average_of_two_traceable_product_labels():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find(name="玉子豆腐")

    assert profile is not None
    assert (
        profile.energy_kcal,
        profile.protein_g,
        profile.total_fat_g,
        profile.saturated_fat_g,
        profile.trans_fat_g,
        profile.available_carbohydrate_g,
        profile.sugars_g,
        profile.sodium_mg,
    ) == pytest.approx((63, 5.55, 4.1, 1.45, 0, 0.9, 0.1, 186))
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "5060027312765" in profile.source_url
    assert "8888090149425" in profile.source_url
    assert "反式脂肪" in repository.correction_notes["玉子豆腐"]
