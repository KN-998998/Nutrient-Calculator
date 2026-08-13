"""批量从香港食安中心抓取 SOP 食材营养数据。

流程:
1. 合并 5月/6月 make-template 输出的唯一食材
2. 清洗名称 → 搜索关键词
3. 搜索 CFS 食物营养搜寻器, 自动匹配最佳候选
4. 拉取营养详情, 组装成工具营养库 CSV
5. 无法匹配的写入待人工确认清单

礼貌爬取: 每次请求间隔约 1 秒。支持断点续跑(进度存 json)。
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import csv
import difflib
import json
import re
import sys
import time
from pathlib import Path

from cfs_fetch import (
    NUTRIENT_MAP,
    fetch_nutrient,
    normalize_keyword,
    search_food,
    to_profile_row,
)

WORKDIR = Path(r"F:\营养素计算工具")
MAY_CSV = WORKDIR / "data" / "ingredients_may.csv"
JUNE_CSV = WORKDIR / "data" / "ingredients_june.csv"
PROGRESS = WORKDIR / "data" / "cfs_progress.json"
MATCHED_CSV = WORKDIR / "data" / "ingredient_nutrients.csv"
UNMATCHED_JSON = WORKDIR / "data" / "cfs_unmatched.json"

# 品牌/规格词, 搜索前剔除, 提高命中率(只用于搜索关键词, 不改原名)
BRAND_WORDS = [
    "亨通", "家樂", "財神", "地捫", "南韓", "泰國香米", "飛羊", "新豐", "彩線",
    "李錦記", "淘大", "雀巢", "獅球嘜", "刀嘜", "維他", "金寶", "美味棧", "珠江橋",
    "龜甲萬", "日本", "韓國", "西班牙", "意大利", "美國", "澳洲", "調味", "調",
    "亨氏", "卡夫", "聯合", "金象", "雙羊", "金杯", "駱駝嘜", "獅頭", "冠益",
]


# 包装/形态描述词, 搜索前剔除
PACK_WORDS = [
    "紅色蓋", "藍色蓋", "綠色蓋", "黃色蓋", "白色蓋", "膠蓋", "蓋",
    "大罐裝", "罐裝", "盒裝", "袋裝", "樽裝", "支裝", "包裝",
    "切半圈片", "切圈", "切絲", "切粒", "切丁", "切條", "切片", "切半",
    "切朵", "切角", "切半圓片", "切一開二", "一開二", "切碎", "切塊",
    "<切絲>", "<切粒>", "清洗", "(清洗)", "（清洗）", "濕",
    "去骨", "去皮", "去殼", "醃製", "腌制", "熟",
]

# 手动映射: SOP 食材名关键词 -> CFS 搜索词(CFS 名称不同或缺失时用)
MANUAL_MAP = {
    "京蔥": "蔥", "大蔥": "蔥", "青蔥": "蔥", "葱": "蔥",
    "豆干": "豆腐乾", "豆乾": "豆腐乾", "枝竹": "腐竹", "支竹": "腐竹",
    "雞中翼": "雞翼", "雞翼槌": "雞翼", "雞鎚": "雞翼", "雞翼": "雞翼",
    "薯仔": "馬鈴薯", "薯角": "馬鈴薯", "烤薯角": "馬鈴薯", "薯仔粒": "馬鈴薯", "馬鈴薯": "馬鈴薯",
    "生抽": "豉油", "老抽": "豉油", "豉油": "豉油", "醬油": "豉油",
    "茄汁": "番茄醬", "茄糕": "番茄", "茄羔": "番茄", "鮮茄": "番茄",
    "意粉": "意粉", "通粉": "通心粉", "蜆殼粉": "蜆殼粉", "貝殼粉": "貝殼粉", "扭扭粉": "扭扭粉",
    "麵粉": "麵粉", "生粉": "玉米澱粉", "粟粉": "粟米澱粉", "澄麵": "澄麵", "糯米粉": "糯米粉",
    "麻油": "芝麻油", "香油": "芝麻油", "芝麻油": "芝麻油",
    "濃縮橙汁": "鮮榨橙汁", "橙汁": "鮮榨橙汁",
    "水餃": "菜肉水餃", "煎餃": "日式煎餃子", "餃子": "菜肉水餃",
    "墨魚餅": "煎墨魚餅",
    "雞球": "雞肉", "雞柳": "雞肉", "雞絲": "雞肉", "雞粒": "雞肉", "雞肉": "雞肉",
    "豬柳扒": "豬肉", "肉片": "豬肉", "肉絲": "豬肉", "免治豬肉": "豬肉",
    "牛肉絲": "牛肉", "牛柳": "牛肉", "肥牛": "牛肉", "牛肉": "牛肉",
    "蝦肉": "蝦", "蝦仁": "蝦", "蝦棗": "蝦", "蝦米": "蝦米",
    "魚柳": "魚", "魚塊": "魚", "魚肉": "魚",
    "雜豆": "雜豆", "紅豆": "紅豆", "綠豆": "綠豆", "黃豆": "黃豆", "黑豆": "黑豆",
    "蛋": "雞蛋", "雞蛋": "雞蛋",
    "米飯": "白飯", "白飯": "白飯", "大米": "白米", "香米": "白米", "絲苗米": "白米", "糙米": "糙米",
    "米粉": "米粉", "米線": "米線", "烏冬": "烏冬", "麵條": "麵條", "拉麵": "拉麵",
    "椰菜": "椰菜", "椰菜花": "椰菜花", "西椰菜": "椰菜花", "紹菜": "紹菜", "白菜仔": "白菜", "小棠菜": "小棠菜",
    "菜心": "菜心", "菜心苗": "菜心", "芥蘭": "芥蘭", "菠菜": "菠菜",
    "草菇": "草菇", "冬菇": "冬菇", "蘑菇": "蘑菇", "金菇": "金菇", "木耳": "木耳",
    "芝士": "芝士", "牛油": "牛油", "忌廉": "忌廉",
    "蜜糖": "蜂蜜", "冰糖": "冰糖", "片糖": "片糖", "紅糖": "紅糖",
    "咖哩": "咖喱", "咖喱": "咖喱",
    "照燒汁": "照燒汁", "濃縮雞汁": "雞湯",
}


def _collapse_parens(text: str) -> str:
    """全角/半角括号统一删除(含混合括号)。"""
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\([^)]*\)", "", text)
    text = text.replace("[", "(").replace("]", ")")
    text = re.sub(r"\([^)]*\)", "", text)
    return text


def make_search_keyword(name: str) -> str:
    kw = normalize_keyword(name)
    kw = kw.replace("＜", "<").replace("＞", ">")
    kw = _collapse_parens(kw)
    # 手动映射优先(按 key 长度降序, 长词优先, 避免 椰菜花 被 椰菜 抢先)
    for key, mapped in sorted(MANUAL_MAP.items(), key=lambda kv: -len(kv[0])):
        if key in kw:
            return mapped
    for w in BRAND_WORDS + PACK_WORDS:
        kw = kw.replace(w, "")
    # 去掉 "肉" 尾(甘筍肉->甘筍)和形态尾(薯仔粒->薯仔, 鮮茄角->鮮茄)
    kw = re.sub(r"(肉|角|粒|絲|丁|條)$", "", kw)
    # 数量尾巴: 25公斤 / 30kg / 1kg*12包 / 30kg)
    kw = re.sub(
        r"[\d.]+(?:kg|KG|克|公斤|斤|磅|公升|升|L|l|毫升|ml|ML|包|袋|樽|支|條|罐|個|只|件|塊|片|盒|箱|打|筒|排|扎|磅)*\**\d*$",
        "",
        kw,
    )
    # 开头数字规格: 51/60蝦肉 -> 蝦肉, 25KG 幼鹽 -> 幼鹽
    kw = re.sub(r"^[\d./]+(?:kg|KG|克|公斤|斤|磅|L|l|公升|毫升|ml|ML|oz|安士|包|袋|樽|支|條|罐|個|只|件)*\s*", "", kw)
    # 分隔符: 取第一段(如 蠔油/財神蠔油 -> 蠔油; 鹽/25KG 幼鹽 -> 鹽)
    kw = kw.split("/")[0].strip()
    # 去掉残留的斜杠/星号/括号/尖括号字符
    kw = re.sub(r"[/*+<>()（）\[\]]", "", kw)
    return kw.strip() or normalize_keyword(name)


def fallback_keywords(kw: str) -> list[str]:
    """主词搜不到时的缩短备选词。"""
    if not kw:
        return []
    candidates = []
    if kw.endswith("粒") or kw.endswith("丁") or kw.endswith("條"):
        candidates.append(kw[:-1])
    if kw.endswith("粉") and len(kw) > 1:
        candidates.append(kw[:-1])
    if len(kw) > 2:
        candidates.append(kw[-2:])  # 取最后两字, 如 砂糖->糖? 不, 幼砂糖->砂糖
    # 去前缀再试: 幼砂糖->砂糖, 雜豆粒->雜豆
    if len(kw) > 2:
        candidates.append(kw[1:])
    if len(kw) > 3:
        candidates.append(kw[2:])
    seen, out = set(), []
    for c in candidates:
        if c and c not in seen and c != kw:
            seen.add(c)
            out.append(c)
    return out


def pick_best(candidates, keyword: str):
    """从候选里选最佳匹配。

    优先级: 候选名(去括号)精确等于关键词 > 候选名以关键词开头 >
    关键词以候选名开头(候选名是关键词的子词) > 相似度。
    返回 (candidate, score)。
    """
    if not candidates:
        return None, 0.0
    kw = keyword.strip()
    if not kw:
        return None, 0.0

    def cname_clean(c) -> str:
        return _collapse_parens(normalize_keyword(c.name))

    # 1) 精确相等(清洗后)
    for c in candidates:
        if cname_clean(c) == kw:
            return c, 1.0
    # 2) 候选名以关键词开头(单字关键词跳过, 避免 鹽->鹽水鴨)
    if len(kw) >= 2:
        for c in candidates:
            cc = cname_clean(c)
            if cc.startswith(kw) and len(cc) <= len(kw) + 6:
                return c, 0.97
    # 3) 关键词以候选名开头(候选名是关键词的子词, 如 鹽 -> 土鹽; 单字同样跳过)
    if len(kw) >= 2:
        for c in candidates:
            cc = cname_clean(c)
            if cc and kw.startswith(cc) and len(cc) >= 1:
                return c, 0.95
    # 4) 相似度
    best, best_score = None, 0.0
    for c in candidates:
        cc = cname_clean(c)
        if not cc:
            continue
        score = difflib.SequenceMatcher(None, kw, cc).ratio()
        if score > best_score:
            best, best_score = c, score
    return best, best_score


def process_one(item: dict, progress: dict, matched_rows: list, lock, i: int, total: int) -> None:
    """处理单个食材: 搜索->匹配->详情。线程安全。"""
    code = (item.get("ingredient_code") or "").strip()
    name = (item.get("ingredient_name") or "").strip()
    key = f"{code}|{name}"
    kw = make_search_keyword(name)
    rec: dict = {"key": key, "code": code, "name": name, "keyword": kw}
    try:
        # 清水/水: 无营养, 直接生成零值行
        if name in ("清水", "水") or kw in ("清水", "水"):
            row = {
                "ingredient_code": code, "ingredient_name": name,
                "aliases": "水", "edible_fraction": 1, "yield_factor": 1,
                "retention_factor": 1, "source": "水(无营养)", "source_food_id": "",
            }
            for fld in NUTRIENT_MAP.values():
                row[fld] = 0
            rec.update(status="matched", matched_name="清水(水)", source="水(无营养)", score=1.0)
            with lock:
                progress[key] = rec
                matched_rows.append(row)
            return

        time.sleep(0.4)
        cands = search_food(kw)
        rec["candidates"] = [c.name for c in cands[:8]]
        best, score = pick_best(cands, kw)
        # 主词无匹配 -> fallback 词重试(最多 2 个)
        if not best or score < 0.5:
            for fk in fallback_keywords(kw)[:2]:
                time.sleep(0.4)
                fcands = search_food(fk)
                fbest, fscore = pick_best(fcands, fk)
                if fbest and fscore >= 0.55:
                    cands, best, score = fcands, fbest, fscore
                    rec["candidates"] = [c.name for c in cands[:8]]
                    rec["fallback_kw"] = fk
                    break
        if best and score >= 0.55:
            time.sleep(0.4)
            detail = fetch_nutrient(best.fg_id, best.fsg_id, best.food_id)
            rec["matched_name"] = detail.get("food_name", "")
            rec["source"] = detail.get("source", "")
            rec["score"] = score
            rec["status"] = "matched"
            if detail.get("source"):
                row = to_profile_row(detail, code, name, best.name)
                rec["row"] = row  # 完整行存入进度, 供落盘重建
                with lock:
                    matched_rows.append(row)
        else:
            rec["status"] = "unmatched"
            rec["reason"] = "no candidate >= 0.55"
    except Exception as exc:  # noqa: BLE001
        rec["status"] = "error"
        rec["reason"] = f"{type(exc).__name__}: {exc}"
    with lock:
        progress[key] = rec
        done = len(progress)
        if done % 10 == 0 or rec["status"] != "matched":
            print(
                f"[{done}/{total}] {rec['status']:9s} {name[:22]:22s} "
                f"kw={kw[:12]:12s} match={rec.get('matched_name','')[:26]}",
                flush=True,
            )
        if done % 40 == 0:
            PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    import argparse
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个食材(调试用)")
    parser.add_argument("--force", action="store_true", help="忽略进度, 重新抓取")
    parser.add_argument("--threads", type=int, default=4, help="并发线程数(默认4)")
    parser.add_argument("--retry-unmatched", action="store_true", help="只重跑 cfs_unmatched.json 里的未匹配项")
    args = parser.parse_args()

    # 1. 合并唯一食材
    unique: dict[tuple[str, str], dict] = {}
    for csv_path in (MAY_CSV, JUNE_CSV):
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                code = (row.get("ingredient_code") or "").strip()
                name = (row.get("ingredient_name") or "").strip()
                if not code and not name:
                    continue
                unique.setdefault((code, name), row)
    items = list(unique.values())

    # 2. 断点续跑: 读进度
    progress: dict[str, dict] = {}
    if PROGRESS.exists() and not args.force:
        progress = json.loads(PROGRESS.read_text(encoding="utf-8"))

    if args.retry_unmatched:
        # 只重跑未匹配/错误的项(忽略进度, 强制重新搜索)
        if UNMATCHED_JSON.exists():
            prev = json.loads(UNMATCHED_JSON.read_text(encoding="utf-8"))
            keys = {r["key"] for r in prev if r.get("status") != "matched"}
            items = [it for it in items if f"{it.get('ingredient_code','')}|{it.get('ingredient_name','')}" in keys]
        else:
            print("无 cfs_unmatched.json, 无项可重跑")
            return 1
        # 把这些 key 从进度里删掉
        for it in items:
            progress.pop(f"{it.get('ingredient_code','')}|{it.get('ingredient_name','')}", None)

    if args.limit:
        items = items[: args.limit]
    print(f"待处理食材: {len(items)}, 线程: {args.threads}", flush=True)
    print(f"已有进度: {len(progress)}", flush=True)

    # 3. 并发处理
    lock = Lock()
    matched_rows: list[dict] = []
    todo = [it for it in items if f"{it.get('ingredient_code','')}|{it.get('ingredient_name','')}" not in progress]
    print(f"待处理: {len(todo)}", flush=True)
    with ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = [
            pool.submit(process_one, it, progress, matched_rows, lock, i, len(items))
            for i, it in enumerate(todo, 1)
        ]
        for f in futures:
            f.result()  # 传播异常

    # 4. 落盘
    PROGRESS.write_text(json.dumps(progress, ensure_ascii=False, indent=1), encoding="utf-8")
    # 从进度重建全部 matched 行(兼容断点续跑, 避免丢行)
    all_rows = {tuple(r["ingredient_code"], ) if False else (r["ingredient_code"], r["ingredient_name"]): r
                for r in matched_rows}
    for rec in progress.values():
        row = rec.get("row")
        if rec.get("status") == "matched" and row:
            all_rows.setdefault((row["ingredient_code"], row["ingredient_name"]), row)
    matched_rows = list(all_rows.values())
    # 重新组装 matched(含之前进度里的)
    for rec in progress.values():
        if rec.get("status") == "matched" and rec.get("source"):
            # 用进度里的候选重新拉详情? 不: 只保留本轮拉到的
            pass
    if matched_rows:
        headers = [
            "ingredient_code", "ingredient_name", "aliases",
            "energy_kcal", "protein_g", "total_fat_g", "saturated_fat_g", "trans_fat_g",
            "available_carbohydrate_g", "sugars_g", "sodium_mg", "dietary_fibre_g",
            "cholesterol_mg", "calcium_mg", "potassium_mg",
            "edible_fraction", "yield_factor", "retention_factor", "source", "source_food_id",
        ]
        with MATCHED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(matched_rows)
    unmatched = [r for r in progress.values() if r.get("status") != "matched"]
    UNMATCHED_JSON.write_text(
        json.dumps(unmatched, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    n_matched = sum(1 for r in progress.values() if r.get("status") == "matched")
    n_unmatched = sum(1 for r in progress.values() if r.get("status") != "matched")
    print("\n==== 汇总 ====", flush=True)
    print(f"总食材: {len(items)}, 已匹配: {n_matched}, 未匹配/错误: {n_unmatched}", flush=True)
    print(f"营养库: {MATCHED_CSV}", flush=True)
    print(f"待处理: {UNMATCHED_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
