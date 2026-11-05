
from __future__ import annotations

from PySide6.QtWidgets import QWidget

from config.settings import SettingsManager
from config.theme import ThemePalette
from core.database import DatabaseManager
from ui.library_page import LibraryPage


class FavoritesPage(LibraryPage):

    def __init__(
        self,
        db: DatabaseManager,
        settings: SettingsManager,
        palette: ThemePalette | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            db=db,
            settings=settings,
            scanner=None,
            palette=palette,
            favorites_only=True,
            parent=parent,
        )
