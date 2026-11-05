
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from config.paths import BIN_DIR


def _subprocess_flags() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


@dataclass
class DependencyStatus:
    ffmpeg_ok: bool
    ffprobe_ok: bool
    ffmpeg_path: str
    ffprobe_path: str
    ffmpeg_version: str
    ytdlp_ok: bool
    ytdlp_version: str
    message: str = ""


@dataclass
class MediaProbeResult:
    duration: float = 0.0
    width: int = 0
    height: int = 0
    video_codec: str = ""
    audio_codec: str = ""
    pix_fmt: str = ""

    @property
    def resolution_label(self) -> str:
        if self.width > 0 and self.height > 0:
            return f"{self.width}x{self.height}"
        return ""

    @property
    def is_premiere_mp4_ready(self) -> bool:
        if not self.video_codec:
            return False
        v_ok = self.video_codec.lower() in ("h264", "avc1")
        pix_ok = self.pix_fmt.lower() in ("yuv420p", "yuvj420p", "")
        a_ok = self.audio_codec.lower() in ("aac", "mp4a", "mp3", "")
        return v_ok and pix_ok and a_ok


class FFmpegCancelledError(Exception):
    pass


class FFmpegManager:

    def __init__(self, custom_path: str = "") -> None:
        self.custom_path = custom_path.strip()
        self.ffmpeg_path: str = ""
        self.ffprobe_path: str = ""
        self.ffmpeg_version: str = ""
        self.refresh(self.custom_path)

    def refresh(self, custom_path: str = "") -> None:
        self.custom_path = custom_path.strip()
        self.ffmpeg_path, self.ffprobe_path = self._discover_binaries(self.custom_path)
        self.ffmpeg_version = self._read_ffmpeg_version(self.ffmpeg_path) if self.ffmpeg_path else ""

    def _discover_binaries(self, custom_path: str) -> tuple[str, str]:
        exe_suffix = ".exe" if sys.platform == "win32" else ""
        candidates_dirs: list[Path] = []

        if custom_path:
            cp = Path(custom_path)
            if cp.is_file() and cp.exists():
                probe_sibling = cp.parent / f"ffprobe{exe_suffix}"
                return str(cp.resolve()), (str(probe_sibling.resolve()) if probe_sibling.exists() else "")
            if cp.is_dir() and cp.exists():
                candidates_dirs.append(cp)
                if (cp / "bin").is_dir():
                    candidates_dirs.append(cp / "bin")

        from config.paths import BUNDLE_ROOT

        for extra_bin in (
            BUNDLE_ROOT / "bin",
            Path(sys.executable).resolve().parent / "bin",
            BIN_DIR,
        ):
            if extra_bin.is_dir():
                candidates_dirs.append(extra_bin)

        sys_ffmpeg = shutil.which("ffmpeg")
        sys_ffprobe = shutil.which("ffprobe")
        if sys_ffmpeg:
            return str(Path(sys_ffmpeg).resolve()), (str(Path(sys_ffprobe).resolve()) if sys_ffprobe else "")

        try:
            import static_ffmpeg

            pkg_root = Path(static_ffmpeg.__file__).resolve().parent / "bin"
            for plat_folder in ("win32", "darwin", "linux"):
                cand = pkg_root / plat_folder
                if cand.is_dir():
                    candidates_dirs.append(cand)
        except Exception:
            pass

        if sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                winget_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
                if winget_dir.is_dir():
                    for match in winget_dir.glob("*FFmpeg*/*/bin"):
                        if match.is_dir():
                            candidates_dirs.append(match)

        for folder in candidates_dirs:
            ff = folder / f"ffmpeg{exe_suffix}"
            fp = folder / f"ffprobe{exe_suffix}"
            if ff.is_file():
                return str(ff.resolve()), (str(fp.resolve()) if fp.is_file() else "")

        try:
            import imageio_ffmpeg

            iio_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
            if iio_exe.is_file():
                BIN_DIR.mkdir(parents=True, exist_ok=True)
                shim_ffmpeg = BIN_DIR / f"ffmpeg{exe_suffix}"
                if not shim_ffmpeg.exists():
                    shutil.copy2(iio_exe, shim_ffmpeg)
                return str(shim_ffmpeg.resolve()), ""
        except Exception:
            pass

        return "", ""

    def _read_ffmpeg_version(self, ffmpeg_bin: str) -> str:
        try:
            proc = subprocess.run(
                [ffmpeg_bin, "-version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                creationflags=_subprocess_flags(),
            )
            if proc.returncode == 0 and proc.stdout:
                first_line = proc.stdout.splitlines()[0]
                m = re.search(r"ffmpeg version\s+([^\s]+)", first_line, re.IGNORECASE)
                return m.group(1) if m else "Hazır"
        except Exception:
            pass
        return ""

    @property
    def is_available(self) -> bool:
        return bool(self.ffmpeg_path and Path(self.ffmpeg_path).is_file())

    def get_ytdlp_ffmpeg_location(self) -> str | None:
        if not self.is_available:
            return None
        ff_path = Path(self.ffmpeg_path)
        if self.ffprobe_path and Path(self.ffprobe_path).parent == ff_path.parent:
            return str(ff_path.parent)
        return str(ff_path)

    def check_dependencies(self) -> DependencyStatus:
        ytdlp_ok = False
        ytdlp_ver = "Bulunamadı"
        try:
            import yt_dlp.version

            ytdlp_ok = True
            ytdlp_ver = yt_dlp.version.__version__
        except Exception:
            pass

        ff_ok = self.is_available and bool(self.ffmpeg_version)
        fp_ok = bool(self.ffprobe_path and Path(self.ffprobe_path).is_file())

        missing: list[str] = []
        if not ytdlp_ok:
            missing.append("yt-dlp")
        if not ff_ok:
            missing.append("FFmpeg")

        if missing:
            msg = (
                f"Eksik bileşen algılandı: {', '.join(missing)}. "
                "Yüksek çözünürlüklü birleştirme ve Premiere Pro dönüştürme için Ayarlar'dan FFmpeg konumunu doğrulayın."
            )
        else:
            msg = "Tüm indirme ve medya işleme motorları hazır."

        return DependencyStatus(
            ffmpeg_ok=ff_ok,
            ffprobe_ok=fp_ok,
            ffmpeg_path=self.ffmpeg_path,
            ffprobe_path=self.ffprobe_path,
            ffmpeg_version=self.ffmpeg_version or "Yok",
            ytdlp_ok=ytdlp_ok,
            ytdlp_version=ytdlp_ver,
            message=msg,
        )

    def probe_media(self, file_path: str | Path) -> MediaProbeResult:
        target = Path(file_path)
        result = MediaProbeResult()
        if not target.is_file():
            return result

        if self.ffprobe_path and Path(self.ffprobe_path).is_file():
            try:
                proc = subprocess.run(
                    [
                        self.ffprobe_path,
                        "-v",
                        "quiet",
                        "-print_format",
                        "json",
                        "-show_format",
                        "-show_streams",
                        str(target),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                    creationflags=_subprocess_flags(),
                )
                if proc.returncode == 0 and proc.stdout:
                    data = json.loads(proc.stdout)
                    fmt = data.get("format") or {}
                    if fmt.get("duration"):
                        result.duration = float(fmt["duration"])
                    for stream in data.get("streams") or []:
                        stype = stream.get("codec_type")
                        if stype == "video" and not result.video_codec:
                            disp = stream.get("disposition") or {}
                            if disp.get("attached_pic") == 1:
                                continue
                            result.video_codec = str(stream.get("codec_name") or "")
                            result.pix_fmt = str(stream.get("pix_fmt") or "")
                            result.width = int(stream.get("width") or 0)
                            result.height = int(stream.get("height") or 0)
                            if not result.duration and stream.get("duration"):
                                result.duration = float(stream["duration"])
                        elif stype == "audio" and not result.audio_codec:
                            result.audio_codec = str(stream.get("codec_name") or "")
                    return result
            except Exception:
                pass

        if self.is_available:
            try:
                proc = subprocess.run(
                    [self.ffmpeg_path, "-hide_banner", "-i", str(target)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=12,
                    creationflags=_subprocess_flags(),
                )
                info = proc.stderr or ""
                dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info)
                if dur_m:
                    h, m, s = int(dur_m.group(1)), int(dur_m.group(2)), float(dur_m.group(3))
                    result.duration = h * 3600 + m * 60 + s
                vid_m = re.search(r"Video:\s*([a-zA-Z0-9_]+).*?,\s*([a-zA-Z0-9_]+).*?(\d{2,5})x(\d{2,5})", info)
                if vid_m:
                    result.video_codec = vid_m.group(1)
                    result.pix_fmt = vid_m.group(2)
                    result.width = int(vid_m.group(3))
                    result.height = int(vid_m.group(4))
                aud_m = re.search(r"Audio:\s*([a-zA-Z0-9_]+)", info)
                if aud_m:
                    result.audio_codec = aud_m.group(1)
            except Exception:
                pass

        return result

    def optimize_for_premiere(
        self,
        input_path: str | Path,
        *,
        progress_callback: Callable[[float], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Path:
        if not self.is_available:
            raise RuntimeError("Premiere Pro optimizasyonu için FFmpeg bulunamadı.")

        src = Path(input_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Dönüştürülecek dosya bulunamadı: {src}")

        probe = self.probe_media(src)
        total_duration = max(probe.duration, 0.1)

        out_final = src.with_suffix(".mp4")
        temp_out = src.with_name(f"{src.stem}.premiere_tmp.mp4")
        if temp_out.exists():
            try:
                temp_out.unlink()
            except OSError:
                pass

        if probe.is_premiere_mp4_ready and src.suffix.lower() == ".mp4":
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-hide_banner",
                "-i",
                str(src),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(temp_out),
            ]
        else:
            v_codec_args = (
                ["-c:v", "copy"]
                if (probe.video_codec.lower() == "h264" and probe.pix_fmt.lower() == "yuv420p")
                else [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-fps_mode",
                    "cfr",
                ]
            )
            a_codec_args = (
                ["-c:a", "copy"]
                if probe.audio_codec.lower() == "aac"
                else ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
            )
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-hide_banner",
                "-i",
                str(src),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                *v_codec_args,
                *a_codec_args,
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                str(temp_out),
            ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_subprocess_flags(),
        )

        recent_lines: list[str] = []
        try:
            if proc.stdout:
                for raw_line in proc.stdout:
                    if cancel_check and cancel_check():
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        if temp_out.exists():
                            temp_out.unlink(missing_ok=True)
                        raise FFmpegCancelledError("Dönüştürme işlemi durduruldu.")

                    line = raw_line.strip()
                    if line:
                        recent_lines.append(line)
                        if len(recent_lines) > 12:
                            recent_lines.pop(0)
                    if line.startswith("out_time_us="):
                        val_str = line.split("=", 1)[1]
                        if val_str.isdigit():
                            sec = int(val_str) / 1_000_000.0
                            pct = min(99.5, max(0.0, (sec / total_duration) * 100.0))
                            if progress_callback:
                                progress_callback(pct)

            proc.wait()
            if cancel_check and cancel_check():
                if temp_out.exists():
                    temp_out.unlink(missing_ok=True)
                raise FFmpegCancelledError("Dönüştürme işlemi durduruldu.")

            if proc.returncode != 0 or not temp_out.is_file():
                if temp_out.exists():
                    temp_out.unlink(missing_ok=True)
                tail = recent_lines[-4:]
                raise RuntimeError(f"FFmpeg dönüştürme hatası: {' '.join(tail)}")

            if src != out_final and src.exists():
                src.unlink(missing_ok=True)
            temp_out.replace(out_final)
            if progress_callback:
                progress_callback(100.0)
            return out_final
        except FFmpegCancelledError:
            raise
        except Exception:
            if proc.poll() is None:
                proc.kill()
            if temp_out.exists():
                temp_out.unlink(missing_ok=True)
            raise

    def extract_thumbnail(self, media_path: str | Path, output_image: str | Path, duration: float = 0.0) -> bool:
        if not self.is_available:
            return False
        src = Path(media_path)
        dst = Path(output_image)
        if not src.is_file():
            return False

        dst.parent.mkdir(parents=True, exist_ok=True)
        seek_sec = min(3.0, duration * 0.2) if duration > 1.0 else 0.0
        try:
            proc = subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-ss",
                    f"{seek_sec:.2f}",
                    "-i",
                    str(src),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=480:-2",
                    "-q:v",
                    "3",
                    str(dst),
                ],
                capture_output=True,
                timeout=12,
                creationflags=_subprocess_flags(),
            )
            return proc.returncode == 0 and dst.is_file() and dst.stat().st_size > 0
        except Exception:
            return False
