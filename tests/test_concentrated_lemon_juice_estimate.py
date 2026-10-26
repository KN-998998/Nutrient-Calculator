from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_concentrated_lemon_juice_uses_traceable_bottled_juice_estimate():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find("DTL0039", "濃縮檸檬汁")

    assert profile is not None
    assert profile.source_type == "manual_estimate"
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.energy_kcal == 20.5
    assert profile.sugars_g == 1.505
    assert profile.sodium_mg == 27.5
    assert "167802" in profile.source_url
    assert "167801" in profile.source_url

    result = calculate_recipe(
        Recipe("檸檬汁菜式", (IngredientAmount("濃縮檸檬汁", 100, "DTL0039"),)),
        repository,
    )

    assert not result.unmatched_ingredients
    assert result.status == "review"
