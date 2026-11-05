
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class ThemePalette:
    key: str
    name: str
    bg_app: str
    bg_sidebar: str
    bg_surface: str
    bg_surface_alt: str
    bg_elevated: str
    bg_hover: str
    bg_input: str
    border: str
    border_hover: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    success: str
    warning: str
    danger: str

THEMES: dict[str, ThemePalette] = {
    "linear_red": ThemePalette(
        key="linear_red",
        name="Linear Koyu (Kırmızı Vurgu)",
        bg_app="#111113",
        bg_sidebar="#171719",
        bg_surface="#18181B",
        bg_surface_alt="#151518",
        bg_elevated="#1F1F23",
        bg_hover="#222227",
        bg_input="#151518",
        border="#29292D",
        border_hover="#3A3A40",
        text_primary="#F0F0F2",
        text_secondary="#929298",
        text_muted="#5E5E66",
        accent="#E05B5B",
        accent_hover="#E86A6A",
        accent_pressed="#C94B4B",
        accent_soft="rgba(224, 91, 91, 0.14)",
        success="#3BA55D",
        warning="#E09F3E",
        danger="#E05B5B",
    ),
    "linear_violet": ThemePalette(
        key="linear_violet",
        name="Linear Koyu (Mor Vurgu)",
        bg_app="#111113",
        bg_sidebar="#171719",
        bg_surface="#18181B",
        bg_surface_alt="#151518",
        bg_elevated="#1F1F23",
        bg_hover="#222227",
        bg_input="#151518",
        border="#29292D",
        border_hover="#3A3A40",
        text_primary="#F0F0F2",
        text_secondary="#929298",
        text_muted="#5E5E66",
        accent="#7C66DC",
        accent_hover="#8D79E6",
        accent_pressed="#6952CA",
        accent_soft="rgba(124, 102, 220, 0.15)",
        success="#3BA55D",
        warning="#E09F3E",
        danger="#E05B5B",
    ),
    "linear_obsidian": ThemePalette(
        key="linear_obsidian",
        name="Obsidyen Siyah (Kırmızı Vurgu)",
        bg_app="#0B0B0D",
        bg_sidebar="#111114",
        bg_surface="#141418",
        bg_surface_alt="#101013",
        bg_elevated="#1A1A20",
        bg_hover="#1E1E25",
        bg_input="#111114",
        border="#242429",
        border_hover="#34343C",
        text_primary="#F0F0F2",
        text_secondary="#8E8E95",
        text_muted="#595962",
        accent="#E05B5B",
        accent_hover="#E86A6A",
        accent_pressed="#C94B4B",
        accent_soft="rgba(224, 91, 91, 0.14)",
        success="#3BA55D",
        warning="#E09F3E",
        danger="#E05B5B",
    ),
}

DEFAULT_THEME_KEY = "linear_red"

def get_theme(theme_key: str | None = None) -> ThemePalette:
    if theme_key and theme_key in THEMES:
        return THEMES[theme_key]
    return THEMES[DEFAULT_THEME_KEY]

