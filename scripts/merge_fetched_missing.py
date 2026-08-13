"""merge_fetched_missing.py —— 把抓取结果合并进营养库(第三阶段)。

修正/补充:
- 淮山肉 <切角> -> 山藥[薯蕷，大薯] (鲜品, 非山藥(乾))
- 姜蓉（沙师弟） -> 薑(去皮) (鲜姜, 非薑(乾))
- 扭扭粉彎曲通心粉（山麥） -> 通心麵[通心粉] (意粉类近似)
- 黑松露醬/黑松露油 -> 蘑菇(乾) (菌类近似)
合并前自动备份; 每行记录 provenance 到 cfs_progress.json。
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cfs_fetch import fetch_nutrient, search_food, to_profile_row  # noqa: E402
from batch_fetch_cfs import pick_best  # noqa: E402

WORKDIR = Path(__file__).resolve().parent.parent
CSV_PATH = WORKDIR / "data" / "ingredient_nutrients.csv"
PROGRESS_PATH = WORKDIR / "data" / "cfs_progress.json"
FETCHED_JSON = WORKDIR / "data" / "samples" / "fetched_missing_rows.json"

# 需要覆盖/补充的抓取: name -> (search_kw, 期望匹配的 CFS 名包含)
OVERRIDE_FETCH = {
    "淮山肉 <切角>": ("山藥", "薯蕷"),
    "姜蓉（沙师弟）": ("薑", "去皮"),
    "扭扭粉彎曲通心粉（山麥）": ("通心粉", "通心粉"),
    "黑松露醬": ("蘑菇", "蘑菇"),
    "黑松露油": ("蘑菇", "蘑菇"),
}


def fetch_one(name: str, kw: str, expect: str) -> dict:
    candidates = search_food(kw)
    best = None
    for c in candidates:
        if expect in c.name:
            best = c
            break
    if best is None:
        _, best = pick_best(candidates, kw)
    if best is None:
        raise RuntimeError(f"{name}: 无候选 (kw={kw})")
    time.sleep(0.3)
    detail = fetch_nutrient(best.fg_id, best.fsg_id, best.food_id)
    row = to_profile_row(detail, ingredient_code="", ingredient_name=name, matched_name=best.name)
    row["_matched_name"] = best.name
    return row


def main() -> int:
    rows = json.loads(FETCHED_JSON.read_text(encoding="utf-8")) if FETCHED_JSON.exists() else []
    # 覆盖/补充
    for name, (kw, expect) in OVERRIDE_FETCH.items():
        try:
            row = fetch_one(name, kw, expect)
            rows = [r for r in rows if r.get("ingredient_name") != name]
            rows.append(row)
            print(f"  [补充] {name} -> {row['_matched_name']}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [ERR] {name}: {exc}")

    # 读主库
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        db_rows = list(csv.DictReader(f))
    headers = list(db_rows[0].keys())
    db_names = {r["ingredient_name"].strip() for r in db_rows}
    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8")) if PROGRESS_PATH.exists() else {}

    shutil.copy2(CSV_PATH, f"data/ingredient_nutrients.bak-{datetime.now().strftime('%Y%m%d%H%M')}")
    added = 0
    for r in rows:
        name = r.get("ingredient_name", "").strip()
        if not name or name in db_names:
            print(f"  [跳过] {name} 已存在")
            continue
        matched = r.pop("_matched_name", "")
        score = r.pop("_score", None)
        row = {h: "" for h in headers}
        for h in headers:
            if h == "aliases":
                row[h] = matched
            elif h in r:
                row[h] = str(r[h]) if r[h] not in (None, "") else ""
            elif h in ("edible_fraction", "yield_factor", "retention_factor"):
                row[h] = "1"
        db_rows.append(row)
        progress[f"|{name}"] = {
            "matched_cfs_name": matched,
            "score": score,
            "source": row.get("source", ""),
            "added_at": datetime.now().isoformat(timespec="seconds"),
            "note": "9月重叠 CFS 补抓(近似匹配, 待营养师复核)",
        }
        added += 1
        print(f"  [加入] {name} <- {matched}")

    if added:
        with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(db_rows)
        PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n新增 {added} 行 -> {CSV_PATH.name}")
    return 0


if __name__ == "__main__":
    main()
