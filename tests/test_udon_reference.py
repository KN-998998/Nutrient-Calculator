from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_packaged_plain_udon_does_not_use_seafood_stir_fry_profile():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("HK0-1659", "30X200G 佳富牌日式烏冬")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (140, 3.5, 0.3, 0, 0, 30.25, 0.2, 125)
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_url == "https://en.sempio.com/product/noodles/view/666"
    assert "非佳富牌" in repository.correction_notes["30x200g佳富牌日式烏冬"]
