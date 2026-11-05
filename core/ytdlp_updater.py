from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import re
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Callable
from pathlib import Path

import requests
from PySide6.QtCore import QObject, Signal

from config.paths import DATA_DIR
from core.logutil import log_event

PKG_DIR: Path = DATA_DIR / "ytdlp_pkg"
_STAMP_FILE: Path = DATA_DIR / "ytdlp_last_check.txt"
PYPI_JSON_URL = "https://pypi.org/pypi/yt-dlp/json"
CHECK_INTERVAL_SECONDS = 24 * 3600
MAX_WHEEL_BYTES = 40 * 1024 * 1024
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
WHEEL_HOST = "files.pythonhosted.org"

_VERSION_RE = re.compile(r"""__version__\s*=\s*['"]([^'"]+)['"]""")
_work_lock = threading.Lock()
_last_attempt = 0.0


def version_tuple(version: str) -> tuple[int, ...]:
    # PyPI nightly sürümleri ".devN" ile biter; bu ek sürüm karşılaştırmasını bozmasın.
    cleaned = re.sub(r"[._-]?(dev|rc|a|b)\d*$", "", version.strip())
    return tuple(int(x) for x in re.findall(r"\d+", cleaned))


def is_newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def override_version() -> str:
    try:
        text = (PKG_DIR / "yt_dlp" / "version.py").read_text(encoding="utf-8")
    except OSError:
        return ""
    m = _VERSION_RE.search(text)
    return m.group(1) if m else ""


def running_version() -> str:
    try:
        import yt_dlp.version

        return str(yt_dlp.version.__version__)
    except Exception:
        return ""


class _OverrideFinder(importlib.abc.MetaPathFinder):
    # PyInstaller'ın gömülü yt_dlp'si yerine DATA_DIR/ytdlp_pkg içindeki sürümü yükler.
    # sys.meta_path'in başında durduğu için sıralama farklarından etkilenmez.

    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname == "yt_dlp":
            return importlib.machinery.PathFinder.find_spec(fullname, [str(PKG_DIR)], target)
        if fullname.startswith("yt_dlp.") and path:
            return importlib.machinery.PathFinder.find_spec(fullname, path, target)
        return None


_finder: _OverrideFinder | None = None


def activate_override() -> bool:
    # yt_dlp ilk kez import edilmeden ÖNCE çağrılmalıdır.
    global _finder
    if _finder is not None or "yt_dlp" in sys.modules:
        return False
    if not (PKG_DIR / "yt_dlp" / "__init__.py").is_file():
        return False
    _finder = _OverrideFinder()
    sys.meta_path.insert(0, _finder)
    return True


def disable_override() -> bool:
    # Güncel paket bozuksa devreden çıkarır; gömülü sürüm yedek olarak kullanılır.
    global _finder
    removed = False
    if _finder is not None:
        try:
            sys.meta_path.remove(_finder)
        except ValueError:
            pass
        _finder = None
        removed = True
    for name in [m for m in sys.modules if m == "yt_dlp" or m.startswith("yt_dlp.")]:
        del sys.modules[name]
    if PKG_DIR.exists():
        bad = PKG_DIR.with_name(PKG_DIR.name + ".bad")
        shutil.rmtree(bad, ignore_errors=True)
        try:
            PKG_DIR.rename(bad)
            removed = True
        except OSError:
            shutil.rmtree(PKG_DIR, ignore_errors=True)
            removed = True
    if removed:
        log_event("Güncel yt-dlp paketi yüklenemedi; gömülü sürüme dönüldü.")
    return removed


def fetch_latest_release() -> tuple[str, str, str]:
    # (sürüm, wheel_url, sha256) döndürür. Nightly (pre-release) sürümler dahildir.
    resp = requests.get(PYPI_JSON_URL, timeout=20)
    resp.raise_for_status()
    releases: dict[str, list[dict]] = resp.json().get("releases", {})

    best: tuple[tuple[int, ...], str, str, str] | None = None
    for ver, files in releases.items():
        wheel = next(
            (
                f
                for f in files
                if f.get("packagetype") == "bdist_wheel" and not f.get("yanked")
            ),
            None,
        )
        if not wheel:
            continue
        key = version_tuple(ver)
        if not key:
            continue
        if best is None or key > best[0]:
            best = (key, ver, str(wheel.get("url") or ""), str((wheel.get("digests") or {}).get("sha256") or ""))
    if best is None or not best[2]:
        raise RuntimeError("PyPI üzerinde yt-dlp sürümü bulunamadı.")
    return best[1], best[2], best[3]


def check_latest() -> tuple[bool, str, str]:
    # (güncelleme_var, çalışan_sürüm, mesaj)
    current = running_version() or "Bilinmiyor"
    pending = override_version()
    latest, _, _ = fetch_latest_release()
    pending_ready = bool(pending) and is_newer(pending, current)
    baseline = pending if pending_ready else current
    if is_newer(latest, baseline):
        return True, current, f"Yeni sürüm mevcut: {latest} (Mevcut: {current})"
    if pending_ready:
        return False, current, f"yt-dlp {pending} indirildi; MediaDock'u yeniden başlatınca etkinleşir."
    return False, current, f"yt-dlp güncel ({current})."


