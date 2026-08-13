from nutrition_tool.cli import main

# WSGI 兼容入口: 供 `flask run` / 自动验证 (hermes verify) 使用。
# 桌面版双击启动仍走 desktop_app/app.py(端口 8317);此处仅让标准 WSGI 服务器能找到应用。
try:
    from desktop_app.app import app as app  # noqa: F401
except ImportError:  # 纯 CLI 环境(无 Flask)不阻塞
    app = None  # type: ignore[assignment]


if __name__ == "__main__":
    raise SystemExit(main())
