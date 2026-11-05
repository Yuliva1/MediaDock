from __future__ import annotations

import gc
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.constants import IMAGE_FORMATS, resolve_platform_info
from config.theme import ThemePalette, get_theme
from core.metadata import GalleryItem, VideoMetadata, cache_thumbnail, format_duration
from ui.icons import get_icon
from ui.widgets.custom_widgets import PlatformBadge
from ui.widgets.flow_layout import FlowLayout


class _ThumbWorker(QObject):

    finished = Signal(int, str)

    def __init__(self, items: list[GalleryItem], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.items = list(items)
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:
        for it in self.items:
            if self._stopped:
                break
            if it.thumbnail_url:
                cached = cache_thumbnail(it.thumbnail_url, f"gal_{it.index}_{it.url[:40]}")
                if cached:
                    self.finished.emit(it.index, cached)


class GalleryItemCard(QFrame):

    selection_changed = Signal(int, bool)

    def __init__(
        self,
        item: GalleryItem,
        palette: ThemePalette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self._palette = palette or get_theme()
        self.setFixedSize(188, 218)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._build_ui()
        self._update_card_style()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)

        self.cb = QCheckBox()
        self.cb.setChecked(self.item.selected)
        self.cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb.toggled.connect(self._on_toggled)
        top.addWidget(self.cb)

        idx_badge = QLabel(f"#{self.item.index}")
        idx_badge.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {self._palette.text_secondary};"
        )
        top.addWidget(idx_badge)
        top.addStretch()

        is_vid = self.item.media_type == "video"
        type_txt = format_duration(self.item.duration) if (is_vid and self.item.duration > 0) else ("Video" if is_vid else "Görsel")
        type_col = "#A78BFA" if is_vid else "#38BDF8"

        type_lbl = QLabel(type_txt)
        type_lbl.setStyleSheet(
            f"background: rgba(255,255,255,0.06); color: {type_col}; "
            "font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px;"
        )
        top.addWidget(type_lbl)
        layout.addLayout(top)

        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(172, 128)
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setStyleSheet(
            f"background-color: {self._palette.bg_app}; border-radius: 5px; color: {self._palette.text_muted}; font-size: 11px;"
        )
        self.thumb_lbl.setText("Yükleniyor...")
        layout.addWidget(self.thumb_lbl)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 2, 0, 0)
        bottom.setSpacing(4)

        dim_txt = f"{self.item.width}x{self.item.height}" if (self.item.width and self.item.height) else ""
        res_lbl = QLabel(dim_txt)
        res_lbl.setStyleSheet(f"color: {self._palette.text_muted}; font-size: 11px;")
        bottom.addWidget(res_lbl)
        bottom.addStretch()

        ext_lbl = QLabel(self.item.ext.upper() if self.item.ext else ("MP4" if is_vid else "JPG"))
        ext_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 600; color: {self._palette.text_secondary};"
        )
        bottom.addWidget(ext_lbl)
        layout.addLayout(bottom)

    def set_thumbnail_path(self, path: str) -> None:
        if not path or not Path(path).is_file():
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
            scaled = pm.scaled(
                172,
                128,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.FastTransformation,
            )
            self.thumb_lbl.setPixmap(scaled)
            self.thumb_lbl.setText("")

    def _on_toggled(self, checked: bool) -> None:
        self.item.selected = checked
        self._update_card_style()
        self.selection_changed.emit(self.item.index, checked)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.cb.toggle()
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        self.cb.blockSignals(True)
        self.cb.setChecked(selected)
        self.item.selected = selected
        self.cb.blockSignals(False)
        self._update_card_style()

    def _update_card_style(self) -> None:
        b_color = self._palette.accent if self.item.selected else self._palette.border
        bg_col = self._palette.bg_elevated if self.item.selected else self._palette.bg_surface
        self.setStyleSheet(
            f"""
            GalleryItemCard {{
                background-color: {bg_col};
                border: 1px solid {b_color};
                border-radius: 8px;
            }}
            """
        )


