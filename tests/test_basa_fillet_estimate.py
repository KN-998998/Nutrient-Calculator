from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_white_box_longli_fillet_uses_traceable_frozen_basa_label_average():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name="300+龍利柳(白盒)")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (65.5344, 14.4885, 1.3817, 0.4408, 0, 0, 0, 292.9389),
        abs=0.001,
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "manual_estimate"
    assert "eatthismuch.com/calories/basa-fillet-1784583" in profile.source_url
    assert "nutritionvalue.org/public_ingredient_60247.html" in profile.source_url
    note = repository.correction_notes[normalize_name("300+龍利柳(白盒)")]
    assert "nutritionvalue.org/public_ingredient_60247.html" in note
    assert "保水处理" in note

    result = calculate_recipe(
        Recipe("龍利柳測試", (IngredientAmount("300+龍利柳(白盒)", 100),)),
        repository,
    )
    assert result.status == "review"
    assert not result.unmatched_ingredients
    assert result.nutrients_per_serving["sodium_mg"] == pytest.approx(292.9389)
