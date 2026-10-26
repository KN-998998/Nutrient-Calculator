from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from .models import IngredientAmount, Recipe


_HEADER_ALIASES = {
    "recipe_name": ("菜品名称", "菜品名", "菜品", "菜名", "餐名", "品名", "菜式", "菜餚", "商品名称", "商品名稱", "dish", "dishname", "recipe", "recipename", "menuitem", "名称", "名字"),
    "recipe_text": ("sop", "sop内容", "sop內容", "做法", "作法", "配方", "食谱", "食譜", "烹调", "烹調", "制作方法", "製作方法", "制作步骤", "製作步驟", "操作步骤", "操作步驟", "用料说明", "用料說明", "recipe text", "instructions", "method"),
    "ingredient_name": ("食材", "食材名称", "食材名稱", "食材系统名称", "食材系統名稱", "原料", "原料名称", "原料名稱", "配料", "配料名称", "配料名稱", "原材料", "食物", "用料", "物料", "材料", "ingredient", "ingredientname", "food", "foodname", "material"),
    "grams": ("克重", "克数", "克數", "重量", "净重", "淨重", "净含量", "淨含量", "用量", "每人用量", "每人下单量", "每人下單量", "人均餐盒实际下单用量", "人均餐盒實際下單用量", "实际下单用量", "實際下單用量", "下单用量", "下單用量", "每份克重", "数量克", "數量克", "克", "g", "gram", "grams", "weight", "amount", "quantity", "qty", "netweight"),
    "code": ("食材编码", "食材編碼", "原料编码", "原料編碼", "物料编码", "物料編碼", "编码", "編碼", "代码", "代碼", "货号", "貨號", "物料号", "物料號", "ingredientcode", "materialcode", "code", "sku"),
    "package_spec": ("規格/單位", "规格/单位", "包裝規格", "包装规格", "規格", "规格"),
    "component": ("食材系统名称", "食材系統名稱", "系统名称", "系統名稱", "组件", "組件", "分类", "分類", "category", "component", "group"),
    "date": (
        "日期", "服务日期", "服務日期", "出餐日期", "date", "servicedate",
        # The September SOP stores the service date as an Excel serial in the
        # first column under the visual header "編號/圖片"; the legacy parser
        # already reads column 0 as the date.
        "編號/圖片", "编号/图片",
    ),
    "meal_set": ("餐别", "餐別", "set", "mealset", "meal"),
}


