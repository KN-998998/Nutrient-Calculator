from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Protocol

from .models import NUTRIENT_FIELDS, Recipe


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    return " ".join(text.split())


def recipe_fingerprint(recipe: Recipe, *, recipe_version: str = "") -> str:
    """Create a stable identity from the recipe, independent of upload date/sheet."""
    ingredients = []
    for ingredient in recipe.ingredients:
        ingredients.append(
            {
                "code": _normalize_text(ingredient.ingredient_code),
                "name": _normalize_text(ingredient.ingredient_name),
                "component": _normalize_text(ingredient.component_name),
                "grams": round(float(ingredient.grams), 6),
                "edible_fraction": ingredient.edible_fraction,
                "yield_factor": ingredient.yield_factor,
                "retention_factor": ingredient.retention_factor,
            }
        )
    ingredients.sort(key=lambda item: (item["code"], item["name"], item["component"], item["grams"]))
    payload = {
        "recipe_name": _normalize_text(recipe.recipe_name),
        "school_stage": _normalize_text(recipe.school_stage),
        "calculation_standard": _normalize_text(recipe.calculation_standard),
        "recipe_version": _normalize_text(recipe_version),
        "ingredients": ingredients,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def default_history_db_path(app_name: str = "NutritionTool") -> Path:
    """Return a user-data path that survives application upgrades and reinstalls."""
    if sys.platform.startswith("win"):
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / app_name / "nutrition_history.sqlite3"


@dataclass(frozen=True)
class HistoryRecord:
    fingerprint: str
    recipe_name: str
    system_nutrients: dict[str, float]
    confirmed_nutrients: dict[str, float]
    revision: int
    confirmed_at: str
    source: str
    reason: str


class HistoryRepository(Protocol):
    def find_confirmed(self, recipe: Recipe) -> HistoryRecord | None:
        ...

    def save_confirmation(
        self,
        recipe: Recipe,
        system_nutrients: Mapping[str, float],
        confirmed_nutrients: Mapping[str, float],
        *,
        reason: str = "",
        source: str = "desktop",
    ) -> HistoryRecord:
        ...


class SQLiteHistoryRepository:
    """Local history store for the desktop application."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS dish_history (
                    fingerprint TEXT PRIMARY KEY,
                    recipe_name TEXT NOT NULL,
                    system_nutrients TEXT NOT NULL,
                    confirmed_nutrients TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    confirmed_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dish_history_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    system_nutrients TEXT NOT NULL,
                    confirmed_nutrients TEXT NOT NULL,
                    changed_fields TEXT NOT NULL,
                    confirmed_at TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    FOREIGN KEY (fingerprint) REFERENCES dish_history(fingerprint)
                );
                CREATE INDEX IF NOT EXISTS idx_history_recipe_name
                    ON dish_history(recipe_name);
                """
            )
        finally:
            connection.close()

    @staticmethod
    def _nutrients(values: Mapping[str, float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for field in NUTRIENT_FIELDS:
            value = values.get(field, 0.0)
            if isinstance(value, bool):
                raise ValueError(f"{field} must be a finite number")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{field} must be a finite number") from exc
            if number != number or number in (float("inf"), float("-inf")) or number < 0:
                raise ValueError(f"{field} must be a finite non-negative number")
            result[field] = round(number, 6)
        return result

    @staticmethod
    def _record(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(
            fingerprint=row["fingerprint"],
            recipe_name=row["recipe_name"],
            system_nutrients=json.loads(row["system_nutrients"]),
            confirmed_nutrients=json.loads(row["confirmed_nutrients"]),
            revision=int(row["revision"]),
            confirmed_at=row["confirmed_at"],
            source=row["source"],
            reason=row["reason"],
        )

    def find_confirmed(self, recipe: Recipe) -> HistoryRecord | None:
        fingerprint = recipe_fingerprint(recipe)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM dish_history WHERE fingerprint = ?", (fingerprint,)
            ).fetchone()
        finally:
            connection.close()
        return self._record(row) if row else None

    def save_confirmation(
        self,
        recipe: Recipe,
        system_nutrients: Mapping[str, float],
        confirmed_nutrients: Mapping[str, float],
        *,
        reason: str = "",
        source: str = "desktop",
    ) -> HistoryRecord:
        fingerprint = recipe_fingerprint(recipe)
        system = self._nutrients(system_nutrients)
        confirmed = self._nutrients(confirmed_nutrients)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        system_json = json.dumps(system, ensure_ascii=False, sort_keys=True)
        confirmed_json = json.dumps(confirmed, ensure_ascii=False, sort_keys=True)
        connection = self._connect()
        try:
            with connection:
                previous = connection.execute(
                    "SELECT * FROM dish_history WHERE fingerprint = ?", (fingerprint,)
                ).fetchone()
                if previous:
                    previous_system = json.loads(previous["system_nutrients"])
                    previous_confirmed = json.loads(previous["confirmed_nutrients"])
                    if previous_system == system and previous_confirmed == confirmed:
                        return self._record(previous)
                revision = int(previous["revision"]) + 1 if previous else 1
                previous_confirmed = json.loads(previous["confirmed_nutrients"]) if previous else {}
                changed_fields = [
                    field for field in NUTRIENT_FIELDS
                    if previous_confirmed.get(field) != confirmed.get(field)
                ]
                connection.execute(
                    """
                    INSERT INTO dish_history(
                        fingerprint, recipe_name, system_nutrients, confirmed_nutrients,
                        revision, confirmed_at, source, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        recipe_name = excluded.recipe_name,
                        system_nutrients = excluded.system_nutrients,
                        confirmed_nutrients = excluded.confirmed_nutrients,
                        revision = excluded.revision,
                        confirmed_at = excluded.confirmed_at,
                        source = excluded.source,
                        reason = excluded.reason
                    """,
                    (
                        fingerprint,
                        recipe.recipe_name,
                        system_json,
                        confirmed_json,
                        revision,
                        now,
                        source,
                        reason,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO dish_history_revisions(
                        fingerprint, revision, system_nutrients, confirmed_nutrients,
                        changed_fields, confirmed_at, source, reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fingerprint,
                        revision,
                        system_json,
                        confirmed_json,
                        json.dumps(changed_fields, ensure_ascii=False),
                        now,
                        source,
                        reason,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM dish_history WHERE fingerprint = ?", (fingerprint,)
                ).fetchone()
        finally:
            connection.close()
        assert row is not None
        return self._record(row)

    def backup(self, destination: str | Path) -> Path:
        destination_path = Path(destination).expanduser()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source = self._connect()
        target = sqlite3.connect(destination_path)
        try:
            source.backup(target)
        finally:
            source.close()
            target.close()
        return destination_path

    def restore(self, source: str | Path) -> None:
        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        source_connection = sqlite3.connect(source_path)
        target = self._connect()
        try:
            source_connection.backup(target)
        finally:
            source_connection.close()
            target.close()
