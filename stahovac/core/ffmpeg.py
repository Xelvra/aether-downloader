"""Vyhledání, stažení a instalace FFmpeg pro méně zkušené uživatele.

FFmpeg je potřeba pro ořez videa a převod na MP3. Pokud není nainstalovaný
v systému, aplikace umožní stáhnout statický build do složky ``bin/`` vedle
aplikace (``get_base_dir()``). Vše je vyřešené jen standardní knihovnou
(urllib, zipfile, tarfile + lzma), takže netřeba žádnou novou závislost.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from uuid import uuid4

from stahovac.utils.format import format_eta, format_speed
from stahovac.utils.paths import get_base_dir

_USER_AGENT = "Mozilla/5.0 (compatible; AetherDownloader/1.0)"

EVERMEET_INFO_URL = "https://evermeet.cx/ffmpeg/info/ffmpeg/release"

_BINARY_NAMES = ("ffmpeg", "ffprobe")


class FfmpegInstallError(Exception):
    """Chyba při stahování nebo instalaci FFmpeg."""


def bin_dir() -> Path:
    """Adresář vedle aplikace, kam se ukládají stažené binárky."""
    return get_base_dir() / "bin"


def find_ffmpeg() -> Path | None:
    """Najde spustitelný FFmpeg – nejdřív v systému (PATH), pak v ``bin/``.

    Vrací absolutní cestu k binárce, nebo ``None``, pokud není k dispozici.
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return Path(system_ffmpeg).resolve()
    local = bin_dir() / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    if local.is_file() and (platform.system() == "Windows" or os.access(local, os.X_OK)):
        return local.resolve()
    return None


def ffmpeg_dir() -> Path | None:
    """Adresář obsahující FFmpeg (a FFprobe) pro ``ffmpeg_location`` yt-dlp."""
    found = find_ffmpeg()
    return found.parent if found else None


def is_ready() -> bool:
    return find_ffmpeg() is not None


