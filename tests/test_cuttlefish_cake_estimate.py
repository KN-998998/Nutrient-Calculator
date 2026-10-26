import unittest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, Recipe
from web_app.app import get_repo


class CuttlefishCakeEstimateTests(unittest.TestCase):
    def test_sop_corn_cuttlefish_cake_uses_reviewable_sugar_sodium_average(self):
        repository = get_repo("hong_kong")
        recipe = Recipe(
            recipe_name="栗米墨魚餅菜式",
            ingredients=(IngredientAmount("栗米墨魚餅", 100, "HK0-2148"),),
        )

        result = calculate_recipe(recipe, repository)

        self.assertEqual(result.status, "review")
        self.assertAlmostEqual(result.nutrients_per_serving["sugars_g"], 2.45)
        self.assertAlmostEqual(result.nutrients_per_serving["sodium_mg"], 497.5)
        self.assertEqual(result.contributions[0].missing_nutrients, ("dietary_fibre_g",))
        self.assertTrue(result.contributions[0].requires_review)
        self.assertIn("tungyuenho.com.hk", result.contributions[0].source_url)


if __name__ == "__main__":
    unittest.main()
