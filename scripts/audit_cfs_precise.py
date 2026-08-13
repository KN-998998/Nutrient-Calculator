"""精准核对: 对指定 CFS 条目拉详情, 与库值逐字段比对。

用法: python scripts/audit_cfs_precise.py [--write]
候选: (CFS搜索词, 期望精确条目名, 库内比对行, 说明)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from cfs_fetch import fetch_nutrient, search_food

WORKDIR = Path(r"F:\营养素计算工具")
DB = WORKDIR / "data" / "ingredient_nutrients.csv"
OUT = WORKDIR / "data" / "audit_cfs_precise.csv"

NUTRIENT_KEYS = {
    "energy_kcal": "能量*",
    "protein_g": "蛋白質",
    "total_fat_g": "脂肪",
    "saturated_fat_g": "飽和脂肪",
    "trans_fat_g": "反式脂肪",
    "available_carbohydrate_g": "碳水化合物*",
    "sugars_g": "糖",
    "sodium_mg": "鈉",
    "dietary_fibre_g": "膳食纖維*",
}

# (搜索词, 期望精确条目名, 库内比对行名, 说明)
TARGETS = [
    ("雞蛋", "雞蛋(全隻，生)", "雞蛋", "库用全熟, 需对比生蛋"),
    ("蘑菇", "蘑菇(鮮蘑)", "蘑菇片", "库用干蘑菇, 需对比鲜蘑"),
    ("大葱", "大葱", "京蔥", "京蔥=大葱 验证"),
    ("菠蘿", "菠蘿[鳳梨，地鳳梨]", "菠蘿粒", "泰源菠萝 vs CFS菠萝"),
    ("番茄", "番茄(Red tomato)", "鮮茄 <切角>", "FRL Red tomato 验证"),
    ("豉油", "豉油", "生抽", "AFCD 豉油 验证"),
    ("白菜", "大白菜(白梗)[黃芽白]", "紹菜", "紹菜=黃芽白 验证"),
    ("河粉", "牛丸河粉（不連湯）", "河粉", "泰源河粉碳水验证"),
    ("白米", "白米(未經烹煮)", "大米", "对照组"),
    ("菜心", "菜心", "菜心", "对照组"),
    ("山藥", "山藥[薯蕷，大薯]", "山藥肉 <切角>", "鲜品对照组"),
    ("冬菇", "冬菇(乾)[毛柄金線菌]", "冬菇", "CFC碳水换算对照组"),
    ("佛手瓜", "佛手瓜[棒瓜，菜餚梨]", "合掌瓜肉 <切角>", "对照组"),
    ("蟹肉", "蟹肉", "蟹柳", "近似匹配对照组"),
    ("豬肉", "豬(瘦)", "牛坑腩切", "肉类对照组(近似)"),
]


def parse_num(detail: dict, key: str) -> float | None:
    v = detail.get(key, "")
    if isinstance(v, (int, float)):
        return float(v)
    v = str(v).strip()
    if not v or v in ("NA", "ND", "Trace", "微量"):
        return None
    m = re.match(r"([-+]?\d+\.?\d*)", v)
    return float(m.group(1)) if m else None


def find_exact(cands, expect: str):
    for c in cands:
        if c.name.strip() == expect:
            return c
    return None


def main() -> None:
    rows = list(csv.DictReader(DB.open(encoding="utf-8-sig")))
    write_out = "--write" in sys.argv
    results = []

    print(f"{'说明':<22} {'CFS条目':<26} {'字段':<8} {'库值':>9} {'官网':>9} {'判定':<4}")
    print("-" * 96)
    for kw, expect, db_name, note in TARGETS:
        cands = search_food(kw)
        cand = find_exact(cands, expect)
        if cand is None:
            print(f"[未找到条目] {kw} -> {expect}")
            time.sleep(0.3)
            continue
        detail = fetch_nutrient(cand.fg_id, cand.fsg_id, cand.food_id)
        time.sleep(0.4)
        db_row = next((r for r in rows if r["ingredient_name"].strip() == db_name), None)
        if db_row is None:
            # 尝试包含匹配
            db_row = next((r for r in rows if db_name in r["ingredient_name"]), None)
        if db_row is None:
            print(f"[库内无行] {db_name} (CFS={expect})")
            continue

        diffs = []
        for field, cfs_key in NUTRIENT_KEYS.items():
            db_raw = db_row.get(field, "").strip()
            db_val = float(db_raw) if db_raw not in ("", "ND", "NA", "Trace", "微量") else None
            web_val = parse_num(detail, cfs_key)
            if db_val is not None and web_val is not None and abs(db_val - web_val) > 0.05:
                diffs.append((field, db_val, web_val))
            elif (db_val is None) != (web_val is None):
                diffs.append((field, db_val, web_val))
        status = "MISMATCH" if diffs else "OK"
        results.append({"说明": note, "CFS条目": expect, "库行": db_name,
                        "数据来源": detail.get("source", ""), "判定": status,
                        "不符字段数": len(diffs)})
        print(f"{note:<22} {expect:<26} {'':<8} {'':>9} {'':>9} {status:<4} ({len(diffs)})")
        for field, dbv, wv in diffs:
            print(f"{'':<22} {'':<26} {field:<8} {str(dbv):>9} {str(wv):>9}")
        carb_raw = str(detail.get("碳水化合物*", ""))
        print(f"{'':<22} {'':<26} 碳水原文  {'':>9} {carb_raw:>9}")

    if write_out:
        with OUT.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else [])
            w.writeheader()
            w.writerows(results)
        print(f"\n已写: {OUT}")
    print(f"\n精准核对完成: {len(results)} 条")


if __name__ == "__main__":
    main()
