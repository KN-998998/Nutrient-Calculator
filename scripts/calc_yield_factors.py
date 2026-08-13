"""用 CFS 生/熟食材对反推产出因子(yield factor)。

原理(USDA True Retention 法简化): 烹煮中蛋白质保留率≈100%,
熟重/生重 ≈ 生食每100g蛋白 ÷ 熟食每100g蛋白。

输入: 生熟对(CFS 食物名)
输出: yield_factors.json  {熟食材名: {"yield": x, "raw_name": ..., "cooked_name": ..., "protein_raw":, "protein_cooked":}}
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from cfs_fetch import fetch_nutrient, search_food

OUT = Path(r"F:\营养素计算工具\data\yield_factors.json")

# (生食材CFS名, 熟食材CFS名, 备注)
PAIRS = [
    ("白米(未經烹煮)", "白米(熟)", "米饭 1:2.9"),
    ("糙米(未經烹煮)", "糙米飯(煮，無添加鹽)", "糙米饭 1:2"),
    ("意粉(乾)", "意粉(乾，煮，無添加鹽)", "意粉 1:2.5"),
    ("全蛋意粉(乾)", "全蛋意粉(乾，煮，無添加鹽)", "全蛋意粉"),
    ("雞胸肉(瘦肉，生)", "雞胸肉(瘦肉，焗，無添加脂肪)", "鸡胸烤"),
    ("雞肉(連皮，生)", "雞肉(燒烤，連皮)", "鸡肉烧烤"),
    ("豬肉(瘦)", "豬肉(清蒸)", "猪肉清蒸"),
    ("免治牛肉(低脂，生)", "免治牛肉(低脂，炒，無添加脂肪)", "免治牛肉"),
    ("菜心", "灼菜心(不加油)", "菜心灼"),
    ("西蘭花", "西蘭花(烚，瀝乾)", "西蘭花烚"),
    ("馬鈴薯(未經烹煮)", "馬鈴薯(烚，瀝乾)", "薯仔烚"),
    ("甘筍(生)", "甘筍(烚，瀝乾)", "甘筍烚"),
]


def find_exact(kw: str):
    """搜索并返回名称完全匹配(去空格比较)的候选。"""
    cands = search_food(kw)
    target = kw.replace(" ", "")
    for c in cands:
        if c.name.replace(" ", "") == target:
            return c
    # 宽松: 候选名包含关键词
    for c in cands:
        if kw.replace(" ", "") in c.name.replace(" ", ""):
            return c
    return None


def get_nutrients(c):
    detail = fetch_nutrient(c.fg_id, c.fsg_id, c.food_id)
    return detail


def main() -> int:
    results = {}
    for raw_name, cooked_name, note in PAIRS:
        try:
            time.sleep(0.4)
            raw_c = find_exact(raw_name)
            time.sleep(0.4)
            cooked_c = find_exact(cooked_name)
            if not raw_c or not cooked_c:
                print(f"✗ {raw_name[:18]:18s} -> {cooked_name[:20]:20s} 未找到候选 "
                      f"(raw={bool(raw_c)}, cooked={bool(cooked_c)})")
                continue
            raw = get_nutrients(raw_c)
            time.sleep(0.3)
            cooked = get_nutrients(cooked_c)

            def num(d, k):
                try:
                    return float(d.get(k, 0) or 0)
                except (TypeError, ValueError):
                    return 0.0

            rp, cp = num(raw, "蛋白質"), num(cooked, "蛋白質")
            rc, cc = num(raw, "碳水化合物*"), num(cooked, "碳水化合物*")
            re_, ce = num(raw, "能量*"), num(cooked, "能量*")
            yields = {}
            if cp > 0:
                yields["yield_protein"] = round(rp / cp, 3)
            if cc > 0:
                yields["yield_carb"] = round(rc / cc, 3)
            if ce > 0:
                yields["yield_energy"] = round(re_ / ce, 3)
            # 取中位作为最终 yield(蛋白/碳水/能量三个估计的稳健值)
            vals = [v for v in (yields.get("yield_protein"), yields.get("yield_carb"), yields.get("yield_energy")) if v]
            final = round(sum(vals) / len(vals), 3) if vals else None
            results[cooked_name] = {
                "yield": final,
                "raw_name": raw_name,
                "cooked_name": raw.get("food_name", cooked_name),
                "raw_source": raw.get("source", ""),
                "cooked_source": cooked.get("source", ""),
                "protein_raw": rp, "protein_cooked": cp,
                "carb_raw": rc, "carb_cooked": cc,
                "energy_raw": re_, "energy_cooked": ce,
                "estimates": yields,
                "note": note,
            }
            print(f"✓ {raw_name[:18]:18s} -> {raw.get('food_name','')[:22]:22s} yield={final} "
                  f"(蛋白{yields.get('yield_protein','-')} 碳水{yields.get('yield_carb','-')} 能量{yields.get('yield_energy','-')})")
        except Exception as exc:  # noqa: BLE001
            print(f"✗ {raw_name[:18]:18s} ERR {type(exc).__name__}: {exc}")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n输出: {OUT}, {len(results)} 个成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
