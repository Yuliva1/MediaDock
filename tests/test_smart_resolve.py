from __future__ import annotations

import pytest

from core import smart_resolve as sr
from core import x_photos


def test_item_fragment_roundtrip():
    url = "https://www.instagram.com/p/ABC123/"
    tagged = sr.with_item(url, 3)
    assert tagged.endswith("#mediadock-item=3")
    assert sr.split_item(tagged) == (url, 3)
    # Tekrar etiketlemek eski sırayı değiştirir, birikmez.
    assert sr.split_item(sr.with_item(tagged, 5)) == (url, 5)
    assert sr.split_item(url) == (url, None)
    # Başka parçalar korunur.
    assert sr.split_item("https://x.com/a#foo") == ("https://x.com/a#foo", None)


@pytest.mark.parametrize(
    "msg",
    [
        "ERROR: [Instagram] Cf6s: There is no video in this post",
        "ERROR: [generic] No video formats found!",
        "ERROR: [twitter] 1: No video could be found in this tweet",
    ],
)
def test_no_video_errors_are_detected(msg):
    assert sr.is_no_video_error(msg)


def test_no_video_detection_ignores_other_errors():
    assert not sr.is_no_video_error("HTTP Error 404: Not Found")


def test_best_image_prefers_largest_area():
    entry = {
        "thumbnails": [
            {"url": "s", "width": 320, "height": 320},
            {"url": "l", "width": 1440, "height": 1800},
            {"url": "m", "width": 1080, "height": 1080},
        ]
    }
    assert sr.best_image(entry) == ("l", 1440, 1800)


def test_best_image_without_sizes_takes_last():
    # Instagram'ın giriş yapılmamış yanıtında boyut yok; yt-dlp en iyiyi sona koyar.
    entry = {"thumbnails": [{"url": "a"}, {"url": "b"}, {"url": "best"}]}
    assert sr.best_image(entry)[0] == "best"


def test_entry_has_video():
    assert sr.entry_has_video({"formats": [{"vcodec": "h264", "ext": "mp4"}]})
    assert not sr.entry_has_video({"formats": [], "thumbnails": [{"url": "x"}]})


def test_pick_entry_bounds():
    info = {"entries": [{"id": 1}, {"id": 2}]}
    assert sr.pick_entry(info, 2) == {"id": 2}
    assert sr.pick_entry(info, None) == {"id": 1}
    with pytest.raises(IndexError):
        sr.pick_entry(info, 3)


def test_summarize():
    assert sr.summarize(["image", "video", "image"]) == "2 fotoğraf + 1 video"
    assert sr.summarize(["video"]) == "1 video"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://x.com/user/status/1577855540407197696", "1577855540407197696"),
        ("https://twitter.com/user/status/1577855540407197696/photo/1", "1577855540407197696"),
        ("https://mobile.twitter.com/i/web/status/123", "123"),
        ("https://www.instagram.com/p/abc/", None),
        ("https://example.com/status/123", None),
    ],
)
def test_tweet_id_from_url(url, expected):
    assert x_photos.tweet_id_from_url(url) == expected


def test_syndication_token_matches_ytdlp():
    jsinterp = pytest.importorskip("yt_dlp.jsinterp")
    import math

    tid = "1577855540407197696"
    expected = jsinterp.js_number_to_string((int(tid) / 1e15) * math.pi, 36).translate(
        str.maketrans(dict.fromkeys("0."))
    )
    assert x_photos.syndication_token(tid) == expected
    assert x_photos.syndication_token(tid)
