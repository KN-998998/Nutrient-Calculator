"""方案 A:CFC2002Ed2 碳水口径修复 —— 总碳水 → 可利用碳水。

依据:香港 NLC 指南碳水默认"可利用碳水"(= 总碳水 - 膳食纤维)。
CFC2002Ed2 来源(78 行)的碳水是总碳水,之前直接存入 available_carbohydrate_g。

处理:
1. 纤维有值(34 行) → 本地直接换算 available = carb - fibre
2. 纤维缺失且碳水>1(31 行) → 联网重抓 CFS 详情补纤维,抓到再换算
3. 纤维缺失且碳水<=1(13 行) → 无影响,跳过
4. 重抓后仍缺纤维 → 输出待人工清单
5. 换算前的总碳水值记录到 progress(可追溯)
"""
from __future__ import annotations

import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from batch_fetch_cfs import make_search_keyword, pick_best  # noqa: E402
from cfs_fetch import fetch_nutrient, search_food  # noqa: E402

WORKDIR = Path(r"F:\营养素计算工具")
CSV_PATH = WORKDIR / "data" / "ingredient_nutrients.csv"
PROGRESS_PATH = WORKDIR / "data" / "cfs_progress.json"
MANUAL_LIST = WORKDIR / "data" / "CFC碳水待人工补录.csv"


def _is_cfc(row: dict) -> bool:
    return "CFC" in (row.get("source") or "")


def refetch_fibre(key: str, rec: dict, lock: Lock, results: dict) -> None:
    name = rec["name"]
    kw = rec.get("keyword") or make_search_keyword(name)
    try:
        time.sleep(0.3)
        cands = search_food(kw)
        best, score = pick_best(cands, kw)
        if not best or score < 0.55:
            with lock:
                results[key] = ("nomatch", None, "", "")
            return
        time.sleep(0.3)
        detail = fetch_nutrient(best.fg_id, best.fsg_id, best.food_id)
        fibre = detail.get("dietary_fibre_g")
        with lock:
            results[key] = ("ok", fibre, detail.get("source", ""), best.name)
    except Exception as exc:  # noqa: BLE001
        with lock:
            results[key] = (f"err:{type(exc).__name__}", None, "", "")


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))

    convert_done = 0
    refetch_targets: list[tuple[str, dict]] = []  # (csv_key, progress_rec)
    skip_count = 0
    headers = list(rows[0].keys())

    for r in rows:
        if not _is_cfc(r):
            continue
        try:
            carb = float(r["available_carbohydrate_g"] or 0)
            fibre = float(r["dietary_fibre_g"] or 0)
        except (ValueError, TypeError):
            continue
        if fibre > 0:
            # 本地换算,记录总碳水
            key = f"{r['ingredient_code']}|{r['ingredient_name']}"
            rec = progress.get(key)
            if rec is not None:
                rec["carb_total_before"] = carb
            new_carb = max(round(carb - fibre, 4), 0.0)
            r["available_carbohydrate_g"] = f"{new_carb:.4f}"
            convert_done += 1
        elif carb > 1:
            key = f"{r['ingredient_code']}|{r['ingredient_name']}"
            rec = progress.get(key)
            if rec is not None:
                refetch_targets.append((key, rec))
            else:
                # progress 里没有记录:输出待人工
                refetch_targets.append((key, {"name": r["ingredient_name"], "code": r["ingredient_code"], "keyword": ""}))
        else:
            skip_count += 1

    print(f"本地换算: {convert_done} 行 | 待联网补纤维: {len(refetch_targets)} 行 | 跳过: {skip_count} 行", flush=True)

    if refetch_targets:
        lock = Lock()
        results: dict[str, tuple] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(refetch_fibre, key, rec, lock, results)
                for key, rec in refetch_targets
            ]
            for f in futures:
                f.result()

        fixed = 0
        manual: list[dict] = []
        for key, rec in refetch_targets:
            status, fibre, source, matched = results.get(key, ("noresult", None, "", ""))
            code, name = key.split("|", 1)
            if status == "ok" and fibre not in (None, "", "NA", "ND", "Trace"):
                try:
                    fv = float(fibre)
                except (ValueError, TypeError):
                    fv = None
                if fv is not None:
                    # 找到 CSV 行更新
                    for r in rows:
                        if f"{r['ingredient_code']}|{r['ingredient_name']}" == key:
                            rec["carb_total_before"] = float(r["available_carbohydrate_g"] or 0)
                            new_carb = max(round(float(r["available_carbohydrate_g"] or 0) - fv, 4), 0.0)
                            r["dietary_fibre_g"] = f"{fv:.4f}"
                            r["available_carbohydrate_g"] = f"{new_carb:.4f}"
                            break
                    fixed += 1
                    print(f"  ✓ {name[:22]:<24} 纤维={fv} → 可用碳水={new_carb}", flush=True)
                    continue
            manual.append({
                "ingredient_code": code,
                "ingredient_name": name,
                "available_carbohydrate_g(总碳水)": rec.get("carb_total_before", ""),
                "reason": f"CFS 重抓纤维未获得 ({status})",
                "searched_keyword": rec.get("keyword") or make_search_keyword(name),
                "matched": matched or "",
            })
        print(f"联网补纤维成功: {fixed} 行 | 仍缺: {len(manual)} 行", flush=True)

        if manual:
            with MANUAL_LIST.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(manual[0].keys()))
                writer.writeheader()
                writer.writerows(manual)

    # 落盘 CSV
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    # 落盘 progress
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")

    # 统计
    cfc = [r for r in rows if _is_cfc(r)]
    cfc_carb = sum(1 for r in cfc if (r["available_carbohydrate_g"] or "").strip())
    cfc_fibre = sum(1 for r in cfc if (r["dietary_fibre_g"] or "").strip())
    print(f"\nCFC 行 {len(cfc)}: 碳水有值 {cfc_carb}, 纤维有值 {cfc_fibre}")
    print("换算完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
