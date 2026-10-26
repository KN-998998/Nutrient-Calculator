from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository, normalize_name


DATA = Path(__file__).resolve().parents[1] / "data"


def test_steamed_pork_patty_uses_raw_pork_proxy_not_crab_cake():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    patty = repository.find("HK0-1669", "肉餅")
    minced_pork_proxy = repository.find(name="肉碎")

    assert patty is not None
    assert minced_pork_proxy is not None
    assert patty.energy_kcal == minced_pork_proxy.energy_kcal
    assert patty.protein_g == minced_pork_proxy.protein_g
    assert patty.trans_fat_g == minced_pork_proxy.trans_fat_g
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(patty.missing_nutrients)
    assert "蟹肉餅" not in patty.aliases
    assert "豬肉" in repository.correction_notes[normalize_name("肉餅")]
