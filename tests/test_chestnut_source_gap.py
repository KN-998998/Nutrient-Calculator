from pathlib import Path

from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_chestnut_uses_complete_ready_to_eat_hong_kong_label_estimate():
    repository = NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
    chestnut = repository.find(name="板栗")

    assert chestnut is not None
    assert chestnut.saturated_fat_g == 0
    assert chestnut.trans_fat_g == 0
    assert chestnut.sugars_g == 9.55
    assert chestnut.missing_nutrients == ()
    assert "BP_117233" in chestnut.source_url
    assert "livesmart.com.hk/ZO0831" in chestnut.source_url
