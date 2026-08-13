import csv
import tempfile
import unittest
from pathlib import Path

from nutrition_tool.repository import NutrientRepository, normalize_name

HEADERS = [
    "ingredient_code", "ingredient_name", "aliases", "energy_kcal", "protein_g",
    "total_fat_g", "saturated_fat_g", "trans_fat_g", "available_carbohydrate_g",
    "sugars_g", "sodium_mg", "dietary_fibre_g", "edible_fraction", "yield_factor",
    "retention_factor", "source", "source_food_id",
]


def _write_csv(path: Path, rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class RepositoryTests(unittest.TestCase):
    def test_carb_uncertain_only_when_fibre_truly_missing(self):
        """纤维已知=0(纯物质)不算待核验; 纤维真缺失(空)才算; 非CFC来源不标。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            base = {
                "ingredient_code": "T1", "ingredient_name": "純糖", "aliases": "",
                "energy_kcal": "400", "protein_g": "0", "total_fat_g": "0",
                "saturated_fat_g": "0", "trans_fat_g": "0", "available_carbohydrate_g": "99.9",
                "sugars_g": "99.9", "sodium_mg": "0", "dietary_fibre_g": "0",
                "edible_fraction": "1", "yield_factor": "1", "retention_factor": "1",
                "source": "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)",
                "source_food_id": "x",
            }
            rows = [
                dict(base),  # CFC + 纤维=0 → 不算待核验
                {**base, "ingredient_code": "T2", "ingredient_name": "缺纖維肉",
                 "dietary_fibre_g": "", "available_carbohydrate_g": "2.9"},  # CFC + 纤维空 → 待核验
                {**base, "ingredient_code": "T3", "ingredient_name": "澳牛",
                 "source": "澳洲新西蘭食品標準管理局", "dietary_fibre_g": ""},  # 非CFC → 不标
                {**base, "ingredient_code": "T4", "ingredient_name": "低碳水",
                 "available_carbohydrate_g": "0.5", "dietary_fibre_g": ""},  # CFC + 碳水<1 → 不标
            ]
            _write_csv(path, rows)
            repo = NutrientRepository.from_csv(path)
            by_code = {p.ingredient_code: p for p in repo.profiles}
            self.assertFalse(by_code["T1"].carb_uncertain, "纤维=0 纯物质不应待核验")
            self.assertTrue(by_code["T2"].carb_uncertain, "纤维真缺失应待核验")
            self.assertFalse(by_code["T3"].carb_uncertain, "非CFC来源不待核验")
            self.assertFalse(by_code["T4"].carb_uncertain, "碳水≤1 不待核验")

    def test_water_matches_without_code(self):
        """清水/水 无编码按名称应命中(营养库4行同名不歧义), 不污染菜式状态。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            base = {
                "ingredient_code": "W1", "ingredient_name": "清水", "aliases": "",
                "energy_kcal": "0", "protein_g": "0", "total_fat_g": "0",
                "saturated_fat_g": "0", "trans_fat_g": "0", "available_carbohydrate_g": "0",
                "sugars_g": "0", "sodium_mg": "0", "dietary_fibre_g": "0",
                "edible_fraction": "1", "yield_factor": "1", "retention_factor": "1",
                "source": "水(无营养)", "source_food_id": "",
            }
            rows = [
                dict(base),
                {**base, "ingredient_code": "W2"},
                {**base, "ingredient_code": "W3"},
            ]
            _write_csv(path, rows)
            repo = NutrientRepository.from_csv(path)
            self.assertIsNotNone(repo.find("", "清水"), "清水无编码应命中")
            self.assertIsNotNone(repo.find("", "水"), "水无编码应命中")

    def test_normalization(self):
        self.assertEqual(normalize_name("翠玉瓜（切半圓片）"), normalize_name("翠玉瓜 <切半圓片>"))

    def test_code_precedes_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            _write_csv(path, [{
                "ingredient_code": "A1", "ingredient_name": "鸡肉", "aliases": "雞肉|鸡块",
                "energy_kcal": 100, "edible_fraction": 1, "yield_factor": 1,
                "retention_factor": 1,
            }])
            repo = NutrientRepository.from_csv(path)
            self.assertEqual(repo.find("A1", "错误名称").ingredient_name, "鸡肉")
            self.assertEqual(repo.find(name="雞肉").ingredient_code, "A1")

    def test_duplicate_code_resolved_by_name(self):
        """重复编码必须按名称消歧：DTL0084 输入鹽 应命中盐而非咖喱砖。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            _write_csv(path, [
                {"ingredient_code": "DTL0084", "ingredient_name": "鹽/25KG 幼鹽",
                 "energy_kcal": 0, "sodium_mg": 39000, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
                {"ingredient_code": "DTL0084", "ingredient_name": "地捫茄汁",
                 "energy_kcal": 85, "sodium_mg": 37.1, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
                {"ingredient_code": "DTL0084", "ingredient_name": "日式咖哩磚",
                 "energy_kcal": 180, "sodium_mg": 210, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
            ])
            repo = NutrientRepository.from_csv(path)
            match = repo.find("DTL0084", "鹽")
            self.assertIsNotNone(match)
            self.assertEqual(match.ingredient_name, "鹽/25KG 幼鹽")
            self.assertEqual(match.sodium_mg, 39000)

    def test_duplicate_code_ambiguous_returns_none(self):
        """重复编码且名称无法唯一确认时返回 None，禁止猜测。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            _write_csv(path, [
                {"ingredient_code": "DTL0084", "ingredient_name": "鹽/25KG 幼鹽",
                 "energy_kcal": 0, "sodium_mg": 39000, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
                {"ingredient_code": "DTL0084", "ingredient_name": "地捫茄汁",
                 "energy_kcal": 85, "sodium_mg": 37.1, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
                {"ingredient_code": "DTL0084", "ingredient_name": "日式咖哩磚",
                 "energy_kcal": 180, "sodium_mg": 210, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
            ])
            repo = NutrientRepository.from_csv(path)
            self.assertIsNone(repo.find("DTL0084", ""))       # 无名称 → 歧义
            self.assertIsNone(repo.find("DTL0084", "未知食材"))  # 名称不匹配 → 歧义

    def test_name_contains_fallback(self):
        """无编码时按名称包含匹配：鹽 应命中 鹽/25KG 幼鹽。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            _write_csv(path, [
                {"ingredient_code": "DTL0084", "ingredient_name": "鹽/25KG 幼鹽",
                 "energy_kcal": 0, "sodium_mg": 39000, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
                {"ingredient_code": "DTL0084", "ingredient_name": "日式咖哩磚",
                 "energy_kcal": 180, "sodium_mg": 210, "edible_fraction": 1,
                 "yield_factor": 1, "retention_factor": 1},
            ])
            repo = NutrientRepository.from_csv(path)
            match = repo.find(name="鹽")
            self.assertIsNotNone(match)
            self.assertEqual(match.sodium_mg, 39000)

    def test_ambiguous_name_returns_none(self):
        """多候选且名称无法消歧时返回 None。"""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "db.csv"
            _write_csv(path, [
                {"ingredient_code": "A1", "ingredient_name": "薯角",
                 "energy_kcal": 100, "edible_fraction": 1, "yield_factor": 1,
                 "retention_factor": 1},
                {"ingredient_code": "A2", "ingredient_name": "薯角",
                 "energy_kcal": 200, "edible_fraction": 1, "yield_factor": 1,
                 "retention_factor": 1},
            ])
            repo = NutrientRepository.from_csv(path)
            self.assertIsNone(repo.find(name="薯角"))


if __name__ == "__main__":
    unittest.main()
