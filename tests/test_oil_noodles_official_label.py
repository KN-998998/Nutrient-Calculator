from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository
from web_app.app import get_repo


DATA = Path(__file__).resolve().parents[1] / "data"


def test_oil_noodles_use_official_noodle_label_not_fried_gluten():
    repository = get_repo("hong_kong")
    profile = repository.find(name="油麵")

    assert profile is not None
    assert profile.ingredient_name == "油麵"
    assert profile.energy_kcal == 345.9
    assert profile.protein_g == 12.4
    assert profile.total_fat_g == 1.1
    assert profile.saturated_fat_g == 0.4
    assert profile.trans_fat_g == 0.0
    assert profile.available_carbohydrate_g == 71.6
    assert profile.sugars_g == 1.2
    assert profile.sodium_mg == 773.0
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.source_type == "manual_estimate"
    assert "yifeng-food.com.tw/product_d.php" in profile.source_url
    assert "油麵筋" not in profile.aliases
    assert "SOP未提供採購品牌" in repository.correction_notes["油麵"]


def test_fried_gluten_profile_is_not_aliased_as_oil_noodles():
    profile = next(
        item for item in NutrientRepository._load_csv(DATA / "ingredient_nutrients.csv")
        if item.ingredient_code == "VCK0194"
    )

    assert profile is not None
    assert profile.ingredient_name == "油麵筋"
    assert "油麵" not in profile.aliases
