# Příspěvky do projektu

Děkujeme za zájem přispět do Aether Downloaderu. Tento dokument popisuje, jak projekt funguje, jak ho spustit ze zdrojového kódu, otestovat a sestavit. Dokumentace pro koncové uživatele je v [README.md](README.md).

---

## Obsah

- [Předpoklady](#předpoklady)
- [Struktura projektu](#struktura-projektu)
- [Vývojářské prostředí](#vývojářské-prostředí)
- [Nástroje a kontrola kvality](#nástroje-a-kontrola-kvality)
- [Životní cyklus stahování](#životní-cyklus-stahování)
- [Konfigurace](#konfigurace)
- [Technologie](#technologie)
- [Vývoj na bezhlavém systému](#vývoj-na-bezhlavém-systému-ssh-android-termux)
- [Sestavení binárky](#sestavení-binárky)
- [CI/CD](#ci-github-actions)
- [yt-dlp jako knihovna](#yt-dlp-jako-knihovna)
- [Řešení problémů](#řešení-problémů)
- [Pravidla pro pull requesty](#pravidla-pro-pull-requesty)
- [Reportování chyb](#reportování-chyb)

---

## Předpoklady

| Nástroj | Verze | Poznámka |
|---|---|---|
| Python | 3.10+ | |
| [uv](https://docs.astral.sh/uv/) | nejnovější | správce balíčků a virtuálních prostředí |
| FFmpeg | libovolná | volitelné pro běh, ale nutné pro testy ořezu/konverze |
| binutils (`strip`) | — | pouze pro sestavení binárky na Linuxu |
| `create-dmg` | — | pouze pro sestavení DMG na macOS |

---

## Struktura projektu

```text
aether-downloader/
├── main.py                     # Vstupní bod aplikace (thin wrapper na stahovac.__main__.run)
├── build.py                    # Sestavení binárky (PyInstaller, --onefile/--onedir/--clean)
├── stahovac.spec               # Konfigurace PyInstalleru (onefile i onedir dle STAHOVAC_BUILD_MODE)
├── pyproject.toml              # Závislosti a nastavení nástrojů (ruff, mypy, pytest, coverage)
├── README.md                   # Dokumentace pro koncové uživatele
├── CONTRIBUTING.md             # Tento soubor (dokumentace pro vývojáře)
├── LICENSE                     # MIT licence
├── LICENSE-THIRD-PARTY.md      # Licence závislostí (FFmpeg a další)
├── .gitignore                  # Definice souborů a složek ignorovaných Gitem
├── uv.lock                     # Zámek závislostí pro správce balíků uv
├── .github/workflows/ci.yml    # CI: ruff, mypy, pytest --cov, build smoke test
├── stahovac/
│   ├── __init__.py             # Balíček
│   ├── __main__.py             # Vstupní bod "python -m stahovac" + CLI (--web/--host/--port)
│   ├── app.py                  # Propojení GUI s logikou (main → GuiApp)
│   ├── downloader.py           # DownloadManager (jediný zdroj pravdy o stavu, job ID, filtrace stale jobů)
│   ├── state.py                # Stav aplikace (AppState)
│   ├── models.py                # Datové modely (VideoMetadata, DownloadParams) + enum DownloadState
│   ├── config/
│   │   ├── __init__.py         # Inicializace balíčku config
│   │   ├── app_config.py       # AppConfig dataclass (schema_version 2, koerce typů, validace CRF/presetů)
│   │   ├── constants.py        # Konstanty, enumy, výchozí hodnoty
│   │   └── manager.py          # JSON konfigurace (načítání, migrace, oprava typů, atomický zápis)
│   ├── core/
│   │   ├── __init__.py         # Inicializace balíčku core
│   │   ├── downloader.py       # Univerzální stahovací engine (job workspace, FFmpeg strategie, cancel, timeouty)
│   │   ├── ffmpeg.py           # Detekce, stažení a instalace FFmpeg do bin/ (bez GUI, čistá logika)
│   │   ├── metadata.py         # Načítání metadat o videu (cache, vlákna, cancel_check)
│   │   └── validator.py        # Validace URL, časových údajů a CRF
│   ├── platforms/               # Platformně specifická logika – 1 soubor = 1 web
│   │   ├── __init__.py         # Registr: dispečink host → platforma, platform_opts()
│   │   ├── base.py             # Sdílené základy (browser hlavičky, base_opts)
│   │   ├── youtube.py          # Opce specifické pro YouTube
│   │   ├── kick.py             # Opce + KickAdapter (stabilní fallback API) + patch yt-dlp KickVODIE
│   │   └── twitch.py           # Opce + browser hlavičky/device ID pro Twitch
│   ├── gui/
│   │   ├── __init__.py         # Inicializace balíčku gui
│   │   ├── app.py              # Hlavní okno, UI smyčka, asynchronní propojení (page.run_thread)
│   │   ├── custom_file_picker.py  # Vlastní dialog pro výběr souborů/složek
│   │   ├── download_view.py    # Karta stahování (metadata executor + request generace)
│   │   ├── quality_view.py     # Karta ořezu a kvality
│   │   ├── storage_view.py     # Karta nastavení (složka, cookies)
│   │   ├── logs_view.py        # Karta historie a logů
│   │   ├── help_view.py        # Obsah nápovědy (overlay)
│   │   └── theme.py            # Barvy, fonty, responsivní škálování, tlačítka
│   ├── storage/
│   │   ├── __init__.py         # Inicializace balíčku storage
│   │   └── history.py          # Historie stahování
│   └── utils/
│       ├── __init__.py         # Inicializace balíčku utils
│       ├── paths.py            # Cesty k souborům a adresářům
│       ├── format.py           # Formátování rychlosti a odhadu času (sdílené s UI)
│       ├── cookies.py          # Převod cookies na yt-dlp opce + validate_cookies_file
│       └── system.py           # Otevření složky v průzkumníku
└── tests/
    ├── __init__.py             # Inicializace testovacího balíčku
    ├── test_config.py          # Konfigurace (AppConfig koerce, load/save/validace)
    ├── test_constants.py       # Konstanty a enumy
    ├── test_cookies.py         # Převod cookies na yt-dlp opce + validace cookie souboru
    ├── test_downloader.py      # Worker, job workspace, FFmpeg strategie, cancel, timeouty, procesy
    ├── test_downloader_helpers.py  # Formátování rychlosti/času
    ├── test_ffmpeg.py          # Detekce FFmpeg, URL mapa, stažení/rozbalení/instalace (mockované)
    ├── test_history.py         # Historie stahování (vč. atomického zápisu)
    ├── test_kick.py            # KickAdapter + patch KickVODIE + verze yt-dlp
    ├── test_manager.py         # DownloadManager (stale job filtrace, job ID)
    ├── test_models.py          # Datové modely + DownloadState
    ├── test_paths.py           # Cesty
    ├── test_state.py           # AppState
    ├── test_system.py          # Průzkumník souborů
    └── test_validator.py       # Validace
```

> `tool/` je lokální adresář pro dev nástroje (v `.gitignore`), stejně jako `.coverage`, cesty a cache.

---

## Vývojářské prostředí

Projekt používá **uv** jako správce balíčků a virtuálních prostředí. Lockfile `uv.lock` je v repozitáři, takže se závislosti instalují reprodukovatelně.

```bash
# 1. Klonování
git clone https://github.com/Xelvra/aether-downloader.git
cd aether-downloader

# 2. Instalace uv (pokud ho nemáš)
curl -LsSf https://astral.sh/uv/install.sh | sh      # Linux/macOS
pip install uv                                          # Windows (nebo: winget install astral-sh.uv)

# 3. Instalace závislostí – vytvoří .venv a použije uv.lock
uv sync --extra dev

# 4. Spuštění
uv run python main.py
```

> `.venv` se nevytváří ručně a neukládá se do Gitu — vždy ho vygeneruje `uv sync`.

---

## Nástroje a kontrola kvality

| Nástroj | Účel | Příkaz |
|---|---|---|
| **Ruff** | Linter | `uv run ruff check .` |
| **Ruff** | Formatter | `uv run ruff format .` |
| **Mypy** | Statická typová kontrola (i neotypované funkce, `check_untyped_defs`) | `uv run mypy stahovac/` |
| **Pytest** | Testy | `uv run pytest` |
| **Pytest-cov** | Pokrytí (práh **80 %**, jinak selže) | `uv run pytest --cov` |

Před odesláním PR spusť aspoň `ruff check .` a `mypy stahovac/`.

---

## Životní cyklus stahování

`DownloadManager` (`stahovac/downloader.py`) je jediný zdroj pravdy o stavu stahování.

**Stavový automat:**

```text
IDLE → FETCHING_METADATA → DOWNLOADING → PROCESSING → FINISHED / FAILED
                                    │
                                    └─ (zrušení) → CANCELLING → FINISHED (success=False)
```

Klíčové vlastnosti:

- `FINISHED` a `FAILED` jsou **terminální stavy**. Nová úloha se přijme kdykoli, kdy `is_busy()` vrací `False`; `start_download()` přejde z jakéhokoli stavu přímo na `DOWNLOADING`.
- Každé stahování má unikátní `job_id` (`uuid.uuid4().hex`). Callbacky z vláken staré úlohy (`job_id != active_job_id`) jsou odfiltrovány — starý worker nemůže přepsat stav nového stahování.
- Callbacky nesou job ID: `on_progress(job_id, percent, speed, eta)`, `on_status(job_id, text, color)`, `on_finish(job_id, success, message)`, `on_state(state)`.
- `on_finish` je centralizovaný v `Downloader._finish_once()` — garantuje jediné volání i při více větvích workeru.
- `Downloader.start()` vrací `bool`; `DownloadManager.start_download()` nastaví stav až po úspěšném přijetí úlohy.
- **Zrušení** (`cancel_download`) nastaví `CANCELLING` a skutečně ukončí worker; UI se odblokuje až po `on_finish`. Nouzové odemykání v GUI je stupňovité:

  | Čas od zrušení | Akce |
  |---|---|
  | 180 s | žádost o zrušení |
  | +30 s | `force_stop()` ukončí child procesy |
  | +30 s | poslední záchrana odemkne UI |

  UI tedy neodemkne dřív, než skončí worker, pokud to není vyloženě nezbytné.
- Worker stahuje do izolovaného adresáře `<output_folder>/.jobs/<job_id>/`; po dokončení se soubory atomicky přesunou (`os.replace`) do cíle a job adresář se vždy smaže (i velké neúplné soubory).
- **Debug diagnostika:** proměnná prostředí `AETHER_KEEP_FAILED_JOBS=1` zachová pracovní adresář neúspěšné úlohy (částečný soubor, metadata) pro analýzu.

---

## Konfigurace

Konfigurace se normalizuje přes `AppConfig` dataclass (`stahovac/config/app_config.py`):

- **`schema_version`**: aktuálně `2`, verzovaně migruje přes `migrate()` (zřetězené migrace v1→v2→…).
- **Koerce typů**: špatné typy z JSON souboru se automaticky opraví.
- **Validace**: `crf` v rozsahu 0–51, kontrola platných presetů.
- Zápis je atomický (`stahovac/config/manager.py`), takže poškození souboru při pádu během zápisu je vyloučeno.

Přidáváš-li novou konfigurační hodnotu, zvyš `schema_version` a přidej migraci — nikdy needituj starou migraci zpětně.

---

## Technologie

| Technologie | Účel |
|---|---|
| **Python 3.10+** | běhové prostředí |
| **[Flet](https://flet.dev/)** | GUI framework (Flutter ve webovém okně) |
| **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** | stahování videí — používá se jako Python knihovna, ne jako samostatná binárka |
| **FFmpeg** | zpracování videa (ořez, konverze na MP3); hledá se v systémovém PATH, jinak si ho aplikace sama stáhne do `bin/` (`stahovac/core/ffmpeg.py`) |

---

## Vývoj na bezhlavém systému (SSH, Android Termux)

Bez grafického prostředí se aplikace automaticky spustí jako webový server:

```bash
uv run python main.py
```

Výchozí adresa je `http://127.0.0.1:8000`. Pro připojení z jiného zařízení v síti:

```bash
uv run python main.py --web --host 0.0.0.0 --port 8000
```

| CLI přepínač | Proměnná prostředí | Výchozí hodnota | Popis |
|---|---|---|---|
| `--web` / `-w` | — | vypnuto | vynutí webový režim i na systému s displejem |
| `--host <ip>` | `AETHER_HOST` | `127.0.0.1` | adresa, na které server naslouchá |
| `--port <číslo>` | `AETHER_PORT` | `8000` | port |

Všechny funkce aplikace fungují stejně jako v desktopovém režimu.

### Android (Termux)

Na Termuxu se systémové balíčky instalují správcem `pkg` (ne `apt`/`apk`):

```bash
pkg install ffmpeg python uv
```

Poté pokračuj podle sekce [Vývojářské prostředí](#vývojářské-prostředí). Není-li `uv` v repozitářích Termuxu, nainstaluj ho standardním instalačním skriptem:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Sestavení binárky

```bash
# Nainstaluj závislosti včetně PyInstalleru (dev extra)
uv sync --extra dev

# Sestav (binárka bude v dist/stahovac)
uv run python build.py --onefile

# Nebo adresářová varianta (rychlejší start, soubory v dist/stahovac/)
uv run python build.py --onedir

# Vyčištění dist/ a build/
uv run python build.py --clean
```

`build.py` před sestavením automaticky zkontroluje systémové nástroje (`ffmpeg`, `strip`) a Python balíčky (PyInstaller, flet-desktop, flet-web). Spec soubor `stahovac.spec` podporuje oba režimy podle proměnné prostředí `STAHOVAC_BUILD_MODE` (`onefile` | `onedir`).

**Linux** — nainstaluj `binutils` (nástroj `strip`):

```bash
sudo apt install binutils      # Debian/Ubuntu
sudo pacman -S binutils        # Arch Linux
sudo dnf install binutils      # Fedora
```

**macOS** — pro DMG instalační balíček je potřeba `create-dmg`.

**Android** — PyInstaller binárky pro Linux nelze na Androidu spustit; na Termuxu se aplikace vždy spouští ze zdrojového kódu (viz [výše](#vývoj-na-bezhlavém-systému-ssh-android-termux)).

---

## CI (GitHub Actions)

`.github/workflows/ci.yml` spouští na každém push/PR tři joby:

| Job | Co dělá |
|---|---|
| **Lint & Typecheck** | `ruff check .` + `mypy stahovac` |
| **Tests** | `pytest --cov` (vyžaduje pokrytí ≥ 80 %) |
| **Build smoke test** | `build.py --onefile` na Linuxu + ověření binárky |

Pro spuštění CI musí být `uv.lock` v synchronizaci s `pyproject.toml` (kontrola přes `uv sync --locked`).

### Vydání (release)

`.github/workflows/release.yml` se spouští při push tagu `v*` (např. `v1.2.0`):

1. sestaví onefile binárku na **Linuxu, Windows a macOS** (artefakty na GitHub Actions),
2. vytvoří **GitHub Release** s binárkami a automaticky generovanými poznámkami (od commitů od minulého tagu).

Před tagem lokálně ověř:

```bash
uv sync --locked --extra dev
uv run ruff check .
uv run mypy stahovac/
uv run pytest --cov
```

---

## yt-dlp jako knihovna

yt-dlp se používá jako Python knihovna, ne jako subprocess. Všechna volání jdou přes `yt_dlp.YoutubeDL`:

```python
import yt_dlp

opts = {
    "format": "bestvideo+bestaudio/best",
    "noplaylist": True,
    "progress_hooks": [my_hook],
}

with yt_dlp.YoutubeDL(opts) as ydl:
    ydl.download([url])
```

Metadata se získávají přes `ydl.extract_info(url, download=False)`.

**Výhody oproti subprocessu:**

- žádná správa binárky (netřeba stahovat, aktualizovat),
- cookies nejsou vidět v seznamu procesů,
- lepší chybové zprávy,
- menší výsledná binárka.

### Kick

Kick nemá oficiální API pro VOD, proto `stahovac/platforms/kick.py`:

- patchuje yt-dlp extractor `KickVODIE` (nový formát URL), a
- definuje stabilní `KickAdapter` (metody `supports()`/`extract()`) jako fallback přes Kick API, pokud patch selže.

Podporovaná verze yt-dlp je ohraničená v `pyproject.toml` (`yt-dlp>=2024.12.0,<2027.0`) a kontrolovaná testem `test_installed_version_within_supported_range`. Při upgradu yt-dlp nejprve spusť testy.

---

## Řešení problémů

| Problém | Řešení |
|---|---|
| `uv sync` selže na zámku závislostí | Zkontroluj, že `uv.lock` odpovídá `pyproject.toml`: `uv sync --locked`. Pokud ne, spusť `uv lock` a commitni aktualizovaný lockfile. |
| `pytest --cov` selže na pokrytí | Práh je 80 %. Přidej testy pro nově napsaný kód, nebo zkontroluj, že jsi neodstranil existující testy. |
| Sestavení na Linuxu selže na `strip` | Chybí `binutils` — nainstaluj podle [sekce Sestavení binárky](#sestavení-binárky). |
| Build na macOS nevytvoří DMG | Chybí `create-dmg` — nainstaluj přes Homebrew (`brew install create-dmg`). |
| FFmpeg se nenajde ani po instalaci | Ověř, že je v systémovém `PATH` (`ffmpeg -version` v terminálu), nebo nech aplikaci stáhnout vlastní kopii do `bin/`. |
| Testy Kick selžou po upgradu yt-dlp | Zkontroluj rozsah verze v `pyproject.toml` a spusť `test_installed_version_within_supported_range`; může být potřeba aktualizovat patch v `stahovac/platforms/kick.py`. |

---

## Pravidla pro pull requesty

1. **Jeden PR = jedna změna** — menší PR se líp kontrolují.
2. **Piš česky nebo anglicky** — komentáře v kódu anglicky, commity a pull requesty česky nebo anglicky.
3. **Dodržuj kódovací styl** — před odesláním spusť `uv run ruff check .` a `uv run mypy stahovac/`.
4. **Nepřidávej emoji do kódu** — emoji patří do README a commit zpráv.
5. **Testuj na svém systému** — projekt musí fungovat na Windows, Linuxu i macOS.
6. **Nepřidávej závislosti bez diskuze** — každá nová knihovna zvětšuje binárku.

---

## Reportování chyb

Chyby hlas na [GitHub Issues](https://github.com/Xelvra/aether-downloader/issues). Uveď:

- operační systém a verzi,
- co jsi dělal (která URL, jaké nastavení),
- co se stalo (chybová hláška, screenshot),
- očekávané chování.
