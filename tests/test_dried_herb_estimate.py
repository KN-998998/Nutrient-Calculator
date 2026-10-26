from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_generic_herb_uses_traceable_dried_herb_average_and_requires_review():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find("HK0-3574", "香草")

    assert profile is not None
    assert profile.source_type == "manual_estimate"
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert "171328" in profile.source_url
    assert "171317" in profile.source_url

    result = calculate_recipe(
        Recipe("香草菜式", (IngredientAmount("香草", 1, "HK0-3574"),)),
        repository,
    )

    assert not result.unmatched_ingredients
    assert result.status == "review"
    assert abs(result.nutrients_per_serving["available_carbohydrate_g"] - 0.18235) < 1e-12
