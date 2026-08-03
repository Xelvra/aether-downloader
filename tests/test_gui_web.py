"""GUI smoke testy přes flet web režim + Playwright.

Flet 0.86 renderuje UI jako Flutter canvas, takže text není v běžném DOM.
Testy proto zapnou Flutter semantics tree (a11y) a pracují s prvky přes
``aria_snapshot()`` – klikání i kontrola layoutu jdou na skutečné UI.

Regrese layoutu: porovnání ``aria_snapshot()`` proti baseline souborům
v ``tests/gui_baselines/`` (při první shodě se baseline vytvoří). Screenshoty
pro ruční kontrolu se ukládají do ``.screenshots/``.

Vyžaduje prohlížeč: ``uv run playwright install chromium`` (jinak se přeskočí).
"""

import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / ".screenshots"
BASELINES = ROOT / "tests" / "gui_baselines"

_ENABLE_SEMANTICS = "document.querySelector('flt-semantics-placeholder')?.click()"
_TAB_LABELS = ("Stahování", "Ořez", "Nastavení", "Historie")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_ready(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(0.3)
    pytest.fail(f"Web server aplikace se nespustil ({url})")


def _terminate_proc(proc) -> None:
    """Ukončí proces i s případnými child procesy (procesová skupina / taskkill).

    ``proc.terminate()`` posílá signál jen přímému procesu; flet server může
    mít potomky, které by jinak zůstaly viset jako sirotci.
    """
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, ProcessLookupError, ValueError):  # proces už skončil
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def gui_page():
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        env = {
            **os.environ,
            "AETHER_BASE_DIR": tmp,
            "AETHER_PORT": str(port),
        }
        proc = subprocess.Popen(
            [sys.executable, "-m", "stahovac", "--web", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            _wait_ready(f"http://127.0.0.1:{port}")
            with playwright.sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch()
                except Exception as exc:  # noqa: BLE001 - chybí prohlížeč
                    pytest.skip(f"Chromium není nainstalovaný: {exc}")
                SHOTS.mkdir(exist_ok=True)
                yield browser, f"http://127.0.0.1:{port}"
                browser.close()
        finally:
            _terminate_proc(proc)


def _open(gui_page, width: int = 1000, height: int = 800):
    browser, base = gui_page
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(base)
    page.wait_for_selector("flt-semantics-placeholder", timeout=20000)
    page.evaluate(_ENABLE_SEMANTICS)
    page.wait_for_selector('[aria-label="Odkaz na video"]', timeout=20000)
    page.wait_for_timeout(300)
    return page


def _aria(page) -> str:
    return page.locator("body").aria_snapshot()


def _wait_aria_contains(page, text: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if text in _aria(page):
            return
        time.sleep(0.4)
    pytest.fail(f"UI neobsahuje očekávaný prvek: {text!r}")


def _assert_aria(page, name: str) -> None:
    path = BASELINES / f"{name}.txt"
    current = _aria(page)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(current, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert current == expected, f"Aria snapshot '{name}' se změnilo:\n{current}"


class TestGuiLoads:
    def test_title_and_version(self, gui_page):
        page = _open(gui_page, 1000)
        assert "Aether Downloader" in page.title()
        assert "Beta" in page.title()
        page.close()


class TestServerCleanup:
    def test_server_process_fully_terminated(self):
        """Po ukončení serveru (terminate helper) nesmí zůstat žádný proces."""
        port = _free_port()
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                **os.environ,
                "AETHER_BASE_DIR": tmp,
                "AETHER_PORT": str(port),
            }
            proc = subprocess.Popen(
                [sys.executable, "-m", "stahovac", "--web", "--host", "127.0.0.1", "--port", str(port)],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                _wait_ready(f"http://127.0.0.1:{port}")
                assert proc.poll() is None, "Server měl běžet"
            finally:
                _terminate_proc(proc)
        assert proc.poll() is not None, "Server se po ukončení neuzavřel"
        if sys.platform != "win32":
            with pytest.raises(ProcessLookupError):
                os.getpgid(proc.pid)

    def test_no_page_errors(self, gui_page):
        browser, base = gui_page
        page = browser.new_page(viewport={"width": 1000, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base)
        page.wait_for_selector("flt-semantics-placeholder", timeout=20000)
        page.evaluate(_ENABLE_SEMANTICS)
        page.wait_for_selector('[aria-label="Odkaz na video"]', timeout=20000)
        assert errors == []
        page.close()


class TestGuiLayout:
    def test_desktop_tabs_visible(self, gui_page):
        page = _open(gui_page, 1000)
        snap = _aria(page)
        for label in _TAB_LABELS:
            assert f'button "{label}"' in snap, f"Chybí karta {label!r} na desktopu"
        _assert_aria(page, "download-1000")
        page.close()

    def test_mobile_hides_tab_bar(self, gui_page):
        page = _open(gui_page, 400)
        snap = _aria(page)
        for label in _TAB_LABELS:
            assert f'button "{label}"' not in snap, f"Karta {label!r} by na mobilu neměla být vidět"
        assert "Odkaz na video" in snap, "Stahovací karta by měla být vidět i na mobilu"
        _assert_aria(page, "download-400")
        page.close()

    def test_switch_to_trim_tab(self, gui_page):
        page = _open(gui_page, 1000)
        page.get_by_role("button", name="Ořez", exact=True).click()
        _wait_aria_contains(page, "Stáhnout celé video bez ořezu")
        _assert_aria(page, "trim-1000")
        page.close()

    def test_switch_to_settings_tab(self, gui_page):
        # Nastavení NEbaselinizujeme: obsahuje cestu k datové složce a stav FFmpeg,
        # což je závislé na prostředí. Kontrolujeme jen stabilní strukturu.
        page = _open(gui_page, 1000)
        page.get_by_role("button", name="Nastavení", exact=True).click()
        _wait_aria_contains(page, "Místo pro uložení:")
        snap = _aria(page)
        assert "Místo pro uložení:" in snap
        assert "FFmpeg:" in snap
        assert "Přeinstalovat FFmpeg" in snap or "Stáhnout FFmpeg" in snap
        page.close()


class TestGuiScreenshots:
    @pytest.mark.parametrize("width", [400, 700, 1000])
    def test_screenshot_artifacts(self, gui_page, width):
        page = _open(gui_page, width=width)
        page.wait_for_timeout(500)
        path = SHOTS / f"width-{width}.png"
        page.screenshot(path=str(path), full_page=True)
        print(f"\nGUI screenshot: {path}")
        page.close()
