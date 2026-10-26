from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_chicken_burger_patty_uses_traceable_average_of_frozen_unbreaded_labels():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name="鸡肉漢堡扒")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (120.6995, 17.2690, 5.3736, 0.9691, 0, 0, 0, 235.2448),
        abs=0.001,
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "manual_estimate"
    assert "bubbafoods.com/nutrition/chicken-bubba-burger" in profile.source_url
    assert "thriftyfoods.com/products/compliments-balance-frozen-chicken-burgers" in profile.source_url
    note = repository.correction_notes[normalize_name("鸡肉漢堡扒")]
    assert "非采购品实测值" in note
    assert "营养师按实物标签复核" in note

    result = calculate_recipe(
        Recipe("雞肉漢堡扒測試", (IngredientAmount("鸡肉漢堡扒", 85.05),)),
        repository,
    )
    assert result.status == "review"
    assert not result.unmatched_ingredients
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(200.0757)
