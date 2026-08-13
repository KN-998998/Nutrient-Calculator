"""重抓全部 matched 食材的详情, 补全钠/糖/膳食纤维/胆固醇等字段。

原因: 早期 fetch_nutrient 正则不匹配含空格的 <td> <div> 行,
导致膳食纤维/糖/钠/胆固醇/矿物质全部漏解析(存为空)。
修复正则后需要重抓全部 267 个食材。

流程: 遍历 progress matched 记录 -> keyword 搜索 -> pick_best -> fetch_nutrient -> 更新 row + CSV
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from batch_fetch_cfs import make_search_keyword, pick_best
from cfs_fetch import fetch_nutrient, search_food, to_profile_row

WORKDIR = Path(r"F:\营养素计算工具")
PROGRESS = WORKDIR / "data" / "cfs_progress.json"
MATCHED_CSV = WORKDIR / "data" / "ingredient_nutrients.csv"


def refetch_one(key: str, rec: dict, lock: Lock, rows_by_key: dict, total: int, done: list) -> None:
    """重抓单个食材详情。"""
    name, code = rec["name"], rec["code"]
    kw = rec.get("keyword") or make_search_keyword(name)
    try:
        time.sleep(0.3)
        cands = search_food(kw)
        best, score = pick_best(cands, kw)
        if not best or score < 0.55:
            rec["refetch"] = f"no match for {kw}"
            with lock:
                done[0] += 1
                print(f"[{done[0]}/{total}] SKIP {name[:22]} (无匹配)", flush=True)
            return
        time.sleep(0.3)
        detail = fetch_nutrient(best.fg_id, best.fsg_id, best.food_id)
        if not detail.get("source"):
            rec["refetch"] = "no source"
            with lock:
                done[0] += 1
                print(f"[{done[0]}/{total}] SKIP {name[:22]} (无来源)", flush=True)
            return
        row = to_profile_row(detail, code, name, best.name)
        rec["row"] = row
        rec["matched_name"] = detail.get("food_name", "")
        rec["source"] = detail.get("source", "")
        rec["refetch"] = "ok"
        with lock:
            rows_by_key[key] = row
            done[0] += 1
            if done[0] % 20 == 0 or done[0] == total:
                print(f"[{done[0]}/{total}] ✓ {name[:22]} 钠={row['sodium_mg']!r}", flush=True)
    except Exception as exc:  # noqa: BLE001
        rec["refetch"] = f"{type(exc).__name__}: {exc}"
        with lock:
            done[0] += 1
            print(f"[{done[0]}/{total}] ERR {name[:22]}: {type(exc).__name__}", flush=True)


def main() -> int:
    progress = json.loads(PROGRESS.read_text(encoding="utf-8"))
    with MATCHED_CSV.open(encoding="utf-8-sig", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    rows_by_key = {
        f"{r['ingredient_code']}|{r['ingredient_name']}": r for r in csv_rows
    }

    targets = {k: v for k, v in progress.items() if v.get("status") == "matched"}
    print(f"待重抓: {len(targets)} 个", flush=True)

    lock = Lock()
    done = [0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(refetch_one, k, v, lock, rows_by_key, len(targets), done)
            for k, v in targets.items()
        ]
        for f in futures:
            f.result()

    # 落盘: progress
    PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
    # 落盘: CSV(用 rows_by_key 重建, 保持原顺序)
    out_rows = []
    for r in csv_rows:
        key = f"{r['ingredient_code']}|{r['ingredient_name']}"
        if key in rows_by_key:
            out_rows.append(rows_by_key[key])
        else:
            out_rows.append(r)
    headers = list(csv_rows[0].keys())
    with MATCHED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(out_rows)

    # 统计
    n_sodium = sum(1 for r in out_rows if r.get("sodium_mg") not in ("", "0", "0.0"))
    n_fibre = sum(1 for r in out_rows if r.get("dietary_fibre_g") not in ("", "0", "0.0"))
    print(f"\n营养库 {len(out_rows)} 行: 钠有值 {n_sodium}, 膳食纤维有值 {n_fibre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
