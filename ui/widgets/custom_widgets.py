
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.theme import ThemePalette, get_theme
from core.metadata import extract_urls_from_text
from ui.icons import get_icon, get_pixmap


def format_iso_date(iso_str: str) -> str:
    if not iso_str:
        return "—"
    months = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso_str)
        return f"{dt.day:02d} {months[dt.month - 1]} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return iso_str[:16].replace("T", " ")


class ToggleSwitch(QWidget):

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = bool(checked)
        self._palette = palette or get_theme()
        self._knob_pos = 1.0 if self._checked else 0.0
        self._hovered = False

        self.setFixedSize(36, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool, emit_signal: bool = False) -> None:
        val = bool(value)
        if self._checked == val:
            return
        self._checked = val
        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(1.0 if val else 0.0)
        self._anim.start()
        if emit_signal:
            self.toggled.emit(self._checked)
        self.update()

    def _on_anim_value(self, val: float) -> None:
        self._knob_pos = float(val)
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.setChecked(not self._checked, emit_signal=True)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        off_color = QColor(self._palette.border_hover if self._hovered else self._palette.bg_elevated)
        on_color = QColor(self._palette.accent_hover if self._hovered else self._palette.accent)

        t = self._knob_pos
        r = int(off_color.red() + (on_color.red() - off_color.red()) * t)
        g = int(off_color.green() + (on_color.green() - off_color.green()) * t)
        b = int(off_color.blue() + (on_color.blue() - off_color.blue()) * t)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setBrush(QColor(r, g, b))
        border_col = QColor(self._palette.accent) if self._checked else QColor(self._palette.border_hover)
        painter.setPen(QPen(border_col, 1.0))
        painter.drawRoundedRect(rect, 9.5, 9.5)

        knob_d = 14.0
        min_x = 3.0
        max_x = self.width() - knob_d - 3.0
        knob_x = min_x + (max_x - min_x) * t
        knob_rect = QRectF(knob_x, (self.height() - knob_d) / 2.0, knob_d, knob_d)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF") if self._checked else QColor(self._palette.text_primary))
        painter.drawEllipse(knob_rect)
        painter.end()


class SmoothProgressBar(QWidget):

    def __init__(self, palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = palette or get_theme()
        self._value = 0.0
        self._display_val = 0.0
        self._custom_color: str | None = None
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.update()

    def set_bar_color(self, hex_color: str | None) -> None:
        self._custom_color = hex_color
        self.update()

    def set_value(self, value: float, animate: bool = True) -> None:
        clamped = max(0.0, min(100.0, float(value)))
        self._value = clamped
        self._anim.stop()
        if animate and abs(clamped - self._display_val) > 0.3:
            self._anim.setStartValue(self._display_val)
            self._anim.setEndValue(clamped)
            self._anim.start()
        else:
            self._display_val = clamped
            self.update()

    set_target_value = set_value

    def _on_anim(self, val: float) -> None:
        self._display_val = float(val)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = float(self.width()), float(self.height())
        radius = h / 2.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._palette.border))
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        if self._display_val > 0.2:
            fill_w = max(h, w * (self._display_val / 100.0))
            fill_col = QColor(self._custom_color or self._palette.accent)
            painter.setBrush(fill_col)
            painter.drawRoundedRect(QRectF(0, 0, min(w, fill_w), h), radius, radius)

        painter.end()


