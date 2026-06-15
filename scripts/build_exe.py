"""Build ClaudeDashboard.exe via PyInstaller (windowed, no console)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SPEC = """\
# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

a = Analysis(
    ['{script}'],
    pathex=['{root}'],
    binaries=[],
    datas=[],
    hiddenimports=['PySide6'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc', 'email', 'http', 'xml', 'html'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ClaudeDashboard',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_repr},
)
"""


def main() -> int:
    icon_path = ROOT / "claude-status.ico"
    if icon_path.exists():
        icon_repr = repr(str(icon_path))
    else:
        icon_repr = "None"
    spec_text = SPEC.format(
        script=str(ROOT / "claude_dashboard.py").replace("\\", "\\\\"),
        root=str(ROOT).replace("\\", "\\\\"),
        icon_repr=icon_repr,
    )
    spec_path = ROOT / "claude-dashboard.spec"
    spec_path.write_text(spec_text, encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_path),
        "--noconfirm",
        "--clean",
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build"),
    ]
    print(">>>", " ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main())
