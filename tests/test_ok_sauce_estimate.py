from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_ok_sauce_has_eight_traceable_estimated_nutrients():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-1643", "ok汁")

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
    ) == (106, 0.7, 0.25, 0.05, 0, 24, 20, 1200)
    assert profile.source_type == "manual_estimate"
    assert "starrymart.co.uk" in profile.source_url
    assert "nutrition.umd.edu" in repository.correction_notes[normalize_name("ok汁")]
    assert "反式" in repository.correction_notes[normalize_name("ok汁")]
    assert not set(profile.missing_nutrients) & {
        "energy_kcal", "protein_g", "total_fat_g", "saturated_fat_g",
        "trans_fat_g", "available_carbohydrate_g", "sugars_g", "sodium_mg",
    }

    result = calculate_recipe(
        Recipe("甜酸醬小菜", (IngredientAmount("ok汁", 5.67, "HK0-1643"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] == 68.04