class GalleryDialog(QDialog):

    def __init__(
        self,
        items: list[GalleryItem],
        meta: VideoMetadata,
        palette: ThemePalette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.items = list(items)
        self.meta = meta
        self._palette = palette or get_theme()
        self._cards: dict[int, GalleryItemCard] = {}
        self._thread: QThread | None = None
        self._worker: _ThumbWorker | None = None

        self.setWindowTitle("MediaDock – Çoklu Medya / Instagram Dump Seçimi")
        self.resize(860, 640)
        self.setMinimumSize(720, 520)

        self._build_ui()
        self._start_async_thumbnail_loading()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f"""
            QDialog {{
                background-color: {self._palette.bg_app};
                color: {self._palette.text_primary};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        plat_name, plat_color = resolve_platform_info(self.meta.extractor, self.meta.webpage_url)
        top_row.addWidget(PlatformBadge(plat_name, plat_color))

        hdr_texts = QVBoxLayout()
        hdr_texts.setSpacing(2)
        title = QLabel(self.meta.title or "Çoklu Medya Paylaşımı")
        title.setStyleSheet("font-size: 15px; font-weight: 700;")
        sub = QLabel(f"Toplam {len(self.items)} medya bulundu. İndirmek istediklerinizi seçin:")
        sub.setObjectName("SecondaryText")
        hdr_texts.addWidget(title)
        hdr_texts.addWidget(sub)
        top_row.addLayout(hdr_texts, 1)

        root.addLayout(top_row)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)

        self.sel_all_btn = QPushButton("Tümünü Seç")
        self.sel_all_btn.setObjectName("SecondaryButton")
        self.sel_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sel_all_btn.clicked.connect(self._select_all)
        ctrl_row.addWidget(self.sel_all_btn)

        self.desel_all_btn = QPushButton("Hiçbirini Seçme")
        self.desel_all_btn.setObjectName("GhostButton")
        self.desel_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.desel_all_btn.clicked.connect(self._deselect_all)
        ctrl_row.addWidget(self.desel_all_btn)

        ctrl_row.addStretch()

        self.counter_lbl = QLabel()
        self.counter_lbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {self._palette.accent};")
        ctrl_row.addWidget(self.counter_lbl)

        fmt_lbl = QLabel("Görsel Formatı:")
        fmt_lbl.setObjectName("FieldLabel")
        ctrl_row.addWidget(fmt_lbl)

        self.format_combo = QComboBox()
        for f in IMAGE_FORMATS:
            self.format_combo.addItem(f, f)
        ctrl_row.addWidget(self.format_combo)

        root.addLayout(ctrl_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {self._palette.bg_app};
                border: 1px solid {self._palette.border};
                border-radius: 8px;
            }}
            """
        )

        container = QWidget()
        flow = FlowLayout(container, margin=12, h_spacing=12, v_spacing=12)

        for it in self.items:
            card = GalleryItemCard(it, self._palette, container)
            card.selection_changed.connect(self._on_card_selection_changed)
            self._cards[it.index] = card
            flow.addWidget(card)

        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addStretch()

        self.cancel_btn = QPushButton("Vazgeç")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(self.cancel_btn)

        self.download_btn = QPushButton()
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setIcon(get_icon("download", "#FFFFFF", 14))
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.clicked.connect(self.accept)
        bottom.addWidget(self.download_btn)

        root.addLayout(bottom)
        self._update_counter()

    def _start_async_thumbnail_loading(self) -> None:
        thread = QThread(self)
        worker = _ThumbWorker(self.items)
        worker.moveToThread(thread)

        def on_thumb(idx: int, path: str) -> None:
            card = self._cards.get(idx)
            if card:
                card.set_thumbnail_path(path)

        def cleanup() -> None:
            worker.deleteLater()
            thread.deleteLater()
            self._thread = None
            self._worker = None

        thread.started.connect(worker.run)
        worker.finished.connect(on_thumb)
        thread.finished.connect(cleanup)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_card_selection_changed(self, idx: int, checked: bool) -> None:
        self._update_counter()

    def _select_all(self) -> None:
        for card in self._cards.values():
            card.set_selected(True)
        self._update_counter()

    def _deselect_all(self) -> None:
        for card in self._cards.values():
            card.set_selected(False)
        self._update_counter()

    def _update_counter(self) -> None:
        selected_count = sum(1 for it in self.items if it.selected)
        tot = len(self.items)
        self.counter_lbl.setText(f"{selected_count} / {tot} Seçildi")
        self.download_btn.setText(f"Seçilen {selected_count} Medyayı İndir")
        self.download_btn.setEnabled(selected_count > 0)

    def get_selected_items(self) -> list[GalleryItem]:
        return [it for it in self.items if it.selected]

    def get_chosen_format(self) -> str:
        return str(self.format_combo.currentData() or "Orijinal")

    def _cleanup_worker(self) -> None:
        if self._worker:
            self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(600)
        self._thread = None
        self._worker = None

    def reject(self) -> None:
        self._cleanup_worker()
        super().reject()

    def accept(self) -> None:
        self._cleanup_worker()
        super().accept()

    def closeEvent(self, event) -> None:
        self._cleanup_worker()
        gc.collect()
        super().closeEvent(event)
