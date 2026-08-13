"""营养素计算桌面工具 —— 上传 SOP Excel, 输出 TT 菜單系統「菜式管理」格式 Excel。

运行:
  开发:  python app.py
  打包:  PyInstaller 打包后双击, 自动打开浏览器

输入:  SOP Excel(支持 5月/6月 那种 "X月X餐配料sop" 多sheet格式)
输出:  菜式管理格式 Excel(菜式編號/SET/餐名/8项营养/主食材/烹調方式等字段)
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import time
import webbrowser
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

# 营养库路径: 打包后从 _MEIPASS 读取
def _resource_path(rel: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / rel
    return Path(__file__).resolve().parent.parent / rel

NUTRIENT_DB = _resource_path("data/ingredient_nutrients.csv")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nutrition_tool.calculator import calculate_recipe
from nutrition_tool.dish_export import DISH_HEADERS, result_to_dish_row, write_dish_excel
from nutrition_tool.repository import NutrientRepository
from nutrition_tool.sop import read_sop_workbook

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB(大SOP文件)

_repo = None


def get_repo() -> NutrientRepository:
    global _repo
    if _repo is None:
        _repo = NutrientRepository.from_csv(NUTRIENT_DB)
    return _repo


@app.route("/")
def index():
    return render_template("index.html")


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


@app.route("/api/process", methods=["POST"])
def process_sop():
    """上传 SOP -> 计算 -> 生成菜式Excel, 返回预览。"""
    files = request.files.getlist("sop_files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "请选择 SOP Excel 文件"}), 400

    _cleanup_old_tmpdirs()
    temp_dir = Path(tempfile.mkdtemp(prefix="nutri_out_"))
    repo = get_repo()
    all_results = []
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
            result = calculate_recipe(recipe, repo)
            if result.status == "incomplete":
                # 未匹配食材: 标注但继续输出
                pass
            all_results.append(result)

    if not all_results:
        return jsonify({"error": "没有找到可计算的菜式(检查是否包含 'X月X餐配料sop' 工作表)"}), 400

    # 内部文件名用 ASCII(避免 URL 中文编码问题), 下载时再给中文名
    out_name = "dish_nutrition_export.xlsx"
    out_path = temp_dir / out_name
    write_dish_excel(all_results, out_path, dish_no_start=dish_no)
    cn_name = f"菜式管理_营养素_{len(all_results)}道菜.xlsx"

    # 预览(前 30 条, 含 warnings 供营养师复核; 8 项营养全量展示)
    preview = []
    for result in all_results[:30]:
        row = result_to_dish_row(result)
        preview.append({
            "SET": row["SET"],
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
            "status": result.status,
            "warnings": result.warnings[:3],
        })

    return jsonify({
        "total": len(all_results),
        "incomplete": sum(1 for r in all_results if r.status == "incomplete"),
        "review": sum(1 for r in all_results if r.status == "review"),
        "sheet_errors": sheet_errors[:20],
        "download": f"/api/download?file={out_name}&dir={temp_dir.name}",
        "download_name": cn_name,
        "preview": preview,
    })


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


def _pick_port(preferred: int) -> int:
    """选择可用端口: 用与 werkzeug 相同的绑定方式(SO_REUSEADDR)探测,
    被占用/Windows 保留段(WinError 10013)时自动 +1 重试;
    范围内全失败时让系统分配随机空闲端口兜底。"""
    import socket
    for port in range(preferred, preferred + 200):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.close()
            return port
        except OSError:
            continue
    # 兜底: 系统分配随机空闲端口(Windows 保留段/全部占用时)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port
    except OSError:
        return preferred


def open_browser(url: str):
    webbrowser.open(url)


if __name__ == "__main__":
    # 桌面模式: 端口可被环境变量 PORT 覆盖; 默认 8317(避开保留段), 占用时自动 +1
    preferred = int(os.environ.get("PORT", "8317"))
    port = _pick_port(preferred)
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.2, open_browser, args=(url,)).start()
    app.run(host="127.0.0.1", port=port, debug=False)
