import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_black_truffle_sauce_uses_traceable_average_product_labels():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find(name="黑松露醬")

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
    ) == pytest.approx((
        206,
        2.683333333333333,
        21.136666666666667,
        3.066666666666667,
        0,
        1.5066666666666666,
        0.91,
        560,
    ))
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert "papatartufi.com" in profile.source_url
    assert "colledeltartufo.it" in profile.source_url
    assert "bascofinefoods.com" in profile.source_url
    assert "待營養師按實際供應標籤復核" in repository.correction_notes["黑松露醬"]
