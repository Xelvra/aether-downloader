"""Child procesy, sanitizace příkazů a souborové helpery.

Vyděleno z `core/downloader.py` (audit §6.1). Na `stahovac.core.downloader`
se odkazujeme přes ``dl_mod`` až za běhu, aby fungovalo monkeypatchování
v testech (`dl_mod.platform`, `dl_mod.os`, `dl_mod.subprocess`,
`dl_mod._kill_process`, ...). ``import dl_mod`` je proto schválně až na konci
souboru – při cyklickém importu tak mají všechny definice hotové.
"""

import atexit
import re
import threading
from pathlib import Path

_CHILD_PROCESSES: set = set()
_CHILD_PROCESSES_LOCK = threading.Lock()

_SENSITIVE_HEADER = re.compile(r"(?i)(cookie|authorization|x-api-key|x-auth-token)\s*:\s*[^\r\n]*")


def _kill_process(proc) -> None:
    try:
        if dl_mod.platform.system() == "Windows":
            dl_mod.subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=dl_mod.subprocess.DEVNULL,
                stderr=dl_mod.subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                dl_mod.os.killpg(dl_mod.os.getpgid(proc.pid), dl_mod.signal.SIGTERM)
                proc.wait(timeout=3)
            except (ProcessLookupError, OSError, dl_mod.subprocess.TimeoutExpired):
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except dl_mod.subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
    except (OSError, dl_mod.subprocess.SubprocessError):
        pass


def _cleanup_child_processes() -> None:
    with _CHILD_PROCESSES_LOCK:
        procs = list(_CHILD_PROCESSES)
        _CHILD_PROCESSES.clear()
    for proc in procs:
        _kill_process(proc)


def _track_process(proc) -> None:
    with _CHILD_PROCESSES_LOCK:
        _CHILD_PROCESSES.add(proc)


def _untrack_process(proc) -> None:
    with _CHILD_PROCESSES_LOCK:
        _CHILD_PROCESSES.discard(proc)


atexit.register(_cleanup_child_processes)


def _sanitize_cmd(cmd: list[str]) -> str:
    """Sestaví příkaz pro log bez citlivých údajů.

    Z URL argumentů odstraňuje query string (podepsané HLS tokeny, expirace)
    a v hlavičkách maskuje hodnoty cookie/autorizace, aby se nedostaly do logu.
    """
    parts: list[str] = []
    for arg in cmd:
        if "://" in arg:
            arg = re.sub(r"(https?://[^?]+)\?[^\s]*", r"\1?…(zamlčeno)", arg)
        parts.append(_SENSITIVE_HEADER.sub(r"\1…(zamlčeno)", arg))
    return " ".join(parts)


def _find_job_file(directory: Path) -> Path | None:
    for f in directory.iterdir():
        if f.is_file():
            return f
    return None


def _unique_dest(dest_dir: Path, name: str) -> Path:
    """Cílová cesta, která nikdy nepřepíše existující soubor.

    Pokud soubor ``name`` už v cílové složce existuje, přidá se číselná
    přípona (``Soubor (1).mp4``, ``Soubor (2).mp4``, ...).
    """
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(1, 1000):
        candidate = dest_dir / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
    return dest


import stahovac.core.downloader as dl_mod  # noqa: E402  (cyklický import – jen runtime přístup)
