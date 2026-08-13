"""WSGI 入口(供 flask run / 部署 / 自动验证使用)。

桌面版双击启动仍走 desktop_app/app.py(端口 8317,自动开浏览器);
本入口让标准 WSGI 服务器(flask run)能加载同一个 Flask 应用。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from desktop_app.app import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8317, debug=False)
