"""Build an auditable nutrition review workbook for a SOP file.

The workbook contains:
- overview and methodology
- primary/secondary dish sheets with the eight Hong Kong nutrition values
- ingredient coverage with per-100g values and provenance
- piece-weight estimates and condiment/brand source inventory
- a gap sheet that stays empty when every ingredient has a usable value

Usage:
    python -X utf8 scripts/build_review_workbook.py ^
        "outputs/2026年...sop....xlsx" ^
        "outputs/2026年9月午餐_营养计算_全食材覆盖.xlsx"
"""
from __future__ import annotations

import argparse
import collections
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.models import NUTRIENT_FIELDS, REQUIRED_NUTRIENT_FIELDS
from nutrition_tool.repository import (
    normalize_name,
    source_label,
    source_match_tier,
)
from nutrition_tool.sop import read_sop_workbook
from web_app.app import get_repo


FIELD_LABELS = {
    "energy_kcal": "能量 kcal",
    "protein_g": "蛋白质 g",
    "total_fat_g": "总脂肪 g",
    "saturated_fat_g": "饱和脂肪 g",
    "trans_fat_g": "反式脂肪 g",
    "available_carbohydrate_g": "可利用碳水 g",
    "sugars_g": "糖 g",
    "sodium_mg": "钠 mg",
    "dietary_fibre_g": "膳食纤维 g",
}
REQUIRED_LABELS = [FIELD_LABELS[f] for f in REQUIRED_NUTRIENT_FIELDS]

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
TITLE_FONT = Font(bold=True, size=15, color="1F4E78")
SUB_FONT = Font(bold=True, size=10, color="404040")
WARN_FILL = PatternFill("solid", fgColor="FFF2CC")
BAD_FILL = PatternFill("solid", fgColor="FCE4D6")
OK_FILL = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="D9E2F3")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _header(sheet, row: int, headers: list[str]) -> None:
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=column, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def _widths(sheet, widths: dict[str, float]) -> None:
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width


def _write_title(sheet, title: str, subtitle: str, columns: int) -> int:
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    cell = sheet.cell(row=1, column=1, value=title)
    cell.font = TITLE_FONT
    cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 26
    sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)
    sheet.cell(row=2, column=1, value=subtitle).font = SUB_FONT
    return 4


def _method(profile) -> str:
    text = f"{profile.source} {profile.source_type}"
    if source_match_tier(profile) == "water_zero":
        return "清水（零营养）"
    if profile.source_type in {"cfs_official", "official_hk"}:
        return "香港 CFS/FRL 官方资料"
    if profile.source_type == "china_food_composition":
        return "CFC 中国食物成分资料"
    if any(marker in text for marker in ("等權", "等权", "均值", "平均")):
        return "同类产品/食材多来源均值"
    if "標籤" in text or "标签" in text:
        return "包装营养标签（每100g换算）"
    if "CFC" in text:
        return "CFC 中国食物成分资料"
    if any(marker in text for marker in ("AFCD", "USDA", "NZ2024", "CNF", "MEXT", "DTU")):
        return "国际官方食物成分库"
    if profile.source_type == "manual_estimate":
        return "人工估算/同类替代"
    if profile.source_type == "reference_other":
        return "国际官方成分库/同类均值"
    return "参考数据"


def _value_check(row) -> str:
    """Flag physically inconsistent nutrient combinations without changing values."""
    values = row.get("values") or {}
    issues: list[str] = []

    def number(field):
        value = values.get(field)
        return float(value) if isinstance(value, (int, float)) else None

    sugar = number("sugars_g")
    carb = number("available_carbohydrate_g")
    fat = number("total_fat_g")
    saturated = number("saturated_fat_g")
    trans = number("trans_fat_g")
    energy = number("energy_kcal")
    protein = number("protein_g")
    if sugar is not None and carb is not None and sugar > carb + 0.001:
        issues.append("糖>可利用碳水")
    if saturated is not None and fat is not None and saturated > fat + 0.001:
        issues.append("饱和脂肪>总脂肪")
    if trans is not None and fat is not None and trans > fat + 0.001:
        issues.append("反式脂肪>总脂肪")
    if None not in (energy, protein, fat, carb):
        calculated = 4 * protein + 9 * fat + 4 * carb
        if calculated > 0 and abs(energy - calculated) / calculated > 0.15:
            issues.append(f"4-9-4能量偏差{(energy - calculated) / calculated:+.0%}")
    return "；".join(issues)


