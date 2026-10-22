"""把 SOP 菜谱计算结果转换并导出为不同的展示格式。

营养师最终结果使用“小學/中學”两个工作表，每行只含菜品名称和 8 项营养。
旧的菜式管理和商品上架转换函数暂时保留，供既有调用方兼容使用。

字段对齐系统菜式管理列表:
  菜式編號 | SET | 餐名 | 主菜 | 主食材類別 | 具體主食材 | 主食/穀物 | 配菜(蔬菜) |
  小食 | 醬汁/風味 | 烹調方式 | 能量(kcal) | 蛋白質(g) | 總脂肪(g) | 飽和脂肪(g) |
  反式脂肪(g) | 碳水化合物(g) | 糖(g) | 鈉(mg) | 成本 | 圖片網址 | 常規菜單 | 過敏源

自动推断规则(第一版够用级, 营养师可在系统内修改):
- SET: 来自 SOP sheet 名 (5月A餐配料sop -> A)
- 餐名: 清洗后的菜名 (去 #★● 标记)
- 主食材類別: 按主要蛋白質食材推断 (雞/豬/牛/海鮮/蛋/素/其他)
- 具體主食材: 主要蛋白質食材名
- 主食/穀物: 米/飯/意粉/麵條/米粉/烏冬等
- 配菜: 蔬菜类食材
- 醬汁/風味: 主食类型判断 (意粉/通粉 -> 西式, 飯/麵 -> 港式)
- 烹調方式: 菜名关键词 (炒/蒸/焗/炆/煮/炸/煎/灼/燴)
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from .models import RecipeResult

# ---- 菜式管理表头(与系统一致) ----
DISH_HEADERS = [
    "菜式編號", "SET", "學段", "餐名", "主菜", "主食材類別", "具體主食材", "主食/穀物",
    "配菜(蔬菜)", "小食", "醬汁/風味", "烹調方式",
    "能量(kcal)", "蛋白質(g)", "總脂肪(g)", "飽和脂肪(g)", "反式脂肪(g)",
    "碳水化合物(g)", "糖(g)", "鈉(mg)",
    "成本", "圖片網址", "常規菜單", "過敏源",
]

# 8 项营养 -> 菜式管理列名
CALCULATION_STANDARD_COL = "計算標準"
CALCULATION_STANDARD_LABELS = {
    "hong_kong": "香港標準",
    "mainland": "內地標準",
}
DISH_HEADERS.insert(-2, CALCULATION_STANDARD_COL)

NUTRIENT_TO_DISH_COL = {
    "energy_kcal": "能量(kcal)",
    "protein_g": "蛋白質(g)",
    "total_fat_g": "總脂肪(g)",
    "saturated_fat_g": "飽和脂肪(g)",
    "trans_fat_g": "反式脂肪(g)",
    "available_carbohydrate_g": "碳水化合物(g)",
    "sugars_g": "糖(g)",
    "sodium_mg": "鈉(mg)",
}

# 商品上架模板固定列名。工具只自动填写「商品名称」和 E 列「商品详情」；
# 分类、图片、规格、库存、上架状态、过敏源等业务字段留给营养师团队。
STORE_UPLOAD_HEADERS = [
    "商品名称",
    "所属分类（请填写已设置的商品分类名称）",
    "商品图片路径（多图用，符合隔开）",
    "商品规格（格式：规格名称-属性名称-价格）（多规格用；符合隔开  例“份量-均量-10；味道-均量-10）（多属性用，符合隔开  例“份量-大份-15，中份-10，小份-5”）",
    "商品详情",
    "虚拟销量",
    "包装费(元/个)",
    "商品库存(-1表示无限库存)",
    "库存预警数",
    "饥饿营销数",
    "是否上架(填1表示上架，填2表示不上架)",
    "最少购买数(最小值为1)",
    "商品属性(填0表示不设置，填1表示新品，填2表示招牌，填3表示推荐)",
    "营养详情(格式:营养名称:营养值)(多营养使用;符号隔开“能量:657;蛋白质:400;维生素A:200",
    "过敏源(请输入系统内有的过敏源，多个逗号隔开)",
]

STORE_DETAIL_FIELDS = (
    ("能量", "能量(kcal)", "Kcal"),
    ("蛋白質", "蛋白質(g)", "g"),
    ("碳水化合物", "碳水化合物(g)", "g"),
    ("脂肪", "總脂肪(g)", "g"),
    ("糖", "糖(g)", "g"),
    ("飽和脂肪", "飽和脂肪(g)", "g"),
    ("反式脂肪", "反式脂肪(g)", "g"),
    ("鈉", "鈉(mg)", "mg"),
)

# 烹调方式关键词(按优先级)
COOKING_RULES = [
    (r"炒", "炒"), (r"蒸", "蒸"), (r"焗", "焗"), (r"烤", "焗"), (r"燒", "焗"),
    (r"炆", "炆"), (r"燉", "燉"), (r"煲", "煲"), (r"煮", "煮"),
    (r"炸", "炸"), (r"煎", "煎"), (r"灼", "灼"), (r"烚", "灼"), (r"燴", "燴"),
    (r"配飯|飯$", "配"),
]

# 主食材類別推断: (匹配词, 类别)
# 规则顺序很重要: 素類 必须在 雞/豬/牛 之前(素肉片/素雞絲 不能判成荤);
# "奶|乳" 在 "牛" 前(牛奶≠牛肉); "蛋" 在 "雞" 前(雞蛋→蛋類)。
# "肉片|肉絲|肉粒|肉碎|肉餅" 等通用名为学生餐默认猪肉(推断, 营养师可改)
PROTEIN_CATEGORY_RULES = [
    (r"素|豆腐|豆乾|枝竹|新餐肉|新魚柳|新豬肉|素肉|素雞|素牛", "素類"),
    (r"蛋", "蛋類"),
    (r"奶|乳", "奶類"),
    (r"雞|鷄", "雞肉"),
    (r"豬|叉燒|餐肉|火腿|肉片|肉絲|肉粒|肉碎|肉餅|肉丁|梅肉|豚肉", "豬肉"),
    (r"牛", "牛肉"),
    (r"魚|蝦|蟹|蜆|帶子|墨魚|魷魚|海鮮", "海鮮"),
]

# 调味料/配料特征(跳过, 不当主食材)
SEASONING_PATTERN = re.compile(
    r"油$|大豆油|麻油|香油|糖|鹽|醬|汁|醋|雞粉|生粉|粟粉|麵粉|澄麵|料酒|酒$|"
    r"咖喱|咖哩|蠔油|生抽|老抽|味精|清水|^水$|香葉|蒜蓉|蔥花|胡椒粉|花椒|八角"
)

# 主食推断
STAPLE_RULES = [
    (r"飯|米", "飯"), (r"意粉|通粉|蜆殼粉|貝殼粉|扭扭粉|螺絲粉", "意粉"),
    (r"麵|烏冬|米粉|米線|瀨粉|河粉", "麵"),
]

# 蔬菜关键词(用于配菜识别)
VEGETABLE_WORDS = [
    "菜", "瓜", "豆", "菇", "筍", "茄", "椒", "蔥", "蒜", "薑", "洋蔥", "椰菜",
    "西蘭", "薯", "芋", "蓮藕", "木耳", "芽菜", "葉", "蘆筍", "芹", "瓜苗", "苗",
]

# 配菜识别排除(蛋白类主食材/加工品, 不是蔬菜)
SIDE_EXCLUDE_PATTERN = re.compile(
    r"豆腐|豆乾|枝竹|腐皮|素肉|素雞|素牛|新餐肉|午餐肉|火腿|魚蛋|"
    r"雞蛋|蛋$|豬肉|牛肉|雞肉|魚柳|蝦仁|墨魚|蜆|帶子|蟹柳"
)


def _clean_dish_name(name: str) -> str:
    """清洗菜名: 去 #★●▲□◆※ 等标记和多余空格。"""
    text = re.sub(r"[#★●▲□◆※不辣]+", "", name or "")
    text = re.sub(r"\s+", "", text)
    return text.strip()


