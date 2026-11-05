from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QThread
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.theme import ThemePalette, get_theme
from core.metadata import format_bytes
from core.updater import UpdateDownloadWorker, UpdateInfo, launch_installer_and_exit
from ui.icons import get_icon, get_pixmap
from ui.widgets.custom_widgets import SmoothProgressBar


class UpdateDialog(QDialog):

    def __init__(self, info: UpdateInfo, palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info
        self._palette = palette or get_theme()
        self._thread: QThread | None = None
        self._worker: UpdateDownloadWorker | None = None
        self._downloaded_path: str = ""

        self.setWindowTitle("MediaDock Güncellemesi")
        self.setFixedWidth(560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {self._palette.bg_app};
                color: {self._palette.text_primary};
                border: 1px solid {self._palette.border};
                border-radius: 10px;
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(16)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(12)

        logo_lbl = QLabel()
        logo_lbl.setPixmap(get_pixmap("logo", self._palette.accent, 26))
        hdr_row.addWidget(logo_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)
        title = QLabel("Yeni Bir Sürüm Mevcut!")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        sub = QLabel(f"{self.info.release_name}  ·  Yayınlanma: {self.info.published_at[:10] if self.info.published_at else 'Güncel'}")
        sub.setObjectName("SecondaryText")
        title_col.addWidget(title)
        title_col.addWidget(sub)
        hdr_row.addLayout(title_col, 1)

        root.addLayout(hdr_row)

        ver_card = QFrame()
        ver_card.setObjectName("SubtlePanel")
        vc_layout = QHBoxLayout(ver_card)
        vc_layout.setContentsMargins(14, 10, 14, 10)
        vc_layout.setSpacing(12)

        cur_box = QLabel(f"Mevcut Sürüm: v{self.info.current_version}")
        cur_box.setObjectName("MutedText")
        arr = QLabel("→")
        arr.setStyleSheet(f"color: {self._palette.accent}; font-weight: bold; font-size: 14px;")
        new_box = QLabel(f"Yeni Sürüm: v{self.info.latest_version}")
        new_box.setStyleSheet(f"color: {self._palette.accent}; font-weight: 600; font-size: 13px;")

        vc_layout.addWidget(cur_box)
        vc_layout.addWidget(arr)
        vc_layout.addWidget(new_box)
        vc_layout.addStretch()

        if self.info.asset_size > 0:
            sz_lbl = QLabel(f"Dosya Boyutu: {format_bytes(self.info.asset_size)}")
            sz_lbl.setObjectName("MutedText")
            vc_layout.addWidget(sz_lbl)

        root.addWidget(ver_card)

        cl_hdr = QLabel("Sürüm Değişiklikleri ve Yenilikler (Changelog):")
        cl_hdr.setObjectName("FieldLabel")
        root.addWidget(cl_hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(180)
        scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {self._palette.bg_surface};
                border: 1px solid {self._palette.border};
                border-radius: 6px;
            }}
            """
        )

        cl_content = QWidget()
        cl_layout = QVBoxLayout(cl_content)
        cl_layout.setContentsMargins(14, 12, 14, 12)

        notes_lbl = QLabel(self.info.release_notes)
        notes_lbl.setWordWrap(True)
        notes_lbl.setTextFormat(Qt.TextFormat.MarkdownText)
        notes_lbl.setStyleSheet(f"color: {self._palette.text_primary}; font-size: 12px; line-height: 1.4;")
        cl_layout.addWidget(notes_lbl)
        cl_layout.addStretch()

        scroll.setWidget(cl_content)
        root.addWidget(scroll)

        self.progress_panel = QFrame()
        self.progress_panel.setObjectName("SubtlePanel")
        self.progress_panel.hide()
        pp_layout = QVBoxLayout(self.progress_panel)
        pp_layout.setContentsMargins(12, 10, 12, 10)
        pp_layout.setSpacing(6)

        pp_top = QHBoxLayout()
        self.prog_status_lbl = QLabel("Güncelleme indiriliyor...")
        self.prog_status_lbl.setObjectName("SecondaryText")
        self.prog_pct_lbl = QLabel("%0")
        self.prog_pct_lbl.setStyleSheet(f"color: {self._palette.accent}; font-weight: 600; font-size: 12px;")
        pp_top.addWidget(self.prog_status_lbl, 1)
        pp_top.addWidget(self.prog_pct_lbl)
        pp_layout.addLayout(pp_top)

        self.progress_bar = SmoothProgressBar(self.progress_panel)
        self.progress_bar.setFixedHeight(6)
        pp_layout.addWidget(self.progress_bar)

        self.speed_lbl = QLabel()
        self.speed_lbl.setObjectName("MutedText")
        pp_layout.addWidget(self.speed_lbl)

        root.addWidget(self.progress_panel)

        self.err_lbl = QLabel()
        self.err_lbl.setStyleSheet(f"color: {self._palette.danger}; font-size: 12px;")
        self.err_lbl.setWordWrap(True)
        self.err_lbl.hide()
        root.addWidget(self.err_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        self.later_btn = QPushButton("Daha Sonra")
        self.later_btn.setObjectName("SecondaryButton")
        self.later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.later_btn.clicked.connect(self._on_later_clicked)
        btn_row.addWidget(self.later_btn)

        self.update_btn = QPushButton("Şimdi Güncelle ve Yeniden Başlat")
        self.update_btn.setObjectName("PrimaryButton")
        self.update_btn.setIcon(get_icon("download", "#FFFFFF", 14))
        self.update_btn.setIconSize(QSize(14, 14))
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(self._start_download)
        btn_row.addWidget(self.update_btn)

        root.addLayout(btn_row)

    def _start_download(self) -> None:
        if self._downloaded_path:
            launch_installer_and_exit(self._downloaded_path)
            return

        if not self.info.download_url:
            self.err_lbl.setText("İndirilebilir kurulum dosyası (setup.exe) bulunamadı.")
            self.err_lbl.show()
            return

        self.err_lbl.hide()
        self.later_btn.setEnabled(False)
        self.update_btn.setEnabled(False)
        self.update_btn.setText("İndiriliyor...")
        self.progress_panel.show()

        thread = QThread(self)
        worker = UpdateDownloadWorker(self.info.download_url, self.info.asset_name)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)

        def cleanup() -> None:
            worker.deleteLater()
            thread.deleteLater()
            self._thread = None
            self._worker = None

        thread.finished.connect(cleanup)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_progress(self, pct: float, dl_bytes: int, tot_bytes: int, speed: float) -> None:
        self.progress_bar.set_target_value(pct)
        self.prog_pct_lbl.setText(f"%{pct:.0f}")
        speed_txt = f"{format_bytes(speed)}/s" if speed > 0 else ""
        size_txt = f"{format_bytes(dl_bytes)} / {format_bytes(tot_bytes)}" if tot_bytes > 0 else format_bytes(dl_bytes)
        self.speed_lbl.setText(f"{size_txt}   ·   {speed_txt}")

    def _on_finished(self, downloaded_path: str) -> None:
        self._downloaded_path = downloaded_path
        self.prog_status_lbl.setText("İndirme tamamlandı! Kurulum başlatılıyor...")
        self.prog_pct_lbl.setText("%100")
        self.progress_bar.set_target_value(100.0)
        self.update_btn.setText("Kuruluma Başla")
        self.update_btn.setEnabled(True)
        self.later_btn.setEnabled(True)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(600, lambda: launch_installer_and_exit(downloaded_path))

    def _on_failed(self, error_message: str) -> None:
        self.progress_panel.hide()
        self.later_btn.setEnabled(True)
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Tekrar Dene")
        self.err_lbl.setText(f"İndirme hatası: {error_message}")
        self.err_lbl.show()

    def _on_later_clicked(self) -> None:
        if self._worker:
            self._worker.cancel()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
        self.reject()

    def closeEvent(self, event) -> None:
        self._on_later_clicked()
        super().closeEvent(event)
