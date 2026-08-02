#!/usr/bin/env python3
"""
Build script for compiling the app into a single binary using PyInstaller.

Usage:
    python build.py                    # build for current platform
    python build.py --onefile         # single-file executable (default)
    python build.py --onedir          # directory bundle
    python build.py --clean           # clean build artifacts first
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "stahovac.spec"


def check_system_deps():
    missing = []

    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")

    if sys.platform == "linux" and not shutil.which("strip"):
        missing.append("binutils (strip)")

    if missing:
        print("Chybějící systémové závislosti:")
        for dep in missing:
            print(f"  - {dep}")
        print()
        print("Nainstaluj je:")
        print("  Debian/Ubuntu:  sudo apt install ffmpeg binutils")
        print("  Arch Linux:     sudo pacman -S ffmpeg binutils")
        print("  Fedora:         sudo dnf install ffmpeg binutils")
        print("  macOS:          brew install ffmpeg binutils")
        print()
        print("Stavět bez nich může způsobit chyby při běhu aplikace.")


def check_python_deps():
    missing = []

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        missing.append("pyinstaller")

    try:
        import flet_desktop  # noqa: F401
    except ImportError:
        missing.append("flet-desktop")

    try:
        import flet_web  # noqa: F401
    except ImportError:
        missing.append("flet-web")

    if missing:
        print("Chybějící Python závislosti:")
        for dep in missing:
            print(f"  - {dep}")
        print()
        print("Nainstaluj je:")
        print(f"  pip install {' '.join(missing)}")
        print()
        sys.exit(1)


def clean():
    for d in [DIST, BUILD]:
        if d.exists():
            shutil.rmtree(d)
    print("Build artifacts cleared.")


def build_binary(onefile: bool = True):
    check_system_deps()
    check_python_deps()

    os.environ["STAHOVAC_BUILD_MODE"] = "onefile" if onefile else "onedir"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--log-level=INFO",
        str(SPEC),
    ]

    print(f"Spouštím ({'onefile' if onefile else 'onedir'}): {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    print(f"\nBuild successful! {'Binary' if onefile else 'Bundle'} in: {DIST}")


def main():
    parser = argparse.ArgumentParser(description="Build stahovac binary")
    parser.add_argument("--onefile", action="store_true", default=True, help="Single-file executable")
    parser.add_argument("--onedir", action="store_true", help="Directory bundle")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    args = parser.parse_args()

    if args.clean:
        clean()
        return

    onefile = not args.onedir if args.onedir else args.onefile
    build_binary(onefile)


if __name__ == "__main__":
    main()
