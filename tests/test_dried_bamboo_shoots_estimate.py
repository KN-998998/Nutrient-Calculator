from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_dried_bamboo_shoots_have_traceable_complete_estimated_profile():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")

    profile = repository.find(name="幹筍絲")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == (
        177,
        15.8,
        1.2,
        0.2,
        0,
        15,
        1,
        50,
    )
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "health.udn.com" in profile.source_url
    assert "可利用碳水按总碳水32g减膳食纤维17g得15g" in repository.correction_notes["幹筍絲"]
    assert "估值" in repository.correction_notes["幹筍絲"]

    result = calculate_recipe(
        Recipe("乾筍絲測試菜", (IngredientAmount("幹筍絲", 28.35),)),
        repository,
    )
    assert result.status == "review"
    assert result.unmatched_ingredients == []
    assert result.nutrients_per_serving["energy_kcal"] == pytest.approx(177 * 0.2835)
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(50 * 0.2835)
