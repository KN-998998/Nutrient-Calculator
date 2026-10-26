import math
from pathlib import Path

from nutrition_tool.models import REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


def test_straw_mushroom_fills_only_unreported_nutrients_from_fresh_mushroom_average():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find("", "草菇<切一開二>")

    assert profile is not None
    assert profile.energy_kcal == 27
    assert profile.available_carbohydrate_g == 2.7
    assert profile.dietary_fibre_g == 1.6
    assert math.isclose(profile.saturated_fat_g, (0.08 + 0.03 / 0.7) / 2, abs_tol=1e-9)
    assert math.isclose(profile.trans_fat_g, (0.00352 + 0) / 2, abs_tol=1e-9)
    assert math.isclose(profile.sugars_g, (0 + 2.0) / 2, abs_tol=1e-9)
    assert not set(profile.missing_nutrients) & set(REQUIRED_NUTRIENT_FIELDS)
    assert "cfs.gov.hk" in profile.source_url
    assert "fdc.nal.usda.gov/food-details/169251/nutrients" in profile.source_url
