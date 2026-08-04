# Testy – konvence

Tento dokument popisuje, jak se testy v projektu organizují a píšou.
Pevná vývojová pravidla (Red-Green-Refactor, gate před commitem) jsou
v [DEVELOPMENT_RULES.md](../DEVELOPMENT_RULES.md).

## Jak spouštět

```bash
# celý suite + pokrytí (práh 80 %)
uv run --extra dev pytest --cov

# jeden soubor / jeden test
uv run --extra dev pytest tests/test_downloader.py
uv run --extra dev pytest tests/test_gui_app.py::TestSafariCookies

# lint + typy před commitem (viz DEVELOPMENT_RULES.md)
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy stahovac/
```

## Organizace – 1 soubor = 1 modul

Každý modul má vlastní testovací soubor:

| Testovací soubor | Testovaný modul |
|---|---|
| `test_config.py`, `test_constants.py` | `config/` |
| `test_downloader.py`, `test_downloader_gaps.py`, `test_downloader_helpers.py` | `core/downloader.py` + mixiny |
| `test_ffmpeg.py` | `core/ffmpeg.py` |
| `test_ffmpeg_install.py` | `gui/ffmpeg_install.py` |
| `test_kick.py`, `test_platforms.py` | `platforms/` |
| `test_manager.py` | `downloader.py` (`DownloadManager`) |
| `test_models.py`, `test_state.py`, `test_validator.py` | `models.py`, `state.py`, `core/validator.py` |
| `test_history.py`, `test_paths.py` | `storage/history.py`, `utils/paths.py` |
| `test_cookies.py`, `test_logging_setup.py`, `test_system.py` | `utils/` |
| `test_main.py`, `test_app.py` | `__main__.py`, `app.py` |
| `test_gui_*.py` | `gui/*` view (viz níže) |
| `test_help_content.py` | `help_content.py` |
| `test_gui_web.py` | E2E přes Playwright (vyžaduje Chromium, jinak se přeskočí) |

## Pravidlo regresních testů

Každá oprava bugu přidá **samostatný test**, který bug reprodukuje, do souboru
odpovídajícího modulu. Název testu popisuje problém (viz DEVELOPMENT_RULES.md §2).

## UI testy (gui/)

Flet widgety jde konstruovat bez běžící aplikace, event handlery jsou obyčejné
callable. Vzor:

- fake `_Page` s `update()`, `run_thread()`, `overlay` (a čím view potřebuje),
- handler se volá přímo s fake eventem `e` (nebo `None`),
- tvrdí se změny **props** (`value`, `visible`, `disabled`, `options` …)
  a volané callbacky (`on_save`, `on_start`, `notify` …),
- časové závislosti (throttle, debounce) přes `monkeypatch` na `time.time`,
  Timery se v testu ruší,
- žádný síťový přístup (mock `MetadataService`, `HistoryManager`,
  `open_path`/`reveal_in_file_manager`, `yt_dlp`, `ffmpeg`).

Velké objekty jako `GuiApp` se konstruují přes `GuiApp.__new__(GuiApp)`
a nastaví se jen atributy, které test potřebuje (viz `tests/test_gui_cancel.py`).

## Pokrytí

- Non-GUI vrstva má práh **80 %** (CI gate).
- `gui/*` je z coverage vyloučené (mnoho větví widgetů) – regrese v UI hlídají
  unit testy výše a E2E `test_gui_web.py` (Playwright baseline).
