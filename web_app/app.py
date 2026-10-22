"""营养素计算 Web 服务 —— 上传 SOP Excel，输出圣类斯上架模板。

运行:
  开发:  python -m web_app.app
  部署:  gunicorn --bind 0.0.0.0:8300 wsgi:app

输入:  A–E 餐配料 SOP 工作表
输出:  圣类斯 15 列上架模板；小学和中学分别生成商品行
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
import time
import traceback
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from nutrition_tool.config import DEFAULT_PORT, MAX_UPLOAD_BYTES, resource_path

NUTRIENT_DB = resource_path("data/ingredient_nutrients.csv")
CFC_DB = resource_path("data/ingredient_nutrients_cfc_fallback.csv")
ALIAS_MAP = resource_path("data/sop_alias_mapping.csv")
STORE_UPLOAD_TEMPLATE = resource_path("data/templates/聖類斯上架模版.xlsx")

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.dish_export import (
    CALCULATION_STANDARD_COL,
    CALCULATION_STANDARD_LABELS,
    DISH_HEADERS,
    NUTRIENT_TO_DISH_COL,
    STORE_UPLOAD_HEADERS,
    dish_row_to_store_upload_row,
    result_to_dish_row,
    write_store_upload_excel,
)
from nutrition_tool.history import (
    SQLiteHistoryRepository,
    default_history_db_path,
)
from nutrition_tool.models import CALCULATION_RULE_VERSION, IngredientAmount, Recipe
from nutrition_tool.repository import (
    NutrientRepository,
    normalize_name,
    source_match_tier,
)
from nutrition_tool.sop import read_sop_workbook

app = Flask(__name__)
EDITABLE_NUTRIENT_FIELDS = tuple(NUTRIENT_TO_DISH_COL)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

_repos = {}
_history_repo = None


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    """Keep API failures machine-readable and leave a local diagnostic trace."""
    if request.path.startswith("/api/"):
        log_path = Path(tempfile.gettempdir()) / "nutrition_tool_error.log"
        try:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {request.method} {request.path}\n")
                traceback.print_exc(file=handle)
        except OSError:
            pass
        return jsonify({
            "error": "服务器处理失败，请检查输入文件或查看本机临时目录 nutrition_tool_error.log",
        }), 500
    raise exc


CALCULATION_STANDARDS = ("hong_kong",)

# Exact SOP spellings that describe a generic CFC food category. These are
# deliberately limited to official CFC rows with complete per-100g values;
# branded products still need a package label before replacing the generic
# reference. Results using these aliases remain reviewable in the UI.
_CFC_FALLBACK_ALIASES = {
    # Fresh ingredients: SOP commonly appends "肉" or a cutting instruction
    # to the menu name. These targets are the corresponding raw CFC rows.
    "甘筍": "CFC_0503010411040",
    "甘筍肉": "CFC_0503010411040",
    "甘筍肉（切片）": "CFC_0503010411040",
    "甘筍肉 <切片>": "CFC_0503010411040",
    "甘筍肉 <切絲>": "CFC_0503010411040",
    "甘筍肉 <切粒>": "CFC_0503010411040",
    "甘筍肉 <切角>": "CFC_0503010411040",
    "紫芯蕃薯肉 <切粒>": "CFC_0503010212020",
    "紫薯飯": "CFC_0503010212020",
    "薯仔肉 <切絲>": "CFC_0503010211010",
    "薯仔肉 <切粒>": "CFC_0503010211010",
    "薯仔肉 <切角>": "CFC_0503010211010",
    "翠玉瓜": "CFC_0503030432180",
    "翠玉瓜 <切半圓片>": "CFC_0503030432180",
    "翠玉瓜（切半圈片）": "CFC_0503030432180",
    "南瓜肉 <切粒>": "CFC_0503030432130",
    "洋蔥": "CFC_0503050443010",
    "洋蔥肉": "CFC_0503050443010",
    "洋蔥肉 <切絲>": "CFC_0503050443010",
    "洋蔥肉 <切粒>": "CFC_0503050443010",
    "紅圓椒": "CFC_0503040431110",
    "紅圓椒肉": "CFC_0503040431110",
    "紅圓椒肉 <切絲>": "CFC_0503040431110",
    "紅圓椒肉 <切角>": "CFC_0503040431110",
    "黃圓椒肉 <切絲>": "CFC_0503040431110",
    "西椒肉 <切絲>": "CFC_0503040431110",
    "紅椒絲": "CFC_0503040431110",
    "青椒絲": "CFC_0503040431090",
    "椰菜花 <切朵>": "CFC_0503020452020",
    "福建椰菜花<切朵>": "CFC_0503020452020",
    "中芹肉 <切段>": "CFC_0503020453110",
    "銀芽": "CFC_0503020422030",
    "金菇(包)": "CFC_0503070510090",
    "珍珠雲耳": "CFC_0503070510140",
    "珍珠雲耳 ( 貓耳朵 )": "CFC_0503070510140",
    "珍珠雲耳 (貓耳朵)": "CFC_0503070510140",
    # Grain/staple spellings used by the SOP.
    "小米（粗糧）": "CFC_0501000151010",
    "麵粉＜指南針＞": "CFC_0501050112010",
    "金盾牌頂級香絲苗米（紅線）25公斤": "CFC_0501000122130",
    "湖北大蛋（件）": "CFC_0509001111010",
    "<清洗>小棠菜苗": "CFC_0503020451070",
    "小棠菜苗": "CFC_0503020451070",
    "茄汁": "CFC_0520002032020",
    "茄醬": "CFC_0520002032020",
    "番茄醬": "CFC_0520002032020",
    "生抽": "CFC_0520002010010",
    "老抽": "CFC_0520002010010",
    "老抽/40斤": "CFC_0520002010010",
    "特級老抽(李錦記) 15kg": "CFC_0520002010010",
    "生抽/40斤淘大金標生抽": "CFC_0520002010010",
    "生抽（錦珍牌）15KG": "CFC_0520002010010",
    "蕃茄汁": "CFC_0520002032020",
    "番茄汁": "CFC_0520002032020",
    "番茄醬": "CFC_0520002032020",
    "地捫茄汁": "CFC_0520002032020",
    "歐柏茄汁(紅色) 3KGX6罐": "CFC_0520002032020",
    "豆瓣醬": "CFC_0520002031010",
    "豆瓣酱": "CFC_0520002031010",
    "豆瓣辣醬": "CFC_0520002031030",
    "辣椒醬": "CFC_0520002031070",
}


def _standard_key(value: object) -> str:
    key = str(value or "hong_kong").strip().lower()
    key = {
        "hk": "hong_kong", "hongkong": "hong_kong", "香港": "hong_kong",
    }.get(key, key)
    if key not in CALCULATION_STANDARDS:
        raise ValueError(f"unsupported calculation standard: {value}")
    return key


def _apply_cfc_aliases(
    repository: NutrientRepository, *, override_existing: bool = False,
) -> NutrientRepository:
    """Apply curated SOP spellings to official CFC fallback rows.

    The same fallback policy is used by both standards: a CFC hit is visible
    as a review warning, but a known menu spelling should not become blank
    merely because the source database uses a different canonical name.
    """
    normalized_aliases = {
        normalize_name(alias): code for alias, code in _CFC_FALLBACK_ALIASES.items()
    }
    repository.register_aliases(
        _CFC_FALLBACK_ALIASES,
        normalized_aliases,
        override=override_existing,
    )
    return repository


def get_repo(standard: str = "hong_kong") -> NutrientRepository:
    key = _standard_key(standard)
    if key not in _repos:
        catalog_profiles = NutrientRepository._load_csv(NUTRIENT_DB)
        supplemental_profiles = NutrientRepository._load_csv(CFC_DB)
        hong_kong_profiles = [
            profile for profile in catalog_profiles
            if source_match_tier(profile) in {"hong_kong_official", "water_zero"}
        ]
        fallback_candidates = [
            profile for profile in catalog_profiles
            if source_match_tier(profile) not in {"hong_kong_official", "water_zero"}
        ] + supplemental_profiles
        fallback_profiles = []
        seen_fallbacks = set()
        for profile in fallback_candidates:
            identity = (
                profile.ingredient_code.strip().upper(),
                profile.ingredient_name.strip(),
                source_match_tier(profile),
                profile.source_food_id.strip(),
            )
            if identity in seen_fallbacks:
                continue
            seen_fallbacks.add(identity)
            fallback_profiles.append(profile)

        alias_profiles = hong_kong_profiles + fallback_profiles
        aliases = NutrientRepository._load_alias_map(
            ALIAS_MAP, profiles=alias_profiles,
        )
        normalized_aliases = NutrientRepository._load_alias_normalized_map(
            ALIAS_MAP, profiles=alias_profiles,
        )
        _repos[key] = _apply_cfc_aliases(NutrientRepository(
            hong_kong_profiles,
            fallback_profiles=fallback_profiles,
            alias_map=aliases,
            alias_normalized_map=normalized_aliases,
        ))
        _repos[key].load_corrections(NUTRIENT_DB.with_name("ingredient_nutrient_corrections.csv"))
    return _repos[key]


def get_history_repo() -> SQLiteHistoryRepository:
    global _history_repo
    configured_path = app.config.get("HISTORY_DB_PATH")
    path = Path(configured_path) if configured_path else default_history_db_path()
    if _history_repo is None or _history_repo.path != path:
        _history_repo = SQLiteHistoryRepository(path)
    return _history_repo


def _recipe_to_dict(recipe: Recipe) -> dict:
    return {
        "recipe_name": recipe.recipe_name,
        "meal_set": recipe.meal_set,
        "school_stage": recipe.school_stage,
        "service_date": recipe.service_date,
        "cooked_weight_g": recipe.cooked_weight_g,
        "source_sheet": recipe.source_sheet,
        "calculation_standard": recipe.calculation_standard,
        "parse_warnings": list(recipe.parse_warnings),
        "ingredients": [
            {
                "ingredient_name": ingredient.ingredient_name,
                "ingredient_code": ingredient.ingredient_code,
                "component_name": ingredient.component_name,
                "grams": ingredient.grams,
                "edible_fraction": ingredient.edible_fraction,
                "yield_factor": ingredient.yield_factor,
                "retention_factor": ingredient.retention_factor,
                "source_row": ingredient.source_row,
                "weight_is_estimated": ingredient.weight_is_estimated,
                "weight_estimate_note": ingredient.weight_estimate_note,
            }
            for ingredient in recipe.ingredients
        ],
    }


def _recipe_from_dict(data: dict) -> Recipe:
    ingredients = tuple(
        IngredientAmount(
            ingredient_name=str(item.get("ingredient_name") or ""),
            grams=float(item.get("grams", 0)),
            ingredient_code=str(item.get("ingredient_code") or ""),
            component_name=str(item.get("component_name") or ""),
            edible_fraction=item.get("edible_fraction"),
            yield_factor=item.get("yield_factor"),
            retention_factor=item.get("retention_factor"),
            source_row=item.get("source_row"),
            weight_is_estimated=bool(item.get("weight_is_estimated", False)),
            weight_estimate_note=str(item.get("weight_estimate_note") or ""),
        )
        for item in data.get("ingredients", [])
    )
    return Recipe(
        recipe_name=str(data.get("recipe_name") or ""),
        ingredients=ingredients,
        meal_set=str(data.get("meal_set") or ""),
        school_stage=str(data.get("school_stage") or ""),
        service_date=str(data.get("service_date") or ""),
        cooked_weight_g=data.get("cooked_weight_g"),
        source_sheet=str(data.get("source_sheet") or ""),
        calculation_standard=_standard_key(data.get("calculation_standard")),
        parse_warnings=tuple(str(item) for item in data.get("parse_warnings", []) if str(item).strip()),
    )


def _result_source_info(result) -> dict:
    labels = []
    fallbacks = []
    for contribution in result.contributions:
        label = contribution.source_label
        if label not in labels:
            labels.append(label)
        if contribution.requires_review:
            fallbacks.append({
                "ingredient_name": contribution.ingredient_name,
                "matched_name": contribution.source_name,
                "match_tier": contribution.match_tier,
                "source_label": contribution.source_label,
                "source_food_id": contribution.source_food_id,
                "source_url": contribution.source_url,
            })
    return {
        "summary": "、".join(labels) if labels else "無已匹配來源",
        "fallbacks": fallbacks,
        "requires_review": bool(fallbacks),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    """Avoid treating a missing optional browser icon as an application error."""
    return "", 204


def _cleanup_old_tmpdirs(max_age_hours: int = 24) -> None:
    """清理超过 max_age_hours 的临时输出目录(避免长期堆积)。"""
    import time as _time
    base = Path(tempfile.gettempdir())
    cutoff = _time.time() - max_age_hours * 3600
    for item in base.glob("nutri_out_*"):
        try:
            if item.is_dir() and item.stat().st_mtime < cutoff:
                import shutil
                shutil.rmtree(item, ignore_errors=True)
        except OSError:
            pass


def _batch_dir(batch_id: object) -> Path | None:
    value = str(batch_id or "").strip()
    if not value or Path(value).name != value or not value.startswith("nutri_out_"):
        return None
    base = Path(tempfile.gettempdir()).resolve()
    target = (base / value).resolve()
    try:
        return target if target.is_relative_to(base) and target.is_dir() else None
    except (ValueError, OSError):
        return None


def _edited_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative number") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return round(number, 2)


@app.route("/api/process", methods=["POST"])
def process_sop():
    """上传 SOP -> 计算 -> 生成小学/中学营养结果表, 返回预览。"""
    files = request.files.getlist("sop_files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "请选择 SOP Excel 文件"}), 400

    _cleanup_old_tmpdirs()
    temp_dir = Path(tempfile.mkdtemp(prefix="nutri_out_"))
    history_repo = get_history_repo()
    all_results = []
    all_recipes = []
    history_records = []
    sheet_errors = []
    # 批次唯一起始编号: 时间戳偏移, 避免多次导入菜式编号重复
    dish_no = 100001 + int(time.time() * 1000) % 900000

    for f in files:
        if not f.filename.lower().endswith((".xlsx", ".xlsm")):
            return jsonify({"error": f"{f.filename} 不是 Excel 文件(.xlsx)"}), 400
        # 安全文件名: 防路径穿越; 保留扩展名
        safe_name = secure_filename(f.filename) or "upload.xlsx"
        tmp_in = temp_dir / safe_name
        f.save(tmp_in)
        try:
            recipes, errors = read_sop_workbook(tmp_in)
            sheet_errors.extend(errors)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"解析 {f.filename} 失败: {exc}"}), 400
        for recipe in recipes:
            result = calculate_recipe(recipe, get_repo(recipe.calculation_standard))
            if result.status == "incomplete":
                # 未匹配食材: 标注但继续输出
                pass
            all_results.append(result)
            all_recipes.append(recipe)
            history_records.append(history_repo.find_confirmed(recipe))

    if not all_results:
        return jsonify({"error": "没有找到可计算的菜式(检查是否包含 'X月X餐配料sop' 工作表)"}), 400

    # 内部文件名用 ASCII(避免 URL 中文编码问题), 下载时再给中文名
    out_name = "store_upload.xlsx"
    out_path = temp_dir / out_name
    export_rows = [
        result_to_dish_row(result, dish_no=str(dish_no + idx))
        for idx, result in enumerate(all_results)
    ]
    for row, history_record in zip(export_rows, history_records):
        if history_record is None:
            continue
        for field, column in NUTRIENT_TO_DISH_COL.items():
            row[column] = round(history_record.confirmed_nutrients[field], 2)
    upload_count = write_store_upload_excel(export_rows, out_path, str(STORE_UPLOAD_TEMPLATE))
    (temp_dir / "batch.json").write_text(
        json.dumps(
            {
                "rows": export_rows,
                "calculation_rule_version": CALCULATION_RULE_VERSION,
                "recipes": [_recipe_to_dict(recipe) for recipe in all_recipes],
                "system_nutrients": [
                    result.nutrients_per_serving for result in all_results
                ],
                "calculation_standards": [
                    result.calculation_standard for result in all_results
                ],
                "history_matches": [record is not None for record in history_records],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cn_name = f"聖類斯上架_小學中學_{upload_count}項.xlsx"

    # 预览(前 30 条, 含 warnings 供营养师复核; 8 项营养全量展示)
    preview = []
    for index, (result, row) in enumerate(zip(all_results, export_rows)):
        source_info = _result_source_info(result)
        store_row = dish_row_to_store_upload_row(row)
        nutrients = {
            field: row.get(column, "")
            for field, column in NUTRIENT_TO_DISH_COL.items()
        }
        preview.append({
            "row_index": index,
            "商品名称": store_row["商品名称"],
            "商品详情": store_row["商品详情"],
            "SET": row["SET"],
            "學段": row["學段"],
            "餐名": row["餐名"],
            "烹調方式": row["烹調方式"],
            "能量(kcal)": row["能量(kcal)"],
            "蛋白質(g)": row["蛋白質(g)"],
            "總脂肪(g)": row["總脂肪(g)"],
            "飽和脂肪(g)": row["飽和脂肪(g)"],
            "反式脂肪(g)": row["反式脂肪(g)"],
            "碳水化合物(g)": row["碳水化合物(g)"],
            "糖(g)": row["糖(g)"],
            "鈉(mg)": row["鈉(mg)"],
            "status": "history-confirmed" if history_records[index] else result.status,
            "calculation_rule_version": result.calculation_rule_version,
            # Do not hide source/parse/missing-field warnings behind the first
            # three messages; the UI can display them in the row tooltip.
            "warnings": result.warnings[:20],
            "unmatched_ingredients": [
                item.get("ingredient_name", "")
                for item in result.unmatched_ingredients
            ],
            "nutrients": nutrients,
            "history_confirmed": history_records[index] is not None,
            "history_revision": (
                history_records[index].revision if history_records[index] else None
            ),
            "calculation_standard": result.calculation_standard,
            "calculation_standard_label": CALCULATION_STANDARD_LABELS.get(
                result.calculation_standard, result.calculation_standard
            ),
            "source_summary": source_info["summary"],
            "fallback_sources": source_info["fallbacks"],
        })

    return jsonify({
        "total": len(all_results),
        "calculation_rule_version": CALCULATION_RULE_VERSION,
        "incomplete": sum(
            1
            for result, history_record in zip(all_results, history_records)
            if result.status == "incomplete" and history_record is None
        ),
        "review": sum(1 for r in all_results if r.status == "review"),
        "history_reused": sum(1 for record in history_records if record is not None),
        "sheet_errors": sheet_errors[:20],
        "batch_id": temp_dir.name,
        "download": f"/api/download?file={out_name}&dir={temp_dir.name}",
        "download_name": cn_name,
        "upload_count": upload_count,
        "store_headers": STORE_UPLOAD_HEADERS,
        "preview": preview,
    })


@app.route("/api/recalculate", methods=["POST"])
def recalculate_row():
    """Recalculate one dish with a selected official data standard."""
    payload = request.get_json(silent=True) or {}
    temp_dir = _batch_dir(payload.get("batch_id"))
    if temp_dir is None:
        return jsonify({"error": "invalid or expired batch_id"}), 400
    try:
        state_path = temp_dir / "batch.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        rows = state["rows"]
        recipes = state.get("recipes", [])
        index = payload.get("row_index")
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(rows):
            raise ValueError("row_index is invalid")
        if index >= len(recipes) or not isinstance(recipes[index], dict):
            raise ValueError("recipe is unavailable for this row")

        # Preserve unsaved numeric edits from other rows while replacing the
        # selected row with its new system calculation.
        for edit in payload.get("edits", []):
            if not isinstance(edit, dict):
                raise ValueError("each edit must be an object")
            edit_index = edit.get("row_index")
            values = edit.get("values")
            if (
                isinstance(edit_index, bool)
                or not isinstance(edit_index, int)
                or not 0 <= edit_index < len(rows)
                or not isinstance(values, dict)
            ):
                raise ValueError("edit is invalid")
            for field, value in values.items():
                if field not in EDITABLE_NUTRIENT_FIELDS:
                    raise ValueError(f"unsupported editable field: {field}")
                rows[edit_index][NUTRIENT_TO_DISH_COL[field]] = _edited_number(value, field)

        standard = _standard_key(payload.get("calculation_standard"))
        recipe_data = dict(recipes[index])
        recipe_data["calculation_standard"] = standard
        recipe = _recipe_from_dict(recipe_data)
        result = calculate_recipe(recipe, get_repo(standard))
        source_info = _result_source_info(result)
        dish_no = rows[index].get(DISH_HEADERS[0], "")
        rows[index] = result_to_dish_row(result, dish_no=str(dish_no))
        recipes[index] = _recipe_to_dict(recipe)
        system_nutrients = state.setdefault("system_nutrients", [{} for _ in rows])
        while len(system_nutrients) < len(rows):
            system_nutrients.append({})
        system_nutrients[index] = result.nutrients_per_serving
        standards = state.setdefault("calculation_standards", ["hong_kong"] * len(rows))
        while len(standards) < len(rows):
            standards.append("hong_kong")
        standards[index] = standard
        history_matches = state.setdefault("history_matches", [False] * len(rows))
        while len(history_matches) < len(rows):
            history_matches.append(False)
        history_matches[index] = False
        state["rows"] = rows
        state["recipes"] = recipes
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        write_store_upload_excel(rows, temp_dir / "store_upload.xlsx", str(STORE_UPLOAD_TEMPLATE))
        store_row = dish_row_to_store_upload_row(rows[index])
        return jsonify({
            "row_index": index,
            "商品名称": store_row["商品名称"],
            "商品详情": store_row["商品详情"],
            "school_stage": result.school_stage,
            "standard": standard,
            "standard_label": CALCULATION_STANDARD_LABELS[standard],
            "nutrients": (
                [None for _ in NUTRIENT_TO_DISH_COL]
                if result.status == "incomplete"
                else [
                    round(result.nutrients_per_serving[field], 2)
                    for field in NUTRIENT_TO_DISH_COL
                ]
            ),
            "status": result.status,
            "calculation_rule_version": result.calculation_rule_version,
            "warnings": result.warnings[:20],
            "unmatched_ingredients": [
                item.get("ingredient_name", "")
                for item in result.unmatched_ingredients
            ],
            "source_summary": source_info["summary"],
            "fallback_sources": source_info["fallbacks"],
        })
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/export-edited", methods=["POST"])
def export_edited():
    payload = request.get_json(silent=True) or {}
    temp_dir = _batch_dir(payload.get("batch_id"))
    if temp_dir is None:
        return jsonify({"error": "invalid or expired batch_id"}), 400
    try:
        state = json.loads((temp_dir / "batch.json").read_text(encoding="utf-8"))
        rows = state["rows"]
        recipes = state.get("recipes", [])
        system_nutrients = state.get("system_nutrients", [])
        history_matches = state.get("history_matches", [])
        edits = payload.get("edits", [])
        if not isinstance(edits, list):
            raise ValueError("edits must be a list")
        changes = []
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("each edit must be an object")
            index = edit.get("row_index")
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(rows):
                raise ValueError("row_index is invalid")
            values = edit.get("values")
            if not isinstance(values, dict):
                raise ValueError("edit values must be an object")
            row = rows[index]
            for field, value in values.items():
                if field not in EDITABLE_NUTRIENT_FIELDS:
                    raise ValueError(f"unsupported editable field: {field}")
                number = _edited_number(value, field)
                column = NUTRIENT_TO_DISH_COL[field]
                old_value = row.get(column, "")
                row[column] = number
                changes.append({
                    "row_index": index,
                    "field": field,
                    "system_value": old_value,
                    "edited_value": number,
                })
        out_name = "store_upload.xlsx"
        out_path = temp_dir / out_name
        upload_count = write_store_upload_excel(rows, out_path, str(STORE_UPLOAD_TEMPLATE))
        (temp_dir / "edit_log.json").write_text(
            json.dumps(changes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        history_saved = 0
        history_warning = ""
        for index, recipe_data in enumerate(recipes):
            if index >= len(system_nutrients) or not isinstance(recipe_data, dict):
                continue
            row = rows[index]
            if row.get("常規菜單") not in {"passed", "history-confirmed"}:
                # Provisional estimates and missing-as-zero results must not
                # become confirmed history just because the workbook was exported.
                continue
            system_values = system_nutrients[index]
            if not isinstance(system_values, dict):
                continue
            confirmed_values = dict(system_values)
            try:
                for field, column in NUTRIENT_TO_DISH_COL.items():
                    confirmed_values[field] = float(row.get(column, ""))
            except (TypeError, ValueError):
                continue
            try:
                get_history_repo().save_confirmation(
                    _recipe_from_dict(recipe_data),
                    system_values,
                    confirmed_values,
                    reason=str(payload.get("reason") or "")[:500],
                    source="web_export",
                )
            except (sqlite3.Error, OSError):
                history_warning = (
                    "Excel 已导出，但历史记录未保存；请检查历史数据库目录的写入权限。"
                )
                break
            history_saved += 1
        return jsonify({
            "download": f"/api/download?file={out_name}&dir={temp_dir.name}",
            "download_name": f"聖類斯上架_小學中學_已修改_{upload_count}項.xlsx",
            "upload_count": upload_count,
            "store_preview": [dish_row_to_store_upload_row(row) for row in rows],
            "changed_cells": len(changes),
            "history_saved": history_saved,
            "history_warning": history_warning,
        })
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/download")
def download():
    name = request.args.get("file", "")
    dirname = request.args.get("dir", "")
    dl_name = request.args.get("name", name)
    # 只允许临时目录内的文件(用 is_relative_to 做组件级路径校验, 防前缀绕过)
    base = Path(tempfile.gettempdir()).resolve()
    try:
        target = (base / dirname / name).resolve()
        is_inside = target.is_relative_to(base)
    except (ValueError, OSError):
        is_inside = False
    if not is_inside or not target.is_file():
        return jsonify({"error": "文件不存在"}), 404
    return send_file(str(target), as_attachment=True, download_name=dl_name)


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", str(DEFAULT_PORT)))
    app.run(host=host, port=port, debug=False)
