"""CFC 碳水口径修复 - 第二轮:补纤维(纯物质/兄弟行)后完成换算。

背景:CFC2002Ed2 详情页对部分食材膳食纤维标 ND(未测定),不是解析失败。
第一轮(fix_cfc_carbs.py)联网重抓确认 ND,剩余 31 行需分类处理:
1. 纯物质(糖/牛油/味精,碳水>95 或明确纯物质):纤维物理 0,有化学依据,不属虚构
2. 同编码兄弟行有纤维值:直接抄(同一食材不同规格/形态)
3. 其余 → 保留在人工清单(data/CFC碳水待人工补录.csv)
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

WORKDIR = Path(r"F:\营养素计算工具")
CSV_PATH = WORKDIR / "data" / "ingredient_nutrients.csv"
PROGRESS_PATH = WORKDIR / "data" / "cfs_progress.json"
MANUAL_LIST = WORKDIR / "data" / "CFC碳水待人工补录.csv"

# 纯物质:仅限明确的糖类/油类/味精(化学上无纤维)。
# 注意排除加工肉肠(蜜糖雞尾腸)、油麵等含"糖/油"字的非纯物质。
PURE_WORDS = ("砂糖", "冰糖", "幼砂糖", "白砂糖", "牛油", "味精", "大豆油", "豆油", "麻油", "生油", "菜油", "食油")
PURE_EXCLUDE = ("雞尾腸", "油麵", "油面", "蜜糖雞尾")
# 明确知道同编码兄弟行有纤维值的(从数据分析确认)
BROTHER_FIBRE = {
    "HK0-1465": 32.3,   # 冬菇片 ← 冬菇/冬菇粒 32.3
    "HK0-0995": 1.3,    # 黃檸檬 ← 兄弟行 1.3
}


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    headers = list(rows[0].keys())
    progress = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))

    pure_fixed = 0
    brother_fixed = 0
    manual_rows = []

    for r in rows:
        if "CFC" not in (r.get("source") or ""):
            continue
        try:
            carb = float(r["available_carbohydrate_g"] or 0)
        except (ValueError, TypeError):
            continue
        f_raw = (r.get("dietary_fibre_g") or "").strip()
        if f_raw:  # 已有纤维,第一轮已换算
            continue
        if carb <= 1:  # 无影响
            continue

        code = (r.get("ingredient_code") or "").strip().upper()
        name = r.get("ingredient_name") or ""
        key = f"{r['ingredient_code']}|{r['ingredient_name']}"
        rec = progress.get(key)

        # 1) 兄弟行
        if code in BROTHER_FIBRE:
            fv = BROTHER_FIBRE[code]
            new_carb = max(round(carb - fv, 4), 0.0)
            r["dietary_fibre_g"] = f"{fv:.4f}"
            r["available_carbohydrate_g"] = f"{new_carb:.4f}"
            if rec is not None:
                rec["carb_total_before"] = carb
                rec["fibre_source"] = f"brother_code:{code}"
            brother_fixed += 1
            print(f"  兄弟行 {name[:20]:<22} 纤维={fv} → 可用碳水={new_carb}", flush=True)
            continue

        # 2) 纯物质(纤维物理 0)
        is_pure = (carb > 95 or any(w in name for w in PURE_WORDS)) and not any(
            x in name for x in PURE_EXCLUDE
        )
        if is_pure:
            r["dietary_fibre_g"] = "0.0000"
            r["available_carbohydrate_g"] = f"{carb:.4f}"  # 减 0 不变
            if rec is not None:
                rec["carb_total_before"] = carb
                rec["fibre_source"] = "physical_zero"
            pure_fixed += 1
            print(f"  纯物质 {name[:20]:<22} 纤维=0(物理) → 可用碳水={carb}", flush=True)
            continue

        # 3) 待人工
        manual_rows.append({
            "ingredient_code": r.get("ingredient_code", ""),
            "ingredient_name": name,
            "available_carbohydrate_g(总碳水)": carb,
            "reason": "CFC 详情纤维 ND,无兄弟行/非纯物质",
            "searched_keyword": rec.get("keyword", "") if rec else "",
        })

    # 落盘 CSV
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")

    if manual_rows:
        with MANUAL_LIST.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(manual_rows[0].keys()))
            writer.writeheader()
            writer.writerows(manual_rows)

    print(f"\n纯物质补 0: {pure_fixed} | 兄弟行补齐: {brother_fixed} | 待人工: {len(manual_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
