from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    SUPPORTED_AUDIO_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    resolve_platform_info,
)
from config.theme import ThemePalette, get_theme
from core.metadata import format_bytes, format_duration
from ui.icons import get_icon
from ui.widgets.custom_widgets import PlatformBadge, RoundedThumbnail, format_iso_date


class _BaseMediaWidget(QFrame):

    play_requested = Signal(int)
    folder_requested = Signal(int)
    copy_path_requested = Signal(int)
    favorite_toggled = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, item: dict[str, Any], palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCardHover")
        self.setProperty("class", "SurfaceCard")
        self._palette = palette or get_theme()
        self.item = dict(item)
        self.media_id = int(item["id"])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_card_style()

    def _apply_card_style(self) -> None:
        self.setStyleSheet(
            f"""
            _BaseMediaWidget, MediaGridCard, MediaListRow {{
                background-color: {self._palette.bg_surface};
                border: 1px solid {self._palette.border};
                border-radius: 8px;
            }}
            _BaseMediaWidget:hover, MediaGridCard:hover, MediaListRow:hover {{
                background-color: {self._palette.bg_elevated};
                border: 1px solid {self._palette.border_hover};
            }}
            """
        )

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.play_requested.emit(self.media_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        ext = Path(self.item.get("file_path", "")).suffix.lower()
        is_image = ext in SUPPORTED_IMAGE_EXTENSIONS or self.item.get("video_codec") == "Görsel"
        action_label = "Görseli Aç" if is_image else "Videoyu Oynat"

        act_play = menu.addAction(get_icon("play", self._palette.text_primary, 14), action_label)
        act_folder = menu.addAction(get_icon("folder", self._palette.text_primary, 14), "Bulunduğu Klasörü Aç")
        act_copy = menu.addAction(get_icon("copy", self._palette.text_primary, 14), "Dosya Yolunu Kopyala")
        menu.addSeparator()
        is_fav = bool(self.item.get("is_favorite"))
        fav_label = "Favorilerden Çıkar" if is_fav else "Favorilere Ekle"
        act_fav = menu.addAction(get_icon("heart_filled" if is_fav else "heart", self._palette.accent, 14), fav_label)
        menu.addSeparator()
        act_del = menu.addAction(get_icon("trash", self._palette.danger, 14), "Kütüphaneden Sil...")

        chosen = menu.exec(event.globalPos())
        if chosen == act_play:
            self.play_requested.emit(self.media_id)
        elif chosen == act_folder:
            self.folder_requested.emit(self.media_id)
        elif chosen == act_copy:
            self.copy_path_requested.emit(self.media_id)
        elif chosen == act_fav:
            self.favorite_toggled.emit(self.media_id)
        elif chosen == act_del:
            self.delete_requested.emit(self.media_id)


def _icon_action_btn(icon_name: str, tooltip: str, color: str, danger: bool = False) -> QPushButton:
    btn = QPushButton()
    btn.setObjectName("DangerGhostButton" if danger else "GhostButton")
    btn.setIcon(get_icon(icon_name, color, 15))
    btn.setIconSize(QSize(15, 15))
    btn.setFixedSize(28, 28)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class MediaGridCard(_BaseMediaWidget):

    def __init__(self, item: dict[str, Any], palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(item, palette, parent)
        self.setFixedWidth(288)

        fpath = str(item.get("file_path", ""))
        ext = Path(fpath).suffix.lower()
        is_audio = ext in SUPPORTED_AUDIO_EXTENSIONS
        is_image = ext in SUPPORTED_IMAGE_EXTENSIONS or item.get("video_codec") == "Görsel"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 11, 11, 11)
        layout.setSpacing(8)

        self.thumb = RoundedThumbnail(width=264, height=148, radius=6, is_audio=is_audio)
        self.thumb.set_palette_theme(self._palette)
        thumb_src = item.get("thumbnail_path") or (fpath if is_image else "")
        self.thumb.set_thumbnail(thumb_src, is_audio=is_audio)
        dur = float(item.get("duration") or 0.0)
        self.thumb.set_badge("" if is_image else (format_duration(dur) if dur > 0 else ""))
        layout.addWidget(self.thumb)

        file_name = str(item.get("file_name") or item.get("title") or "Medya")
        title_lbl = QLabel()
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent; border: none;")
        tip_action = "görüntüleyicide açın" if is_image else "oynatıcıda açın"
        title_lbl.setToolTip(f"{file_name}\nÇift tıklayarak varsayılan {tip_action}")
        fm = title_lbl.fontMetrics()
        title_lbl.setText(fm.elidedText(file_name, Qt.TextElideMode.ElideRight, 260))
        layout.addWidget(title_lbl)

        res = str(item.get("resolution") or item.get("format") or "Medya")
        size_txt = format_bytes(item.get("file_size"))
        meta_lbl = QLabel(f"{res}  ·  {size_txt}")
        meta_lbl.setStyleSheet(f"color: {self._palette.text_secondary}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(meta_lbl)

        date_lbl = QLabel(format_iso_date(str(item.get("downloaded_at") or "")))
        date_lbl.setStyleSheet(f"color: {self._palette.text_muted}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(date_lbl)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 2, 0, 0)
        bottom.setSpacing(3)

        plat_name, plat_color = resolve_platform_info(item.get("platform"), item.get("source_url", ""))
        badge = PlatformBadge(plat_name, plat_color)
        bottom.addWidget(badge)
        bottom.addStretch()

        play_tip = "Görseli aç" if is_image else "Videoyu oynat"
        play_btn = _icon_action_btn("play", play_tip, self._palette.text_primary)
        play_btn.clicked.connect(lambda: self.play_requested.emit(self.media_id))

        folder_btn = _icon_action_btn("folder", "Klasörü aç", self._palette.text_secondary)
        folder_btn.clicked.connect(lambda: self.folder_requested.emit(self.media_id))

        copy_btn = _icon_action_btn("copy", "Dosya yolunu kopyala", self._palette.text_secondary)
        copy_btn.clicked.connect(lambda: self.copy_path_requested.emit(self.media_id))

        is_fav = bool(item.get("is_favorite"))
        self.fav_btn = _icon_action_btn(
            "heart_filled" if is_fav else "heart",
            "Favorilerden çıkar" if is_fav else "Favorilere ekle",
            self._palette.accent if is_fav else self._palette.text_secondary,
        )
        self.fav_btn.clicked.connect(lambda: self.favorite_toggled.emit(self.media_id))

        del_btn = _icon_action_btn("trash", "Sil", self._palette.text_secondary, danger=True)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.media_id))

        for b in (play_btn, folder_btn, copy_btn, self.fav_btn, del_btn):
            bottom.addWidget(b)

        layout.addLayout(bottom)


class MediaListRow(_BaseMediaWidget):

    def __init__(self, item: dict[str, Any], palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(item, palette, parent)
        self.setFixedHeight(78)

        fpath = str(item.get("file_path", ""))
        ext = Path(fpath).suffix.lower()
        is_audio = ext in SUPPORTED_AUDIO_EXTENSIONS
        is_image = ext in SUPPORTED_IMAGE_EXTENSIONS or item.get("video_codec") == "Görsel"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 14, 8)
        layout.setSpacing(14)

        self.thumb = RoundedThumbnail(width=106, height=60, radius=5, is_audio=is_audio)
        self.thumb.set_palette_theme(self._palette)
        thumb_src = item.get("thumbnail_path") or (fpath if is_image else "")
        self.thumb.set_thumbnail(thumb_src, is_audio=is_audio)
        dur = float(item.get("duration") or 0.0)
        self.thumb.set_badge("" if is_image else (format_duration(dur) if dur > 0 else ""))
        layout.addWidget(self.thumb)

        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 2, 0, 2)
        info_col.setSpacing(4)

        file_name = str(item.get("file_name") or item.get("title") or "Medya")
        title_lbl = QLabel(file_name)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; background: transparent; border: none;")
        title_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        tip_action = "görüntüleyicide açın" if is_image else "oynatıcıda açın"
        title_lbl.setToolTip(f"{file_name}\nÇift tıklayarak varsayılan {tip_action}")

        sub_row = QHBoxLayout()
        sub_row.setSpacing(10)

        plat_name, plat_color = resolve_platform_info(item.get("platform"), item.get("source_url", ""))
        sub_row.addWidget(PlatformBadge(plat_name, plat_color))

        res = str(item.get("resolution") or item.get("format") or "—")
        dur_str = format_duration(dur)
        size_str = format_bytes(item.get("file_size"))
        date_str = format_iso_date(str(item.get("downloaded_at") or ""))

        line_txt = f"{res}   ·   Boyut: {size_str}   ·   {date_str}" if is_image else f"{res}   ·   Süre: {dur_str}   ·   Boyut: {size_str}   ·   {date_str}"
        details = QLabel(line_txt)
        details.setStyleSheet(f"color: {self._palette.text_secondary}; font-size: 12px; background: transparent; border: none;")
        sub_row.addWidget(details)
        sub_row.addStretch()

        info_col.addWidget(title_lbl)
        info_col.addLayout(sub_row)
        layout.addLayout(info_col, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)

        play_tip = "Görseli aç" if is_image else "Videoyu oynat"
        play_btn = _icon_action_btn("play", play_tip, self._palette.text_primary)
        play_btn.clicked.connect(lambda: self.play_requested.emit(self.media_id))

        folder_btn = _icon_action_btn("folder", "Klasörü aç", self._palette.text_secondary)
        folder_btn.clicked.connect(lambda: self.folder_requested.emit(self.media_id))

        copy_btn = _icon_action_btn("copy", "Dosya yolunu kopyala", self._palette.text_secondary)
        copy_btn.clicked.connect(lambda: self.copy_path_requested.emit(self.media_id))

        is_fav = bool(item.get("is_favorite"))
        fav_btn = _icon_action_btn(
            "heart_filled" if is_fav else "heart",
            "Favorilerden çıkar" if is_fav else "Favorilere ekle",
            self._palette.accent if is_fav else self._palette.text_secondary,
        )
        fav_btn.clicked.connect(lambda: self.favorite_toggled.emit(self.media_id))

        del_btn = _icon_action_btn("trash", "Sil", self._palette.text_secondary, danger=True)
        del_btn.clicked.connect(lambda: self.delete_requested.emit(self.media_id))

        for b in (play_btn, folder_btn, copy_btn, fav_btn, del_btn):
            actions.addWidget(b)

        layout.addLayout(actions)
