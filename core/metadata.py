from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import requests
from PIL import Image
from PySide6.QtCore import QObject, QThread, Signal

from config.constants import (
    IMAGE_FORMATS,
    SUPPORTED_IMAGE_EXTENSIONS,
    resolve_platform_info,
)
from config.paths import THUMBNAILS_DIR
from core.extractor import extract

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

CLIPBOARD_MEDIA_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "kick.com",
    "x.com",
    "twitter.com",
    "instagram.com",
    "tiktok.com",
    "twitch.tv",
    "reddit.com",
    "redd.it",
    "facebook.com",
    "fb.watch",
    "vimeo.com",
    "dailymotion.com",
    "soundcloud.com",
    "bilibili.com",
    "pinterest.com",
    "pinimg.com",
    "imgur.com",
    "artstation.com",
    "unsplash.com",
)


@dataclass
class GalleryItem:
    index: int
    url: str
    thumbnail_url: str
    media_type: str
    title: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    ext: str = ""
    selected: bool = True
    thumbnail_path: str = ""


@dataclass
class VideoMetadata:
    url: str
    webpage_url: str
    video_id: str
    title: str
    uploader: str
    duration: float
    platform: str
    platform_color: str
    extractor: str
    thumbnail_url: str = ""
    thumbnail_path: str = ""
    has_video: bool = True
    has_audio: bool = True
    available_heights: set[int] = field(default_factory=set)
    available_containers: set[str] = field(default_factory=lambda: {"MP4", "MKV", "WEBM"})
    max_height: int = 0
    is_live: bool = False
    media_type: str = "video"
    image_width: int = 0
    image_height: int = 0
    file_size: int = 0
    is_gallery: bool = False
    gallery_items: list[GalleryItem] = field(default_factory=list)


def sanitize_filename(raw_title: str, fallback: str = "MediaDock_Media", max_length: int = 130) -> str:
    if not raw_title:
        return fallback

    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', " ", raw_title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")

    if not cleaned:
        cleaned = fallback

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" ._-")

    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    return cleaned or fallback


