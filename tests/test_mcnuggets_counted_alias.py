from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from nutrition_tool.repository import NutrientRepository
from nutrition_tool.sop import _estimate_portion_weight


DATA = Path(__file__).resolve().parents[1] / "data"


def test_four_piece_mcnugget_name_uses_average_profile_and_market_piece_weight():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find(name="麥樂雞4块")
    estimated_weight = _estimate_portion_weight(
        recipe_name="熱狗包",
        ingredient_name="麥樂雞4块",
        component_name="",
        count_cell=None,
    )

    assert profile is not None
    assert profile.energy_kcal == 235
    assert profile.source_type == "reference_other"
    assert "NZ2024_N47" in profile.source_food_id
    assert estimated_weight is not None
    assert estimated_weight[0] == 80

    result = calculate_recipe(
        Recipe("熱狗包", (IngredientAmount("麥樂雞4块", estimated_weight[0]),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] == 188


def test_eel_profile_uses_comparable_label_average_and_source_links():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("170-0480", "鰻魚粒")

    assert profile is not None
    assert profile.available_carbohydrate_g == 9.4
    assert profile.sugars_g == 8.3
    assert profile.source_type == "manual_estimate"
    assert "sea-chicken.com.tw/product/" in profile.source_url
    assert "freemart.com.tw/product/product_info/15300" in profile.source_url
    assert "available_carbohydrate_g" not in profile.missing_nutrients
