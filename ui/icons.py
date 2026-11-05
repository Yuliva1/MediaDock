
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from config.paths import ICONS_DIR, is_frozen

SVG_TEMPLATES: dict[str, str] = {
    "logo": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">
        <rect x="2.5" y="2.5" width="19" height="19" rx="5" stroke="{color}" stroke-width="1.8"/>
        <path d="M9.5 8.5L16 12L9.5 15.5V8.5Z" fill="{color}"/>
        <path d="M7 18H17" stroke="{color}" stroke-width="1.6" stroke-linecap="round" opacity="0.65"/>
    </svg>""",
    "home": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 10.5L12 3l9 7.5"/>
        <path d="M5 9.5V19a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V9.5"/>
        <path d="M9.5 20.5v-6h5v6"/>
    </svg>""",
    "download": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 4v11"/>
        <path d="M7.5 11L12 15.5 16.5 11"/>
        <path d="M4 19.5h16"/>
    </svg>""",
    "library": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="4" width="18" height="16" rx="2.5"/>
        <path d="M7.5 4v16"/>
        <path d="M3 9.5h4.5"/>
        <path d="M3 14.5h4.5"/>
        <polygon points="12,9.5 16.5,12 12,14.5" fill="{color}" stroke="none"/>
    </svg>""",
    "heart": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20.4 5.6a5 5 0 0 0-7.07 0L12 6.93l-1.33-1.33a5 5 0 0 0-7.07 7.07l1.33 1.33L12 21l7.07-7 1.33-1.33a5 5 0 0 0 0-7.07z"/>
    </svg>""",
    "heart_filled": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20.4 5.6a5 5 0 0 0-7.07 0L12 6.93l-1.33-1.33a5 5 0 0 0-7.07 7.07l1.33 1.33L12 21l7.07-7 1.33-1.33a5 5 0 0 0 0-7.07z"/>
    </svg>""",
    "history": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8"/>
        <path d="M3 3v5h5"/>
        <path d="M12 7v5l3.2 2"/>
    </svg>""",
    "settings": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.08a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.08a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.08a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
    </svg>""",
    "link": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
    </svg>""",
    "paste": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="2.5" width="6" height="4" rx="1"/>
        <path d="M9 4.5H6.5A1.5 1.5 0 0 0 5 6v13.5A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H15"/>
    </svg>""",
    "search": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="11" cy="11" r="7"/>
        <path d="M20 20l-3.8-3.8"/>
    </svg>""",
    "close": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 6L6 18"/>
        <path d="M6 6l12 12"/>
    </svg>""",
    "play": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="7,5 19,12 7,19"/>
    </svg>""",
    "pause": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="{color}" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="6.5" y="5" width="3.5" height="14" rx="1"/>
        <rect x="14" y="5" width="3.5" height="14" rx="1"/>
    </svg>""",
    "refresh": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 0 1-15.4 6.36L3 16"/>
        <path d="M3 21v-5h5"/>
        <path d="M3 12a9 9 0 0 1 15.4-6.36L21 8"/>
        <path d="M21 3v5h-5"/>
    </svg>""",
    "folder": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.2l2 2.2h8.8A1.5 1.5 0 0 1 21 8.7v9.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5V6.5z"/>
    </svg>""",
    "copy": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="9" width="11" height="11" rx="2"/>
        <path d="M5 15H4a1.5 1.5 0 0 1-1.5-1.5V4A1.5 1.5 0 0 1 4 2.5h9.5A1.5 1.5 0 0 1 15 4v1"/>
    </svg>""",
    "trash": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 7h16"/>
        <path d="M9.5 7V4.5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1V7"/>
        <path d="M6.5 7l.8 12a1.5 1.5 0 0 0 1.5 1.4h6.4a1.5 1.5 0 0 0 1.5-1.4l.8-12"/>
        <path d="M10 11v5.5"/>
        <path d="M14 11v5.5"/>
    </svg>""",
    "grid": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/>
        <rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/>
        <rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/>
        <rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>
    </svg>""",
    "list": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 6h12"/>
        <path d="M8 12h12"/>
        <path d="M8 18h12"/>
        <circle cx="4.2" cy="6" r="1" fill="{color}"/>
        <circle cx="4.2" cy="12" r="1" fill="{color}"/>
        <circle cx="4.2" cy="18" r="1" fill="{color}"/>
    </svg>""",
    "plus": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 5v14"/>
        <path d="M5 12h14"/>
    </svg>""",
    "layers": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12,3 2,8 12,13 22,8"/>
        <path d="M2 13l10 5 10-5"/>
        <path d="M2 18l10 5 10-5"/>
    </svg>""",
    "check": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 6L9 17l-5-5"/>
    </svg>""",
    "alert": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="9"/>
        <path d="M12 8v4.5"/>
        <circle cx="12" cy="16" r="0.6" fill="{color}"/>
    </svg>""",
    "film": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2.5" y="4" width="19" height="16" rx="2.5"/>
        <path d="M7 4v16"/>
        <path d="M17 4v16"/>
        <path d="M2.5 12h19"/>
    </svg>""",
    "music": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18V5l12-2v13"/>
        <circle cx="6" cy="18" r="3"/>
        <circle cx="18" cy="16" r="3"/>
    </svg>""",
    "sparkles": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z"/>
        <path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15z"/>
    </svg>""",
    "chevron_down": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 9l6 6 6-6"/>
    </svg>""",
    "external": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 4h6v6"/>
        <path d="M10 14L20 4"/>
        <path d="M18 13v5.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H11"/>
    </svg>""",
}


def export_svg_assets(default_color: str = "#F0F0F2") -> Path:
    target_dir = ICONS_DIR
    if not is_frozen():
        target_dir.mkdir(parents=True, exist_ok=True)
        for name, svg in SVG_TEMPLATES.items():
            color = "#929298" if name == "chevron_down" else default_color
            out_file = target_dir / f"{name}.svg"
            if not out_file.exists():
                out_file.write_text(svg.format(color=color), encoding="utf-8")
    chevron_path = target_dir / "chevron_down.svg"
    if not chevron_path.exists():
        from config.paths import DATA_DIR

        fallback_chevron = DATA_DIR / "chevron_down.svg"
        fallback_chevron.parent.mkdir(parents=True, exist_ok=True)
        fallback_chevron.write_text(
            SVG_TEMPLATES["chevron_down"].format(color="#929298"),
            encoding="utf-8",
        )
        return fallback_chevron
    return chevron_path


@lru_cache(maxsize=256)
def get_pixmap(name: str, color: str = "#F0F0F2", size: int = 18) -> QPixmap:
    template = SVG_TEMPLATES.get(name, SVG_TEMPLATES["link"])
    svg_bytes = QByteArray(template.format(color=color).encode("utf-8"))
    renderer = QSvgRenderer(svg_bytes)

    scale = 2
    px_size = size * scale
    image = QImage(px_size, px_size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0, 0, px_size, px_size))
    painter.end()

    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(float(scale))
    return pixmap


@lru_cache(maxsize=256)
def get_icon(name: str, color: str = "#F0F0F2", size: int = 18) -> QIcon:
    return QIcon(get_pixmap(name, color, size))
