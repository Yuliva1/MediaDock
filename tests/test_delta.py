import hashlib
import http.server
import json
import re
import shutil
import socketserver
import threading
import zlib
from pathlib import Path

import pytest

from core import delta_update as du
from tools import make_release_assets as mra


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    ignore_range = False

    def log_message(self, *a):
        pass

    def do_GET(self):
        rng = self.headers.get("Range")
        path = Path(self.directory) / self.path.lstrip("/")
        data = path.read_bytes()
        if rng and not RangeHandler.ignore_range:
            m = re.match(r"bytes=(\d+)-(\d+)", rng)
            a, b = int(m.group(1)), int(m.group(2))
            chunk = data[a : b + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
        else:
            chunk = data
            self.send_response(200)
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


@pytest.fixture
def server(tmp_path):
    RangeHandler.ignore_range = False
    handler = lambda *a, **k: RangeHandler(*a, directory=str(tmp_path / "release"), **k)  # noqa: E731
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def make_app(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def build_release(tmp_path, files):
    dist = tmp_path / "dist"
    shutil.rmtree(dist, ignore_errors=True)
    make_app(dist, files)
    out = tmp_path / "release"
    out.mkdir(exist_ok=True)
    manifest = mra.build_zip_and_manifest(dist, out / "mediadock-app.zip", "2.0.0")
    return manifest


OLD = {
    "MediaDock.exe": b"exe-v1" * 5000,
    "_internal/big.dll": bytes(range(256)) * 4000,
    "_internal/same.bin": b"unchanged" * 3000,
    "_internal/removed.txt": b"gone",
}
NEW = {
    "MediaDock.exe": b"exe-v2" * 5000,
    "_internal/big.dll": OLD["_internal/big.dll"],
    "_internal/same.bin": OLD["_internal/same.bin"],
    "_internal/new/added.txt": b"hello",
}


def test_plan_and_worthwhile(tmp_path):
    manifest = build_release(tmp_path, NEW)
    app = tmp_path / "app"
    make_app(app, OLD)
    needed = {e["path"] for e in du.plan_changes(manifest, app)}
    assert needed == {"MediaDock.exe", "_internal/new/added.txt"}
    assert du.delta_is_worthwhile(manifest, du.plan_changes(manifest, app))


def test_full_delta_roundtrip(tmp_path, server):
    # Önceki sürüm: manifest'li kurulum (silinecek dosyayı bilebilmek için)
    old_manifest = build_release(tmp_path, OLD)
    app = tmp_path / "app"
    make_app(app, OLD)
    (app / du.INSTALLED_MANIFEST).write_text(json.dumps(old_manifest), encoding="utf-8")

    manifest = build_release(tmp_path, NEW)
    needed = du.plan_changes(manifest, app)
    staging = tmp_path / "staging"
    seen = []
    du.download_changed(manifest, needed, f"{server}/mediadock-app.zip", staging, lambda d, t, s: seen.append((d, t)))
    assert seen and seen[-1][0] == seen[-1][1]

    du.apply_staged(staging, app)
    for rel, data in NEW.items():
        assert (app / rel).read_bytes() == data
    assert not (app / "_internal/removed.txt").exists()
    assert (app / "_internal/removed.txt.old").exists()
    assert not staging.exists()

    assert du.cleanup_old_files(app) >= 2
    assert not list(app.rglob("*.old"))
    assert du.plan_changes(manifest, app) == []


def test_corrupted_download_is_rejected(tmp_path, server):
    manifest = build_release(tmp_path, NEW)
    app = tmp_path / "app"
    make_app(app, OLD)
    needed = du.plan_changes(manifest, app)
    zp = tmp_path / "release" / "mediadock-app.zip"
    raw = bytearray(zp.read_bytes())
    e = next(x for x in needed if x["path"] == "MediaDock.exe")
    raw[e["doff"] + 3] ^= 0xFF
    zp.write_bytes(bytes(raw))
    with pytest.raises(du.DeltaError):
        du.download_changed(manifest, needed, f"{server}/mediadock-app.zip", tmp_path / "st")


def test_server_without_range_falls_back(tmp_path, server):
    manifest = build_release(tmp_path, NEW)
    app = tmp_path / "app"
    make_app(app, OLD)
    RangeHandler.ignore_range = True
    with pytest.raises(du.DeltaError, match="Range"):
        du.download_changed(manifest, du.plan_changes(manifest, app), f"{server}/mediadock-app.zip", tmp_path / "st")


def test_cancel(tmp_path, server):
    manifest = build_release(tmp_path, NEW)
    app = tmp_path / "app"
    make_app(app, OLD)
    with pytest.raises(du.DeltaCancelled):
        du.download_changed(manifest, du.plan_changes(manifest, app), f"{server}/mediadock-app.zip", tmp_path / "st", cancel=lambda: True)


@pytest.mark.parametrize("bad", ["../evil.dll", "/abs/x", "a/../../b", "C:/x", "a\\b"])
def test_path_traversal_rejected(bad):
    with pytest.raises(du.DeltaError):
        du.safe_rel_path(bad)


def test_apply_rolls_back_on_failure(tmp_path, monkeypatch):
    manifest = build_release(tmp_path, NEW)
    app = tmp_path / "app"
    make_app(app, OLD)
    staging = tmp_path / "st"
    for e in manifest["files"]:
        p = staging / "files" / e["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(NEW[e["path"]])
    (staging / du.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    real_replace = du.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 4:
            raise OSError("disk dolu")
        return real_replace(src, dst)

    monkeypatch.setattr(du.os, "replace", flaky)
    with pytest.raises(OSError):
        du.apply_staged(staging, app)
    monkeypatch.setattr(du.os, "replace", real_replace)
    for rel, data in OLD.items():
        assert (app / rel).read_bytes() == data, rel
    assert not list(app.rglob("*.new"))


def test_clean_environment_drops_pyinstaller_vars(monkeypatch):
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "x")
    monkeypatch.setenv("_MEIPASS2", "y")
    env = du.clean_environment()
    assert "_PYI_APPLICATION_HOME_DIR" not in env and "_MEIPASS2" not in env


def test_manifest_hash_helpers():
    assert hashlib.sha256(zlib.decompress(zlib.compress(b"x"))).hexdigest() == hashlib.sha256(b"x").hexdigest()
