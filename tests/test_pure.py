from core.metadata import clean_social_url, extract_urls_from_text, translate_ytdlp_error
from core.updater import parse_semver, parse_sha256sums


def test_semver_ordering():
    assert parse_semver("v1.0.10") > parse_semver("1.0.9")
    assert parse_semver("1.1.0") > parse_semver("1.0.99")
    assert parse_semver("1.0.5") == parse_semver("V1.0.5")
    assert parse_semver("garbage") == (0, 0, 0)


def test_sha256sums_parsing():
    h = "a" * 64
    text = f"{h}  MediaDock-Setup.exe\n{h.upper()} *Manifest.json\nbozuk satir\n"
    sums = parse_sha256sums(text)
    assert sums["mediadock-setup.exe"] == h
    assert sums["manifest.json"] == h
    assert len(sums) == 2


def test_clean_social_url():
    assert clean_social_url("https://www.instagram.com/reel/ABC123/?igsh=xyz") == "https://www.instagram.com/reel/ABC123/"
    assert clean_social_url("https://twitter.com/u/status/123?s=20") == "https://x.com/u/status/123"
    assert clean_social_url("https://example.com/a?b=1") == "https://example.com/a?b=1"


def test_extract_urls_dedup_and_trailing_punct():
    text = "bak https://example.com/a. ve https://example.com/a, tekrar https://example.com/b)"
    assert extract_urls_from_text(text) == ["https://example.com/a", "https://example.com/b"]
    assert extract_urls_from_text("") == []


def test_translate_error_ansi_stripped():
    msg = translate_ytdlp_error("\x1b[0;31mERROR:\x1b[0m this video is private")
    assert "\x1b" not in msg and "gizli" in msg


IG_NO_FORMATS = (
    "ERROR: [Instagram] DdhtmSuMYnj: No video formats found!; please report this issue on  "
    "https://github.com/yt-dlp/yt-dlp/issues?q= , filling out the appropriate issue template. "
    "Confirm you are on the latest version using  yt-dlp -U"
)


def test_instagram_no_video_formats_is_not_blamed_on_engine():
    msg = translate_ytdlp_error(IG_NO_FORMATS)
    assert "Instagram" in msg and "yt-dlp" in msg and "güncellemek sorunu çözmez" in msg
    assert "güncel değil" not in msg


def test_no_video_formats_does_not_trigger_engine_refresh():
    from core.metadata import _looks_like_extractor_failure

    assert not _looks_like_extractor_failure(IG_NO_FORMATS.lower())
    assert _looks_like_extractor_failure("unable to extract video data; please report this issue")


def test_generic_extractor_failure_message_depends_on_engine_freshness(monkeypatch):
    import core.metadata as md

    raw = "ERROR: [site] x: Unable to extract video data; please report this issue"
    monkeypatch.setattr(md, "_ytdlp_is_fresh", lambda *a, **k: True)
    assert "güncel görünüyor" in md.translate_ytdlp_error(raw)
    monkeypatch.setattr(md, "_ytdlp_is_fresh", lambda *a, **k: False)
    assert "güncel değil" in md.translate_ytdlp_error(raw)
