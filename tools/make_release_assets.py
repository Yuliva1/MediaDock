"""Release dosyalarını üretir: mediadock-app.zip, manifest.json, sha256sums.txt.

Kullanım:
    python tools/make_release_assets.py [--dist dist/MediaDock]
        [--installer installer/MediaDock-Setup.exe] [--out release]

``mediadock-app.zip`` içindeki her dosya ayrı ayrı sıkıştırılır; manifest her
dosyanın zip içindeki veri konumunu (doff) saklar. İstemci böylece yalnızca
değişen dosyaları HTTP Range ile indirebilir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.constants import APP_VERSION  # noqa: E402

ASSET_ZIP = "mediadock-app.zip"
ASSET_MANIFEST = "manifest.json"
ASSET_SUMS = "sha256sums.txt"
FIXED_TIME = (2020, 1, 1, 0, 0, 0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_zip_and_manifest(dist: Path, out_zip: Path, version: str) -> dict:
    files = sorted(p for p in dist.rglob("*") if p.is_file())
    if not files:
        raise SystemExit(f"Dosya bulunamadı: {dist}")

    entries: list[dict] = []
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for p in files:
            rel = p.relative_to(dist).as_posix()
            data = p.read_bytes()
            info = zipfile.ZipInfo(rel, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
            entries.append({"path": rel, "size": len(data), "sha256": sha256_bytes(data)})

    by_name = {e["path"]: e for e in entries}
    with zipfile.ZipFile(out_zip) as zf, open(out_zip, "rb") as raw:
        for info in zf.infolist():
            raw.seek(info.header_offset)
            hdr = raw.read(30)
            if hdr[:4] != b"PK\x03\x04":
                raise SystemExit(f"Bozuk yerel başlık: {info.filename}")
            nlen, elen = struct.unpack("<HH", hdr[26:30])
            e = by_name[info.filename]
            e["doff"] = info.header_offset + 30 + nlen + elen
            e["csize"] = info.compress_size
            e["method"] = info.compress_type

    return {
        "version": version,
        "zip": ASSET_ZIP,
        "zip_size": out_zip.stat().st_size,
        "files": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=str(ROOT / "dist" / "MediaDock"))
    ap.add_argument("--installer", default=str(ROOT / "installer" / "MediaDock-Setup.exe"))
    ap.add_argument("--out", default=str(ROOT / "release"))
    ap.add_argument("--version", default=APP_VERSION)
    args = ap.parse_args()

    dist, out = Path(args.dist), Path(args.out)
    if not dist.is_dir():
        raise SystemExit(f"dist klasörü yok: {dist}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    zip_path = out / ASSET_ZIP
    manifest = build_zip_and_manifest(dist, zip_path, args.version)
    manifest_path = out / ASSET_MANIFEST
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")

    release_files = [zip_path, manifest_path]
    installer = Path(args.installer)
    if installer.is_file():
        shutil.copy2(installer, out / installer.name)
        release_files.append(out / installer.name)
    else:
        print(f"Uyarı: kurulum dosyası yok, atlandı: {installer}")

    lines = [f"{sha256_path(p)}  {p.name}" for p in release_files]
    (out / ASSET_SUMS).write_text("\n".join(lines) + "\n", encoding="utf-8")

    total = sum(e["size"] for e in manifest["files"])
    print(f"Sürüm {args.version}: {len(manifest['files'])} dosya, {total/1e6:.1f} MB (zip {manifest['zip_size']/1e6:.1f} MB)")
    print(f"Çıktı: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
