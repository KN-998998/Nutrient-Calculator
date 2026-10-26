import pytest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from web_app.app import get_repo


def test_frozen_gyoza_fills_only_missing_values_from_two_hk_references():
    repository = get_repo("hong_kong")
    profile = repository.find("HK0-2087", "急凍餃子")

    assert profile is not None
    assert profile.energy_kcal == 240
    assert profile.protein_g == 7.7
    assert profile.total_fat_g == 13
    assert profile.saturated_fat_g == 3.3
    assert profile.trans_fat_g == 0.1
    assert profile.available_carbohydrate_g == 23
    assert profile.sugars_g == 2.3375
    assert profile.sodium_mg == 350
    assert profile.source_type == "reference_other"
    assert "doll.com.hk" in profile.source_url
    assert "bowtie.com.hk" in profile.source_url
    assert "等權" in repository.correction_notes["急凍餃子2個"]
    assert not set(profile.missing_nutrients) & {
        "energy_kcal", "protein_g", "total_fat_g", "saturated_fat_g",
        "trans_fat_g", "available_carbohydrate_g", "sugars_g", "sodium_mg",
    }

    result = calculate_recipe(
        Recipe("日式煎餃", (IngredientAmount("急凍餃子", 56.7, "HK0-2087"),)),
        repository,
    )
    assert result.status == "review"
    assert result.nutrients_per_serving["sugars_g"] == pytest.approx(2.3375 * 0.567)
