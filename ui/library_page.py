
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import SettingsManager
from config.theme import ThemePalette, get_theme
from core.database import DatabaseManager
from core.downloader import open_file_in_default_player, reveal_in_explorer
from core.scanner import LibraryScanner
from ui.icons import get_icon, get_pixmap
from ui.widgets.custom_widgets import DeleteMediaDialog, EmptyStateWidget
from ui.widgets.flow_layout import FlowLayout
from ui.widgets.media_card import MediaGridCard, MediaListRow


class LibraryPage(QWidget):

    library_changed = Signal()
    toast_requested = Signal(str, str)

    SORT_OPTIONS: list[tuple[str, str]] = [
        ("Tarihe göre (En yeni)", "date_desc"),
        ("Tarihe göre (En eski)", "date_asc"),
        ("İsme göre (A → Z)", "name_asc"),
        ("İsme göre (Z → A)", "name_desc"),
        ("Boyuta göre (En büyük)", "size_desc"),
        ("Boyuta göre (En küçük)", "size_asc"),
    ]

    def __init__(
        self,
        db: DatabaseManager,
        settings: SettingsManager,
        scanner: LibraryScanner | None = None,
        palette: ThemePalette | None = None,
        favorites_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._settings = settings
        self._scanner = scanner
        self._palette = palette or get_theme()
        self._favorites_only = favorites_only
        self._view_mode = "grid"
        self._page_size = 48
        self._current_page = 1
        self._total_pages = 1
        self._total_items = 0

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        page_title = "Favoriler" if self._favorites_only else "Medya Kütüphanesi"
        page_sub = (
            "Favorilere eklediğiniz video ve ses kayıtları"
            if self._favorites_only
            else "İndirilen tüm medya dosyalarınız düzenli arşiv görünümünde"
        )
        title_lbl = QLabel(page_title)
        title_lbl.setObjectName("PageTitle")
        self.sub_lbl = QLabel(page_sub)
        self.sub_lbl.setObjectName("PageSubtitle")
        title_col.addWidget(title_lbl)
        title_col.addWidget(self.sub_lbl)

        header.addLayout(title_col)
        header.addStretch()

        self.count_lbl = QLabel("0 öğe")
        self.count_lbl.setObjectName("MutedText")
        header.addWidget(self.count_lbl)

        if not self._favorites_only and self._scanner is not None:
            self.scan_btn = QPushButton("Klasörü Tara")
            self.scan_btn.setObjectName("SecondaryButton")
            self.scan_btn.setIcon(get_icon("refresh", self._palette.text_primary, 14))
            self.scan_btn.setIconSize(QSize(14, 14))
            self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.scan_btn.clicked.connect(lambda: self._scanner.scan(self._settings.data.download_dir))
            header.addSpacing(8)
            header.addWidget(self.scan_btn)
        else:
            self.scan_btn = None

        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        search_frame = QFrame()
        search_frame.setObjectName("SubtlePanel")
        sf_layout = QHBoxLayout(search_frame)
        sf_layout.setContentsMargins(10, 2, 8, 2)
        sf_layout.setSpacing(6)

        self.search_icon = QLabel()
        self.search_icon.setPixmap(get_pixmap("search", self._palette.text_secondary, 15))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Dosya adı, başlık veya kanal ara...")
        self.search_input.setStyleSheet("border: none; background: transparent; padding: 5px 2px;")
        self.search_input.textChanged.connect(lambda _: self.refresh(reload_platforms=False))

        sf_layout.addWidget(self.search_icon)
        sf_layout.addWidget(self.search_input, 1)
        toolbar.addWidget(search_frame, 1)

        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(155)
        self.platform_combo.addItem("Tüm Platformlar")
        self.platform_combo.currentIndexChanged.connect(lambda _: self.refresh(reload_platforms=False))
        toolbar.addWidget(self.platform_combo)

        self.sort_combo = QComboBox()
        self.sort_combo.setMinimumWidth(185)
        for label, code in self.SORT_OPTIONS:
            self.sort_combo.addItem(label, code)
        self.sort_combo.currentIndexChanged.connect(lambda _: self.refresh(reload_platforms=False))
        toolbar.addWidget(self.sort_combo)

        view_box = QHBoxLayout()
        view_box.setSpacing(4)
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)

        self.grid_btn = QPushButton()
        self.grid_btn.setObjectName("GhostButton")
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.setFixedSize(32, 32)
        self.grid_btn.setIcon(get_icon("grid", self._palette.text_primary, 15))
        self.grid_btn.setToolTip("Izgara görünümü")
        self.grid_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.grid_btn.clicked.connect(lambda: self._set_view_mode("grid"))

        self.list_btn = QPushButton()
        self.list_btn.setObjectName("GhostButton")
        self.list_btn.setCheckable(True)
        self.list_btn.setFixedSize(32, 32)
        self.list_btn.setIcon(get_icon("list", self._palette.text_secondary, 15))
        self.list_btn.setToolTip("Liste görünümü")
        self.list_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_btn.clicked.connect(lambda: self._set_view_mode("list"))

        self._view_group.addButton(self.grid_btn)
        self._view_group.addButton(self.list_btn)
        view_box.addWidget(self.grid_btn)
        view_box.addWidget(self.list_btn)
        toolbar.addLayout(view_box)

        root.addLayout(toolbar)

        div = QFrame()
        div.setObjectName("Divider")
        root.addWidget(div)

        self.stack = QStackedWidget()

        empty_icon = "heart" if self._favorites_only else "library"
        empty_title = "Henüz favori medya yok" if self._favorites_only else "Medya kütüphaneniz boş"
        empty_sub = (
            "Medya Kütüphanesi'ndeki videoların kalp ikonuna tıklayarak favorilerinize ekleyebilirsiniz."
            if self._favorites_only
            else "İndirdiğiniz tüm video ve ses dosyaları küçük resimleriyle birlikte burada otomatik listelenir."
        )
        self.empty_widget = EmptyStateWidget(empty_icon, empty_title, empty_sub)

        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid_flow = FlowLayout(self.grid_host, margin=2, h_spacing=12, v_spacing=12)
        self.grid_scroll.setWidget(self.grid_host)

        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 2, 4, 16)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.list_scroll.setWidget(self.list_host)

        self.stack.addWidget(self.empty_widget)
        self.stack.addWidget(self.grid_scroll)
        self.stack.addWidget(self.list_scroll)
        root.addWidget(self.stack, 1)

        self.pagination_bar = QFrame()
        self.pagination_bar.setObjectName("SubtlePanel")
        self.pagination_bar.hide()
        pg_lay = QHBoxLayout(self.pagination_bar)
        pg_lay.setContentsMargins(14, 8, 14, 8)
        pg_lay.setSpacing(12)

        self.prev_page_btn = QPushButton("← Önceki Sayfa")
        self.prev_page_btn.setObjectName("SecondaryButton")
        self.prev_page_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_page_btn.clicked.connect(self._on_prev_page)

        self.page_info_lbl = QLabel("Sayfa 1 / 1")
        self.page_info_lbl.setObjectName("MutedText")

        self.next_page_btn = QPushButton("Sonraki Sayfa →")
        self.next_page_btn.setObjectName("SecondaryButton")
        self.next_page_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_page_btn.clicked.connect(self._on_next_page)

        pg_lay.addWidget(self.prev_page_btn)
        pg_lay.addStretch()
        pg_lay.addWidget(self.page_info_lbl)
        pg_lay.addStretch()
        pg_lay.addWidget(self.next_page_btn)
        root.addWidget(self.pagination_bar)

    def _set_view_mode(self, mode: str) -> None:
        if self._view_mode == mode:
            return
        self._view_mode = mode
        self.grid_btn.setIcon(
            get_icon("grid", self._palette.text_primary if mode == "grid" else self._palette.text_secondary, 15)
        )
        self.list_btn.setIcon(
            get_icon("list", self._palette.text_primary if mode == "list" else self._palette.text_secondary, 15)
        )
        self.refresh(reload_platforms=False)

    def _reload_platform_choices(self) -> None:
        current = self.platform_combo.currentText() or "Tüm Platformlar"
        platforms = self._db.get_distinct_platforms()

        self.platform_combo.blockSignals(True)
        self.platform_combo.clear()
        self.platform_combo.addItem("Tüm Platformlar")
        for p in platforms:
            self.platform_combo.addItem(p)
        idx = self.platform_combo.findText(current)
        self.platform_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.platform_combo.blockSignals(False)

    def _clear_containers(self) -> None:
        while self.grid_flow.count():
            li = self.grid_flow.takeAt(0)
            if li and li.widget():
                li.widget().deleteLater()

        while self.list_layout.count() > 1:
            li = self.list_layout.takeAt(0)
            if li and li.widget():
                li.widget().deleteLater()

    def _on_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self.refresh(reload_platforms=False, reset_page=False)

    def _on_next_page(self) -> None:
        if self._current_page < self._total_pages:
            self._current_page += 1
            self.refresh(reload_platforms=False, reset_page=False)

    def refresh(self, reload_platforms: bool = True, reset_page: bool = True) -> None:
        if reload_platforms:
            self._reload_platform_choices()

        if reset_page:
            self._current_page = 1

        search_txt = self.search_input.text().strip()
        platform_val = self.platform_combo.currentText()
        sort_code = str(self.sort_combo.currentData() or "date_desc")

        total_count = self._db.get_media_items_count(
            search=search_txt,
            platform=platform_val,
            favorites_only=self._favorites_only,
        )
        self._total_items = total_count
        self._total_pages = max(1, (total_count + self._page_size - 1) // self._page_size)

        if self._current_page > self._total_pages:
            self._current_page = self._total_pages
        if self._current_page < 1:
            self._current_page = 1

        offset = (self._current_page - 1) * self._page_size
        items = self._db.get_media_items(
            search=search_txt,
            platform=platform_val,
            favorites_only=self._favorites_only,
            sort_by=sort_code,
            limit=self._page_size,
            offset=offset,
        )

        self.count_lbl.setText(f"{total_count} medya")
        self._clear_containers()

        if not items:
            self.pagination_bar.hide()
            self.stack.setCurrentIndex(0)
            return

        if self._total_pages > 1:
            self.prev_page_btn.setEnabled(self._current_page > 1)
            self.next_page_btn.setEnabled(self._current_page < self._total_pages)
            self.page_info_lbl.setText(f"Sayfa {self._current_page} / {self._total_pages}   ·   Toplam {self._total_items} medya")
            self.pagination_bar.show()
        else:
            self.pagination_bar.hide()

        if self._view_mode == "grid":
            for it in items:
                card = MediaGridCard(it, palette=self._palette, parent=self.grid_host)
                self._wire_item_widget(card)
                self.grid_flow.addWidget(card)
            self.stack.setCurrentIndex(1)
        else:
            for it in items:
                row = MediaListRow(it, palette=self._palette, parent=self.list_host)
                self._wire_item_widget(row)
                self.list_layout.insertWidget(self.list_layout.count() - 1, row)
            self.stack.setCurrentIndex(2)

    def _wire_item_widget(self, widget: MediaGridCard | MediaListRow) -> None:
        widget.play_requested.connect(self._handle_play)
        widget.folder_requested.connect(self._handle_open_folder)
        widget.copy_path_requested.connect(self._handle_copy_path)
        widget.favorite_toggled.connect(self._handle_toggle_favorite)
        widget.delete_requested.connect(self._handle_delete)

    def _handle_play(self, media_id: int) -> None:
        item = self._db.get_media_by_id(media_id)
        if not item:
            return
        if not open_file_in_default_player(item["file_path"]):
            self.toast_requested.emit("Dosya diskte bulunamadı veya taşınmış.", "error")

    def _handle_open_folder(self, media_id: int) -> None:
        item = self._db.get_media_by_id(media_id)
        if not item:
            return
        if not reveal_in_explorer(item["file_path"]):
            self.toast_requested.emit("Klasör bulunamadı.", "error")

    def _handle_copy_path(self, media_id: int) -> None:
        item = self._db.get_media_by_id(media_id)
        if not item:
            return
        QApplication.clipboard().setText(str(item["file_path"]))
        self.toast_requested.emit("Dosya yolu panoya kopyalandı.", "success")

    def _handle_toggle_favorite(self, media_id: int) -> None:
        new_state = self._db.toggle_favorite(media_id)
        msg = "Favorilere eklendi." if new_state else "Favorilerden çıkarıldı."
        self.toast_requested.emit(msg, "info")
        self.refresh(reload_platforms=False, reset_page=False)
        self.library_changed.emit()

    def _handle_delete(self, media_id: int) -> None:
        item = self._db.get_media_by_id(media_id)
        if not item:
            return
        fpath = Path(item["file_path"])
        dlg = DeleteMediaDialog(item.get("file_name") or item.get("title") or "Medya", fpath.is_file(), self)
        if not dlg.exec():
            return

        if dlg.delete_from_disk and fpath.is_file():
            try:
                fpath.unlink()
            except OSError as exc:
                self.toast_requested.emit(f"Dosya silinemedi: {exc}", "error")
                return

        self._db.delete_media_item(media_id)
        self.toast_requested.emit(
            "Dosya ve kütüphane kaydı silindi." if dlg.delete_from_disk else "Kütüphaneden kaldırıldı.",
            "info",
        )
        self.refresh(reload_platforms=True, reset_page=False)
        self.library_changed.emit()

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.search_icon.setPixmap(get_pixmap("search", palette.text_secondary, 15))
        if self.scan_btn:
            self.scan_btn.setIcon(get_icon("refresh", palette.text_primary, 14))
        self.grid_btn.setIcon(
            get_icon("grid", palette.text_primary if self._view_mode == "grid" else palette.text_secondary, 15)
        )
        self.list_btn.setIcon(
            get_icon("list", palette.text_primary if self._view_mode == "list" else palette.text_secondary, 15)
        )
        self.refresh(reload_platforms=False)
