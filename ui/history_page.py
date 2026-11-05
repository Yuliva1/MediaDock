
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.constants import SUPPORTED_AUDIO_EXTENSIONS, resolve_platform_info
from config.theme import ThemePalette, get_theme
from core.database import DatabaseManager
from core.downloader import open_file_in_default_player, reveal_in_explorer
from core.metadata import format_bytes
from ui.icons import get_icon, get_pixmap
from ui.widgets.custom_widgets import (
    EmptyStateWidget,
    PlatformBadge,
    RoundedThumbnail,
    format_iso_date,
)


class _HistoryRow(QFrame):

    redownload_requested = Signal(str)
    delete_entry_requested = Signal(int)
    toast_requested = Signal(str, str)

    def __init__(self, entry: dict[str, Any], palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self._palette = palette
        self.entry = entry
        self.history_id = int(entry["id"])

        file_path = str(entry.get("file_path") or "")
        file_exists = bool(file_path and Path(file_path).is_file())
        is_audio = Path(file_path).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(14)

        thumb = RoundedThumbnail(width=100, height=56, radius=5, is_audio=is_audio)
        thumb.set_palette_theme(palette)
        thumb.set_thumbnail(entry.get("thumbnail_path"), is_audio=is_audio)
        layout.addWidget(thumb)

        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 1, 0, 1)
        info_col.setSpacing(4)

        title = str(entry.get("title") or entry.get("source_url") or "Medya")
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_lbl.setToolTip(f"{title}\n{entry.get('source_url', '')}")

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)

        plat_name, plat_color = resolve_platform_info(entry.get("platform"), entry.get("source_url", ""))
        meta_row.addWidget(PlatformBadge(plat_name, plat_color))

        fmt = str(entry.get("format") or "MP4")
        qual = str(entry.get("quality") or "")
        spec = f"{fmt} · {qual}" if qual and qual != fmt else fmt
        size_txt = format_bytes(entry.get("file_size"))
        date_txt = format_iso_date(str(entry.get("downloaded_at") or ""))
        disk_state = "" if file_exists else "   ·   (Dosya taşındı/silindi)"

        meta_lbl = QLabel(f"{spec}   ·   {size_txt}   ·   {date_txt}{disk_state}")
        meta_lbl.setObjectName("SecondaryText")
        meta_row.addWidget(meta_lbl)
        meta_row.addStretch()

        info_col.addWidget(title_lbl)
        info_col.addLayout(meta_row)
        layout.addLayout(info_col, 1)

        actions = QHBoxLayout()
        actions.setSpacing(5)

        if file_exists:
            play_btn = self._icon_btn("play", "Oynat", palette.text_primary)
            play_btn.clicked.connect(lambda: open_file_in_default_player(file_path))
            actions.addWidget(play_btn)

            folder_btn = self._icon_btn("folder", "Klasörde göster", palette.text_secondary)
            folder_btn.clicked.connect(lambda: reveal_in_explorer(file_path))
            actions.addWidget(folder_btn)

        src_url = str(entry.get("source_url") or "")
        if src_url:
            copy_url_btn = self._icon_btn("link", "Kaynak bağlantıyı kopyala", palette.text_secondary)
            copy_url_btn.clicked.connect(self._copy_url)
            actions.addWidget(copy_url_btn)

            redl_btn = self._icon_btn("download", "Ana sayfada yeniden aç / indir", palette.accent)
            redl_btn.clicked.connect(lambda: self.redownload_requested.emit(src_url))
            actions.addWidget(redl_btn)

        del_btn = self._icon_btn("trash", "Geçmişten sil", palette.text_secondary, danger=True)
        del_btn.clicked.connect(lambda: self.delete_entry_requested.emit(self.history_id))
        actions.addWidget(del_btn)

        layout.addLayout(actions)

    @staticmethod
    def _icon_btn(icon_name: str, tip: str, color: str, danger: bool = False) -> QPushButton:
        b = QPushButton()
        b.setObjectName("DangerGhostButton" if danger else "GhostButton")
        b.setIcon(get_icon(icon_name, color, 15))
        b.setIconSize(QSize(15, 15))
        b.setFixedSize(28, 28)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _copy_url(self) -> None:
        QApplication.clipboard().setText(str(self.entry.get("source_url") or ""))
        self.toast_requested.emit("Video bağlantısı panoya kopyalandı.", "success")


