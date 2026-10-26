from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"
PORK_BURGER_NAMES = ("豬柳漢堡扒",)
PORK_BURGER_AVERAGE_PER_100G = (
    265.858416,
    16.544027,
    21.402876,
    7.281264,
    0,
    0.331126,
    0,
    61.772195,
)


def test_pork_burger_uses_average_of_two_product_labels_and_remains_reviewable():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profiles = [repository.find("HK0-1037", name) for name in PORK_BURGER_NAMES]

    assert all(profile is not None for profile in profiles)
    for profile in profiles:
        assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
            PORK_BURGER_AVERAGE_PER_100G
        )
        assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
        assert profile.source_type == "manual_estimate"
        assert "gfsstore.com/products/109151" in profile.source_url
        assert "eatthismuch.com/calories/pork-burgers-1993385" in profile.source_url
        note = repository.correction_notes[normalize_name("豬柳漢堡扒")]
        assert "113.4g" in note and "151g" in note
        assert "待營養師復核" in note

    result = calculate_recipe(
        Recipe("豬柳漢堡扒", (IngredientAmount("豬柳漢堡扒", 113.4, "HK0-1037"),)),
        repository,
    )
    assert result.status == "review"
    assert result.unmatched_ingredients == []
    assert result.nutrients_per_serving["energy_kcal"] == pytest.approx(
        PORK_BURGER_AVERAGE_PER_100G[0] * 1.134
    )