class RoundedThumbnail(QWidget):

    def __init__(
        self,
        width: int = 160,
        height: int = 90,
        radius: int = 6,
        is_audio: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._radius = radius
        self._pixmap: QPixmap | None = None
        self._badge_text: str = ""
        self._is_audio = is_audio
        self._palette = get_theme()
        if width > 0 and height > 0:
            self.setFixedSize(width, height)

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.update()

    def set_thumbnail(self, image_path: str | None, is_audio: bool = False) -> None:
        self._is_audio = is_audio
        if image_path and Path(image_path).is_file():
            pm = QPixmap(image_path)
            self._pixmap = pm if not pm.isNull() else None
        else:
            self._pixmap = None
        self.update()

    def set_badge(self, text: str) -> None:
        self._badge_text = text.strip()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(clip_path)

        painter.fillRect(rect, QColor(self._palette.bg_surface_alt))

        if self._pixmap and not self._pixmap.isNull():
            dpr = self.devicePixelRatioF()
            target_size = QSize(int(self.width() * dpr), int(self.height() * dpr))
            scaled = self._pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(dpr)
            sw = scaled.width() / dpr
            sh = scaled.height() / dpr
            sx = (self.width() - sw) / 2.0
            sy = (self.height() - sh) / 2.0
            painter.drawPixmap(QPoint(int(sx), int(sy)), scaled)
        else:
            icon_name = "music" if self._is_audio else "film"
            icon_pm = get_pixmap(icon_name, self._palette.text_muted, 24)
            ix = int((self.width() - 24) / 2)
            iy = int((self.height() - 24) / 2)
            painter.drawPixmap(ix, iy, icon_pm)

        if self._badge_text and self._badge_text != "00:00":
            font = QFont("Segoe UI", 8)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(self._badge_text) + 10
            th = 18
            bx = self.width() - tw - 6
            by = self.height() - th - 6
            badge_rect = QRectF(bx, by, tw, th)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(17, 17, 19, 215))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor("#F0F0F2"))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._badge_text)

        painter.setClipping(False)
        painter.setPen(QPen(QColor(self._palette.border), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, self._radius, self._radius)
        painter.end()


class PlatformBadge(QFrame):

    def __init__(self, platform_name: str = "Web Medya", dot_color: str = "#929298", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dot_color = dot_color
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)

        self.dot = QLabel()
        self.dot.setFixedSize(6, 6)
        self.label = QLabel(platform_name)
        self.label.setStyleSheet("font-size: 11px; font-weight: 600; background: transparent; border: none;")

        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        self.set_platform(platform_name, dot_color)

    def set_platform(self, platform_name: str, dot_color: str = "#929298") -> None:
        self._dot_color = dot_color
        self.label.setText(platform_name)
        self.dot.setStyleSheet(f"background-color: {dot_color}; border-radius: 3px; border: none;")
        self.setStyleSheet(
            "PlatformBadge { background-color: rgba(255, 255, 255, 0.04); "
            "border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 5px; }"
        )


class EmptyStateWidget(QWidget):

    def __init__(
        self,
        icon_name: str,
        title: str,
        subtitle: str,
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.action_clicked = None
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(24, 48, 24, 48)
        layout.setSpacing(10)

        icon_box = QFrame()
        icon_box.setObjectName("SurfaceCard")
        icon_box.setFixedSize(48, 48)
        ib_layout = QVBoxLayout(icon_box)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        ib_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setPixmap(get_pixmap(icon_name, "#929298", 22))
        ib_layout.addWidget(self.icon_label)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("SectionTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setObjectName("SecondaryText")
        sub_lbl.setWordWrap(True)
        sub_lbl.setMaximumWidth(380)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(icon_box, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(4)
        layout.addWidget(title_lbl, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub_lbl, 0, Qt.AlignmentFlag.AlignCenter)

        self.action_btn: QPushButton | None = None
        if action_text:
            self.action_btn = QPushButton(action_text)
            self.action_btn.setObjectName("SecondaryButton")
            self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addSpacing(6)
            layout.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignCenter)


class ToastOverlay(QFrame):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("BannerCard")
        self.setFixedHeight(40)
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 14, 8)
        layout.setSpacing(8)

        self.icon_lbl = QLabel()
        self.msg_lbl = QLabel()
        self.msg_lbl.setStyleSheet("font-size: 12px; font-weight: 500;")
        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.msg_lbl)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.valueChanged.connect(lambda v: self._opacity.setOpacity(float(v)))
        self._anim.finished.connect(self._on_anim_finished)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

    def _on_anim_finished(self) -> None:
        if self._opacity.opacity() <= 0.05:
            self.hide()

    def show_toast(self, message: str, kind: str = "info", palette: ThemePalette | None = None) -> None:
        pal = palette or get_theme()
        icon_map = {
            "success": ("check", pal.success),
            "error": ("alert", pal.danger),
            "warning": ("alert", pal.warning),
            "info": ("sparkles", pal.accent),
        }
        ic_name, ic_color = icon_map.get(kind, ("check", pal.accent))
        self.icon_lbl.setPixmap(get_pixmap(ic_name, ic_color, 16))
        self.msg_lbl.setText(message)
        self.adjustSize()
        self.setMinimumWidth(min(440, max(220, self.sizeHint().width() + 12)))
        self.reposition()

        self._timer.stop()
        self._anim.stop()
        self._opacity.setOpacity(0.0)
        self.show()
        self.raise_()

        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(3000)

    def _fade_out(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._opacity.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def reposition(self) -> None:
        if self.parentWidget():
            pw = self.parentWidget().width()
            ph = self.parentWidget().height()
            self.move(pw - self.width() - 24, ph - self.height() - 24)


class DeleteMediaDialog(QDialog):

    def __init__(self, title_text: str, file_exists: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Medyayı Sil")
        self.setModal(True)
        self.setFixedWidth(420)
        self.delete_from_disk = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)

        hdr = QLabel("Kütüphaneden Kaldır")
        hdr.setObjectName("SectionTitle")

        desc = QLabel(f"“{title_text}” öğesini kaldırmak istediğinize emin misiniz?")
        desc.setObjectName("SecondaryText")
        desc.setWordWrap(True)

        layout.addWidget(hdr)
        layout.addWidget(desc)

        self.disk_checkbox = QCheckBox("Dosyayı bilgisayardan da kalıcı olarak sil")
        self.disk_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disk_checkbox.setStyleSheet("font-size: 12px; spacing: 8px; padding: 4px 0;")
        if file_exists:
            layout.addWidget(self.disk_checkbox)

        layout.addSpacing(6)
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Vazgeç")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        confirm_btn = QPushButton("Kaldır")
        confirm_btn.setObjectName("PrimaryButton")
        confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def on_confirm() -> None:
            self.delete_from_disk = self.disk_checkbox.isChecked()
            self.accept()

        confirm_btn.clicked.connect(on_confirm)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)


class BatchUrlDialog(QDialog):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Toplu Bağlantı Ekle")
        self.setModal(True)
        self.resize(520, 340)
        self.urls: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(12)

        hdr = QLabel("Birden Fazla Bağlantıyı Sıraya Ekle")
        hdr.setObjectName("SectionTitle")

        sub = QLabel(
            "Her satıra bir video bağlantısı yapıştırın. "
            "İndirmeler varsayılan kalite ve format ayarlarınızla sıraya alınacaktır."
        )
        sub.setObjectName("SecondaryText")
        sub.setWordWrap(True)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "https://www.youtube.com/watch?v=...\n"
            "https://kick.com/...\n"
            "https://x.com/.../status/..."
        )

        self.count_lbl = QLabel("0 geçerli bağlantı algılandı")
        self.count_lbl.setObjectName("MutedText")
        self.editor.textChanged.connect(self._update_count)

        btn_row = QHBoxLayout()
        paste_btn = QPushButton("Panodan Yapıştır")
        paste_btn.setObjectName("SecondaryButton")
        paste_btn.setIcon(get_icon("paste", "#F0F0F2", 14))
        paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        paste_btn.clicked.connect(self._paste_clipboard)

        btn_row.addWidget(paste_btn)
        btn_row.addStretch()

        cancel_btn = QPushButton("Vazgeç")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)

        self.add_btn = QPushButton("Sıraya Ekle")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.setEnabled(False)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_submit)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.add_btn)

        layout.addWidget(hdr)
        layout.addWidget(sub)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.count_lbl)
        layout.addLayout(btn_row)

    def _paste_clipboard(self) -> None:
        from PySide6.QtWidgets import QApplication

        text = QApplication.clipboard().text()
        if text:
            existing = self.editor.toPlainText().strip()
            combined = f"{existing}\n{text.strip()}" if existing else text.strip()
            self.editor.setPlainText(combined)

    def _update_count(self) -> None:
        found = extract_urls_from_text(self.editor.toPlainText())
        self.urls = found
        self.count_lbl.setText(f"{len(found)} geçerli bağlantı algılandı")
        self.add_btn.setEnabled(len(found) > 0)

    def _on_submit(self) -> None:
        if self.urls:
            self.accept()
