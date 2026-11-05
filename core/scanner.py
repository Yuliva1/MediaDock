
from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests
from PySide6.QtCore import QObject, QThread, Signal

from config.constants import SUPPORTED_AUDIO_EXTENSIONS, SUPPORTED_MEDIA_EXTENSIONS
from config.paths import THUMBNAILS_DIR, is_frozen
from core.database import DatabaseManager
from core.ffmpeg import FFmpegManager, _subprocess_flags


class _FolderScanWorker(QObject):
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, folder: str, db: DatabaseManager, ffmpeg_mgr: FFmpegManager) -> None:
        super().__init__()
        self.folder = Path(folder)
        self.db = db
        self.ffmpeg_mgr = ffmpeg_mgr

    def run(self) -> None:
        try:
            if not self.folder.is_dir():
                self.finished.emit(0)
                return

            known_paths = self.db.get_known_file_paths()
            added_count = 0

            for entry in sorted(self.folder.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if not entry.is_file():
                    continue
                lower_name = entry.name.lower()
                if lower_name.endswith((".part", ".ytdl", ".premiere_tmp.mp4")) or ".part-" in lower_name:
                    continue
                if entry.suffix.lower() not in SUPPORTED_MEDIA_EXTENSIONS:
                    continue

                resolved_str = str(entry.resolve())
                if resolved_str in known_paths:
                    continue

                stat = entry.stat()
                if stat.st_size == 0:
                    continue

                probe = self.ffmpeg_mgr.probe_media(entry)
                is_audio = entry.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
                fmt_name = entry.suffix.lstrip(".").upper()
                res_label = f"Ses ({fmt_name})" if is_audio else (probe.resolution_label or fmt_name)

                thumb_path = ""
                if not is_audio and self.ffmpeg_mgr.is_available:
                    digest = hashlib.sha1(resolved_str.encode("utf-8", errors="ignore")).hexdigest()[:14]
                    out_thumb = THUMBNAILS_DIR / f"scan_{digest}.jpg"
                    if out_thumb.is_file() or self.ffmpeg_mgr.extract_thumbnail(entry, out_thumb, probe.duration):
                        thumb_path = str(out_thumb)

                mtime_iso = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                self.db.upsert_media_item(
                    title=entry.stem,
                    file_name=entry.name,
                    file_path=resolved_str,
                    source_url="",
                    platform="Yerel Medya",
                    uploader="",
                    duration=probe.duration,
                    resolution=res_label,
                    format_name=fmt_name,
                    video_codec=probe.video_codec,
                    audio_codec=probe.audio_codec,
                    file_size=stat.st_size,
                    thumbnail_path=thumb_path,
                    premiere_ready=probe.is_premiere_mp4_ready or is_audio,
                    downloaded_at=mtime_iso,
                )
                added_count += 1

            self.finished.emit(added_count)
        except Exception as exc:
            self.error.emit(str(exc))


class LibraryScanner(QObject):

    scan_started = Signal()
    scan_completed = Signal(int)
    scan_failed = Signal(str)

    def __init__(self, db: DatabaseManager, ffmpeg_mgr: FFmpegManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._ffmpeg = ffmpeg_mgr
        self._thread: QThread | None = None
        self._worker: _FolderScanWorker | None = None

    def scan(self, folder: str) -> None:
        if self._thread is not None and self._thread.isRunning():
            return

        self.scan_started.emit()
        thread = QThread()
        worker = _FolderScanWorker(folder, self._db, self._ffmpeg)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self.scan_completed.emit)
        worker.error.connect(self.scan_failed.emit)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)

        def cleanup() -> None:
            self._worker = None
            self._thread = None
            worker.deleteLater()
            thread.deleteLater()

        thread.finished.connect(cleanup)
        self._thread = thread
        self._worker = worker
        thread.start()


class _YtDlpUpdateWorker(QObject):
    finished = Signal(bool, str, str)

    def __init__(self, do_upgrade: bool = False) -> None:
        super().__init__()
        self.do_upgrade = do_upgrade

    def run(self) -> None:
        current_ver = "Bilinmiyor"
        try:
            import importlib
            import yt_dlp.version

            importlib.reload(yt_dlp.version)
            current_ver = yt_dlp.version.__version__
        except Exception:
            pass

        if self.do_upgrade:
            if is_frozen():
                self.finished.emit(
                    False,
                    current_ver,
                    "Paketlenmiş (.exe) sürümde motor güncellemesi uygulama sürümüyle birlikte yapılır.",
                )
                return
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=90,
                    creationflags=_subprocess_flags(),
                )
                if proc.returncode == 0:
                    import importlib
                    import yt_dlp.version

                    importlib.reload(yt_dlp.version)
                    new_ver = yt_dlp.version.__version__
                    self.finished.emit(True, new_ver, f"yt-dlp başarıyla güncellendi ({new_ver}).")
                else:
                    self.finished.emit(False, current_ver, "Güncelleme sırasında pip hatası oluştu.")
            except Exception as exc:
                self.finished.emit(False, current_ver, f"Güncelleme başarısız: {exc}")
            return

        try:
            resp = requests.get("https://pypi.org/pypi/yt-dlp/json", timeout=8)
            if resp.status_code == 200:
                latest = str(resp.json().get("info", {}).get("version") or "").strip()
                if latest and latest != current_ver:
                    self.finished.emit(
                        True,
                        current_ver,
                        f"Yeni sürüm mevcut: {latest} (Mevcut: {current_ver})",
                    )
                else:
                    self.finished.emit(False, current_ver, f"yt-dlp güncel ({current_ver}).")
            else:
                self.finished.emit(False, current_ver, f"Sürüm sunucusuna ulaşılamadı (Mevcut: {current_ver}).")
        except Exception:
            self.finished.emit(False, current_ver, f"Bağlantı kurulamadı (Mevcut: {current_ver}).")


class YtDlpUpdater(QObject):

    status_ready = Signal(bool, str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: _YtDlpUpdateWorker | None = None

    def check_or_upgrade(self, do_upgrade: bool = False) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        thread = QThread()
        worker = _YtDlpUpdateWorker(do_upgrade=do_upgrade)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self.status_ready.emit)
        worker.finished.connect(thread.quit)

        def cleanup() -> None:
            self._worker = None
            self._thread = None
            worker.deleteLater()
            thread.deleteLater()

        thread.finished.connect(cleanup)
        self._thread = thread
        self._worker = worker
        thread.start()
