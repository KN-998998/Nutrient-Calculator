# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: 营养素计算工具 (Windows / macOS)
# 打包: pyinstaller 营养素计算工具.spec
# 产物: dist/营养素计算工具/ (含 exe/app, 双击即用)

a = Analysis(
    ['desktop_app/app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('data/ingredient_nutrients.csv', 'data'),
        ('desktop_app/templates/index.html', 'templates'),
    ],
    hiddenimports=[
        'openpyxl.cell._writer',
        'openpyxl.styles',
        'flask',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'matplotlib', 'numpy'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='营养素计算工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # Windows 不弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,   # macOS 用
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='营养素计算工具',
)

# macOS: 生成 .app(macOS 上执行 pyinstaller 时生效, Windows 自动忽略)
app = BUNDLE(
    coll,
    name='营养素计算工具.app',
    icon=None,
    bundle_identifier='com.tt.nutrition-calculator',
)

