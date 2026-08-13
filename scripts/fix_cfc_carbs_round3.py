"""CFC 碳水口径修复 - 第三轮:重算能量。

背景:CFC2002Ed2 的能量值按"总碳水"计算(中国数据库惯例)。
方案 A 把碳水换成可利用碳水后,能量字段口径必须同步:
    energy_kcal = 4×可用碳水 + 4×蛋白質 + 9×總脂肪   (香港方法指引官方公式)

只重算"已换算碳水"的 CFC 行(纤维>0);待人工行(纤维未知)保持原样,
等纤维补齐后再统一重算。原能量值记录到 progress(可追溯)。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

WORKDIR = Path(r"F:\营养素计算工具")
CSV_PATH = WORKDIR / "data" / "ingredient_nutrients.csv"
PROGRESS_PATH = WORKDIR / "data" / "cfs_progress.json"


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    headers = list(rows[0].keys())
    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))

    recomputed = 0
    skipped = 0
    for r in rows:
        if "CFC" not in (r.get("source") or ""):
            continue
        try:
            carb = float(r["available_carbohydrate_g"] or 0)
            fibre = float(r["dietary_fibre_g"] or 0)
            protein = float(r["protein_g"] or 0)
            fat = float(r["total_fat_g"] or 0)
            old_energy = float(r["energy_kcal"] or 0)
        except (ValueError, TypeError):
            continue
        if fibre <= 0:  # 未换算碳水(待人工/无纤维) → 不动
            skipped += 1
            continue
        new_energy = round(4 * carb + 4 * protein + 9 * fat, 4)
        key = f"{r['ingredient_code']}|{r['ingredient_name']}"
        rec = progress.get(key)
        if rec is not None:
            rec["energy_kcal_before_carb_fix"] = old_energy
        r["energy_kcal"] = f"{new_energy:.4f}"
        recomputed += 1
        if recomputed <= 8 or old_energy - new_energy > 50:
            print(f"  {r['ingredient_name'][:20]:<22} 能量 {old_energy:>6} → {new_energy:>7.1f}", flush=True)

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n重算能量: {recomputed} 行 | 保持原样(待人工/无纤维): {skipped} 行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
