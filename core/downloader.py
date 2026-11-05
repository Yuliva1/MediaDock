from __future__ import annotations

import gc
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QObject, QThread, Signal

from config.constants import resolve_platform_info
from config.settings import SettingsManager
from core.database import DatabaseManager, now_iso
from core.extractor import extract
from core.ffmpeg import FFmpegCancelledError, FFmpegManager
from core.metadata import (
    GalleryItem,
    VideoMetadata,
    cache_thumbnail,
    fetch_video_metadata,
    sanitize_filename,
    translate_ytdlp_error,
)


class _TaskPausedException(Exception):
    pass


class _TaskCancelledException(Exception):
    pass


@dataclass
class DownloadOptions:
    video_format: str = "MP4"
    quality_label: str = "En iyi kalite"
    target_height: int | None = None
    audio_mode: str = "video"
    premiere_optimize: bool = False


@dataclass
class DownloadTask:
    task_id: str
    url: str
    title: str
    platform: str = "Web Medya"
    uploader: str = ""
    duration: float = 0.0
    thumbnail_path: str = ""
    thumbnail_url: str = ""
    video_format: str = "MP4"
    quality_label: str = "En iyi kalite"
    target_height: int | None = None
    audio_mode: str = "video"
    premiere_optimize: bool = False
    output_dir: str = ""
    file_stem: str = ""
    final_path: str = ""
    status: str = "queued"
    status_text: str = "Sırada bekliyor"
    progress: float = 0.0
    speed_bps: float = 0.0
    eta_seconds: int | None = None
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error_message: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "url": self.url,
            "title": self.title,
            "platform": self.platform,
            "uploader": self.uploader,
            "duration": self.duration,
            "thumbnail_path": self.thumbnail_path,
            "thumbnail_url": self.thumbnail_url,
            "video_format": self.video_format,
            "quality_label": self.quality_label,
            "target_height": self.target_height,
            "audio_mode": self.audio_mode,
            "premiere_optimize": self.premiere_optimize,
            "output_dir": self.output_dir,
            "file_stem": self.file_stem,
            "final_path": self.final_path,
            "status": self.status,
            "status_text": self.status_text,
            "progress": self.progress,
            "speed_bps": self.speed_bps,
            "eta_seconds": self.eta_seconds,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error_message": self.error_message,
            "created_at": self.created_at,
        }


def _unique_file_stem(directory: Path, base_stem: str, expected_ext: str) -> str:
    candidate = base_stem
    idx = 2
    while (directory / f"{candidate}.{expected_ext.lstrip('.')}").exists():
        candidate = f"{base_stem} ({idx})"
        idx += 1
    return candidate