def _detect_cooking(recipe_name: str) -> str:
    for pattern, method in COOKING_RULES:
        if re.search(pattern, recipe_name):
            return method
    return ""


def _detect_category_and_protein(ingredients: list, recipe_name: str = "") -> tuple[str, str]:
    """返回 (主食材類別, 具體主食材)。

    策略: 1) 食材优先(跳过调味料); 2) 菜名兜底(如 SOP 主食材叫"肉片"时)。
    """
    for ing in ingredients:
        name = ing.ingredient_name
        if SEASONING_PATTERN.search(name):
            continue
        for pattern, category in PROTEIN_CATEGORY_RULES:
            if re.search(pattern, name):
                return category, name
    # 菜名兜底: "薯仔洋蔥牛肉片配飯" 含"牛" -> 牛肉; 具體主食材留空由营养师填
    for pattern, category in PROTEIN_CATEGORY_RULES:
        if re.search(pattern, recipe_name):
            return category, ""
    return "其他", ""


def _detect_staple(ingredients: list) -> str:
    for ing in ingredients:
        name = ing.ingredient_name
        if SEASONING_PATTERN.search(name):
            continue  # 麵粉/生粉等是配料, 不是主食
        for pattern, staple in STAPLE_RULES:
            if re.search(pattern, name):
                return staple
    return ""


