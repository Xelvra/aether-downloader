import os
import platform
import subprocess
import sys
from pathlib import Path


def _is_wine() -> bool:
    """True, když aplikace běží pod Wine (Windows binárka na Linuxu/BSD).

    Wine hlásí ``platform.system() == "Windows"``, ale ``os.startfile``
    (chyba ``WinError 6``) ani ``explorer /select`` (tichá no-op) pod ním
    nefungují spolehlivě. Detekce podle proměnných prostředí a cesty
    k Python interpretu – pak se použijí nativní Linux otevírače.
    """
    if platform.system() != "Windows":
        return False
    if any(os.environ.get(k) for k in ("WINELOADER", "WINESERVER", "WINEPREFIX")):
        return True
    return "wine" in (sys.executable or "").lower()


def _wine_to_unix(path: str) -> str:
    """Převede Windows cestu (``C:\\…``, ``Z:\\…``) na Unix cestu pro Wine.

    ``Z:\\`` ukazuje na Linuxový root (``/``); ostatní disky na
    ``$WINEPREFIX/dosdevices/<disk>:/``. Prefix se bere z proměnné prostředí
    ``WINEPREFIX`` (hostitelská cesta) – když není k dispozici, vrátí se cesta
    beze změny, ať se otevírač nesnaží o nesmyslný UnixPath. Nativní cesty se
    vrátí beze změny.

    Pozor: pod Wine je ``pathlib.Path`` typu ``WindowsPath``, proto se cesta
    staví jen z řetězců, ne přes ``Path()``.
    """
    p = str(path).replace("/", "\\")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        tail = p[2:].lstrip("\\").replace("\\", "/")
        if drive == "z":
            return "/" + tail
        prefix = os.environ.get("WINEPREFIX")
        if prefix and ":" not in prefix:
            return f"{prefix.rstrip('/')}/dosdevices/{drive}:/{tail}"
    return str(path)


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


_WINE_UNIX_OPENERS: tuple[str, ...] = (
    "/usr/bin/xdg-open",
    "/usr/bin/gio",
    "/usr/bin/kde-open5",
    "/usr/bin/kde-open",
    "/usr/bin/exo-open",
)


def _open_linux_wine(unix_path: str) -> tuple[bool, str]:
    """Spustí Linux výchozí aplikaci pod Wine přes ``start /unix``.

    Wine nedokáže spouštět nativní Linux binárky přímo přes ``subprocess``
    (CreateProcess je odmítne), ale vestavěný ``start.exe /unix <bin> <args>``
    Unix proces na hostitelském systému spolehlivě spustí.
    """
    last = "Pro tento typ souboru není nastaven žádný program."
    for opener in _WINE_UNIX_OPENERS:
        cmd = ["start", "/unix", opener, *(["open"] if "gio" in opener else []), unix_path]
        ok, msg = _run(cmd)
        if ok:
            return True, ""
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
            if _is_wine():
                return _open_linux_wine(_wine_to_unix(str(path)))
            return _run_startfile(str(path))
        if system == "Darwin":
            return _run(["open", str(path)])
        return _open_linux(str(path))
    except Exception as exc:  # pragma: no cover
        return False, f"{type(exc).__name__}: {exc}"


_LINUX_SELECT_CMDS: tuple[tuple[str, ...], ...] = (
    ("nautilus", "--select"),
    ("dolphin", "--select"),
    ("nemo", "--select"),
    ("thunar",),
    ("pcmanfm", "--select"),
)


def _reveal_windows(path: str) -> tuple[bool, str]:
    try:
        subprocess.Popen(["explorer", f"/select,{path}"], start_new_session=True)
        return True, ""
    except Exception as exc:  # pragma: no cover - platform dependent
        return False, f"{type(exc).__name__}: {exc}"


def _reveal_linux(path: str) -> tuple[bool, str]:
    """Linux/BSD: vybrat soubor ve správci souborů, jinak otevřít rodičovskou složku."""
    last = "Nepodařilo se otevřít správce souborů."
    for args in _LINUX_SELECT_CMDS:
        cmd = [*args, path]
        ok, msg = _run(cmd)
        if ok:
            return True, ""
        if msg.startswith("Příkaz nenalezen"):
            continue
        last = msg or last
    return _open_linux(str(Path(path).parent))


_WINE_UNIX_REVEAL: tuple[tuple[str, ...], ...] = (
    ("/usr/bin/nautilus", "--select"),
    ("/usr/bin/dolphin", "--select"),
    ("/usr/bin/nemo", "--select"),
    ("/usr/bin/thunar",),
    ("/usr/bin/pcmanfm", "--select"),
)


def _reveal_linux_wine(unix_path: str) -> tuple[bool, str]:
    """Pod Wine vybere soubor v Linux správci souborů (přes ``start /unix``)."""
    last = "Nepodařilo se otevřít správce souborů."
    for args in _WINE_UNIX_REVEAL:
        cmd = ["start", "/unix", *args, unix_path]
        ok, msg = _run(cmd)
        if ok:
            return True, ""
        if msg.startswith("Příkaz nenalezen"):
            continue
        last = msg or last
    parent = unix_path.rsplit("/", 1)[0] if "/" in unix_path else unix_path
    return _open_linux_wine(parent)


def reveal_in_file_manager(path_str: str) -> tuple[bool, str]:
    """Ukáže soubor ve správci souborů (vybere ho v dané složce).

    Vrací (úspěch, zpráva). Při neúspěchu otevře alespoň rodičovskou složku
    souboru, takže uživatel vždy skončí na místě, kde soubor leží.
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
            if _is_wine():
                return _reveal_linux_wine(_wine_to_unix(str(path)))
            return _reveal_windows(str(path))
        if system == "Darwin":
            return _run(["open", "-R", str(path)])
        return _reveal_linux(str(path))
    except Exception as exc:  # pragma: no cover - platform dependent
        return False, f"{type(exc).__name__}: {exc}"
