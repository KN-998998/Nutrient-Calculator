"""convert_dish_sop.py —— 把「菜品SOP」格式转换为标准「X月X餐配料sop」工作簿。

背景
----
核心解析器 nutrition_tool/sop.py 只认标准格式：
  - sheet 名必须包含 "配料sop"（如 "5月A餐配料sop"）
  - 列结构: A日期 / B菜名 / C食材系統 / D配料名称 / E单位 / F克重(数字) / G配料代码
而业务端有时拿到的是另一种格式：「一行一道菜 + 配方(含克重)文本列」，
如 "熟米饭180g、牛肋条150g、蒜片15g"。本脚本负责把后者归一化成标准格式，
供 sop.py / 桌面工具直接消费，核心解析器零改动。

用法
----
  python scripts/convert_dish_sop.py <输入.xlsx> [输出.xlsx] [--meal-set A] [--date 2026-08-12]

输入格式识别（自动）
  - 表头行包含「菜品名称」(或 菜名/名称) 列 + 「配方」列(表头含"配方")
  - 配方文本以 、 ， , ; ； 分隔；每个配料项支持:
      名称NNNg / 名称NNN克        -> 克重直接取
      名称NNNml / NNN毫升         -> 按密度1.0换算克重(标"待人工核验")
      名称NNN个/粒/片/根/条/只/块  -> 括号克重优先((80g) 或（80g）);
                                    无括号则查 QTY_GRAMS 表, 查不到留空标警告
      名称NNNg（煮熟NNNg）        -> 取第一个数字(生重, 符合 CFS 原始可食部口径)
  - 特殊归一化: 冰块 -> 清水(营养等价, 均为0能量水)

输出
----
  标准配料sop 工作簿: sheet "X月X餐配料sop" (X = --meal-set, 默认 A),
  列结构对齐 sop.py 期望。转换中无法确定克重的项输出到 stdout 警告清单。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from openpyxl import Workbook, load_workbook
except ImportError as exc:  # pragma: no cover
    raise SystemExit("需要 openpyxl: pip install -r requirements.txt") from exc

# ---------------------------------------------------------------- 配置

# 表头识别: 菜名列 / 配方列
NAME_HEADERS = {"菜品名称", "菜名", "名称"}
RECIPE_HEADER_KEY = "配方"

# 数量单位 -> 每单位克重 (默认值, 全部「待人工核验」, 以营养师确认为准)
QTY_GRAMS: dict[str, float] = {
    "温泉蛋": 50.0,   # 中等大小全蛋可食部
    "鸡蛋": 50.0,
    "蛋": 50.0,
    "牛肉饼": 80.0,
    "菠萝片": 40.0,
    "虾仁": 8.0,      # 单粒虾仁
    "香水柠檬": 8.3,  # 3片25g
    "柠檬": 8.3,
    "黄九芽": 5.0,    # 装饰性配菜
}

# 体积单位 -> 密度假设 (待人工核验; 糖浆实际密度>1, 此处保守取1)
VOLUME_DENSITY_G_PER_ML = 1.0

# 营养等价归一化: 冰块(0能量水) -> 清水
WATER_SYNONYMS = {"冰块", "冰", "冰塊"}

# 分隔符
SEPARATORS = re.compile(r"[、，,;；/|]")

# 先剥离尾部括号注记, 再解析主体
_PAREN_RE = re.compile(r"^(?P<main>.+?)(?:\s*[（(](?P<paren>[^（）()]*)[）)])?$")
_MAIN_RE = re.compile(
    r"^\s*(?P<name>.+?)\s*"
    r"(?:(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>g|克|G|ml|毫升|ML|mL|个|粒|片|根|条|只|块|塊|枚|份|串|杯))?\s*$"
)
_PAREN_G_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:g|克)")


# ---------------------------------------------------------------- 解析

class ParsedItem:
    __slots__ = ("name", "grams", "unit", "qty", "note")

    def __init__(self, name: str, grams: float | None, unit: str = "", qty: str = "", note: str = ""):
        self.name = name
        self.grams = grams
        self.unit = unit
        self.qty = qty
        self.note = note


def parse_recipe_text(text: str) -> list[ParsedItem]:
    """把配方文本拆成配料项列表。返回项按文本顺序。"""
    items: list[ParsedItem] = []
    for raw in SEPARATORS.split(text):
        raw = raw.strip()
        if not raw:
            continue
        # 1) 剥掉尾部括号("干意面70g（煮熟220g）" / "牛肉饼1个（80g）")
        pm = _PAREN_RE.match(raw)
        main = pm.group("main").strip() if pm else raw
        paren = pm.group("paren").strip() if pm and pm.group("paren") else ""

        # 2) 解析主体: 名称 + 可选数量/单位
        mm = _MAIN_RE.match(main)
        if not mm:
            items.append(ParsedItem(raw, None, note="无法解析格式"))
            continue
        name = mm.group("name").strip()
        unit = (mm.group("unit") or "").lower()
        qty = mm.group("qty") or ""

        # 营养等价归一化
        if name in WATER_SYNONYMS:
            name = "清水"

        # 3) 括号克重: 仅当单位是数量词且主体没带克重时采用(如 "牛肉饼1个（80g）")
        paren_grams: float | None = None
        if paren and unit in ("个", "粒", "片", "根", "条", "只", "块", "塊", "枚", "份", "串", "杯"):
            pg = _PAREN_G_RE.search(paren)
            if pg:
                paren_grams = float(pg.group(1))

        grams: float | None = None
        note = ""
        if unit == "g" or unit == "克":
            grams = float(qty)
        elif unit in ("ml", "毫升"):
            grams = round(float(qty) * VOLUME_DENSITY_G_PER_ML, 1)
            note = "体积按密度1.0换算克重(待人工核验)"
        elif unit in ("个", "粒", "片", "根", "条", "只", "块", "塊", "枚", "份", "串", "杯"):
            if paren_grams:
                grams = paren_grams
            elif name in QTY_GRAMS:
                grams = QTY_GRAMS[name]
                note = f"数量{qty}{unit}按默认表换算{grams}g(待人工核验)"
            else:
                note = f"数量{qty}{unit}无克重来源(待人工核验)"
        else:
            # 只有名称(无数量无单位)
            note = "无克重信息(待人工核验)"
        items.append(ParsedItem(name, grams, unit=unit, qty=qty, note=note))
    return items


def find_header_row(worksheet) -> tuple[int, int, int]:
    """在 worksheet 里找表头行, 返回 (行号1基, 菜名列idx, 配方列idx); 找不到抛 ValueError。"""
    for row_idx, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
        if not row:
            continue
        name_col = recipe_col = -1
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            s = str(cell).strip()
            if s in NAME_HEADERS:
                name_col = col_idx
            elif RECIPE_HEADER_KEY in s:
                recipe_col = col_idx
        if name_col >= 0 and recipe_col >= 0:
            return row_idx, name_col, recipe_col
    raise ValueError("找不到表头(需包含「菜品名称」和「配方」列)")


def convert_workbook(src_path: Path, meal_set: str, service_date: str) -> tuple[Path, list[str]]:
    """转换工作簿, 返回 (输出路径, 警告清单)。"""
    wb_in = load_workbook(src_path, read_only=True, data_only=True)
    warnings: list[str] = []
    wb_out = Workbook()
    ws_out = wb_out.active
    ws_out.title = f"{meal_set}月{meal_set}餐配料sop"
    ws_out.append(["日期", "菜名", "食材/系統名稱", "配料名称", "单位", "克重", "配料代码"])

    sheet_count = 0
    try:
        for ws in wb_in.worksheets:
            try:
                header_row, name_col, recipe_col = find_header_row(ws)
            except ValueError:
                continue  # 非菜品SOP格式的 sheet, 跳过
            sheet_count += 1
            for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
                if name_col >= len(row) or recipe_col >= len(row):
                    continue
                dish_name = str(row[name_col] or "").strip()
                recipe_text = str(row[recipe_col] or "").strip()
                if not dish_name or not recipe_text:
                    continue
                items = parse_recipe_text(recipe_text)
                if not items:
                    warnings.append(f"[{dish_name}] 配方文本为空或无法解析")
                    continue
                # 标准格式约定: 菜名只写在该菜第一行, 后续配料行留空(sop.py 以 B 列非空为菜式边界)
                for idx, it in enumerate(items):
                    name_cell = dish_name if idx == 0 else ""
                    ws_out.append([service_date, name_cell, "", it.name, it.unit, it.grams, ""])
                    if it.note:
                        warnings.append(f"[{dish_name}] {it.name}: {it.note}")
    finally:
        wb_in.close()

    if sheet_count == 0:
        wb_out.close()
        raise ValueError("输入文件里没有「菜品SOP」格式的 sheet(需含 菜品名称+配方 表头)")

    out_path = src_path.parent / f"{src_path.stem}_配料sop.xlsx"
    wb_out.save(out_path)
    wb_out.close()
    return out_path, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="菜品SOP 格式 xlsx")
    ap.add_argument("output", type=Path, nargs="?", help="输出路径(默认: 输入同目录 *_配料sop.xlsx)")
    ap.add_argument("--meal-set", default="A", help="餐别代号, 用于 sheet 名 (默认 A)")
    ap.add_argument("--date", default="", help="服务日期, 写入 A 列 (默认留空)")
    args = ap.parse_args()

    out, warnings = convert_workbook(args.input.resolve(), args.meal_set, args.date)
    if args.output:
        out.replace(args.output)
        out = args.output.resolve()
    print(f"已生成: {out}")
    print(f"警告 {len(warnings)} 条:")
    for w in warnings:
        print("  ⚠", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