def _clean(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _top(counter, limit: int = 3) -> str:
    if not counter:
        return ""
    return "、".join(key for key, _ in counter.most_common(limit))


def load_sop_context(path: str, used_sheets=None) -> dict:
    """Read codes/specs/suppliers from the raw SOP sheets for the audit table."""
    from openpyxl import load_workbook

    used = {name.strip() for name in used_sheets} if used_sheets else None
    context: dict[str, dict] = {}
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            if "配料sop" not in sheet.title:
                continue
            if used is not None and sheet.title.strip() not in used:
                continue
            for row in sheet.iter_rows(min_row=2, values_only=True):
                name = _clean(row[3]) if len(row) > 3 else ""
                if not name or "合計" in name:
                    continue
                item = context.setdefault(name, {
                    "codes": collections.Counter(),
                    "specs": collections.Counter(),
                    "suppliers": collections.Counter(),
                })
                code = _clean(row[8]) if len(row) > 8 else ""
                spec = _clean(row[9]) if len(row) > 9 else ""
                supplier = _clean(row[11]) if len(row) > 11 else ""
                if code:
                    item["codes"][code] += 1
                if spec and not spec.replace(".", "", 1).isdigit():
                    item["specs"][spec] += 1
                if supplier and supplier != "0" and not supplier.replace(".", "", 1).isdigit():
                    item["suppliers"][supplier] += 1
    finally:
        workbook.close()
    return context


def build_coverage(results, repository, context=None):
    """Return one row per SOP ingredient name that is actually used."""
    context = context or {}
    coverage: dict[str, dict] = {}
    for result in results:
        for contribution in result.contributions:
            name = contribution.ingredient_name
            item = coverage.setdefault(name, {
                "name": name,
                "codes": collections.Counter(),
                "specs": collections.Counter(),
                "suppliers": collections.Counter(),
                "source_names": set(),
                "uses": 0,
                "dishes": set(),
                "profile": None,
                "recipes": set(),
            })
            item["uses"] += 1
            raw_context = context.get(name, {})
            item["codes"].update(raw_context.get("codes", ()))
            item["specs"].update(raw_context.get("specs", ()))
            item["suppliers"].update(raw_context.get("suppliers", ()))
            item["dishes"].add((result.school_stage, result.meal_set, result.recipe_name))
            item["recipes"].add(result.recipe_name)
            if contribution.ingredient_code:
                item["codes"][contribution.ingredient_code] += 1
            if item["profile"] is None:
                item["profile"] = repository.find(
                    code=contribution.ingredient_code,
                    name=name,
                )
            if item["profile"] is None:
                # Fall back to the profile the calculator actually used.
                item["profile"] = repository.find(name=contribution.source_name)
            item["source_names"].add(contribution.source_name)

    rows = []
    for name, item in coverage.items():
        profile = item["profile"]
        is_water = name == "清水"
        row = {
            "name": name,
            "uses": item["uses"],
            "dish_count": len(item["dishes"]),
            "codes": "" if is_water else _top(item["codes"]) + ("（SOP内多個編碼）" if len(item["codes"]) > 1 else ""),
            "specs": "" if is_water else _top(item["specs"]) + ("（SOP内多個規格）" if len(item["specs"]) > 1 else ""),
            "suppliers": "" if is_water else _top(item["suppliers"]),
            "profile_name": profile.ingredient_name if profile else "",
            "source_name": "、".join(sorted(item["source_names"])[:3]),
            "values": {},
            "missing": [],
            "source": profile.source if profile else "",
            "source_id": profile.source_food_id if profile else "",
            "source_url": profile.source_url if profile else "",
            "source_date": profile.source_date if profile else "",
            "source_type": profile.source_type if profile else "",
            "tier": source_match_tier(profile) if profile else "unmatched",
            "label": source_label(profile) if profile else "未匹配",
            "method": _method(profile) if profile else "未匹配",
            "note": repository.correction_notes.get(normalize_name(name), "") if profile else "",
            "matched": profile is not None,
        }
        if profile:
            for field in NUTRIENT_FIELDS:
                row["values"][field] = getattr(profile, field, None)
            row["missing"] = [
                field for field in REQUIRED_NUTRIENT_FIELDS
                if field in set(profile.missing_nutrients)
            ]
        else:
            row["values"] = {field: None for field in NUTRIENT_FIELDS}
            row["missing"] = list(REQUIRED_NUTRIENT_FIELDS)
        rows.append(row)
    rows.sort(key=lambda r: (-r["uses"], r["name"]))
    return rows


def _write_dish_sheet(sheet, results) -> None:
    headers = [
        "菜品名称", "餐别", "SOP工作表", "输入食材总重 g",
        "能量 kcal", "蛋白质 g", "总脂肪 g", "饱和脂肪 g",
        "反式脂肪 g", "可利用碳水 g", "糖 g", "钠 mg",
        "状态", "复核提示数",
    ]
    start = _write_title(
        sheet,
        "学生餐八项营养计算结果（每份）",
        "数值完整不代表采购规格已确认；所有菜品均需营养师复核后上架。逐条提示见「复核明细」。",
        len(headers),
    )
    _header(sheet, start, headers)
    for index, result in enumerate(results, start=start + 1):
        if result.status == "incomplete":
            nutrient_values = [None] * len(REQUIRED_NUTRIENT_FIELDS)
        else:
            nutrient_values = [
                round(result.nutrients_per_serving[field], 3)
                for field in REQUIRED_NUTRIENT_FIELDS
            ]
        row = [
            result.recipe_name,
            result.meal_set,
            result.source_sheet,
            round(result.input_weight_g, 3),
            *nutrient_values,
            "八项完整（待复核）" if result.status != "incomplete" else "不完整",
            len(result.warnings),
        ]
        for column, value in enumerate(row, start=1):
            cell = sheet.cell(row=index, column=column, value=value)
            cell.border = BORDER
            if column <= 4:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            elif column <= 12:
                cell.alignment = Alignment(horizontal="right", vertical="top")
                cell.number_format = "0.000"
            else:
                cell.alignment = CENTER
            if result.status == "review":
                cell.fill = WARN_FILL
            elif result.status == "incomplete":
                cell.fill = BAD_FILL
        if result.warnings:
            comment = Comment("\n".join(result.warnings)[:30000], "营养素计算工具")
            sheet.cell(row=index, column=1).comment = comment
    sheet.freeze_panes = sheet.cell(row=start + 1, column=2)
    sheet.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(results)}"
    _widths(sheet, {"A": 42, "B": 7, "C": 20, "D": 13})
    for column in range(5, 13):
        sheet.column_dimensions[get_column_letter(column)].width = 12
    sheet.column_dimensions["M"].width = 18
    sheet.column_dimensions["N"].width = 11


