"""X (Twitter) gönderilerindeki fotoğrafları çözer.

yt-dlp X'te yalnızca videoları döndürür; fotoğraflı tweet'lerde "No video could
be found" der, karışık tweet'lerde fotoğrafları atlar. X'in herkese açık
gömme (syndication) uç noktası, giriş gerektirmeden tweet'teki tüm medyayı
verir. yt-dlp de aynı uç noktayı yedek olarak kullanır.

Fotoğraf adresleri (``pbs.twimg.com/media/...``) kalıcıdır, süresi dolmaz.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

SYNDICATION_URL = "https://cdn.syndication.twimg.com/tweet-result"
_STATUS_RE = re.compile(r"/(?:i/web/)?(?:[^/]+/)?status(?:es)?/(\d+)")
X_HOSTS = ("x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com", "fxtwitter.com", "vxtwitter.com")


@dataclass
class XMedia:
    kind: str  # "image" | "video"
    url: str  # görsel için doğrudan adres, video için tweet adresi
    thumbnail_url: str
    width: int = 0
    height: int = 0
    video_index: int = 0  # yt-dlp oynatma listesindeki video sırası (yalnızca video)


@dataclass
class XPost:
    tweet_id: str
    text: str
    author: str
    media: list[XMedia]

    @property
    def has_photos(self) -> bool:
        return any(m.kind == "image" for m in self.media)


def tweet_id_from_url(url: str) -> str | None:
    try:
        p = urlparse(url)
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in X_HOSTS):
        return None
    m = _STATUS_RE.search(p.path)
    return m.group(1) if m else None


def _to_base36_fraction(val: float) -> str:
    """JavaScript ``Number.prototype.toString(36)`` eşdeğeri (pozitif sayılar için)."""
    try:
        from yt_dlp.jsinterp import js_number_to_string

        return js_number_to_string(val, 36)
    except Exception:
        digits = "0123456789abcdefghijklmnopqrstuvwxyz"
        ip, fp = int(val), val - int(val)
        out = ""
        while True:
            out = digits[ip % 36] + out
            ip //= 36
            if not ip:
                break
        if fp:
            out += "."
            for _ in range(11):
                fp *= 36
                d = int(fp)
                out += digits[d]
                fp -= d
                if not fp:
                    break
        return out


def syndication_token(tweet_id: str) -> str:
    raw = _to_base36_fraction((int(tweet_id) / 1e15) * math.pi)
    return raw.translate(str.maketrans(dict.fromkeys("0.")))


def _orig(url: str) -> str:
    # pbs.twimg.com/media/ABC.jpg -> en yüksek kalite
    if "pbs.twimg.com/media/" in url and "name=" not in url:
        return url + ("&" if "?" in url else "?") + "name=orig"
    return url


def fetch_post(url: str, timeout: float = 10.0) -> XPost | None:
    tweet_id = tweet_id_from_url(url)
    if not tweet_id:
        return None
    resp = requests.get(
        SYNDICATION_URL,
        params={"id": tweet_id, "token": syndication_token(tweet_id)},
        headers={"User-Agent": "Googlebot"},
        timeout=timeout,
    )
    if resp.status_code != 200 or not resp.text.strip():
        return None
    data = resp.json()
    details = list(data.get("mediaDetails") or [])
    quoted = data.get("quoted_tweet") or {}
    details += list(quoted.get("mediaDetails") or [])

    media: list[XMedia] = []
    video_no = 0
    for d in details:
        kind = str(d.get("type") or "")
        size = (d.get("original_info") or {})
        w, h = int(size.get("width") or 0), int(size.get("height") or 0)
        thumb = str(d.get("media_url_https") or "")
        if kind == "photo":
            if thumb:
                media.append(XMedia("image", _orig(thumb), thumb, w, h))
        elif kind in ("video", "animated_gif"):
            video_no += 1
            media.append(XMedia("video", url, thumb, w, h, video_index=video_no))

    user = data.get("user") or {}
    author = str(user.get("screen_name") or user.get("name") or "")
    text = re.sub(r"\s*https://t\.co/\S+\s*$", "", str(data.get("text") or "")).strip()
    return XPost(tweet_id=tweet_id, text=text, author=author, media=media)
