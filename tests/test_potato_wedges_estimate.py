from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from web_app.app import get_repo


def test_packaged_potato_wedges_use_sourced_two_profile_average_as_review():
    repository = get_repo("hong_kong")
    profile = repository.find("HK0-2615", "薯角")
    assert profile is not None
    assert profile.energy_kcal == 122
    assert profile.protein_g == 2.175
    assert profile.total_fat_g == 2.9
    assert profile.saturated_fat_g == 0.525
    assert profile.trans_fat_g == 0.025
    assert profile.available_carbohydrate_g == 21.15
    assert profile.sugars_g == 0.6
    assert profile.sodium_mg == 37.5
    assert profile.source_type == "reference_other"
    assert "168443" in profile.source_url
    assert "mccainusafoodservice.com" in profile.source_url
    assert "等權" in repository.correction_notes["薯角"]

    result = calculate_recipe(
        Recipe("薯角菜式", (IngredientAmount("薯角", 100, "HK0-2615"),)),
        repository,
    )
    assert result.status == "review"
    assert result.contributions[0].missing_nutrients == ()
    assert result.contributions[0].requires_review