def format_duration(seconds: float | int | None) -> str:
    if not seconds or seconds <= 0:
        return "00:00"
    total = int(round(float(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_bytes(size_bytes: int | float | None) -> str:
    if not size_bytes or size_bytes <= 0:
        return "—"
    val = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if val < 1024.0 or unit == "TB":
            if unit in ("B", "KB"):
                return f"{val:.0f} {unit}"
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return "—"


def clean_social_url(raw_url: str) -> str:
    try:
        parsed = urlparse(raw_url)
        host = parsed.netloc.lower()
        if "instagram.com" in host:
            m = re.match(r"^/(p|reel|tv)/([^/?#]+)", parsed.path)
            if m:
                return f"https://www.instagram.com/{m.group(1)}/{m.group(2)}/"
        elif "twitter.com" in host or "x.com" in host:
            m = re.match(r"^/([^/?#]+/status/[0-9]+)", parsed.path)
            if m:
                return f"https://x.com/{m.group(1)}"
    except Exception:
        pass
    return raw_url


def extract_urls_from_text(text: str) -> list[str]:
    if not text:
        return []
    matches = re.findall(r"https?://[^\s<>\"']+", text.strip())
    seen: set[str] = set()
    urls: list[str] = []
    for raw in matches:
        cleaned = raw.rstrip(".,;)]}")
        cleaned = clean_social_url(cleaned)
        parsed = urlparse(cleaned)
        if parsed.scheme in ("http", "https") and parsed.netloc and cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    return urls


def is_direct_image_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        path = unquote(parsed.path).lower()
        if any(path.endswith(ext) for ext in SUPPORTED_IMAGE_EXTENSIONS):
            return True
        query = parsed.query.lower()
        if any(hint in query for hint in ("format=png", "format=jpg", "format=webp", "ext=jpg", "ext=png")):
            return True
        netloc = parsed.netloc.lower()
        if any(h in netloc for h in ("cdninstagram.com", "fbcdn.net", "twimg.com", "pinimg.com", "imgur.com")):
            if any(ext in path for ext in (".jpg", ".jpeg", ".png", ".webp", ".heic", ".ico")):
                return True
    except Exception:
        pass
    return False


def is_probable_media_url(text: str, strict_clipboard: bool = False) -> bool:
    urls = extract_urls_from_text(text)
    if len(urls) != 1:
        return False
    parsed = urlparse(urls[0])
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    lower_path = parsed.path.lower()
    if lower_path.endswith((".pdf", ".zip", ".rar", ".7z", ".tar", ".gz", ".exe", ".msi", ".css", ".js")):
        return False

    if any(lower_path.endswith(ext) for ext in SUPPORTED_IMAGE_EXTENSIONS):
        return True

    if not strict_clipboard:
        return "." in host

    return any(host == dom or host.endswith(f".{dom}") for dom in CLIPBOARD_MEDIA_DOMAINS)


def _bucket_resolution(width: int | None, height: int | None, format_note: str = "") -> int | None:
    note_match = re.search(r"(2160|1440|1080|720|480|360)p", format_note or "", re.IGNORECASE)
    if note_match:
        return int(note_match.group(1))

    w = int(width or 0)
    h = int(height or 0)
    if w <= 0 and h <= 0:
        return None

    if w > 0 and h > 0:
        if h > w:
            ref = w
        else:
            ref = max(h, int(round(w * 9 / 16)))
    else:
        ref = max(w, h)

    if ref >= 1900:
        return 2160
    if ref >= 1300:
        return 1440
    if ref >= 950:
        return 1080
    if ref >= 640:
        return 720
    if ref >= 420:
        return 480
    if ref >= 300:
        return 360
    return None


def cache_thumbnail(thumbnail_url: str, key_seed: str) -> str:
    if not thumbnail_url:
        return ""
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(key_seed.encode("utf-8", errors="ignore")).hexdigest()[:16]
    out_path = THUMBNAILS_DIR / f"thumb_{digest}.jpg"
    if out_path.is_file() and out_path.stat().st_size > 0:
        return str(out_path)

    try:
        resp = requests.get(
            thumbnail_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            stream=True,
            timeout=8,
        )
        if resp.status_code == 200:
            tmp_t = THUMBNAILS_DIR / f"tmp_{digest}.dat"
            with open(tmp_t, "wb") as f:
                for c in resp.iter_content(chunk_size=32768):
                    f.write(c)
            with Image.open(tmp_t) as img:
                rgb = img.convert("RGB")
                rgb.thumbnail((480, 270), Image.Resampling.LANCZOS)
                rgb.save(out_path, format="JPEG", quality=82, optimize=True)
            try:
                tmp_t.unlink(missing_ok=True)
            except OSError:
                pass
            return str(out_path)
    except Exception:
        pass
    return ""


def translate_ytdlp_error(err: Exception | str) -> str:
    raw = str(err or "")
    clean = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    lower = clean.lower()

    if "instagram" in lower and "empty media response" in lower:
        return (
            "Instagram bu görseli oturum açmadan sunmuyor. Hesabınızın güvenliği için kişisel çerezleriniz çekilmemiştir. "
            "Görseli indirmek için tarayıcıda sağ tıklayıp 'Resim adresini kopyala' diyerek MediaDock'a yapıştırabilirsiniz."
        )
    if "private" not in lower and any(k in lower for k in ("not a bot", "sign in", "login", "log in")):
        return (
            "Bu içerik için giriş gerekiyor. Firefox, Edge veya Chrome'da ilgili platforma giriş yap, "
            "tarayıcıyı kapat ve tekrar dene; MediaDock oturumu otomatik kullanır."
        )
    if any(k in lower for k in ("private video", "private content", "this video is private")):
        return "Bu içerik gizli (özel) olarak ayarlanmış. Yalnızca herkese açık veya erişim izniniz olan içerikler indirilebilir."
    if any(k in lower for k in ("sign in", "login required", "logged-in", "cookies", "authentication", "members-only")):
        return "Bu içerik platform girişi, yaş doğrulaması veya abonelik gerektiriyor. Yalnızca erişim izni gerektirmeyen içerikler indirilebilir."
    if any(k in lower for k in ("not available in your country", "geo", "blocked in your country")):
        return "Bu video bulunduğunuz bölge/ülke için erişime kapatılmış."
    if any(k in lower for k in ("video unavailable", "has been removed", "does not exist", "404", "not found")):
        return "İçerik bulunamadı veya yayından kaldırılmış. Lütfen bağlantının doğruluğunu kontrol edin."
    if "unsupported url" in lower:
        return "Bu bağlantı desteklenen bir medya kaynağı olarak algılanamadı."
    if any(k in lower for k in ("getaddrinfo failed", "timed out", "connection", "network is unreachable")):
        return "Ağ bağlantısı kurulamadı. İnternet bağlantınızı kontrol edip tekrar deneyin."
    if "403" in lower or "forbidden" in lower:
        return "Platform erişimi reddetti (HTTP 403). Bağlantı geçici olarak kısıtlanmış olabilir veya oturum gerekebilir."
    if "429" in lower or "too many requests" in lower:
        return "Platform çok fazla istek algıladı (HTTP 429). Kısa bir süre bekleyip tekrar deneyin."

    clean = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[^:]*:\s*)?", "", clean).strip()
    if len(clean) > 220:
        clean = clean[:220].rstrip() + "..."
    return clean or "Medya bilgileri alınırken beklenmeyen bir hata oluştu."


class HTMLImageScraper(HTMLParser):

    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.image_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        src = ""
        if tag == "img":
            src = d.get("src") or d.get("data-src") or d.get("data-original") or d.get("data-lazy-src") or ""
        elif tag == "source":
            src = d.get("srcset") or d.get("src") or ""
            if src and "," in src:
                src = src.split(",")[-1].strip().split(" ")[0]
        elif tag == "meta" and d.get("property") in ("og:image", "twitter:image", "image"):
            src = d.get("content") or ""

        if src and not src.startswith("data:"):
            full = urljoin(self.base_url, src)
            parsed = urlparse(full)
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in SUPPORTED_IMAGE_EXTENSIONS) or "format=" in parsed.query.lower():
                if not any(ign in path_lower for ign in ("/icon", "/avatar", "/emoji", "favicon", "tracking", "pixel")):
                    if full not in self.image_urls:
                        self.image_urls.append(full)


def scrape_webpage_gallery(url: str) -> list[GalleryItem]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, stream=True, timeout=8)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "").lower()
        if "html" not in content_type:
            return []

        chunks = []
        tot = 0
        for chunk in resp.iter_content(chunk_size=32768):
            chunks.append(chunk)
            tot += len(chunk)
            if tot >= 524288:
                break
        html_text = b"".join(chunks).decode("utf-8", errors="ignore")

        parser = HTMLImageScraper(url)
        parser.feed(html_text)

        title_m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE)
        page_title = sanitize_filename(title_m.group(1).strip() if title_m else "Web Galeri", fallback="Web Galeri")

        items: list[GalleryItem] = []
        for i, img_url in enumerate(parser.image_urls[:60], 1):
            items.append(
                GalleryItem(
                    index=i,
                    url=img_url,
                    thumbnail_url=img_url,
                    media_type="image",
                    title=f"{page_title} - {i:02d}",
                    width=0,
                    height=0,
                    duration=0.0,
                    ext=Path(urlparse(img_url).path).suffix.lstrip(".").lower() or "jpg",
                    selected=True,
                )
            )
        return items
    except Exception:
        return []


