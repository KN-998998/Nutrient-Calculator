from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_vegetarian_beef_steak_uses_traceable_complete_brand_label_reference():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name="素牛扒")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (216.6, 19.1, 12.2, 2.31, 0, 7.6, 4.5, 867),
        abs=0.001,
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "manual_estimate"
    assert "foreverhealth.com.tw/tw/Products_detail/48" in profile.source_url
    note = repository.correction_notes[normalize_name("素牛扒")]
    assert "SOP未確認採購品牌" in note
    assert "待營養師按實物標籤覆核" in note

    result = calculate_recipe(
        Recipe("素牛扒測試", (IngredientAmount("素牛扒", 100),)),
        repository,
    )
    assert result.status == "review"
    assert not result.unmatched_ingredients
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(867)
