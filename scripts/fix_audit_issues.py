"""审计修复脚本: 修正营养库中与 CFS 官网核对发现的错误匹配/未换算行。

修复项:
A. 匹配错误(数据来源错误):
   1. 鮮冬菇肉/鮮冬菇粒 → 香菇[香蕈，冬菇](鲜品 26kcal) — 原误用 冬菇(乾) 212kcal
   2. 蘑菇片 → 蘑菇(鮮蘑)(24kcal) — 原误用 蘑菇(乾) 252kcal
   3. 蒜蓉(沙师弟) → 大蒜[蒜頭](128kcal) — 原误用 蒜蓉包(面包 338kcal)
   4. 雪菜粒 → 芥菜[雪裏紅，雪菜](27kcal) — 原误用 雪菜燒鴨絲炆米粉(混合菜)
   5. 芝士腸 → 法蘭克褔香腸(熟)(247kcal) — 原误用 芝士/忌廉意粉醬(酱料)
   6. 黃雪耳 → 銀耳(乾)[白木耳](261kcal) — 原误用 雪耳木瓜糖水(混合菜)
   7. 紹菜 → 大白菜(白梗)[黃芽白](22kcal) — 原误用 白菜(小白菜系 13kcal)
   8. 雞蛋 → 雞蛋(全隻，生)(127kcal) — 原用 全熟(137kcal), SOP 生蛋重量配生蛋值
   9. 菠蘿粒 → 菠蘿[鳳梨，地鳳梨](44kcal) — 原泰源 51kcal 且 糖>碳水 违和
B. CFC 碳水未换算(漏网行):
   10. 鮮菇粉/黑松露醬/黑松露油/合掌瓜/京蔥/什豆 — available=总碳水-纤维, 能量重算

幂等: 每行修复前检查当前值, 已修复则跳过。
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

WORKDIR = Path(r"F:\营养素计算工具")
DB = WORKDIR / "data" / "ingredient_nutrients.csv"
PROGRESS = WORKDIR / "data" / "cfs_progress.json"

# (匹配名, 正确CFS条目名, 数据来源, {字段:值})
FIX_MATCH = [
    ("鮮冬菇肉 <切,開四>", "香菇[香蕈，冬菇]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "26", "protein_g": "2.2", "total_fat_g": "0.3",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "5.2",
        "sugars_g": "", "sodium_mg": "1.4", "dietary_fibre_g": "3.3",
    }),
    ("鮮冬菇粒", "香菇[香蕈，冬菇]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "26", "protein_g": "2.2", "total_fat_g": "0.3",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "5.2",
        "sugars_g": "", "sodium_mg": "1.4", "dietary_fibre_g": "3.3",
    }),
    ("蘑菇片", "蘑菇(鮮蘑)", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "24", "protein_g": "2.7", "total_fat_g": "0.1",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "4.1",
        "sugars_g": "", "sodium_mg": "8.3", "dietary_fibre_g": "2.1",
    }),
    ("蒜蓉（沙师弟）", "大蒜[蒜頭]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "128", "protein_g": "4.5", "total_fat_g": "0.2",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "27.6",
        "sugars_g": "", "sodium_mg": "19.6", "dietary_fibre_g": "1.1",
    }),
    ("雪菜粒", "芥菜[雪裏紅，雪菜]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "27", "protein_g": "2.0", "total_fat_g": "0.4",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "4.7",
        "sugars_g": "", "sodium_mg": "30.5", "dietary_fibre_g": "1.6",
    }),
    ("芝士腸3個", "法蘭克褔香腸(熟)", "澳洲新西蘭食品標準管理局 (AFCD R2)", {
        "energy_kcal": "247", "protein_g": "14.3", "total_fat_g": "19.9",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "3.4",
        "sugars_g": "0.2", "sodium_mg": "770", "dietary_fibre_g": "1.8",
    }),
    ("黃雪耳", "銀耳(乾)[白木耳]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "261", "protein_g": "10.0", "total_fat_g": "1.4",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "67.3",
        "sugars_g": "", "sodium_mg": "82.1", "dietary_fibre_g": "30.4",
    }),
    ("紹菜", "大白菜(白梗)[黃芽白]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "22", "protein_g": "1.7", "total_fat_g": "0.2",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "3.7",
        "sugars_g": "", "sodium_mg": "89.3", "dietary_fibre_g": "0.6",
    }),
    ("<清洗>紹菜", "大白菜(白梗)[黃芽白]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "22", "protein_g": "1.7", "total_fat_g": "0.2",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "3.7",
        "sugars_g": "", "sodium_mg": "89.3", "dietary_fibre_g": "0.6",
    }),
    ("雞蛋", "雞蛋(全隻，生)", "澳洲新西蘭食品標準管理局 (AFCD R2)", {
        "energy_kcal": "127", "protein_g": "12.6", "total_fat_g": "8.5",
        "saturated_fat_g": "2.3", "trans_fat_g": "", "available_carbohydrate_g": "0.3",
        "sugars_g": "", "sodium_mg": "150", "dietary_fibre_g": "0",
    }),
    ("菠蘿粒", "菠蘿[鳳梨，地鳳梨]", "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)", {
        "energy_kcal": "44", "protein_g": "0.5", "total_fat_g": "0.1",
        "saturated_fat_g": "", "trans_fat_g": "", "available_carbohydrate_g": "10.8",
        "sugars_g": "", "sodium_mg": "0.8", "dietary_fibre_g": "1.3",
    }),
]

# 碳水未换算行: (匹配名, 新available_carb, 能量重算: 4*碳水+4*蛋白+9*脂肪)
FIX_CARB = [
    ("鮮菇粉", 32.3, 212.1),      # 64.6-32.3
    ("黑松露醬", 14.4, 242.1),    # 31.6-17.2
    ("黑松露油", 14.4, 242.1),
    ("合掌瓜肉 <切角>", 2.6, 16.1),  # 3.8-1.2
    ("合掌瓜肉 <切絲>", 2.6, 16.1),
    ("京蔥", 5.2, 30.3),           # 6.5-1.3
    ("什豆", 5.2, 35.9),           # 7-1.8
]

NUTRIENT_FIELDS = [
    "energy_kcal", "protein_g", "total_fat_g", "saturated_fat_g", "trans_fat_g",
    "available_carbohydrate_g", "sugars_g", "sodium_mg", "dietary_fibre_g",
]


def main() -> None:
    backup = DB.with_name(f"ingredient_nutrients.bak-{time.strftime('%Y%m%d%H%M%S')}-审计修复2")
    # 已有备份则不再覆盖
    rows = list(csv.DictReader(DB.open(encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys())
    changed = 0
    notes = []

    def find_rows(name: str):
        return [r for r in rows if r["ingredient_name"].strip() == name]

    # A. 匹配修复
    for name, cfs_name, source, values in FIX_MATCH:
        hits = find_rows(name)
        if not hits:
            notes.append(f"[跳过] 无行: {name}")
            continue
        for row in hits:
            old_energy = row["energy_kcal"]
            if old_energy == values["energy_kcal"]:
                notes.append(f"[已修/幂等] {name} energy={old_energy}")
                continue
            row["aliases"] = cfs_name
            row["source"] = source
            for field, val in values.items():
                row[field] = val
            changed += 1
            notes.append(f"[修复] {name}: energy {old_energy} → {values['energy_kcal']} (←{cfs_name})")

    # B. 碳水未换算行
    for name, new_carb, new_energy in FIX_CARB:
        for row in find_rows(name):
            old_carb = row["available_carbohydrate_g"]
            if abs(float(old_carb or 0) - new_carb) < 0.01:
                notes.append(f"[已修/幂等] {name} carb={old_carb}")
                continue
            row["available_carbohydrate_g"] = f"{new_carb:g}"
            row["energy_kcal"] = f"{new_energy:g}"
            changed += 1
            notes.append(f"[碳水换算] {name}: carb {old_carb} → {new_carb}, energy → {new_energy}")

    with DB.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    for line in notes:
        print(line)
    print(f"\n共修改 {changed} 行; 备份: {backup.name if backup.exists() else '(使用前置备份)'}")


if __name__ == "__main__":
    main()
