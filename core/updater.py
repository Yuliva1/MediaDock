from __future__ import annotations

import hashlib
import json
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
from PySide6.QtCore import QObject, Signal

from config.constants import APP_VERSION, DEFAULT_UPDATE_REPO
from config.paths import is_frozen
from core import delta_update
from core.logutil import log_event

ASSET_MANIFEST = "manifest.json"
ASSET_ZIP = "mediadock-app.zip"
ASSET_SUMS = "sha256sums.txt"
# Sihirbazsız (sessiz) kurulum: kullanıcı yalnızca ilerleme çubuğunu görür.
INSTALLER_ARGS = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]


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
    manifest_url: str = ""
    app_zip_url: str = ""
    sums_url: str = ""


def check_for_updates(repo_or_url: str, current_version: str = APP_VERSION) -> UpdateInfo:
    target = repo_or_url.strip()
    if not target:
        target = DEFAULT_UPDATE_REPO

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

    manifest_url = ""
    app_zip_url = ""
    sums_url = ""

    assets = data.get("assets")
    if isinstance(assets, list):
        for a in assets:
            lname = str(a.get("name") or "").lower()
            url_ = str(a.get("browser_download_url") or "")
            if lname == ASSET_MANIFEST:
                manifest_url = url_
            elif lname == ASSET_ZIP:
                app_zip_url = url_
            elif lname == ASSET_SUMS:
                sums_url = url_
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
        manifest_url=manifest_url,
        app_zip_url=app_zip_url,
        sums_url=sums_url,
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


