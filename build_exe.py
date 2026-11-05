from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ISCC_CANDIDATES = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
)


def generate_app_ico() -> Path:
    ico_dir = ROOT / "assets" / "icons"
    ico_dir.mkdir(parents=True, exist_ok=True)
    ico_path = ico_dir / "mediadock.ico"

    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = 24
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=108,
        fill=(23, 23, 25, 255),
        outline=(52, 52, 60, 255),
        width=8,
    )
    draw.polygon([(196, 148), (356, 240), (196, 332)], fill=(224, 91, 91, 255))
    draw.rounded_rectangle([156, 376, 356, 402], radius=13, fill=(240, 240, 242, 220))

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)
    return ico_path


def copy_ffmpeg_into_dist() -> None:
    from core.ffmpeg import FFmpegManager

    fm = FFmpegManager()
    if not fm.is_available:
        print("FFmpeg bulunamadi, pakete eklenmedi.")
        return

    bin_dir = ROOT / "dist" / "MediaDock" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for src in (fm.ffmpeg_path, fm.ffprobe_path):
        if src and Path(src).is_file():
            shutil.copy2(src, bin_dir / Path(src).name)
            print(f"Eklendi: {Path(src).name}")


def find_iscc() -> Path | None:
    on_path = shutil.which("iscc")
    if on_path:
        return Path(on_path)
    return next((p for p in ISCC_CANDIDATES if p.is_file()), None)


def build() -> int:
    from ui.icons import export_svg_assets

    export_svg_assets()
    generate_app_ico()

    dist_app = ROOT / "dist" / "MediaDock"
    if dist_app.exists():
        shutil.rmtree(dist_app, ignore_errors=True)

    cmd = [sys.executable, "-m", "PyInstaller", str(ROOT / "MediaDock.spec"), "--noconfirm"]
    if "--clean" in sys.argv:
        cmd.append("--clean")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        return result.returncode

    copy_ffmpeg_into_dist()

    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup bulunamadi; kurulum dosyasi uretilmedi.")
        return 0

    result = subprocess.run([str(iscc), str(ROOT / "installer.iss")], cwd=str(ROOT))
    if result.returncode == 0:
        inst_target = ROOT / "installer" / "MediaDock-Setup.exe"
        if inst_target.exists():
            shutil.copy2(inst_target, ROOT / "MediaDock-Setup.exe")
        print(f"Kurulum dosyasi: {inst_target}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(build())
