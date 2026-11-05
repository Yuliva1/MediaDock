from pathlib import Path

ROOT = Path(SPECPATH)
ASSETS_ICONS = ROOT / "assets" / "icons"
ICO_FILE = ASSETS_ICONS / "mediadock.ico"
VERSION_FILE = ROOT / "version_info.txt"

datas = []
if ASSETS_ICONS.exists():
    datas.append((str(ASSETS_ICONS), "assets/icons"))

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtSvg",
        "yt_dlp",
        "yt_dlp_ejs",
        "PIL.Image",
        "requests",
        "curl_cffi",
        "core.updater",
        "ui.widgets.update_dialog",
        "ui.widgets.gallery_dialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.QtPdf",
        "tkinter",
        "matplotlib",
        "scipy",
        "numpy",
        "numba",
        "llvmlite",
        "onnxruntime",
        "rembg",
        "kivy",
        "pygame",
        "selenium",
        "flask",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MediaDock",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICO_FILE) if ICO_FILE.exists() else None,
    version=str(VERSION_FILE) if VERSION_FILE.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MediaDock",
)
