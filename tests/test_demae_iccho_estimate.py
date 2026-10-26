from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_demae_iccho_uses_three_official_bag_flavours_average():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("HK0-3217", "出前一丁")

    assert profile is not None
    expected_per_100g = (461.481481, 10.407407, 20.407407, 13.259259,
                         0, 59.148148, 2.444444, 1493.333333)
    observed = tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS)
    assert observed == pytest.approx(expected_per_100g)
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "reference_other"
    assert all(flavour in profile.source_url for flavour in (
        "chicken-flavour", "pack-five-spice-beef-flavour", "pack-seafood-flavour"
    ))
    assert "口味未註明" in repository.correction_notes["出前一丁"]

    result = calculate_recipe(
        Recipe("即食麵小菜", (IngredientAmount("出前一丁", 100, "HK0-3217"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(1493.333333)
