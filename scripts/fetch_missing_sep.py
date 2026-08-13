"""fetch_missing_sep.py —— 9月重叠未匹配食材 CFS 定向抓取(第二阶段, v2 多关键词回退)。

用法:
  python scripts/fetch_missing_sep.py
流程:
  1. 读 data/待补抓食材_9月重叠.json (未匹配清单)
  2. 对每个食材: 依次尝试搜索关键词(CFS 粤语叫法优先) → pick_best → fetch_nutrient
  3. 收集: 匹配成功的行 → data/samples/fetched_missing_rows.json; 未匹配 → 打印待人工
  (不直接合并主库, 先人工审查可疑匹配再合并)
"""
from __future__ import annotations

import csv
import difflib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batch_fetch_cfs import make_search_keyword, pick_best  # noqa: E402
from cfs_fetch import fetch_nutrient, search_food, to_profile_row  # noqa: E402

WORKDIR = Path(__file__).resolve().parent.parent
MISSING_JSON = WORKDIR / "data" / "待补抓食材_9月重叠.json"
OUT_JSON = WORKDIR / "data" / "samples" / "fetched_missing_rows.json"
DB_CSV = WORKDIR / "data" / "ingredient_nutrients.csv"

# SOP名 -> [搜索关键词列表, 依次尝试](CFS 粤语叫法优先)
KEYWORD_CHAINS: dict[str, list[str]] = {
    "鮮菇粉": ["冬菇粉", "香菇粉", "冬菇"],
    "照燒汁": ["照燒", "燒汁"],
    "合掌瓜肉 <切角>": ["佛手瓜", "合掌瓜"],
    "合掌瓜肉 <切絲>": ["佛手瓜", "合掌瓜"],
    "淮山肉 <切角>": ["山藥", "淮山"],
    "泰國紅米": ["紅米", "糙米"],
    "鮮露": ["魚露"],
    "沙爹醬": ["沙嗲", "沙嗲醬"],
    "豆辦醬": ["豆瓣醬"],
    "黑磨豉醬": ["麵豉", "豉醬"],
    "牛坑腩切": ["牛腩"],
    "<清洗>紹菜": ["黃芽白", "紹菜", "白菜"],
    "紹菜": ["黃芽白", "紹菜", "白菜"],
    "京蔥": ["大蔥", "青蔥", "蔥"],
    "青椒絲": ["甜椒", "青椒", "燈籠椒"],
    "青椒角": ["甜椒", "青椒", "燈籠椒"],
    "紅椒絲": ["紅甜椒", "甜椒"],
    "紅圓椒肉 <切角>": ["紅甜椒", "甜椒", "圓椒"],
    "紅圓椒絲": ["紅甜椒", "甜椒", "圓椒"],
    "黃圓椒肉 <切角>": ["黃甜椒", "甜椒", "圓椒"],
    "黃圓椒絲": ["黃甜椒", "甜椒", "圓椒"],
    "紫芯蕃薯肉 <切粒>": ["紫薯", "番薯", "紫心番薯"],
    "300+龍利柳(白盒)": ["龍利柳", "魚柳"],
    "扭扭粉彎曲通心粉（山麥）": ["通心粉", "扭扭粉", "意粉"],
    "黑松露醬": ["黑松露", "蘑菇", "冬菇"],
    "黑松露油": ["黑松露", "蘑菇", "冬菇"],
    "姜蓉（沙师弟）": ["薑"],
    "煮饭油（沙师弟）": ["粟米油", "菜籽油", "大豆油"],
    "豬頸肉片": ["豬頸肉", "豬肉"],
    "豬軟骨": ["豬軟骨", "豬骨"],
    "玉子豆腐": ["玉子豆腐", "雞蛋豆腐", "豆腐"],
    "珍珠雞": ["珍珠雞"],
    "素牛扒": ["素肉", "素雞"],
    "素鴨": ["素鴨", "素雞"],
    "荷蘭豆": ["荷蘭豆"],
    "什豆": ["雜豆", "豆"],
    "披薩": ["薄餅", "披薩", "比薩"],
    "薯蓉粉": ["薯蓉", "馬鈴薯"],
    "柱侯醬": ["柱侯", "麵豉"],
    "<清洗>小棠菜苗": ["小棠菜", "白菜", "菜心"],
    "雞下脾": ["雞下脾", "雞脾", "雞腿"],
    "蟹柳": ["蟹棒", "蟹柳", "仿蟹"],
    "牛肉丸2個": ["牛丸", "牛肉丸"],
    "肉丸2個": ["牛丸", "豬肉丸", "牛肉丸"],
}

