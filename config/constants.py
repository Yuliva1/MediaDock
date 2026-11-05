from __future__ import annotations

APP_NAME = "MediaDock"
APP_SUBTITLE = "Universal Media Downloader"
APP_VERSION = "1.0.4"
APP_ORGANIZATION = "Yuliva"
APP_AUTHOR = "Yuliva"
DEFAULT_UPDATE_REPO = "Yuliva1/MediaDock"

VIDEO_FORMATS: list[str] = ["MP4", "MKV", "WEBM"]
DEFAULT_VIDEO_FORMAT = "MP4"

IMAGE_FORMATS: list[str] = ["Orijinal", "PNG", "JPG", "WEBP"]
DEFAULT_IMAGE_FORMAT = "Orijinal"

VIDEO_QUALITIES: list[tuple[str, int | None]] = [
    ("En iyi kalite", None),
    ("2160p (4K)", 2160),
    ("1440p", 1440),
    ("1080p", 1080),
    ("720p", 720),
    ("480p", 480),
    ("360p", 360),
]
DEFAULT_VIDEO_QUALITY = "En iyi kalite"

AUDIO_MODES: list[tuple[str, str]] = [
    ("Videolu indirme", "video"),
    ("MP3", "mp3"),
    ("M4A", "m4a"),
    ("WAV", "wav"),
]
DEFAULT_AUDIO_MODE = "video"

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".opus"}
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".svg"}
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_IMAGE_EXTENSIONS

PLATFORM_DISPLAY_MAP: dict[str, tuple[str, str]] = {
    "youtube": ("YouTube", "#FF4E45"),
    "youtubetab": ("YouTube", "#FF4E45"),
    "kick": ("Kick", "#53FC18"),
    "kickclips": ("Kick", "#53FC18"),
    "kickvod": ("Kick", "#53FC18"),
    "twitter": ("X (Twitter)", "#E7E9EA"),
    "x": ("X (Twitter)", "#E7E9EA"),
    "instagram": ("Instagram", "#E1306C"),
    "tiktok": ("TikTok", "#25F4EE"),
    "twitch": ("Twitch", "#9146FF"),
    "twitchvod": ("Twitch", "#9146FF"),
    "twitchclips": ("Twitch", "#9146FF"),
    "reddit": ("Reddit", "#FF5700"),
    "facebook": ("Facebook", "#1877F2"),
    "vimeo": ("Vimeo", "#1AB7EA"),
    "dailymotion": ("Dailymotion", "#0066DC"),
    "soundcloud": ("SoundCloud", "#FF5500"),
    "bilibili": ("BiliBili", "#00A1D6"),
    "pinterest": ("Pinterest", "#E60023"),
    "linkedin": ("LinkedIn", "#0A66C2"),
    "imgur": ("Imgur", "#1BB76E"),
    "artstation": ("ArtStation", "#13AFF0"),
    "unsplash": ("Unsplash", "#F0F0F2"),
}

PRIORITY_PLATFORMS: list[str] = [
    "YouTube",
    "Kick",
    "X (Twitter)",
    "Instagram",
    "TikTok",
    "Twitch",
    "Reddit",
    "Facebook",
    "Vimeo",
    "Pinterest",
]


def resolve_platform_info(extractor: str | None, url: str = "") -> tuple[str, str]:
    if extractor:
        clean_key = extractor.lower().split(":")[0].replace("_", "").replace("-", "")
        for prefix, info in PLATFORM_DISPLAY_MAP.items():
            if clean_key == prefix or clean_key.startswith(prefix):
                return info
        readable = extractor.split(":")[0].replace("_", " ").strip()
        if readable.lower() != "generic":
            return (readable.title() if readable.islower() else readable, "#929298")

    lower_url = (url or "").lower()
    url_hints = [
        (("youtube.com", "youtu.be"), ("YouTube", "#FF4E45")),
        (("kick.com",), ("Kick", "#53FC18")),
        (("twitter.com", "x.com"), ("X (Twitter)", "#E7E9EA")),
        (("instagram.com",), ("Instagram", "#E1306C")),
        (("tiktok.com",), ("TikTok", "#25F4EE")),
        (("twitch.tv",), ("Twitch", "#9146FF")),
        (("reddit.com", "redd.it"), ("Reddit", "#FF5700")),
        (("facebook.com", "fb.watch"), ("Facebook", "#1877F2")),
        (("vimeo.com",), ("Vimeo", "#1AB7EA")),
        (("pinterest.com", "pinimg.com"), ("Pinterest", "#E60023")),
        (("imgur.com",), ("Imgur", "#1BB76E")),
        (("artstation.com",), ("ArtStation", "#13AFF0")),
        (("unsplash.com",), ("Unsplash", "#F0F0F2")),
    ]
    for domains, info in url_hints:
        if any(domain in lower_url for domain in domains):
            return info

    return ("Web Medya", "#929298")
