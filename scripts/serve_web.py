"""Run the Flask application as a persistent HTTP service on Windows ECS.

The desktop launcher keeps its local-browser behavior. This entry point is for
server deployment only: it does not open a browser and uses a fixed default
listener of 0.0.0.0:8300.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web_app.app import app  # noqa: E402


def server_settings(env: Mapping[str, str] | None = None) -> tuple[str, int]:
    values = os.environ if env is None else env
    host = values.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    raw_port = values.get("PORT", "8300").strip() or "8300"
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(f"PORT must be an integer: {raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"PORT must be between 1 and 65535: {port}")
    return host, port


def main() -> None:
    from waitress import serve

    host, port = server_settings()
    print(f"Nutrient calculator listening on http://{host}:{port}", flush=True)
    serve(app, host=host, port=port, threads=4, ident="nutrient-calculator")


if __name__ == "__main__":
    main()