class _DownloadWorker(QObject):

    progress_changed = Signal(str, dict)
    metadata_enriched = Signal(str, dict)
    completed = Signal(str, str)
    paused = Signal(str)
    cancelled = Signal(str)
    failed = Signal(str, str)

    def __init__(
        self,
        task_snapshot: dict[str, Any],
        ffmpeg_mgr: FFmpegManager,
        pause_event: threading.Event,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self.task = dict(task_snapshot)
        self.ffmpeg_mgr = ffmpeg_mgr
        self.pause_event = pause_event
        self.cancel_event = cancel_event
        self._last_emit_ts = 0.0
        self._final_filepath: str = ""

    def _check_interrupt(self) -> None:
        if self.cancel_event.is_set():
            raise _TaskCancelledException()
        if self.pause_event.is_set():
            raise _TaskPausedException()

    def _download_image_direct(self, task_id: str, url: str, out_dir: Path, file_stem: str, target_fmt: str) -> None:
        self.progress_changed.emit(
            task_id,
            {"status": "downloading", "status_text": "Görsel indiriliyor...", "progress": 10.0},
        )
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, stream=True, timeout=25, headers=headers)
        resp.raise_for_status()

        tot_bytes = int(resp.headers.get("Content-Length") or 0)
        dl_bytes = 0
        part_file = out_dir / f"{file_stem}.part_img"
        t0 = time.monotonic()

        with open(part_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                self._check_interrupt()
                if not chunk:
                    continue
                f.write(chunk)
                dl_bytes += len(chunk)
                now = time.monotonic()
                if now - self._last_emit_ts >= 0.08:
                    self._last_emit_ts = now
                    speed = dl_bytes / max(now - t0, 0.001)
                    pct = (dl_bytes / tot_bytes * 100.0) if tot_bytes > 0 else 50.0
                    self.progress_changed.emit(
                        task_id,
                        {
                            "status": "downloading",
                            "status_text": "Görsel indiriliyor",
                            "progress": min(95.0, pct),
                            "speed_bps": speed,
                            "downloaded_bytes": dl_bytes,
                            "total_bytes": tot_bytes or dl_bytes,
                        },
                    )

        from PIL import Image

        norm_target = target_fmt.upper()
        if norm_target == "PNG":
            dest = out_dir / f"{file_stem}.png"
            with Image.open(part_file) as im:
                im.save(dest, format="PNG")
            part_file.unlink(missing_ok=True)
        elif norm_target == "JPG":
            dest = out_dir / f"{file_stem}.jpg"
            with Image.open(part_file) as im:
                rgb = im.convert("RGB")
                rgb.save(dest, format="JPEG", quality=92, optimize=True)
            part_file.unlink(missing_ok=True)
        elif norm_target == "WEBP":
            dest = out_dir / f"{file_stem}.webp"
            with Image.open(part_file) as im:
                im.save(dest, format="WEBP", quality=90)
            part_file.unlink(missing_ok=True)
        else:
            orig_fmt = "JPEG"
            try:
                with Image.open(part_file) as im:
                    orig_fmt = (im.format or "JPEG").upper()
            except Exception:
                pass
            ext_map = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif", "BMP": "bmp"}
            final_ext = ext_map.get(orig_fmt, "jpg")
            dest = out_dir / f"{file_stem}.{final_ext}"
            if dest.exists():
                dest.unlink(missing_ok=True)
            part_file.replace(dest)

        gc.collect()

        self.progress_changed.emit(
            task_id,
            {
                "status": "downloading",
                "status_text": "Tamamlandı",
                "progress": 100.0,
                "speed_bps": 0.0,
                "eta_seconds": 0,
            },
        )
        self.completed.emit(task_id, str(dest))

    def run(self) -> None:
        task_id = self.task["task_id"]
        url = self.task["url"]
        out_dir = Path(self.task["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_loc = self.ffmpeg_mgr.get_ytdlp_ffmpeg_location()

        try:
            self._check_interrupt()

            if self.task.get("title") in ("", "Bağlantı hazırlanıyor...") or not self.task.get("file_stem"):
                self.progress_changed.emit(
                    task_id,
                    {"status": "downloading", "status_text": "Medya bilgileri alınıyor..."},
                )
                meta = fetch_video_metadata(url, ffmpeg_loc)
                if meta.media_type == "image":
                    self.task["audio_mode"] = "image"
                    expected_ext = "png" if self.task["video_format"] == "PNG" else ("jpg" if self.task["video_format"] == "JPG" else ("webp" if self.task["video_format"] == "WEBP" else "jpg"))
                else:
                    expected_ext = (
                        self.task["audio_mode"].lower()
                        if self.task["audio_mode"] != "video"
                        else self.task["video_format"].lower()
                    )
                stem = _unique_file_stem(out_dir, sanitize_filename(meta.title), expected_ext)
                meta_patch = {
                    "title": meta.title,
                    "platform": meta.platform,
                    "uploader": meta.uploader,
                    "duration": meta.duration,
                    "thumbnail_path": meta.thumbnail_path,
                    "thumbnail_url": meta.thumbnail_url,
                    "file_stem": stem,
                    "audio_mode": self.task["audio_mode"],
                }
                self.task.update(meta_patch)
                self.metadata_enriched.emit(task_id, meta_patch)

            self._check_interrupt()

            file_stem = self.task["file_stem"]
            audio_mode = self.task["audio_mode"]
            video_fmt = self.task["video_format"]

            if audio_mode == "image" or (video_fmt in ("PNG", "JPG", "WEBP", "Orijinal") and float(self.task.get("duration") or 0) == 0):
                self._download_image_direct(task_id, url, out_dir, file_stem, video_fmt)
                return

            video_fmt_lower = video_fmt.lower()
            target_h = self.task.get("target_height")
            premiere_opt = bool(self.task.get("premiere_optimize"))

            outtmpl = str(out_dir / f"{file_stem}.%(ext)s")

            def progress_hook(d: dict[str, Any]) -> None:
                self._check_interrupt()
                st = d.get("status")
                now = time.monotonic()
                if st == "downloading":
                    if now - self._last_emit_ts < 0.12:
                        return
                    self._last_emit_ts = now
                    dl_bytes = int(d.get("downloaded_bytes") or 0)
                    tot_bytes = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
                    speed = float(d.get("speed") or 0.0)
                    eta = d.get("eta")
                    pct = (dl_bytes / tot_bytes * 100.0) if tot_bytes > 0 else 0.0
                    pct = min(99.0, max(0.0, pct))
                    self.progress_changed.emit(
                        task_id,
                        {
                            "status": "downloading",
                            "status_text": "İndiriliyor",
                            "progress": pct,
                            "speed_bps": speed,
                            "eta_seconds": int(eta) if eta is not None else None,
                            "downloaded_bytes": dl_bytes,
                            "total_bytes": tot_bytes,
                        },
                    )
                elif st == "finished":
                    fname = d.get("filename")
                    if fname:
                        self._final_filepath = str(fname)
                    self.progress_changed.emit(
                        task_id,
                        {
                            "status": "downloading",
                            "status_text": "Akışlar birleştiriliyor...",
                            "progress": 99.0,
                            "speed_bps": 0.0,
                            "eta_seconds": 0,
                        },
                    )

            def postprocessor_hook(d: dict[str, Any]) -> None:
                self._check_interrupt()
                info_dict = d.get("info_dict") or {}
                fpath = info_dict.get("filepath") or info_dict.get("_filename")
                if fpath:
                    self._final_filepath = str(fpath)

            ydl_opts: dict[str, Any] = {
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "continuedl": True,
                "retries": 5,
                "fragment_retries": 5,
                "concurrent_fragment_downloads": 4,
                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],
            }
            if ffmpeg_loc:
                ydl_opts["ffmpeg_location"] = ffmpeg_loc

            if audio_mode in ("mp3", "m4a", "wav"):
                ydl_opts["format"] = "bestaudio/best"
                if ffmpeg_loc:
                    ydl_opts["postprocessors"] = [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": audio_mode,
                            "preferredquality": "320" if audio_mode == "mp3" else "0",
                        }
                    ]
            else:
                ydl_opts["format"] = "bv*+ba/b"
                sort_rules: list[str] = []
                if target_h:
                    sort_rules.append(f"res:{int(target_h)}")

                if video_fmt_lower == "mp4":
                    sort_rules.extend(["vcodec:h264", "acodec:m4a", "ext:mp4:m4a"])
                    ydl_opts["merge_output_format"] = "mp4"
                    ydl_opts["postprocessor_args"] = {"merger": ["-movflags", "+faststart"]}
                elif video_fmt_lower == "webm":
                    sort_rules.extend(["vcodec:vp9.2", "acodec:opus", "ext:webm"])
                    ydl_opts["merge_output_format"] = "webm"
                else:
                    ydl_opts["merge_output_format"] = "mkv"

                if sort_rules:
                    ydl_opts["format_sort"] = sort_rules

            info = extract(url, ydl_opts, download=True)
            if info and "entries" in info and info["entries"]:
                info = [e for e in info["entries"] if e][0]
            if info and not self.task.get("thumbnail_path"):
                t_url = str(info.get("thumbnail") or "")
                if t_url:
                    plat, _ = resolve_platform_info(info.get("extractor_key"), url)
                    vid = str(info.get("id") or file_stem)
                    cached = cache_thumbnail(t_url, f"{plat}_{vid}")
                    if cached:
                        self.metadata_enriched.emit(task_id, {"thumbnail_path": cached})

            self._check_interrupt()

            resolved_file = self._locate_output_file(out_dir, file_stem, audio_mode, video_fmt_lower)
            if not resolved_file or not resolved_file.is_file():
                raise RuntimeError("İndirilen medya dosyası disk üzerinde doğrulanamadı.")

            if audio_mode == "video" and premiere_opt and self.ffmpeg_mgr.is_available:
                self.progress_changed.emit(
                    task_id,
                    {
                        "status": "converting",
                        "status_text": "Premiere Pro için optimize ediliyor (H.264 / AAC)...",
                        "progress": 0.0,
                        "speed_bps": 0.0,
                        "eta_seconds": None,
                    },
                )

                def on_conv_progress(pct: float) -> None:
                    now = time.monotonic()
                    if now - self._last_emit_ts < 0.15:
                        return
                    self._last_emit_ts = now
                    self.progress_changed.emit(
                        task_id,
                        {
                            "status": "converting",
                            "status_text": f"Premiere Pro için dönüştürülüyor (%{pct:.0f})",
                            "progress": pct,
                        },
                    )

                opt_target = out_dir / f"{file_stem}.mp4"
                temp_opt = out_dir / f"{file_stem}.premiere_tmp.mp4"

                self._check_interrupt()
                success = self.ffmpeg_mgr.convert_for_premiere(
                    input_path=resolved_file,
                    output_path=temp_opt,
                    progress_callback=on_conv_progress,
                    cancel_check=lambda: self.cancel_event.is_set() or self.pause_event.is_set(),
                )
                self._check_interrupt()

                if success and temp_opt.is_file() and temp_opt.stat().st_size > 0:
                    if resolved_file.resolve() != opt_target.resolve() and resolved_file.exists():
                        try:
                            resolved_file.unlink(missing_ok=True)
                        except OSError:
                            pass
                    if opt_target.exists() and opt_target.resolve() != temp_opt.resolve():
                        opt_target.unlink(missing_ok=True)
                    temp_opt.replace(opt_target)
                    resolved_file = opt_target
                else:
                    if temp_opt.exists():
                        temp_opt.unlink(missing_ok=True)

            self.progress_changed.emit(
                task_id,
                {
                    "status": "downloading",
                    "status_text": "Tamamlandı",
                    "progress": 100.0,
                    "speed_bps": 0.0,
                    "eta_seconds": 0,
                },
            )
            self.completed.emit(task_id, str(resolved_file))

        except _TaskPausedException:
            self.paused.emit(task_id)
        except (_TaskCancelledException, FFmpegCancelledError):
            self._cleanup_temp_files(out_dir, self.task.get("file_stem", ""))
            self.cancelled.emit(task_id)
        except Exception as exc:
            msg = translate_ytdlp_error(exc)
            self.failed.emit(task_id, msg)

    def _locate_output_file(
        self,
        out_dir: Path,
        file_stem: str,
        audio_mode: str,
        video_fmt: str,
    ) -> Path | None:
        target_ext = audio_mode.lower() if audio_mode != "video" else video_fmt.lower()
        preferred = out_dir / f"{file_stem}.{target_ext}"
        if preferred.is_file():
            return preferred

        if self._final_filepath:
            fp = Path(self._final_filepath)
            if fp.is_file() and not fp.name.endswith(".part"):
                return fp

        for cand in sorted(out_dir.glob(f"{file_stem}.*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if cand.suffix.lower() not in (".part", ".ytdl", ".temp") and not cand.name.endswith(".premiere_tmp.mp4"):
                if cand.is_file():
                    return cand
        return None

    @staticmethod
    def _cleanup_temp_files(out_dir: Path, file_stem: str) -> None:
        if not file_stem or not out_dir.is_dir():
            return
        for item in out_dir.glob(f"{file_stem}*"):
            if item.name.endswith((".part", ".ytdl", ".premiere_tmp.mp4")) or ".part-" in item.name:
                try:
                    item.unlink(missing_ok=True)
                except OSError:
                    pass


class DownloadManager(QObject):

    task_added = Signal(dict)
    task_updated = Signal(dict)
    task_removed = Signal(str)
    task_completed = Signal(dict, int)
    task_failed = Signal(dict, str)
    counts_changed = Signal(int, int)

    def __init__(
        self,
        db: DatabaseManager,
        settings: SettingsManager,
        ffmpeg_mgr: FFmpegManager,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db = db
        self._settings = settings
        self._ffmpeg = ffmpeg_mgr

        self._tasks: dict[str, DownloadTask] = {}
        self._task_order: list[str] = []
        self._running: dict[str, tuple[QThread, _DownloadWorker, threading.Event, threading.Event]] = {}
        self._shutting_down = False

        self._settings.settings_changed.connect(self._schedule)

    def get_all_tasks(self) -> list[dict[str, Any]]:
        return [self._tasks[tid].to_dict() for tid in reversed(self._task_order) if tid in self._tasks]

    def get_active_count(self) -> int:
        return sum(
            1
            for t in self._tasks.values()
            if t.status in ("queued", "downloading", "converting")
        )

    def _emit_counts(self) -> None:
        self.counts_changed.emit(self.get_active_count(), len(self._tasks))

    def restore_persisted_tasks(self) -> None:
        rows = self._db.get_recoverable_tasks()
        for row in rows:
            prev_status = row["status"]
            status_text = "Sırada bekliyor" if prev_status in ("queued", "downloading", "converting") else "Duraklatıldı"
            task = DownloadTask(
                task_id=row["task_id"],
                url=row["url"],
                title=row["title"],
                platform=row.get("platform") or "Web Medya",
                uploader=row.get("uploader") or "",
                duration=float(row.get("duration") or 0.0),
                thumbnail_path=row.get("thumbnail_path") or "",
                thumbnail_url=row.get("thumbnail_url") or "",
                video_format=row.get("video_format") or "MP4",
                quality_label=row.get("quality_label") or "En iyi kalite",
                target_height=int(row["target_height"]) if row.get("target_height") is not None else None,
                audio_mode=row.get("audio_mode") or "video",
                premiere_optimize=bool(row.get("premiere_optimize")),
                output_dir=row.get("output_dir") or str(self._settings.data.download_dir),
                file_stem=row.get("file_stem") or "",
                final_path=row.get("final_path") or "",
                status="queued" if prev_status in ("queued", "downloading", "converting") else "paused",
                status_text=status_text,
                progress=float(row.get("progress") or 0.0),
                downloaded_bytes=int(row.get("downloaded_bytes") or 0),
                total_bytes=int(row.get("total_bytes") or 0),
                created_at=row.get("created_at") or now_iso(),
            )
            self._tasks[task.task_id] = task
            self._task_order.append(task.task_id)
            self.task_added.emit(task.to_dict())

        self._emit_counts()
        self._schedule()

    def enqueue_from_metadata(self, meta: VideoMetadata, options: DownloadOptions) -> str:
        out_dir = Path(self._settings.data.download_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if options.audio_mode == "image" or meta.media_type == "image":
            expected_ext = "png" if options.video_format == "PNG" else ("jpg" if options.video_format == "JPG" else ("webp" if options.video_format == "WEBP" else "jpg"))
        else:
            expected_ext = (
                options.audio_mode.lower()
                if options.audio_mode != "video"
                else ("mp4" if options.premiere_optimize else options.video_format.lower())
            )
        stem = _unique_file_stem(out_dir, sanitize_filename(meta.title), expected_ext)

        task = DownloadTask(
            task_id=uuid.uuid4().hex[:12],
            url=meta.url,
            title=meta.title,
            platform=meta.platform,
            uploader=meta.uploader,
            duration=meta.duration,
            thumbnail_path=meta.thumbnail_path,
            thumbnail_url=meta.thumbnail_url,
            video_format="MP4" if (options.premiere_optimize and options.audio_mode == "video") else options.video_format,
            quality_label=options.quality_label,
            target_height=options.target_height,
            audio_mode=options.audio_mode,
            premiere_optimize=options.premiere_optimize if options.audio_mode == "video" else False,
            output_dir=str(out_dir),
            file_stem=stem,
            status="queued",
            status_text="Sırada bekliyor",
        )
        self._register_task(task)
        return task.task_id

    def enqueue_gallery_items(
        self,
        items: list[GalleryItem],
        image_format: str = "Orijinal",
        premiere_opt: bool = False,
    ) -> list[str]:
        out_dir = Path(self._settings.data.download_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        added_ids: list[str] = []

        for item in items:
            if not item.selected:
                continue

            is_img = item.media_type == "image"
            if is_img:
                expected_ext = "png" if image_format == "PNG" else ("jpg" if image_format == "JPG" else ("webp" if image_format == "WEBP" else (item.ext or "jpg")))
                video_fmt = image_format
                audio_mode = "image"
                quality_label = "Görsel"
                target_h = item.height or None
                prem = False
            else:
                expected_ext = "mp4" if premiere_opt else (item.ext or "mp4")
                video_fmt = "MP4"
                audio_mode = "video"
                quality_label = f"{item.height}p" if item.height else "En iyi kalite"
                target_h = item.height or None
                prem = premiere_opt

            stem = _unique_file_stem(out_dir, sanitize_filename(item.title), expected_ext)
            task = DownloadTask(
                task_id=uuid.uuid4().hex[:12],
                url=item.url,
                title=item.title,
                platform="Instagram" if "instagram" in item.url.lower() else "Web Medya",
                duration=item.duration,
                thumbnail_url=item.thumbnail_url,
                video_format=video_fmt,
                quality_label=quality_label,
                target_height=target_h,
                audio_mode=audio_mode,
                premiere_optimize=prem,
                output_dir=str(out_dir),
                file_stem=stem,
                status="queued",
                status_text="Sırada bekliyor",
            )
            self._register_task(task)
            added_ids.append(task.task_id)

        return added_ids

    def enqueue_urls(self, urls: list[str], options: DownloadOptions | None = None) -> list[str]:
        opts = options or DownloadOptions(
            video_format=self._settings.data.default_format,
            quality_label=self._settings.data.default_quality,
            target_height=self._height_from_label(self._settings.data.default_quality),
            audio_mode="video",
            premiere_optimize=self._settings.data.premiere_optimize_default,
        )
        out_dir = Path(self._settings.data.download_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        added_ids: list[str] = []
        for raw_url in urls:
            url = raw_url.strip()
            if not url:
                continue
            plat_name, _ = resolve_platform_info(None, url)
            task = DownloadTask(
                task_id=uuid.uuid4().hex[:12],
                url=url,
                title="Bağlantı hazırlanıyor...",
                platform=plat_name,
                video_format="MP4" if (opts.premiere_optimize and opts.audio_mode == "video") else opts.video_format,
                quality_label=opts.quality_label,
                target_height=opts.target_height,
                audio_mode=opts.audio_mode,
                premiere_optimize=opts.premiere_optimize if opts.audio_mode == "video" else False,
                output_dir=str(out_dir),
                file_stem="",
                status="queued",
                status_text="Sırada bekliyor",
            )
            self._register_task(task)
            added_ids.append(task.task_id)
        return added_ids

    @staticmethod
    def _height_from_label(label: str) -> int | None:
        from config.constants import VIDEO_QUALITIES

        for q_label, height in VIDEO_QUALITIES:
            if q_label == label:
                return height
        return None

    def _register_task(self, task: DownloadTask) -> None:
        self._tasks[task.task_id] = task
        self._task_order.append(task.task_id)
        self._db.save_download_task(task.to_dict())
        self.task_added.emit(task.to_dict())
        self._emit_counts()
        self._schedule()

    def _schedule(self) -> None:
        if self._shutting_down:
            return
        limit = max(1, min(8, int(self._settings.data.max_concurrent_downloads)))
        while len(self._running) < limit:
            next_task: DownloadTask | None = None
            for tid in self._task_order:
                t = self._tasks.get(tid)
                if t and t.status == "queued" and tid not in self._running:
                    next_task = t
                    break
            if not next_task:
                break
            self._start_worker(next_task)

    def _start_worker(self, task: DownloadTask) -> None:
        pause_ev = threading.Event()
        cancel_ev = threading.Event()

        task.status = "downloading"
        task.status_text = "Bağlanıyor..."
        task.error_message = ""
        self._db.save_download_task(task.to_dict())
        self.task_updated.emit(task.to_dict())
        self._emit_counts()

        thread = QThread()
        worker = _DownloadWorker(task.to_dict(), self._ffmpeg, pause_ev, cancel_ev)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress_changed.connect(self._on_worker_progress)
        worker.metadata_enriched.connect(self._on_worker_metadata)
        worker.completed.connect(self._on_worker_completed)
        worker.paused.connect(self._on_worker_paused)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.failed.connect(self._on_worker_failed)

        def cleanup() -> None:
            self._running.pop(task.task_id, None)
            worker.deleteLater()
            thread.deleteLater()
            self._emit_counts()
            self._schedule()

        for terminal_sig in (worker.completed, worker.paused, worker.cancelled, worker.failed):
            terminal_sig.connect(thread.quit)
        thread.finished.connect(cleanup)

        self._running[task.task_id] = (thread, worker, pause_ev, cancel_ev)
        thread.start()

    def _on_worker_progress(self, task_id: str, patch: dict[str, Any]) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        for k, v in patch.items():
            if hasattr(task, k):
                setattr(task, k, v)
        self.task_updated.emit(task.to_dict())

    def _on_worker_metadata(self, task_id: str, patch: dict[str, Any]) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        for k, v in patch.items():
            if hasattr(task, k):
                setattr(task, k, v)
        self._db.save_download_task(task.to_dict())
        self.task_updated.emit(task.to_dict())

    def _on_worker_completed(self, task_id: str, final_filepath: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return

        fpath = Path(final_filepath)
        file_size = fpath.stat().st_size if fpath.is_file() else task.total_bytes

        if task.audio_mode == "image" or (task.duration == 0 and task.video_format in ("PNG", "JPG", "WEBP", "Orijinal")):
            res_label = "Görsel"
            try:
                from PIL import Image
                with Image.open(fpath) as im:
                    res_label = f"{im.width}x{im.height}"
            except Exception:
                pass
            fmt_name = fpath.suffix.lstrip(".").upper() or task.video_format.upper()
            premiere_ready = False
            probe = None
            duration = 0.0
        elif task.audio_mode != "video":
            probe = self._ffmpeg.probe_media(fpath) if fpath.is_file() else None
            duration = probe.duration if (probe and probe.duration > 0) else task.duration
            res_label = f"Ses ({task.audio_mode.upper()})"
            fmt_name = task.audio_mode.upper()
            premiere_ready = True
        else:
            probe = self._ffmpeg.probe_media(fpath) if fpath.is_file() else None
            duration = probe.duration if (probe and probe.duration > 0) else task.duration
            res_label = (probe.resolution_label if (probe and probe.resolution_label) else task.quality_label)
            fmt_name = fpath.suffix.lstrip(".").upper() or task.video_format.upper()
            premiere_ready = bool(task.premiere_optimize or (probe and probe.is_premiere_mp4_ready))

        thumb_path = task.thumbnail_path
        if (not thumb_path or not Path(thumb_path).is_file()) and task.audio_mode == "video":
            from config.paths import THUMBNAILS_DIR

            gen_thumb = THUMBNAILS_DIR / f"local_{task.task_id}.jpg"
            if self._ffmpeg.extract_thumbnail(fpath, gen_thumb, duration):
                thumb_path = str(gen_thumb)
                task.thumbnail_path = thumb_path
        elif (not thumb_path or not Path(thumb_path).is_file()) and (task.audio_mode == "image" or duration == 0):
            thumb_path = str(fpath)
            task.thumbnail_path = thumb_path

        task.final_path = str(fpath)
        task.total_bytes = file_size
        task.downloaded_bytes = file_size
        task.progress = 100.0
        task.speed_bps = 0.0
        task.eta_seconds = 0
        task.status = "completed"
        task.status_text = "Tamamlandı"

        media_id = self._db.upsert_media_item(
            title=task.title,
            file_name=fpath.name,
            file_path=str(fpath),
            source_url=task.url,
            platform=task.platform,
            uploader=task.uploader,
            duration=duration,
            resolution=res_label,
            format_name=fmt_name,
            video_codec="Görsel" if task.audio_mode == "image" else (probe.video_codec if probe else ""),
            audio_codec=probe.audio_codec if probe else "",
            file_size=file_size,
            thumbnail_path=thumb_path,
            premiere_ready=premiere_ready,
        )

        self._db.add_history_entry(
            task_id=task.task_id,
            title=task.title,
            source_url=task.url,
            platform=task.platform,
            uploader=task.uploader,
            format_name=fmt_name,
            quality=res_label,
            file_path=str(fpath),
            file_size=file_size,
            duration=duration,
            thumbnail_path=thumb_path,
            premiere_optimized=task.premiere_optimize,
            status="completed",
        )

        self._db.remove_download_task(task.task_id)
        self.task_updated.emit(task.to_dict())
        self.task_completed.emit(task.to_dict(), media_id)
        self._emit_counts()

    def _on_worker_paused(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        if self._shutting_down:
            task.status = "queued"
            task.status_text = "Devam etmek üzere kaydedildi"
            self._db.save_download_task(task.to_dict())
            return

        task.status = "paused"
        task.status_text = "Duraklatıldı"
        task.speed_bps = 0.0
        task.eta_seconds = None
        self._db.save_download_task(task.to_dict())
        self.task_updated.emit(task.to_dict())
        self._emit_counts()

    def _on_worker_cancelled(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        if task_id in self._task_order:
            self._task_order.remove(task_id)
        self._db.remove_download_task(task_id)
        self.task_removed.emit(task_id)
        self._emit_counts()

    def _on_worker_failed(self, task_id: str, err_msg: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        task.status = "failed"
        task.status_text = "İndirme başarısız"
        task.error_message = err_msg
        task.speed_bps = 0.0
        task.eta_seconds = None
        self._db.save_download_task(task.to_dict())
        self.task_updated.emit(task.to_dict())
        self.task_failed.emit(task.to_dict(), err_msg)
        self._emit_counts()

    def pause_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        if task_id in self._running:
            _, _, pause_ev, _ = self._running[task_id]
            task.status_text = "Duraklatılıyor..."
            self.task_updated.emit(task.to_dict())
            pause_ev.set()
        elif task.status == "queued":
            task.status = "paused"
            task.status_text = "Duraklatıldı"
            self._db.save_download_task(task.to_dict())
            self.task_updated.emit(task.to_dict())
            self._emit_counts()

    def resume_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task or task.status not in ("paused", "failed"):
            return
        task.status = "queued"
        task.status_text = "Sırada bekliyor"
        task.error_message = ""
        self._db.save_download_task(task.to_dict())
        self.task_updated.emit(task.to_dict())
        self._emit_counts()
        self._schedule()

    def retry_task(self, task_id: str) -> None:
        self.resume_task(task_id)

    def cancel_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        if task_id in self._running:
            _, _, _, cancel_ev = self._running[task_id]
            task.status_text = "İptal ediliyor..."
            self.task_updated.emit(task.to_dict())
            cancel_ev.set()
        else:
            _DownloadWorker._cleanup_temp_files(Path(task.output_dir), task.file_stem)
            self._tasks.pop(task_id, None)
            if task_id in self._task_order:
                self._task_order.remove(task_id)
            self._db.remove_download_task(task_id)
            self.task_removed.emit(task_id)
            self._emit_counts()

    def clear_completed(self) -> None:
        to_remove = [tid for tid, t in self._tasks.items() if t.status == "completed"]
        for tid in to_remove:
            self._tasks.pop(tid, None)
            if tid in self._task_order:
                self._task_order.remove(tid)
            self.task_removed.emit(tid)
        self._db.clear_finished_tasks()
        self._emit_counts()

    def shutdown(self) -> None:
        self._shutting_down = True
        active_threads: list[QThread] = []
        for task_id, (thread, _, pause_ev, _) in list(self._running.items()):
            task = self._tasks.get(task_id)
            if task:
                task.status = "queued"
                self._db.save_download_task(task.to_dict())
            pause_ev.set()
            active_threads.append(thread)

        for thread in active_threads:
            thread.quit()
            thread.wait(2500)


def open_file_in_default_player(file_path: str) -> bool:
    target = Path(file_path)
    if not target.is_file():
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(target))
            return True
    except OSError:
        pass
    return False


def _select_item_in_explorer(item_path: str) -> bool:
    if sys.platform != "win32":
        return False
    target = Path(item_path).resolve()
    if not target.exists():
        return False

    import subprocess
    ps_cmd = (
        f"$p = '{str(target)}'; "
        f"$dir = [System.IO.Path]::GetDirectoryName($p); "
        f"$name = [System.IO.Path]::GetFileName($p); "
        f"$sh = New-Object -ComObject Shell.Application; "
        f"$found = $false; "
        f"foreach ($w in $sh.Windows()) {{ "
        f"  try {{ "
        f"    $loc = [System.Uri]::UnescapeDataString($w.LocationURL); "
        f"    if ($loc -like 'file:///*') {{ "
        f"      $winPath = $loc.Substring(8).Replace('/', '\\'); "
        f"      if ($winPath.TrimEnd('\\') -ieq $dir.TrimEnd('\\')) {{ "
        f"        $items = $w.Document.Folder.Items(); "
        f"        $it = $items.Item($name); "
        f"        if ($it) {{ $w.Document.SelectItem($it, 17); $found = $true; break; }} "
        f"      }} "
        f"    }} "
        f"  }} catch {{}} "
        f"}}; "
        f"if (-not $found) {{ & explorer.exe /select,$p }}"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            timeout=5,
        )
        return True
    except Exception:
        pass
    return False


def reveal_in_explorer(file_or_dir_path: str) -> bool:
    target = Path(file_or_dir_path).resolve()
    if not target.exists():
        if target.parent.is_dir():
            target = target.parent
        else:
            return False

    if target.is_file():
        return _select_item_in_explorer(str(target))

    if target.is_dir():
        try:
            if sys.platform == "win32":
                os.startfile(str(target))
                return True
        except OSError:
            pass
    return False
