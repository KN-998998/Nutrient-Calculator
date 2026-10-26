from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_frankfurter_uses_two_traceable_comparable_products():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name="法蘭克福腸")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (285.5, 12.15, 24.65, 8.46, 0.237, 3.73, 2.55, 807)
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "huntsfoodgroup.co.uk" in profile.source_url
    assert "fdc.nal.usda.gov" in profile.source_url
    assert "非SOP採購品" in repository.correction_notes["法蘭克福腸"]