def _download_wheel(url: str, expected_sha256: str, dest: Path) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != WHEEL_HOST:
        raise RuntimeError("Paket adresi beklenen PyPI sunucusundan değil; işlem durduruldu.")
    if not expected_sha256:
        raise RuntimeError("Paket için doğrulama özeti (SHA-256) bulunamadı; işlem durduruldu.")
    sha = hashlib.sha256()
    size = 0
    with requests.get(url, stream=True, timeout=30) as resp:
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_WHEEL_BYTES:
                    raise RuntimeError("İndirilen paket beklenenden büyük; işlem durduruldu.")
                sha.update(chunk)
                fh.write(chunk)
    if sha.hexdigest().lower() != expected_sha256.lower():
        raise RuntimeError("İndirilen paketin doğrulama özeti (SHA-256) eşleşmedi.")


def _extract_package(wheel_path: Path, target_root: Path) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        if sum(i.file_size for i in zf.infolist()) > MAX_UNPACKED_BYTES:
            raise RuntimeError("Paket açıldığında beklenenden çok büyük; işlem durduruldu.")
        for info in zf.infolist():
            parts = Path(info.filename).parts
            if not parts or parts[0] != "yt_dlp" or info.is_dir():
                continue
            if ".." in parts or Path(info.filename).is_absolute():
                raise RuntimeError("Paket içinde geçersiz dosya yolu bulundu.")
            out = target_root.joinpath(*parts)
            out.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, out.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    if not (target_root / "yt_dlp" / "__init__.py").is_file() or not (target_root / "yt_dlp" / "version.py").is_file():
        raise RuntimeError("İndirilen paket eksik veya bozuk.")


def _swap_in(new_dir: Path) -> None:
    old_dir = PKG_DIR.with_name(PKG_DIR.name + ".old")
    shutil.rmtree(old_dir, ignore_errors=True)
    had_old = PKG_DIR.exists()
    if had_old:
        PKG_DIR.rename(old_dir)
    try:
        new_dir.rename(PKG_DIR)
    except OSError:
        if had_old and old_dir.exists() and not PKG_DIR.exists():
            old_dir.rename(PKG_DIR)
        raise
    shutil.rmtree(old_dir, ignore_errors=True)


def install_latest() -> tuple[bool, str, str]:
    # (yüklendi_mi, sürüm, mesaj). Başarısızlıkta çalışan paket korunur, istisna fırlatmaz.
    with _work_lock:
        current = running_version() or "Bilinmiyor"
        try:
            latest, url, sha256 = fetch_latest_release()
            pending = override_version()
            pending_ready = bool(pending) and is_newer(pending, current)
            baseline = pending if pending_ready else current
            if not is_newer(latest, baseline):
                if pending_ready:
                    return False, current, f"yt-dlp {pending} indirildi; MediaDock'u yeniden başlatınca etkinleşir."
                return False, current, f"yt-dlp güncel ({current})."

            DATA_DIR.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix="ytdlp_new_", dir=str(DATA_DIR)))
            try:
                wheel_file = staging / "pkg.whl"
                _download_wheel(url, sha256, wheel_file)
                new_root = staging / "root"
                new_root.mkdir()
                _extract_package(wheel_file, new_root)
                wheel_file.unlink(missing_ok=True)
                _swap_in(new_root)
            finally:
                shutil.rmtree(staging, ignore_errors=True)

            log_event(f"yt-dlp güncellendi: {current} -> {latest}")
            return True, latest, f"yt-dlp {latest} indirildi. Etkinleşmesi için MediaDock'u yeniden başlatın."
        except Exception as exc:
            log_event(f"yt-dlp güncellemesi başarısız: {exc}")
            return False, current, f"Güncelleme başarısız: {exc}"


def _read_stamp() -> float:
    try:
        return float(_STAMP_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0.0


def _write_stamp() -> None:
    try:
        _STAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STAMP_FILE.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def run_in_background(
    on_done: Callable[[bool, str, str], None] | None = None,
    min_interval: float = CHECK_INTERVAL_SECONDS,
) -> bool:
    # Son denemeden beri min_interval geçmediyse hiçbir şey yapmaz. UI'ı bloklamaz.
    global _last_attempt
    now = time.time()
    if now - max(_read_stamp(), _last_attempt) < min_interval:
        return False
    if _work_lock.locked():
        return False
    _last_attempt = now

    def worker() -> None:
        ok, ver, msg = install_latest()
        if not msg.startswith("Güncelleme başarısız"):
            _write_stamp()
        if on_done is not None:
            try:
                on_done(ok, ver, msg)
            except Exception:
                pass

    threading.Thread(target=worker, name="ytdlp-updater", daemon=True).start()
    return True


class YtDlpAutoUpdater(QObject):
    message = Signal(str, str)

    def start(self) -> None:
        def done(installed: bool, _ver: str, msg: str) -> None:
            if installed:
                self.message.emit(msg, "success")

        run_in_background(done, CHECK_INTERVAL_SECONDS)
