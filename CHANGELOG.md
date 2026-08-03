# Changelog

## [Unreleased]

### Přidáno
- GUI regresní testy (Playwright) – aplikace se spouští ve web režimu, ověřuje se vykreslení, přepínání karet a responsive layout přes aria snapshot baseline.

### Opraveno
- Dvojitá informace o průběhu instalace FFmpeg – podrobný progress (procenta, rychlost, zbývající čas) se zobrazuje jen ve společném pruhu aplikace; v Nastavení zůstává jednoduchý status „Stahuji FFmpeg…".
- Plynulejší roztažení okna – karty v horní liště se roztahují rovnoměrně, mezery mezi ikonami už neskáčou při změně šířky okna.

## [1.3.2] – 2026-08-03

### Opraveno
- Dvojitý progress bar při instalaci FFmpeg – průběh se zobrazuje jen ve společném pruhu aplikace, ne v Nastavení.
- Poskakování prvků v UI při změně velikosti okna – rozložení se přebudovává jen při překročení breakpointu, ne při každém tahu okna.
- Neplatný FFmpeg mirror asset se už nedostane do release (při přeskočení se soubor smaže, nepřihraje se omylem).

### Změněno
- Release má v popisu průvodce stažením (přehledné odkazy na binárky pro každý systém) a kontrolní součty v rozbalovací sekci místo samostatných souborů – v seznamu souborů zůstanou jen binárky a FFmpeg assety.

## [1.3.1] – 2026-08-03

### Opraveno
- FFmpeg mirror asset se při buildu validuje (magické byty + velikost) – neplatný archiv se už nenahraje do release.
- Aplikace při neplatném mirror archivu spadne na oficiální upstream (oprava korupčního Linux assetu z v1.3.0).

### Přidáno
- `CHANGELOG.md` s historií všech verzí a odkaz v README.

### Změněno
- Verze 1.3.1.

## [1.3.0] – 2026-08-03

### Přidáno
- FFmpeg je přibalený přímo v macOS `.app` – aplikace funguje hned po instalaci, bez dalšího stahování.
- Ořez videa a převod na MP3 si při prvním použití automaticky stáhnou a nainstalují FFmpeg (žádný banner ani tlačítko, průběh jako u stahování).
- Nová sekce **FFmpeg** v Nastavení – aktuální stav instalace a tlačítko Stáhnout/Přeinstalovat.
- FFmpeg mirror na **GitHub Releases** se **SHA256 ověřením** – spolehlivé stahování místo johnvansickle/gyan/evermeet, s fallbackem na upstream.
- Release workflow se spouští jen po pushnutí tagu `v*` (ruční Run workflow = čistý test buildů bez publikace).

### Opraveno
- Tokeny a cookies už neunikají do logu (sanitizace příkazů FFmpeg).
- CRF se validuje jen při zapnutém překódování (prázdné pole už neblokuje ořez bez re-encode).
- Smoke test na macOS ověřuje přibalený FFmpeg uvnitř `.app`.
- CI akce přesunuty na Node 24 (zmizelo varování o deprecation Node 20).
- Odstraněn mrtvý kód (`ffmpeg_dir`, `is_ready`, `sz_at`, `open_folder_in_explorer`, `VideoMetadata.language`).

### Odstraněno
- Banner „FFmpeg není nainstalován" a hláška při spuštění aplikace.
- Rušivá poznámka k cookies v Nastavení (patří do nápovědy).

### Změněno
- `LICENSE-THIRD-PARTY.md` a nápověda odpovídají realitě distribuce FFmpeg.

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
