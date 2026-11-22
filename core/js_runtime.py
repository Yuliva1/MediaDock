"""YouTube için JavaScript çalıştırıcısı (Deno / Node / Bun) seçimi.

yt-dlp, YouTube'un imza ve "n" korumalarını çözmek için harici bir JavaScript
çalıştırıcısına ihtiyaç duyar; yoksa bazı biçimler (çoğu zaman yüksek
çözünürlükler) eksik gelir. Öncelik: pakete eklenen ``bin/deno.exe`` ->
sistemdeki deno -> node -> bun.
"""

from __future__ import annotations

import shutil
import sys
from functools import lru_cache
from pathlib import Path

_EXE = ".exe" if sys.platform == "win32" else ""


def _bin_dirs() -> list[Path]:
    from config.paths import BIN_DIR, BUNDLE_ROOT

    dirs = [BUNDLE_ROOT / "bin", Path(sys.executable).resolve().parent / "bin", BIN_DIR]
    out: list[Path] = []
    for d in dirs:
        if d not in out:
            out.append(d)
    return out


@lru_cache(maxsize=1)
def runtimes() -> dict[str, dict[str, str]]:
    """yt-dlp ``js_runtimes`` seçeneği için yapılandırma."""
    found: dict[str, dict[str, str]] = {}
    for d in _bin_dirs():
        deno = d / f"deno{_EXE}"
        if deno.is_file():
            found["deno"] = {"path": str(deno.resolve())}
            break
    if "deno" not in found and shutil.which("deno"):
        found["deno"] = {}
    for name in ("node", "bun"):
        if shutil.which(name):
            found[name] = {}
    return found or {"deno": {}}


def describe() -> tuple[bool, str]:
    """(hazır_mı, kullanıcıya gösterilecek kısa açıklama)."""
    rts = runtimes()
    available = []
    for name, cfg in rts.items():
        if cfg.get("path") or shutil.which(name):
            available.append(f"{name} (paket içi)" if cfg.get("path") else name)
    if available:
        return True, "YouTube JavaScript çözücü: " + ", ".join(available)
    return False, (
        "YouTube için JavaScript çalıştırıcısı (Deno) bulunamadı; bazı yüksek çözünürlükler eksik gelebilir."
    )
