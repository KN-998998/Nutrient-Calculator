from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from .models import NUTRIENT_FIELDS, NutrientProfile


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = text.replace("臺", "台").replace("鷄", "雞").replace("葱", "蔥")
    return re.sub(r"[\s<>()（）\[\]【】_/\-]+", "", text)


def _number(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = (row.get(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"字段 {key} 不是有效数字: {raw!r}") from exc


class NutrientRepository:
    """营养数据库仓库。

    匹配策略（v2，重复编码消歧）：
    - 编码存在且唯一：直接返回（编码优先于名称，保持原行为）。
    - 编码存在但重复：必须结合食材名称消歧；无法唯一确认时返回 None，
      让上层把结果标记为 incomplete，绝不静默猜测。
    - 无编码或编码未命中：按名称查找；先精确匹配，再包含匹配，仍歧义返回 None。
    """

    def __init__(self, profiles: list[NutrientProfile]):
        self.profiles = profiles
        self._by_code: dict[str, list[NutrientProfile]] = {}
        self._by_name: dict[str, list[NutrientProfile]] = {}
        for profile in profiles:
            code = profile.ingredient_code.strip().upper()
            if code:
                self._by_code.setdefault(code, []).append(profile)
            for name in (profile.ingredient_name, *profile.aliases):
                normalized = normalize_name(name)
                if normalized:
                    bucket = self._by_name.setdefault(normalized, [])
                    if profile not in bucket:  # 同一 profile 去重(名称与别名重复时)
                        bucket.append(profile)

    @classmethod
    def from_csv(cls, path: str | Path) -> "NutrientRepository":
        profiles: list[NutrientProfile] = []
        with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), start=2):
                if not (row.get("ingredient_code") or row.get("ingredient_name")):
                    continue
                try:
                    values = {field: _number(row, field) for field in NUTRIENT_FIELDS}
                    aliases = tuple(x.strip() for x in (row.get("aliases") or "").split("|") if x.strip())
                    source = (row.get("source") or "").strip()
                    carb = values["available_carbohydrate_g"]
                    # 纤维"已知"= 单元格有数值(含纯物质纤维=0: 糖/牛油/味精, 化学事实);
                    # 纤维"真缺失" = 单元格为空/ND/NA/Trace (CFC 详情页无纤维数据)
                    raw_fibre = (row.get("dietary_fibre_g") or "").strip()
                    fibre_known = raw_fibre not in ("", "ND", "NA", "Trace", "trace", "N/A")
                    # CFC 来源、纤维真缺失且碳水>1 → 碳水口径未换算, 待核验
                    carb_uncertain = "CFC" in source and not fibre_known and carb > 1
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
                            **values,
                        )
                    )
                except ValueError as exc:
                    raise ValueError(f"营养数据库第 {row_number} 行错误: {exc}") from exc
        return cls(profiles)

    def find(self, code: str = "", name: str = "") -> NutrientProfile | None:
        if code:
            candidates = self._by_code.get(code.strip().upper())
            if candidates:
                if len(candidates) == 1:
                    return candidates[0]
                # 重复编码：必须结合名称消歧
                if name:
                    resolved = self._disambiguate(candidates, name)
                    if resolved is not None:
                        return resolved
                # 编码歧义且名称无法唯一消歧 → 不返回, 落到名称查找
                # (真实 SOP 常带过期/冲突编码, 但名称本身唯一)
        # 无编码、编码未命中、或编码歧义消歧失败：按名称查找
        if name:
            # 水(清水/水): 营养等价0, 同名多行歧义无意义 → 直接返回水行, 不污染菜式状态
            if name.strip() in ("清水", "水"):
                for profile in self.profiles:
                    if "水(无营养)" in profile.source:
                        return profile
            candidates = self._name_candidates(name)
            if candidates:
                if len(candidates) == 1:
                    return candidates[0]
                resolved = self._disambiguate(candidates, name)
                if resolved is not None:
                    return resolved
                return None
        return None

    def _name_candidates(self, name: str) -> list[NutrientProfile] | None:
        """按名称取候选：先精确键，再包含扫描（去重）。"""
        norm = normalize_name(name)
        if not norm:
            return None
        exact = self._by_name.get(norm)
        if exact:
            return exact
        found: list[NutrientProfile] = []
        seen: set[int] = set()
        for key, profiles in self._by_name.items():
            if norm in key:
                for profile in profiles:
                    if id(profile) not in seen:
                        seen.add(id(profile))
                        found.append(profile)
        return found or None

    def _disambiguate(self, candidates: list[NutrientProfile], name: str) -> NutrientProfile | None:
        """在候选池内按名称消歧：完全相等 → 前缀 → 包含；唯一命中才返回。"""
        norm = normalize_name(name)
        if not norm:
            return None
        # 1) 名称或别名完全相等
        exact = [
            p for p in candidates
            if normalize_name(p.ingredient_name) == norm
            or any(normalize_name(a) == norm for a in p.aliases)
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return None
        # 2) 名称或别名以输入开头
        starts = [
            p for p in candidates
            if normalize_name(p.ingredient_name).startswith(norm)
            or any(normalize_name(a).startswith(norm) for a in p.aliases)
        ]
        if len(starts) == 1:
            return starts[0]
        if len(starts) > 1:
            return None
        # 3) 名称或别名包含输入
        contains = [
            p for p in candidates
            if norm in normalize_name(p.ingredient_name)
            or any(norm in normalize_name(a) for a in p.aliases)
        ]
        if len(contains) == 1:
            return contains[0]
        return None
