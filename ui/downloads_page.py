
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import SettingsManager
from config.theme import ThemePalette, get_theme
from core.downloader import DownloadManager, open_file_in_default_player, reveal_in_explorer
from ui.icons import get_icon
from ui.widgets.custom_widgets import BatchUrlDialog, EmptyStateWidget
from ui.widgets.download_card import DownloadCard


class DownloadsPage(QWidget):

    go_home_requested = Signal()
    batch_urls_requested = Signal(list)
    toast_requested = Signal(str, str)

    def __init__(
        self,
        download_mgr: DownloadManager,
        settings: SettingsManager,
        palette: ThemePalette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dl = download_mgr
        self._settings = settings
        self._palette = palette or get_theme()
        self._cards: dict[str, DownloadCard] = {}
        self._active_filter = "all"

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 24)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel("İndirmeler")
        title.setObjectName("PageTitle")
        self.subtitle = QLabel("Aktif ve sırada bekleyen tüm medya indirmeleri")
        self.subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(self.subtitle)

        header.addLayout(title_col)
        header.addStretch()

        self.batch_btn = QPushButton("Toplu Ekle")
        self.batch_btn.setObjectName("SecondaryButton")
        self.batch_btn.setIcon(get_icon("plus", self._palette.text_primary, 14))
        self.batch_btn.setIconSize(QSize(14, 14))
        self.batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.batch_btn.clicked.connect(self._open_batch_dialog)

        self.open_dir_btn = QPushButton("Klasörü Aç")
        self.open_dir_btn.setObjectName("SecondaryButton")
        self.open_dir_btn.setIcon(get_icon("folder", self._palette.text_primary, 14))
        self.open_dir_btn.setIconSize(QSize(14, 14))
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_dir_btn.clicked.connect(lambda: reveal_in_explorer(self._settings.data.download_dir))

        self.clear_done_btn = QPushButton("Tamamlananları Temizle")
        self.clear_done_btn.setObjectName("SecondaryButton")
        self.clear_done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_done_btn.clicked.connect(self._dl.clear_completed)

        header.addWidget(self.batch_btn)
        header.addWidget(self.open_dir_btn)
        header.addWidget(self.clear_done_btn)
        root.addLayout(header)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_group = QButtonGroup(self)
        self._filter_group.setExclusive(True)

        filters = [
            ("all", "Tümü"),
            ("active", "Aktif"),
            ("paused", "Duraklatılan"),
            ("completed", "Tamamlanan"),
            ("failed", "Hatalı"),
        ]
        for key, label in filters:
            btn = QPushButton(label)
            btn.setObjectName("FilterPill")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if key == "all":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked=False, k=key: self._set_filter(k))
            self._filter_group.addButton(btn)
            filter_row.addWidget(btn)

        filter_row.addStretch()
        root.addLayout(filter_row)

        div = QFrame()
        div.setObjectName("Divider")
        root.addWidget(div)

        self.stack = QStackedWidget()

        self.empty_state = EmptyStateWidget(
            icon_name="download",
            title="Henüz indirme görevi yok",
            subtitle="Ana sayfadan bir bağlantı yapıştırarak veya toplu bağlantı ekleyerek indirmeye başlayabilirsiniz.",
            action_text="Yeni İndirme Başlat",
        )
        if self.empty_state.action_btn:
            self.empty_state.action_btn.clicked.connect(self.go_home_requested.emit)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 2, 4, 16)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch(1)
        scroll.setWidget(self.cards_host)

        self.stack.addWidget(self.empty_state)
        self.stack.addWidget(scroll)
        root.addWidget(self.stack, 1)

    def _connect_signals(self) -> None:
        self._dl.task_added.connect(self._on_task_added)
        self._dl.task_updated.connect(self._on_task_updated)
        self._dl.task_removed.connect(self._on_task_removed)

    def _on_task_added(self, task: dict[str, Any]) -> None:
        tid = task["task_id"]
        if tid in self._cards:
            self._cards[tid].update_task(task)
            self._apply_filter_visibility()
            return

        card = DownloadCard(task, palette=self._palette, parent=self.cards_host)
        card.pause_requested.connect(self._dl.pause_task)
        card.resume_requested.connect(self._dl.resume_task)
        card.cancel_requested.connect(self._dl.cancel_task)
        card.retry_requested.connect(self._dl.retry_task)
        card.play_requested.connect(self._play_file)
        card.open_folder_requested.connect(reveal_in_explorer)

        self._cards[tid] = card
        self.cards_layout.insertWidget(0, card)
        self._apply_filter_visibility()

    def _on_task_updated(self, task: dict[str, Any]) -> None:
        card = self._cards.get(task["task_id"])
        if card:
            card.update_task(task)
            self._apply_filter_visibility()

    def _on_task_removed(self, task_id: str) -> None:
        card = self._cards.pop(task_id, None)
        if card:
            self.cards_layout.removeWidget(card)
            card.deleteLater()
        self._apply_filter_visibility()

    def _play_file(self, path: str) -> None:
        if not open_file_in_default_player(path):
            self.toast_requested.emit("Dosya bulunamadı veya taşınmış.", "error")

    def _set_filter(self, key: str) -> None:
        self._active_filter = key
        self._apply_filter_visibility()

    def _matches_filter(self, status: str) -> bool:
        if self._active_filter == "all":
            return True
        if self._active_filter == "active":
            return status in ("queued", "downloading", "converting")
        return status == self._active_filter

    def _apply_filter_visibility(self) -> None:
        visible_count = 0
        for card in self._cards.values():
            vis = self._matches_filter(card.status)
            card.setVisible(vis)
            if vis:
                visible_count += 1

        self.stack.setCurrentIndex(1 if visible_count > 0 else 0)

    def _open_batch_dialog(self) -> None:
        dlg = BatchUrlDialog(self)
        if dlg.exec() and dlg.urls:
            self.batch_urls_requested.emit(dlg.urls)

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.batch_btn.setIcon(get_icon("plus", palette.text_primary, 14))
        self.open_dir_btn.setIcon(get_icon("folder", palette.text_primary, 14))
        for card in self._cards.values():
            card.set_palette_theme(palette)