def _detect_side_dishes(ingredients: list) -> str:
    """配菜(蔬菜): 收集蔬菜类食材名, 去重取前几个(排除调味料和蛋白类)。"""
    veggies = []
    for ing in ingredients:
        name = ing.ingredient_name
        if SEASONING_PATTERN.search(name):
            continue
        if SIDE_EXCLUDE_PATTERN.search(name):
            continue
        if any(v in name for v in VEGETABLE_WORDS):
            # 去掉加工词
            clean = re.sub(r"[<>\s切絲切粒切丁切條切片切半圈切朵切角清洗一開二]+", "", name)
            if clean and clean not in veggies:
                veggies.append(clean)
    return "、".join(veggies[:4])


def _detect_flavor(staple: str) -> str:
    if "意粉" in staple or "通粉" in staple or "蜆殼" in staple or "貝殼" in staple:
        return "西式"
    return "港式"


def result_to_dish_row(result: RecipeResult, dish_no: str = "") -> dict:
    """RecipeResult -> 菜式管理一行。"""
    ingredients = [c for c in result.contributions if c.nutrients]
    category, protein = _detect_category_and_protein(ingredients, result.recipe_name)
    staple = _detect_staple(ingredients)
    side = _detect_side_dishes(ingredients)
    cooking = _detect_cooking(result.recipe_name)

    row = {h: "" for h in DISH_HEADERS}
    calculation_standard = getattr(result, "calculation_standard", "hong_kong")
    standard_label = CALCULATION_STANDARD_LABELS.get(
        calculation_standard, calculation_standard
    )
    fallback_labels = []
    for contribution in result.contributions:
        if not getattr(contribution, "requires_review", False):
            continue
        label = getattr(contribution, "source_label", "來源待確認")
        if label not in fallback_labels:
            fallback_labels.append(label)
    if fallback_labels:
        standard_label += "（後備：" + "、".join(fallback_labels) + "）"
    row[CALCULATION_STANDARD_COL] = standard_label
    row["菜式編號"] = dish_no
    row["SET"] = result.meal_set
    row["學段"] = getattr(result, "school_stage", "")
    row["餐名"] = _clean_dish_name(result.recipe_name)
    # 主菜需要独立的菜品拆分规则；无法可靠拆分时留空，避免重复餐名造成误导。
    row["主菜"] = ""
    row["主食材類別"] = category
    row["具體主食材"] = protein
    row["主食/穀物"] = staple
    row["配菜(蔬菜)"] = side
    row["醬汁/風味"] = _detect_flavor(staple)
    row["烹調方式"] = cooking
    for field, col in NUTRIENT_TO_DISH_COL.items():
        # Incomplete recipes contain only a partial sum; keep nutrient cells
        # blank so a partial result is never mistaken for a valid zero.
        value = None if result.status == "incomplete" else result.nutrients_per_serving.get(field)
        row[col] = round(value, 2) if value is not None else ""
    # 未匹配食材提示放进过敏源? 不, 放常规菜单列做状态标注
    row["常規菜單"] = result.status
    return row


def _excel_safe(value: object) -> object:
    """Excel 公式注入防护: 文本以 = + - @ 开头时加单引号前缀。"""
    if isinstance(value, str) and value and value[0] in "=+-@":
        return "'" + value
    return value


def _compact_number(value: object) -> str:
    """Return a non-negative numeric value with at most two decimal places."""
    if isinstance(value, bool) or value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    if not number.is_finite() or number < 0:
        return ""
    rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(rounded, "f").rstrip("0").rstrip(".")


def format_store_nutrition_detail(dish_row: dict) -> str:
    """Format the supplied template's E-column eight-nutrient description."""
    parts = []
    for label, column, unit in STORE_DETAIL_FIELDS:
        value = _compact_number(dish_row.get(column, ""))
        if value == "":
            return ""
        parts.append(f"{label}{value}({unit})")
    return " ".join(parts)


