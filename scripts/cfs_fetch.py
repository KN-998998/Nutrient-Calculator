"""香港食安中心(CFS)食物營養搜尋器批量抓取。

链路(已实测验证):
1. 搜索:  POST https://www.cfs.gov.hk/tc_chi/nutrient/presearch3.php
          data: keylang=C&inShortMode=0&fg_id=&fsg_id=&keyword=<词>&searchcriteria=and&keyword2=
          返回食物候选列表, 每个候选链接 javascript:tosubmit('fg','fsg','food_id')
2. 详情:  POST https://www.cfs.gov.hk/tc_chi/nutrient/fc-myreport.php
          data: fg_id=<fg>&fsg_id=<fsg>&food_id=<food_id>&inShortMode=
          返回每100克可食部 18 项营养 + 数据来源

页面为 UTF-8 编码。请求间保留礼貌间隔, 避免给政府网站造成压力。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
import ssl
from dataclasses import dataclass, field

BASE = "https://www.cfs.gov.hk/tc_chi/nutrient"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "nutrition-tool-integration/0.1 (internal use)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

_CTX = ssl.create_default_context()


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _post(path: str, data: dict[str, str], timeout: int = 30) -> str:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
        return _decode(resp.read())


@dataclass
class FoodCandidate:
    name: str
    alias: str
    fg_id: str
    fsg_id: str
    food_id: str

    def detail_url(self) -> str:
        return f"{BASE}/fc-myreport.php?fg_id={self.fg_id}&fsg_id={self.fsg_id}&food_id={self.food_id}"


def search_food(keyword: str, session: dict | None = None) -> list[FoodCandidate]:
    """按关键词搜索食物, 返回候选列表。

    注意: 页面表单初始 action 为 presearch3.php, 但 onsubmit 的 strfun()
    会把 action 改为 search3.php 再提交 —— 真正的搜索端点是 search3.php。
    """
    html = _post(
        "/search3.php",
        {
            "keylang": "C",
            "inShortMode": "0",
            "fg_id": "",
            "fsg_id": "",
            "keyword": keyword,
            "searchcriteria": "and",
            "keyword2": "",
        },
    )
    candidates: list[FoodCandidate] = []
    # 每个候选: <a href="javascript:tosubmit ('fg','fsg','food_id');">名称</a>
    for m in re.finditer(
        r"javascript:tosubmit\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*;\s*\"?[^>]*>([^<]+)",
        html,
    ):
        fg, fsg, fid, name = m.group(1), m.group(2), m.group(3), m.group(4).strip()
        candidates.append(FoodCandidate(name=name, alias="", fg_id=fg, fsg_id=fsg, food_id=fid))
    return candidates


def fetch_nutrient(fg_id: str, fsg_id: str, food_id: str) -> dict:
    """获取单个食物的营养详情(每100克可食部)。"""
    html = _post(
        "/fc-myreport.php",
        {"fg_id": fg_id, "fsg_id": fsg_id, "food_id": food_id, "inShortMode": ""},
    )
    result: dict = {"food_name": "", "source": ""}
    name_m = re.search(r"<th>食物名稱:\s*</th>\s*<td[^>]*>\s*([^<]+)", html)
    src_m = re.search(r"<th>資料來源:\s*</th>\s*<td[^>]*>\s*([^<]+)", html)
    if name_m:
        result["food_name"] = name_m.group(1).strip()
    if src_m:
        result["source"] = src_m.group(1).strip()
    # 营养行: <td>营养名</td><td>单位(可能包div, 标签间可能有空格)</td><td>数值(可能包div)</td>
    # 注意: CFS 部分行是 <td> <div align=center>克</div></td> (td与div间有空格)
    for row_m in re.finditer(
        r"<td>([^<]+)</td>\s*<td[^>]*>\s*(?:<[^>]+>\s*)*([^<]*)\s*(?:<[^>]+>\s*)*</td>\s*<td[^>]*>\s*(?:<[^>]+>\s*)*([^<]*)\s*(?:<[^>]+>\s*)*</td>",
        html,
    ):
        nutrient, unit, value = row_m.group(1).strip(), row_m.group(2).strip(), row_m.group(3).strip()
        result[nutrient] = value
    return result


NUTRIENT_MAP = {
    "能量*": "energy_kcal",
    "蛋白質": "protein_g",
    "碳水化合物*": "available_carbohydrate_g",
    "脂肪": "total_fat_g",
    "膳食纖維*": "dietary_fibre_g",
    "糖": "sugars_g",
    "飽和脂肪": "saturated_fat_g",
    "反式脂肪": "trans_fat_g",
    "膽固醇": "cholesterol_mg",
    "鈣": "calcium_mg",
    "鈉": "sodium_mg",
    "鉀": "potassium_mg",
}


def to_profile_row(detail: dict, ingredient_code: str, ingredient_name: str, matched_name: str) -> dict:
    """把 CFS 详情转成工具营养库 CSV 行。"""
    def num(key: str) -> str:
        v = detail.get(key, "")
        if v in ("", "NA", "ND", "Trace", "微量"):
            return ""
        try:
            return f"{float(v):g}"
        except ValueError:
            return ""
    row = {
        "ingredient_code": ingredient_code,
        "ingredient_name": ingredient_name,
        "aliases": matched_name,
        "edible_fraction": 1,
        "yield_factor": 1,
        "retention_factor": 1,
        "source": detail.get("source", "香港食安中心"),
        "source_food_id": "",
    }
    for cfs_key, field_name in NUTRIENT_MAP.items():
        row[field_name] = num(cfs_key)
    return row


def normalize_keyword(name: str) -> str:
    """把 SOP 食材名清洗成适合搜索的关键词。"""
    text = name.strip()
    text = re.sub(r"[<>\s]+", "", text)
    # 去掉品牌/规格括号段, 保留主词
    text = re.sub(r"（[^）]*）", "", text)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    # 去掉加工/形态后缀(双字以上直接替换)
    for suffix in (
        "（切半圈片）", "(切半圈片)", "切絲", "切粒", "切丁", "切條", "切片", "切半",
        "<切絲>", "<切粒>", "醃製", "腌制", "已熟", "熟",
    ):
        text = text.replace(suffix, "")
    # 单字形态尾只在字符串尾部删除(避免 絲苗米 被误删成 苗米)
    text = re.sub(r"[絲粒丁條片]$", "", text)
    # 数量/规格尾巴
    text = re.sub(r"[\d]+[克個件隻包袋樽]*$", "", text)
    return text.strip()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        kw = sys.argv[2] if len(sys.argv) > 2 else "雞肉"
        print(f"== 搜索: {kw} ==")
        for c in search_food(kw)[:10]:
            print(f"  {c.name!r}  fg={c.fg_id} fsg={c.fsg_id} id={c.food_id}")
        print("== 详情(第一个候选) ==")
        cands = search_food(kw)
        if cands:
            detail = fetch_nutrient(cands[0].fg_id, cands[0].fsg_id, cands[0].food_id)
            for k, v in detail.items():
                print(f"  {k}: {v}")
