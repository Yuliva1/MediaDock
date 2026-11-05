import re
from pathlib import Path

import build_exe
from config.constants import APP_VERSION

ROOT = Path(__file__).resolve().parent.parent


def test_version_info_matches_constants():
    assert (ROOT / "version_info.txt").read_text(encoding="utf-8") == build_exe.render_version_info()


def test_installer_has_no_hardcoded_version():
    iss = (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert "/DAppVersion" in (ROOT / "build_exe.py").read_text(encoding="utf-8")
    assert not re.search(rf'#define AppVersion "{re.escape(APP_VERSION)}"', iss)


def test_single_update_repo():
    for rel in ("ui/main_window.py", "ui/settings_page.py", "core/updater.py"):
        assert "Yuliva1/MediaDock" not in (ROOT / rel).read_text(encoding="utf-8"), rel
        assert '"Yuliva/MediaDock"' not in (ROOT / rel).read_text(encoding="utf-8"), rel
