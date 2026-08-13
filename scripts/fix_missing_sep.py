"""fix_missing_sep.py —— 9月重叠未匹配食材修复: 第一阶段(别名/去污染, 零网络)。

问题背景
--------
9月菜单×5/6月SOP 重叠验证有 51 种食材未匹配, 其中一部分营养库**已有等价食材**,
只是: (a) 别名污染(批量抓取时给多行设了相同 alias → 消歧永远歧义),
    (b) 缺少命名变体别名(SOP 用 甘荀絲/鮮茄角/牛冧片/椰菜絲/福花 等写法)。

本脚本只做 CSV 别名修复, 不做网络抓取。修改前自动备份。

修复清单
--------
1. 别名污染: DTL0079 糖行只保留 白砂糖 行的 alias; 蠔油行只保留 蠔油 行的 alias
2. 别名补充(SOP 名 → 库内行):
   甘荀絲 → 甘筍絲
   鮮茄角/蕃茄角 → 鮮茄 <切角>
   牛冧片 → 牛片
   椰菜絲 → 西椰菜（切絲）
   福花 → 福建椰菜花<切朵>
"""
from __future__ import annotations

import csv
import shutil
from datetime import datetime
from pathlib import Path

WORKDIR = Path(__file__).resolve().parent.parent
CSV_PATH = WORKDIR / "data" / "ingredient_nutrients.csv"

# (ingredient_code, ingredient_name) 唯一确定要改的行
ALIAS_CLEANUP: dict[tuple[str, str], str] = {
    # 只保留 canonical 行的 alias; 其他糖行清掉 alias
    ("DTL0079", "南韓幼砂糖（包/30kg)"): "",
    ("DTL0079", "30KG 韓國幼砂糖"): "",
    ("DTL0079", "砂糖/30KG 韓國幼砂糖"): "",
    ("DTL0079", "白砂糖/30KG 韓國幼砂糖（德利行）"): "",
    ("DTL0079", "白砂糖/30KG 韓國幼砂糖"): "",
    ("", "砂糖"): "",  # 空编码 砂糖 行也带着 alias 白砂糖 → 清掉
    # 蠔油: 只保留 canonical 蠔油 行
    ("DTL0158", "蠔油/財神蠔油"): "",
    ("DTL0158", "錦珍財神蠔油"): "",
    ("HK0-1595", "12X510G 李錦記素食蠔油"): "",
    ("HK0-1595", "素蠔油"): "",
    # 上轮误加 鮮茄角 别名(与 HK0-2289 鮮茄角 行冲突) → 重置为仅 番茄/番茄角/蕃茄角
    ("HK0-1373", "鮮茄 <切角>"): "番茄|番茄角|蕃茄角",
    # 荷蘭豆/珍珠雞 双行同名歧义 → 清非 canonical 行的别名
    ("HK0-2408", "荷蘭豆肉"): "",
    ("", "珍珠雞"): "",
}

# 给 target 行追加别名(合并到现有 aliases, 用 | 分隔)
ALIAS_ADD: dict[str, tuple[str, list[str]]] = {
    # target_code -> (target_name, [新别名])
    "甘筍絲": ("VHF024", ["甘荀絲"]),
    "鮮茄 <切角>": ("HK0-1373", ["蕃茄角", "番茄角"]),  # 鮮茄角 已有独立行 HK0-2289, 不加
    "牛片": ("HK0-3235", ["牛冧片"]),
    "西椰菜（切絲）": ("HK0-1082", ["椰菜絲"]),
    "福建椰菜花<切朵>": ("HK0-1567", ["福花"]),
    "魚柳": ("HK0-1312", ["300+龍利柳(白盒)", "龍利柳"]),
    "牛肉丸2個": ("HK0-1861", ["肉丸2個"]),
}

# 重命名(消除同名歧义): (code, old_name) -> new_name
RENAME: dict[tuple[str, str], str] = {
    ("", "牛肉丸2個"): "牛肉丸",  # 与 HK0-1861 同名歧义 → 改名保留
    ("", "珍珠雞"): "珍珠雞(舊)",  # 与 HK0-1474 同名歧义 → 改名保留
}


def main() -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    headers = list(rows[0].keys())

    shutil.copy2(CSV_PATH, f"data/ingredient_nutrients.bak-{datetime.now().strftime('%Y%m%d%H%M')}")
    changes = 0

    # 1) 清别名污染
    for (code, name), new_alias in ALIAS_CLEANUP.items():
        for r in rows:
            if r["ingredient_code"].strip() == code and r["ingredient_name"].strip() == name:
                old = r.get("aliases", "")
                if old != new_alias:
                    print(f"  清alias: {code} {name}: {old!r} -> {new_alias!r}")
                    r["aliases"] = new_alias
                    changes += 1

    # 2) 补别名
    for target_name, (code, new_aliases) in ALIAS_ADD.items():
        for r in rows:
            if r["ingredient_code"].strip() == code and r["ingredient_name"].strip() == target_name:
                existing = set(x.strip() for x in (r.get("aliases") or "").split("|") if x.strip())
                added = [a for a in new_aliases if a not in existing]
                if added:
                    print(f"  加alias: {code} {target_name} +{added}")
                    r["aliases"] = "|".join(sorted(existing | set(added)))
                    changes += 1

    # 3) 重命名(消歧)
    for (code, old_name), new_name in RENAME.items():
        for r in rows:
            if r["ingredient_code"].strip() == code and r["ingredient_name"].strip() == old_name:
                print(f"  改名: {code or '(无码)'} {old_name} -> {new_name}")
                r["ingredient_name"] = new_name
                changes += 1

    if changes:
        with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=headers)
            w.writeheader()
            w.writerows(rows)
    print(f"\n改动 {changes} 处, 已写回 {CSV_PATH.name}")
    return 0


if __name__ == "__main__":
    main()