def _write_overview(sheet, sop_path, results, coverage, errors, estimated):
    sheet.sheet_view.showGridLines = False
    _write_title(
        sheet,
        "营养计算复核总览",
        f"输入：{Path(sop_path).name}｜生成日期：{date.today().isoformat()}",
        4,
    )
    primary = sum(1 for result in results if result.school_stage == "小學")
    secondary = sum(1 for result in results if result.school_stage == "中學")
    incomplete = sum(1 for result in results if result.status == "incomplete")
    unmatched = [row for row in coverage if not row["matched"]]
    missing_required = [row for row in coverage if row["matched"] and row["missing"]]
    all_eight = [row for row in coverage if row["matched"] and not row["missing"]]
    sources = collections.Counter(row["method"] for row in coverage)
    rows = [
        ("SOP 菜式记录", len(results), "小学 / 中学", f"{primary} / {secondary}"),
        ("SOP 解析异常", len(errors), "未匹配食材", len(unmatched)),
        ("唯一 SOP 食材名", len(coverage), "八项完整食材", len(all_eight)),
        ("缺少必需营养项的食材", len(missing_required), "克重估算记录", len(estimated)),
        ("菜品状态：八项完整待复核", sum(1 for r in results if r.status != "incomplete"), "不完整", incomplete),
        ("数值校验提示食材", sum(1 for row in coverage if _value_check(row)), "数值校验提示项", "见食材营养值页"),
    ]
    row = 4
    _header(sheet, row, ["盘点指标", "数值", "盘点指标", "数值"])
    row += 1
    for left_name, left_value, right_name, right_value in rows:
        sheet.cell(row=row, column=1, value=left_name).font = SUB_FONT
        sheet.cell(row=row, column=2, value=left_value).alignment = Alignment(horizontal="center")
        sheet.cell(row=row, column=3, value=right_name).font = SUB_FONT
        sheet.cell(row=row, column=4, value=right_value).alignment = Alignment(horizontal="center")
        for column in range(1, 5):
            sheet.cell(row=row, column=column).border = BORDER
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="食材来源与匹配方式").font = TITLE_FONT
    row += 1
    _header(sheet, row, ["匹配方式", "食材数", "占比", "说明"])
    row += 1
    total = len(coverage) or 1
    explanations = {
        "香港 CFS/FRL 官方资料": "食安中心营养资料库/食物研究化验所原始值",
        "品牌／包裝營養標籤": "实际品牌或同规格包装标签，按每100g换算",
        "CFC 中国食物成分资料": "中国疾控 CFC2002Ed2；碳水已换算可利用碳水",
        "非香港國際參考資料": "AFCD/USDA/NZ/CNF 等官方成分库，或同类均值",
        "人工整理參考資料": "人工补录的参考档案",
        "通用估算資料": "同类产品/食材均值或按件估重",
        "來源待確認資料": "来源待确认，仅作暂算",
        "未匹配": "没有可用档案",
        "国际官方成分库/同类均值": "AFCD/USDA/NZ/CNF 等官方值，或同种食材多来源均值",
        "国际官方食物成分库": "AFCD/USDA/NZ/CNF 等单一条目",
        "同类产品/食材多来源均值": "2–5 款同类产品/同种食材逐项算术平均",
        "包装营养标签（每100g换算）": "实际品牌或同规格包装标签，按每100g换算",
        "参考数据": "来源未细分的参考值，需复核",
        "人工估算/同类替代": "同类产品/食材均值或按件估重",
    }
    for label, count in sources.most_common():
        sheet.cell(row=row, column=1, value=label).border = BORDER
        sheet.cell(row=row, column=2, value=count).alignment = Alignment(horizontal="center")
        sheet.cell(row=row, column=3, value=round(count / total, 4)).number_format = "0.0%"
        sheet.cell(row=row, column=4, value=explanations.get(label, "")).alignment = WRAP
        for column in range(1, 5):
            sheet.cell(row=row, column=column).border = BORDER
        row += 1

    row += 2
    sheet.cell(row=row, column=1, value="口径与限制").font = TITLE_FONT
    notes = [
        "1. 八项 = 能量、蛋白质、总脂肪、饱和脂肪、反式脂肪、可利用碳水、糖、钠；全部按每100g可食部存储，按SOP克重折算。",
        "2. 优先香港 CFS/FRL；其次实际品牌标签；再次同类产品/食材均值或国际官方成分库；均保留来源与估算说明。",
        "3. 调味品先查本身包装标签；无标签时用3–5款同类产品每100g均值（本表按实际取得的2–5款记录，未凑数）。",
        "4. 非克重单位仅在SOP克重无效时按件估重；优先用SOP规格反推（如魚蓉燒賣2000g/140粒、披薩180g/個），其次品牌/市售单重。",
        "5. 全部菜品当前为“八项完整、待营养师复核”；估算值不等于供应商实测，采购规格确认后应重算。",
    ]
    for note in notes:
        row += 1
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        cell = sheet.cell(row=row, column=1, value=note)
        cell.alignment = WRAP
        sheet.row_dimensions[row].height = 30
    _widths(sheet, {"A": 38, "B": 16, "C": 18, "D": 75})


