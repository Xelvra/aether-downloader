# Changelog

## [Unreleased]

### Přidáno
- ROADMAP: sekce **„Technický dluh z auditu (05.08.2026)"** – zbylé nálezy (cyklické importy, monkeypatchování, kompozice místo mixinů, event struktura, sjednocení konfigurace, …) se naplánují spolu s dalšími funkcemi, takže nebude potřeba nový audit.
- Dokumentace: `DEVELOPMENT_RULES.md` (pevná vývojová pravidla – Red-Green-Refactor, každý bug nese regresní test, gate před commitem, determinismus) a `tests/README.md` (konvence testů), odkazy z CONTRIBUTING.
- Testy GUI: `tests/test_gui_quality_view.py` a `tests/test_gui_download_view.py` – unit testy event handlerů a změn props (toggle času/reencode, end-option, `update_qualities`, debounce, `refresh_metadata`, `update_metadata_ui`, `set_downloading`).
- Testy GUI: `tests/test_gui_logs_view.py`, `tests/test_gui_storage_view.py`, `tests/test_gui_help_view.py` – render historie, otevírání souborů/složek (úspěch i chyba → notify), `_picker_mode`, pickery s debounce, stav FFmpeg, cookies, vykreslení nápovědy.
- Testy GUI: `tests/test_gui_app.py` – zbylé metody `GuiApp` (resize/breakpointy, Safari blokace, `_start_download_impl`, `_do_start_download`, `_on_save_settings`, cap logů 500, throttling progress/status, `_force_unlock_ui`, tab switching, help/drawer, `_apply_*` marshaling).
- Testy: pokrytí negui vrstvy rozšířeno o edge cases `AppState.update_config_from_ui`.
- Testy: odstraněn overengineering – „coverage theater" testy triviálních/nedostupných větví (`_bundled_ffmpeg_path` se simulovaným frozen, OSError větev `_looks_like_archive`, `_coerce_bool(None)`, stream handler v `configure_logging`, Wine `continue`/file-manager chain) a testy čistých delegací v `GuiApp`; zjednodušeny Wine otevírače (`xdg-open` + otevření rodičovské složky místo fallback řetězců) a `_wine_to_unix` (jen `Z:\` → `/`). CONTRIBUTING: strom projektu odpovídá realitě.
- Testy: `TestDoStartDownload` mockuje `ffmpeg.find_ffmpeg` – testy jsou deterministické i v CI bez nainstalovaného FFmpeg.

### Změněno
- Oprava (audit CRITICAL-06): `_unique_dest()` už nemá arbitrární limit 999 kolizí (`while True` místo `range(1, 1000)`) – po 999 shodných názvech se soubor nikdy nepřepíše. Regresní test s 1000+ kolizemi.
- Oprava (audit CRITICAL-04): nový `utils/paths.py::truncate_filename()` + konstanta `MAX_FILENAME_STEM` (150) – extrémně dlouhé tituly videí (300+ znaků) už nezpůsobí OSError/FileNotFoundError. Aplikováno na názvy ranged HLS výstupu, FFmpeg ořezu i přesunu hotových souborů. Regresní testy.
- Oprava (audit CRITICAL-02): `DownloadView` dostal `_closed` flag – `close()` ho nastaví a `refresh_metadata()` po zavření už neodešle práci do `ThreadPoolExecutor` (race při shutdown se nezakrývá jen `except RuntimeError`). Regresní testy.
- Oprava (audit CRITICAL-01): `DownloadView.refresh_metadata()` už nepolyká `except Exception` – chytá jen očekávané `MetadataError` (nová výjimka v `core/metadata.py`, do které se balí chyby yt-dlp). Programátorské/threadové chyby se zalogují a propadnou, aby šly odhalit. Regresní testy.
- Dokumentace: FFmpeg se automaticky stahuje vždy, když v systému chybí – ne jen k ořezu/MP3, ale i ke spojení obrazu se zvukem (merge) při stahování MP4. Aktualizováno v README a nápovědě v aplikaci (`help_content.py`).

## [1.3.5] – 2026-08-04

