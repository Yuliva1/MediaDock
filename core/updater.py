from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from PySide6.QtCore import QObject, QThread, Signal

from config.constants import APP_VERSION


def parse_semver(ver_str: str) -> tuple[int, ...]:
    cleaned = re.sub(r"^[^\d]*", "", ver_str.strip())
    parts = re.split(r"[^\d]+", cleaned)
    nums: list[int] = []
    for p in parts:
        if p.isdigit():
            nums.append(int(p))
    return tuple(nums) if nums else (0, 0, 0)


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    has_update: bool
    release_name: str = ""
    release_notes: str = ""
    published_at: str = ""
    download_url: str = ""
    asset_name: str = ""
    asset_size: int = 0


def check_for_updates(repo_or_url: str, current_version: str = APP_VERSION) -> UpdateInfo:
    target = repo_or_url.strip()
    if not target:
        target = "Yuliva/MediaDock"

    headers = {
        "User-Agent": f"MediaDock-Client/{current_version}",
        "Accept": "application/vnd.github.v3+json",
    }

    if target.startswith("http://") or target.startswith("https://"):
        url = target
    else:
        clean_slug = target.strip("/").replace("https://github.com/", "").replace("http://github.com/", "")
        url = f"https://api.github.com/repos/{clean_slug}/releases/latest"

    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 404:
        return UpdateInfo(
            current_version=current_version,
            latest_version=current_version,
            has_update=False,
            release_name=f"MediaDock v{current_version}",
            release_notes="Henüz GitHub üzerinde yeni bir sürüm yayınlanmadı.",
        )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    tag_name = str(data.get("tag_name") or data.get("version") or "")
    remote_ver = tag_name.lstrip("vV")
    cur_tuple = parse_semver(current_version)
    rem_tuple = parse_semver(remote_ver)

    has_update = rem_tuple > cur_tuple

    rel_name = str(data.get("name") or f"MediaDock v{remote_ver}")
    body = str(data.get("body") or data.get("changelog") or "Yeni iyileştirmeler ve hata düzeltmeleri.")
    pub_at = str(data.get("published_at") or data.get("release_date") or "")

    dl_url = str(data.get("download_url") or "")
    asset_name = ""
    asset_size = 0

    assets = data.get("assets")
    if isinstance(assets, list):
        for a in assets:
            name = str(a.get("name") or "")
            if name.lower().endswith(".exe"):
                dl_url = str(a.get("browser_download_url") or "")
                asset_name = name
                asset_size = int(a.get("size") or 0)
                if "setup" in name.lower():
                    break

    if not asset_name and dl_url:
        asset_name = Path(dl_url.split("?")[0]).name or "MediaDock-Setup.exe"

    return UpdateInfo(
        current_version=current_version,
        latest_version=remote_ver,
        has_update=has_update,
        release_name=rel_name,
        release_notes=body,
        published_at=pub_at,
        download_url=dl_url,
        asset_name=asset_name,
        asset_size=asset_size,
    )


class UpdateCheckWorker(QObject):

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, repo_or_url: str, current_version: str = APP_VERSION) -> None:
        super().__init__()
        self.repo_or_url = repo_or_url
        self.current_version = current_version

    def run(self) -> None:
        try:
            info = check_for_updates(self.repo_or_url, self.current_version)
            self.finished.emit(info)
        except Exception as exc:
            self.failed.emit(str(exc))


class UpdateDownloadWorker(QObject):

    progress = Signal(float, int, int, float)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, download_url: str, asset_name: str) -> None:
        super().__init__()
        self.download_url = download_url
        self.asset_name = asset_name or "MediaDock-Setup.exe"
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            temp_dir = Path(tempfile.gettempdir()) / "MediaDock-Update"
            temp_dir.mkdir(parents=True, exist_ok=True)
            dest = temp_dir / self.asset_name

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MediaDock"}
            resp = requests.get(self.download_url, headers=headers, stream=True, timeout=30)
            resp.raise_for_status()

            total_bytes = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            t0 = time.monotonic()
            last_emit = 0.0

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=131072):
                    if self._cancelled:
                        raise RuntimeError("Güncelleme indirme işlemi kullanıcı tarafından iptal edildi.")
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if now - last_emit >= 0.1:
                        last_emit = now
                        pct = (downloaded / total_bytes * 100.0) if total_bytes > 0 else 50.0
                        speed = downloaded / max(now - t0, 0.001)
                        self.progress.emit(min(99.0, pct), downloaded, total_bytes, speed)

            self.progress.emit(100.0, downloaded, total_bytes or downloaded, 0.0)
            self.finished.emit(str(dest.resolve()))

        except Exception as exc:
            self.failed.emit(str(exc))


def launch_installer_and_exit(installer_path: str) -> None:
    path_obj = Path(installer_path).resolve()
    if not path_obj.is_file():
        raise FileNotFoundError(f"Kurulum dosyası bulunamadı: {installer_path}")

    try:
        os.startfile(str(path_obj))
    except Exception:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(path_obj)], creationflags=flags, close_fds=True)

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app:
        app.quit()
    sys.exit(0)
