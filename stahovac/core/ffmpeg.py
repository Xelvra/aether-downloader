"""Vyhledání, stažení a instalace FFmpeg pro méně zkušené uživatele.

FFmpeg je potřeba pro ořez videa a převod na MP3. Pokud není nainstalovaný
v systému, aplikace umožní stáhnout statický build do složky ``bin/`` vedle
aplikace (``get_base_dir()``). Vše je vyřešené jen standardní knihovnou
(urllib, zipfile, tarfile + lzma), takže netřeba žádnou novou závislost.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from uuid import uuid4

from stahovac.utils.format import format_eta, format_speed
from stahovac.utils.paths import get_base_dir
from stahovac.utils.ssl import make_ssl_context

_USER_AGENT = "Mozilla/5.0 (compatible; AetherDownloader/1.0)"

EVERMEET_INFO_URL = "https://evermeet.cx/ffmpeg/info/ffmpeg/release"

# GitHub mirror statických buildů: release.yml nahrává oficiální archivy jako
# release assety (spolehlivý zdroj místo johnvansickle/gyan/evermeet) a k nim
# soubory *.sha256. Aplikace dává mirroru přednost a ověřuje SHA256; když není
# k dispozici (starší release bez assetů), vrátí se na upstream.
GITHUB_REPO = "Xelvra/aether-downloader"
GITHUB_RELEASES_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

_BINARY_NAMES = ("ffmpeg", "ffprobe")

# Známá umístění FFmpeg, která nemusí být v PATH: .app spuštěný z Finderu má
# minimální PATH (/usr/bin, /bin, ...), takže Homebrew (/opt/homebrew na
# Apple Silicon, /usr/local na Intelu) tam chybí – aplikace by falešně hlásila,
# že FFmpeg není nainstalovaný.
_MACOS_HOMEBREW_PATHS: tuple[Path, ...] = (
    Path("/opt/homebrew/bin/ffmpeg"),
    Path("/usr/local/bin/ffmpeg"),
    Path.home() / "homebrew" / "bin" / "ffmpeg",
)


class FfmpegInstallError(Exception):
    """Chyba při stahování nebo instalaci FFmpeg."""


# Koordinace instalace na pozadí: worker, který stahuje FFmpeg (spouští ho
# GUI), dá přes _install_event vědět, že skončil. Ostatní vlákna (worker
# stahování videa) přes wait_until_ready() počkají, až bude FFmpeg k dispozici.
_install_lock = threading.Lock()
_install_event = threading.Event()
_install_in_progress = False


def bin_dir() -> Path:
    """Adresář vedle aplikace, kam se ukládají stažené binárky."""
    return get_base_dir() / "bin"


def install_in_progress() -> bool:
    """True, když právě běží instalace FFmpeg (v jiném vlákně)."""
    return _install_in_progress


def wait_until_ready(timeout: float = 60 * 20) -> bool:
    """Počká, až bude FFmpeg k dispozici.

    Když instalace probíhá na pozadí, počká na její dokončení (úspěch i
    selhání). Když se nic neinstaluje, vrátí okamžitě. Vrací ``True``, jakmile
    ``find_ffmpeg()`` najde binárku.
    """
    if find_ffmpeg() is not None:
        return True
    if not install_in_progress():
        return False
    _install_event.wait(timeout)
    return find_ffmpeg() is not None


def _bundled_ffmpeg_path() -> Path | None:
    """FFmpeg přibalený do binárky PyInstalleru (``sys._MEIPASS``).

    U onefile je ``_MEIPASS`` dočasný extrakční adresář, u onedir (macOS .app)
    finální adresář s binárkou – obojí pokrývá přibalenou verzi. Na macOS je
    tato verze garantovaně otestovaná s daným releasem, proto má přednost před
    ``bin/`` (ručně stažené) i Homebrew.
    """
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    candidate = Path(base) / name
    if candidate.is_file() and (platform.system() == "Windows" or os.access(candidate, os.X_OK)):
        return candidate.resolve()
    return None


def find_ffmpeg() -> Path | None:
    """Najde spustitelný FFmpeg.

    Pořadí kontrol: systémový ``PATH`` → přibalená verze (``_MEIPASS``) →
    ``bin/`` vedle aplikace → známá umístění Homebrew (macOS). PATH má
    přednost, protože respektuje explicitní volbu uživatele; přibalená verze
    před ``bin/``, protože je garantovaně otestovaná s tímto releasem.

    Vrací absolutní cestu k binárce, nebo ``None``, pokud není k dispozici.
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return Path(system_ffmpeg).resolve()
    bundled = _bundled_ffmpeg_path()
    if bundled is not None:
        return bundled
    local = bin_dir() / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    if local.is_file() and (platform.system() == "Windows" or os.access(local, os.X_OK)):
        return local.resolve()
    if sys.platform == "darwin":
        for candidate in _MACOS_HOMEBREW_PATHS:
            if candidate.is_file():
                return candidate.resolve()
    return None


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

    Vrací ``None`` pro nepodporovanou platformu/architekturu. Volání je
    bezpečné z více vláken: když už instalace běží, další volání počká na
    výsledek a vrátí stav po dokončení.
    """
    if not claim_install():
        _install_event.wait()
        return find_ffmpeg()
    return run_install(progress_cb, cancel_check)


def claim_install() -> bool:
    """Synchronně si vyžádá instalaci FFmpeg.

    Vrací ``True``, když volání instalaci začíná (má pokračovat přes
    ``run_install``), jinak ``False``, protože instalace už běží nebo je
    vyžádaná. GUI to volá před spuštěním background vlákna, takže
    ``wait_until_ready()`` (z workeru stahování videa) hned ví, že instalace
    přijde, a počká na ni bez race.
    """
    global _install_in_progress
    with _install_lock:
        if _install_in_progress:
            return False
        _install_in_progress = True
        _install_event.clear()
        return True


def run_install(progress_cb=None, cancel_check=None) -> Path | None:
    """Provede samotné stahování a instalaci FFmpeg do ``bin/``.

    Předpokládá, že si instalaci vyžádal volající (``claim_install()`` vracel
    ``True``) – obvykle ho volá background vlákno spuštěné GUI.
    """
    global _install_in_progress
    try:
        return _download_and_install_impl(progress_cb, cancel_check)
    except FfmpegInstallError:
        raise
    except Exception as ex:
        raise FfmpegInstallError(f"Instalace FFmpeg selhala: {ex}") from ex
    finally:
        _install_event.set()
        with _install_lock:
            _install_in_progress = False


def _download_and_install_impl(progress_cb, cancel_check) -> Path | None:
    target_dir = bin_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = target_dir / f".ffmpeg-download-{uuid4().hex[:8]}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        if cancel_check is not None and cancel_check():
            raise FfmpegInstallError("Stahování FFmpeg bylo zrušeno.")
        archive = _download_archive(tmp_dir, progress_cb, cancel_check)
        if archive is None:
            return None
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


def _download_archive(tmp_dir: Path, progress_cb, cancel_check) -> Path | None:
    """Stáhne archiv FFmpeg do ``tmp_dir``; vrátí cestu k souboru.

    Přednost má GitHub mirror (se SHA256 ověřením), při neúspěchu se spadne
    na oficiální upstream. Vrací ``None`` pro nepodporovanou platformu.
    """
    mirror = _resolve_mirror(cancel_check)
    if mirror is not None:
        url, expected_sha = mirror
        archive = tmp_dir / _url_archive_name(url)
        try:
            _download(url, archive, progress_cb, cancel_check)
            _verify_sha256(archive, expected_sha)
            if not _looks_like_archive(archive):
                raise FfmpegInstallError("Mirror asset není platný archiv.")
            return archive
        except FfmpegInstallError:
            if cancel_check is not None and cancel_check():
                raise
            archive.unlink(missing_ok=True)
    upstream_url = _resolve_download_url(cancel_check)
    if not upstream_url:
        return None
    archive = tmp_dir / _url_archive_name(upstream_url)
    _download(upstream_url, archive, progress_cb, cancel_check)
    return archive


def _looks_like_archive(path: Path) -> bool:
    """Ověří, že soubor skutečně vypadá jako očekávaný archiv (magické byty).

    Chrání před bot-check stránkami, které servery občas vrátí místo souboru
    (johnvansickle na IP adresách CI). Neznámý typ souboru nechá projít.
    """
    try:
        with path.open("rb") as handle:
            head = handle.read(6)
    except OSError:
        return False
    name = path.name.lower()
    if name.endswith(".tar.xz"):
        return head.startswith(b"\xfd7zXZ")
    if name.endswith(".zip"):
        return head.startswith(b"PK\x03\x04")
    return True


def mirror_asset_name(system: str | None = None, machine: str | None = None) -> str | None:
    """Název mirror assetu na GitHubu pro daný OS a architekturu.

    Musí sedět s tím, co nahrává ``release.yml``. Nepodporovaná kombinace
    (kterou CI nebuilduje) vrací ``None``.
    """
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "ffmpeg-linux-x86_64-static.tar.xz"
        if machine in ("aarch64", "arm64"):
            return "ffmpeg-linux-arm64-static.tar.xz"
        if machine.startswith("armv"):
            return "ffmpeg-linux-armhf-static.tar.xz"
        return None
    if system == "Windows":
        if machine in ("x86_64", "amd64"):
            return "ffmpeg-windows-x86_64-essentials.zip"
        return None
    if system == "Darwin":
        return "ffmpeg-macos.zip"
    return None


def _resolve_mirror(cancel_check=None) -> tuple[str, str] | None:
    """Najde GitHub mirror asset pro aktuální platformu.

    Vrací ``(url, sha256)``, nebo ``None``, když mirror není k dispozici
    (starší release bez assetů, nerelevantní platforma, chyba sítě/API).
    """
    asset_name = mirror_asset_name()
    if not asset_name:
        return None
    data = _http_get(GITHUB_RELEASES_LATEST, cancel_check, max_bytes=1 << 20)
    if not data:
        return None
    try:
        release = json.loads(data)
        assets = {a.get("name"): a.get("browser_download_url") for a in release.get("assets", []) if a}
    except (TypeError, ValueError):
        return None
    url = assets.get(asset_name)
    if not url:
        return None
    sha_data = _http_get(assets.get(f"{asset_name}.sha256", ""), cancel_check, max_bytes=1 << 20)
    if not sha_data:
        return None
    digest = sha_data.decode("utf-8", "replace").strip().split()[0] if sha_data else ""
    if len(digest) != 64 or not all(c in "0123456789abcdefABCDEF" for c in digest):
        return None
    return url, digest


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != expected.lower():
        raise FfmpegInstallError("Kontrola SHA256 staženého FFmpeg se nezdařila – zkus to prosím znovu.")


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
        with urllib.request.urlopen(request, timeout=30, context=make_ssl_context()) as response:
            data = response.read(max_bytes + 1)
            return bytes(data) if data is not None else None
    except (OSError, ValueError):
        return None


def _download(url: str, dest: Path, progress_cb, cancel_check) -> Path:
    started = time.time()
    downloaded = 0
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60, context=make_ssl_context()) as response:
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
