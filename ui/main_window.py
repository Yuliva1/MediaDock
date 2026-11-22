from __future__ import annotations

import ctypes
import sys

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QThread, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME, APP_SUBTITLE, APP_VERSION, DEFAULT_UPDATE_REPO
from config.settings import SettingsManager
from config.theme import ThemePalette, build_stylesheet, get_theme
from core import threads
from core.database import DatabaseManager
from core.downloader import DownloadManager, DownloadOptions, reveal_in_explorer
from core.ffmpeg import FFmpegManager
from core.metadata import MetadataController, VideoMetadata, extract_urls_from_text
from core.scanner import LibraryScanner
from core.updater import UpdateCheckWorker, UpdateInfo
from ui.downloads_page import DownloadsPage
from ui.favorites_page import FavoritesPage
from ui.history_page import HistoryPage
from ui.home_page import HomePage
from ui.icons import export_svg_assets, get_icon, get_pixmap
from ui.library_page import LibraryPage
from ui.settings_page import SettingsPage
from ui.sidebar import Sidebar
from ui.widgets.custom_widgets import ToastOverlay
from ui.widgets.update_dialog import UpdateDialog


def apply_windows_dark_frame(hwnd: int, hex_caption_bg: str = "#171719") -> None:
    if sys.platform != "win32":
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        dark_mode = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))

        clean = hex_caption_bg.lstrip("#")
        if len(clean) == 6:
            r, g, b = int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)
            colorref = ctypes.c_int((b << 16) | (g << 8) | r)
            dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 35, ctypes.byref(colorref), ctypes.sizeof(colorref))
    except Exception:
        pass


