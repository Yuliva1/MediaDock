
from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from config.constants import APP_NAME, APP_ORGANIZATION, APP_VERSION
from config.paths import ensure_app_directories
from config.settings import SettingsManager
from core.database import DatabaseManager
from core.ffmpeg import FFmpegManager
from ui.main_window import MainWindow


def _configure_windows_app_id() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MediaDock.Desktop.App.1")
        except Exception:
            pass


def main() -> int:
    _configure_windows_app_id()
    ensure_app_directories()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setApplicationVersion(APP_VERSION)

    db = DatabaseManager()
    settings = SettingsManager(db)
    ffmpeg_mgr = FFmpegManager(settings.data.ffmpeg_custom_path)

    window = MainWindow(db=db, settings=settings, ffmpeg_mgr=ffmpeg_mgr)
    window.show()

    if "--self-test" in sys.argv:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(800, window.close)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
