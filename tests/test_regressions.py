"""Daha önce sahada patlamış hataların geri gelmesini önleyen testler."""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = ("core", "ui", "config")


def _py_files():
    for d in SOURCE_DIRS:
        yield from (ROOT / d).rglob("*.py")
    yield ROOT / "main.py"


def test_downloader_only_calls_existing_ffmpeg_methods():
    # v1.1.4: downloader var olmayan convert_for_premiere() metodunu çağırıyordu.
    from core.ffmpeg import FFmpegManager

    tree = ast.parse((ROOT / "core" / "downloader.py").read_text(encoding="utf-8"))
    used: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr in ("ffmpeg_mgr", "_ffmpeg")
        ):
            used.add(node.attr)
    assert used, "downloader içinde FFmpegManager kullanımı bulunamadı"
    missing = sorted(a for a in used if not hasattr(FFmpegManager, a))
    assert not missing, f"FFmpegManager'da olmayan öznitelikler: {missing}"


def test_every_setting_is_used_somewhere():
    # v1.1.4: auto_check_updates tanımlıydı ama hiçbir yerde okunmuyordu.
    from config.settings import AppSettingsData

    corpus = "\n".join(
        p.read_text(encoding="utf-8") for p in _py_files() if p.name != "settings.py"
    )
    unused = [f.name for f in fields(AppSettingsData) if f.name not in corpus]
    assert not unused, f"Hiçbir yerde kullanılmayan ayarlar: {unused}"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_update_dialog_progress_bar_paints(qapp):
    # v1.1.4: SmoothProgressBar'a tema yerine QFrame veriliyordu; her karede AttributeError.
    from config.theme import ThemePalette
    from core.updater import UpdateInfo
    from ui.widgets.update_dialog import UpdateDialog

    info = UpdateInfo(current_version="1.0.0", latest_version="9.9.9", has_update=True)
    dlg = UpdateDialog(info, allow_skip=True)
    assert isinstance(dlg.progress_bar._palette, ThemePalette)
    dlg.progress_panel.show()
    dlg.progress_bar.set_value(42.0)
    dlg.progress_bar.resize(300, 6)
    dlg.progress_bar.grab()  # paintEvent çalışır; hata olursa test düşer
    dlg.deleteLater()


def test_update_dialog_close_cancels_pending_apply(qapp, monkeypatch):
    # İndirme bitince güncelleme kısa gecikmeyle uygulanır; "Kapat" bunu iptal etmeli.
    from core.updater import UpdateInfo
    from ui.widgets import update_dialog as ud

    applied: list[str] = []
    monkeypatch.setattr(ud, "finalize_update", lambda p: applied.append(p))
    info = UpdateInfo(current_version="1.0.0", latest_version="9.9.9", has_update=True)
    dlg = ud.UpdateDialog(info)
    dlg.show()
    dlg._on_finished("C:/fake/path")
    assert dlg._apply_timer.isActive()
    dlg._on_later_clicked()
    assert not dlg._apply_timer.isActive()
    dlg._apply_pending()  # zamanlayıcı yine de tetiklense bile uygulanmamalı
    assert applied == []
    dlg.deleteLater()


def test_update_dialog_skip_emits_version(qapp):
    from core.updater import UpdateInfo
    from ui.widgets.update_dialog import UpdateDialog

    info = UpdateInfo(current_version="1.0.0", latest_version="2.3.4", has_update=True)
    dlg = UpdateDialog(info, allow_skip=True)
    got: list[str] = []
    dlg.skip_version_requested.connect(got.append)
    dlg._on_skip_clicked()
    assert got == ["2.3.4"]
    dlg.deleteLater()
