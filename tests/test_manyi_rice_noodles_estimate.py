from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_manyi_dry_rice_noodles_have_eight_traceable_values():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("DTL160", "4KG滿姨米粉")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (346, 8, 0.1, 0, 0, 78.3, 0.89, 5.9)
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "2667395" in profile.source_url
    assert "2627855" in profile.source_url
    assert "非滿姨" in repository.correction_notes["4kg滿姨米粉"]