def _write_coverage(sheet, coverage):
    fields = list(REQUIRED_NUTRIENT_FIELDS) + ["dietary_fibre_g"]
    headers = [
        "SOP食材名", "使用次数", "涉及菜品数", "SOP编码", "规格/单位", "供应商",
        *[FIELD_LABELS[f] for f in fields],
        "来源类别", "匹配方式", "来源说明", "来源URL", "核查日期", "状态", "数值校验", "估算/匹配说明",
    ]
    start = _write_title(
        sheet,
        "全量食材营养值（每100g可食部）",
        f"共 {len(coverage)} 个实际使用的食材名；八项完整 {sum(1 for r in coverage if r['matched'] and not r['missing'])} 个。空白表示来源未报告；本表所有行均已有可用于八项计算的数值。",
        len(headers),
    )
    _header(sheet, start, headers)
    for index, row in enumerate(coverage, start=start + 1):
        values = [row["values"].get(field) for field in fields]
        status = "八项完整" if row["matched"] and not row["missing"] else (
            "缺：" + "、".join(FIELD_LABELS[f] for f in row["missing"]) if row["matched"] else "未匹配"
        )
        cells = [
            row["name"], row["uses"], row["dish_count"], row["codes"], row["specs"],
            row["suppliers"], *values, row["label"], row["method"], row["source"],
            row["source_url"], row["source_date"], status, _value_check(row), row["note"],
        ]
        for column, value in enumerate(cells, start=1):
            cell = sheet.cell(row=index, column=column, value=value)
            cell.border = BORDER
            cell.alignment = WRAP if column in (1, 5, 6, 16, 17, 18, 20, 22, 23) else Alignment(vertical="top")
            if 7 <= column <= 15 and isinstance(value, (int, float)):
                cell.number_format = "0.000"
            if column == 21:
                cell.fill = OK_FILL if status == "八项完整" else BAD_FILL
                cell.alignment = CENTER
            if column == 22 and value:
                cell.fill = WARN_FILL
                cell.alignment = WRAP
    sheet.freeze_panes = sheet.cell(row=start + 1, column=2)
    sheet.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(coverage)}"
    _widths(sheet, {"A": 30, "B": 9, "C": 10, "D": 16, "E": 16, "F": 10})
    for column in range(7, 16):
        sheet.column_dimensions[get_column_letter(column)].width = 11
    _widths(sheet, {"P": 20, "Q": 24, "R": 55, "S": 45, "T": 11, "U": 18, "V": 28, "W": 70})


