"""修复被错误映射为"椰菜"(卷心菜)的椰菜花/西椰菜类食材。"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import csv
import json
import time
from pathlib import Path

from batch_fetch_cfs import make_search_keyword, pick_best, fallback_keywords
from cfs_fetch import fetch_nutrient, search_food, to_profile_row

WORKDIR = Path(r"F:\营养素计算工具")
PROGRESS = WORKDIR / "data" / "cfs_progress.json"
MATCHED_CSV = WORKDIR / "data" / "ingredient_nutrients.csv"

# 名称含这些词 -> 应按"椰菜花"重抓
FIX_WORDS = ["椰菜花", "西椰菜", "福建椰菜花"]
# 但也包含 椰菜苗(是菜苗不是椰菜花), 单独排除
EXCLUDE = ["椰菜苗"]


def main() -> int:
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    with MATCHED_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    targets = [
        r for r in rows
        if r["aliases"] == "椰菜"
        and any(w in r["ingredient_name"] for w in FIX_WORDS)
        and not any(e in r["ingredient_name"] for e in EXCLUDE)
    ]
    print(f"待修复: {len(targets)} 行")
    fixed = 0
    for row in targets:
        name = row["ingredient_name"]
        code = row["ingredient_code"]
        kw = "椰菜花"
        key = f"{code}|{name}"
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
                    new_row = to_profile_row(detail, code, name, best.name)
                    row.update(new_row)
                    if key in progress:
                        progress[key].update(
                            status="matched", matched_name=detail.get("food_name", ""),
                            source=detail.get("source", ""), score=score, keyword=kw, row=new_row,
                        )
                    fixed += 1
                    print(f"  ✓ {name[:24]:24s} -> {detail.get('food_name','')[:36]}", flush=True)
                else:
                    print(f"  ✗ {name[:24]:24s} 详情无来源", flush=True)
            else:
                print(f"  ✗ {name[:24]:24s} 无匹配(kw={kw})", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {name[:24]:24s} {type(exc).__name__}: {exc}", flush=True)

    PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        headers = list(rows[0].keys())
        with MATCHED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
    print(f"\n修复完成: {fixed}/{len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
