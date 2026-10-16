from __future__ import annotations

import csv
import math
import re
import unicodedata
from pathlib import Path

from .models import NUTRIENT_FIELDS, NutrientProfile


_RAW_ONION_NAMES = {"洋蔥", "洋蔥絲", "洋蔥粒", "洋蔥角", "洋蔥肉 <切絲>", "洋蔥肉 <切粒>"}
_ANIMAL_WORDS = (
    "魚", "鱼", "蝦", "虾", "蟹", "雞", "鸡", "鴨", "鸭", "豬", "猪",
    "牛", "羊", "魚柳", "鱼柳",
)

# 等价学名桥：在 aggressive（fallback）模式下，把索引/查询键同时扩展到这些等价词，
# 以打通 SOP 香港俗名 ↔ CFC 学名 的差异（例：甘筍 ↔ 胡蘿蔔，黃芽白 ↔ 大白菜）。
_CANONICAL_SYNONYMS: tuple[tuple[str, ...], ...] = (
    ("甘筍", "胡蘿蔔", "紅蘿蔔", "胡萝卜", "红萝卜", "甘荀"),
    ("枸杞菜", "枸杞葉"),
    ("枸杞子", "杞子"),
    ("番薯", "甘薯", "红薯", "紅薯", "白薯", "蕃薯"),
    ("大白菜", "黃芽白", "紹菜", "白菜"),
    ("甜椒", "圓椒", "西椒", "燈籠椒", "黄圆椒", "黃圓椒", "紅圓椒", "紅西椒", "黃西椒", "彩椒"),
    ("佛手瓜", "合掌瓜", "棒瓜", "菜餚梨"),
    ("南瓜", "倭瓜", "番瓜", "青皮南瓜"),
    ("番茄", "蕃茄"),
    ("馬鈴薯", "薯仔", "土豆", "馬鈴薯"),
    ("玉米", "粟米", "栗米", "苞谷", "玉蜀黍"),
    # 西椰菜(粤语/香港学生餐) = 西蘭花(broccoli)，≠ 椰菜花(cauliflower)
    ("西椰菜", "西蘭花", "西兰花", "綠菜花", "绿菜花", "青花菜"),
    ("豆油", "大豆油"),
    ("麵條", "面条"),
    ("米粉", "秈米粉", "米線", "米线"),
    ("什果", "熱帶雜果", "什錦水果"),
    # 雞絲（去皮切丝）通常用雞胸肉，CFC 有「雞胸脯肉」133 kcal
    ("雞絲", "雞胸脯肉", "雞胸肉"),
    # 銀芽 = 去根綠豆芽；牛坑腩 = 牛腩部位；中芹 = 芹菜
    ("銀芽", "綠豆芽", "豆芽"),
    ("牛坑腩", "牛肉", "牛腩"),
    ("中芹", "芹菜", "藥芹", "旱芹"),
    # 麵粉 = 小麥粉；金菇 = 金針菇；蜆肉 = 河蜆
    ("麵粉", "小麥粉", "面粉"),
    ("金菇", "金針菇"),
    ("蜆肉", "河蜆"),  # 不含单字"蜆"避免 contains 误配
    ("蒜容", "蒜蓉"),  # SOP 常见错字
    # 雞脾菇(港式)=杏鲍菇；煙肉=培根；雜豆=三色豆
    ("雞脾菇", "杏鲍菇", "杏鮑菇", "雞腿菇"),
    ("煙肉", "培根"),
    ("雜豆", "三色豆", "杂豆"),
    # 蜆殼粉=意粉的一種（shell pasta）
    ("蜆殼粉", "通心粉", "意粉", "意大利粉"),
)


def _canonical_expand(normed: str) -> set[str]:
    """返回包含 normed 自身的等价学名集合（用于 fallback aggressive 建索引/查询）。"""
    result = {normed}
    if not normed:
        return result
    for group in _CANONICAL_SYNONYMS:
        norms = {normalize_name_for_fallback(g) for g in group}
        if normed in norms:
            result.update(norms)
            break
    return result


def _is_quarantined_profile(profile: NutrientProfile) -> bool:
    """Exclude known CFS deep-fried onion data from raw-onion SOP matches."""
    return (
        profile.ingredient_name.strip() in _RAW_ONION_NAMES
        and profile.energy_kcal >= 300
    )