def _write_estimates(sheet, estimated):
    headers = ["学段", "餐别", "菜品名称", "食材", "估算克重 g", "SOP原始值", "估算依据"]
    start = _write_title(
        sheet,
        "按件/按规格估重记录",
        "仅在SOP克重为0或无法解析时启用；优先SOP规格反推，其次品牌/市售单重。",
        len(headers),
    )
    _header(sheet, start, headers)
    for index, item in enumerate(estimated, start=start + 1):
        cells = [
            item["stage"], item["meal_set"], item["recipe"], item["name"],
            round(item["grams"], 3), item["raw"], item["note"],
        ]
        for column, value in enumerate(cells, start=1):
            cell = sheet.cell(row=index, column=column, value=value)
            cell.border = BORDER
            cell.alignment = WRAP if column in (3, 4, 7) else Alignment(vertical="top")
            if column == 5:
                cell.number_format = "0.000"
    sheet.freeze_panes = sheet.cell(row=start + 1, column=2)
    _widths(sheet, {"A": 8, "B": 7, "C": 42, "D": 22, "E": 12, "F": 14, "G": 90})


def _write_condiments(sheet, coverage):
    keywords = (
        "醬", "酱", "汁", "油", "鹽", "盐", "糖", "粉", "醋", "露", "味精",
        "蠔油", "蚝油", "茄汁", "沙爹", "沙嗲", "柱侯", "柱候", "咖喱", "咖哩",
        "照燒", "瑞士汁", "ok汁", "蜜糖", "豆瓣", "豆辦", "黑松露", "美極", "雞粉",
    )
    rows = [row for row in coverage if any(keyword in row["name"] for keyword in keywords)]
    headers = ["SOP调味品/酱料名", "使用次数", "八项数值", "来源类别", "匹配方式", "来源/均值说明", "来源URL"]
    start = _write_title(
        sheet,
        "调味品与品牌来源盘点",
        "先查本身包装标签；无标签时才用同类产品每100g均值。均值至少记录实际采用的品牌数，不用单一品牌冒充实际采购品。",
        len(headers),
    )
    _header(sheet, start, headers)
    for index, row in enumerate(rows, start=start + 1):
        values = " / ".join(
            f"{FIELD_LABELS[field].split()[0]}={row['values'].get(field):g}"
            if isinstance(row["values"].get(field), (int, float)) else f"{FIELD_LABELS[field].split()[0]}=—"
            for field in REQUIRED_NUTRIENT_FIELDS
        )
        cells = [row["name"], row["uses"], values, row["label"], row["method"], row["source"], row["source_url"]]
        for column, value in enumerate(cells, start=1):
            cell = sheet.cell(row=index, column=column, value=value)
            cell.border = BORDER
            cell.alignment = WRAP
    sheet.freeze_panes = sheet.cell(row=start + 1, column=2)
    _widths(sheet, {"A": 30, "B": 9, "C": 78, "D": 22, "E": 26, "F": 70, "G": 55})