class MainWindow(QMainWindow):

    def __init__(
        self,
        db: DatabaseManager,
        settings: SettingsManager,
        ffmpeg_mgr: FFmpegManager,
    ) -> None:
        super().__init__()
        self.db = db
        self.settings = settings
        self.ffmpeg_mgr = ffmpeg_mgr
        self.palette: ThemePalette = get_theme(self.settings.data.theme)
        self._chevron_path = str(export_svg_assets(self.palette.text_primary))

        self.setWindowTitle(f"{APP_NAME} – {APP_SUBTITLE}")
        self.setMinimumSize(1040, 680)
        self.resize(1220, 780)
        self.setAcceptDrops(True)
        self.setWindowIcon(get_icon("logo", self.palette.accent, 32))

        self.metadata_ctrl = MetadataController(self.ffmpeg_mgr.get_ytdlp_ffmpeg_location, self)
        self.download_mgr = DownloadManager(self.db, self.settings, self.ffmpeg_mgr, self)
        self.scanner = LibraryScanner(self.db, self.ffmpeg_mgr, self)

        self._build_ui()
        self._setup_tray_notifications()
        self._apply_theme(self.palette.key)
        self._connect_signals()

        QTimer.singleShot(150, self._startup_sequence)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("MainCentralWidget")
        self.setCentralWidget(central)

        main_row = QHBoxLayout(central)
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)

        self.sidebar = Sidebar(self.palette, central)
        main_row.addWidget(self.sidebar)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(0)

        self.dep_banner = QFrame()
        self.dep_banner.setObjectName("BannerCard")
        self.dep_banner.hide()
        db_row = QHBoxLayout(self.dep_banner)
        db_row.setContentsMargins(18, 9, 18, 9)
        db_row.setSpacing(10)

        self.dep_icon = QLabel()
        self.dep_icon.setPixmap(get_pixmap("alert", self.palette.warning, 16))
        self.dep_msg_lbl = QLabel()
        self.dep_msg_lbl.setStyleSheet("font-size: 12px;")
        self.dep_msg_lbl.setWordWrap(True)

        dep_fix_btn = QPushButton("Ayarları Aç")
        dep_fix_btn.setObjectName("SecondaryButton")
        dep_fix_btn.clicked.connect(lambda: self.sidebar.select_page("settings"))

        db_row.addWidget(self.dep_icon)
        db_row.addWidget(self.dep_msg_lbl, 1)
        db_row.addWidget(dep_fix_btn)
        right_col.addWidget(self.dep_banner)

        self.stack = QStackedWidget()
        self.home_page = HomePage(self.metadata_ctrl, self.settings, self.palette, self)
        self.downloads_page = DownloadsPage(self.download_mgr, self.settings, self.palette, self)
        self.library_page = LibraryPage(self.db, self.settings, self.scanner, self.palette, False, self)
        self.favorites_page = FavoritesPage(self.db, self.settings, self.palette, self)
        self.history_page = HistoryPage(self.db, self.palette, self)
        self.settings_page = SettingsPage(self.settings, self.ffmpeg_mgr, self.scanner, self.palette, self)

        self._page_keys = ["home", "downloads", "library", "favorites", "history", "settings"]
        for page in (
            self.home_page,
            self.downloads_page,
            self.library_page,
            self.favorites_page,
            self.history_page,
            self.settings_page,
        ):
            self.stack.addWidget(page)

        right_col.addWidget(self.stack, 1)
        main_row.addLayout(right_col, 1)

        self.toast = ToastOverlay(central)

        self._fade_anim: QPropertyAnimation | None = None

    def _setup_tray_notifications(self) -> None:
        self.tray_icon: QSystemTrayIcon | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(get_icon("logo", self.palette.accent, 32), self)
            self.tray_icon.setToolTip(APP_NAME)
            menu = QMenu(self)
            menu.addAction("MediaDock'u Aç", self._restore_from_tray)
            menu.addSeparator()
            menu.addAction("Çıkış", self._quit_from_tray)
            self.tray_icon.setContextMenu(menu)
            self.tray_icon.activated.connect(self._on_tray_activated)
            self.tray_icon.show()
        self._tray_hint_shown = False

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setProperty("mediadock_force_quit", True)
        self.close()
        if app is not None:
            app.quit()

    def _connect_signals(self) -> None:
        self.sidebar.page_selected.connect(self._switch_page)
        self.settings.theme_changed.connect(self._apply_theme)

        self.home_page.download_requested.connect(self._on_single_download_requested)
        self.home_page.gallery_download_requested.connect(self._on_gallery_download_requested)
        self.home_page.batch_urls_requested.connect(self._on_batch_urls_requested)
        self.downloads_page.batch_urls_requested.connect(self._on_batch_urls_requested)
        self.downloads_page.go_home_requested.connect(lambda: self.sidebar.select_page("home"))

        self.library_page.library_changed.connect(self._on_library_modified)
        self.favorites_page.library_changed.connect(self._on_library_modified)

        self.history_page.redownload_url_requested.connect(self._on_redownload_from_history)

        self.download_mgr.counts_changed.connect(lambda active, total: self._refresh_sidebar_badges())
        self.download_mgr.task_completed.connect(self._on_download_completed)
        self.download_mgr.task_failed.connect(self._on_download_failed)

        self.scanner.scan_completed.connect(self._on_scan_completed)
        self.scanner.scan_failed.connect(lambda err: self._on_scan_failed(err))

        self.settings_page.dependencies_refreshed.connect(self._run_dependency_check)

        for pg in (
            self.downloads_page,
            self.library_page,
            self.favorites_page,
            self.history_page,
            self.settings_page,
        ):
            pg.toast_requested.connect(self.show_toast)

    def _startup_sequence(self) -> None:
        apply_windows_dark_frame(int(self.winId()), self.palette.bg_sidebar)
        self._run_dependency_check()
        self.download_mgr.restore_persisted_tasks()
        self._refresh_sidebar_badges()

        if self.settings.data.auto_scan_library:
            self.scanner.scan(self.settings.data.download_dir)

        if self.settings.data.auto_check_updates and "--self-test" not in sys.argv:
            QTimer.singleShot(2500, self._check_updates_background)

    def _check_updates_background(self) -> None:
        repo = self.settings.data.update_repo or DEFAULT_UPDATE_REPO
        thread = threads.track(QThread(self))
        worker = UpdateCheckWorker(repo, APP_VERSION)
        worker.moveToThread(thread)
        self._bg_update_thread = thread
        self._bg_update_worker = worker

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_background_update_checked)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._cleanup_background_update)
        thread.start()

    def _on_background_update_checked(self, info: UpdateInfo) -> None:
        if not info.has_update:
            return
        if info.latest_version and info.latest_version == self.settings.data.skipped_update_version:
            # Kullanıcı bu sürümü atlamayı seçti; Ayarlar'dan elle denetlenebilir.
            return
        self.show_toast(f"Yeni MediaDock sürümü mevcut: v{info.latest_version}", "info")
        QTimer.singleShot(250, lambda: self._show_update_dialog(info, allow_skip=True))

    def _cleanup_background_update(self) -> None:
        worker = getattr(self, "_bg_update_worker", None)
        thread = getattr(self, "_bg_update_thread", None)
        self._bg_update_worker = None
        self._bg_update_thread = None
        if worker is not None:
            worker.deleteLater()
        if thread is not None:
            thread.deleteLater()

    def _show_update_dialog(self, info: UpdateInfo, allow_skip: bool = False) -> None:
        if getattr(self, "_update_dialog_open", False):
            return
        self._update_dialog_open = True
        try:
            dlg = UpdateDialog(info, self.palette, self, allow_skip=allow_skip)
            dlg.skip_version_requested.connect(self._on_skip_version)
            dlg.exec()
        finally:
            self._update_dialog_open = False

    def _on_skip_version(self, version: str) -> None:
        self.settings.update(skipped_update_version=version)
        self.show_toast(f"v{version} atlandı. Ayarlar'dan istediğiniz zaman güncelleyebilirsiniz.", "info")

    def _run_dependency_check(self) -> None:
        status = self.ffmpeg_mgr.check_dependencies()
        self.sidebar.update_engine_status(status)

        if not status.ytdlp_ok or not status.ffmpeg_ok:
            self.dep_msg_lbl.setText(status.message)
            self.dep_banner.show()
            self.show_toast("Eksik bağımlılık algılandı. Lütfen Ayarlar sayfasını kontrol edin.", "warning")
        else:
            self.dep_banner.hide()

    def _switch_page(self, key: str) -> None:
        if key not in self._page_keys:
            return
        idx = self._page_keys.index(key)
        if self.stack.currentIndex() == idx:
            return

        if key == "library":
            self.library_page.refresh()
        elif key == "favorites":
            self.favorites_page.refresh()
        elif key == "history":
            self.history_page.refresh()
        elif key == "settings":
            self.settings_page.refresh_dependency_labels()

        self.stack.setCurrentIndex(idx)
        target_widget = self.stack.currentWidget()
        if target_widget:
            effect = QGraphicsOpacityEffect(target_widget)
            target_widget.setGraphicsEffect(effect)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(85)
            anim.setStartValue(0.72)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.finished.connect(lambda w=target_widget: w.setGraphicsEffect(None))
            self._fade_anim = anim
            anim.start()

    def _on_single_download_requested(self, meta: VideoMetadata, options: DownloadOptions) -> None:
        self.download_mgr.enqueue_from_metadata(meta, options)
        self.home_page.reset()
        msg = "Görsel indirme sırasına eklendi." if meta.media_type == "image" else "İndirme kuyruğa eklendi."
        self.show_toast(msg, "success")
        self.sidebar.select_page("downloads")

    def _on_gallery_download_requested(self, items: list, image_format: str, platform: str = "") -> None:
        added = self.download_mgr.enqueue_gallery_items(items, image_format, platform=platform)
        if added:
            self.show_toast(f"{len(added)} medya indirme sırasına eklendi.", "success")
            self.sidebar.select_page("downloads")

    def _on_batch_urls_requested(self, urls: list[str]) -> None:
        added = self.download_mgr.enqueue_urls(urls)
        if added:
            self.show_toast(f"{len(added)} bağlantı indirme sırasına eklendi.", "success")
            self.sidebar.select_page("downloads")

    def _on_redownload_from_history(self, url: str) -> None:
        self.sidebar.select_page("home")
        self.home_page.load_url(url, auto=False)

    def _on_download_completed(self, task: dict, media_id: int) -> None:
        title = str(task.get("title") or "Medya")
        self.library_page.refresh()
        self.favorites_page.refresh()
        self.history_page.refresh()
        self._refresh_sidebar_badges()

        self.show_toast(f"Tamamlandı: {title[:48]}", "success")

        if self.settings.data.desktop_notifications and self.tray_icon:
            self.tray_icon.showMessage(
                "İndirme Tamamlandı – MediaDock",
                title,
                QSystemTrayIcon.MessageIcon.Information,
                4000,
            )

        if self.settings.data.open_folder_on_complete and task.get("final_path"):
            reveal_in_explorer(str(task["final_path"]))

    def _on_download_failed(self, task: dict, error_message: str) -> None:
        self.show_toast(f"İndirme hatası: {error_message[:65]}", "error")

    def _on_library_modified(self) -> None:
        self.library_page.refresh()
        self.favorites_page.refresh()
        self._refresh_sidebar_badges()

    def _on_scan_completed(self, added_count: int) -> None:
        self.settings_page.notify_scan_finished()
        if added_count > 0:
            self.library_page.refresh()
            self._refresh_sidebar_badges()
            self.show_toast(f"{added_count} yeni medya dosyası kütüphaneye eklendi.", "success")

    def _on_scan_failed(self, err: str) -> None:
        self.settings_page.notify_scan_finished()
        self.show_toast(f"Klasör tarama hatası: {err}", "error")

    def _refresh_sidebar_badges(self) -> None:
        active_dl = self.download_mgr.get_active_count()
        total_media, total_favs = self.db.get_media_counts()
        self.sidebar.update_badges(active_dl, total_media, total_favs)

    def _apply_theme(self, theme_key: str) -> None:
        self.palette = get_theme(theme_key)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(build_stylesheet(self.palette, self._chevron_path))

        self.setWindowIcon(get_icon("logo", self.palette.accent, 32))
        if self.tray_icon:
            self.tray_icon.setIcon(get_icon("logo", self.palette.accent, 32))

        apply_windows_dark_frame(int(self.winId()), self.palette.bg_sidebar)

        self.sidebar.set_palette_theme(self.palette)
        self.home_page.set_palette_theme(self.palette)
        self.downloads_page.set_palette_theme(self.palette)
        self.library_page.set_palette_theme(self.palette)
        self.favorites_page.set_palette_theme(self.palette)
        self.history_page.set_palette_theme(self.palette)
        self.settings_page.set_palette_theme(self.palette)
        self._run_dependency_check()

    def show_toast(self, message: str, kind: str = "info") -> None:
        self.toast.show_toast(message, kind=kind, palette=self.palette)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.toast.reposition()

    def dragEnterEvent(self, event) -> None:
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        raw = ""
        if md.hasUrls():
            raw = "\n".join(u.toString() for u in md.urls() if u.isValid())
        elif md.hasText():
            raw = md.text()
        urls = extract_urls_from_text(raw)
        if len(urls) > 1:
            self._on_batch_urls_requested(urls)
        elif len(urls) == 1:
            self.sidebar.select_page("home")
            self.home_page.load_url(urls[0])
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        force = bool(app.property("mediadock_force_quit")) if app is not None else True
        if self.settings.data.close_to_tray and self.tray_icon is not None and not force:
            # Pencere gizlenir, indirmeler arka planda sürer.
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray_icon.showMessage(
                    APP_NAME,
                    "MediaDock arka planda çalışmaya devam ediyor. Kapatmak için simgeye sağ tıklayıp Çıkış'ı seçin.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            return
        self.download_mgr.shutdown()
        if self.tray_icon:
            self.tray_icon.hide()
        self.db.close()
        super().closeEvent(event)
