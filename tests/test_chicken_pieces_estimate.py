from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_sop_chicken_pieces_use_complete_raw_chicken_average_for_review():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("HK0-2518", "雞粒")

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
    ) == (108.5, 19.7, 3.25, 0.975, 0.015, 0, 0, 98)
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "reference_other"
    assert profile.source_food_id == "NZ2024_M10007;NZ2024_M10013"
    assert "部位" in repository.correction_notes[normalize_name("雞粒")]

    result = calculate_recipe(
        Recipe("南瓜汁雞肉", (IngredientAmount("雞粒", 99.225, "HK0-2518"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["protein_g"] == pytest.approx(19.547325)


@pytest.mark.parametrize("name", ["雞塊", "雞塊（沙師弟）"])
def test_unbreaded_sop_chicken_blocks_use_raw_chicken_average_not_nuggets(name):
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name=name)

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (108.5, 19.7, 3.25, 0.975, 0.015, 0, 0, 98)
    )
    assert profile.source_food_id == "NZ2024_M10007;NZ2024_M10013"
    assert "未裹粉" in repository.correction_notes[normalize_name(name)]

    result = calculate_recipe(Recipe("青瓜雞粒", (IngredientAmount(name, 99.225),)), repository)
    assert result.status == "review"
    assert result.nutrients_per_serving["protein_g"] == pytest.approx(19.547325)
    assert profile.energy_kcal != repository.find(name="麥樂雞").energy_kcal
