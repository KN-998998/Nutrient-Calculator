"""gen_mock_sop 生成器回归测试 —— 锁定拟真数据的结构契约与营养库匹配率。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from gen_mock_sop import generate  # noqa: E402

from nutrition_tool.repository import NutrientRepository  # noqa: E402
from nutrition_tool.sop import read_sop_workbook  # noqa: E402


class GenMockSopTests(unittest.TestCase):
    def test_generates_standard_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "mock.xlsx"
            stats = generate(out)
            self.assertEqual(len(stats["sheets"]), 5)  # A-E 餐
            self.assertGreaterEqual(stats["dishes"], 30)
            self.assertGreaterEqual(stats["ingredients"], 200)
            self.assertEqual(stats["unmatched_names"], [])  # 全部食材在库内

            recipes, errors = read_sop_workbook(out)
            self.assertEqual(len(recipes), stats["dishes"])
            self.assertEqual(errors, [])

            repo = NutrientRepository.from_csv(
                Path(__file__).resolve().parent.parent / "data" / "ingredient_nutrients.csv"
            )
            from nutrition_tool.calculator import calculate_recipe

            for recipe in recipes:
                result = calculate_recipe(recipe, repo)
                self.assertEqual(
                    result.unmatched_ingredients, [],
                    f"{recipe.recipe_name} 存在未匹配食材",
                )


if __name__ == "__main__":
    unittest.main()
