# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for StellarPulse — works on macOS, Windows and Linux.

Build from the repo root:
    pyinstaller --noconfirm packaging/stellarpulse.spec
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, REPO_ROOT)

version_ns = {}
with open(os.path.join(REPO_ROOT, "src", "version.py"), encoding="utf-8") as f:
    exec(f.read(), version_ns)
APP_VERSION = version_ns["__version__"]
APP_NAME = version_ns["APP_NAME"]

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

icon_file = None
if IS_MAC:
    icon_file = os.path.join(SPECPATH, "StellarPulse.icns")
elif IS_WIN:
    icon_file = os.path.join(SPECPATH, "StellarPulse.ico")

hiddenimports = []
if IS_MAC:
    hiddenimports += ["objc", "AppKit", "Foundation"]

a = Analysis(
    [os.path.join(REPO_ROOT, "main.py")],
    pathex=[REPO_ROOT],
    binaries=[],
    datas=[(os.path.join(REPO_ROOT, "assets"), "assets")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # PyQt5/PySide sneak in from anaconda environments and their Qt5
    # dylibs then shadow PyQt6's Qt6 at runtime ("incompatible Qt library").
    excludes=["tkinter", "PyQt5", "PySide2", "PySide6", "matplotlib", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name=f"{APP_NAME}.app",
        icon=icon_file,
        bundle_identifier="app.stellarpulse.timer",
        version=APP_VERSION,
        info_plist={
            "CFBundleDisplayName": "星际脉动",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "© StellarPulse",
        },
    )
