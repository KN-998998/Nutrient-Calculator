"""用 CFS 营养库计算 SOP 菜品营养, 与历史结果比对。

流程:
1. 从 ingredient_nutrients.csv 建 NutrientRepository
2. read_sop_workbook 解析 5月/6月 SOP -> 菜谱
3. calculate_recipe 计算每道菜营养(不匹配的食材标记)
4. 从 history_results.json 读历史结果
5. 按菜名(去餐别前缀/日期编号)匹配, 对比 8 项营养, 输出差异报告
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
import re
from pathlib import Path

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.repository import NutrientRepository, normalize_name
from nutrition_tool.sop import read_sop_workbook

WORKDIR = Path(r"F:\营养素计算工具")
SOP_MAY = WORKDIR / "菜单+SOP" / "finnal-2026年5月Lunch 學生餐單Menusop 0516.xlsx"
SOP_JUNE = WORKDIR / "菜单+SOP" / "finnal-2026年6月Lunch 學生餐單Menusop.xlsx"
DB_CSV = WORKDIR / "data" / "ingredient_nutrients.csv"
HISTORY_JSON = WORKDIR / "data" / "history_results.json"

FIELDS = [
    ("energy_kcal", "能量"),
    ("protein_g", "蛋白質"),
    ("total_fat_g", "總脂肪"),
    ("saturated_fat_g", "飽和脂肪"),
    ("trans_fat_g", "反式脂肪"),
    ("available_carbohydrate_g", "碳水"),
    ("sugars_g", "糖"),
    ("sodium_mg", "鈉"),
]

HISTORY_FIELD_KEYS = [f[0] for f in FIELDS]


def clean_recipe_name(name: str) -> str:
    """历史结果名: 'A(27)蔥爆牛肉片配飯(菜心苗)' -> '蔥爆牛肉片配飯(菜心苗)'"""
    text = str(name or "").strip()
    text = re.sub(r"^[A-E][(（][\d.]+[)）]", "", text)  # 去 餐别(日期)
    text = re.sub(r"[#★●▲□◆※不辣]", "", text)
    return text.strip()


def main() -> int:
    if not DB_CSV.exists():
        print("缺少 ingredient_nutrients.csv —— 请先运行 batch_fetch_cfs.py")
        return 1
    repo = NutrientRepository.from_csv(DB_CSV)
    print(f"营养库: {len(repo.profiles)} 个食材")

    # 1. 计算 5/6 月菜品
    results = []
    for sop_path, month in ((SOP_MAY, "5"), (SOP_JUNE, "6")):
        recipes, errors = read_sop_workbook(sop_path)
        print(f"{month}月 SOP: {len(recipes)} 道菜, 解析异常 {len(errors)}")
        for recipe in recipes:
            r = calculate_recipe(recipe, repo)
            results.append({"month": month, "recipe": recipe, "result": r})

    # 2. 读历史结果
    history = json.loads(HISTORY_JSON.read_text(encoding="utf-8"))

    # 3. 按清洗后菜名匹配
    def find_recipe(month: str, hname: str):
        h_clean = clean_recipe_name(hname)
        h_norm = normalize_name(h_clean)
        best, best_score = None, 0.0
        for item in results:
            if item["month"] != month:
                continue
            rn = normalize_name(item["recipe"].recipe_name)
            # 精确/包含优先
            if rn == h_norm:
                return item
            score = max(
                (rn in h_norm, h_norm in rn),
            )
            if score and not best_score:
                best = item
                best_score = 1
        return best if best_score else None

    matched = 0
    compared = 0
    diff_rows = []
    unmatched_hist = []
    for h in history:
        if h["month"] not in ("5", "6") or not h["nutrients"]:
            continue
        item = find_recipe(h["month"], h["name"])
        if not item:
            unmatched_hist.append(h["name"])
            continue
        matched += 1
        result = item["result"]
        if result.status == "incomplete":
            continue  # 有未匹配食材, 不比对
        # 对比 8 项
        diffs = []
        for field, label in FIELDS:
            hv = h["nutrients"].get(field)
            cv = result.nutrients_per_serving.get(field)
            if hv is None or cv is None:
                continue
            if cv == 0:
                ratio = None
            else:
                ratio = abs(hv - cv) / cv
            if ratio is not None and ratio > 0.30:
                diffs.append(f"{label}: 历史={hv:g} 计算={cv:.2f} (差{ratio:.0%})")
        compared += 1
        if diffs:
            diff_rows.append({
                "month": h["month"],
                "name": h["name"],
                "sop_name": item["recipe"].recipe_name,
                "status": result.status,
                "diffs": diffs,
                "n_diffs": len(diffs),
            })

    print(f"\n==== 比对结果 ====")
    print(f"历史结果(5/6月)总数: {len([h for h in history if h['month'] in ('5','6')])}")
    print(f"匹配到 SOP: {matched}, 未匹配: {len(unmatched_hist)}")
    print(f"可比对(无未匹配食材): {compared}")
    print(f"差异>30% 的项: {len(diff_rows)}")

    if unmatched_hist:
        print("\n未匹配历史菜名(前10):")
        for n in unmatched_hist[:10]:
            print(f"  - {n}")

    if diff_rows:
        print("\n==== 差异明细(前 20) ====")
        for d in diff_rows[:20]:
            print(f"[{d['month']}月] {d['name'][:36]}")
            print(f"      SOP: {d['sop_name'][:36]}")
            for diff in d["diffs"]:
                print(f"        {diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
