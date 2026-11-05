from __future__ import annotations

import threading
from typing import Any
from urllib.parse import urlparse

from config.paths import DATA_DIR

BROWSERS = ("edge", "chrome", "firefox", "brave", "opera", "vivaldi")

AUTH_MARKERS = (
    "sign in",
    "not a bot",
    "log in",
    "login",
    "logged-in",
    "logged in",
    "cookies",
    "confirm your age",
    "age-restricted",
    "age restricted",
    "authentication",
    "members-only",
    "rate-limit",
)

COOKIE_READ_MARKERS = (
    "cookie",
    "could not find",
    "dpapi",
    "decrypt",
    "database is locked",
    "permission denied",
)

_COOKIE_OPTION_KEYS = ("cookiesfrombrowser", "cookiefile")

_state_file = DATA_DIR / "auth_browser.txt"
_lock = threading.Lock()
_remembered: str | None = None
_loaded = False
_cookies_enabled = False


def set_cookies_enabled(enabled: bool) -> None:
    global _cookies_enabled
    _cookies_enabled = bool(enabled)


def cookies_enabled() -> bool:
    return _cookies_enabled


def is_instagram_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return "instagram.com" in host or "cdninstagram.com" in host


def _load_remembered() -> str | None:
    global _remembered, _loaded
    with _lock:
        if not _loaded:
            _loaded = True
            try:
                value = _state_file.read_text(encoding="utf-8").strip()
                _remembered = value if value in BROWSERS else None
            except OSError:
                _remembered = None
        return _remembered


def _remember(browser: str) -> None:
    global _remembered
    with _lock:
        _remembered = browser
        try:
            _state_file.parent.mkdir(parents=True, exist_ok=True)
            _state_file.write_text(browser, encoding="utf-8")
        except OSError:
            pass


def _message(exc: BaseException) -> str:
    return str(exc).lower()


def is_auth_error(exc: BaseException) -> bool:
    msg = _message(exc)
    return any(marker in msg for marker in AUTH_MARKERS)


def _is_cookie_read_error(exc: BaseException) -> bool:
    msg = _message(exc)
    return any(marker in msg for marker in COOKIE_READ_MARKERS)


def _import_yt_dlp() -> Any:
    try:
        import yt_dlp

        return yt_dlp
    except Exception:
        # Güncellenmiş paket bozuksa gömülü sürüme dön.
        from core import ytdlp_updater

        if not ytdlp_updater.disable_override():
            raise
        import yt_dlp

        return yt_dlp


def _run(url: str, opts: dict[str, Any], download: bool) -> dict[str, Any] | None:
    yt_dlp = _import_yt_dlp()

    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=download)


def _browser_order() -> list[str]:
    known = _load_remembered()
    order = [known] if known else []
    order.extend(b for b in BROWSERS if b != known)
    return order


def extract(url: str, opts: dict[str, Any], download: bool = False) -> dict[str, Any] | None:
    instagram = is_instagram_url(url)
    # Instagram için çerez seçenekleri ne olursa olsun yt-dlp'ye hiç iletilmez.
    safe_opts = {k: v for k, v in opts.items() if k not in _COOKIE_OPTION_KEYS} if instagram else opts

    try:
        return _run(url, safe_opts, download)
    except Exception as first_exc:
        # Tarayıcı çerezleri yalnızca kullanıcı açıkça izin verdiyse ve Instagram dışı sitelerde denenir.
        if instagram or not _cookies_enabled or not is_auth_error(first_exc):
            raise
        first_error = first_exc

    for browser in _browser_order():
        try:
            info = _run(url, {**opts, "cookiesfrombrowser": (browser,)}, download)
        except Exception as exc:
            if is_auth_error(exc) or _is_cookie_read_error(exc):
                continue
            raise
        _remember(browser)
        return info

    raise first_error
