"""dish_export 推断逻辑回归测试(双agent审查修复: 素类/牛奶/豆腐/公式注入)。"""
import unittest

from nutrition_tool.dish_export import (
    _detect_category_and_protein,
    _detect_side_dishes,
    _detect_staple,
    _excel_safe,
)
from nutrition_tool.models import IngredientAmount


def _ings(*names: str) -> list:
    return [IngredientAmount(ingredient_name=n, grams=10) for n in names]


class DishExportInferenceTests(unittest.TestCase):
    def test_vegetarian_not_misclassified(self):
        """素肉片/素牛肉片/素雞絲 → 素類(修复前误判为荤)。"""
        for dish, ings in [
            ("素肉片炒翠玉瓜", ["素肉片", "翠玉瓜", "油", "鹽"]),
            ("素牛肉片炆薯仔", ["素牛肉片", "薯仔", "油"]),
            ("素雞絲炒菜心", ["素雞絲", "菜心", "油"]),
        ]:
            category, _ = _detect_category_and_protein(_ings(*ings), dish)
            self.assertEqual(category, "素類", f"{dish} → {category}")

    def test_milk_not_beef(self):
        """牛奶/牛乳 → 奶類(修复前误判为牛肉)。"""
        category, protein = _detect_category_and_protein(
            _ings("牛奶", "雞蛋", "糖"), "香草牛奶燉蛋"
        )
        self.assertEqual(category, "奶類", f"实际: {category}")
        self.assertEqual(protein, "牛奶")

    def test_egg_precedes_chicken(self):
        category, _ = _detect_category_and_protein(_ings("雞蛋", "飯"), "雞蛋炒飯")
        self.assertEqual(category, "蛋類")

    def test_staple_detection(self):
        self.assertEqual(_detect_staple(_ings("雞絲", "意粉", "白汁")), "意粉")
        self.assertEqual(_detect_staple(_ings("雞蛋", "飯")), "飯")

    def test_tofu_not_side_dish(self):
        """麻婆豆腐: 豆腐是主食材, 不应进配菜。"""
        side = _detect_side_dishes(_ings("豆腐", "豬肉碎", "辣醬"))
        self.assertNotIn("豆腐", side)

    def test_vegetables_still_detected(self):
        side = _detect_side_dishes(_ings("牛肉", "翠玉瓜", "油"))
        self.assertIn("翠玉瓜", side)

    def test_excel_safe_formula_injection(self):
        self.assertEqual(_excel_safe("=SUM(A1)"), "'=SUM(A1)")
        self.assertEqual(_excel_safe("+cmd"), "'+cmd")
        self.assertEqual(_excel_safe("-1"), "'-1")
        self.assertEqual(_excel_safe("@import"), "'@import")
        self.assertEqual(_excel_safe("正常菜名"), "正常菜名")
        self.assertEqual(_excel_safe(123), 123)


if __name__ == "__main__":
    unittest.main()