def fetch_image_metadata(url: str) -> VideoMetadata:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, stream=True, timeout=10)
    resp.raise_for_status()

    content_len = int(resp.headers.get("Content-Length") or 0)

    buf = io.BytesIO()
    for chunk in resp.iter_content(chunk_size=65536):
        buf.write(chunk)
        if buf.tell() >= 2097152:
            break

    buf.seek(0)
    width, height = 0, 0
    try:
        with Image.open(buf) as im:
            width, height = im.size
    except Exception:
        pass

    if content_len == 0:
        content_len = buf.tell()

    parsed = urlparse(url)
    raw_name = Path(unquote(parsed.path)).name
    stem = Path(raw_name).stem if raw_name else "Görsel"
    title = sanitize_filename(stem, fallback="Web Görseli")

    platform_name, platform_color = resolve_platform_info(None, url)
    if platform_name == "Web Medya":
        platform_name = "Web Görsel"
        platform_color = "#38BDF8"

    video_id = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    cached_thumb = cache_thumbnail(url, f"{platform_name}_{video_id}")

    return VideoMetadata(
        url=url,
        webpage_url=url,
        video_id=video_id,
        title=title,
        uploader=parsed.netloc or platform_name,
        duration=0.0,
        platform=platform_name,
        platform_color=platform_color,
        extractor="image_direct",
        thumbnail_url=url,
        thumbnail_path=cached_thumb or url,
        has_video=False,
        has_audio=False,
        available_heights={height} if height else set(),
        available_containers=set(IMAGE_FORMATS),
        max_height=height,
        is_live=False,
        media_type="image",
        image_width=width,
        image_height=height,
        file_size=content_len,
    )


