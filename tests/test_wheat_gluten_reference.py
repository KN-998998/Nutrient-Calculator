from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_wheat_gluten_uses_hong_kong_cfs_reference_and_stays_reviewable():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("", "麵筋")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (358, 75.2, 0, 0, 0, 13.2, 0, 29)
    )
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "reference_other"
    assert "bowtie.com.hk" in profile.source_url
    note = repository.correction_notes[normalize_name("麵筋")]
    assert "香港食物安全中心" in note
    assert "SOP未註明" in note
    assert "低置信度" in note

    result = calculate_recipe(
        Recipe("甜酸齋", (IngredientAmount("麵筋", 100),)), repository
    )
    assert result.status == "review"
    assert not result.unmatched_ingredients
    assert result.nutrients_per_serving["protein_g"] == pytest.approx(75.2)