def _normalise_label(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


_NORMALISED_ALIASES = {
    role: tuple(_normalise_label(alias) for alias in aliases)
    for role, aliases in _HEADER_ALIASES.items()
}


def _header_role(value: object) -> tuple[str | None, int]:
    label = _normalise_label(value)
    if not label:
        return None, 0
    scored: list[tuple[int, str]] = []
    for role, aliases in _NORMALISED_ALIASES.items():
        for alias in aliases:
            if label == alias:
                scored.append((100, role))
            elif alias and alias in label:
                scored.append((50 + min(len(alias), 20), role))
    if not scored:
        return None, 0
    scored.sort(reverse=True)
    return scored[0][1], scored[0][0]


SCHOOL_STAGES = ("小學", "中學")


def _school_stage(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if "中小學" in text or "中小学" in text:
        return ""
    is_primary = "小學" in text or "小学" in text
    is_secondary = "中學" in text or "中学" in text
    if is_primary == is_secondary:
        return ""
    return "小學" if is_primary else "中學"


def _stage_weight_columns(header_row: tuple[object, ...]) -> dict[str, int]:
    """Return per-serving gram columns explicitly labelled by school stage."""
    columns: dict[str, int] = {}
    for column_index, value in enumerate(header_row):
        role, _ = _header_role(value)
        stage = _school_stage(value)
        if role == "grams" and stage and stage not in columns:
            columns[stage] = column_index
    return columns


TOTAL_MARKERS = {"合計生重", "合计生重", "食材/系統名稱", "食材/系统名称"}
WATER_NAMES = {"清水", "水"}
_COUNT_RE = re.compile(
    r"(?P<count>\d+(?:\.\d+)?)\s*(?P<unit>個|个|隻|只|粒|條|条|塊|块|件|片)"
)
_COUNT_UNIT_NORMALISATION = {
    "個": "個", "个": "個", "隻": "隻", "只": "隻", "粒": "粒",
    "條": "條", "条": "條", "塊": "塊", "块": "塊", "件": "件", "片": "片",
}
_PACK_WEIGHT_RE = re.compile(
    r"(?P<weight>\d+(?:\.\d+)?)\s*(?P<unit>kg|公斤|千克|g|克|公克)\s*/\s*(?P<container>袋|包|盒|箱)",
    re.IGNORECASE,
)
_PACK_COUNT_RE = re.compile(
    r"(?P<count>\d+(?:\.\d+)?)\s*(?P<unit>個|个|隻|只|粒|條|条|塊|块|件|片)\s*/\s*(?P<container>袋|包|盒|箱)"
)

# A per-piece weight explicitly written in the SOP specification column,
# e.g. "180G/個".  This is a stated weight, not a market estimate, so it must
# not be flagged as weight_is_estimated.
_UNIT_WEIGHT_RE = re.compile(
    r"(?P<weight>\d+(?:\.\d+)?)\s*(?P<unit>kg|公斤|千克|g|克|公克)\s*[/／]\s*"
    r"(?P<each>個|个|隻|只|粒|條|条|塊|块|件|片)",
    re.IGNORECASE,
)


def _portion_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = _COUNT_RE.sub("", text)
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


def _load_portion_estimates() -> tuple[dict[str, dict[str, object]], list[dict[str, object]]]:
    path = Path(__file__).resolve().parent.parent / "data" / "portion_estimates.json"
    if not path.exists():
        return {}, []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items: dict[str, dict[str, object]] = {}
    for item in payload.get("items", []):
        for name in (item.get("name", ""), *item.get("aliases", [])):
            key = _portion_key(name)
            if key:
                items[key] = item
    return items, payload.get("recipe_specific_estimates", [])


_PORTION_ESTIMATES, _RECIPE_SPECIFIC_ESTIMATES = _load_portion_estimates()


def _clean_count_suffix(value: str) -> str:
    return _COUNT_RE.sub("", value).strip()


def _specified_unit_weight(*, count_hint: object, package_spec: object) -> tuple[float, str] | None:
    """Use a per-piece weight explicitly stated in the SOP specification column.

    Example: package_spec="180G/個", count_hint="披薩 1个" -> (180.0,
    "按SOP規格180G/個×1個").  This is a stated weight, not an estimate.
    """
    specification = unicodedata.normalize("NFKC", str(package_spec or ""))
    match = _UNIT_WEIGHT_RE.search(specification)
    if not match:
        return None
    serving = _COUNT_RE.search(str(count_hint or ""))
    if not serving:
        return None
    serving_unit = _COUNT_UNIT_NORMALISATION.get(serving.group("unit"), "")
    specified_unit = _COUNT_UNIT_NORMALISATION.get(match.group("each"), "")
    if not serving_unit or serving_unit != specified_unit:
        return None
    weight_g = float(match.group("weight"))
    if match.group("unit").casefold() in {"kg", "公斤", "千克"}:
        weight_g *= 1000
    count = float(serving.group("count"))
    return weight_g * count, f"按SOP規格{match.group(0)}×{count:g}{serving.group('unit')}"


def _estimate_portion_weight(
    *, recipe_name: str, ingredient_name: str, component_name: str, count_cell: object,
    package_spec: object = None, allow_recipe_specific: bool = True,
) -> tuple[float, str] | None:
    serving_count = None
    for text in (ingredient_name, component_name, count_cell):
        serving_count = _COUNT_RE.search(str(text or ""))
        if serving_count:
            break
    if serving_count:
        specification = unicodedata.normalize("NFKC", str(package_spec or ""))
        pack_weight = _PACK_WEIGHT_RE.search(specification)
        pack_count = _PACK_COUNT_RE.search(specification)
        serving_unit = _COUNT_UNIT_NORMALISATION[serving_count.group("unit")]
        package_unit = (
            _COUNT_UNIT_NORMALISATION[pack_count.group("unit")] if pack_count else ""
        )
        if (pack_weight and pack_count
                and pack_weight.group("container") == pack_count.group("container")
                and (serving_unit == package_unit or "個" in {serving_unit, package_unit})
                and float(pack_count.group("count")) > 0):
            weight_g = float(pack_weight.group("weight"))
            if pack_weight.group("unit").casefold() in {"kg", "公斤", "千克"}:
                weight_g *= 1000
            count = float(serving_count.group("count"))
            grams = weight_g / float(pack_count.group("count")) * count
            note = f"按SOP規格{pack_weight.group(0)}÷約{pack_count.group(0)}×{count:g}{serving_count.group('unit')}暫估"
            return grams, note

    ingredient_key = _portion_key(ingredient_name)
    recipe_key = _portion_key(recipe_name)
    if allow_recipe_specific:
        for rule in _RECIPE_SPECIFIC_ESTIMATES:
            recipe_fragment = _portion_key(rule.get("recipe_contains", ""))
            aliases = {_portion_key(name) for name in rule.get("ingredient_aliases", [])}
            if recipe_fragment and recipe_fragment in recipe_key and ingredient_key in aliases:
                return float(rule["grams"]), str(rule.get("note") or "菜式專用估算")

    item = _PORTION_ESTIMATES.get(ingredient_key)
    if item is None:
        return None
    expected_unit = str(item.get("unit", ""))
    accepted_units = {expected_unit, *item.get("alternate_units", [])}
    for text in (ingredient_name, component_name, count_cell):
        match = _COUNT_RE.search(str(text or ""))
        if not match:
            continue
        unit = _COUNT_UNIT_NORMALISATION.get(match.group("unit"), "")
        if unit not in accepted_units:
            continue
        count = float(match.group("count"))
        grams = count * float(item["grams_per_unit"])
        note = str(item.get("note") or f"{item['grams_per_unit']:g}g/{expected_unit} × {count:g}{unit}")
        return grams, note
    return None


def _excel_date(value: object) -> str:
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (int, float)) and value > 30000:
        return (datetime(1899, 12, 30) + timedelta(days=int(value))).strftime("%Y-%m-%d")
    return str(value or "").strip()


def _numeric_grams(value: object, *, sheet: str, row: int, ingredient: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{sheet}!F{row} {ingredient}: 克重不能是布尔值")
    if isinstance(value, (int, float)):
        grams = float(value)
    else:
        raw = str(value or "").strip()
        try:
            grams = float(raw)
        except ValueError as exc:
            raise ValueError(f"{sheet}!F{row} {ingredient}: 克重不是数字 ({raw or '空白'})") from exc
    import math
    if not math.isfinite(grams):
        raise ValueError(f"{sheet}!F{row} {ingredient}: 克重不是有限数值 ({grams!r})")
    return grams


_WEIGHT_RE = re.compile(
    r"(?P<value>[+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*"
    r"(?P<unit>kg|公斤|千克|g|克|公克)",
    re.IGNORECASE,
)


def _parse_weight_value(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("克重不能是布尔值")
    if isinstance(value, (int, float)):
        grams = float(value)
    else:
        raw = str(value or "").strip()
        match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*(kg|公斤|千克|g|克|公克)?", raw, re.IGNORECASE)
        if not match:
            raise ValueError(f"克重不是数字 ({raw or '空白'})")
        grams = float(match.group(1))
        if (match.group(2) or "").casefold() in {"kg", "公斤", "千克"}:
            grams *= 1000
    import math
    if not math.isfinite(grams):
        raise ValueError(f"克重不是有限数值({grams!r})")
    return grams


def _embedded_weight(value: object) -> tuple[str, float] | None:
    text = str(value or "").strip()
    match = _WEIGHT_RE.search(text)
    if not match:
        return None
    grams = float(match.group("value"))
    if match.group("unit").casefold() in {"kg", "公斤", "千克"}:
        grams *= 1000
    name = (text[: match.start()] + text[match.end() :]).strip(" \t-:：()（）[]【】")
    return name, grams


def _split_recipe_text(value: object) -> list[tuple[str, float]]:
    text = str(value or "").strip()
    if not text:
        return []
    items: list[tuple[str, float]] = []
    # Scan each delimited segment so text such as "鸡肉80g 米饭100g"
    # yields two ingredients instead of treating the second item as part of
    # the first ingredient name.
    for token in re.split(r"[\n\r,，、;；|]+", text):
        matches = list(_WEIGHT_RE.finditer(token))
        cursor = 0
        for match in matches:
            name = token[cursor : match.start()].strip(" \t-:：()（）[]【】/")
            if not name:
                cursor = match.end()
                continue
            grams = float(match.group("value"))
            if match.group("unit").casefold() in {"kg", "公斤", "千克"}:
                grams *= 1000
            items.append((name, grams))
            cursor = match.end()
    return items


def _column_letter(index: int) -> str:
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _detect_layout(rows: list[tuple[object, ...]]) -> tuple[int, dict[str, int]] | None:
    """Find a semantic header row and its column roles."""
    for header_index, row in enumerate(rows[:40]):
        roles: dict[str, tuple[int, int]] = {}
        for column_index, value in enumerate(row):
            role, score = _header_role(value)
            if role and (role not in roles or score > roles[role][0]):
                roles[role] = (score, column_index)
        selected = {role: pair[1] for role, pair in roles.items()}
        # The established SOP template uses "套餐" for the dish and
        # "菜式" for a component/sub-recipe. Both labels otherwise look like
        # recipe-name aliases, so resolve this pair explicitly.
        normalised_headers = {
            _normalise_label(value): column_index
            for column_index, value in enumerate(row)
            if _normalise_label(value)
        }
        meal_column = next(
            (
                normalised_headers[label]
                for label in ("套餐", "餐点", "餐點")
                if label in normalised_headers
            ),
            None,
        )
        dish_component_column = next(
            (
                normalised_headers[label]
                for label in ("菜式", "菜式名称", "菜式名稱")
                if label in normalised_headers
            ),
            None,
        )
        if meal_column is not None and dish_component_column is not None:
            selected["recipe_name"] = meal_column
            selected["component"] = dish_component_column
        if "recipe_name" in selected and ("ingredient_name" in selected or "recipe_text" in selected):
            return header_index, selected
    return None


def _infer_layout_from_content(
    rows: list[tuple[object, ...]],
) -> tuple[int, dict[str, int]] | None:
    """Infer a layout when headers are present but use unknown labels.

    This is intentionally conservative: a candidate must contain a textual
    dish column, a textual ingredient column, and at least one independently
    parseable weight column (or a recipe-text column with embedded weights).
    Ambiguous/header-only sheets are left for the caller to report.
    """
    if len(rows) < 2:
        return None

    def text_stats(data: list[tuple[object, ...]], column: int) -> tuple[int, int, float]:
        values = [str(_value(row, column) or "").strip() for row in data]
        nonempty = [value for value in values if value]
        average_length = (
            sum(len(value) for value in nonempty) / len(nonempty) if nonempty else 0.0
        )
        return len(nonempty), len(values) - len(nonempty), average_length

    def weight_count(data: list[tuple[object, ...]], column: int) -> int:
        count = 0
        for row in data:
            value = _value(row, column)
            if value in (None, ""):
                continue
            try:
                _parse_weight_value(value)
            except ValueError:
                continue
            count += 1
        return count

    def embedded_count(data: list[tuple[object, ...]], column: int) -> int:
        return sum(1 for row in data if _WEIGHT_RE.search(str(_value(row, column) or "")))

    width = max(len(row) for row in rows)
    # Try a conventional header row first, then a genuinely headerless table.
    for header_index in (0, -1):
        data = rows[header_index + 1 :] if header_index == 0 else rows
        if not data:
            continue
        text_columns = [
            column
            for column in range(width)
            if text_stats(data, column)[0] >= 1
        ]

        # One-cell-per-dish SOP text with unknown headers.
        text_candidates = [
            column for column in text_columns if embedded_count(data, column) >= 1
        ]
        for text_column in text_candidates:
            recipe_candidates = [column for column in text_columns if column != text_column]
            if not recipe_candidates:
                continue
            recipe_column = max(
                recipe_candidates,
                key=lambda column: (
                    text_stats(data, column)[0],
                    text_stats(data, column)[2],
                ),
            )
            if text_stats(data, recipe_column)[0] >= 1:
                return header_index, {
                    "recipe_name": recipe_column,
                    "recipe_text": text_column,
                }

        numeric_candidates = [
            column for column in range(width) if weight_count(data, column) >= 1
        ]
        if not numeric_candidates:
            continue
        ingredient_candidates = [column for column in text_columns if column not in numeric_candidates]
        if not ingredient_candidates:
            continue
        ingredient_column = max(
            ingredient_candidates,
            key=lambda column: (
                text_stats(data, column)[0],
                -text_stats(data, column)[2],
            ),
        )
        recipe_candidates = [column for column in ingredient_candidates if column != ingredient_column]
        if not recipe_candidates:
            continue
        recipe_column = max(
            recipe_candidates,
            key=lambda column: (
                text_stats(data, column)[1],
                text_stats(data, column)[2],
            ),
        )
        if text_stats(data, recipe_column)[0] and text_stats(data, ingredient_column)[0]:
            grams_column = max(numeric_candidates, key=lambda column: weight_count(data, column))
            return header_index, {
                "recipe_name": recipe_column,
                "ingredient_name": ingredient_column,
                "grams": grams_column,
            }
    return None


def _value(row: tuple[object, ...], column: int | None) -> object:
    return row[column] if column is not None and column < len(row) else None


def _meal_set(sheet_name: str) -> str:
    for value in "ABCDE":
        if f"{value}餐" in sheet_name:
            return value
    return ""


def _is_primary_sop_sheet(sheet_name: str) -> bool:
    """Accept canonical A–E sheets and explicitly staged school variants."""
    compact = re.sub(r"\s+", "", sheet_name).lower()
    stem = r"(?:\d+月)?[abcde]餐配料sop"
    if re.fullmatch(stem, compact):
        return True
    variant = re.fullmatch(stem + r"[（(]([^()（）]+)[）)]", compact)
    return variant is not None and bool(_school_stage(variant.group(1)))


def _read_sop_workbook_legacy(
    path: str | Path,
    sheet_names: Iterable[str] | None = None,
    *,
    strict: bool = False,
) -> tuple[list[Recipe], list[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("读取 SOP Excel 需要安装 openpyxl：pip install -r requirements.txt") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    requested = {name.strip() for name in sheet_names or ()}
    recipes: list[Recipe] = []
    errors: list[str] = []
    try:
        for worksheet in workbook.worksheets:
            sheet_name = worksheet.title
            if not requested and worksheet.sheet_state != "visible":
                continue
            if requested and sheet_name.strip() not in requested:
                continue
            if not requested and not _is_primary_sop_sheet(sheet_name):
                continue
            if "配料sop" not in sheet_name.lower():
                continue

            current_name = ""
            current_date = ""
            current_component = ""
            current_ingredients: list[IngredientAmount] = []
            current_parse_warnings: list[str] = []

            def flush() -> None:
                nonlocal current_ingredients, current_parse_warnings
                if current_name and (current_ingredients or current_parse_warnings):
                    recipes.append(
                        Recipe(
                            recipe_name=current_name,
                            ingredients=tuple(current_ingredients),
                            meal_set=_meal_set(sheet_name),
                            school_stage=_school_stage(sheet_name),
                            service_date=current_date,
                            source_sheet=sheet_name,
                            parse_warnings=tuple(current_parse_warnings),
                        )
                    )
                current_ingredients = []
                current_parse_warnings = []

            for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                values = list(row) + [None] * 18
                if row_number == 1:
                    continue
                if values[1]:
                    flush()
                    current_name = str(values[1]).strip()
                    current_date = _excel_date(values[0])
                    current_component = ""
                if values[2]:
                    current_component = str(values[2]).strip()
                ingredient_name = str(values[3] or "").strip()
                if not current_name or not ingredient_name or ingredient_name in TOTAL_MARKERS:
                    continue
                try:
                    grams = _numeric_grams(
                        values[5], sheet=sheet_name, row=row_number, ingredient=ingredient_name
                    )
                except ValueError as exc:
                    message = str(exc)
                    errors.append(message)
                    current_parse_warnings.append(message)
                    if strict:
                        raise
                    continue
                current_ingredients.append(
                    IngredientAmount(
                        ingredient_name=ingredient_name,
                        ingredient_code=str(values[6] or "").strip(),
                        component_name=current_component,
                        grams=grams,
                        source_row=row_number,
                    )
                )
            flush()
    finally:
        workbook.close()
    return recipes, errors


def read_sop_workbook(
    path: str | Path,
    sheet_names: Iterable[str] | None = None,
    *,
    strict: bool = False,
) -> tuple[list[Recipe], list[str]]:
    """Read SOP workbooks by semantic fields rather than fixed coordinates.

    Two layouts are supported: one ingredient per row, or one dish per row
    with an SOP/recipe text cell containing weights such as ``80g`` or ``0.1kg``.
    Unknown structures are reported as errors instead of being guessed.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("读取 SOP Excel 需要安装 openpyxl") from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    requested = {name.strip() for name in sheet_names or ()}
    recipes: list[Recipe] = []
    errors: list[str] = []
    inspected_sheets = 0
    try:
        for worksheet in workbook.worksheets:
            sheet_name = worksheet.title
            if not requested and worksheet.sheet_state != "visible":
                continue
            if requested and sheet_name.strip() not in requested:
                continue
            if not requested and not _is_primary_sop_sheet(sheet_name):
                continue
            inspected_sheets += 1
            rows = [tuple(row) for row in worksheet.iter_rows(values_only=True)]
            layout = _detect_layout(rows)
            if layout is None:
                layout = _infer_layout_from_content(rows)
            if layout is None:
                continue
            header_index, columns = layout
            sheet_stage = _school_stage(sheet_name)
            name_col = columns["recipe_name"]
            date_col = columns.get("date")
            set_col = columns.get("meal_set")
            component_col = columns.get("component")
            code_col = columns.get("code")
            package_col = columns.get("package_spec")

            ingredient_col = columns.get("ingredient_name")
            has_ingredient_values = (
                ingredient_col is not None
                and any(
                    str(_value(row, ingredient_col) or "").strip()
                    for row in rows[header_index + 1 :]
                )
            )

            # When a sheet contains both a free-form SOP column and a
            # structured ingredient column, prefer the structured rows. The
            # SOP text is often cooking notes without reliably parseable
            # weights; use it only when no ingredient values are present.
            if "recipe_text" in columns and not has_ingredient_values:
                text_col = columns["recipe_text"]
                for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
                    recipe_name = str(_value(row, name_col) or "").strip()
                    recipe_text = _value(row, text_col)
                    if not recipe_name or not str(recipe_text or "").strip():
                        continue
                    parsed_items = _split_recipe_text(recipe_text)
                    if not parsed_items:
                        message = f"{sheet_name}!{_column_letter(text_col)}{row_index} {recipe_name}: SOP中没有可确认的克重"
                        errors.append(message)
                        if strict:
                            raise ValueError(message)
                        continue
                    recipes.append(
                        Recipe(
                            recipe_name=recipe_name,
                            ingredients=tuple(
                                IngredientAmount(
                                    ingredient_name=item_name,
                                    grams=grams,
                                    component_name=str(_value(row, component_col) or "").strip(),
                                    ingredient_code=str(_value(row, code_col) or "").strip(),
                                    source_row=row_index,
                                )
                                for item_name, grams in parsed_items
                            ),
                            meal_set=str(_value(row, set_col) or "").strip() or _meal_set(sheet_name),
                            school_stage=sheet_stage,
                            service_date=_excel_date(_value(row, date_col)),
                            source_sheet=sheet_name,
                        )
                    )
                continue

            if ingredient_col is None:
                continue
            stage_columns = _stage_weight_columns(rows[header_index])
            if stage_columns:
                if sheet_stage:
                    selected_column = stage_columns.get(sheet_stage)
                    weight_specs = (
                        [(sheet_stage, selected_column)]
                        if selected_column is not None
                        else [(sheet_stage, columns.get("grams", -1))]
                    )
                else:
                    weight_specs = [
                        (stage, stage_columns[stage])
                        for stage in SCHOOL_STAGES
                        if stage in stage_columns
                    ]
            else:
                weight_specs = [(sheet_stage, columns.get("grams", -1))]

            for school_stage, grams_col in weight_specs:
                current_name = ""
                current_date = ""
                current_set = ""
                current_component = ""
                current_ingredients: list[IngredientAmount] = []
                current_parse_warnings: list[str] = []

                def flush() -> None:
                    nonlocal current_ingredients, current_parse_warnings
                    if current_name and (current_ingredients or current_parse_warnings):
                        recipes.append(
                            Recipe(
                                recipe_name=current_name,
                                ingredients=tuple(current_ingredients),
                                meal_set=current_set or _meal_set(sheet_name),
                                school_stage=school_stage,
                                service_date=current_date,
                                source_sheet=sheet_name,
                                parse_warnings=tuple(current_parse_warnings),
                            )
                        )
                    current_ingredients = []
                    current_parse_warnings = []

                for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
                    raw_name = str(_value(row, name_col) or "").strip()
                    if raw_name:
                        if current_name and raw_name != current_name:
                            flush()
                        current_name = raw_name
                        current_date = _excel_date(_value(row, date_col))
                        current_set = str(_value(row, set_col) or "").strip()
                        current_component = ""
                    if _value(row, component_col):
                        current_component = str(_value(row, component_col)).strip()
                    ingredient_value = str(_value(row, ingredient_col) or "").strip()
                    if not current_name or not ingredient_value or ingredient_value in TOTAL_MARKERS:
                        continue
                    embedded = _embedded_weight(ingredient_value)
                    weight_value = _value(row, grams_col) if grams_col >= 0 else None
                    # An explicit weight column is authoritative. Ingredient
                    # names frequently contain package sizes such as "25KG";
                    # only strip an embedded weight when no separate weight was
                    # supplied.
                    ingredient_name = ingredient_value
                    if weight_value in (None, "") and embedded:
                        ingredient_name = embedded[0]
                        weight_value = embedded[1]
                    ingredient_name = _clean_count_suffix(ingredient_name)
                    if (not ingredient_name and _COUNT_RE.fullmatch(ingredient_value)
                            and current_component and current_component not in TOTAL_MARKERS):
                        ingredient_name = current_component
                    count_cell = _value(row, grams_col - 1) if grams_col > 0 else None
                    # Keep a count embedded in the original ingredient label for
                    # per-piece estimates after removing it from the lookup name.
                    count_hint = f"{ingredient_value} {count_cell or ''}"
                    borrowed_count_stage = ""
                    if (len(stage_columns) == 2 and school_stage
                            and not any(_COUNT_RE.search(str(value or "")) for value in
                                        (ingredient_value, current_component, count_cell))):
                        other_stage = next(stage for stage in SCHOOL_STAGES if stage != school_stage)
                        other_grams_col = stage_columns[other_stage]
                        other_count = _value(row, other_grams_col - 1)
                        if _COUNT_RE.search(str(other_count or "")):
                            count_hint = f"{count_hint} {other_count}"
                            borrowed_count_stage = other_stage
                    weight_is_estimated = False
                    weight_estimate_note = ""
                    try:
                        grams = _parse_weight_value(weight_value)
                    except ValueError as exc:
                        specified = _specified_unit_weight(
                            count_hint=count_hint,
                            package_spec=_value(row, package_col),
                        )
                        if specified is not None:
                            grams, weight_estimate_note = specified
                            weight_is_estimated = False
                            if borrowed_count_stage:
                                weight_estimate_note += f"；{school_stage}數量未填，暫沿用同一SOP的{borrowed_count_stage}數量，待復核"
                        else:
                            estimate = _estimate_portion_weight(
                                recipe_name=current_name,
                                ingredient_name=ingredient_name,
                                component_name=current_component,
                                count_cell=count_hint,
                                package_spec=_value(row, package_col),
                                allow_recipe_specific=False,
                            )
                            if estimate is not None:
                                grams, weight_estimate_note = estimate
                                weight_is_estimated = True
                                if borrowed_count_stage:
                                    weight_estimate_note += f"；{school_stage}數量未填，暫沿用同一SOP的{borrowed_count_stage}數量，待復核"
                            else:
                                source_column = _column_letter(
                                    grams_col if grams_col >= 0 else ingredient_col
                                )
                                stage_suffix = f"（{school_stage}）" if school_stage else ""
                                message = (
                                    f"{sheet_name}{stage_suffix}!{source_column}{row_index} "
                                    f"{ingredient_name}: {exc}"
                                )
                                errors.append(message)
                                current_parse_warnings.append(message)
                                if strict:
                                    raise ValueError(message) from exc
                                continue
                    if grams == 0 and not weight_is_estimated:
                        specified = _specified_unit_weight(
                            count_hint=count_hint,
                            package_spec=_value(row, package_col),
                        )
                        if specified is not None:
                            grams, weight_estimate_note = specified
                            weight_is_estimated = False
                            if borrowed_count_stage:
                                weight_estimate_note += f"；{school_stage}數量未填，暫沿用同一SOP的{borrowed_count_stage}數量，待復核"
                        else:
                            estimate = _estimate_portion_weight(
                                recipe_name=current_name,
                                ingredient_name=ingredient_name,
                                component_name=current_component,
                                count_cell=count_hint,
                                package_spec=_value(row, package_col),
                            )
                            if estimate is not None:
                                grams, weight_estimate_note = estimate
                                weight_is_estimated = True
                                if borrowed_count_stage:
                                    weight_estimate_note += f"；{school_stage}數量未填，暫沿用同一SOP的{borrowed_count_stage}數量，待復核"
                            else:
                                source_column = _column_letter(
                                    grams_col if grams_col >= 0 else ingredient_col
                                )
                                stage_suffix = f"（{school_stage}）" if school_stage else ""
                                message = (
                                    f"{sheet_name}{stage_suffix}!{source_column}{row_index} "
                                    f"{ingredient_name}: 用量为空或为0，且无可核实的单件克重"
                                )
                                errors.append(message)
                                current_parse_warnings.append(message)
                                if strict:
                                    raise ValueError(message)
                                continue
                    current_ingredients.append(
                        IngredientAmount(
                            ingredient_name=ingredient_name,
                            ingredient_code=str(_value(row, code_col) or "").strip(),
                            component_name=current_component,
                            grams=grams,
                            source_row=row_index,
                            weight_is_estimated=weight_is_estimated,
                            weight_estimate_note=weight_estimate_note,
                        )
                    )
                flush()
    finally:
        workbook.close()
    # Older project workbooks may contain mojibake headers; retain the
    # positional reader as a compatibility fallback for known *配料sop sheets.
    if not recipes:
        legacy_recipes, legacy_errors = _read_sop_workbook_legacy(
            path, sheet_names, strict=strict
        )
        if legacy_recipes:
            return legacy_recipes, legacy_errors
    if inspected_sheets and not recipes and not errors:
        errors.append("未识别到包含菜品名称、原料/SOP和克重信息的工作表")
    return recipes, errors
