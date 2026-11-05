from __future__ import annotations

import logging
import re
import threading
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse

from config.paths import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_FILE = LOG_DIR / "mediadock.log"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_lock = threading.Lock()
_logger: logging.Logger | None = None


def _get_logger() -> logging.Logger | None:
    global _logger
    with _lock:
        if _logger is not None:
            return _logger
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
            logger = logging.getLogger("mediadock")
            logger.setLevel(logging.INFO)
            logger.propagate = False
            logger.addHandler(handler)
            _logger = logger
        except OSError:
            _logger = None
        return _logger


def _safe_url(url: str) -> str:
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}{p.path}"
    except Exception:
        return "?"


def _ytdlp_version() -> str:
    try:
        import yt_dlp.version

        return str(yt_dlp.version.__version__)
    except Exception:
        return "?"


def log_event(message: str) -> None:
    logger = _get_logger()
    if logger is not None:
        logger.info(_ANSI_RE.sub("", message))


def log_extraction_error(url: str, exc: BaseException) -> None:
    # Yalnızca bağlantı (sorgu parametresiz), yt-dlp sürümü ve hata metni yazılır.
    # Çerez, token veya kişisel veri loglanmaz.
    text = _ANSI_RE.sub("", str(exc)).replace("\r", " ").replace("\n", " | ")
    log_event(f"yt-dlp={_ytdlp_version()}  url={_safe_url(url)}  hata={text[:1500]}")


def log_exception(context: str, exc_type, exc, tb) -> None:
    import traceback

    text = "".join(traceback.format_exception(exc_type, exc, tb))
    log_event(f"YAKALANMAYAN HATA ({context})\n{text}")


def read_log_tail(max_lines: int = 60) -> str:
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(günlük dosyası henüz oluşmadı)"
    return "\n".join(lines[-max_lines:]) or "(günlük boş)"


def build_report(extra: dict[str, str] | None = None) -> str:
    import platform
    import sys

    from config.constants import APP_VERSION

    info = {
        "MediaDock": APP_VERSION,
        "yt-dlp": _ytdlp_version(),
        "Python": sys.version.split()[0],
        "Sistem": platform.platform(),
        "Paketli": str(bool(getattr(sys, "frozen", False))),
    }
    info.update(extra or {})
    header = "\n".join(f"{k}: {v}" for k, v in info.items())
    return f"{header}\n\n--- Son günlük kayıtları ---\n{read_log_tail()}\n"
