"""convert_dish_sop 解析器回归测试 —— 锁定配方文本→配料项 的解析行为。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from convert_dish_sop import parse_recipe_text  # noqa: E402


class ParseRecipeTextTests(unittest.TestCase):
    def test_grams_plain(self):
        items = parse_recipe_text("熟米饭180g、牛肋条150g、蒜片15g")
        self.assertEqual([(i.name, i.grams) for i in items],
                         [("熟米饭", 180.0), ("牛肋条", 150.0), ("蒜片", 15.0)])

    def test_paren_grams_takes_precedence(self):
        # 括号克重优先于数量换算
        items = parse_recipe_text("牛肉饼1个（80g）")
        self.assertEqual(items[0].name, "牛肉饼")
        self.assertEqual(items[0].grams, 80.0)

    def test_cooked_weight_note_ignored(self):
        # "干意面70g（煮熟220g）" 取生重 70g, 括号注记不污染解析
        items = parse_recipe_text("干意面70g（煮熟220g）、奶油酱130g")
        self.assertEqual(items[0].name, "干意面")
        self.assertEqual(items[0].grams, 70.0)
        self.assertEqual(items[1].grams, 130.0)

    def test_quantity_default_table(self):
        items = parse_recipe_text("温泉蛋1个")
        self.assertEqual(items[0].name, "温泉蛋")
        self.assertEqual(items[0].grams, 50.0)
        self.assertIn("待人工核验", items[0].note)

    def test_quantity_without_grams_flagged(self):
        items = parse_recipe_text("神秘食材2串")
        self.assertEqual(items[0].name, "神秘食材")
        self.assertIsNone(items[0].grams)
        self.assertIn("待人工核验", items[0].note)

    def test_volume_uses_density(self):
        items = parse_recipe_text("黑糖糖浆30ml")
        self.assertEqual(items[0].grams, 30.0)
        self.assertIn("待人工核验", items[0].note)

    def test_ice_mapped_to_water(self):
        items = parse_recipe_text("冰块180g")
        self.assertEqual(items[0].name, "清水")
        self.assertEqual(items[0].grams, 180.0)


if __name__ == "__main__":
    unittest.main()
