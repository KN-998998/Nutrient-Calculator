"""verify_sep_overlap.py —— 验证 9月菜单与 5/6月 SOP 重叠菜式的计算结果。

流程:
  1. 读 docs/9月菜单_SOP覆盖对照.csv 拿到 9月菜式 → 对应SOP菜谱 的映射(非"无"匹配)
  2. read_sop_workbook 解析 5月/6月 SOP → 提取匹配菜谱(去重)
  3. calculate_recipe 全管线计算 → 状态/营养/未匹配/警告汇总
  4. 输出验证表 + 导出菜式管理 Excel(供打开核对)
"""
from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from nutrition_tool.sop import read_sop_workbook
from nutrition_tool.repository import NutrientRepository
from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.dish_export import write_dish_excel, result_to_dish_row

WORKDIR = Path(__file__).resolve().parent.parent
SOP_FILES = [
    WORKDIR / "菜单+SOP" / "finnal-2026年5月Lunch 學生餐單Menusop 0516.xlsx",
    WORKDIR / "菜单+SOP" / "finnal-2026年6月Lunch 學生餐單Menusop.xlsx",
]


def clean(name: str) -> str:
    name = re.sub(r"[#★●▲□◆※♁◎]", "", name or "")
    name = re.sub(r"[（(][^（）()]*[）)]", "", name)
    return name.strip()


def main() -> int:
    # 1) 对照表 → 需要计算的 SOP 菜谱名
    mapping: dict[str, str] = {}  # sop_clean_name -> 9月菜式
    with (WORKDIR / "docs" / "9月菜单_SOP覆盖对照.csv").open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["匹配"] != "无" and row["对应SOP菜谱"]:
                mapping.setdefault(clean(row["对应SOP菜谱"]), row["9月菜式"])

    # 2) 解析 SOP → 提取匹配菜谱
    repo = NutrientRepository.from_csv(WORKDIR / "data" / "ingredient_nutrients.csv")
    found: dict[str, list] = {}  # clean_name -> [recipes]
    for path in SOP_FILES:
        recipes, errors = read_sop_workbook(path)
        for r in recipes:
            c = clean(r.recipe_name)
            if c in mapping:
                found.setdefault(c, []).append(r)

    # 3) 计算 + 汇总
    print(f"匹配 SOP 菜谱: {len(mapping)} | 在 SOP 中找到: {len(found)}")
    print(f"{'9月菜式':<30}{'SOP菜谱':<28}{'餐':<3}{'配料':<4}{'状态':<11}{'能量':<7}{'蛋白':<6}{'碳水':<7}{'钠':<7}")
    results = []
    status_counter = Counter()
    unmatched_all: Counter = Counter()
    missing_recipes = []
    for cname, sep_dish in mapping.items():
        if cname not in found:
            missing_recipes.append(sep_dish)
            continue
        # 多个月份/多行同名: 取第一个(克重可能不同, 待人工核验), 记录月份
        recipe = found[cname][0]
        res = calculate_recipe(recipe, repo)
        results.append(res)
        status_counter[res.status] += 1
        for u in res.unmatched_ingredients:
            unmatched_all[u["ingredient_name"]] += 1
        n = res.nutrients_per_serving
        print(f"{sep_dish[:28]:<30}{recipe.recipe_name[:26]:<28}{recipe.meal_set:<3}"
              f"{len(recipe.ingredients):<4}{res.status:<11}{n['energy_kcal']:<7.0f}"
              f"{n['protein_g']:<6.1f}{n['available_carbohydrate_g']:<7.1f}{n['sodium_mg']:<7.0f}")
        for w in res.warnings[:2]:
            print(f"    ⚠ {w[:80]}")
        for u in res.unmatched_ingredients[:4]:
            print(f"    ✗ 未匹配: {u['ingredient_name']} ({u['grams']}g)")

    print(f"\n=== 汇总 ===")
    print(f"状态分布: {dict(status_counter)}")
    if unmatched_all:
        print(f"未匹配食材(全重叠部分): {len(unmatched_all)} 种")
        for name, cnt in unmatched_all.most_common(15):
            print(f"  ✗ {name} x{cnt}")
    else:
        print("未匹配食材: 0 —— 全部命中营养库")
    if missing_recipes:
        print(f"⚠ 对照表里有 {len(missing_recipes)} 道在 SOP 中未找到菜谱:")
        for d in missing_recipes:
            print(f"  - {d[:50]}")

    # 4) 导出菜式管理 Excel
    out = WORKDIR / "data" / "samples" / "9月重叠部分_营养验证.xlsx"
    write_dish_excel(results, str(out), dish_no_start=100001)
    print(f"\n已导出: {out} ({len(results)} 道)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
