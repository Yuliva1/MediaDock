"""Yalnızca değişen dosyaları indiren (delta) güncelleme motoru.

Qt'ye bağımlı değildir; böylece tek başına test edilebilir.

Çalışma mantığı:
  * Release'te ``mediadock-app.zip`` (her dosya ayrı sıkıştırılmış) ve
    ``manifest.json`` (her dosyanın SHA-256, boyut ve zip içindeki konumu) bulunur.
  * İstemci, kurulu dosyaların hash'ini manifest ile karşılaştırır ve yalnızca
    farklı olanları HTTP Range istekleriyle zip'in içinden çeker.
  * Dosyalar önce geçici klasöre indirilip doğrulanır, sonra yerine konur.
    Çalışan exe/DLL'ler Windows'ta silinemez ama yeniden adlandırılabilir; bu
    yüzden eski dosya ``.old`` olarak kenara alınır ve sonraki açılışta temizlenir.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import requests

MANIFEST_NAME = "manifest.json"
INSTALLED_MANIFEST = ".mediadock-manifest.json"
OLD_SUFFIX = ".old"
NEW_SUFFIX = ".new"
WORTHWHILE_RATIO = 0.6

ProgressCb = Callable[[int, int, float], None]


class DeltaError(RuntimeError):
    pass


class DeltaCancelled(DeltaError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def app_dir_for_frozen() -> Path:
    return Path(sys.executable).resolve().parent


def check_writable(app_dir: Path) -> None:
    try:
        fd, tmp = tempfile.mkstemp(prefix=".wtest", dir=str(app_dir))
        os.close(fd)
        os.unlink(tmp)
    except OSError as exc:
        raise DeltaError(f"Uygulama klasörüne yazılamıyor: {exc}") from exc


def safe_rel_path(rel: str) -> PurePosixPath:
    p = PurePosixPath(rel)
    if not rel or p.is_absolute() or ".." in p.parts or "\\" in rel or ":" in rel:
        raise DeltaError(f"Manifestte güvensiz dosya yolu: {rel!r}")
    return p


def _local_path(app_dir: Path, rel: str) -> Path:
    return app_dir.joinpath(*safe_rel_path(rel).parts)


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise DeltaError("Manifest geçersiz: dosya listesi yok.")
    for e in files:
        safe_rel_path(str(e.get("path", "")))
        for key in ("size", "csize", "doff", "sha256", "method"):
            if key not in e:
                raise DeltaError(f"Manifest girdisi eksik alan içeriyor: {key}")
        if e["method"] not in (0, 8):
            raise DeltaError("Desteklenmeyen sıkıştırma yöntemi.")
    return files


def plan_changes(manifest: dict[str, Any], app_dir: Path) -> list[dict[str, Any]]:
    """Kurulu dosyalarla karşılaştırıp indirilmesi gereken girdileri döndürür."""
    needed: list[dict[str, Any]] = []
    for e in validate_manifest(manifest):
        target = _local_path(app_dir, e["path"])
        try:
            if target.is_file() and target.stat().st_size == int(e["size"]):
                if sha256_file(target) == str(e["sha256"]).lower():
                    continue
        except OSError:
            pass
        needed.append(e)
    return needed


def delta_is_worthwhile(manifest: dict[str, Any], needed: list[dict[str, Any]]) -> bool:
    total = sum(int(e["csize"]) for e in manifest["files"])
    if total <= 0:
        return False
    return sum(int(e["csize"]) for e in needed) <= total * WORTHWHILE_RATIO


def _fetch_range(session: requests.Session, url: str, start: int, length: int, cancel: Callable[[], bool]) -> bytes:
    headers = {"Range": f"bytes={start}-{start + length - 1}", "Accept-Encoding": "identity"}
    resp = session.get(url, headers=headers, stream=True, timeout=30)
    try:
        if resp.status_code != 206:
            raise DeltaError(f"Sunucu Range isteğini desteklemiyor (HTTP {resp.status_code}).")
        buf = bytearray()
        for chunk in resp.iter_content(chunk_size=131072):
            if cancel():
                raise DeltaCancelled("Güncelleme indirme işlemi kullanıcı tarafından iptal edildi.")
            buf += chunk
        if len(buf) != length:
            raise DeltaError("Eksik veri alındı.")
        return bytes(buf)
    finally:
        resp.close()


def _decode(entry: dict[str, Any], raw: bytes) -> bytes:
    if entry["method"] == 0:
        return raw
    try:
        return zlib.decompress(raw, -15)
    except zlib.error as exc:
        raise DeltaError(f"{entry['path']}: sıkıştırma hatası ({exc})") from exc


def download_changed(
    manifest: dict[str, Any],
    needed: list[dict[str, Any]],
    zip_url: str,
    staging: Path,
    on_progress: ProgressCb | None = None,
    cancel: Callable[[], bool] = lambda: False,
) -> None:
    """``needed`` listesindeki dosyaları zip'ten çekip ``staging/files`` altına yazar."""
    import time

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    files_dir = staging / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    total = sum(int(e["csize"]) for e in needed)
    done = 0
    t0 = time.monotonic()
    last = 0.0

    with requests.Session() as session:
        session.headers["User-Agent"] = "MediaDock-Updater"
        for e in needed:
            if cancel():
                raise DeltaCancelled("Güncelleme indirme işlemi kullanıcı tarafından iptal edildi.")
            csize = int(e["csize"])
            raw = _fetch_range(session, zip_url, int(e["doff"]), csize, cancel) if csize > 0 else b""
            data = _decode(e, raw)
            if len(data) != int(e["size"]) or hashlib.sha256(data).hexdigest() != str(e["sha256"]).lower():
                raise DeltaError(f"{e['path']}: SHA-256 doğrulaması başarısız.")
            dest = _local_path(files_dir, e["path"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            done += csize
            now = time.monotonic()
            if on_progress and now - last >= 0.1:
                last = now
                on_progress(done, total, done / max(now - t0, 0.001))

    (staging / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    if on_progress:
        on_progress(total, total, 0.0)


def apply_staged(staging: Path, app_dir: Path) -> None:
    """İndirilen dosyaları yerine koyar; hata olursa hepsini geri alır."""
    manifest = json.loads((staging / MANIFEST_NAME).read_text(encoding="utf-8"))
    files = validate_manifest(manifest)
    files_dir = staging / "files"
    check_writable(app_dir)

    moved: list[tuple[Path, Path | None]] = []  # (hedef, yedek)
    try:
        for e in files:
            src = _local_path(files_dir, e["path"])
            if not src.is_file():
                continue
            target = _local_path(app_dir, e["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_new = target.with_name(target.name + NEW_SUFFIX)
            shutil.copy2(src, tmp_new)
            backup: Path | None = None
            if target.exists():
                backup = target.with_name(target.name + OLD_SUFFIX)
                if backup.exists():
                    try:
                        backup.unlink()
                    except OSError:
                        backup = target.with_name(f"{target.name}.{os.getpid()}{OLD_SUFFIX}")
                os.replace(target, backup)
            moved.append((target, backup))
            os.replace(tmp_new, target)

        _remove_obsolete(app_dir, manifest)
        (app_dir / INSTALLED_MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    except Exception:
        for target, backup in reversed(moved):
            try:
                if target.exists():
                    target.unlink()
            except OSError:
                pass
            if backup is not None and backup.exists():
                try:
                    os.replace(backup, target)
                except OSError:
                    pass
        for p in app_dir.rglob(f"*{NEW_SUFFIX}"):
            try:
                p.unlink()
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _remove_obsolete(app_dir: Path, new_manifest: dict[str, Any]) -> None:
    """Önceki sürümde olup yenisinde olmayan dosyaları siler (önceki manifest varsa)."""
    prev_path = app_dir / INSTALLED_MANIFEST
    if not prev_path.is_file():
        return
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
        old_paths = {str(e["path"]) for e in prev.get("files", [])}
    except (OSError, ValueError, KeyError):
        return
    keep = {str(e["path"]) for e in new_manifest["files"]}
    for rel in old_paths - keep:
        try:
            target = _local_path(app_dir, rel)
        except DeltaError:
            continue
        try:
            if target.is_file():
                os.replace(target, target.with_name(target.name + OLD_SUFFIX))
        except OSError:
            pass


def cleanup_old_files(app_dir: Path) -> int:
    """Önceki güncellemeden kalan ``.old`` / ``.new`` dosyalarını temizler."""
    removed = 0
    try:
        for pattern in (f"*{OLD_SUFFIX}", f"*{NEW_SUFFIX}"):
            for p in app_dir.rglob(pattern):
                try:
                    p.unlink()
                    removed += 1
                except OSError:
                    pass  # hâlâ kilitli olabilir; sonraki açılışta denenir
    except OSError:
        pass
    return removed


def clean_environment() -> dict[str, str]:
    """PyInstaller'ın bıraktığı değişkenleri temizlenmiş ortam (yeniden başlatma için)."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("_PYI") or key in ("_MEIPASS2", "PYTHONHOME", "PYTHONPATH"):
            env.pop(key, None)
    return env


def restart_app(exe_path: Path) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        env=clean_environment(),
        creationflags=flags,
        close_fds=True,
    )
