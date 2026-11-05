
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_bundle_root() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def get_writable_root() -> Path:
    if is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
        return base / "MediaDock"
    return Path(__file__).resolve().parent.parent


BUNDLE_ROOT: Path = get_bundle_root()
WRITABLE_ROOT: Path = get_writable_root()

ASSETS_DIR: Path = BUNDLE_ROOT / "assets"
ICONS_DIR: Path = (WRITABLE_ROOT / "assets" / "icons") if not is_frozen() else (ASSETS_DIR / "icons")
THUMBNAILS_DIR: Path = WRITABLE_ROOT / "assets" / "thumbnails"
DATA_DIR: Path = WRITABLE_ROOT / "data"
BIN_DIR: Path = DATA_DIR / "bin"
DB_PATH: Path = DATA_DIR / "mediadock.db"


def get_default_download_dir() -> Path:
    videos_dir = Path.home() / "Videos" / "MediaDock"
    return videos_dir


def ensure_app_directories() -> None:
    for folder in (DATA_DIR, BIN_DIR, THUMBNAILS_DIR, get_default_download_dir()):
        folder.mkdir(parents=True, exist_ok=True)
    if not is_frozen():
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
