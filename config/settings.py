from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QObject, Signal

from config.constants import DEFAULT_UPDATE_REPO, DEFAULT_VIDEO_FORMAT, DEFAULT_VIDEO_QUALITY
from config.paths import get_default_download_dir, is_frozen
from config.theme import DEFAULT_THEME_KEY

if TYPE_CHECKING:
    from core.database import DatabaseManager

RUN_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "MediaDock"


@dataclass
class AppSettingsData:
    download_dir: str = ""
    default_format: str = DEFAULT_VIDEO_FORMAT
    default_quality: str = DEFAULT_VIDEO_QUALITY
    max_concurrent_downloads: int = 3
    premiere_optimize_default: bool = False
    launch_on_startup: bool = False
    theme: str = DEFAULT_THEME_KEY
    ffmpeg_custom_path: str = ""
    auto_scan_library: bool = True
    clipboard_auto_detect: bool = True
    desktop_notifications: bool = True
    open_folder_on_complete: bool = False
    auto_check_updates: bool = True
    update_repo: str = DEFAULT_UPDATE_REPO

    def __post_init__(self) -> None:
        if not self.download_dir:
            self.download_dir = str(get_default_download_dir())


class SettingsManager(QObject):

    settings_changed = Signal()
    theme_changed = Signal(str)

    def __init__(self, db: DatabaseManager) -> None:
        super().__init__()
        self._db = db
        self.data = AppSettingsData()
        self.load()

    def load(self) -> None:
        stored = self._db.get_all_settings()
        defaults = asdict(AppSettingsData())

        merged: dict[str, Any] = {}
        for key, default_val in defaults.items():
            if key not in stored:
                merged[key] = default_val
                continue
            raw_val = stored[key]
            if isinstance(default_val, bool):
                merged[key] = str(raw_val).lower() in ("1", "true", "yes")
            elif isinstance(default_val, int):
                try:
                    merged[key] = int(raw_val)
                except (TypeError, ValueError):
                    merged[key] = default_val
            else:
                merged[key] = str(raw_val)

        if sys.platform == "win32":
            reg_state = is_startup_enabled()
            if "launch_on_startup" not in stored:
                merged["launch_on_startup"] = reg_state

        self.data = AppSettingsData(**merged)
        try:
            Path(self.data.download_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            fallback = get_default_download_dir()
            fallback.mkdir(parents=True, exist_ok=True)
            self.data.download_dir = str(fallback)

    def save(self) -> None:
        payload = {k: str(v) for k, v in asdict(self.data).items()}
        self._db.set_settings_bulk(payload)
        try:
            Path(self.data.download_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self.settings_changed.emit()

    def update(self, **kwargs: Any) -> None:
        old_theme = self.data.theme
        for key, value in kwargs.items():
            if hasattr(self.data, key):
                setattr(self.data, key, value)

        if "launch_on_startup" in kwargs and sys.platform == "win32":
            set_startup_enabled(bool(self.data.launch_on_startup))

        self.save()
        if self.data.theme != old_theme:
            self.theme_changed.emit(self.data.theme)


def _build_startup_command() -> str:
    if is_frozen():
        return f'"{Path(sys.executable).resolve()}"'
    main_script = Path(__file__).resolve().parent.parent / "main.py"
    python_exe = Path(sys.executable).resolve()
    pythonw_exe = python_exe.with_name("pythonw.exe")
    runner = pythonw_exe if pythonw_exe.exists() else python_exe
    return f'"{runner}" "{main_script}"'


def is_startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REGISTRY_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return bool(val)
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, _build_startup_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
