from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def repository():
    return NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )


@pytest.mark.parametrize(("name", "code"), [("肉碎", "HK0-1311"), ("肉粒", "HK0-2004")])
def test_unlabeled_meat_uses_disclosed_pork_average_pending_species_check(repository, name, code):
    profile = repository.find(code, name)

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
    ) == (172.801, 21.367, 9.733, 3.617, 0.05149, 0, 0, 52.333)
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "reference_other"
    assert "AFCD3_F007057" in profile.source_food_id
    assert "豬肉身份待確認" in repository.correction_notes[normalize_name(name)]

    result = calculate_recipe(
        Recipe("肉菜", (IngredientAmount(name, 28.35, code),)), repository
    )
    assert result.status == "review"
    assert result.nutrients_per_100g is not None


def test_chicken_leg_pieces_use_raw_lean_leg_reference_pending_skin_check(repository):
    profile = repository.find("HK0-2518", "雞脾粒")

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
    ) == (117, 18.5, 4.8, 1.4, 0.02132, 0, 0, 71)
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "reference_other"
    assert profile.source_food_id == "070703F002647"
    assert "皮" in repository.correction_notes[normalize_name("雞脾粒")]

    result = calculate_recipe(
        Recipe("雞脾粒菜", (IngredientAmount("雞脾粒", 170.1, "HK0-2518"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_100g is not None