def build_stylesheet(palette: ThemePalette, chevron_icon_path: str = "") -> str:
    chevron_rule = ""
    if chevron_icon_path:
        clean_path = chevron_icon_path.replace("\\", "/")
        chevron_rule = f'image: url("{clean_path}"); width: 14px; height: 14px;'

    return f"""
    QWidget {{
        background-color: transparent;
        color: {palette.text_primary};
        font-family: "Segoe UI Variable Text", "Inter", "Segoe UI", sans-serif;
        font-size: 13px;
        selection-background-color: {palette.accent};
        selection-color: #FFFFFF;
        outline: none;
    }}

    QMainWindow, QWidget#MainCentralWidget {{
        background-color: {palette.bg_app};
    }}

    QDialog {{
        background-color: {palette.bg_surface};
        border: 1px solid {palette.border};
    }}

    QToolTip {{
        background-color: {palette.bg_elevated};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 12px;
    }}

    QFrame#SurfaceCard {{
        background-color: {palette.bg_surface};
        border: 1px solid {palette.border};
        border-radius: 8px;
    }}

    QFrame#SurfaceCardHover:hover {{
        background-color: {palette.bg_elevated};
        border: 1px solid {palette.border_hover};
    }}

    QFrame#SubtlePanel {{
        background-color: {palette.bg_surface_alt};
        border: 1px solid {palette.border};
        border-radius: 8px;
    }}

    QFrame#HeroInputBar {{
        background-color: {palette.bg_surface};
        border: 1px solid {palette.border};
        border-radius: 8px;
    }}

    QFrame#HeroInputBar[focused="true"] {{
        border: 1px solid {palette.accent};
    }}

    QFrame#BannerCard {{
        background-color: {palette.bg_elevated};
        border: 1px solid {palette.border};
        border-radius: 8px;
    }}

    QFrame#Sidebar {{
        background-color: {palette.bg_sidebar};
        border-right: 1px solid {palette.border};
    }}

    QLabel#PageTitle {{
        color: {palette.text_primary};
        font-size: 20px;
        font-weight: 600;
    }}

    QLabel#PageSubtitle {{
        color: {palette.text_secondary};
        font-size: 13px;
        font-weight: 400;
    }}

    QLabel#SectionTitle {{
        color: {palette.text_primary};
        font-size: 14px;
        font-weight: 600;
    }}

    QLabel#FieldLabel {{
        color: {palette.text_secondary};
        font-size: 12px;
        font-weight: 500;
    }}

    QLabel#MutedText {{
        color: {palette.text_muted};
        font-size: 12px;
    }}

    QLabel#SecondaryText {{
        color: {palette.text_secondary};
        font-size: 12px;
    }}

    QPushButton#PrimaryButton {{
        background-color: {palette.accent};
        color: #FFFFFF;
        border: 1px solid {palette.accent};
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 13px;
        font-weight: 600;
        min-height: 20px;
    }}

    QPushButton#PrimaryButton:hover {{
        background-color: {palette.accent_hover};
        border-color: {palette.accent_hover};
    }}

    QPushButton#PrimaryButton:pressed {{
        background-color: {palette.accent_pressed};
        border-color: {palette.accent_pressed};
    }}

    QPushButton#PrimaryButton:disabled {{
        background-color: {palette.bg_elevated};
        color: {palette.text_muted};
        border-color: {palette.border};
    }}

    QPushButton#SecondaryButton {{
        background-color: {palette.bg_elevated};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: 6px;
        padding: 6px 12px;
        font-size: 12px;
        font-weight: 500;
        min-height: 20px;
    }}

    QPushButton#SecondaryButton:hover {{
        background-color: {palette.bg_hover};
        border-color: {palette.border_hover};
    }}

    QPushButton#SecondaryButton:pressed {{
        background-color: {palette.bg_surface_alt};
    }}

    QPushButton#SecondaryButton:disabled {{
        color: {palette.text_muted};
        background-color: {palette.bg_surface_alt};
        border-color: {palette.border};
    }}

    QPushButton#GhostButton {{
        background-color: transparent;
        color: {palette.text_secondary};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 12px;
        font-weight: 500;
    }}

    QPushButton#GhostButton:hover {{
        background-color: {palette.bg_hover};
        color: {palette.text_primary};
        border-color: {palette.border};
    }}

    QPushButton#GhostButton:checked {{
        background-color: {palette.bg_elevated};
        color: {palette.text_primary};
        border-color: {palette.border_hover};
    }}

    QPushButton#DangerGhostButton {{
        background-color: transparent;
        color: {palette.text_secondary};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 12px;
    }}

    QPushButton#DangerGhostButton:hover {{
        background-color: {palette.accent_soft};
        color: {palette.danger};
        border-color: {palette.danger};
    }}

    QPushButton#FilterPill {{
        background-color: transparent;
        color: {palette.text_secondary};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
        font-weight: 500;
    }}

    QPushButton#FilterPill:hover {{
        color: {palette.text_primary};
        background-color: {palette.bg_hover};
    }}

    QPushButton#FilterPill:checked {{
        background-color: {palette.bg_elevated};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
    }}

    QLineEdit {{
        background-color: {palette.bg_input};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: 6px;
        padding: 6px 10px;
        font-size: 13px;
        min-height: 20px;
    }}

    QLineEdit:hover {{
        border-color: {palette.border_hover};
    }}

    QLineEdit:focus {{
        border-color: {palette.accent};
    }}

    QLineEdit#BorderlessUrlInput {{
        background-color: transparent;
        border: none;
        padding: 8px 4px;
        font-size: 14px;
    }}

    QPlainTextEdit, QTextEdit {{
        background-color: {palette.bg_input};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: 6px;
        padding: 8px;
        font-size: 13px;
    }}

    QPlainTextEdit:focus, QTextEdit:focus {{
        border-color: {palette.accent};
    }}

    QComboBox {{
        background-color: {palette.bg_input};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: 6px;
        padding: 6px 28px 6px 10px;
        font-size: 13px;
        min-height: 20px;
    }}

    QComboBox:hover {{
        border-color: {palette.border_hover};
    }}

    QComboBox:focus, QComboBox:on {{
        border-color: {palette.accent};
    }}

    QComboBox:disabled {{
        background-color: {palette.bg_surface_alt};
        color: {palette.text_muted};
        border-color: {palette.border};
    }}

    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 26px;
        border: none;
        background: transparent;
    }}

    QComboBox::down-arrow {{
        {chevron_rule}
    }}

    QComboBox QAbstractItemView {{
        background-color: {palette.bg_elevated};
        color: {palette.text_primary};
        border: 1px solid {palette.border_hover};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {palette.bg_hover};
        selection-color: {palette.text_primary};
        outline: none;
    }}

    QComboBox QAbstractItemView::item {{
        min-height: 28px;
        padding: 4px 8px;
        border-radius: 4px;
    }}

    QSpinBox {{
        background-color: {palette.bg_input};
        color: {palette.text_primary};
        border: 1px solid {palette.border};
        border-radius: 6px;
        padding: 5px 8px;
        min-height: 20px;
    }}

    QSpinBox:hover {{
        border-color: {palette.border_hover};
    }}

    QSpinBox:focus {{
        border-color: {palette.accent};
    }}

    QScrollArea {{
        border: none;
        background-color: transparent;
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 2px 1px 2px 1px;
    }}

    QScrollBar::handle:vertical {{
        background: {palette.border};
        min-height: 28px;
        border-radius: 3px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {palette.border_hover};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 1px 2px 1px 2px;
    }}

    QScrollBar::handle:horizontal {{
        background: {palette.border};
        min-width: 28px;
        border-radius: 3px;
    }}

    QScrollBar::handle:horizontal:hover {{
        background: {palette.border_hover};
    }}

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
        width: 0px;
    }}

    QFrame#Divider {{
        background-color: {palette.border};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}

    QMenu {{
        background-color: {palette.bg_elevated};
        color: {palette.text_primary};
        border: 1px solid {palette.border_hover};
        border-radius: 8px;
        padding: 4px;
    }}

    QMenu::item {{
        padding: 6px 20px 6px 12px;
        border-radius: 4px;
        font-size: 12px;
    }}

    QMenu::item:selected {{
        background-color: {palette.bg_hover};
        color: {palette.text_primary};
    }}

    QMenu::separator {{
        height: 1px;
        background: {palette.border};
        margin: 4px 6px;
    }}
    """
