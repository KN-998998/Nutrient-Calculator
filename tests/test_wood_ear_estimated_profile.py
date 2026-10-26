from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"
WOOD_EAR_NAMES = ("木耳", "雲耳", "珍珠雲耳 ( 貓耳朵 )")
WOOD_EAR_PER_100G = (167, 10.28, 0.92, 0.11, 0, 14.21, 0.26, 63)


def test_dtl0108_wood_ear_names_use_reviewable_dried_profile():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profiles = [repository.find("DTL0108", name) for name in WOOD_EAR_NAMES]

    assert all(profile is not None for profile in profiles)
    for profile in profiles:
        assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
            WOOD_EAR_PER_100G
        )
        assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
        assert profile.source_type == "manual_estimate"
        assert "nutritionvalue.org/public_ingredient_48952.html" in profile.source_url

    assert all(
        "乾品" in repository.correction_notes[normalize_name(name)]
        for name in WOOD_EAR_NAMES
    )
    assert all(
        "待營養師復核" in repository.correction_notes[normalize_name(name)]
        for name in WOOD_EAR_NAMES
    )

    result = calculate_recipe(
        Recipe("雲耳蒸雞", (IngredientAmount("雲耳", 8.505, "DTL0108"),)),
        repository,
    )
    assert result.status == "review"
    assert result.unmatched_ingredients == []
    assert result.nutrients_per_serving["energy_kcal"] == pytest.approx(167 * 0.08505)