def parse_sha256sums(text: str) -> dict[str, str]:
    """``<hash>  <dosya>`` biçimli metni {küçük_harf_ad: hash} sözlüğüne çevirir."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m:
            result[m.group(2).strip().lower()] = m.group(1).lower()
    return result


class UpdateCancelled(RuntimeError):
    pass


class UpdateDownloadWorker(QObject):
    """Önce delta (yalnızca değişen dosyalar), olmazsa tam kurulum dosyasını indirir.

    ``finished`` sinyali: klasör yolu = delta hazır, dosya yolu = tam kurulum dosyası.
    """

    progress = Signal(float, int, int, float)
    finished = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(
        self,
        download_url: str,
        asset_name: str,
        info: UpdateInfo | None = None,
        app_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.download_url = download_url
        self.asset_name = asset_name or "MediaDock-Setup.exe"
        self.info = info
        self._app_dir = app_dir
        self._cancelled = False
        self._sums: dict[str, str] | None = None

    def cancel(self) -> None:
        self._cancelled = True

    def _check_cancel(self) -> bool:
        return self._cancelled

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MediaDock"}

    def _load_sums(self) -> dict[str, str]:
        if self._sums is not None:
            return self._sums
        self._sums = {}
        if self.info and self.info.sums_url:
            try:
                resp = requests.get(self.info.sums_url, headers=self._headers(), timeout=20)
                resp.raise_for_status()
                self._sums = parse_sha256sums(resp.text)
            except Exception as exc:
                log_event(f"sha256sums alınamadı: {exc}")
        return self._sums

    def _delta_target(self) -> Path | None:
        if not (self.info and self.info.manifest_url and self.info.app_zip_url):
            return None
        if self._app_dir is not None:
            return self._app_dir
        return delta_update.app_dir_for_frozen() if is_frozen() else None

    def _run_delta(self, app_dir: Path) -> Path:
        info = self.info
        assert info is not None
        self.status.emit("Değişen dosyalar belirleniyor...")
        delta_update.check_writable(app_dir)

        resp = requests.get(info.manifest_url, headers=self._headers(), timeout=20)
        resp.raise_for_status()
        expected = self._load_sums().get(ASSET_MANIFEST)
        if expected and hashlib.sha256(resp.content).hexdigest() != expected:
            raise delta_update.DeltaError("Manifest doğrulaması başarısız.")
        manifest = json.loads(resp.content.decode("utf-8"))

        needed = delta_update.plan_changes(manifest, app_dir)
        if not delta_update.delta_is_worthwhile(manifest, needed):
            raise delta_update.DeltaError("Delta güncelleme bu sürüm için uygun değil.")

        total = sum(int(e["csize"]) for e in needed)
        self.status.emit(f"Yalnızca değişen {len(needed)} dosya indiriliyor...")
        staging = Path(tempfile.gettempdir()) / "MediaDock-Update" / "delta"

        def on_progress(done: int, tot: int, speed: float) -> None:
            pct = (done / tot * 100.0) if tot > 0 else 0.0
            self.progress.emit(min(99.0, pct), done, tot, speed)

        try:
            delta_update.download_changed(
                manifest, needed, info.app_zip_url, staging, on_progress, self._check_cancel
            )
        except delta_update.DeltaCancelled as exc:
            raise UpdateCancelled(str(exc)) from exc
        self.progress.emit(100.0, total, total, 0.0)
        return staging

    def _run_full(self) -> Path:
        self.status.emit("Tam kurulum dosyası indiriliyor...")
        temp_dir = Path(tempfile.gettempdir()) / "MediaDock-Update"
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest = temp_dir / self.asset_name

        resp = requests.get(self.download_url, headers=self._headers(), stream=True, timeout=30)
        resp.raise_for_status()

        total_bytes = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        t0 = time.monotonic()
        last_emit = 0.0
        h = hashlib.sha256()

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=131072):
                if self._cancelled:
                    raise UpdateCancelled("Güncelleme indirme işlemi kullanıcı tarafından iptal edildi.")
                if not chunk:
                    continue
                f.write(chunk)
                h.update(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_emit >= 0.1:
                    last_emit = now
                    pct = (downloaded / total_bytes * 100.0) if total_bytes > 0 else 50.0
                    speed = downloaded / max(now - t0, 0.001)
                    self.progress.emit(min(99.0, pct), downloaded, total_bytes, speed)

        expected = self._load_sums().get(self.asset_name.lower())
        if expected and h.hexdigest() != expected:
            dest.unlink(missing_ok=True)
            raise RuntimeError("İndirilen kurulum dosyasının SHA-256 doğrulaması başarısız. Dosya silindi.")
        if not expected:
            log_event("Uyarı: sürümde sha256sums.txt yok; kurulum dosyası hash ile doğrulanmadı.")

        self.progress.emit(100.0, downloaded, total_bytes or downloaded, 0.0)
        return dest.resolve()

    def run(self) -> None:
        try:
            app_dir = self._delta_target()
            if app_dir is not None:
                try:
                    self.finished.emit(str(self._run_delta(app_dir)))
                    return
                except UpdateCancelled:
                    raise
                except Exception as exc:
                    log_event(f"Delta güncelleme kullanılamadı, tam kuruluma geçiliyor: {exc}")

            if not self.download_url:
                raise RuntimeError("İndirilebilir kurulum dosyası (setup.exe) bulunamadı.")
            self.finished.emit(str(self._run_full()))
        except Exception as exc:
            self.failed.emit(str(exc))


def _quit_app() -> None:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app:
        app.quit()
    sys.exit(0)


def apply_delta_and_restart(staging_dir: str) -> None:
    if not is_frozen():
        raise RuntimeError("Delta güncelleme yalnızca kurulu (exe) sürümde uygulanabilir.")
    delta_update.apply_staged(Path(staging_dir), delta_update.app_dir_for_frozen())
    log_event("Delta güncelleme uygulandı, uygulama yeniden başlatılıyor.")
    delta_update.restart_app(Path(sys.executable).resolve())
    _quit_app()


def finalize_update(path: str) -> None:
    """Worker'ın ürettiği yolu uygular: klasör = delta, dosya = tam kurulum."""
    if Path(path).is_dir():
        apply_delta_and_restart(path)
    else:
        launch_installer_and_exit(path)


def launch_installer_and_exit(installer_path: str) -> None:
    path_obj = Path(installer_path).resolve()
    if not path_obj.is_file():
        raise FileNotFoundError(f"Kurulum dosyası bulunamadı: {installer_path}")

    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        subprocess.Popen(
            [str(path_obj), *INSTALLER_ARGS],
            creationflags=flags,
            close_fds=True,
            env=delta_update.clean_environment(),
        )
    except OSError:
        # Yükseltilmiş yetki gerekiyorsa (UAC) sihirbazlı normal çalıştırma.
        os.startfile(str(path_obj))  # type: ignore[attr-defined]

    _quit_app()
