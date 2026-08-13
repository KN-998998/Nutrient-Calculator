from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

from .models import IngredientAmount, Recipe


TOTAL_MARKERS = {"合計生重", "合计生重", "食材/系統名稱", "食材/系统名称"}
WATER_NAMES = {"清水", "水"}


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


def _meal_set(sheet_name: str) -> str:
    for value in "ABCDE":
        if f"{value}餐" in sheet_name:
            return value
    return ""


def read_sop_workbook(
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
            if "配料sop" not in sheet_name.lower():
                continue

            current_name = ""
            current_date = ""
            current_component = ""
            current_ingredients: list[IngredientAmount] = []

            def flush() -> None:
                nonlocal current_ingredients
                if current_name and current_ingredients:
                    recipes.append(
                        Recipe(
                            recipe_name=current_name,
                            ingredients=tuple(current_ingredients),
                            meal_set=_meal_set(sheet_name),
                            service_date=current_date,
                            source_sheet=sheet_name,
                        )
                    )
                current_ingredients = []

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
                    errors.append(str(exc))
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