def fetch_video_metadata(url: str, ffmpeg_location: str | None = None) -> VideoMetadata:
    if is_direct_image_url(url):
        try:
            return fetch_image_metadata(url)
        except Exception:
            pass

    try:
        probe = requests.head(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=3.0,
            allow_redirects=True,
        )
        ctype = probe.headers.get("Content-Type", "").lower()
        if ctype.startswith("image/"):
            return fetch_image_metadata(url)
    except Exception:
        pass

    is_yt = any(h in url.lower() for h in ("youtube.com", "youtu.be"))
    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": is_yt and ("list=" not in url.lower()),
        "skip_download": True,
        "socket_timeout": 15,
    }
    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    info: dict[str, Any] | None = None
    try:
        info = extract(url, ydl_opts)
    except Exception:
        info = None

    if not info:
        scraped_items = scrape_webpage_gallery(url)
        if len(scraped_items) >= 2:
            parsed = urlparse(url)
            platform_name, platform_color = resolve_platform_info(None, url)
            cached_thumb = cache_thumbnail(scraped_items[0].thumbnail_url, f"gallery_{parsed.netloc}")
            return VideoMetadata(
                url=url,
                webpage_url=url,
                video_id=hashlib.sha1(url.encode("utf-8")).hexdigest()[:10],
                title=scraped_items[0].title.split(" - ")[0],
                uploader=parsed.netloc,
                duration=0.0,
                platform=platform_name,
                platform_color=platform_color,
                extractor="web_gallery",
                thumbnail_url=scraped_items[0].thumbnail_url,
                thumbnail_path=cached_thumb,
                has_video=False,
                has_audio=False,
                available_heights=set(),
                available_containers=set(IMAGE_FORMATS),
                max_height=0,
                is_live=False,
                media_type="gallery",
                is_gallery=True,
                gallery_items=scraped_items,
            )
        raise RuntimeError("Medya bilgileri alınamadı.")

    entries = [e for e in info.get("entries", []) if e] if info.get("entries") else []
    extractor = str(info.get("extractor_key") or info.get("extractor") or "")
    webpage_url = str(info.get("webpage_url") or url)
    platform_name, platform_color = resolve_platform_info(extractor, webpage_url)

    if len(entries) > 1:
        base_title = str(info.get("title") or info.get("description") or "Çoklu Paylaşım").splitlines()[0].strip()
        if len(base_title) > 120:
            base_title = base_title[:117] + "..."
        uploader = str(info.get("uploader") or info.get("channel") or platform_name)
        video_id = str(info.get("id") or hashlib.md5(webpage_url.encode("utf-8")).hexdigest()[:10])

        gallery_items: list[GalleryItem] = []
        for idx, entry in enumerate(entries, 1):
            e_url = str(entry.get("url") or entry.get("webpage_url") or url)
            fmts = entry.get("formats") or []
            if fmts:
                best = fmts[-1]
                e_url = str(best.get("url") or e_url)

            t_url = str(entry.get("thumbnail") or "")
            if not t_url and entry.get("thumbnails"):
                t_cands = [t.get("url") for t in entry["thumbnails"] if t.get("url")]
                if t_cands:
                    t_url = str(t_cands[-1])

            raw_vcodec = entry.get("vcodec")
            dur = float(entry.get("duration") or 0.0)
            fmt_ext = str(entry.get("ext") or "").lower()
            is_vid = (raw_vcodec != "none" and raw_vcodec is not None) or dur > 0 or fmt_ext in ("mp4", "webm", "mkv", "mov")
            m_type = "video" if is_vid else "image"

            if not t_url and not is_vid:
                t_url = e_url

            w = int(entry.get("width") or 0)
            h = int(entry.get("height") or 0)
            item_title = f"{base_title} - {idx:02d}"

            gallery_items.append(
                GalleryItem(
                    index=idx,
                    url=e_url,
                    thumbnail_url=t_url,
                    media_type=m_type,
                    title=item_title,
                    width=w,
                    height=h,
                    duration=dur,
                    ext=fmt_ext or ("mp4" if is_vid else "jpg"),
                    selected=True,
                )
            )

        cached_thumb = cache_thumbnail(gallery_items[0].thumbnail_url, f"{platform_name}_{video_id}")
        return VideoMetadata(
            url=url,
            webpage_url=webpage_url,
            video_id=video_id,
            title=base_title,
            uploader=uploader,
            duration=sum(i.duration for i in gallery_items),
            platform=platform_name,
            platform_color=platform_color,
            extractor=extractor,
            thumbnail_url=gallery_items[0].thumbnail_url,
            thumbnail_path=cached_thumb,
            has_video=any(i.media_type == "video" for i in gallery_items),
            has_audio=any(i.media_type == "video" for i in gallery_items),
            available_heights=set(),
            available_containers=set(IMAGE_FORMATS) | {"MP4"},
            max_height=max((i.height for i in gallery_items), default=0),
            is_live=False,
            media_type="gallery",
            is_gallery=True,
            gallery_items=gallery_items,
        )

    if entries:
        info = entries[0]

    formats = info.get("formats") or []
    available_heights: set[int] = set()
    has_video = False
    has_audio = False
    max_height = 0

    audio_only_exts = {"mp3", "m4a", "wav", "ogg", "opus", "flac", "aac"}
    for fmt in formats:
        raw_vcodec = fmt.get("vcodec")
        raw_acodec = fmt.get("acodec")
        fmt_ext = str(fmt.get("ext") or info.get("ext") or "").lower()
        w = fmt.get("width")
        h = fmt.get("height")
        note = str(fmt.get("format_note") or fmt.get("format_id") or "")

        is_video_stream = (raw_vcodec != "none") and not (raw_vcodec is None and fmt_ext in audio_only_exts)
        is_audio_stream = raw_acodec != "none"

        if is_video_stream:
            has_video = True
            bucket = _bucket_resolution(w, h, note)
            if bucket:
                available_heights.add(bucket)
                max_height = max(max_height, bucket)
        if is_audio_stream:
            has_audio = True

    top_bucket = _bucket_resolution(info.get("width"), info.get("height"), str(info.get("format_note") or ""))
    if top_bucket:
        has_video = True
        available_heights.add(top_bucket)
        max_height = max(max_height, top_bucket)

    top_ext = str(info.get("ext") or "").lower()
    if not formats:
        if top_ext in audio_only_exts:
            has_video = False
            has_audio = True
        elif top_ext in SUPPORTED_IMAGE_EXTENSIONS:
            has_video = False
            has_audio = False
        else:
            has_video = True
            has_audio = True

    is_pure_image = (not has_video) and (not has_audio) and (top_ext in SUPPORTED_IMAGE_EXTENSIONS or "image" in extractor.lower())

    thumb_url = str(info.get("thumbnail") or "")
    if not thumb_url and info.get("thumbnails"):
        thumbs = [t.get("url") for t in info["thumbnails"] if t.get("url")]
        if thumbs:
            thumb_url = str(thumbs[-1])

    video_id = str(info.get("id") or hashlib.md5(webpage_url.encode("utf-8")).hexdigest()[:10])
    cached_thumb = cache_thumbnail(thumb_url, f"{platform_name}_{video_id}")

    title = str(info.get("title") or info.get("description") or "Adsız Medya").splitlines()[0].strip()
    if len(title) > 160:
        title = title[:157] + "..."

    uploader = str(
        info.get("uploader")
        or info.get("channel")
        or info.get("creator")
        or info.get("uploader_id")
        or platform_name
    )

    duration = float(info.get("duration") or 0.0)
    is_live = bool(info.get("is_live"))

    if is_pure_image:
        containers = set(IMAGE_FORMATS)
        media_type = "image"
    else:
        containers = {"MP4", "MKV", "WEBM"} if ffmpeg_location else {"MP4"}
        media_type = "video" if has_video else "audio"

    return VideoMetadata(
        url=url,
        webpage_url=webpage_url,
        video_id=video_id,
        title=title,
        uploader=uploader,
        duration=duration,
        platform=platform_name,
        platform_color=platform_color,
        extractor=extractor,
        thumbnail_url=thumb_url,
        thumbnail_path=cached_thumb,
        has_video=has_video,
        has_audio=has_audio or has_video,
        available_heights=available_heights,
        available_containers=containers,
        max_height=max_height,
        is_live=is_live,
        media_type=media_type,
    )


