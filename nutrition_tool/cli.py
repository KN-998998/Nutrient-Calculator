from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .calculator import calculate_recipe
from .exporters import export_json, export_summary_csv
from .repository import NutrientRepository
from .sop import read_sop_workbook
from .templates import write_database_template


def _sheets(value: str | None) -> list[str] | None:
    return [item.strip() for item in value.split(",") if item.strip()] if value else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="香港学生餐营养素计算工具")
    commands = parser.add_subparsers(dest="command", required=True)

    template = commands.add_parser("make-template", help="从 SOP 提取唯一食材，生成营养数据库填写模板")
    template.add_argument("sop", type=Path)
    template.add_argument("output", type=Path)
    template.add_argument("--sheets", help="逗号分隔的工作表名称；默认读取所有配料sop表")

    calculate = commands.add_parser("calculate-sop", help="根据食材营养数据库批量计算 SOP 套餐")
    calculate.add_argument("sop", type=Path)
    calculate.add_argument("database", type=Path)
    calculate.add_argument("output", type=Path, help="输出 .json 或 .csv")
    calculate.add_argument("--sheets", help="逗号分隔的工作表名称")
    calculate.add_argument("--strict", action="store_true", help="遇到非数值克重立即失败")
    calculate.add_argument("--energy-threshold", type=float, default=0.05, help="能量差异警告阈值，默认0.05")
    calculate.add_argument("--include-details", action="store_true", help="JSON保留逐食材贡献明细（默认已保留）")

    inspect = commands.add_parser("inspect-sop", help="检查 SOP 可解析套餐、食材与克重错误")
    inspect.add_argument("sop", type=Path)
    inspect.add_argument("--sheets", help="逗号分隔的工作表名称")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect-sop":
        recipes, errors = read_sop_workbook(args.sop, _sheets(args.sheets))
        print(json.dumps({
            "recipes": len(recipes),
            "ingredients": sum(len(recipe.ingredients) for recipe in recipes),
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        return 1 if errors else 0

    recipes, errors = read_sop_workbook(
        args.sop,
        _sheets(args.sheets),
        strict=getattr(args, "strict", False),
    )
    if args.command == "make-template":
        count = write_database_template(recipes, args.output)
        print(f"已生成 {args.output}，共 {count} 个唯一食材。")
        if errors:
            print(f"跳过 {len(errors)} 个克重异常：", file=sys.stderr)
            print("\n".join(errors), file=sys.stderr)
        return 0

    repository = NutrientRepository.from_csv(args.database)
    results = [
        calculate_recipe(recipe, repository, energy_warning_threshold=args.energy_threshold)
        for recipe in recipes
    ]
    if args.output.suffix.lower() == ".json":
        export_json(results, args.output)
    elif args.output.suffix.lower() == ".csv":
        export_summary_csv(results, args.output)
    else:
        raise ValueError("输出文件必须是 .json 或 .csv")
    summary = {
        "recipes": len(results),
        "passed": sum(result.status == "passed" for result in results),
        "review": sum(result.status == "review" for result in results),
        "incomplete": sum(result.status == "incomplete" for result in results),
        "sop_errors": errors,
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
