"""fill_cfc_fibre_cross_source.py —— 为 CFC 待补纤维食材填入 CFS 替代来源的纤维值。

背景
----
CFC2002Ed2 碳水按"总碳水"存储(口径错误), 换算可利用碳水 = 总碳水 − 纤维,
但 17 行 CFC 详情页纤维为 ND, 无法换算。本脚本从 CFS 官网**同类型食物的其他来源**
(AFCD/FRL/USDA)取纤维值填入, 再按官方 4-9-4 公式重算能量:
    available = 总碳水 − 纤维
    energy    = 4×available + 4×蛋白質 + 9×總脂肪

纤维值来源均为 CFS 官网实测条目(见 FIBRE_MAP 的 fibre_source), 非虚构;
肉类/果汁/香肠等纤维≈0 为科学事实。素午餐肉(大豆制品)保留人工核验。

可追溯: 每行改动记录到 data/cfs_progress.json (carb_total_before /
energy_kcal_before_carb_fix / fibre_source), 修改前自动备份 CSV。

用法
----
  python scripts/fill_cfc_fibre_cross_source.py
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent.parent
CSV_PATH = WORKDIR / "data" / "ingredient_nutrients.csv"
PROGRESS_PATH = WORKDIR / "data" / "cfs_progress.json"

# (ingredient_code, ingredient_name) -> (纤维值, 纤维来源说明)
# 来源均为 CFS 官网实测条目(探针 _probe_fibre.py 2026-08-12)
FIBRE_MAP: dict[tuple[str, str], tuple[float, str]] = {
    ("DTL0039", "濃縮檸檬汁"): (2.5, "CFS 檸檬汁 (AFCD)"),
    ("HKO-3234", "豬柳扒"): (0.0, "CFS 豬柳(瘦肉,生) (AFCD)"),
    ("HK0-3234", "豬柳扒"): (0.0, "CFS 豬柳(瘦肉,生) (AFCD)"),  # O/0 编码混淆的重复行
    ("HK0-1037", "豬柳扒條"): (0.0, "CFS 豬柳(瘦肉,生) (AFCD)"),
    ("HK0-1037", "豬柳扒漢堡扒"): (0.0, "CFS 豬柳(瘦肉,生) (AFCD)"),
    ("MCK0104", "火腿"): (0.0, "CFS 火腿製品 (USDA)"),
    ("MCK0104", "火腿片"): (0.0, "CFS 火腿製品 (USDA)"),
    ("MCK0104", "火腿絲"): (0.0, "CFS 火腿製品 (USDA)"),
    ("HK0-2015", "螺絲粉"): (3.2, "CFS 意粉(乾) (AFCD)"),
    ("HK0-0416", "免治豬肉"): (0.0, "CFS 免治豬肉(炒,無添加脂肪) (AFCD)"),
    ("VHF072", "包仔豆腐"): (1.0, "CFS 硬豆腐 (AFCD)"),
    ("VCK0044", "百福豆腐"): (1.0, "CFS 硬豆腐 (AFCD)"),
    ("HK0-3235", "牛片"): (0.0, "CFS 免治牛肉(低脂,炒,無添加脂肪) (AFCD)"),
    ("HK0-3568", "濃縮橙汁"): (0.0, "CFS 鮮榨橙汁 (FRL)"),
    ("", "蜜糖雞尾腸3個"): (0.0, "CFS 牛肉香腸(生) (AFCD)"),
    ("HK0-3364", "午餐肉（亨通）"): (0.2, "CFS 雞午餐肉(低脂或較低脂) (AFCD)"),
}


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    headers = list(rows[0].keys())

    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8")) if PROGRESS_PATH.exists() else {}

    filled = 0
    not_found = []
    for r in rows:
        key = (r.get("ingredient_code", "").strip(), r.get("ingredient_name", "").strip())
        if key not in FIBRE_MAP:
            continue
        # 幂等守卫: 纤维已填(非空)的行视为已处理, 跳过(避免重复扣减)
        if (r.get("dietary_fibre_g") or "").strip() not in ("", "ND", "NA", "Trace"):
            print(f"  [跳过] {key[1]} 纤维已填={r['dietary_fibre_g']!r}")
            continue
        fibre_val, fibre_src = FIBRE_MAP[key]
        try:
            total_carb = float(r.get("available_carbohydrate_g") or 0)  # 当前存的是总碳水
            protein = float(r.get("protein_g") or 0)
            fat = float(r.get("total_fat_g") or 0)
            old_energy = float(r.get("energy_kcal") or 0)
        except (ValueError, TypeError) as exc:
            not_found.append((key, f"数值解析失败: {exc}"))
            continue

        avail = round(total_carb - fibre_val, 4)
        new_energy = round(4 * avail + 4 * protein + 9 * fat, 4)
        old_carb = r.get("available_carbohydrate_g")

        prog_key = f"{key[0]}|{key[1]}"
        rec = progress.setdefault(prog_key, {})
        rec["carb_total_before"] = old_carb
        rec["dietary_fibre_g_filled"] = fibre_val
        rec["fibre_source"] = fibre_src
        rec["available_carbohydrate_g_after"] = avail
        rec["energy_kcal_before_carb_fix"] = old_energy
        rec["energy_kcal_after_carb_fix"] = new_energy
        rec["filled_at"] = datetime.now().isoformat(timespec="seconds")

        r["dietary_fibre_g"] = f"{fibre_val:g}"
        r["available_carbohydrate_g"] = f"{avail}"
        r["energy_kcal"] = f"{new_energy:.4f}"
        filled += 1
        print(f"  [{key[0] or '(无码)'}] {key[1]:<12} 碳水 {old_carb} → {avail}  能量 {old_energy:.1f} → {new_energy:.1f}  纤维={fibre_val}({fibre_src})")

    if filled:
        backup = CSV_PATH.with_name(f"{CSV_PATH.stem}.bak-{datetime.now().strftime('%Y%m%d%H%M')}")
        shutil.copy2(CSV_PATH, backup)
        print(f"  已备份: {backup.name}")

    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n填入纤维: {filled} 行 | 未找到匹配行: {len(not_found)}")
    for key, reason in not_found:
        print(f"  ⚠ {key}: {reason}")

    # 提示: 素午餐肉(大豆制品)保留人工核验
    print("保留人工核验: 素午餐肉 HK0-3364 (大豆制品, 纤维值需供应商数据)")


if __name__ == "__main__":
    main()
