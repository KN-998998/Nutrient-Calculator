from pathlib import Path

import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import NutrientRepository


DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.mark.parametrize("name", ["豬頸肉", "豬頸肉片"])
def test_raw_pork_neck_uses_same_cut_official_reference_but_roasted_stays_distinct(name):
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name=name)

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (206, 18.3, 14.8, 5.3, 0, 0.1, 0.1, 59)
    )
    assert not set(REQUIRED_NUTRIENT_FIELDS) & set(profile.missing_nutrients)
    assert profile.source_url == "https://www.matvaretabellen.no/en/pork-neck-chops-raw/"
    assert "去骨" in repository.correction_notes[name]

    result = calculate_recipe(Recipe("豬頸肉小菜", (IngredientAmount(name, 100),)), repository)
    assert result.status == "review"
    assert result.nutrients_per_serving["total_fat_g"] == pytest.approx(14.8)



def test_roasted_pork_neck_uses_cooked_reference_not_raw_profile():
    repository = NutrientRepository.from_csv(DATA / "ingredient_nutrients.csv")
    profile = repository.find(name="燒豬頸肉")

    assert profile is not None
    assert tuple(getattr(profile, field) for field in REQUIRED_NUTRIENT_FIELDS) == pytest.approx(
        (271, 26.7, 18.2, 6.5, 0, 0.1, 0.1, 79)
    )
    assert profile.source_url == "https://www.matvaretabellen.no/en/pork-neck-chops-roasted-without-fat/"
    assert "熟重" in repository.correction_notes["燒豬頸肉"]
    assert "調味" in repository.correction_notes["燒豬頸肉"]
    assert repository.find(name="豬頸肉").energy_kcal != profile.energy_kcal
