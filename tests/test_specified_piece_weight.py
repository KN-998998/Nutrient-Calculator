import tempfile
from pathlib import Path

from openpyxl import Workbook

from nutrition_tool.sop import _specified_unit_weight, read_sop_workbook


def test_explicit_per_piece_weight_is_not_an_estimate():
    assert _specified_unit_weight(count_hint="披薩 1个", package_spec="180G/個") == (
        180.0,
        "按SOP規格180G/個×1个",
    )
    assert _specified_unit_weight(count_hint="法蘭克福腸 2條", package_spec="50g/條") == (
        100.0,
        "按SOP規格50g/條×2條",
    )
    assert _specified_unit_weight(count_hint="披薩 1个", package_spec="180G") is None
    assert _specified_unit_weight(count_hint="披薩 1个", package_spec="180G/條") is None


def test_pizza_180g_spec_is_used_as_stated_weight():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "9月A餐配料sop"
    sheet.append([
        "編號/圖片", "套餐", "菜式", "食材/系統名稱", "安士（小學）",
        "人均餐盒實際下單用量（g）（小學）", "安士（中學）",
        "人均餐盒實際下單用量（g）（中學）", "編碼", "規格/單位",
    ])
    sheet.append([46266, "披薩測試", "主菜", "披薩", "1个", "#VALUE!", "", "", "", "180G/個"])
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "pizza.xlsx"
        workbook.save(path)
        workbook.close()
        recipes, errors = read_sop_workbook(path)
    assert not errors
    assert len(recipes) == 2  # one recipe per school stage
    for recipe in recipes:
        ingredient = recipe.ingredients[0]
        assert ingredient.grams == 180.0
        assert ingredient.weight_is_estimated is False
        assert "180G/個" in ingredient.weight_estimate_note
