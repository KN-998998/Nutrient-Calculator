from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_fish_siu_mai_keeps_hong_kong_profile_and_estimates_only_missing_fields():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    for name in ("魚蓉燒賣", "魚蓉燒賣4個"):
        profile = repository.find("HK0-0644", name)
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
        ) == (200, 11, 13, 3.7, 0, 10, 2.7, 746.2)
        assert profile.source_type == "reference_other"
        assert "doll.com.hk" in profile.source_url
        assert "sunlokoutlet.com" in profile.source_url
        assert "FRL" in repository.correction_notes[normalize_name(name)]

    result = calculate_recipe(
        Recipe("魚蓉燒賣小菜", (IngredientAmount("魚蓉燒賣", 2000 / 140 * 4, "HK0-0644"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] > 0
