from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_unbranded_thirteen_spice_uses_complete_comparable_product_label():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find("", "十三香")

    assert profile is not None
    assert profile.energy_kcal == 382
    assert profile.protein_g == 9.8
    assert profile.total_fat_g == 7.8
    assert profile.saturated_fat_g == 0
    assert profile.trans_fat_g == 0
    assert profile.available_carbohydrate_g == 68.2
    assert profile.sugars_g == 2.04
    assert profile.sodium_mg == 64
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "新光十三香25g" in repository.correction_notes["十三香"]
    assert "每份" in repository.correction_notes["十三香"]
