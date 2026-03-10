# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules("src")
hiddenimports += collect_submodules("config")

a = Analysis(
    ["onTroFinanceStarter.py"],
    pathex=[],
    binaries=[],
    datas=[
        (".env.example", "."),
        ("README.md", "."),
        ("config", "config"),
        ("data", "data"),
        ("docs", "docs"),
        ("frontend/dist", "frontend/dist"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name="onTroFinanceStarter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