def _is_semantically_incompatible(profile: NutrientProfile, input_name: str) -> bool:
    """Prevent a vegetarian ingredient from falling through to an animal profile, and vice versa.
    双向校验：
      1) SOP 写了"素"，但候选包含动物词且未标素 → 不兼容（原规则）
      2) SOP 没写"素"，但候选 ingredient/aliases 带"素" → 不兼容（例：去皮雞絲 ≠ 素雞絲卷）
    """
    normalized = normalize_name(input_name)
    # 1) SOP 显式素菜 → 候选不能是"名字含动物词但未标素"
    if "素" in normalized:
        for component in (profile.ingredient_name, *profile.aliases):
            component_text = normalize_name(component)
            if "素" in component_text or "植物" in component_text or "齋" in component_text or "大豆" in component_text or "蛋白" in component_text:
                continue
            if any(word in component_text for word in _ANIMAL_WORDS):
                return True
        return False
    # 2) SOP 没写"素" → 候选若显式标"素"，除非 SOP 食材名本身也暗示素
    if input_name.strip():
        has_vegetable_root = any(w in normalized for w in ("青菜", "白菜", "菠菜", "芹菜", "豆腐", "菇", "木耳"))
        if has_vegetable_root:
            return False
        profile_text = normalize_name(profile.ingredient_name + "".join(profile.aliases))
        if "素" in profile_text:
            # 只有当 profile 主体是动物肉（雞/牛/豬）但又标"素"时才一定不兼容
            # （素雞絲卷/素牛肉片 都是豆制品，不能当真鸡肉/牛肉用）
            if any(word + "絲" in profile_text or word + "片" in profile_text or word + "粒" in profile_text
                   for word in ("雞", "牛", "豬", "猪", "鸭", "鴨", "鱼", "魚", "蝦", "虾", "蟹", "鸡")):
                return True
            if any(word in profile_text for word in _ANIMAL_WORDS):
                return True
    return False


def normalize_name(value: str) -> str:
    """主库/默认 归一化：保持宽松、稳定的历史行为，仅去符号与繁简统一。
    （原来的 299 行手工 aliases 依赖这种严格性；如果这里清洗过度，会把已精确匹配的变成歧义）。
    """
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = text.replace("臺", "台").replace("鷄", "雞").replace("葱", "蔥")
    return re.sub(r"[\s<>()（）\[\]【】_/\-]+", "", text)


def normalize_name_for_fallback(value: str) -> str:
    """fallback（国内 CFC）专用的激进归一化：提 SOP 根词，去掉 <切絲>/25KG/品牌/形态词。
    与 CFC fallback CSV 的 aliases 构造策略呼应，以实现「SOP 叫法 ↔ CFC 学名」的宽松匹配。
    """
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    # 繁简统一：简体→繁体（SOP 用繁体，CFC 部分条目用简体）
    _SIMP_TO_TRAD = str.maketrans({
        "葱": "蔥", "萝": "蘿", "卜": "蔔", "鸡": "雞", "猪": "豬",
        "鱼": "魚", "虾": "蝦", "饭": "飯", "汤": "湯",
        "酱": "醬", "盐": "鹽", "笋": "筍", "姜": "薑", "肠": "腸",
        "脑": "腦", "头": "頭", "贝": "貝", "苹": "蘋", "烧": "燒",
        "烟": "煙", "凤": "鳳", "厨": "廚", "条": "條", "针": "針",
        "丝": "絲", "壳": "殼", "钉": "釘", "仑": "崙", "团": "團",
        "圆": "圓", "块": "塊", "须": "須",
    })
    text = text.translate(_SIMP_TO_TRAD)
    text = text.replace("臺", "台").replace("鷄", "雞")
    # 先按 "/" 取第一段（如 "豆油/15L 福字生油" → "豆油"），必须在去符号前做
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    # 0) 国别/产地词 + 品种前缀词（去掉后不影响食材本体）
    for prefix in ("日本", "泰國", "韓國", "西班牙", "意大利", "美國", "澳洲", "本地", "巴西",
                   "紫芯", "紫心", "紅心", "黃心", "龍口"):
        text = text.replace(prefix, "")
    # 0.5) 粤语/国语的小称后缀（不改变食材本体）
    for dim in ("仔", "細", "小"):
        if text.endswith(dim) and len(text) > len(dim) + 1:
            text = text[: -len(dim)]
    for w in (
        "切絲", "切粒", "切丁", "切條", "切片", "切角", "切塊", "切碎", "切朵",
        "切半", "切一開二", "一開二", "切圈", "切半圓片", "切圈片",
        "去骨", "去皮", "去殼", "醃製", "腌制", "清洗", "濕", "熟",
        "有皮", "無皮", "連皮", "不連皮", "黑帶", "箱拆包", "拆包", "切段", "貓耳朵", "108倉", "包",
    ):
        text = text.replace(w, "")
    text = re.sub(r"\b\d+[a-z+]+\b", "", text)
    text = re.sub(r"x\d+(?:kg|g|ml|l|lb|包|箱|罐)", "", text)
    text = re.sub(r"\d+(?:kg|lb|ml|g|l|磅|包|個|條|裝|ml裝)", "", text)
    # 去掉残留的独立数字前缀（如 "6X1KG 香菇精粉" → "6香菇精粉" → "香菇精粉"）
    text = re.sub(r"^\d+", "", text)
    for brand in ("福字", "家樂牌", "雙囍牌", "大紅日", "大廚師", "紅日",
                   "滿姨", "大利", "塔牌", "地捫", "地扪", "李錦記", "omnipork", "omnimeat", "珍珠"):
        text = text.replace(brand.lower(), "")
    text = re.sub(r"[\s<>()（）\[\]【】_/\-+*#%&|]+", "", text)
    text = text.replace("牌", "")
    # 英文残留词（strip / pork / meat 等，\b 在中英文边界不生效，直接 replace）
    for eng in ("strip", "pork", "meat"):
        text = text.replace(eng, "")
    # 形态尾词剥离：>=3 字符才剥（"洋蔥絲"→"洋蔥"），避免 2 字核心词被误伤（"豆腐"）
    # 注意："肉"不是切法后缀，不剥（素肉/午餐肉/雞肉 是食材本体）
    if len(text) >= 3:
        text = re.sub(r"(角|粒|絲|丁|條|片)$", "", text)
    return text.strip()