def _write_gaps(sheet, coverage, errors):
    headers = ["SOP食材名", "SOP编码", "缺少的必需营养项", "当前来源", "处理建议"]
    start = _write_title(
        sheet,
        "缺口食材",
        "本表为空表示所有实际使用的SOP食材均已有八项数值。数量栏「1個」不是食材名，不列入缺口。",
        len(headers),
    )
    _header(sheet, start, headers)
    gaps = [row for row in coverage if not row["matched"] or row["missing"]]
    if not gaps:
        sheet.cell(row=start + 1, column=1, value="无缺口：全部食材均有可用于八项计算的数值。")
        sheet.merge_cells(start_row=start + 1, start_column=1, end_row=start + 1, end_column=5)
        sheet.cell(row=start + 1, column=1).fill = OK_FILL
    for index, row in enumerate(gaps, start=start + 1):
        values = [row["name"], row["codes"], "、".join(FIELD_LABELS[f] for f in row["missing"]), row["source"], "补查标签/同类均值"]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=index, column=column, value=value)
            cell.border = BORDER
            cell.alignment = WRAP
            cell.fill = BAD_FILL
    if errors:
        index = start + len(gaps) + 2
        sheet.cell(row=index, column=1, value="SOP解析异常").font = SUB_FONT
        for offset, error in enumerate(errors, start=1):
            sheet.cell(row=index + offset, column=1, value=str(error))
    _widths(sheet, {"A": 32, "B": 18, "C": 40, "D": 55, "E": 30})


def _write_details(sheet, results):
    headers = ["学段", "餐别", "菜品名称", "状态", "输入食材总重 g", "复核提示"]
    start = _write_title(
        sheet,
        "复核明细",
        "逐菜列出估算、替代来源、非香港来源及组成校验提示；营养师按此复核。",
        len(headers),
    )
    _header(sheet, start, headers)
    for index, result in enumerate(results, start=start + 1):
        cells = [
            result.school_stage, result.meal_set, result.recipe_name,
            "八项完整（待复核）" if result.status != "incomplete" else "不完整",
            round(result.input_weight_g, 3), "\n".join(result.warnings),
        ]
        for column, value in enumerate(cells, start=1):
            cell = sheet.cell(row=index, column=column, value=value)
            cell.border = BORDER
            cell.alignment = WRAP if column in (3, 6) else Alignment(vertical="top")
            if column == 5:
                cell.number_format = "0.000"
    sheet.freeze_panes = sheet.cell(row=start + 1, column=2)
    _widths(sheet, {"A": 8, "B": 7, "C": 42, "D": 18, "E": 12, "F": 120})


