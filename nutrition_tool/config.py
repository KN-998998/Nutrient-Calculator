"""Runtime paths and application defaults shared by adapters and entrypoints."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def resource_path(relative_path: str) -> Path:
    """Resolve a project resource from the source checkout used by the service."""
    return PROJECT_ROOT / relative_path


MAX_UPLOAD_BYTES = 500 * 1024 * 1024
DEFAULT_PORT = 8300