### Opraveno
- Windows CI: testy cross-platform – cesty (`ffmpeg.exe`, absolutní cesty) a přeskočení Linux-specific testů na Windows (kill přes `os.getpgid`, kontrola spustitelnosti).
- Ctrl+C / shutdown aplikace (Termux, web režim): `main()` už nespolkne `CancelledError` – flet-web tak po zrušení session nevolá `after_event()` na zrušenou (None) session a při ukončení se nevypíše traceback `AttributeError: 'NoneType' object has no attribute 'after_event'`.
- CONTRIBUTING: opraveno časování nouzového odemykání UI – `180 s / +30 s / +30 s` → `8 s / +8 s` (soulad se skutečnými hodnotami v `gui/app.py`).
- Auto-instalace FFmpeg (Windows bez FFmpeg, ořez/MP3): `FfmpegInstallController` přistupoval k host atributům přes veřejné názvy, ale `GuiApp` je má privátní – padalo `AttributeError: 'GuiApp' object has no attribute 'progress_bar'` a stahování (např. Twitch) se nespustilo. Oprava + regresní test reálného zapojení GuiApp → controller.
- Auto-instalace FFmpeg při prvním použití: yt-dlp potřebuje FFmpeg nejen na ořez/MP3, ale i na **merge video+audio** (`bestvideo+bestaudio`) při běžném stahování MP4. Auto-instalace se teď spustí vždy, když FFmpeg chybí, a worker počká na instalaci **před** sestavením yt-dlp opcí – jinak yt-dlp čerstvě staženou binárku nenašel a stahování spadlo na „ffmpeg is not installed". Regresní test pořadí `_ensure_ffmpeg_ready` → `_build_ydl_opts`.
- Otevírání souborů/složek z historie **pod Wine** (Windows binárka na Linuxu): `os.startfile` házel `WinError 6` a `explorer /select` byl tichá no-op. Wine nedokáže spouštět nativní Linux binárky přes `subprocess`, proto aplikace Wine detekuje (`WINEPREFIX`/`WINELOADER`/cesta k interpretu), převede Windows cestu na Unix (`Z:\` → `/`) a Linux otevírače (`xdg-open`, `gio`, `kde-open5`, správce souborů) spouští přes vestavěný `start /unix` – historie i nastavení tak fungují i pod Wine. Testy detekce Wine, převodu cesty a spuštění přes `start /unix`.

### Změněno
- CI: OSV-Scanner pin na `v2.3.8` (major tag `v2` neexistuje).
- README: správné pořadí v Obsahu (Ukázky až za Rychlý start).
- Dokumentace: Android (Termux) – do `pkg install` přidáno `git` (v Termuxu není předinstalovaný), `rust`, `binutils` a `clang` (kompilace balíčků bez Android kola); instalace bez dev balíčků `uv sync` – Playwright a PyInstaller nemají binárky pro Android, pro vývoj se vynechávají přes `--no-install-package`.
- Refactoring (nálezy auditu): `StorageView._picker_mode` inicializováno v `__init__`; `_notify()` sjednoceno do sdílené `theme.notify()`; CRF coerce má jediný zdroj pravdy `coerce_crf()` v `config/app_config.py` (Downloader/GuiApp jen delegují); metadata cache používá sdílený eviction helper a `_add_to_cache` je dokumentovaný testovací seed helper.
- Logování: nový `utils/logging.py::configure_logging()` – technické logy z `logging` modulu (Kick/metadata/ssl/yt-dlp) se už neztrácejí, ale píšou se do `app.log` v app-data adresáři (`RotatingFileHandler`, DEBUG) s konzolí na WARNING; zavolá se při startu v `_setup_runtime()`. Souborové logy pomůžou při hlášení bugů (Discord/GitHub Issues).
- Ikonky: `ICON_SIZE`/`ICON_SIZE_LARGE` (zamrzlé konstanty z importu) nahrazeny funkcemi `icon_size()`/`icon_size_large()` v `theme.py` – ikony se teď škálují konzistentně se `sz()` při přechodu přes breakpointy (audit §4.2).
- Validace stahování: validační řetězec (URL, časový rozsah, CRF) přesunut z `GuiApp._start_download_impl` do `core/validator.py::validate_download_params()` s fasádou `DownloadManager.validate()` – validace už nežije v GUI vrstvě, může ji použít i budoucí CLI/vstupní bod (audit §6.2).
- FFmpeg instalace: flow (start/progress/done/failed) vydělen z `GuiApp` do nového `FfmpegInstallController` (`gui/ffmpeg_install.py`); `GuiApp` jen deleguje přes `self.ffmpeg_install` (audit §6.2).
- Rozdělení `core/downloader.py` (902 → 300 řádků, audit §6.1): odpovědnosti přesunuty do `core/_ytdlp.py` (`YtDlpMixin` – opce, retry, klasifikace chyb), `core/_ffmpeg.py` (`FfmpegTrimMixin` – ořez, sledování procesu), `core/_hls_ranged.py` (`HlsRangedMixin` – ranged HLS), `core/_process.py` (child procesy, sanitizace, souborové helpery). `Downloader` zůstává orchestrátor a re-exportuje symboly, takže importy testů zůstaly beze změny.
- Přidán `ROADMAP.md` – pracovní seznam plánovaných funkcí (playlisty, fronta, resume, auto-update, proxy/rate-limit, světlý motiv, ikona) a položky k diskusi (i18n rozvázání enumů, Android binárka); odkaz z README.

## [1.3.4] – 2026-08-03

### Přidáno
- Bezpečnost: `SECURITY.md` (privátní hlášení zranitelností), Dependabot (pip + GitHub Actions) a CI audit zranitelností přes OSV-Scanner.
- GitHub meta: šablony pro issue (bug report, feature request), šablona pull requestu a `CODE_OF_CONDUCT.md`.

### Opraveno
- README: nefunkční odkazy na sekci Android – emoji `📱` v nadpisu mění GitHub kotvu na `#-android-pro-pokročilejší-uživatele`, odkazy ukazovaly na kotvu bez úvodní pomlčky.

### Změněno
- CI: testy navíc na Windows a macOS (GUI testy zůstávají na Ubuntu), kontrola `ruff format --check`, release ověřuje shodu tagu `v*` s `APP_VERSION`.
- README: sekce **Ukázky** se screenshoty aplikace, CI badge, upřesněná formulace podporovaných webů (přes yt-dlp).
- Nápověda: obsah oddělený od vykreslování do `stahovac/help_content.py` (datová vrstva + testy struktury).
- Kick testy: plně mockované, testovací data používají fiktivní kanál – žádný reálný účet ani subscription, žádné riziko poškození skutečného kanálu.
- Dokumentace: README a CONTRIBUTING – poznámka k testování platforem (Linux 100 %, Windows přes Wine, macOS/ostatní buildy komunitou); README – odstraněna věta o nápovědě k příkazům pro instalaci FFmpeg.

## [1.3.3] – 2026-08-03

### Přidáno
- GUI regresní testy (Playwright) – aplikace se spouští ve web režimu, ověřuje se vykreslení, přepínání karet a responsive layout přes aria snapshot baseline (`tests/gui_baselines/`), screenshoty jako CI artefakt.

### Opraveno
- Orphan procesy: SIGTERM teď vede na čisté ukončení (proběhne atexit cleanup child procesů); testy GUI zabíjejí celou procesovou skupinu, takže po ukončení serveru nezůstává viset žádný proces.
- Dvojitá informace o průběhu instalace FFmpeg – podrobný progress (procenta, rychlost, zbývající čas) se zobrazuje jen ve společném pruhu aplikace; v Nastavení zůstává jednoduchý status „Stahuji FFmpeg…" (dokončení 1.3.2).
- Plynulejší roztažení okna – karty v horní liště se roztahují rovnoměrně, mezery mezi ikonami už neskáčou při změně šířky okna (dokončení 1.3.2).

### Změněno
- Dokumentace: README (macOS má FFmpeg přibalený, sjednocená FFmpeg sekce, podporované systémy bez falešné Linux ARM binárky, vysvětlení názvu „stahovac"), LICENSE-THIRD-PARTY (GitHub mirror jako primární zdroj FFmpeg + licence zabalených Python závislostí), CONTRIBUTING (Playwright, bezpečnostní varování k `--host 0.0.0.0`, odstraněny zastaralé DMG zmínky), CHANGELOG (sjednocené pořadí kategorií).

## [1.3.2] – 2026-08-03

### Opraveno
- Dvojitý progress bar při instalaci FFmpeg – průběh se zobrazuje jen ve společném pruhu aplikace, ne v Nastavení.
- Poskakování prvků v UI při změně velikosti okna – rozložení se přebudovává jen při překročení breakpointu, ne při každém tahu okna.
- Neplatný FFmpeg mirror asset se už nedostane do release (při přeskočení se soubor smaže, nepřihraje se omylem).

### Změněno
- Release má v popisu průvodce stažením (přehledné odkazy na binárky pro každý systém) a kontrolní součty v rozbalovací sekci místo samostatných souborů – v seznamu souborů zůstanou jen binárky a FFmpeg assety.

## [1.3.1] – 2026-08-03

### Přidáno
- `CHANGELOG.md` s historií všech verzí a odkaz v README.

### Opraveno
- FFmpeg mirror asset se při buildu validuje (magické byty + velikost) – neplatný archiv se už nenahraje do release.
- Aplikace při neplatném mirror archivu spadne na oficiální upstream (oprava korupčního Linux assetu z v1.3.0).

## [1.3.0] – 2026-08-03

### Přidáno
- FFmpeg je přibalený přímo v macOS `.app` – aplikace funguje hned po instalaci, bez dalšího stahování.
- Ořez videa a převod na MP3 si při prvním použití automaticky stáhnou a nainstalují FFmpeg (žádný banner ani tlačítko, průběh jako u stahování).
- Nová sekce **FFmpeg** v Nastavení – aktuální stav instalace a tlačítko Stáhnout/Přeinstalovat.
- FFmpeg mirror na **GitHub Releases** se **SHA256 ověřením** – spolehlivé stahování místo johnvansickle/gyan/evermeet, s fallbackem na upstream.
- Release workflow se spouští jen po pushnutí tagu `v*` (ruční Run workflow = čistý test buildů bez publikace).

### Opraveno
- CRF se validuje jen při zapnutém překódování (prázdné pole už neblokuje ořez bez re-encode).
- Smoke test na macOS ověřuje přibalený FFmpeg uvnitř `.app`.
- CI akce přesunuty na Node 24 (zmizelo varování o deprecation Node 20).

### Bezpečnost
- Tokeny a cookies už neunikají do logu (sanitizace příkazů FFmpeg).

### Změněno
- `LICENSE-THIRD-PARTY.md` a nápověda odpovídají realitě distribuce FFmpeg.

### Odstraněno
- Banner „FFmpeg není nainstalován" a hláška při spuštění aplikace.
- Rušivá poznámka k cookies v Nastavení (patří do nápovědy).
- Mrtvý kód (`ffmpeg_dir`, `is_ready`, `sz_at`, `open_folder_in_explorer`, `VideoMetadata.language`).

## [1.2.9] – 2026-08-02

### Opraveno
- Smoke test binárky: retry na přechodné timeouty + johnvansickle jako best-effort (neblokuje release).

## [1.2.8] – 2026-08-02

### Změněno
- Dokumentace k Safari cookies na macOS (TCC) v README a nápovědě.

## [1.2.7] – 2026-08-02

### Přidáno
- SHA256 checksumy artefaktů v release.

### Opraveno
- Robustnější otevírání souborů z historie (verifikace + viditelné chybové hlášení).
- URL validace při zadávání odkazu.
- Varování při spuštění ve webovém režimu.

## [1.2.6] – 2026-08-02

### Opraveno
- Kick VOD: správný výběr archivovaného videa místo živého streamu.

## [1.2.5] – 2026-08-02

### Opraveno
- macOS `.app`: AppTranslocation, nalezení Homebrew FFmpeg i mimo PATH (Finder má minimální PATH).
- File picker: tlačítko „Vybrat" v režimu souboru se povolí až po výběru.

### Změněno
- Auditní testy jádra – pokrytí 100 % (downloader, config, kick, ffmpeg, picker).

## [1.2.4] – 2026-08-02

### Přidáno
- macOS `.app` bundle pro Apple Silicon i Intel.

### Opraveno
- Build na Windows probíhá v bash (default byl pwsh).
- Uživatelská data se ukládají mimo app bundle.
- Otevírání souboru z historie s verifikací.

## [1.2.3] – 2026-08-02

### Opraveno
- Kick sub-only VOD přes `session_token` cookies a fallback scraping stránky.

## [1.2.2] – 2026-08-02

### Přidáno
- Self-test binárky (`--check`) – TLS/CA a připojení.

### Opraveno
- TLS ověřování v CI buildu (certifi CA bundle).

## [1.2.1] – 2026-08-02

### Opraveno
- Použití zabaleného certifi CA bundle pro TLS v PyInstaller buildech.

## [1.2.0] – 2026-08-02

### Přidáno
- První verze Aether Downloaderu – stahování z YouTube, Kick a Twitch, ořez videa, převod na MP3, GUI ve Fletu.
