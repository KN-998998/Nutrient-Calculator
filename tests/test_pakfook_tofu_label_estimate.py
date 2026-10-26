from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_pakfook_tofu_uses_firm_tofu_label_as_reviewable_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("VCK0044", "百福豆腐")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (61, 3.5, 4.6, 0.7, 0, 1.2, 0.8, 24)
    )
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_brand_label"
    assert "PNS_133725_PAKFOOK_FIRM_TOFU" == profile.source_food_id
    assert "PNSHK-133725-nutrition-zoom.jpg" in profile.source_url
    assert "假设" in repository.correction_notes["百福豆腐"]
    assert "硬豆腐" in repository.correction_notes["百福豆腐"]

    result = calculate_recipe(
        Recipe("素麻婆豆腐", (IngredientAmount("百福豆腐", 170.1, "VCK0044"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["energy_kcal"] == pytest.approx(61 * 1.701)
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(24 * 1.701)
