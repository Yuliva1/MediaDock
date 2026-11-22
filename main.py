
from __future__ import annotations

import ctypes
import faulthandler
import logging
import os
import sys
import time
import threading

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from config.constants import APP_NAME, APP_ORGANIZATION, APP_VERSION
from config.paths import ensure_app_directories, is_frozen
from config.settings import SettingsManager
from core import delta_update, threads
from core.database import DatabaseManager
from core.extractor import set_cookies_enabled, set_instagram_cookies_allowed
from core.ffmpeg import FFmpegManager
from core.logutil import LOG_DIR, log_event, log_exception
from core.ytdlp_updater import YtDlpAutoUpdater, activate_override
from ui.main_window import MainWindow


def _configure_windows_app_id() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MediaDock.Desktop.App.1")
        except Exception:
            pass


def _install_excepthooks() -> None:
    """Yakalanmayan hataları günlüğe yazar (console=False derlemede aksi halde iz kalmaz)."""

    def hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log_exception("ana iş parçacığı", exc_type, exc, tb)

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        log_exception(f"iş parçacığı {getattr(args.thread, 'name', '?')}", args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = hook
    threading.excepthook = thread_hook

    # Qt/C++ tarafındaki çökmeler için: Python yığınını crash.log'a yazar.
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        crash_fh = open(LOG_DIR / "crash.log", "a", encoding="utf-8")
        # Her oturumun başına sürüm/saat yazılır; çökme hangi sürümde oldu anlaşılsın.
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        crash_fh.write(f"\n--- MediaDock {APP_VERSION} oturumu {stamp} (pid {os.getpid()}) ---\n")
        crash_fh.flush()
        faulthandler.enable(crash_fh)
    except Exception:
        pass


def _cleanup_temp_thumbnails() -> None:
    # Yarım kalan küçük resim indirmeleri (tmp_*.dat) birikmesin.
    from config.paths import THUMBNAILS_DIR

    try:
        for leftover in THUMBNAILS_DIR.glob("tmp_*.dat"):
            leftover.unlink(missing_ok=True)
    except OSError:
        pass


def main() -> int:
    _configure_windows_app_id()
    ensure_app_directories()
    _install_excepthooks()
    _cleanup_temp_thumbnails()
    log_event(f"MediaDock {APP_VERSION} başlatıldı.")
    if is_frozen():
        # Önceki delta güncellemeden kalan .old dosyalarını temizle.
        delta_update.cleanup_old_files(delta_update.app_dir_for_frozen())
    # Güncellenmiş yt-dlp varsa, yt_dlp ilk kez import edilmeden önce devreye alınmalı.
    activate_override()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setApplicationVersion(APP_VERSION)

    db = DatabaseManager()
    settings = SettingsManager(db)
    def _apply_cookie_policy() -> None:
        set_cookies_enabled(settings.data.use_browser_cookies)
        set_instagram_cookies_allowed(settings.data.instagram_cookies_opt_in)

    _apply_cookie_policy()
    settings.settings_changed.connect(_apply_cookie_policy)
    ffmpeg_mgr = FFmpegManager(settings.data.ffmpeg_custom_path)

    window = MainWindow(db=db, settings=settings, ffmpeg_mgr=ffmpeg_mgr)
    window.show()

    engine_updater = YtDlpAutoUpdater(window)
    engine_updater.message.connect(window.show_toast)

    if "--self-test" in sys.argv:
        QTimer.singleShot(800, window.close)
    else:
        QTimer.singleShot(6000, engine_updater.start)

    code = app.exec()
    return _finish(code)


def _finish(code: int) -> int:
    """Arka plan işlerini kısa süre bekler; bitmeyen varsa Qt'nin abort()'una düşmeden çıkar."""
    if threads.wait_all(3000):
        return code
    log_event(f"Kapanışta {len(threads.running())} arka plan işi bitmedi; uygulama doğrudan sonlandırılıyor.")
    logging.shutdown()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    # Çalışan QThread nesneleri Python kapanışında yok edilirse Qt süreci abort() eder.
    os._exit(code)


if __name__ == "__main__":
    raise SystemExit(main())
