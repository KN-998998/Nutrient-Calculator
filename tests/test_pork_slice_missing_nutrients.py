from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


def test_pork_slice_has_complete_eight_nutrients_with_traceable_estimates():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find("", "豚肉片")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.saturated_fat_g > 0
    assert 0 < profile.trans_fat_g < profile.total_fat_g
    assert profile.sugars_g == 0
    assert "foodstandards.gov.au" in profile.source_url
    assert "AFCD" in repository.correction_notes["豚肉片"]
    assert "待復核" in repository.correction_notes["豚肉片"]


def test_pork_plum_cubes_use_cfs_lean_pork_and_complete_eight_nutrients():
    repository = NutrientRepository.from_csv("data/ingredient_nutrients.csv")
    profile = repository.find("HK0-2004", "梅肉粒")

    assert profile is not None
    assert not set(profile.missing_nutrients).intersection(REQUIRED_NUTRIENT_FIELDS)
    assert profile.available_carbohydrate_g == 1.5
    assert abs(profile.saturated_fat_g - 2.304058) < 0.001
    assert abs(profile.trans_fat_g - 0.0328) < 0.001
    assert profile.sugars_g == 0
    assert "0506060811100" in profile.source_food_id.split(";")
    assert "fc-myreport.php" in profile.source_url
    assert "foodstandards.gov.au" in profile.source_url
    assert "AFCD" in repository.correction_notes["梅肉粒"]
