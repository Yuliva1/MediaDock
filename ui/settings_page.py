from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_AUTHOR, APP_VERSION, DEFAULT_UPDATE_REPO, VIDEO_FORMATS, VIDEO_QUALITIES
from config.paths import get_default_download_dir
from config.settings import SettingsManager
from config.theme import THEMES, ThemePalette, get_theme
from core.downloader import reveal_in_explorer
from core.ffmpeg import FFmpegManager
from core.logutil import LOG_DIR, LOG_FILE, build_report
from core.scanner import LibraryScanner, YtDlpUpdater
from core.updater import UpdateCheckWorker, UpdateInfo
from ui.icons import get_icon
from ui.widgets.custom_widgets import ToggleSwitch
from ui.widgets.update_dialog import UpdateDialog


class _SettingsCard(QFrame):

    def __init__(self, section_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(18, 16, 18, 16)
        self.vbox.setSpacing(12)

        hdr = QLabel(section_title)
        hdr.setObjectName("SectionTitle")
        self.vbox.addWidget(hdr)
        self._first_row = True

    def add_row(self, title: str, subtitle: str, right_widget: QWidget) -> None:
        if not self._first_row:
            div = QFrame()
            div.setObjectName("Divider")
            self.vbox.addWidget(div)
        self._first_row = False

        row = QHBoxLayout()
        row.setSpacing(16)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        s_lbl = QLabel(subtitle)
        s_lbl.setObjectName("MutedText")
        s_lbl.setWordWrap(True)
        texts.addWidget(t_lbl)
        texts.addWidget(s_lbl)

        row.addLayout(texts, 1)
        row.addWidget(right_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        self.vbox.addLayout(row)

    def add_custom(self, widget_or_layout: QWidget | QHBoxLayout | QVBoxLayout) -> None:
        if not self._first_row:
            div = QFrame()
            div.setObjectName("Divider")
            self.vbox.addWidget(div)
        self._first_row = False
        if isinstance(widget_or_layout, QWidget):
            self.vbox.addWidget(widget_or_layout)
        else:
            self.vbox.addLayout(widget_or_layout)


class SettingsPage(QWidget):

    dependencies_refreshed = Signal()
    toast_requested = Signal(str, str)

    def __init__(
        self,
        settings: SettingsManager,
        ffmpeg_mgr: FFmpegManager,
        scanner: LibraryScanner,
        palette: ThemePalette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._ffmpeg = ffmpeg_mgr
        self._scanner = scanner
        self._palette = palette or get_theme()
        self._updater = YtDlpUpdater(self)
        self._toggles: list[ToggleSwitch] = []
        self._check_update_thread: QThread | None = None

        self._build_ui()
        self._load_values()
        self._updater.status_ready.connect(self._on_ytdlp_status)

    def _make_toggle(self, checked: bool = False) -> ToggleSwitch:
        sw = ToggleSwitch(checked=checked, palette=self._palette)
        self._toggles.append(sw)
        return sw

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        canvas = QWidget()
        scroll.setWidget(canvas)
        c_layout = QVBoxLayout(canvas)
        c_layout.setContentsMargins(32, 26, 32, 32)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        container = QWidget()
        container.setMaximumWidth(820)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        title = QLabel("Ayarlar")
        title.setObjectName("PageTitle")
        sub = QLabel("İndirme tercihlerini, kurgu uyumluluğunu, medya motorlarını ve güncellemeleri yapılandırın")
        sub.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(sub)

        update_card = _SettingsCard("Uygulama Güncellemesi ve Sürüm Dağıtımı")

        up_col = QVBoxLayout()
        up_col.setSpacing(8)
        u_info_lbl = QLabel(f"MediaDock v{APP_VERSION}  ·  Geliştirici / Sahibi: {APP_AUTHOR}")
        u_info_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {self._palette.accent};")
        u_desc_lbl = QLabel("Uygulama her açılışta arka planda GitHub Releases üzerinden güncellemeleri otomatik denetler.")
        u_desc_lbl.setObjectName("MutedText")
        up_col.addWidget(u_info_lbl)
        up_col.addWidget(u_desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.check_app_update_btn = QPushButton("Güncellemeleri Denetle")
        self.check_app_update_btn.setObjectName("PrimaryButton")
        self.check_app_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_app_update_btn.clicked.connect(self._check_app_updates)
        btn_row.addWidget(self.check_app_update_btn)

        open_log_btn = QPushButton("Günlüğü Aç")
        open_log_btn.setObjectName("SecondaryButton")
        open_log_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_log_btn.clicked.connect(self._open_log)
        btn_row.addWidget(open_log_btn)

        copy_report_btn = QPushButton("Hata Raporunu Kopyala")
        copy_report_btn.setObjectName("SecondaryButton")
        copy_report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_report_btn.clicked.connect(self._copy_report)
        btn_row.addWidget(copy_report_btn)
        btn_row.addStretch()

        up_col.addLayout(btn_row)
        update_card.add_custom(up_col)
        root.addWidget(update_card)

        storage_card = _SettingsCard("Depolama ve Medya Kütüphanesi")

        dir_col = QVBoxLayout()
        dir_col.setSpacing(8)
        d_title = QLabel("İndirme Klasörü")
        d_title.setStyleSheet("font-size: 13px; font-weight: 500;")
        d_sub = QLabel("İndirilen tüm video, ses ve görsel dosyalarının kaydedileceği ana dizin.")
        d_sub.setObjectName("MutedText")

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.dir_input = QLineEdit()
        self.dir_input.setReadOnly(True)

        browse_dir_btn = QPushButton("Değiştir...")
        browse_dir_btn.setObjectName("SecondaryButton")
        browse_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_dir_btn.clicked.connect(self._choose_download_dir)

        open_dir_btn = QPushButton("Klasörü Aç")
        open_dir_btn.setObjectName("SecondaryButton")
        open_dir_btn.setIcon(get_icon("folder", self._palette.text_primary, 14))
        open_dir_btn.setIconSize(QSize(14, 14))
        open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_dir_btn.clicked.connect(lambda: reveal_in_explorer(self._settings.data.download_dir))
        self._open_dir_btn = open_dir_btn

        reset_dir_btn = QPushButton("Varsayılan")
        reset_dir_btn.setObjectName("GhostButton")
        reset_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_dir_btn.clicked.connect(self._reset_download_dir)

        dir_row.addWidget(self.dir_input, 1)
        dir_row.addWidget(browse_dir_btn)
        dir_row.addWidget(open_dir_btn)
        dir_row.addWidget(reset_dir_btn)

        dir_col.addWidget(d_title)
        dir_col.addWidget(d_sub)
        dir_col.addLayout(dir_row)
        storage_card.add_custom(dir_col)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(12)
        scan_texts = QVBoxLayout()
        scan_texts.setSpacing(2)
        s_hdr = QLabel("İndirilen Dosyaları Kütüphaneye Tara")
        s_hdr.setStyleSheet("font-size: 13px; font-weight: 500;")
        s_desc = QLabel("İndirme klasöründeki mevcut video ve görselleri tarayıp kütüphaneye aktarır.")
        s_desc.setObjectName("MutedText")
        scan_texts.addWidget(s_hdr)
        scan_texts.addWidget(s_desc)

        self.scan_now_btn = QPushButton("Şimdi Tara")
        self.scan_now_btn.setObjectName("SecondaryButton")
        self.scan_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_now_btn.clicked.connect(self._run_manual_scan)

        scan_row.addLayout(scan_texts, 1)
        scan_row.addWidget(self.scan_now_btn)
        storage_card.add_custom(scan_row)

        self.auto_scan_toggle = self._make_toggle(True)
        self.auto_scan_toggle.toggled.connect(lambda v: self._settings.update(auto_scan_library=v))
        storage_card.add_row(
            "Uygulama Açılışında Otomatik Tara",
            "Uygulama başlatıldığında indirme dizinindeki yeni dosyaları arka planda otomatik indeksler.",
            self.auto_scan_toggle,
        )
        root.addWidget(storage_card)

        defaults_card = _SettingsCard("Varsayılan İndirme Tercihleri")

        self.default_fmt_combo = QComboBox()
        for fmt in VIDEO_FORMATS:
            self.default_fmt_combo.addItem(fmt, fmt)
        self.default_fmt_combo.currentIndexChanged.connect(
            lambda: self._settings.update(default_format=str(self.default_fmt_combo.currentData()))
        )
        defaults_card.add_row(
            "Varsayılan Video Formatı",
            "Yeni bir video bağlantısı yapıştırıldığında ilk seçilecek kapsayıcı formatı.",
            self.default_fmt_combo,
        )

        self.default_qual_combo = QComboBox()
        for q_label, _ in VIDEO_QUALITIES:
            self.default_qual_combo.addItem(q_label, q_label)
        self.default_qual_combo.currentIndexChanged.connect(
            lambda: self._settings.update(default_quality=str(self.default_qual_combo.currentData()))
        )
        defaults_card.add_row(
            "Varsayılan Video Kalitesi",
            "Platform destekliyorsa otomatik olarak hedeflenecek video çözünürlüğü.",
            self.default_qual_combo,
        )

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 8)
        self.concurrent_spin.setValue(3)
        self.concurrent_spin.valueChanged.connect(
            lambda v: self._settings.update(max_concurrent_downloads=int(v))
        )
        defaults_card.add_row(
            "Eş Zamanlı İndirme Sayısı",
            "Aynı anda aktif olarak indirilebilecek azami medya akışı (1 - 8).",
            self.concurrent_spin,
        )

        self.premiere_default_toggle = self._make_toggle(False)
        self.premiere_default_toggle.toggled.connect(
            lambda v: self._settings.update(premiere_optimize_default=v)
        )
        defaults_card.add_row(
            "Premiere Pro Optimizasyonunu Varsayılan Aç",
            "Her indirmede otomatik olarak H.264/AAC ve YUV420p dönüştürmesini etkinleştirir.",
            self.premiere_default_toggle,
        )
        root.addWidget(defaults_card)

        system_card = _SettingsCard("Sistem ve Entegrasyon")

        self.theme_combo = QComboBox()
        for t_key, t_info in THEMES.items():
            self.theme_combo.addItem(t_info.name, t_key)
        self.theme_combo.currentIndexChanged.connect(
            lambda: self._settings.update(theme=str(self.theme_combo.currentData()))
        )
        system_card.add_row(
            "Arayüz Teması",
            "Modern koyu tonlar, Linear esintili yüksek kontrast ve mor/kırmızı vurgu varyantları.",
            self.theme_combo,
        )

        self.clipboard_toggle = self._make_toggle(True)
        self.clipboard_toggle.toggled.connect(
            lambda v: self._settings.update(clipboard_auto_detect=v)
        )
        system_card.add_row(
            "Panoyu Otomatik Algıla",
            "Kopyalanan medya ve görsel bağlantılarını tespit edip bildirim çubuğu gösterir.",
            self.clipboard_toggle,
        )

        self.notify_toggle = self._make_toggle(True)
        self.notify_toggle.toggled.connect(
            lambda v: self._settings.update(desktop_notifications=v)
        )
        system_card.add_row(
            "Masaüstü Bildirimleri",
            "İndirme tamamlandığında Windows işletim sistemi bildirim baloncuğu görüntüler.",
            self.notify_toggle,
        )

        self.open_complete_toggle = self._make_toggle(False)
        self.open_complete_toggle.toggled.connect(
            lambda v: self._settings.update(open_folder_on_complete=v)
        )
        system_card.add_row(
            "İndirme Tamamlandığında Klasörü Aç",
            "Her başarılı indirmeden sonra dosyanın bulunduğu klasörü Windows Gezgini'nde açar ve dosyayı seçer.",
            self.open_complete_toggle,
        )

        self.startup_toggle = self._make_toggle(False)
        self.startup_toggle.toggled.connect(self._on_startup_toggled)
        system_card.add_row(
            "Windows Açılışında Başlat",
            "Bilgisayar açıldığında MediaDock uygulamasını arka planda otomatik çalıştırır.",
            self.startup_toggle,
        )

        shortcut_btn = QPushButton("Masaüstü Kısayolu Oluştur")
        shortcut_btn.setObjectName("SecondaryButton")
        shortcut_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        shortcut_btn.clicked.connect(self._create_desktop_shortcut)
        system_card.add_row(
            "Masaüstü Kısayolu",
            "Masaüstüne tek tıkla MediaDock erişim simgesi ekler.",
            shortcut_btn,
        )
        root.addWidget(system_card)

        engine_card = _SettingsCard("İndirme Motorları ve Bağımlılıklar")

        ff_block = QVBoxLayout()
        ff_block.setSpacing(6)
        ff_hdr = QLabel("FFmpeg & FFprobe Durumu")
        ff_hdr.setStyleSheet("font-size: 13px; font-weight: 500;")
        self.ff_status_lbl = QLabel()
        self.ff_status_lbl.setObjectName("MutedText")
        self.ff_status_lbl.setWordWrap(True)
        ff_block.addWidget(ff_hdr)
        ff_block.addWidget(self.ff_status_lbl)

        ff_row = QHBoxLayout()
        ff_row.setSpacing(8)
        self.ffmpeg_input = QLineEdit()
        self.ffmpeg_input.setPlaceholderText("Özel ffmpeg.exe yolu (Boş bırakılırsa gömülü/PATH kullanılır)")

        choose_ff_btn = QPushButton("Gözat...")
        choose_ff_btn.setObjectName("SecondaryButton")
        choose_ff_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        choose_ff_btn.clicked.connect(self._choose_ffmpeg_path)

        apply_ff_btn = QPushButton("Uygula")
        apply_ff_btn.setObjectName("SecondaryButton")
        apply_ff_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_ff_btn.clicked.connect(self._apply_ffmpeg_path)

        clear_ff_btn = QPushButton("Sıfırla")
        clear_ff_btn.setObjectName("GhostButton")
        clear_ff_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_ff_btn.clicked.connect(self._clear_custom_ffmpeg)

        ff_row.addWidget(self.ffmpeg_input, 1)
        ff_row.addWidget(choose_ff_btn)
        ff_row.addWidget(apply_ff_btn)
        ff_row.addWidget(clear_ff_btn)
        ff_block.addLayout(ff_row)
        engine_card.add_custom(ff_block)

        yt_block = QVBoxLayout()
        yt_block.setSpacing(6)
        yt_top = QHBoxLayout()
        yt_top.setSpacing(12)
        yt_texts = QVBoxLayout()
        yt_texts.setSpacing(2)
        yt_hdr = QLabel("yt-dlp İndirme Motoru")
        yt_hdr.setStyleSheet("font-size: 13px; font-weight: 500;")
        self.yt_desc_lbl = QLabel()
        self.yt_desc_lbl.setObjectName("MutedText")
        self.yt_desc_lbl.setWordWrap(True)
        yt_texts.addWidget(yt_hdr)
        yt_texts.addWidget(self.yt_desc_lbl)
        yt_top.addLayout(yt_texts, 1)

        yt_ctrl = QHBoxLayout()
        yt_ctrl.setSpacing(8)
        self.check_yt_btn = QPushButton("Kontrol Et")
        self.check_yt_btn.setObjectName("SecondaryButton")
        self.check_yt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_yt_btn.clicked.connect(self._check_ytdlp)

        self.upgrade_yt_btn = QPushButton("Güncelle")
        self.upgrade_yt_btn.setObjectName("PrimaryButton")
        self.upgrade_yt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.upgrade_yt_btn.clicked.connect(self._upgrade_ytdlp)

        yt_ctrl.addWidget(self.check_yt_btn)
        yt_ctrl.addWidget(self.upgrade_yt_btn)
        yt_top.addLayout(yt_ctrl)
        yt_block.addLayout(yt_top)

        engine_card.add_custom(yt_block)

        self.cookies_toggle = self._make_toggle(False)
        self.cookies_toggle.toggled.connect(
            lambda v: self._settings.update(use_browser_cookies=v)
        )
        engine_card.add_row(
            "Tarayıcı Çerezlerini Kullan",
            "Giriş gerektiren sitelerde tarayıcınızdaki oturumu denemeye izin verir. "
            "Varsayılan olarak kapalıdır. Instagram için bu özellik hesap güvenliği nedeniyle her zaman devre dışıdır.",
            self.cookies_toggle,
        )
        root.addWidget(engine_card)

        c_layout.addWidget(container)

    def _load_values(self) -> None:
        d = self._settings.data
        self.dir_input.setText(d.download_dir)
        self.auto_scan_toggle.setChecked(d.auto_scan_library, emit_signal=False)

        self.default_fmt_combo.blockSignals(True)
        idx_f = self.default_fmt_combo.findData(d.default_format)
        if idx_f >= 0:
            self.default_fmt_combo.setCurrentIndex(idx_f)
        self.default_fmt_combo.blockSignals(False)

        self.default_qual_combo.blockSignals(True)
        idx_q = self.default_qual_combo.findData(d.default_quality)
        if idx_q >= 0:
            self.default_qual_combo.setCurrentIndex(idx_q)
        self.default_qual_combo.blockSignals(False)

        self.concurrent_spin.blockSignals(True)
        self.concurrent_spin.setValue(int(d.max_concurrent_downloads))
        self.concurrent_spin.blockSignals(False)

        self.premiere_default_toggle.setChecked(d.premiere_optimize_default, emit_signal=False)

        self.theme_combo.blockSignals(True)
        idx_t = self.theme_combo.findData(d.theme)
        if idx_t >= 0:
            self.theme_combo.setCurrentIndex(idx_t)
        self.theme_combo.blockSignals(False)

        self.clipboard_toggle.setChecked(d.clipboard_auto_detect, emit_signal=False)
        self.notify_toggle.setChecked(d.desktop_notifications, emit_signal=False)
        self.open_complete_toggle.setChecked(d.open_folder_on_complete, emit_signal=False)
        self.startup_toggle.setChecked(d.launch_on_startup, emit_signal=False)
        self.cookies_toggle.setChecked(d.use_browser_cookies, emit_signal=False)

        self.ffmpeg_input.setText(d.ffmpeg_custom_path)
        self.refresh_dependency_labels()

    def refresh_dependency_labels(self) -> None:
        dep = self._ffmpeg.check_dependencies()
        if dep.ffmpeg_ok:
            self.ff_status_lbl.setText(
                f"Durum: Hazır ({dep.ffmpeg_version})  ·  Konum: {dep.ffmpeg_path}"
            )
        else:
            self.ff_status_lbl.setText("Durum: FFmpeg bulunamadı. Lütfen ffmpeg.exe dosyasını seçin.")
        self.yt_desc_lbl.setText(f"Kurulu sürüm: yt-dlp {dep.ytdlp_version}")

    def _choose_download_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "İndirme Klasörü Seç",
            self._settings.data.download_dir,
        )
        if chosen:
            norm = str(Path(chosen).resolve())
            self.dir_input.setText(norm)
            self._settings.update(download_dir=norm)
            self.toast_requested.emit("İndirme klasörü güncellendi.", "success")

    def _reset_download_dir(self) -> None:
        default_dir = str(get_default_download_dir().resolve())
        self.dir_input.setText(default_dir)
        self._settings.update(download_dir=default_dir)
        self.toast_requested.emit("Varsayılan klasöre (Videos/MediaDock) dönüldü.", "info")

    def _save_update_repo(self) -> None:
        repo = self.repo_input.text().strip()
        if not repo:
            repo = DEFAULT_UPDATE_REPO
            self.repo_input.setText(repo)
        self._settings.update(update_repo=repo)
        self.toast_requested.emit("Güncelleme deposu kaydedildi.", "success")

    def _open_log(self) -> None:
        target = LOG_FILE if LOG_FILE.exists() else LOG_DIR
        if not reveal_in_explorer(str(target)):
            self.toast_requested.emit("Günlük dosyası henüz oluşmadı.", "info")

    def _copy_report(self) -> None:
        QGuiApplication.clipboard().setText(build_report())
        self.toast_requested.emit("Hata raporu panoya kopyalandı. Destek için yapıştırabilirsiniz.", "success")

    def _check_app_updates(self) -> None:
        self.check_app_update_btn.setEnabled(False)
        self.check_app_update_btn.setText("Denetleniyor...")

        repo = self._settings.data.update_repo or DEFAULT_UPDATE_REPO

        thread = QThread(self)
        worker = UpdateCheckWorker(repo, APP_VERSION)
        worker.moveToThread(thread)

        def on_checked(info: UpdateInfo) -> None:
            self.check_app_update_btn.setEnabled(True)
            self.check_app_update_btn.setText("Güncellemeleri Denetle")
            if info.has_update:
                QTimer.singleShot(150, lambda: self._show_update_dialog(info))
            else:
                self.toast_requested.emit(
                    f"MediaDock güncel (v{info.current_version}). En yeni sürümü kullanıyorsunuz.",
                    "info",
                )

        def on_failed(err_msg: str) -> None:
            self.check_app_update_btn.setEnabled(True)
            self.check_app_update_btn.setText("Güncellemeleri Denetle")
            self.toast_requested.emit(f"Güncelleme denetimi başarısız: {err_msg[:60]}", "error")

        def cleanup() -> None:
            worker.deleteLater()
            thread.deleteLater()
            self._check_update_thread = None

        thread.started.connect(worker.run)
        worker.finished.connect(on_checked)
        worker.failed.connect(on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(cleanup)
        thread.start()

    def _show_update_dialog(self, info: UpdateInfo) -> None:
        dlg = UpdateDialog(info, self._palette, self.window())
        dlg.exec()

    def _run_manual_scan(self) -> None:
        self.scan_now_btn.setEnabled(False)
        self.scan_now_btn.setText("Taranıyor...")
        self._scanner.scan(self._settings.data.download_dir)

    def notify_scan_finished(self) -> None:
        self.scan_now_btn.setEnabled(True)
        self.scan_now_btn.setText("Şimdi Tara")

    def _on_startup_toggled(self, enabled: bool) -> None:
        self._settings.update(launch_on_startup=enabled)
        self.toast_requested.emit(
            "Windows başlangıcında çalıştırma etkinleştirildi."
            if enabled
            else "Windows başlangıcında çalıştırma kapatıldı.",
            "info",
        )

    def _create_desktop_shortcut(self) -> None:
        import subprocess
        import sys
        from config.paths import WRITABLE_ROOT, is_frozen

        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            self.toast_requested.emit("Masaüstü dizini bulunamadı.", "error")
            return

        exe_candidates = [
            Path(sys.executable).resolve() if is_frozen() else Path(""),
            WRITABLE_ROOT / "MediaDock.exe",
            WRITABLE_ROOT / "dist" / "MediaDock" / "MediaDock.exe",
            WRITABLE_ROOT / "dist" / "MediaDock.exe",
        ]
        target_exe = next((p for p in exe_candidates if p and p.is_file()), None)
        lnk_path = desktop / "MediaDock.lnk"
        ico_path = WRITABLE_ROOT / "assets" / "icons" / "mediadock.ico"

        if target_exe:
            target_str = str(target_exe)
            args_str = ""
            workdir_str = str(target_exe.parent)
        else:
            pyw = Path(sys.executable).resolve().with_name("pythonw.exe")
            target_str = str(pyw if pyw.exists() else Path(sys.executable).resolve())
            main_py = Path(__file__).resolve().parent.parent / "main.py"
            args_str = f'"{main_py}"'
            workdir_str = str(main_py.parent)

        icon_str = str(ico_path) if ico_path.is_file() else target_str
        ps_script = (
            "$ws = New-Object -ComObject WScript.Shell; "
            f'$s = $ws.CreateShortcut("{lnk_path}"); '
            f'$s.TargetPath = "{target_str}"; '
            f"$s.Arguments = '{args_str}'; "
            f'$s.WorkingDirectory = "{workdir_str}"; '
            f'$s.IconLocation = "{icon_str}"; '
            "$s.Save()"
        )
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True, capture_output=True)
            self.toast_requested.emit("Masaüstüne MediaDock kısayolu oluşturuldu.", "success")
        except Exception as exc:
            self.toast_requested.emit(f"Kısayol oluşturulamadı: {exc}", "error")

    def _choose_ffmpeg_path(self) -> None:
        file_filter = "FFmpeg Yürütülebilir (ffmpeg.exe);;Tüm Dosyalar (*)"
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "FFmpeg Konumunu Seçin",
            self.ffmpeg_input.text() or str(Path.home()),
            file_filter,
        )
        if chosen:
            self.ffmpeg_input.setText(str(Path(chosen).resolve()))
            self._apply_ffmpeg_path()

    def _apply_ffmpeg_path(self) -> None:
        custom = self.ffmpeg_input.text().strip()
        self._settings.update(ffmpeg_custom_path=custom)
        self._ffmpeg.refresh(custom)
        self.refresh_dependency_labels()
        self.dependencies_refreshed.emit()

        if self._ffmpeg.is_available:
            self.toast_requested.emit(f"FFmpeg doğrulandı ({self._ffmpeg.ffmpeg_version}).", "success")
        else:
            self.toast_requested.emit("Belirtilen konumda geçerli bir FFmpeg bulunamadı.", "error")

    def _clear_custom_ffmpeg(self) -> None:
        self.ffmpeg_input.clear()
        self._apply_ffmpeg_path()

    def _check_ytdlp(self) -> None:
        self.check_yt_btn.setEnabled(False)
        self.yt_desc_lbl.setText("PyPI üzerinden son sürüm kontrol ediliyor...")
        self._updater.check_or_upgrade(do_upgrade=False)

    def _upgrade_ytdlp(self) -> None:
        self.check_yt_btn.setEnabled(False)
        self.upgrade_yt_btn.setEnabled(False)
        self.yt_desc_lbl.setText("yt-dlp güncelleniyor, lütfen bekleyin...")
        self._updater.check_or_upgrade(do_upgrade=True)

    def _on_ytdlp_status(self, action_positive: bool, version: str, message: str) -> None:
        self.check_yt_btn.setEnabled(True)
        self.upgrade_yt_btn.setEnabled(True)
        self.yt_desc_lbl.setText(message)
        self.dependencies_refreshed.emit()
        self.toast_requested.emit(message, "success" if action_positive else "info")

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self._open_dir_btn.setIcon(get_icon("folder", palette.text_primary, 14))
        for sw in self._toggles:
            sw.set_palette_theme(palette)
