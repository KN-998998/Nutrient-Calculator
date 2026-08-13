import unittest

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import IngredientAmount, NutrientProfile, Recipe
from nutrition_tool.repository import NutrientRepository


class CalculatorTests(unittest.TestCase):
    def test_weighted_sum_and_energy_check(self):
        repository = NutrientRepository([
            NutrientProfile(
                ingredient_code="RICE",
                ingredient_name="白米饭",
                energy_kcal=130,
                protein_g=2.5,
                total_fat_g=0.3,
                available_carbohydrate_g=28,
                sugars_g=0.1,
                sodium_mg=1,
            ),
            NutrientProfile(
                ingredient_code="CHICKEN",
                ingredient_name="鸡肉",
                energy_kcal=165,
                protein_g=31,
                total_fat_g=3.6,
                saturated_fat_g=1,
                available_carbohydrate_g=0,
                sodium_mg=74,
            ),
        ])
        recipe = Recipe(
            "鸡肉饭",
            (
                IngredientAmount("白米饭", 200, "RICE"),
                IngredientAmount("鸡肉", 100, "CHICKEN"),
            ),
        )
        result = calculate_recipe(recipe, repository)
        self.assertAlmostEqual(result.nutrients_per_serving["energy_kcal"], 425)
        self.assertAlmostEqual(result.nutrients_per_serving["protein_g"], 36)
        self.assertAlmostEqual(result.nutrients_per_serving["available_carbohydrate_g"], 56)
        self.assertEqual(result.status, "passed")

    def test_factors_and_unmatched_status(self):
        repository = NutrientRepository([
            NutrientProfile(
                ingredient_code="FISH",
                ingredient_name="带骨鱼",
                energy_kcal=100,
                protein_g=20,
                edible_fraction=0.8,
                yield_factor=0.75,
                retention_factor=0.9,
            )
        ])
        recipe = Recipe(
            "鱼餐",
            (
                IngredientAmount("带骨鱼", 100, "FISH"),
                IngredientAmount("未知酱料", 10, "UNKNOWN"),
            ),
        )
        result = calculate_recipe(recipe, repository)
        self.assertAlmostEqual(result.edible_weight_g, 80)
        self.assertAlmostEqual(result.estimated_cooked_weight_g, 60)
        self.assertAlmostEqual(result.nutrients_per_serving["protein_g"], 14.4)
        self.assertEqual(result.status, "incomplete")
        self.assertEqual(len(result.unmatched_ingredients), 1)

    def test_rejects_negative_grams(self):
        repository = NutrientRepository([])
        recipe = Recipe("错误", (IngredientAmount("食材", -1),))
        with self.assertRaises(ValueError):
            calculate_recipe(recipe, repository)

    def test_rejects_nan_and_inf_grams(self):
        import math
        repository = NutrientRepository([])
        for bad in (float("nan"), float("inf"), float("-inf")):
            recipe = Recipe("错误", (IngredientAmount("食材", bad),))
            with self.assertRaises(ValueError):
                calculate_recipe(recipe, repository)

    def test_unmatched_sets_per_100g_none(self):
        repository = NutrientRepository([
            NutrientProfile(
                ingredient_code="RICE", ingredient_name="白米饭",
                energy_kcal=130, protein_g=2.5, total_fat_g=0.3,
                available_carbohydrate_g=28,
            )
        ])
        recipe = Recipe(
            "鸡肉饭",
            (
                IngredientAmount("白米饭", 200, "RICE"),
                IngredientAmount("未知食材", 50, "UNKNOWN"),
            ),
        )
        result = calculate_recipe(recipe, repository)
        self.assertEqual(result.status, "incomplete")
        self.assertIsNone(result.nutrients_per_100g)

    def test_carb_uncertain_marks_review(self):
        repository = NutrientRepository([
            NutrientProfile(
                ingredient_code="CFC1", ingredient_name="火腿",
                energy_kcal=200, protein_g=10, total_fat_g=15,
                available_carbohydrate_g=4.9, carb_uncertain=True,
            )
        ])
        recipe = Recipe("火腿飯", (IngredientAmount("火腿", 50, "CFC1"),))
        result = calculate_recipe(recipe, repository)
        self.assertEqual(result.status, "review")
        self.assertTrue(any("碳水口径待核验" in w for w in result.warnings))


if __name__ == "__main__":
    unittest.main()