class HistoryPage(QWidget):

    redownload_url_requested = Signal(str)
    toast_requested = Signal(str, str)

    def __init__(self, db: DatabaseManager, palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._palette = palette or get_theme()
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel("İndirme Geçmişi")
        title.setObjectName("PageTitle")
        sub = QLabel("Daha önce indirilen tüm medya kayıtları ve indirme zamanları")
        sub.setObjectName("PageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(sub)

        header.addLayout(title_col)
        header.addStretch()

        self.clear_btn = QPushButton("Geçmişi Temizle")
        self.clear_btn.setObjectName("SecondaryButton")
        self.clear_btn.setIcon(get_icon("trash", self._palette.text_primary, 14))
        self.clear_btn.setIconSize(QSize(14, 14))
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.clicked.connect(self._confirm_clear_all)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        search_frame = QFrame()
        search_frame.setObjectName("SubtlePanel")
        sf_layout = QHBoxLayout(search_frame)
        sf_layout.setContentsMargins(10, 2, 8, 2)
        sf_layout.setSpacing(6)

        self.search_icon = QLabel()
        self.search_icon.setPixmap(get_pixmap("search", self._palette.text_secondary, 15))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Geçmişte video başlığı, platform veya bağlantı ara...")
        self.search_input.setStyleSheet("border: none; background: transparent; padding: 5px 2px;")
        self.search_input.textChanged.connect(lambda _: self.refresh())

        sf_layout.addWidget(self.search_icon)
        sf_layout.addWidget(self.search_input, 1)
        root.addWidget(search_frame)

        div = QFrame()
        div.setObjectName("Divider")
        root.addWidget(div)

        self.stack = QStackedWidget()
        self.empty_widget = EmptyStateWidget(
            "history",
            "İndirme geçmişi boş",
            "Tamamlanan tüm indirmeleriniz tarih ve kaynak bilgileriyle birlikte burada saklanır.",
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 2, 4, 16)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        scroll.setWidget(self.list_host)

        self.stack.addWidget(self.empty_widget)
        self.stack.addWidget(scroll)
        root.addWidget(self.stack, 1)

    def refresh(self) -> None:
        while self.list_layout.count() > 1:
            li = self.list_layout.takeAt(0)
            if li and li.widget():
                li.widget().deleteLater()

        entries = self._db.get_history_entries(self.search_input.text().strip())
        self.clear_btn.setEnabled(len(entries) > 0)

        if not entries:
            self.stack.setCurrentIndex(0)
            return

        for entry in entries:
            row = _HistoryRow(entry, self._palette, self.list_host)
            row.redownload_requested.connect(self.redownload_url_requested.emit)
            row.delete_entry_requested.connect(self._delete_one)
            row.toast_requested.connect(self.toast_requested.emit)
            self.list_layout.insertWidget(self.list_layout.count() - 1, row)

        self.stack.setCurrentIndex(1)

    def _delete_one(self, history_id: int) -> None:
        self._db.delete_history_entry(history_id)
        self.refresh()

    def _confirm_clear_all(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Geçmişi Temizle")
        dlg.setFixedWidth(390)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 18)
        lay.setSpacing(12)

        t = QLabel("Tüm indirme geçmişi silinsin mi?")
        t.setObjectName("SectionTitle")
        s = QLabel("Bu işlem yalnızca geçmiş listesini temizler; bilgisayarınızdaki indirilen video dosyaları silinmez.")
        s.setObjectName("SecondaryText")
        s.setWordWrap(True)

        btns = QHBoxLayout()
        btns.addStretch()
        c_btn = QPushButton("Vazgeç")
        c_btn.setObjectName("SecondaryButton")
        c_btn.clicked.connect(dlg.reject)
        ok_btn = QPushButton("Temizle")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.clicked.connect(dlg.accept)
        btns.addWidget(c_btn)
        btns.addWidget(ok_btn)

        lay.addWidget(t)
        lay.addWidget(s)
        lay.addLayout(btns)

        if dlg.exec():
            self._db.clear_history()
            self.toast_requested.emit("İndirme geçmişi temizlendi.", "info")
            self.refresh()

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.search_icon.setPixmap(get_pixmap("search", palette.text_secondary, 15))
        self.clear_btn.setIcon(get_icon("trash", palette.text_primary, 14))
        self.refresh()
