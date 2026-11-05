import zipfile
from pathlib import Path

import pytest

from core import downloader, updater, ytdlp_updater


def test_explorer_script_never_contains_the_file_path(monkeypatch, tmp_path):
    # Başlıktan gelen dosya adı PowerShell kodu olarak yorumlanmamalı.
    evil = tmp_path / "x'; Start-Process calc; '.mp4"
    evil.write_bytes(b"x")
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})

    monkeypatch.setattr(downloader.sys, "platform", "win32")
    monkeypatch.setattr("subprocess.run", fake_run)
    assert downloader._select_item_in_explorer(str(evil)) is True
    script = captured["cmd"][-1]
    assert "Start-Process" not in script and "calc" not in script
    assert captured["env"]["MEDIADOCK_TARGET"].endswith(evil.name)


def test_open_refuses_executable_extensions(monkeypatch, tmp_path):
    exe = tmp_path / "evil.exe"
    exe.write_bytes(b"MZ")
    started = []
    revealed = []
    monkeypatch.setattr(downloader.sys, "platform", "win32")
    monkeypatch.setattr(downloader.os, "startfile", lambda p: started.append(p), raising=False)
    monkeypatch.setattr(downloader, "reveal_in_explorer", lambda p: revealed.append(p) or True)
    assert downloader.open_file_in_default_player(str(exe)) is True
    assert started == [] and revealed == [str(exe)]

    ok = tmp_path / "clip.mp4"
    ok.write_bytes(b"x")
    downloader.open_file_in_default_player(str(ok))
    assert started == [str(ok)]


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://github.com/o/r/releases/download/v1/a.exe", True),
        ("https://objects.githubusercontent.com/x/a.exe", True),
        ("https://release-assets.githubusercontent.com/x/a.exe", True),
        ("http://github.com/o/r/a.exe", False),
        ("https://evil.example.com/a.exe", False),
        ("https://github.com.evil.example.com/a.exe", False),
        ("https://githubusercontent.com.evil.io/a.exe", False),
    ],
)
def test_asset_url_trust(url, ok):
    assert updater._is_trusted_asset_url(url, "api.github.com") is ok


def test_repo_slug_validation():
    with pytest.raises(ValueError):
        updater.check_for_updates("../../etc/passwd")
    with pytest.raises(ValueError):
        updater.check_for_updates("a/b/c")


def test_ytdlp_wheel_host_and_hash_required(tmp_path):
    with pytest.raises(RuntimeError):
        ytdlp_updater._download_wheel("https://evil.example.com/yt_dlp.whl", "a" * 64, tmp_path / "w.whl")
    with pytest.raises(RuntimeError):
        ytdlp_updater._download_wheel("http://files.pythonhosted.org/x.whl", "a" * 64, tmp_path / "w.whl")
    with pytest.raises(RuntimeError):
        ytdlp_updater._download_wheel("https://files.pythonhosted.org/x.whl", "", tmp_path / "w.whl")


def test_ytdlp_wheel_rejects_path_traversal_and_bombs(tmp_path, monkeypatch):
    bad = tmp_path / "bad.whl"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("yt_dlp/../evil.py", "x")
    with pytest.raises(RuntimeError):
        ytdlp_updater._extract_package(bad, tmp_path / "out")

    big = tmp_path / "big.whl"
    with zipfile.ZipFile(big, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("yt_dlp/__init__.py", "0" * 4096)
    monkeypatch.setattr(ytdlp_updater, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(RuntimeError):
        ytdlp_updater._extract_package(big, tmp_path / "out2")


def test_scanner_survives_files_vanishing(tmp_path, monkeypatch):
    from core.scanner import _FolderScanWorker

    (tmp_path / "a.mp4").write_bytes(b"x")

    class FakeDB:
        def get_known_file_paths(self):
            return set()

    results = []
    w = _FolderScanWorker(str(tmp_path), FakeDB(), None)
    w.finished.connect(results.append)
    errors = []
    w.error.connect(errors.append)
    orig = Path.stat

    def flaky(self, *a, **k):
        if self.name == "a.mp4":
            raise FileNotFoundError(self)
        return orig(self, *a, **k)

    monkeypatch.setattr(Path, "stat", flaky)
    w.run()
    assert not errors and results == [0]
