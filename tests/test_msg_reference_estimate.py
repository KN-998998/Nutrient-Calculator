from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_pure_msg_uses_disclosed_analogue_for_four_unreported_fields():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-1290", "味精")

    assert profile is not None
    assert profile.energy_kcal == 268
    assert profile.protein_g == 40.1
    assert profile.total_fat_g == 0.2
    assert profile.sodium_mg == 8160
    assert profile.saturated_fat_g == 0
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 0
    assert profile.sugars_g == 0
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "reference_other"
    assert "spicesinc.com/ingredients/msg-monosodium-glutamate" in profile.source_url
    assert "同類估算" in repository.correction_notes[normalize_name("味精")]

    result = calculate_recipe(
        Recipe("味精測試", (IngredientAmount("味精", 2.835, "HK0-1290"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_100g is not None
    assert result.nutrients_per_serving["sodium_mg"] == 231.336
