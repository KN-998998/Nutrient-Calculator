from pathlib import Path

import pytest

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"
SEPTEMBER_SOP_INGREDIENTS = (
    "五柳",
    "五柳菜",
    "(濕)炸支竹",
    "百合",
    "包仔豆腐",
    "大利 火腿片 2磅/包",
    "豆腐乾",
    "豆乾",
    "鰻魚粒",
    "素雞",
    "素牛肉碎",
    "素肉絲",
    "素鴨",
    "蒜蓉（沙师弟）",
    "油麵",
)


@pytest.mark.parametrize("ingredient_name", SEPTEMBER_SOP_INGREDIENTS)
def test_september_sop_ingredient_has_all_eight_nutrients(ingredient_name, repository):
    profile = repository.find(name=ingredient_name)

    assert profile is not None, f"{ingredient_name} has no matched nutrient profile"
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)


def test_september_soy_shreds_use_tvp_reference_not_soy_chicken(repository):
    profile = repository.find(name="素肉絲")

    assert profile is not None
    assert profile.energy_kcal == 329.64
    assert profile.protein_g == 50.33
    assert "TVP" in profile.source
    assert "待復核" in repository.correction_notes["素肉絲"]


def test_september_vegetarian_duck_has_traceable_label_estimates(repository):
    profile = repository.find(name="素鴨")

    assert profile is not None
    assert profile.saturated_fat_g == 1.38
    assert profile.trans_fat_g == 0.0
    assert profile.sugars_g == 2.97
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "vegelink.com" in profile.source_url
    assert "cheerfullinks.com" in profile.source_url
    assert "tjinstoko.eu" in profile.source_url
    assert "待復核" in repository.correction_notes["素鴨"]


def test_dali_ham_keeps_official_ham_carbohydrate_value(repository):
    profile = repository.find(name="大利 火腿片 2磅/包")

    assert profile is not None
    assert profile.available_carbohydrate_g == 4.9


def test_eel_cubes_use_average_of_traceable_cooked_eel_labels(repository):
    profile = repository.find(name="鰻魚粒")

    assert profile is not None
    assert profile.energy_kcal == pytest.approx(264.0)
    assert profile.protein_g == pytest.approx(20.6)
    assert profile.total_fat_g == pytest.approx(16.0)
    assert profile.saturated_fat_g == pytest.approx(4.1)
    assert profile.trans_fat_g == 0.0
    assert profile.available_carbohydrate_g == pytest.approx(9.4)
    assert profile.sugars_g == pytest.approx(8.3)
    assert profile.sodium_mg == pytest.approx(477.0)
    assert profile.source_type == "manual_estimate"
    assert "sea-chicken.com.tw/product/" in profile.source_url
    assert "freemart.com.tw/product/product_info/15300" in profile.source_url
    assert "平均" in repository.correction_notes["鰻魚粒"]


def test_packaged_tofu_fills_cfc_missing_fields_from_plain_firm_tofu_labels(repository):
    profile = repository.find(name="包仔豆腐")

    assert profile is not None
    assert profile.saturated_fat_g == pytest.approx(0.595238, abs=1e-6)
    assert profile.trans_fat_g == 0.0
    assert profile.sugars_g == pytest.approx(0.588235, abs=1e-6)
    assert profile.sodium_mg == pytest.approx(8.683473, abs=1e-6)
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "traderjoes.com" in profile.source_url
    assert "heb.com" in profile.source_url
    assert "待复核" in repository.correction_notes["包仔豆腐"]


def test_september_vegetarian_beef_mince_uses_comparable_product_labels(repository):
    profile = repository.find(name="素牛肉碎")

    assert profile is not None
    assert profile.energy_kcal == 234.8
    assert profile.protein_g == 17.05
    assert profile.total_fat_g == 14.6
    assert profile.saturated_fat_g == 2.85
    assert profile.trans_fat_g == 0.0
    assert profile.available_carbohydrate_g == 8.8
    assert profile.sugars_g == 3.6
    assert profile.sodium_mg == 830.5
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "Products_detail/59" in profile.source_url
    assert "Products_detail/48" in profile.source_url
    assert "待复核" in repository.correction_notes["素牛肉碎"]


def test_september_soy_chicken_fills_cfs_missing_fields_from_product_labels(repository):
    profile = repository.find(name="素雞")

    assert profile is not None
    assert profile.energy_kcal == 191.7
    assert profile.protein_g == 16.5
    assert profile.total_fat_g == 12.5
    assert profile.saturated_fat_g == 3.4
    assert profile.trans_fat_g == 0.0
    assert profile.sugars_g == 3.6
    assert profile.sodium_mg == 373.8
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "food_id=0502000315220" in profile.source_url
    assert "Products_detail/47" in profile.source_url
    assert "Products_detail/48" in profile.source_url
    assert "Products_detail/59" in profile.source_url
    assert any(marker in repository.correction_notes["素雞"] for marker in ("待复核", "待復核"))


def test_september_lily_uses_fresh_cfc_profile_not_dried_labels(repository):
    profile = repository.find(name="百合")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (166.0, 3.2, 0.1, 0.02, 0.0, 37.1, 1.5, 6.7)
    )
    assert profile.source_type == "manual_estimate"
    assert "0503050454090" in profile.source_food_id
    assert "鮮百合" in repository.correction_notes["百合"]
    assert "125g/盒" in repository.correction_notes["百合"]


def test_count_suffixed_fish_cake_duplicate_has_all_eight_nutrients(repository):
    profile = repository.find(name="栗米墨魚餅2個")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.sugars_g == pytest.approx(2.45)
    assert profile.sodium_mg == pytest.approx(497.5)


def test_quantity_only_one_piece_cell_stays_blocked(repository):
    assert repository.find(name="1個") is None


def test_official_source_types_map_to_expected_match_tiers():
    from nutrition_tool.models import NutrientProfile
    from nutrition_tool.repository import source_match_tier

    assert source_match_tier(NutrientProfile(source_type="cfs_official")) == "hong_kong_official"
    assert source_match_tier(NutrientProfile(source_type="china_food_composition")) == "fallback_cfc"


def test_pizza_piece_weight_uses_sop_180g_spec():
    import json

    payload = json.loads((DATA / "portion_estimates.json").read_text(encoding="utf-8"))
    item = next(item for item in payload["items"] if item["name"] == "披薩")

    assert item["grams_per_unit"] == 180.0
    assert "180G/個" in item["note"]


@pytest.fixture(scope="module")
def repository():
    return NutrientRepository.from_csv(
        DATA / "ingredient_nutrients.csv",
        [DATA / "ingredient_nutrients_cfc_fallback.csv"],
        DATA / "sop_alias_mapping.csv",
    )
