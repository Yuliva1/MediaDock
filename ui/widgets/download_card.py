
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.constants import resolve_platform_info
from config.theme import ThemePalette, get_theme
from core.metadata import format_bytes, format_duration
from ui.icons import get_icon
from ui.widgets.custom_widgets import PlatformBadge, RoundedThumbnail, SmoothProgressBar


class DownloadCard(QFrame):

    pause_requested = Signal(str)
    resume_requested = Signal(str)
    cancel_requested = Signal(str)
    retry_requested = Signal(str)
    play_requested = Signal(str)
    open_folder_requested = Signal(str)

    def __init__(self, task: dict[str, Any], palette: ThemePalette | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SurfaceCard")
        self._palette = palette or get_theme()
        self.task_id: str = task["task_id"]
        self._task = dict(task)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(14)

        is_audio = task.get("audio_mode", "video") != "video"
        self.thumb = RoundedThumbnail(width=144, height=81, radius=6, is_audio=is_audio)
        root.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignVCenter)

        mid = QVBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        plat_name, plat_color = resolve_platform_info(task.get("platform"), task.get("url", ""))
        self.platform_badge = PlatformBadge(plat_name, plat_color)
        top_row.addWidget(self.platform_badge, 0)

        self.spec_lbl = QLabel()
        self.spec_lbl.setObjectName("MutedText")
        self.spec_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; padding: 1px 6px; "
            "border-radius: 4px; background: rgba(255,255,255,0.04);"
        )
        top_row.addWidget(self.spec_lbl, 0)
        top_row.addStretch()

        self.pct_lbl = QLabel("0%")
        self.pct_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        top_row.addWidget(self.pct_lbl, 0)

        self.title_lbl = QLabel()
        self.title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.progress_bar = SmoothProgressBar(self._palette)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        self.status_lbl = QLabel()
        self.status_lbl.setObjectName("SecondaryText")

        self.speed_lbl = QLabel()
        self.speed_lbl.setObjectName("MutedText")

        self.eta_lbl = QLabel()
        self.eta_lbl.setObjectName("MutedText")

        self.size_lbl = QLabel()
        self.size_lbl.setObjectName("MutedText")

        stats_row.addWidget(self.status_lbl)
        stats_row.addWidget(self.speed_lbl)
        stats_row.addWidget(self.eta_lbl)
        stats_row.addWidget(self.size_lbl)
        stats_row.addStretch()

        mid.addLayout(top_row)
        mid.addWidget(self.title_lbl)
        mid.addWidget(self.progress_bar)
        mid.addLayout(stats_row)
        root.addLayout(mid, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(4, 0, 0, 0)
        actions.setSpacing(6)

        self.pause_btn = self._make_btn("Duraklat", "pause", "SecondaryButton")
        self.pause_btn.clicked.connect(lambda: self.pause_requested.emit(self.task_id))

        self.resume_btn = self._make_btn("Devam Et", "play", "SecondaryButton")
        self.resume_btn.clicked.connect(lambda: self.resume_requested.emit(self.task_id))

        self.retry_btn = self._make_btn("Yeniden Dene", "refresh", "PrimaryButton")
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.task_id))

        self.play_btn = self._make_btn("Oynat", "play", "SecondaryButton")
        self.play_btn.clicked.connect(self._on_play)

        self.folder_btn = self._make_btn("Klasör", "folder", "GhostButton")
        self.folder_btn.setToolTip("Dosyanın bulunduğu klasörü aç")
        self.folder_btn.clicked.connect(self._on_open_folder)

        self.cancel_btn = self._make_btn("", "close", "DangerGhostButton")
        self.cancel_btn.setFixedSize(30, 30)
        self.cancel_btn.setToolTip("İndirmeyi iptal et / kaldır")
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.task_id))

        for b in (self.pause_btn, self.resume_btn, self.retry_btn, self.play_btn, self.folder_btn, self.cancel_btn):
            actions.addWidget(b)

        root.addLayout(actions, 0)
        self.update_task(task, initial=True)

    def _make_btn(self, text: str, icon_name: str, obj_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(obj_name)
        color = "#FFFFFF" if obj_name == "PrimaryButton" else self._palette.text_primary
        btn.setIcon(get_icon(icon_name, color, 14))
        btn.setIconSize(QSize(14, 14))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.thumb.set_palette_theme(palette)
        self.progress_bar.set_palette_theme(palette)
        self.update_task(self._task, initial=True)

    @property
    def status(self) -> str:
        return str(self._task.get("status", "queued"))

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            st = str(self._task.get("status", "queued"))
            if st == "completed":
                self._on_play()
            else:
                self._on_open_folder()
        super().mouseDoubleClickEvent(event)

    def _on_play(self) -> None:
        fp = self._task.get("final_path") or ""
        if fp:
            self.play_requested.emit(fp)

    def _on_open_folder(self) -> None:
        fp = self._task.get("final_path")
        if not fp:
            out_dir = self._task.get("output_dir", "")
            stem = self._task.get("file_stem", "")
            fp = str(Path(out_dir) / stem) if (out_dir and stem) else out_dir
        if fp:
            self.open_folder_requested.emit(fp)

    def update_task(self, task: dict[str, Any], initial: bool = False) -> None:
        self._task = dict(task)
        st = str(task.get("status", "queued"))
        is_audio = task.get("audio_mode", "video") != "video"

        self.thumb.set_thumbnail(task.get("thumbnail_path"), is_audio=is_audio)
        dur = float(task.get("duration") or 0.0)
        self.thumb.set_badge(format_duration(dur) if dur > 0 else "")

        plat_name, plat_color = resolve_platform_info(task.get("platform"), task.get("url", ""))
        self.platform_badge.set_platform(plat_name, plat_color)

        if is_audio:
            spec = f"SES · {str(task.get('audio_mode', '')).upper()}"
        else:
            spec = f"{task.get('video_format', 'MP4')} · {task.get('quality_label', 'En iyi kalite')}"
            if task.get("premiere_optimize"):
                spec += " · Premiere Pro"
        self.spec_lbl.setText(spec)

        raw_title = str(task.get("title") or task.get("url") or "Video")
        self.title_lbl.setToolTip(raw_title)
        fm = self.title_lbl.fontMetrics()
        self.title_lbl.setText(fm.elidedText(raw_title, Qt.TextElideMode.ElideRight, 520))

        pct = float(task.get("progress") or 0.0)
        self.pct_lbl.setText(f"%{pct:.1f}" if st in ("downloading", "converting") else f"%{pct:.0f}")
        self.progress_bar.set_value(pct, animate=not initial)

        if st == "completed":
            self.progress_bar.set_bar_color(self._palette.success)
            self.status_lbl.setStyleSheet(f"color: {self._palette.success}; font-size: 12px; font-weight: 600;")
            self.status_lbl.setText("Tamamlandı")
        elif st == "failed":
            self.progress_bar.set_bar_color(self._palette.danger)
            self.status_lbl.setStyleSheet(f"color: {self._palette.danger}; font-size: 12px; font-weight: 500;")
            err = str(task.get("error_message") or "İndirme başarısız oldu.")
            self.status_lbl.setToolTip(err)
            self.status_lbl.setText(fm.elidedText(err, Qt.TextElideMode.ElideRight, 460))
        elif st == "paused":
            self.progress_bar.set_bar_color(self._palette.warning)
            self.status_lbl.setStyleSheet(f"color: {self._palette.warning}; font-size: 12px; font-weight: 500;")
            self.status_lbl.setText("Duraklatıldı")
        else:
            self.progress_bar.set_bar_color(self._palette.accent)
            self.status_lbl.setStyleSheet(f"color: {self._palette.text_secondary}; font-size: 12px;")
            self.status_lbl.setText(str(task.get("status_text") or "İndiriliyor"))

        speed = float(task.get("speed_bps") or 0.0)
        eta = task.get("eta_seconds")
        dl_b = int(task.get("downloaded_bytes") or 0)
        tot_b = int(task.get("total_bytes") or 0)

        if st == "downloading" and speed > 0:
            self.speed_lbl.setText(f"Hız: {format_bytes(speed)}/sn")
            self.speed_lbl.show()
        else:
            self.speed_lbl.hide()

        if st == "downloading" and eta is not None and eta >= 0:
            self.eta_lbl.setText(f"Kalan: {format_duration(eta)}")
            self.eta_lbl.show()
        else:
            self.eta_lbl.hide()

        if tot_b > 0 and st in ("downloading", "paused"):
            self.size_lbl.setText(f"Boyut: {format_bytes(dl_b)} / {format_bytes(tot_b)}")
            self.size_lbl.show()
        elif tot_b > 0:
            self.size_lbl.setText(f"Boyut: {format_bytes(tot_b)}")
            self.size_lbl.show()
        elif dl_b > 0:
            self.size_lbl.setText(f"İndirilen: {format_bytes(dl_b)}")
            self.size_lbl.show()
        else:
            self.size_lbl.hide()

        self.pause_btn.setVisible(st in ("queued", "downloading", "converting"))
        self.resume_btn.setVisible(st == "paused")
        self.retry_btn.setVisible(st == "failed")
        self.play_btn.setVisible(st == "completed")
        self.folder_btn.setVisible(st in ("downloading", "converting", "paused", "completed", "failed"))
        self.cancel_btn.setToolTip("Listeden kaldır" if st == "completed" else "İndirmeyi iptal et")
