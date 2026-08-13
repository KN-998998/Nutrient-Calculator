import unittest

from nutrition_tool.models import NutrientProfile
from nutrition_tool.repository import NutrientRepository
from nutrition_tool.service import ContractError, NutritionCalculationService


class NutritionCalculationServiceTests(unittest.TestCase):
    def setUp(self):
        repository = NutrientRepository(
            [
                NutrientProfile(
                    ingredient_code="RICE",
                    ingredient_name="Rice",
                    energy_kcal=130,
                    protein_g=2.7,
                    available_carbohydrate_g=28,
                )
            ]
        )
        self.service = NutritionCalculationService(repository)

    def test_calculates_through_versioned_contract(self):
        response = self.service.calculate(
            {
                "contract_version": "nutrition.calculation.v1",
                "recipe": {
                    "recipe_name": "Rice portion",
                    "ingredients": [
                        {"ingredient_code": "RICE", "ingredient_name": "Rice", "grams": 200}
                    ],
                },
            }
        )

        self.assertEqual(response["contract_version"], "nutrition.calculation.v1")
        self.assertEqual(response["result"]["nutrients_per_serving"]["energy_kcal"], 260)

    def test_rejects_unknown_contract_version(self):
        with self.assertRaises(ContractError):
            self.service.calculate(
                {
                    "contract_version": "nutrition.calculation.v2",
                    "recipe": {"ingredients": [{"ingredient_name": "Rice", "grams": 1}]},
                }
            )


if __name__ == "__main__":
    unittest.main()