class MetadataFetchWorker(QObject):

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, ffmpeg_location: str | None = None) -> None:
        super().__init__()
        self.url = url
        self.ffmpeg_location = ffmpeg_location

    def run(self) -> None:
        try:
            meta = fetch_video_metadata(self.url, self.ffmpeg_location)
            self.finished.emit(meta)
        except Exception as exc:
            self.failed.emit(translate_ytdlp_error(exc))


class MetadataController(QObject):

    loading_started = Signal(str)
    metadata_ready = Signal(object)
    metadata_error = Signal(str)

    def __init__(self, ffmpeg_location_provider: Any, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._get_ffmpeg_loc = ffmpeg_location_provider
        self._active_threads: list[tuple[QThread, MetadataFetchWorker]] = []
        self._request_seq = 0

    def fetch(self, url: str) -> None:
        clean_url = url.strip()
        if not clean_url:
            return
        self._request_seq += 1
        req_id = self._request_seq
        self.loading_started.emit(clean_url)

        thread = QThread()
        worker = MetadataFetchWorker(clean_url, self._get_ffmpeg_loc())
        worker.moveToThread(thread)

        def on_done(meta: VideoMetadata) -> None:
            if req_id == self._request_seq:
                self.metadata_ready.emit(meta)
            thread.quit()

        def on_err(msg: str) -> None:
            if req_id == self._request_seq:
                self.metadata_error.emit(msg)
            thread.quit()

        def on_thread_finished() -> None:
            self._active_threads[:] = [(t, w) for (t, w) in self._active_threads if t is not thread]
            worker.deleteLater()
            thread.deleteLater()

        thread.started.connect(worker.run)
        worker.finished.connect(on_done)
        worker.failed.connect(on_err)
        thread.finished.connect(on_thread_finished)

        self._active_threads.append((thread, worker))
        thread.start()

    def invalidate_pending(self) -> None:
        self._request_seq += 1