def get_ffmpeg_version() -> str | None:
    """Vrátí verzi FFmpeg (např. ``"6.1.1"``) nebo ``None``, když není k dispozici."""
    binary = find_ffmpeg()
    if binary is None:
        return None
    try:
        proc = subprocess.run(
            [str(binary), "-version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    first_line = proc.stdout.splitlines()[0]
    match = re.search(r"version\s+[a-z]*([0-9][0-9.]*)", first_line)
    return match.group(1) if match else first_line


def get_download_url(system: str | None = None, machine: str | None = None) -> str | None:
    """Statický odkaz na nejnovější stabilní build pro aktuální OS a architekturu.

    Linux a Windows vrací přímo soubor; macOS vrací JSON API evermeet.cx,
    ze kterého se finální odkaz dočte při samotném stahování.
    Nepodporovaná kombinace vrací ``None``.
    """
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        if machine in ("aarch64", "arm64"):
            return "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz"
        if machine.startswith("armv"):
            return "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-armhf-static.tar.xz"
        return None
    if system == "Windows":
        if machine in ("x86_64", "amd64"):
            return "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        return None
    if system == "Darwin":
        return EVERMEET_INFO_URL
    return None


def download_and_install(progress_cb=None, cancel_check=None) -> Path | None:
    """Stáhne a nainstaluje FFmpeg do ``bin/``; vrací cestu k binárce.

    - ``progress_cb(percent: float, speed: str, eta: str)`` – průběh stahování
    - ``cancel_check() -> bool`` – vrací ``True``, když má být stahování zrušeno

    Vrací ``None`` pro nepodporovanou platformu/architekturu.
    """
    try:
        return _download_and_install_impl(progress_cb, cancel_check)
    except FfmpegInstallError:
        raise
    except Exception as ex:
        raise FfmpegInstallError(f"Instalace FFmpeg selhala: {ex}") from ex


def _download_and_install_impl(progress_cb, cancel_check) -> Path | None:
    url = _resolve_download_url(cancel_check)
    if not url:
        return None
    target_dir = bin_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_dir / f".ffmpeg-download-{uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        if cancel_check is not None and cancel_check():
            raise FfmpegInstallError("Stahování FFmpeg bylo zrušeno.")
        archive = tmp_dir / _url_archive_name(url)
        _download(url, archive, progress_cb, cancel_check)
        extract_dir = tmp_dir / "extract"
        _extract(archive, extract_dir)
        binaries = _find_binaries(extract_dir)
        if "ffmpeg" not in binaries:
            raise FfmpegInstallError("Ve staženém archivu nebyl nalezen FFmpeg.")
        _install_binaries(binaries, target_dir)
        _smoke_test(target_dir)
        return target_dir / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _resolve_download_url(cancel_check=None) -> str | None:
    url = get_download_url()
    if not url:
        return None
    if url != EVERMEET_INFO_URL:
        return url
    data = _http_get(EVERMEET_INFO_URL, cancel_check)
    if not data:
        raise FfmpegInstallError("Nepodařilo se zjistit odkaz na FFmpeg pro macOS.")
    try:
        info = json.loads(data)
        return str(info["download"]["zip"]["url"])
    except (KeyError, TypeError, ValueError) as ex:
        raise FfmpegInstallError("Neplatná odpověď serveru s FFmpeg.") from ex


def _url_archive_name(url: str) -> str:
    return Path(urllib.parse.urlparse(url).path).name or "ffmpeg-archive"


def _http_get(url: str, cancel_check=None, max_bytes: int = 1 << 20) -> bytes | None:
    if cancel_check is not None and cancel_check():
        raise FfmpegInstallError("Stahování FFmpeg bylo zrušeno.")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(max_bytes + 1)
            return bytes(data) if data is not None else None
    except (OSError, ValueError):
        return None


def _download(url: str, dest: Path, progress_cb, cancel_check) -> Path:
    started = time.time()
    downloaded = 0
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or 0)
            with dest.open("wb") as handle:
                while True:
                    if cancel_check is not None and cancel_check():
                        raise FfmpegInstallError("Stahování FFmpeg bylo zrušeno.")
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb is not None:
                        percent = (downloaded / total * 100) if total > 0 else 0
                        elapsed = time.time() - started
                        speed = (downloaded / elapsed) if elapsed > 0 else None
                        eta = (total - downloaded) / speed if (total and speed) else None
                        progress_cb(percent, format_speed(speed), format_eta(eta))
    except (OSError, ValueError) as ex:
        raise FfmpegInstallError(f"Nepodařilo se stáhnout FFmpeg: {ex}") from ex
    return dest


def _extract(archive: Path, extract_dir: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        _extract_zip(archive, extract_dir)
    elif name.endswith(".tar.xz") or name.endswith(".tar.bz2") or name.endswith(".tgz"):
        _extract_tar(archive, extract_dir)
    else:
        raise FfmpegInstallError(f"Nepodporovaný typ archivu: {name}")


def _safe_target(base: Path, name: str) -> Path:
    target = (base / name).resolve()
    base_res = base.resolve()
    if not (target == base_res or base_res in target.parents):
        raise FfmpegInstallError(f"Neplatná cesta v archivu: {name}")
    return target


def _extract_zip(archive: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            target = _safe_target(extract_dir, info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _extract_tar(archive: Path, extract_dir: Path) -> None:
    extract_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            target = _safe_target(extract_dir, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            if src is None:
                continue
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _find_binaries(extract_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in extract_dir.rglob("*"):
        if not path.is_file():
            continue
        stem = path.stem.lower()
        if stem in _BINARY_NAMES and stem not in found:
            found[stem] = path
        if set(found) == set(_BINARY_NAMES):
            break
    return found


def _install_binaries(binaries: dict[str, Path], target_dir: Path) -> None:
    for kind, source in binaries.items():
        suffix = ".exe" if platform.system() == "Windows" else ""
        dest = target_dir / f"{kind}{suffix}"
        if source.resolve() != dest.resolve():
            os.replace(source, dest)
        if platform.system() != "Windows":
            os.chmod(dest, 0o755)


def _smoke_test(target_dir: Path) -> None:
    binary = target_dir / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    try:
        subprocess.run(
            [str(binary), "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise FfmpegInstallError("Stažený FFmpeg nefunguje – zkus to prosím znovu.") from None
