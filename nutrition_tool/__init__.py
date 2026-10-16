"""香港学生餐营养素计算核心。"""

from .calculator import calculate_recipe
from .history import (
    HistoryRecord,
    SQLiteHistoryRepository,
    default_history_db_path,
    recipe_fingerprint,
)
from .models import IngredientAmount, NutrientProfile, Recipe, RecipeResult
from .service import CONTRACT_VERSION, ContractError, NutritionCalculationService

__all__ = [
    "IngredientAmount",
    "NutrientProfile",
    "Recipe",
    "RecipeResult",
    "calculate_recipe",
    "HistoryRecord",
    "SQLiteHistoryRepository",
    "default_history_db_path",
    "recipe_fingerprint",
    "CONTRACT_VERSION",
    "ContractError",
    "NutritionCalculationService",
]
