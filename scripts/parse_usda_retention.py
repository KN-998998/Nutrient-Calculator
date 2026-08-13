"""解析 USDA Table of Nutrient Retention Factors Release 6 (retn06.txt)。

PDF 提取后结构:每条记录 = 4位RetentionCode, 2位FoodGroupCode, 描述行,
后面跟 26 个营养素保留率(数字,可能一行多个或跨行,直到下一条记录)。

输出: usda_retention.json
  {"TURKEY,SIMMERED,WO/DRIPPINGS": {"group": "05", "sodium": 70, "energy": 100, ...}}
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path(r"F:\营养素计算工具\docs\retn06.txt")
OUT = Path(r"F:\营养素计算工具\data\usda_retention.json")

NUTRIENTS = [
    "calcium", "iron", "magnesium", "phosphorus", "potassium", "sodium", "zinc", "copper",
    "vitamin_c", "thiamin", "riboflavin", "niacin", "vitamin_b6", "folate_food", "folic_acid",
    "folate_total", "choline", "vitamin_b12", "vitamin_a_iu", "vitamin_a_re", "alcohol",
    "carotene_beta", "carotene_alpha", "cryptoxanthin", "lycopene", "lutein",
]

# 我们关心的: 钠有保留率; 宏量(能量/蛋白/脂肪/碳水)表里没有 -> 默认 100


def parse() -> dict:
    lines = SRC.read_text(encoding="utf-8").split("\n")
    records: dict[str, dict] = {}
    i = 0
    n = len(lines)
    # 定位第一条记录
    while i < n and not re.match(r"^\d{4}$", lines[i].strip()):
        i += 1

    while i + 2 < n:
        code = lines[i].strip()
        group = lines[i + 1].strip()
        desc = lines[i + 2].strip()
        if not re.match(r"^\d{4}$", code) or not re.match(r"^\d{2}$", group) or not desc:
            i += 1
            continue
        # 收集描述后的所有数字
        j = i + 3
        numbers: list[int] = []
        while j < n:
            line = lines[j].strip()
            if re.match(r"^\d{4}$", line):  # 下一条记录开始
                break
            # 提取行内所有数字(空格分隔)
            for tok in line.split():
                if re.match(r"^\d{1,3}$", tok):
                    numbers.append(int(tok))
                else:
                    break  # 非数字说明描述未结束? 保守处理: 停止
            j += 1
        if len(numbers) >= 26:
            rec = {"group": group, "description": desc}
            for k, nutrient in enumerate(NUTRIENTS):
                rec[nutrient] = numbers[k]
            records[desc] = rec
        i = j
    return records


if __name__ == "__main__":
    records = parse()
    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"解析 {len(records)} 条记录 -> {OUT}")

    # 抽样: 肉类/蔬菜的钠保留率
    import collections
    groups = collections.Counter(rec["group"] for rec in records.values())
    print(f"食物组分布: {dict(groups)}")
    for desc, rec in list(records.items())[:8]:
        print(f"  {desc[:44]:44s} 钠={rec['sodium']} 蛋白无(默认100)")
    # 常用烹调方式行
    for kw in ["RICE", "PASTA", "CHICKEN,ROASTED", "BEEF,", "POTATO,BOILED", "CARROT,"]:
        hits = [d for d in records if kw in d]
        for d in hits[:3]:
            r = records[d]
            print(f"  [{kw}] {d[:48]:48s} 钠={r['sodium']}")
