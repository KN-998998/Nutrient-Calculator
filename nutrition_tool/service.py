from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .calculator import calculate_recipe
from .models import IngredientAmount, Recipe
from .repository import NutrientRepository


CONTRACT_VERSION = "nutrition.calculation.v1"


class ContractError(ValueError):
    """Raised when an external request does not satisfy the public contract."""


def _optional_number(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field_name} must be a number") from exc


def _required_number(value: Any, field_name: str) -> float:
    number = _optional_number(value, field_name)
    if number is None:
        raise ContractError(f"{field_name} is required")
    return number


@dataclass(frozen=True)
class NutritionCalculationService:
    """Framework-independent application boundary for UI, API and batch jobs."""

    repository: NutrientRepository

    def calculate(self, request: Mapping[str, Any]) -> dict[str, Any]:
        version = request.get("contract_version", CONTRACT_VERSION)
        if version != CONTRACT_VERSION:
            raise ContractError(
                f"unsupported contract_version {version!r}; expected {CONTRACT_VERSION!r}"
            )

        recipe_data = request.get("recipe")
        if not isinstance(recipe_data, Mapping):
            raise ContractError("recipe must be an object")
        raw_ingredients = recipe_data.get("ingredients")
        if not isinstance(raw_ingredients, list) or not raw_ingredients:
            raise ContractError("recipe.ingredients must be a non-empty list")

        ingredients: list[IngredientAmount] = []
        for index, item in enumerate(raw_ingredients):
            if not isinstance(item, Mapping):
                raise ContractError(f"recipe.ingredients[{index}] must be an object")
            name = str(item.get("ingredient_name") or "").strip()
            code = str(item.get("ingredient_code") or "").strip()
            if not name and not code:
                raise ContractError(
                    f"recipe.ingredients[{index}] requires ingredient_name or ingredient_code"
                )
            ingredients.append(
                IngredientAmount(
                    ingredient_name=name,
                    ingredient_code=code,
                    grams=_required_number(item.get("grams"), f"recipe.ingredients[{index}].grams"),
                    component_name=str(item.get("component_name") or "").strip(),
                    edible_fraction=_optional_number(item.get("edible_fraction"), "edible_fraction"),
                    yield_factor=_optional_number(item.get("yield_factor"), "yield_factor"),
                    retention_factor=_optional_number(item.get("retention_factor"), "retention_factor"),
                )
            )

        recipe = Recipe(
            recipe_name=str(recipe_data.get("recipe_name") or "").strip(),
            ingredients=tuple(ingredients),
            meal_set=str(recipe_data.get("meal_set") or "").strip(),
            service_date=str(recipe_data.get("service_date") or "").strip(),
            cooked_weight_g=_optional_number(recipe_data.get("cooked_weight_g"), "cooked_weight_g"),
            source_sheet=str(recipe_data.get("source_sheet") or "").strip(),
        )
        result = calculate_recipe(recipe, self.repository)
        return {
            "contract_version": CONTRACT_VERSION,
            "result": result.to_dict(),
        }
