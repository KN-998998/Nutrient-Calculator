from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_yulian_sesame_oil_fills_only_unreported_fields_from_pure_oil_labels():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find("HK0-3218", "4X5L 玉蓮麻油 (紅蓋)")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (898, 0, 99.7, 2 / 14 * 100, 0, 0.2, 0, 1.1)
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "nowfoods.com" in profile.source_url
    assert "heb.com" in profile.source_url
    assert "非玉蓮" in repository.correction_notes["4x5l玉蓮麻油紅蓋"]