def _number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = (row.get(key) or "").strip()
    if _is_missing_value(raw):
        return default
    try:
        value = float(raw)
        if not math.isfinite(value) or value < 0:
            raise ValueError("必须为非负有限数值")
        return value
    except ValueError as exc:
        raise ValueError(f"字段 {key} 不是有效数字: {raw!r}") from exc


def _is_missing_value(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"", "nd", "na", "n/a", "trace"}


def _classify_source(source: str) -> str:
    """Return a stable source category for policy decisions and UI warnings."""
    text = source.strip()
    if "无营养" in text:
        return "water_zero"
    if "人工补录" in text:
        if any(marker in text for marker in ("官方营养标签", "官方營養標籤", "包装营养标签", "包裝營養標籤")):
            return "manual_brand_label"
        if any(marker in text for marker in ("通用值", "估算", "均值", "参考资料")):
            return "manual_estimate"
        return "manual_reference"
    if "CFC" in text:
        return "official_cfc"
    if any(marker in text for marker in ("食安中心", "食品安全中心", "FRL")):
        return "official_hk"
    if "官方营养标签" in text or "官方營養標籤" in text:
        return "official_brand_label"
    return "reference_other" if text else "unknown"


MATCH_TIER_LABELS = {
    "hong_kong_official": "香港 CFS/FRL 官方資料",
    "water_zero": "清水（不計營養素）",
    "brand_label": "品牌／包裝營養標籤",
    "fallback_cfc": "CFC 中國食物成分資料",
    "fallback_international": "非香港國際參考資料",
    "manual_reference": "人工整理參考資料",
    "generic_estimate": "通用估算資料",
    "unknown_fallback": "來源待確認資料",
}

FALLBACK_TIER_ORDER = (
    "brand_label",
    "fallback_cfc",
    "fallback_international",
    "manual_reference",
    "generic_estimate",
    "unknown_fallback",
)


def source_match_tier(profile: NutrientProfile) -> str:
    """Map source metadata to the Hong Kong-first matching policy tier."""
    source_type = profile.source_type
    if not source_type or source_type == "unknown":
        source_type = _classify_source(profile.source)
    return {
        "official_hk": "hong_kong_official",
        "water_zero": "water_zero",
        "official_brand_label": "brand_label",
        "manual_brand_label": "brand_label",
        "official_cfc": "fallback_cfc",
        "reference_other": "fallback_international",
        "manual_reference": "manual_reference",
        "manual_estimate": "generic_estimate",
    }.get(source_type, "unknown_fallback")


def source_label(profile: NutrientProfile) -> str:
    return MATCH_TIER_LABELS[source_match_tier(profile)]


def source_requires_review(profile: NutrientProfile) -> bool:
    return source_match_tier(profile) not in {"hong_kong_official", "water_zero"}


def _is_water_name(value: str) -> bool:
    """Recognise water labels plus Excel formula/cell-reference residue."""
    text = unicodedata.normalize("NFKC", value or "").strip()
    return bool(re.fullmatch(
        r"(?:清水|水|冰水)(?:\s*\+\s*(?:[A-Z]{1,3}\d+){1,2}(?::[A-Z]{1,3}\d+)?)?",
        text,
        flags=re.IGNORECASE,
    ))


