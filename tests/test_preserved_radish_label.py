from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unbranded_preserved_radish_uses_complete_official_comparable_label():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")

    profile = repository.find(name="菜脯")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == (
        43,
        2,
        0,
        0,
        0,
        8.7,
        3.9,
        3000,
    )
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "yifeng-food.com.tw" in profile.source_url
    assert "品牌" in repository.correction_notes["菜脯"]
    assert "待復核" in repository.correction_notes["菜脯"]

    result = calculate_recipe(
        Recipe("菜脯炒蛋", (IngredientAmount("菜脯", 14.175),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(425.25)
    assert result.nutrients_per_serving["sugars_g"] == pytest.approx(0.552825)
