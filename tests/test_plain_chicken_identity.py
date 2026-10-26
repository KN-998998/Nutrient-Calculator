from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_plain_chicken_does_not_use_chicken_rice_nutrients():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find("HK0-2081", "白切雞")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (219, 24.68, 12.56, 3.5, 0.015, 0, 0, 67)
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "171051" in profile.source_url
    assert "白切雞飯" in repository.correction_notes[normalize_name("白切雞")]

    result = calculate_recipe(
        Recipe("白切雞測試", (IngredientAmount("白切雞", 100, "HK0-2081"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["available_carbohydrate_g"] == 0
