"""Akıllı bağlantı çözücü yardımcıları.

yt-dlp, içinde video olmayan gönderilerde (Instagram fotoğrafı, fotoğraflı
carousel vb.) "There is no video in this post" / "No video formats found"
hatası verir; oysa gönderinin tam çözünürlüklü görsel adreslerini zaten
çözmüştür. ``ignore_no_formats_error`` ile aynı istek tekrarlanınca bu bilgi
kaybolmaz ve görseller indirilebilir.

Galeri öğeleri, süresi dolan CDN adresleri yerine kaynak gönderi adresi + öğe
sırası olarak saklanır (``...#mediadock-item=3``). Adres indirme anında yeniden
çözülür; böylece sırada bekleyen ya da yeniden başlatmadan sonra devam eden
indirmeler de çalışır. Parça (#...) sunucuya hiç gönderilmez.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

ITEM_KEY = "mediadock-item="

# yt-dlp'nin "video yok ama içerik var" anlamına gelen hata ifadeleri.
NO_VIDEO_MARKERS = (
    "no video formats found",
    "there is no video in this post",
    "no video could be found",
    "this post does not contain a video",
)

VIDEO_EXTS = {"mp4", "webm", "mkv", "mov", "m4v", "flv", "avi", "ts", "m3u8"}
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "heic", "avif"}


def is_no_video_error(exc: BaseException | str) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in NO_VIDEO_MARKERS)


def with_item(url: str, index: int) -> str:
    """Kaynak adrese galeri öğe sırasını (1'den başlar) ekler."""
    clean, _ = split_item(url)
    p = urlparse(clean)
    return urlunparse(p._replace(fragment=f"{ITEM_KEY}{int(index)}"))


def split_item(url: str) -> tuple[str, int | None]:
    """``(parçasız_adres, öğe_sırası|None)`` döndürür."""
    p = urlparse(url)
    m = re.fullmatch(rf"{re.escape(ITEM_KEY)}(\d+)", p.fragment or "")
    if not m:
        return url, None
    return urlunparse(p._replace(fragment="")), int(m.group(1))


def entry_has_video(entry: dict[str, Any]) -> bool:
    for f in entry.get("formats") or []:
        vcodec = f.get("vcodec")
        ext = str(f.get("ext") or "").lower()
        if vcodec not in (None, "none") or (vcodec is None and ext in VIDEO_EXTS):
            return True
    if float(entry.get("duration") or 0) > 0:
        return True
    return bool(entry.get("url")) and str(entry.get("ext") or "").lower() in VIDEO_EXTS


def best_image(entry: dict[str, Any]) -> tuple[str, int, int]:
    """Girdideki en büyük görselin ``(adres, genişlik, yükseklik)`` bilgisi.

    yt-dlp küçük resimleri kötüden iyiye sıralar; boyut bilgisi varsa alana
    göre, yoksa listedeki son (en iyi) öğe seçilir.
    """
    thumbs = [t for t in (entry.get("thumbnails") or []) if isinstance(t, dict) and t.get("url")]
    if thumbs:
        sized = [t for t in thumbs if (t.get("width") or 0) and (t.get("height") or 0)]
        if sized:
            best = max(sized, key=lambda t: int(t["width"]) * int(t["height"]))
            return str(best["url"]), int(best["width"]), int(best["height"])
        last = thumbs[-1]
        return str(last["url"]), int(last.get("width") or 0), int(last.get("height") or 0)
    direct = str(entry.get("url") or "")
    if direct and str(entry.get("ext") or "").lower() in IMAGE_EXTS:
        return direct, int(entry.get("width") or 0), int(entry.get("height") or 0)
    thumb = str(entry.get("thumbnail") or "")
    return thumb, 0, 0


def pick_entry(info: dict[str, Any], index: int | None) -> dict[str, Any]:
    entries = [e for e in (info.get("entries") or []) if e]
    if not entries:
        return info
    if index is None:
        return entries[0]
    if not 1 <= index <= len(entries):
        raise IndexError(f"Gönderide {index}. öğe yok (toplam {len(entries)}).")
    return entries[index - 1]


def summarize(kinds: list[str]) -> str:
    """["image","video","image"] -> "2 fotoğraf + 1 video"."""
    n_img = sum(1 for k in kinds if k == "image")
    n_vid = sum(1 for k in kinds if k == "video")
    parts = []
    if n_img:
        parts.append(f"{n_img} fotoğraf")
    if n_vid:
        parts.append(f"{n_vid} video")
    return " + ".join(parts) or f"{len(kinds)} öğe"
