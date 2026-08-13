"""审计修复第二轮: CFC 来源修复行碳水换算(总碳水→可利用)+能量重算。

规则(官方): CFC2002Ed2 碳水=总碳水, available=总碳水-膳食纤维,
能量重算 = 4×available + 4×protein + 9×total_fat (4-9-4)。

涉及行(第一轮从官网取的 CFC 值):
- 鮮冬菇肉/鮮冬菇粒 香菇[香蕈，冬菇]: 5.2-3.3=1.9, en=1.9*4+2.2*4+0.3*9=19.1
- 蘑菇片 蘑菇(鮮蘑): 4.1-2.1=2.0, en=2.0*4+2.7*4+0.1*9=19.7
- 蒜蓉 大蒜[蒜頭]: 27.6-1.1=26.5, en=26.5*4+4.5*4+0.2*9=125.8
- 雪菜粒 芥菜[雪裏紅，雪菜]: 4.7-1.6=3.1, en=3.1*4+2.0*4+0.4*9=24.0
- 黃雪耳 銀耳(乾): 67.3-30.4=36.9, en=36.9*4+10.0*4+1.4*9=200.2
- 紹菜/<清洗>紹菜 大白菜(白梗)[黃芽白]: 3.7-0.6=3.1, en=3.1*4+1.7*4+0.2*9=21.0
- 菠蘿粒 菠蘿[鳳梨，地鳳梨]: 10.8-1.3=9.5, en=9.5*4+0.5*4+0.1*9=40.9
- 菠蘿粒（新豐）[大罐裝]: 泰源糖>碳水违和, 一并换 CFC 菠萝
幂等: 已换算则跳过。
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

WORKDIR = Path(r"F:\营养素计算工具")
DB = WORKDIR / "data" / "ingredient_nutrients.csv"

# (匹配名, 新available, 新energy, 备注)
FIX = [
    ("鮮冬菇肉 <切,開四>", 1.9, 19.1, "香菇[香蕈，冬菇] 鲜品换算"),
    ("鮮冬菇粒", 1.9, 19.1, "香菇[香蕈，冬菇] 鲜品换算"),
    ("蘑菇片", 2.0, 19.7, "蘑菇(鮮蘑) 换算"),
    ("蒜蓉（沙师弟）", 26.5, 125.8, "大蒜[蒜頭] 换算"),
    ("雪菜粒", 3.1, 24.0, "芥菜[雪裏紅，雪菜] 换算"),
    ("黃雪耳", 36.9, 200.2, "銀耳(乾)[白木耳] 换算"),
    ("紹菜", 3.1, 21.0, "大白菜(白梗)[黃芽白] 换算"),
    ("<清洗>紹菜", 3.1, 21.0, "大白菜(白梗)[黃芽白] 换算"),
    ("菠蘿粒", 9.5, 40.9, "菠蘿[鳳梨，地鳳梨] 换算"),
    ("菠蘿粒（新豐）[大罐裝]", 9.5, 40.9, "泰源糖>碳水违和→CFC菠萝"),
]


def main() -> None:
    rows = list(csv.DictReader(DB.open(encoding="utf-8-sig")))
    fieldnames = list(rows[0].keys())
    changed = 0
    notes = []
    for name, new_carb, new_energy, note in FIX:
        for row in rows:
            if row["ingredient_name"].strip() != name:
                continue
            old_carb = row["available_carbohydrate_g"]
            if old_carb and abs(float(old_carb) - new_carb) < 0.01:
                notes.append(f"[幂等跳过] {name}")
                continue
            row["available_carbohydrate_g"] = f"{new_carb:g}"
            row["energy_kcal"] = f"{new_energy:g}"
            if name == "菠蘿粒（新豐）[大罐裝]":
                row["aliases"] = "菠蘿[鳳梨，地鳳梨]"
                row["source"] = "中國疾病預防控制中心轄下的營養與食品安全所 (CFC2002Ed2)"
                row["sugars_g"] = ""
                row["sodium_mg"] = "0.8"
                row["dietary_fibre_g"] = "1.3"
                row["protein_g"] = "0.5"
                row["total_fat_g"] = "0.1"
            changed += 1
            notes.append(f"[换算] {name}: carb {old_carb} → {new_carb}, energy → {new_energy} ({note})")

    with DB.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    for line in notes:
        print(line)
    print(f"\n第二轮修改 {changed} 行")


if __name__ == "__main__":
    main()
