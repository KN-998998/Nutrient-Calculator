from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_pearl_chicken_keeps_hk_values_and_marks_trans_fat_proxy():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    profile = repository.find("HK0-1474", "珍珠雞")

    assert profile is not None
    assert profile.energy_kcal == 220
    assert profile.protein_g == 6.4
    assert profile.trans_fat_g == 0
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert "mynetdiary.com" in profile.source_url
    assert "tasteasianfood.com" in profile.source_url
    assert "暫估" in repository.correction_notes["珍珠雞"]