def build_workbook(sop_path: str, output_path: str, sheet_names=None) -> dict:
    recipes, errors = read_sop_workbook(sop_path, sheet_names)
    repository = get_repo("hong_kong")
    results = [calculate_recipe(recipe, repository) for recipe in recipes]
    used_sheets = {result.source_sheet for result in results}
    coverage = build_coverage(results, repository, load_sop_context(sop_path, used_sheets))

    estimated = []
    for result in results:
        for contribution in result.contributions:
            if not contribution.weight_is_estimated:
                continue
            estimated.append({
                "stage": result.school_stage,
                "meal_set": result.meal_set,
                "recipe": result.recipe_name,
                "name": contribution.ingredient_name,
                "grams": contribution.input_weight_g,
                "raw": contribution.weight_estimate_note.split("；")[0][:60],
                "note": contribution.weight_estimate_note,
            })

    workbook = Workbook()
    overview = workbook.active
    overview.title = "复核总览"
    _write_overview(overview, sop_path, results, coverage, errors, estimated)

    primary = workbook.create_sheet("小学")
    secondary = workbook.create_sheet("中学")
    _write_dish_sheet(primary, [r for r in results if r.school_stage == "小學"])
    _write_dish_sheet(secondary, [r for r in results if r.school_stage == "中學"])

    _write_coverage(workbook.create_sheet("食材营养值"), coverage)
    _write_estimates(workbook.create_sheet("克重估算"), estimated)
    _write_condiments(workbook.create_sheet("调味品与品牌来源"), coverage)
    _write_gaps(workbook.create_sheet("缺口食材"), coverage, errors)
    _write_details(workbook.create_sheet("复核明细"), results)

    workbook.save(output_path)
    workbook.close()

    return {
        "recipes": len(results),
        "primary": sum(1 for r in results if r.school_stage == "小學"),
        "secondary": sum(1 for r in results if r.school_stage == "中學"),
        "incomplete": sum(1 for r in results if r.status == "incomplete"),
        "coverage": len(coverage),
        "all_eight": sum(1 for r in coverage if r["matched"] and not r["missing"]),
        "unmatched": sum(1 for r in coverage if not r["matched"]),
        "missing_required": sum(1 for r in coverage if r["matched"] and r["missing"]),
        "estimated": len(estimated),
        "errors": len(errors),
        "output": output_path,
    }


def build_simple_workbook(sop_path: str, output_path: str, sheet_names=None) -> dict:
    """Write the minimal primary/secondary sheets: dish name + eight values."""
    from nutrition_tool.nutrition_export import write_school_nutrition_excel

    recipes, errors = read_sop_workbook(sop_path, sheet_names)
    repository = get_repo("hong_kong")
    results = [calculate_recipe(recipe, repository) for recipe in recipes]
    counts = write_school_nutrition_excel(
        [result for result in results if result.school_stage == "小學"],
        [result for result in results if result.school_stage == "中學"],
        output_path,
    )
    return {
        "recipes": len(results),
        "primary": counts["primary"],
        "secondary": counts["secondary"],
        "incomplete": sum(1 for result in results if result.status == "incomplete"),
        "errors": len(errors),
        "output": output_path,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成学生餐营养复核工作簿")
    parser.add_argument("sop", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sheets", help="逗号分隔的SOP工作表名")
    parser.add_argument("--simple-output", type=Path, help="另存只含菜名和八项营养的小学/中学两页工作簿")
    args = parser.parse_args(argv)
    sheets = [s.strip() for s in args.sheets.split(",") if s.strip()] if args.sheets else None
    summary = build_workbook(str(args.sop), str(args.output), sheets)
    if args.simple_output:
        summary["simple"] = build_simple_workbook(str(args.sop), str(args.simple_output), sheets)
    print(summary)
    return 0 if summary["unmatched"] == 0 and summary["missing_required"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