def dish_row_to_store_upload_row(dish_row: dict) -> dict:
    """Map one auditable dish row to the storefront upload template."""
    upload_row = {header: "" for header in STORE_UPLOAD_HEADERS}
    meal_set = str(dish_row.get("SET") or "").strip()
    school_stage = str(dish_row.get("學段") or "").strip()
    dish_name = str(dish_row.get("餐名") or "").strip()
    prefix = meal_set
    if school_stage:
        prefix += f"({school_stage})" if prefix else school_stage
    upload_row["商品名称"] = f"{prefix}{dish_name}" if prefix else dish_name
    upload_row["商品详情"] = format_store_nutrition_detail(dish_row)
    return upload_row


def write_store_upload_excel(
    rows: Iterable[dict],
    path: str,
    template_path: str | None = None,
) -> int:
    """Fill the supplied 15-column template in separate primary/secondary sheets."""
    from copy import copy
    from pathlib import Path
    from openpyxl import load_workbook

    if template_path is None:
        template_path = str(
            Path(__file__).resolve().parent.parent
            / "data"
            / "templates"
            / "聖類斯上架模版.xlsx"
        )
    workbook = load_workbook(template_path)
    try:
        primary_sheet = workbook.active
        actual_headers = [
            primary_sheet.cell(1, column).value
            for column in range(1, len(STORE_UPLOAD_HEADERS) + 1)
        ]
        if actual_headers != STORE_UPLOAD_HEADERS or primary_sheet.max_column != len(STORE_UPLOAD_HEADERS):
            raise ValueError("上架模板表头与项目要求的15列不一致")

        primary_sheet.title = "小学标准"
        secondary_sheet = workbook.copy_worksheet(primary_sheet)
        secondary_sheet.title = "中学标准"
        sheets_by_stage = {
            "小學": primary_sheet,
            "中學": secondary_sheet,
        }
        row_styles = {
            worksheet.title: [
                copy(worksheet.cell(2, column)._style)
                for column in range(1, len(STORE_UPLOAD_HEADERS) + 1)
            ] if worksheet.max_row >= 2 else []
            for worksheet in (primary_sheet, secondary_sheet)
        }
        row_heights = {
            worksheet.title: worksheet.row_dimensions[2].height
            if worksheet.max_row >= 2 else None
            for worksheet in (primary_sheet, secondary_sheet)
        }
        for worksheet in (primary_sheet, secondary_sheet):
            if worksheet.max_row > 1:
                worksheet.delete_rows(2, worksheet.max_row - 1)

        count = 0
        for dish_row in rows:
            upload_row = dish_row_to_store_upload_row(dish_row)
            if not upload_row["商品详情"]:
                continue
            stage = str(dish_row.get("學段") or "").strip()
            worksheet = sheets_by_stage.get(stage)
            if worksheet is None:
                raise ValueError(
                    f"菜品「{dish_row.get('餐名') or upload_row['商品名称']}」的學段「{stage}」無法識別，"
                    "只接受小學或中學"
                )
            worksheet.append(
                [_excel_safe(upload_row.get(header, "")) for header in STORE_UPLOAD_HEADERS]
            )
            count += 1
            for column, style in enumerate(row_styles[worksheet.title], start=1):
                worksheet.cell(worksheet.max_row, column)._style = copy(style)
            row_height = row_heights[worksheet.title]
            if row_height is not None:
                worksheet.row_dimensions[worksheet.max_row].height = row_height

        for worksheet in (primary_sheet, secondary_sheet):
            worksheet.auto_filter.ref = worksheet.dimensions
        workbook.active = workbook.index(primary_sheet)
        workbook.save(path)
        return count
    finally:
        workbook.close()


def write_dish_rows_excel(rows: Iterable[dict], path: str) -> int:
    """Write already materialized dish rows to the TT dish-management workbook."""
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "菜式"
    ws.append(DISH_HEADERS)
    count = 0
    for row in rows:
        ws.append([_excel_safe(row.get(header, "")) for header in DISH_HEADERS])
        count += 1
    for col_idx, header in enumerate(DISH_HEADERS, start=1):
        width = max(len(header) * 2, 12)
        ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 30)
    wb.save(path)
    return count


def write_dish_excel(results: Iterable[RecipeResult], path: str, dish_no_start: int = 100001) -> int:
    """导出菜式管理 Excel(用 openpyxl)。返回行数。"""
    rows = (
        result_to_dish_row(result, dish_no=str(dish_no_start + idx))
        for idx, result in enumerate(results)
    )
    return write_dish_rows_excel(rows, path)
