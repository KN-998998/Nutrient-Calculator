from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_orange_concentrate_uses_undiluted_reference_not_ready_to_drink_juice():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    concentrate = repository.find("HK0-3568", "濃縮橙汁")

    assert concentrate is not None
    assert concentrate.energy_kcal == 148
    assert concentrate.total_fat_g == 0.25
    assert concentrate.trans_fat_g == 0
    assert concentrate.available_carbohydrate_g == 34.2
    assert concentrate.sugars_g == 29.7
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(concentrate.missing_nutrients)
    assert "169923" in concentrate.source_url
