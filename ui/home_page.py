from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QStandardItemModel
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config.constants import (
    AUDIO_MODES,
    IMAGE_FORMATS,
    PRIORITY_PLATFORMS,
    VIDEO_FORMATS,
    VIDEO_QUALITIES,
)
from config.settings import SettingsManager
from config.theme import ThemePalette, get_theme
from core.downloader import DownloadOptions
from core.metadata import (
    MetadataController,
    VideoMetadata,
    extract_urls_from_text,
    format_duration,
    is_probable_media_url,
)
from ui.icons import get_icon, get_pixmap
from ui.widgets.custom_widgets import (
    BatchUrlDialog,
    PlatformBadge,
    RoundedThumbnail,
    ToggleSwitch,
)
from ui.widgets.gallery_dialog import GalleryDialog


class HomePage(QWidget):

    download_requested = Signal(object, object)
    batch_urls_requested = Signal(list)
    gallery_download_requested = Signal(list, str)

    def __init__(
        self,
        metadata_ctrl: MetadataController,
        settings: SettingsManager,
        palette: ThemePalette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._meta_ctrl = metadata_ctrl
        self._settings = settings
        self._palette = palette or get_theme()
        self._current_meta: VideoMetadata | None = None
        self._last_fetched_url: str = ""
        self._dismissed_clipboard_url: str = ""

        self.setAcceptDrops(True)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(450)
        self._debounce_timer.timeout.connect(self._auto_analyze_current_text)

        self._build_ui()
        self._connect_signals()
        self.apply_defaults_from_settings()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        canvas = QWidget()
        scroll.setWidget(canvas)

        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(36, 32, 36, 32)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.container = QWidget()
        self.container.setMaximumWidth(820)
        self.container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        c_layout = QVBoxLayout(self.container)
        c_layout.setContentsMargins(0, 8, 0, 0)
        c_layout.setSpacing(16)

        header_box = QVBoxLayout()
        header_box.setSpacing(6)

        hdr_top = QHBoxLayout()
        title = QLabel("Medya İndir")
        title.setObjectName("PageTitle")

        self.batch_btn = QPushButton("Toplu Bağlantı Ekle")
        self.batch_btn.setObjectName("SecondaryButton")
        self.batch_btn.setIcon(get_icon("layers", self._palette.text_primary, 14))
        self.batch_btn.setIconSize(QSize(14, 14))
        self.batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.batch_btn.clicked.connect(self._open_batch_dialog)

        hdr_top.addWidget(title)
        hdr_top.addStretch()
        hdr_top.addWidget(self.batch_btn)

        subtitle = QLabel(
            "YouTube, Kick, X, Instagram dump/post, TikTok veya görsel ve video bağlantısı yapıştırın."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        header_box.addLayout(hdr_top)
        header_box.addWidget(subtitle)
        c_layout.addLayout(header_box)
        c_layout.addSpacing(4)

        self.clipboard_banner = QFrame()
        self.clipboard_banner.setObjectName("BannerCard")
        self.clipboard_banner.hide()
        cb_layout = QHBoxLayout(self.clipboard_banner)
        cb_layout.setContentsMargins(12, 8, 10, 8)
        cb_layout.setSpacing(10)

        self.cb_icon = QLabel()
        self.cb_icon.setPixmap(get_pixmap("link", self._palette.accent, 15))
        self.cb_text = QLabel()
        self.cb_text.setObjectName("SecondaryText")
        self.cb_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        self.cb_use_btn = QPushButton("Bağlantıyı Yükle")
        self.cb_use_btn.setObjectName("SecondaryButton")
        self.cb_use_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_use_btn.clicked.connect(self._apply_detected_clipboard_url)

        self.cb_close_btn = QPushButton()
        self.cb_close_btn.setObjectName("GhostButton")
        self.cb_close_btn.setIcon(get_icon("close", self._palette.text_secondary, 13))
        self.cb_close_btn.setFixedSize(26, 26)
        self.cb_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_close_btn.clicked.connect(self._dismiss_clipboard_banner)

        cb_layout.addWidget(self.cb_icon)
        cb_layout.addWidget(self.cb_text, 1)
        cb_layout.addWidget(self.cb_use_btn)
        cb_layout.addWidget(self.cb_close_btn)
        c_layout.addWidget(self.clipboard_banner)

        self.input_bar = QFrame()
        self.input_bar.setObjectName("HeroInputBar")
        self.input_bar.setProperty("focused", "false")
        ib_layout = QHBoxLayout(self.input_bar)
        ib_layout.setContentsMargins(14, 6, 8, 6)
        ib_layout.setSpacing(8)

        self.link_icon_lbl = QLabel()
        self.link_icon_lbl.setPixmap(get_pixmap("link", self._palette.text_secondary, 17))
        ib_layout.addWidget(self.link_icon_lbl)

        self.url_input = QLineEdit()
        self.url_input.setObjectName("BorderlessUrlInput")
        self.url_input.setPlaceholderText("Video, görsel veya Instagram dump bağlantısını buraya yapıştırın...")
        self.url_input.installEventFilter(self)
        ib_layout.addWidget(self.url_input, 1)

        self.clear_btn = QPushButton()
        self.clear_btn.setObjectName("GhostButton")
        self.clear_btn.setIcon(get_icon("close", self._palette.text_secondary, 14))
        self.clear_btn.setFixedSize(28, 28)
        self.clear_btn.setToolTip("Bağlantıyı temizle")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.hide()
        self.clear_btn.clicked.connect(self._clear_url)
        ib_layout.addWidget(self.clear_btn)

        self.paste_btn = QPushButton("Yapıştır")
        self.paste_btn.setObjectName("SecondaryButton")
        self.paste_btn.setIcon(get_icon("paste", self._palette.text_primary, 14))
        self.paste_btn.setIconSize(QSize(14, 14))
        self.paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_btn.clicked.connect(self._paste_from_clipboard)
        ib_layout.addWidget(self.paste_btn)

        c_layout.addWidget(self.input_bar)

        self.loading_card = QFrame()
        self.loading_card.setObjectName("SubtlePanel")
        self.loading_card.hide()
        ld_layout = QHBoxLayout(self.loading_card)
        ld_layout.setContentsMargins(14, 12, 14, 12)
        ld_layout.setSpacing(10)

        self.loading_icon = QLabel()
        self.loading_icon.setPixmap(get_pixmap("refresh", self._palette.accent, 16))
        self.loading_lbl = QLabel("Medya bilgileri ve dump akışları analiz ediliyor...")
        self.loading_lbl.setObjectName("SecondaryText")
        ld_layout.addWidget(self.loading_icon)
        ld_layout.addWidget(self.loading_lbl, 1)
        c_layout.addWidget(self.loading_card)

        self.error_card = QFrame()
        self.error_card.setObjectName("SurfaceCard")
        self.error_card.hide()
        err_layout = QHBoxLayout(self.error_card)
        err_layout.setContentsMargins(14, 12, 14, 12)
        err_layout.setSpacing(10)

        self.err_icon = QLabel()
        self.err_icon.setPixmap(get_pixmap("alert", self._palette.danger, 18))
        self.err_lbl = QLabel()
        self.err_lbl.setWordWrap(True)
        self.err_lbl.setStyleSheet(f"color: {self._palette.text_primary}; font-size: 12px;")

        self.err_retry_btn = QPushButton("Tekrar Dene")
        self.err_retry_btn.setObjectName("SecondaryButton")
        self.err_retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.err_retry_btn.clicked.connect(lambda: self._trigger_fetch(force=True))

        err_layout.addWidget(self.err_icon, 0, Qt.AlignmentFlag.AlignTop)
        err_layout.addWidget(self.err_lbl, 1)
        err_layout.addWidget(self.err_retry_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        c_layout.addWidget(self.error_card)

        self.preview_card = QFrame()
        self.preview_card.setObjectName("SurfaceCard")
        self.preview_card.hide()
        pv_root = QVBoxLayout(self.preview_card)
        pv_root.setContentsMargins(18, 18, 18, 18)
        pv_root.setSpacing(16)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)

        self.preview_thumb = RoundedThumbnail(width=224, height=126, radius=6)
        meta_row.addWidget(self.preview_thumb, 0, Qt.AlignmentFlag.AlignTop)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(6)
        meta_col.setContentsMargins(0, 2, 0, 2)

        badge_line = QHBoxLayout()
        badge_line.setSpacing(8)
        self.platform_badge = PlatformBadge()
        self.max_res_lbl = QLabel()
        self.max_res_lbl.setObjectName("MutedText")
        self.max_res_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 600; padding: 2px 7px; "
            "border-radius: 4px; background: rgba(255,255,255,0.05);"
        )
        badge_line.addWidget(self.platform_badge)
        badge_line.addWidget(self.max_res_lbl)
        badge_line.addStretch()

        self.video_title_lbl = QLabel()
        self.video_title_lbl.setWordWrap(True)
        self.video_title_lbl.setStyleSheet("font-size: 15px; font-weight: 600; line-height: 1.3;")

        self.channel_lbl = QLabel()
        self.channel_lbl.setObjectName("SecondaryText")

        self.duration_lbl = QLabel()
        self.duration_lbl.setObjectName("MutedText")

        meta_col.addLayout(badge_line)
        meta_col.addWidget(self.video_title_lbl)
        meta_col.addWidget(self.channel_lbl)
        meta_col.addWidget(self.duration_lbl)
        meta_col.addStretch()

        meta_row.addLayout(meta_col, 1)
        pv_root.addLayout(meta_row)

        div = QFrame()
        div.setObjectName("Divider")
        pv_root.addWidget(div)

        self.opts_grid = QGridLayout()
        self.opts_grid.setHorizontalSpacing(12)
        self.opts_grid.setVerticalSpacing(6)

        self.lbl_fmt = QLabel("Format")
        self.lbl_fmt.setObjectName("FieldLabel")
        self.lbl_qual = QLabel("Kalite / Çözünürlük")
        self.lbl_qual.setObjectName("FieldLabel")
        self.lbl_aud = QLabel("Ses / Tür")
        self.lbl_aud.setObjectName("FieldLabel")

        self.format_combo = QComboBox()
        self.quality_combo = QComboBox()
        self.audio_combo = QComboBox()

        for fmt in VIDEO_FORMATS:
            self.format_combo.addItem(fmt, fmt)
        for q_label, q_height in VIDEO_QUALITIES:
            self.quality_combo.addItem(q_label, q_height)
        for a_label, a_code in AUDIO_MODES:
            self.audio_combo.addItem(a_label, a_code)

        self.opts_grid.addWidget(self.lbl_fmt, 0, 0)
        self.opts_grid.addWidget(self.lbl_qual, 0, 1)
        self.opts_grid.addWidget(self.lbl_aud, 0, 2)
        self.opts_grid.addWidget(self.format_combo, 1, 0)
        self.opts_grid.addWidget(self.quality_combo, 1, 1)
        self.opts_grid.addWidget(self.audio_combo, 1, 2)
        self.opts_grid.setColumnStretch(0, 1)
        self.opts_grid.setColumnStretch(1, 1)
        self.opts_grid.setColumnStretch(2, 1)
        pv_root.addLayout(self.opts_grid)

        self.premiere_panel = QFrame()
        self.premiere_panel.setObjectName("SubtlePanel")
        pr_layout = QHBoxLayout(self.premiere_panel)
        pr_layout.setContentsMargins(12, 10, 12, 10)
        pr_layout.setSpacing(10)

        pr_icon = QLabel()
        pr_icon.setPixmap(get_pixmap("film", self._palette.accent, 16))

        pr_texts = QVBoxLayout()
        pr_texts.setSpacing(2)
        pr_title = QLabel("Premiere Pro için optimize et")
        pr_title.setStyleSheet("font-size: 12px; font-weight: 600;")
        pr_desc = QLabel("Kurgu yazılımlarında sorunsuz açılması için H.264 video, AAC ses ve YUV420p MP4 çıktısı üretir.")
        pr_desc.setObjectName("MutedText")
        pr_texts.addWidget(pr_title)
        pr_texts.addWidget(pr_desc)

        self.premiere_toggle = ToggleSwitch(checked=False, palette=self._palette)

        pr_layout.addWidget(pr_icon)
        pr_layout.addLayout(pr_texts, 1)
        pr_layout.addWidget(self.premiere_toggle)
        pv_root.addWidget(self.premiere_panel)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.target_folder_lbl = QLabel()
        self.target_folder_lbl.setObjectName("MutedText")
        action_row.addWidget(self.target_folder_lbl, 1)

        self.download_btn = QPushButton("İndirmeyi Başlat")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setIcon(get_icon("download", "#FFFFFF", 15))
        self.download_btn.setIconSize(QSize(15, 15))
        self.download_btn.setMinimumHeight(34)
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.clicked.connect(self._emit_download)
        action_row.addWidget(self.download_btn)

        pv_root.addLayout(action_row)
        c_layout.addWidget(self.preview_card)

        self.platforms_hint_panel = QFrame()
        self.platforms_hint_panel.setObjectName("SubtlePanel")
        ph_layout = QVBoxLayout(self.platforms_hint_panel)
        ph_layout.setContentsMargins(16, 14, 16, 14)
        ph_layout.setSpacing(8)

        ph_hdr = QLabel("Desteklenen Başlıca Platformlar")
        ph_hdr.setObjectName("FieldLabel")
        ph_sub = QLabel(
            "  ·  ".join(PRIORITY_PLATFORMS) + "  ve yüzlerce video / görsel / dump kaynağı"
        )
        ph_sub.setObjectName("MutedText")
        ph_sub.setWordWrap(True)

        ph_layout.addWidget(ph_hdr)
        ph_layout.addWidget(ph_sub)
        c_layout.addWidget(self.platforms_hint_panel)

        c_layout.addStretch(1)
        canvas_layout.addWidget(self.container)

    def _connect_signals(self) -> None:
        self.url_input.textChanged.connect(self._on_text_changed)
        self.url_input.returnPressed.connect(self._on_return_pressed)

        self.audio_combo.currentIndexChanged.connect(self._sync_option_states)
        self.premiere_toggle.toggled.connect(self._sync_option_states)

        self._meta_ctrl.loading_started.connect(self._on_meta_loading)
        self._meta_ctrl.metadata_ready.connect(self._on_meta_ready)
        self._meta_ctrl.metadata_error.connect(self._on_meta_error)

        self._settings.settings_changed.connect(self.apply_defaults_from_settings)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

    def eventFilter(self, watched, event) -> bool:
        if watched is self.url_input:
            from PySide6.QtCore import QEvent

            if event.type() == QEvent.Type.FocusIn:
                self.input_bar.setProperty("focused", "true")
                self.input_bar.style().unpolish(self.input_bar)
                self.input_bar.style().polish(self.input_bar)
            elif event.type() == QEvent.Type.FocusOut:
                self.input_bar.setProperty("focused", "false")
                self.input_bar.style().unpolish(self.input_bar)
                self.input_bar.style().polish(self.input_bar)
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event) -> None:
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        raw = ""
        if md.hasUrls():
            raw = "\n".join(u.toString() for u in md.urls() if u.isValid())
        elif md.hasText():
            raw = md.text()

        urls = extract_urls_from_text(raw)
        if len(urls) > 1:
            self.batch_urls_requested.emit(urls)
        elif len(urls) == 1:
            self.load_url(urls[0])
        event.acceptProposedAction()

    def _on_clipboard_changed(self) -> None:
        if not self._settings.data.clipboard_auto_detect:
            return
        text = (QApplication.clipboard().text() or "").strip()
        if not is_probable_media_url(text, strict_clipboard=True):
            return
        urls = extract_urls_from_text(text)
        if not urls:
            return
        url = urls[0]
        if url in (self.url_input.text().strip(), self._last_fetched_url, self._dismissed_clipboard_url):
            return

        fm = self.cb_text.fontMetrics()
        short = fm.elidedText(f"Panoda bağlantı algılandı: {url}", Qt.TextElideMode.ElideRight, 480)
        self.cb_text.setText(short)
        self.clipboard_banner.setProperty("detected_url", url)
        self.clipboard_banner.show()

    def _apply_detected_clipboard_url(self) -> None:
        url = str(self.clipboard_banner.property("detected_url") or "")
        self.clipboard_banner.hide()
        if url:
            self.load_url(url)

    def _dismiss_clipboard_banner(self) -> None:
        self._dismissed_clipboard_url = str(self.clipboard_banner.property("detected_url") or "")
        self.clipboard_banner.hide()

    def _paste_from_clipboard(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if not text:
            return
        urls = extract_urls_from_text(text)
        if len(urls) > 1:
            self.batch_urls_requested.emit(urls)
            return
        target = urls[0] if urls else text
        self.load_url(target)

    def load_url(self, url: str) -> None:
        clean = url.strip()
        self.clipboard_banner.hide()
        self.url_input.setText(clean)
        self._trigger_fetch(force=True)

    def _clear_url(self) -> None:
        self._debounce_timer.stop()
        self._meta_ctrl.invalidate_pending()
        self.url_input.clear()
        self._current_meta = None
        self._last_fetched_url = ""
        self.loading_card.hide()
        self.error_card.hide()
        self.preview_card.hide()
        self.platforms_hint_panel.show()

    def _on_text_changed(self, text: str) -> None:
        has_text = bool(text.strip())
        self.clear_btn.setVisible(has_text)
        if not has_text:
            self._clear_url()
            return
        if is_probable_media_url(text, strict_clipboard=False):
            self._debounce_timer.start()

    def _on_return_pressed(self) -> None:
        ready = (
            self._current_meta is not None
            and self.preview_card.isVisible()
            and self.url_input.text().strip() == self._last_fetched_url
        )
        if ready:
            self._emit_download()
        else:
            self._trigger_fetch(force=True)

    def reset(self) -> None:
        self._clear_url()
        self.url_input.setFocus()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.url_input.setFocus()

    def _auto_analyze_current_text(self) -> None:
        self._trigger_fetch(force=False)

    def _trigger_fetch(self, force: bool = False) -> None:
        self._debounce_timer.stop()
        raw = self.url_input.text().strip()
        urls = extract_urls_from_text(raw)
        if len(urls) > 1:
            self.batch_urls_requested.emit(urls)
            self._clear_url()
            return

        target = urls[0] if urls else raw
        if not target:
            return
        if not force and target == self._last_fetched_url and self._current_meta is not None:
            return

        self._last_fetched_url = target
        self._meta_ctrl.fetch(target)

    def _on_meta_loading(self, url: str) -> None:
        self.error_card.hide()
        self.preview_card.hide()
        self.platforms_hint_panel.hide()
        self.loading_card.show()

    def _on_meta_error(self, message: str) -> None:
        self.loading_card.hide()
        self.preview_card.hide()
        self.platforms_hint_panel.hide()
        self.err_lbl.setText(message)
        self.error_card.show()

    def _on_meta_ready(self, meta: VideoMetadata) -> None:
        self._current_meta = meta
        self.loading_card.hide()
        self.error_card.hide()
        self.platforms_hint_panel.hide()

        is_gallery = meta.is_gallery and len(meta.gallery_items) > 1
        is_img = meta.media_type == "image"

        self.preview_thumb.set_thumbnail(meta.thumbnail_path, is_audio=not meta.has_video and not is_img and not is_gallery)
        self.preview_thumb.set_badge("" if (is_img or is_gallery) else (format_duration(meta.duration) if meta.duration > 0 else ""))

        self.platform_badge.set_platform(meta.platform, meta.platform_color)

        if is_gallery:
            self.max_res_lbl.setText(f"{len(meta.gallery_items)} Medya (Dump)")
            self.max_res_lbl.show()
            self.download_btn.setText(f"Medyaları Seç ve İndir ({len(meta.gallery_items)})")
            self.premiere_panel.hide()
        elif is_img:
            dim_txt = f"{meta.image_width}x{meta.image_height}" if (meta.image_width and meta.image_height) else "Görsel"
            self.max_res_lbl.setText(dim_txt)
            self.max_res_lbl.show()
            self.download_btn.setText("Görseli İndir")
            self.premiere_panel.hide()
        elif meta.max_height > 0:
            self.max_res_lbl.setText(f"Maks. {meta.max_height}p")
            self.max_res_lbl.show()
            self.download_btn.setText("İndirmeyi Başlat")
            self.premiere_panel.show()
        elif not meta.has_video:
            self.max_res_lbl.setText("Yalnızca Ses")
            self.max_res_lbl.show()
            self.download_btn.setText("İndirmeyi Başlat")
            self.premiere_panel.hide()
        else:
            self.max_res_lbl.hide()
            self.download_btn.setText("İndirmeyi Başlat")
            self.premiere_panel.show()

        self.video_title_lbl.setText(meta.title)
        self.channel_lbl.setText(f"Kaynak: {meta.uploader}")
        if is_gallery:
            self.duration_lbl.setText(f"Çoklu Paylaşım / Dump: {len(meta.gallery_items)} adet görsel ve video içeriyor")
        elif is_img:
            self.duration_lbl.setText("Tür: Görsel Dosyası")
        else:
            dur_txt = "Canlı Yayın" if meta.is_live else (format_duration(meta.duration) if meta.duration > 0 else "Bilinmiyor")
            self.duration_lbl.setText(f"Süre: {dur_txt}")

        self._populate_formats_for_meta(meta)
        self._apply_available_qualities(meta)
        self._sync_option_states()
        self.preview_card.show()

    def _populate_formats_for_meta(self, meta: VideoMetadata) -> None:
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        if meta.media_type == "image":
            for fmt in IMAGE_FORMATS:
                self.format_combo.addItem(fmt, fmt)
            self.lbl_fmt.setText("Görsel Formatı")
        else:
            for fmt in VIDEO_FORMATS:
                self.format_combo.addItem(fmt, fmt)
            self.lbl_fmt.setText("Video Formatı")
            fmt_idx = self.format_combo.findData(self._settings.data.default_format)
            if fmt_idx >= 0:
                self.format_combo.setCurrentIndex(fmt_idx)
        self.format_combo.blockSignals(False)

    def _apply_available_qualities(self, meta: VideoMetadata) -> None:
        model = self.quality_combo.model()
        assert isinstance(model, QStandardItemModel)

        is_gallery = meta.is_gallery and len(meta.gallery_items) > 1
        is_img = meta.media_type == "image" or is_gallery
        if is_img:
            for idx in range(model.rowCount()):
                item = model.item(idx)
                if item:
                    item.setEnabled(False)
            it0 = model.item(0)
            if it0:
                it0.setText("Orijinal Çözünürlük")
                it0.setEnabled(True)
            self.quality_combo.setCurrentIndex(0)
            return

        it0 = model.item(0)
        if it0:
            it0.setText("En iyi kalite")

        known_heights = meta.available_heights
        for idx, (base_label, height) in enumerate(VIDEO_QUALITIES):
            item = model.item(idx)
            if item is None:
                continue

            if height is None:
                supported = meta.has_video
            else:
                supported = meta.has_video and (height in known_heights)

            item.setEnabled(supported)
            if supported:
                item.setText(base_label)
                item.setForeground(QColor(self._palette.text_primary))
            else:
                item.setText(f"{base_label}  (Mevcut değil)")
                item.setForeground(QColor(self._palette.text_muted))

        preferred_label = self._settings.data.default_quality
        chosen_idx = 0
        for idx, (base_label, _) in enumerate(VIDEO_QUALITIES):
            it = model.item(idx)
            if base_label == preferred_label and it and it.isEnabled():
                chosen_idx = idx
                break
        self.quality_combo.setCurrentIndex(chosen_idx)

        if not meta.has_video and self.audio_combo.currentData() == "video":
            self.audio_combo.setCurrentIndex(1)

    def _sync_option_states(self) -> None:
        if self._current_meta and (self._current_meta.is_gallery or self._current_meta.media_type == "image"):
            self.quality_combo.setEnabled(False)
            self.audio_combo.setEnabled(False)
            self.premiere_toggle.setEnabled(False)
            self.format_combo.setEnabled(not self._current_meta.is_gallery)
            return

        audio_mode = str(self.audio_combo.currentData() or "video")
        is_video_mode = audio_mode == "video" and (self._current_meta is None or self._current_meta.has_video)
        premiere_on = self.premiere_toggle.isChecked()

        self.quality_combo.setEnabled(is_video_mode)
        self.audio_combo.setEnabled(True)
        self.premiere_toggle.setEnabled(is_video_mode)

        if not is_video_mode:
            self.format_combo.setEnabled(False)
        elif premiere_on:
            mp4_idx = self.format_combo.findData("MP4")
            if mp4_idx >= 0:
                self.format_combo.setCurrentIndex(mp4_idx)
            self.format_combo.setEnabled(False)
        else:
            self.format_combo.setEnabled(True)

    def apply_defaults_from_settings(self) -> None:
        if self._current_meta is None or (self._current_meta.media_type != "image" and not self._current_meta.is_gallery):
            fmt_idx = self.format_combo.findData(self._settings.data.default_format)
            if fmt_idx >= 0 and self.format_combo.isEnabled():
                self.format_combo.setCurrentIndex(fmt_idx)

            if self._current_meta is None:
                for idx, (label, _) in enumerate(VIDEO_QUALITIES):
                    if label == self._settings.data.default_quality:
                        self.quality_combo.setCurrentIndex(idx)
                        break

            self.premiere_toggle.setChecked(self._settings.data.premiere_optimize_default, emit_signal=False)

        self.target_folder_lbl.setText(f"Kayıt konumu: {self._settings.data.download_dir}")
        self._sync_option_states()

    def _emit_download(self) -> None:
        if not self._current_meta:
            return

        if self._current_meta.is_gallery and len(self._current_meta.gallery_items) > 1:
            dlg = GalleryDialog(self._current_meta.gallery_items, self._current_meta, self._palette, self)
            if dlg.exec():
                selected = dlg.get_selected_items()
                chosen_fmt = dlg.get_chosen_format()
                if selected:
                    self.gallery_download_requested.emit(selected, chosen_fmt)
                    self.reset()
            return

        if self._current_meta.media_type == "image":
            options = DownloadOptions(
                video_format=str(self.format_combo.currentData() or "Orijinal"),
                quality_label="Görsel",
                target_height=self._current_meta.image_height or None,
                audio_mode="image",
                premiere_optimize=False,
            )
        else:
            q_idx = self.quality_combo.currentIndex()
            q_label, q_height = VIDEO_QUALITIES[q_idx] if 0 <= q_idx < len(VIDEO_QUALITIES) else ("En iyi kalite", None)

            options = DownloadOptions(
                video_format=str(self.format_combo.currentData() or "MP4"),
                quality_label=q_label,
                target_height=q_height,
                audio_mode=str(self.audio_combo.currentData() or "video"),
                premiere_optimize=self.premiere_toggle.isChecked(),
            )
        self.download_requested.emit(self._current_meta, options)

    def _open_batch_dialog(self) -> None:
        dlg = BatchUrlDialog(self)
        if dlg.exec() and dlg.urls:
            self.batch_urls_requested.emit(dlg.urls)

    def set_palette_theme(self, palette: ThemePalette) -> None:
        self._palette = palette
        self.preview_thumb.set_palette_theme(palette)
        self.premiere_toggle.set_palette_theme(palette)
        self.link_icon_lbl.setPixmap(get_pixmap("link", palette.text_secondary, 17))
        self.cb_icon.setPixmap(get_pixmap("link", palette.accent, 15))
        self.loading_icon.setPixmap(get_pixmap("refresh", palette.accent, 16))
        self.err_icon.setPixmap(get_pixmap("alert", palette.danger, 18))
        self.batch_btn.setIcon(get_icon("layers", palette.text_primary, 14))
        self.paste_btn.setIcon(get_icon("paste", palette.text_primary, 14))
        if self._current_meta:
            self._apply_available_qualities(self._current_meta)
