import os
import platform
import subprocess
from pathlib import Path


def _run(cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Spustí příkaz a vrátí (úspěch, chybová zpráva).

    Čeká na dokončení, takže umí rozlišit skutečné selhání (chybějící program,
    nenastavená asociace…). ``xdg-open``/``gio`` se u grafických aplikací
    vrací prakticky okamžitě, blokování UI tedy nehrozí.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            start_new_session=True,
        )
    except FileNotFoundError:
        return False, f"Příkaz nenalezen: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"Časový limit vypršel: {cmd[0]}"
    if proc.returncode == 0:
        return True, ""
    detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
    return False, detail or f"Selhal příkaz: {' '.join(cmd)}"


def _run_startfile(path: str) -> tuple[bool, str]:
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _open_linux(path: str) -> tuple[bool, str]:
    """Linux/BSD: zkusit xdg-open, pak gio (GNOME) a kde-open (KDE)."""
    last = "Pro tento typ souboru není nastaven žádný program."
    for opener in ("xdg-open", "gio", "kde-open5", "kde-open", "exo-open"):
        cmd = [opener, "open", path] if opener == "gio" else [opener, path]
        ok, msg = _run(cmd)
        if ok:
            return True, ""
        if msg.startswith("Příkaz nenalezen"):
            continue
        last = msg or last
    return False, last


def open_path(path_str: str) -> tuple[bool, str]:
    """Otevře soubor nebo složku v defaultní aplikaci.

    Vrací (úspěch, zpráva). Při úspěchu je zpráva prázdná; při neúspěchu
    obsahuje čitelné zdůvodnění (soubor neexistuje, není nastaven program…),
    aby selhání nebylo tiché.
    """
    try:
        path = Path(path_str).expanduser().resolve()
    except (OSError, ValueError) as exc:
        return False, f"Neplatná cesta: {exc}"
    if not path.exists():
        return False, f"Cesta neexistuje:\n{path}"

    system = platform.system()
    try:
        if system == "Windows":
            return _run_startfile(str(path))
        if system == "Darwin":
            return _run(["open", str(path)])
        return _open_linux(str(path))
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"


def open_folder_in_explorer(path_str: str) -> bool:
    """Zpětně kompatibilní varianta bez zprávy (vrací jen úspěch)."""
    ok, _ = open_path(path_str)
    return ok
