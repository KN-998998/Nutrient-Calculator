from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_chinese_yam_uses_same_species_reference_for_missing_fields():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("HK0-2229", "淮山肉 <切角>")

    assert profile is not None
    assert profile.energy_kcal == 57  # Preserve the existing CFC identity.
    assert profile.protein_g == 1.9
    assert profile.saturated_fat_g == pytest.approx(0.1 / 4.2)
    assert profile.trans_fat_g == 0
    assert profile.sugars_g == pytest.approx(1.3 / 4.2)
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "moleq.com" in profile.source_url
    assert "myfooddata.com" in profile.source_url
    assert "估算" in repository.correction_notes["淮山肉切角"]
