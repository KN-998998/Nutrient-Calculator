from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize(("name", "code"), [
    ("肉眼粒", "MCK0084"),
    ("豬肉眼粒 1.5cm*1.5cm", "HK0-3229"),
])
def test_pork_eye_uses_two_raw_loin_references_with_species_caveat(name, code):
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find(code, name)

    assert profile is not None
    observed = tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS)
    assert observed == pytest.approx(
        (169.8135755, 21.6, 9.3, 3.425, 0.041985, 0, 0, 49.5)
    )
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "reference_other"
    assert "AFCD3_F007037" in profile.source_food_id
    assert "AFCD3_F007030" in profile.source_food_id
    assert "祥記" in repository.correction_notes[normalize_name(name)]

    result = calculate_recipe(Recipe("肉眼粒小菜", (IngredientAmount(name, 85.05, code),)), repository)
    assert result.status == "review"
    assert result.nutrients_per_serving["protein_g"] == pytest.approx(21.6 * 0.8505)
