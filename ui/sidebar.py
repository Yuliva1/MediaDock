
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.constants import APP_NAME, APP_VERSION
from config.theme import ThemePalette, get_theme
from core.ffmpeg import DependencyStatus
from ui.icons import get_icon, get_pixmap


class _NavButton(QPushButton):

    def __init__(self, key: str, title: str, icon_name: str, palette: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.key = key
        self.title_text = title
        self.icon_name = icon_name
        self._palette = palette
        self._active = False
        self._hovered = False
        self._badge_count = 0
        self._badge_accent = False

        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 10, 0)
        row.setSpacing(10)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(16, 16)
        self.icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.text_lbl = QLabel(title)
        self.text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.badge_lbl = QLabel()
        self.badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.badge_lbl.hide()

        row.addWidget(self.icon_lbl)
        row.addWidget(self.text_lbl, 1)
        row.addWidget(self.badge_lbl, 0)

        self._refresh_visuals()

    def set_active(self, active: bool) -> None:
        if self._active != active:
            self._active = active
            self._refresh_visuals()

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self._refresh_visuals()

    def set_badge(self, count: int, highlight: bool = False) -> None:
        self._badge_count = max(0, int(count))
        self._badge_accent = highlight
        if self._badge_count > 0:
            self.badge_lbl.setText(str(self._badge_count if self._badge_count < 100 else "99+"))
            self.badge_lbl.show()
        else:
            self.badge_lbl.hide()
        self._refresh_visuals()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._refresh_visuals()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._refresh_visuals()
        super().leaveEvent(event)

    def _refresh_visuals(self) -> None:
        fg = self._palette.text_primary if (self._active or self._hovered) else self._palette.text_secondary
        ic_col = self._palette.accent if self._active else fg
        weight = "600" if self._active else "500"

        self.icon_lbl.setPixmap(get_pixmap(self.icon_name, ic_col, 16))
        self.text_lbl.setStyleSheet(f"color: {fg}; font-size: 13px; font-weight: {weight}; background: transparent;")

        if self._badge_accent:
            self.badge_lbl.setStyleSheet(
                f"background-color: {self._palette.accent}; color: #FFFFFF; "
                "border-radius: 8px; padding: 1px 6px; font-size: 10px; font-weight: 700;"
            )
        else:
            self.badge_lbl.setStyleSheet(
                f"background-color: {self._palette.bg_hover}; color: {self._palette.text_secondary}; "
                "border-radius: 8px; padding: 1px 6px; font-size: 10px; font-weight: 600;"
            )
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._palette.bg_elevated))
            painter.drawRoundedRect(QRectF(0, 1, self.width(), self.height() - 2), 6, 6)
            painter.setBrush(QColor(self._palette.accent))
            painter.drawRoundedRect(QRectF(0, 7, 3, self.height() - 14), 1.5, 1.5)
        elif self._hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._palette.bg_hover))
            painter.drawRoundedRect(QRectF(0, 1, self.width(), self.height() - 2), 6, 6)

        painter.end()


class Sidebar(QFrame):

    page_selected = Signal(str)

    NAV_ITEMS: list[tuple[str, str, str]] = [
        ("home", "Ana Sayfa", "home"),
        ("downloads", "İndirmeler", "download"),
        ("library", "Medya Kütüphanesi", "library"),
        ("favorites", "Favoriler", "heart"),
        ("history", "Geçmiş", "history"),
        ("settings", "Ayarlar", "settings"),
    ]

    def __init__(self, palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(226)
        self._palette = palette or get_theme()
        self._buttons: dict[str, _NavButton] = {}
        self._current_key = "home"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 0, 6, 14)
        brand_row.setSpacing(10)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(22, 22)
        self.logo_lbl.setPixmap(get_pixmap("logo", self._palette.accent, 22))

        brand_title = QLabel(APP_NAME)
        brand_title.setStyleSheet("font-size: 15px; font-weight: 700; letter-spacing: 0.2px;")

        brand_row.addWidget(self.logo_lbl)
        brand_row.addWidget(brand_title)
        brand_row.addStretch()
        layout.addLayout(brand_row)

        for key, label, icon_name in self.NAV_ITEMS:
            if key == "settings":
                layout.addSpacing(8)
                div = QFrame()
                div.setObjectName("Divider")
                layout.addWidget(div)
                layout.addSpacing(6)

            btn = _NavButton(key, label, icon_name, self._palette, self)
            btn.clicked.connect(lambda checked=False, k=key: self.select_page(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch(1)

        self.footer_card = QFrame()
        self.footer_card.setObjectName("SubtlePanel")
        self.footer_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.footer_card.mouseReleaseEvent = lambda ev: self.select_page("settings")

        f_layout = QVBoxLayout(self.footer_card)
        f_layout.setContentsMargins(10, 9, 10, 9)
        f_layout.setSpacing(4)

        status_row = QHBoxLayout()
        status_row.setSpacing(7)
        self.engine_dot = QLabel()
        self.engine_dot.setFixedSize(7, 7)
        self.engine_lbl = QLabel("Motor kontrol ediliyor...")
        self.engine_lbl.setStyleSheet("font-size: 11px; font-weight: 600;")

        status_row.addWidget(self.engine_dot)
        status_row.addWidget(self.engine_lbl, 1)

        self.sub_engine_lbl = QLabel("")
        self.sub_engine_lbl.setObjectName("MutedText")
        self.sub_engine_lbl.setStyleSheet("font-size: 11px;")

        self.version_lbl = QLabel(f"Sürüm v{APP_VERSION}")
        self.version_lbl.setObjectName("MutedText")
        self.version_lbl.setStyleSheet("font-size: 11px;")

        f_layout.addLayout(status_row)
        f_layout.addWidget(self.sub_engine_lbl)
        f_layout.addWidget(self.version_lbl)

        layout.addWidget(self.footer_card)
        self.select_page("home", emit_signal=False)

    def select_page(self, key: str, emit_signal: bool = True) -> None:
        if key not in self._buttons:
            return
        self._current_key = key
        for k, btn in self._buttons.items():
            btn.set_active(k == key)
        if emit_signal:
            self.page_selected.emit(key)

    def update_badges(self, active_downloads: int = 0, library_total: int = 0, favorites_total: int = 0) -> None:
        self._buttons["downloads"].set_badge(active_downloads, highlight=True)
        self._buttons["library"].set_badge(library_total, highlight=False)
        self._buttons["favorites"].set_badge(favorites_total, highlight=False)

    def update_engine_status(self, status: DependencyStatus) -> None:
        if status.ytdlp_ok and status.ffmpeg_ok:
            dot_col = self._palette.success
            title = "Motor Aktif · Hazır"
            sub = f"yt-dlp {status.ytdlp_version} · FFmpeg"
        elif status.ytdlp_ok and not status.ffmpeg_ok:
            dot_col = self._palette.warning
            title = "FFmpeg Eksik"
            sub = f"yt-dlp {status.ytdlp_version}"
        else:
            dot_col = self._palette.danger
            title = "Motor Eksik"
            sub = "Bağımlılık hatası"

        self.engine_dot.setStyleSheet(f"background-color: {dot_col}; border-radius: 3px;")
        self.engine_lbl.setText(title)
        self.sub_engine_lbl.setText(sub)
        self.footer_card.setToolTip(
            f"{status.message}\nyt-dlp: {status.ytdlp_version}\nFFmpeg: {status.ffmpeg_version}"
        )

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.logo_lbl.setPixmap(get_pixmap("logo", palette.accent, 22))
        for btn in self._buttons.values():
            btn.set_palette_theme(palette)