# 已知同物异名(SOP名 -> CFS名), sim 低也接受
KNOWN_EQUIVALENT = {
    "合掌瓜肉 <切角>": ["佛手瓜"],
    "合掌瓜肉 <切絲>": ["佛手瓜"],
    "淮山肉 <切角>": ["山藥"],
    "泰國紅米": ["糙米"],
    "鮮菇粉": ["冬菇", "香菇"],
    "青椒絲": ["甜椒", "青椒"],
    "青椒角": ["甜椒", "青椒"],
    "紅椒絲": ["紅甜椒", "甜椒"],
    "紅圓椒肉 <切角>": ["紅甜椒", "甜椒"],
    "紅圓椒絲": ["紅甜椒", "甜椒"],
    "黃圓椒肉 <切角>": ["黃甜椒", "甜椒"],
    "黃圓椒絲": ["黃甜椒", "甜椒"],
    "紹菜": ["白菜", "黃芽白"],
    "<清洗>紹菜": ["白菜", "黃芽白"],
    "<清洗>小棠菜苗": ["白菜", "小棠菜"],
    "薯蓉粉": ["馬鈴薯", "薯蓉"],
    "姜蓉（沙师弟）": ["薑"],
    "煮饭油（沙师弟）": ["粟米油", "菜籽油", "大豆油"],
    "扭扭粉彎曲通心粉（山麥）": ["通心粉", "通心麵", "意粉"],
    "玉子豆腐": ["豆腐"],
    "素牛扒": ["素雞", "素肉"],
    "素鴨": ["素雞", "素鴨"],
    "什豆": ["豆"],
    "雞下脾": ["雞脾", "雞腿"],
}

SCORE_THRESHOLD = 0.6
MAX_KEYWORDS = 3


def main() -> int:
    missing = json.loads(MISSING_JSON.read_text(encoding="utf-8"))
    db_names = {r["ingredient_name"].strip() for r in csv.DictReader(DB_CSV.open(encoding="utf-8-sig"))}
    matched_rows = []
    unmatched = []
    print(f"待抓取 {len(missing)} 种(已剔除库内同名)\n")

    for name, count in sorted(missing.items(), key=lambda x: -x[1]):
        if name.strip() in db_names:
            print(f"  [跳过] {name} 库内已存在同名")
            continue
        chains = KEYWORD_CHAINS.get(name) or [make_search_keyword(name)]
        best_pair = None
        for kw in chains[:MAX_KEYWORDS]:
            try:
                candidates = search_food(kw)
            except Exception as exc:  # noqa: BLE001
                print(f"  [ERR] {name} (kw={kw}): {exc}")
                continue
            best, score = pick_best(candidates, kw)
            time.sleep(0.3)
            if best is not None and score >= SCORE_THRESHOLD:
                best_pair = (best, score, kw)
                break
        if best_pair is None:
            print(f"  ✗ {name:<20} 无匹配 (尝试 {chains[:MAX_KEYWORDS]})")
            unmatched.append({"name": name, "reason": f"无匹配 尝试={chains[:MAX_KEYWORDS]}"})
            continue
        best, score, used_kw = best_pair
        try:
            detail = fetch_nutrient(best.fg_id, best.fsg_id, best.food_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {name:<20} 详情失败: {exc}")
            unmatched.append({"name": name, "reason": f"详情失败: {exc}"})
            continue
        row = to_profile_row(detail, ingredient_code="", ingredient_name=name, matched_name=best.name)
        # 判定: 混合菜(饭/面/汤/粉/包/肚/三文治等)一律拒; 其余按 相似度或已知同物异名表 接受
        sim = difflib.SequenceMatcher(None, name.replace(" ", ""), best.name).ratio()
        mixed_dish = any(k in best.name for k in ("飯", "麵", "湯", "粉", "三文治", "薄餅", "披薩", "包", "肚", "粥"))
        equivalent = any(e in best.name for e in KNOWN_EQUIVALENT.get(name, []))
        accept = (not mixed_dish) and (sim >= 0.35 or equivalent)
        row["_matched_name"] = best.name
        row["_score"] = round(score, 2)
        row["_suspicious"] = not accept
        if accept:
            matched_rows.append(row)
            print(f"  ✓ {name:<20} -> {best.name} (score {score:.2f}, sim {sim:.2f})")
        else:
            unmatched.append({"name": name, "reason": f"拒绝: {best.name} (mixed={mixed_dish}, sim {sim:.2f}, equiv {equivalent})"})
            print(f"  ✗ {name:<20} -> {best.name} 拒绝 (mixed={mixed_dish})")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(matched_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n收录 {len(matched_rows)} 种 -> {OUT_JSON}")
    print(f"未收录 {len(unmatched)} 种:")
    for u in unmatched:
        print(f"  - {u['name']}: {u['reason']}")
    return 0


if __name__ == "__main__":
    main()
