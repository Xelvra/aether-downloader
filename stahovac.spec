# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

_root = Path(SPECPATH)
_build_mode = os.environ.get("STAHOVAC_BUILD_MODE", "onefile")

datas = [(str(_root / 'stahovac'), 'stahovac'), (str(_root / 'README.md'), '.')]
binaries = []
hiddenimports = ['yt_dlp', 'yt_dlp.extractor', 'flet', 'flet_desktop', 'flet_web']
# Pluginy yt-dlp (EJS solver pro YouTube, impersonace pro Kick) – načítají se
# přes yt-dlp PyInstaller hook, ale pro jistotu je uvádíme i explicitně.
hiddenimports += ['yt_dlp_ejs', 'curl_cffi']
tmp_ret = collect_all('yt_dlp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flet_desktop')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('flet_web')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# certifi: CA bundle musí být uvnitř binárky, aby TLS fungovalo i tam, kde
# systémové úložiště certifikátů není dostupné (typicky CI build).
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# yt-dlp-ejs: JS solver (core.min.js / lib.min.js) pro YouTube PO tokeny.
tmp_ret = collect_all('yt_dlp_ejs')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# FFmpeg z <repo>/bin (stáhne ho release.yml před buildem): na macOS se
# přibalí do .app, takže aplikace funguje hned bez dalšího stahování.
# Na Windows/Linux se FFmpeg stahuje za běhu (Nastavení / auto-install).
_ffmpeg_dir = _root / 'bin'
if sys.platform == 'darwin' and (_ffmpeg_dir / 'ffmpeg').is_file():
    binaries.append((str(_ffmpeg_dir / 'ffmpeg'), '.'))
    if (_ffmpeg_dir / 'ffprobe').is_file():
        binaries.append((str(_ffmpeg_dir / 'ffprobe'), '.'))


a = Analysis(
    [str(_root / 'main.py')],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if _build_mode == "onedir":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='stahovac',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='stahovac',
    )
    # Na macOS zabalíme COLLECT do .app bundle – jinak Finder otevírá holý
    # executable jako text („zobrazí se kód") a nejde ho spustit dvojklikem.
    if sys.platform == 'darwin':
        app = BUNDLE(
            coll,
            name='stahovac.app',
            icon=None,
            bundle_identifier='cz.stahovac.desktop',
        )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='stahovac',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