def _resolve_canonical_code(
    row: dict[str, str], profiles: list[NutrientProfile],
) -> str:
    """Resolve a mapping row against the currently selected standard.

    Historical mappings may retain a Hong Kong code while their canonical
    name points to a CFC entity. When that code is absent from the selected
    database, resolve the unique canonical name instead of dropping the alias.
    """
    code = (row.get("canonical_code") or row.get("matched_code") or "").strip().upper()
    valid_codes = {
        profile.ingredient_code.strip().upper()
        for profile in profiles if profile.ingredient_code.strip()
    }
    if code in valid_codes:
        return code
    canonical_name = (row.get("canonical_name") or row.get("matched_name") or "").strip()
    if not canonical_name:
        return ""
    strict = normalize_name(canonical_name)
    candidates = [
        profile for profile in profiles
        if normalize_name(profile.ingredient_name) == strict
    ]
    if len(candidates) == 1:
        return candidates[0].ingredient_code.strip().upper()
    return ""


class NutrientRepository:
    """营养数据库仓库。

    匹配策略（v2，重复编码消歧）：
    - 编码存在且唯一：直接返回（编码优先于名称，保持原行为）。
    - 编码存在但重复：必须结合食材名称消歧；无法唯一确认时返回 None，
      让上层把结果标记为 incomplete，绝不静默猜测。
    - 无编码或编码未命中：按名称查找；先精确匹配，再包含匹配，仍歧义返回 None。

    新增 v3 回退（fallback）模式：
    - 构造时可传入 `fallback_profiles`（国内 CFC 等），这些 profile 仅在主库未命中时参与匹配；
    - 命中来源含「国内参考」的 profile 在 source 字段带标记，上层可据此生成告警。
    """

    def __init__(
        self,
        profiles: list[NutrientProfile],
        fallback_profiles: list[NutrientProfile] | None = None,
        alias_map: dict[str, str] | None = None,
        alias_normalized_map: dict[str, str] | None = None,
    ):
        # 隔离：fallback 只在主库查找失败后单独跑，不参与主库的编码/名称索引
        # （否则 CFC 1200+ 条学会名会在"包含匹配"阶段把大量精确匹配顶成歧义）
        self.profiles = profiles
        self._corrections: dict[str, NutrientProfile | None] = {}
        self.correction_notes: dict[str, str] = {}
        self.fallback_profiles = list(fallback_profiles) if fallback_profiles else []
        self._primary = NutrientRepository._build_index(profiles)
        # Keep the combined index for backwards-compatible diagnostics, while
        # runtime matching walks explicit tiers so a lower-quality source can
        # never win because of CSV row order or a shared code.
        self._fallback = NutrientRepository._build_index(
            self.fallback_profiles, aggressive=True,
        )
        grouped_fallbacks: dict[str, list[NutrientProfile]] = {}
        for profile in self.fallback_profiles:
            grouped_fallbacks.setdefault(source_match_tier(profile), []).append(profile)
        ordered_tiers = list(FALLBACK_TIER_ORDER)
        ordered_tiers.extend(
            sorted(tier for tier in grouped_fallbacks if tier not in FALLBACK_TIER_ORDER)
        )
        self._fallback_indexes = [
            (tier, NutrientRepository._build_index(grouped_fallbacks[tier], aggressive=True))
            for tier in ordered_tiers
            if grouped_fallbacks.get(tier)
        ]
        self._global_by_code: dict[str, list[NutrientProfile]] = {}
        for profile in profiles + self.fallback_profiles:
            code = profile.ingredient_code.strip().upper()
            if code:
                self._global_by_code.setdefault(code, []).append(profile)
        # SOP 别名快速查找表：sop_name → matched_code（从历史 SOP 匹配结果自动生成）
        # find() 时先查这张表，命中则直接按 code 取 profile，跳过归一化链
        # Copy caller-owned mappings so runtime registration cannot mutate an
        # external dict and so the repository owns its matching state.
        self._alias_map = dict(alias_map or {})
        self._alias_normalized_map = dict(alias_normalized_map or {})
        valid_codes = {
            profile.ingredient_code.strip().upper()
            for profile in profiles + self.fallback_profiles
            if profile.ingredient_code.strip()
        }
        self._alias_map = {
            alias: code for alias, code in self._alias_map.items()
            if code.upper() in valid_codes
        }
        self._alias_normalized_map = {
            alias: code for alias, code in self._alias_normalized_map.items()
            if code.upper() in valid_codes
        }

    def register_aliases(
        self,
        aliases: dict[str, str],
        normalized_aliases: dict[str, str] | None = None,
        *,
        override: bool = False,
    ) -> int:
        """Register curated aliases without exposing index implementation.

        Aliases targeting unknown codes are ignored. Existing mappings are
        preserved by default; callers must opt into ``override`` explicitly.
        The return value is the number of exact aliases accepted.
        """
        valid_codes = {
            profile.ingredient_code.strip().upper()
            for profile in self.profiles + self.fallback_profiles
            if profile.ingredient_code.strip()
        }
        accepted = 0
        for alias, code in aliases.items():
            alias_text = str(alias).strip()
            code_text = str(code).strip().upper()
            if not alias_text or code_text not in valid_codes:
                continue
            if override or alias_text not in self._alias_map:
                if alias_text not in self._alias_map:
                    accepted += 1
                self._alias_map[alias_text] = code_text
        for alias, code in (normalized_aliases or {}).items():
            alias_text = str(alias).strip()
            code_text = str(code).strip().upper()
            if not alias_text or code_text not in valid_codes:
                continue
            if override or alias_text not in self._alias_normalized_map:
                self._alias_normalized_map[alias_text] = code_text
        return accepted

    @staticmethod
    def _build_index(
        profiles: list[NutrientProfile],
        *,
        aggressive: bool = False,
    ) -> dict[str, object]:
        """建索引。
        - aggressive=False（主库）：严格 normalize_name，保持历史行为。
        - aggressive=True（fallback）：激进提根词 normalize_name_for_fallback，
          把「<切絲>」「25KG」「品牌」这些去掉后额外登记一份，命中机率提高。
        """
        normalizer = normalize_name_for_fallback if aggressive else normalize_name
        by_code: dict[str, list[NutrientProfile]] = {}
        by_name: dict[str, list[NutrientProfile]] = {}
        for profile in profiles:
            if _is_quarantined_profile(profile):
                continue
            code = profile.ingredient_code.strip().upper()
            if code:
                by_code.setdefault(code, []).append(profile)
            for name in (profile.ingredient_name, *profile.aliases):
                normalized = normalizer(name)
                if normalized:
                    keys = {normalized}
                    if aggressive:
                        keys.update(_canonical_expand(normalized))
                    for k in keys:
                        if not k:
                            continue
                        bucket = by_name.setdefault(k, [])
                        if profile not in bucket:
                            bucket.append(profile)
                # aggressive 模式再加一份"严格 normalize"作为兜底，别名表里有学名时也能抓
                if aggressive:
                    strict = normalize_name(name)
                    if strict and strict != normalized:
                        strict_keys = {strict}
                        strict_keys.update(_canonical_expand(strict))
                        for sk in strict_keys:
                            if not sk:
                                continue
                            bucket2 = by_name.setdefault(sk, [])
                            if profile not in bucket2:
                                bucket2.append(profile)
        return {"by_code": by_code, "by_name": by_name, "all_profiles": profiles,
                "aggressive": aggressive}

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        fallback_csvs: list[str | Path] | None = None,
        alias_map_csv: str | Path | None = None,
        alias_include_candidates: bool = False,
    ) -> "NutrientRepository":
        profiles = cls._load_csv(path)
        fallbacks: list[NutrientProfile] = []
        for fp in fallback_csvs or []:
            if Path(fp).exists():
                fallbacks.extend(cls._load_csv(fp))
        alias_map: dict[str, str] = {}
        alias_normalized_map: dict[str, str] = {}
        if alias_map_csv and Path(alias_map_csv).exists():
            alias_profiles = profiles + fallbacks
            alias_map = cls._load_alias_map(
                alias_map_csv, profiles=alias_profiles,
                include_candidates=alias_include_candidates,
            )
            alias_normalized_map = cls._load_alias_normalized_map(
                alias_map_csv, profiles=alias_profiles,
                include_candidates=alias_include_candidates,
            )
        repository = cls(
            profiles,
            fallbacks,
            alias_map=alias_map,
            alias_normalized_map=alias_normalized_map,
        )
        repository.load_corrections(Path(path).with_name("ingredient_nutrient_corrections.csv"))
        return repository

    def load_corrections(self, path: str | Path) -> None:
        """Exact SOP-name decisions take precedence over recycled codes and fuzzy aliases."""
        if not Path(path).exists():
            return
        profiles = {p.ingredient_code: p for p in self._load_csv(path)}
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                name = normalize_name(row["ingredient_name"])
                if name in self._corrections:
                    raise ValueError(f"修正档案食材名重复: {row['ingredient_name']}")
                action = row.get("action", "replace")
                if action not in {"replace", "block"}:
                    raise ValueError(f"不支持的修正动作: {action}")
                self._corrections[name] = None if action == "block" else profiles[row["ingredient_code"]]
                self.correction_notes[name] = row.get("repair_note", "")

    @staticmethod
    def _load_alias_map(
        path: str | Path,
        *,
        profiles: list[NutrientProfile] | None = None,
        include_candidates: bool = False,
    ) -> dict[str, str]:
        """加载 SOP 别名映射 CSV → {sop_name: matched_code}"""
        candidates: dict[str, set[str]] = {}
        with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                status = (row.get("mapping_status") or "confirmed").strip().lower()
                allowed = {"confirmed", "approved", "已确认", "确认"}
                if include_candidates:
                    allowed.add("candidate")
                if status not in allowed:
                    continue
                sop_name = (row.get("alias_name") or row.get("sop_name") or "").strip()
                matched_code = (row.get("canonical_code") or row.get("matched_code") or "").strip()
                if profiles and ("canonical_code" in row or "canonical_name" in row):
                    matched_code = _resolve_canonical_code(row, profiles)
                if sop_name and matched_code:
                    candidates.setdefault(sop_name, set()).add(matched_code.upper())
        # Names with multiple target codes are ambiguous.  Do not let CSV row
        # order silently select one of them for the runtime fast path.
        return {
            sop_name: next(iter(codes))
            for sop_name, codes in candidates.items()
            if len(codes) == 1
        }

    @staticmethod
    def _load_alias_normalized_map(
        path: str | Path,
        *,
        profiles: list[NutrientProfile] | None = None,
        include_candidates: bool = False,
    ) -> dict[str, str]:
        """Load only unambiguous normalized aliases from canonical mappings."""
        candidates: dict[str, set[str]] = {}
        with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                status = (row.get("mapping_status") or "confirmed").strip().lower()
                allowed = {"confirmed", "approved", "已确认", "确认"}
                if include_candidates:
                    allowed.add("candidate")
                if status not in allowed:
                    continue
                alias = (row.get("alias_normalized") or "").strip()
                if not alias:
                    alias = normalize_name((row.get("alias_name") or row.get("sop_name") or "").strip())
                code = (row.get("canonical_code") or row.get("matched_code") or "").strip().upper()
                if profiles and ("canonical_code" in row or "canonical_name" in row):
                    code = _resolve_canonical_code(row, profiles).upper()
                if alias and code:
                    candidates.setdefault(alias, set()).add(code)
        return {
            alias: next(iter(codes))
            for alias, codes in candidates.items()
            if len(codes) == 1
        }

    @staticmethod
    def _load_csv(path: str | Path) -> list[NutrientProfile]:
        profiles: list[NutrientProfile] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), start=2):
                if not (row.get("ingredient_code") or row.get("ingredient_name")):
                    continue
                try:
                    # NA/ND/Trace retain missing metadata, never become confirmed zero.
                    inferred = []
                    for parent, children in (
                        ("total_fat_g", ("saturated_fat_g", "trans_fat_g")),
                    ):
                        if not _is_missing_value(row.get(parent)) and _number(row, parent) == 0:
                            # Do not erase a reported Trace/ND or contradictory positive child.
                            if all(_is_missing_value(row.get(c)) or _number(row, c) == 0 for c in children):
                                for child in children:
                                    if (row.get(child) or "").strip().casefold() in {"", "na", "n/a"}:
                                        row[child] = "0"
                                        inferred.append(child)
                    values = {field: _number(row, field) for field in NUTRIENT_FIELDS}
                    aliases = tuple(x.strip() for x in (row.get("aliases") or "").split("|") if x.strip())
                    source = (row.get("source") or "").strip()
                    if inferred:
                        source += "；总脂肪为0，脂肪分项按同一报告精度记0：" + ",".join(inferred)
                    missing_nutrients = tuple(
                        field for field in NUTRIENT_FIELDS
                        if _is_missing_value(row.get(field))
                    )
                    source_type = (row.get("source_type") or "").strip() or _classify_source(source)
                    carb = values["available_carbohydrate_g"]
                    raw_fibre = (row.get("dietary_fibre_g") or "").strip()
                    fibre_known = raw_fibre not in ("", "ND", "NA", "Trace", "trace", "N/A")
                    # 国内参考 CFC、纤维真缺失且碳水>1 → 待核验
                    carb_uncertain = ("CFC" in source) and not fibre_known and carb > 1
                    profiles.append(
                        NutrientProfile(
                            ingredient_code=(row.get("ingredient_code") or "").strip(),
                            ingredient_name=(row.get("ingredient_name") or "").strip(),
                            aliases=aliases,
                            edible_fraction=_number(row, "edible_fraction", 1.0),
                            yield_factor=_number(row, "yield_factor", 1.0),
                            retention_factor=_number(row, "retention_factor", 1.0),
                            source=source,
                            source_food_id=(row.get("source_food_id") or "").strip(),
                            carb_uncertain=carb_uncertain,
                            source_type=source_type,
                            source_url=(row.get("source_url") or "").strip(),
                            source_date=(row.get("source_date") or "").strip(),
                            missing_nutrients=missing_nutrients,
                            is_zero_nutrient=(source_type == "water_zero"),
                            **values,
                        )
                    )
                except ValueError as exc:
                    raise ValueError(f"营养数据库第 {row_number} 行错误: {exc}") from exc
        return profiles

    def find(self, code: str = "", name: str = "") -> NutrientProfile | None:
        corrected_name = normalize_name(name)
        if corrected_name in self._corrections:
            return self._corrections[corrected_name]
        # SOP 别名只能在当前来源层内加速；它不能让非香港编码越过
        # 一个可用的香港名称候选。
        alias_code = None
        if name:
            alias_code = self._alias_map.get(name.strip())
            if alias_code is None:
                alias_code = self._alias_normalized_map.get(normalize_name(name))

        normalized_code = code.strip().upper()
        global_code_candidates = self._global_by_code.get(normalized_code, [])
        if len(global_code_candidates) > 1:
            # Duplicate codes can span source tiers (DTL0084 is the known
            # example). Resolve by the supplied food name before applying the
            # source hierarchy; never let splitting the catalogs make a
            # globally duplicated code look unique inside one tier.
            for index in [self._primary, *(item[1] for item in self._fallback_indexes)]:
                tier_candidates = [
                    profile for profile in index["by_code"].get(normalized_code, [])
                    if not _is_semantically_incompatible(profile, name)
                ]
                if not tier_candidates or not name:
                    continue
                resolved = NutrientRepository._disambiguate_static(
                    tier_candidates,
                    name,
                    aggressive=False,
                )
                if resolved is not None:
                    return resolved
            # No unique name confirmation: continue with name-only lookup.
            # The ambiguous code and any alias pointing at it are unsafe.
            code = ""
            if alias_code and alias_code.upper() == normalized_code:
                alias_code = None

        def find_alias_in(index: dict[str, object]) -> NutrientProfile | None:
            if not alias_code:
                return None
            candidates = index["by_code"].get(alias_code.upper())
            candidates = [
                profile for profile in (candidates or [])
                if not _is_semantically_incompatible(profile, name)
            ]
            if len(candidates) == 1:
                return candidates[0]
            if candidates and name:
                return NutrientRepository._disambiguate_static(
                    candidates,
                    name,
                    aggressive=bool(index.get("aggressive")),
                )
            return None

        alias_match = find_alias_in(self._primary)
        if alias_match is not None:
            return alias_match

        # 香港官方层按编码/名称完整查找。即使 SOP 带的是后备库编码，
        # 只要名称在香港层可确认，仍必须使用香港数据。
        result = self._find_in(self._primary, code, name)
        if result is not None:
            return result

        # 香港层未命中后，才按品牌标签、CFC、其他国际资料、估算值降级。
        for _tier, index in self._fallback_indexes:
            alias_match = find_alias_in(index)
            if alias_match is not None:
                return alias_match
            fallback_match = self._find_in(index, code, name)
            if fallback_match is not None:
                return fallback_match
        return None

    @staticmethod
    def _find_in(index: dict[str, object], code: str, name: str) -> NutrientProfile | None:
        by_code: dict[str, list[NutrientProfile]] = index["by_code"]
        by_name: dict[str, list[NutrientProfile]] = index["by_name"]
        all_profiles: list[NutrientProfile] = index["all_profiles"]
        aggressive: bool = bool(index.get("aggressive"))
        if code:
            candidates = by_code.get(code.strip().upper())
            if candidates:
                candidates = [
                    profile for profile in candidates
                    if not _is_semantically_incompatible(profile, name)
                ]
                if not candidates:
                    return None
                if len(candidates) == 1:
                    return candidates[0]
                if name:
                    resolved = NutrientRepository._disambiguate_static(
                        candidates, name, aggressive=aggressive,
                    )
                    if resolved is not None:
                        return resolved
        if name:
            if _is_water_name(name):
                for profile in all_profiles:
                    if profile.is_zero_nutrient or "水(无营养)" in profile.source:
                        return profile
            candidates = NutrientRepository._name_candidates_static(
                by_name, name, aggressive=aggressive,
            )
            if candidates:
                candidates = [
                    profile for profile in candidates
                    if not _is_semantically_incompatible(profile, name)
                ]
                if not candidates:
                    return None
                if len(candidates) == 1:
                    return candidates[0]
                resolved = NutrientRepository._disambiguate_static(
                    candidates, name, aggressive=aggressive,
                )
                if resolved is not None:
                    return resolved
                return None
        return None

    @staticmethod
    def _name_candidates_static(
        by_name: dict[str, list[NutrientProfile]], name: str, *, aggressive: bool = False,
    ) -> list[NutrientProfile] | None:
        norm_strict = normalize_name(name)
        norm_loose = normalize_name_for_fallback(name) if aggressive else None
        # 1) 精确键（严格/宽松各查一次；fallback 扩展等价学名；不重复）
        exact_keys: set[str] = set()
        for k in (norm_strict, norm_loose):
            if not k:
                continue
            exact_keys.add(k)
            if aggressive:
                exact_keys.update(_canonical_expand(k))
        buckets: list[list[NutrientProfile]] = []
        for key in exact_keys:
            exact = by_name.get(key)
            if exact:
                buckets.append(exact)
        if buckets:
            # 合并 + 按 id 去重
            seen: set[int] = set()
            merged: list[NutrientProfile] = []
            for b in buckets:
                for p in b:
                    if id(p) not in seen:
                        seen.add(id(p)); merged.append(p)
            return merged
        # 2) 包含扫描（主库：只按 strict 包含；fallback：strict+loose 任一包含都算；fallback 把等价词也当 needle）
        found: list[NutrientProfile] = []
        seen2: set[int] = set()
        keys_to_check: set[str] = set()
        for k in (norm_strict, norm_loose):
            if not k:
                continue
            keys_to_check.add(k)
            if aggressive:
                keys_to_check.update(_canonical_expand(k))
        for key, profiles in by_name.items():
            hit = any(needle and needle in key for needle in keys_to_check)
            if hit:
                for profile in profiles:
                    if id(profile) not in seen2:
                        seen2.add(id(profile))
                        found.append(profile)
        return found or None

    @staticmethod
    def _disambiguate_static(
        candidates: list[NutrientProfile], name: str, *, aggressive: bool = False,
    ) -> NutrientProfile | None:
        norm_s = normalize_name(name)
        norm_l = normalize_name_for_fallback(name) if aggressive else None
        if not norm_s:
            return None

        def name_keys(p: NutrientProfile):
            for text in (p.ingredient_name, *p.aliases):
                yield normalize_name(text)
                if aggressive:
                    yield normalize_name_for_fallback(text)

        def equivalent_roots(profiles: list[NutrientProfile]) -> bool:
            """aggressive fallback 专用：判断所有候选是否是同一个食材。
            等价条件：①所有 ingredient_name 的 loose norm + 等价扩展 两两有交集；或 ② ingredient_name 全同。
            """
            if len(profiles) <= 1:
                return True
            root_sets = []
            for p in profiles:
                base = normalize_name_for_fallback(p.ingredient_name) or normalize_name(p.ingredient_name)
                root_sets.append(_canonical_expand(base))
            # 所有 roots 集两两有交集
            for i in range(len(root_sets)):
                for j in range(i + 1, len(root_sets)):
                    if not (root_sets[i] & root_sets[j]):
                        return False
            return True

        def pick_equivalent(profiles: list[NutrientProfile]) -> NutrientProfile:
            """同根等价（如生洋葱 vs 脱水洋葱、水發木耳 vs 乾木耳）取能量最低者：
            SOP 食材几乎都是生鲜原料态，干制/脱水/油炸的能量明显更高，选低能量更贴近原料。
            """
            return min(profiles, key=lambda p: (p.energy_kcal, p.ingredient_code))

        for norm in {n for n in (norm_s, norm_l) if n}:
            # 优先：ingredient_name 精确匹配（而非 alias），避免 alias 污染
            name_exact = [p for p in candidates
                          if normalize_name(p.ingredient_name) == norm
                          or (aggressive and normalize_name_for_fallback(p.ingredient_name) == norm)]
            if len(name_exact) == 1:
                return name_exact[0]
            if len(name_exact) > 1:
                if aggressive and equivalent_roots(name_exact):
                    return pick_equivalent(name_exact)
                return None
            # 然后：alias 也算精确匹配
            exact = [p for p in candidates if any(k == norm for k in name_keys(p))]
            if len(exact) == 1:
                return exact[0]
            if len(exact) > 1:
                if aggressive and equivalent_roots(exact):
                    return pick_equivalent(exact)
                return None
        for norm in {n for n in (norm_s, norm_l) if n}:
            starts = [p for p in candidates if any(k.startswith(norm) for k in name_keys(p))]
            if len(starts) == 1:
                return starts[0]
            if len(starts) > 1:
                if aggressive and equivalent_roots(starts):
                    return pick_equivalent(starts)
                return None
        for norm in {n for n in (norm_s, norm_l) if n}:
            contains = [p for p in candidates if any(norm in k for k in name_keys(p))]
            if len(contains) == 1:
                return contains[0]
        # 最后：aggressive 模式下如果所有候选是等价食材，取能量最低者
        if aggressive and equivalent_roots(candidates):
            return pick_equivalent(candidates)
        return None
