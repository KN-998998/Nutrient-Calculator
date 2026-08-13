"""修复错误匹配的食材营养数据。

对已知错误匹配(key 列表)用修正后的关键词重新搜索+抓取,
更新 cfs_progress.json 和 ingredient_nutrients.csv。
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import csv
import json
import time
from pathlib import Path

from batch_fetch_cfs import (
    MATCHED_CSV,
    PROGRESS,
    UNMATCHED_JSON,
    make_search_keyword,
    pick_best,
    fallback_keywords,
)
from cfs_fetch import NUTRIENT_MAP, fetch_nutrient, search_food, to_profile_row

WORKDIR = Path(r"F:\营养素计算工具")

# 需要修复的食材名(错误匹配 -> 修复原因)
FIX_NAMES = [
    "生粉",                      # 匹配成粟米(玉米), 应为玉米澱粉
    "25KG 風車生粉",              # 同上
    "濃縮橙汁",                   # 匹配成橙汁汽水, 应为鮮榨橙汁
    "4X5L 玉蓮麻油 (紅蓋)",          # 匹配成胡麻油(亚麻籽油), 应为芝麻油
    "蔥阿伯東北手工水餃",             # 匹配成水餃湯粗麵條, 应为菜肉水餃
    "12X510G 李錦記素食蠔油",        # 匹配成蠔油(普通), 素食蠔油近似可接受但确认
    "大米/泰國香米（飛羊）[彩線]25公斤",  # 匹配成小米, 应为白米
    "大米",                          # 同上
    "大米/金盾牌頂級香絲苗米（紅線）25公斤",  # 同上
]


def main() -> int:
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    # 读现有 CSV 行
    rows = []
    if MATCHED_CSV.exists():
        with MATCHED_CSV.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

    fixed = 0
    for name in FIX_NAMES:
        key = next((k for k, v in progress.items() if v.get("name") == name), None)
        if not key:
            print(f"跳过(不在进度): {name}")
            continue
        rec = progress[key]
        code = rec["code"]
        kw = make_search_keyword(name)
        print(f"修复 [{name}] kw={kw}", flush=True)
        try:
            time.sleep(0.5)
            cands = search_food(kw)
            best, score = pick_best(cands, kw)
            if not best or score < 0.55:
                for fk in fallback_keywords(kw)[:2]:
                    time.sleep(0.5)
                    fcands = search_food(fk)
                    fbest, fscore = pick_best(fcands, fk)
                    if fbest and fscore >= 0.55:
                        cands, best, score = fcands, fbest, fscore
                        break
            if best and score >= 0.55:
                time.sleep(0.5)
                detail = fetch_nutrient(best.fg_id, best.fsg_id, best.food_id)
                if detail.get("source"):
                    row = to_profile_row(detail, code, name, best.name)
                    rec.update(
                        status="matched",
                        matched_name=detail.get("food_name", ""),
                        source=detail.get("source", ""),
                        score=score,
                        keyword=kw,
                        candidates=[c.name for c in cands[:8]],
                        row=row,
                    )
                    # 更新 CSV 行
                    replaced = False
                    for r in rows:
                        if r["ingredient_name"] == name:
                            r.update(row)
                            replaced = True
                            break
                    if not replaced:
                        rows.append(row)
                    fixed += 1
                    print(f"  -> {detail.get('food_name', '')[:40]} ({detail.get('source','')[:20]})", flush=True)
                else:
                    rec["status"] = "unmatched"
                    rec["reason"] = "重新抓取无来源"
            else:
                rec["status"] = "unmatched"
                rec["reason"] = f"无候选 >= 0.55 (kw={kw})"
                print(f"  仍无匹配 kw={kw}", flush=True)
        except Exception as exc:  # noqa: BLE001
            rec["status"] = "error"
            rec["reason"] = f"{type(exc).__name__}: {exc}"
            print(f"  错误: {exc}", flush=True)

    PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        headers = list(rows[0].keys())
        with MATCHED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
    print(f"\n修复完成: {fixed}/{len(FIX_NAMES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
