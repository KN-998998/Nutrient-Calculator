from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unspecified_doubanjiang_estimates_unreported_fields_from_comparable_labels():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )

    profile = repository.find("REVIEW_202609_0047", "豆辦醬")

    assert profile is not None
    # Original CFC values remain the source for nutrients it reported.
    assert profile.energy_kcal == 181
    assert profile.protein_g == 13.6
    assert profile.total_fat_g == 6.8
    assert profile.available_carbohydrate_g == 17.1
    assert profile.sodium_mg == 6012
    # Means from two labelled chilli-bean-sauce products, normalized to 100 g.
    assert profile.saturated_fat_g == pytest.approx((3.0 + 0.2) / 2)
    assert profile.trans_fat_g == 0
    assert profile.sugars_g == pytest.approx((13.0 + 2.4) / 2)
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_type == "manual_estimate"
    assert "辣豆瓣酱240g" in repository.correction_notes["豆辦醬"]
    assert "鵑城牌郫县一级豆瓣酱" in repository.correction_notes["豆辦醬"]
