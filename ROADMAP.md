# Roadmap – plánované funkce (k diskusi)

Tento dokument je **pracovní seznam** nápadů na nové funkce a architektonické
změny. Nejde o závazek – položky se přidávají na základě zpětné vazby
uživatelů a diskuse u GitHub Issues. Sekce „K diskusi" čekají na rozhodnutí,
než se začnou implementovat.

**Aktuální stav:** refaktoring proběhl (audit `tool/audit-aether-downloader.md`),
proto je teď vhodná chvíle funkce diskutovat – kód je rozdělený na čisté
odpovědnosti (`core/_ytdlp.py`, `core/_ffmpeg.py`, `core/_hls_ranged.py`,
`core/_process.py`, `FfmpegInstallController`), takže většina položek níže
má připravené místo, kam ji zapojit.

---

## Kandidáti na funkce

| Funkce | Popis | Úsilí | Poznámka |
|---|---|---|---|
| **Stahování playlistů** | Vložení URL playlistu dnes stáhne jen jedno video (`noplaylist: True` je natvrdo). | Střední | Běžný požadavek u downloaderů; dotáhnout výběr „celý playlist / jen video". |
| **Fronta / dávkové stahování** | Dnes `is_busy()` blokuje start druhého stahování – uživatel musí čekat a klikat znovu. Jednoduchá FIFO fronta (URL, jedno po druhém) by výrazně zlepšila UX. | Střední | Logicky by seděla do `DownloadManager` (fasáda). |
| **Obnovení po zrušení/pádu** | Zrušené stahování dlouhého VOD při 90 % znamená start od nuly (`.jobs/<id>/` se vždy smaže). | Vysoké | Vědomé rozhodnutí kvůli izolaci job adresářů; vyžaduje resume logiku v yt-dlp (`continue`). |
| **Kontrola aktualizací v appce** | Nápověda radí „stáhni novou verzi ručně". Při startu by šlo zkontrolovat GitHub API a nabídnout aktualizaci. | Nízké | Snadné díky stabilnímu release procesu (semver tagy + binárky). |
| **Omezení rychlosti / proxy** | yt-dlp podporuje `ratelimit` i `proxy`; ani jedno není vystavené v Nastavení. | Nízké | Pomůže uživatelům za omezenou linkou nebo firemní sítí. |
| **Světlý motiv** | `theme_mode = DARK` je natvrdo v `gui/app.py`. | Nízké | Čistě kosmetické; vyžaduje rozvázání barev v `theme.py`. |
| **Ikona aplikace** | `stahovac.spec` nemá `icon=` (Windows/Linux) a na macOS je `icon=None` – binárky běží s výchozí PyInstaller ikonou. | Nízké | Stačí přidat `.ico`/`.icns` a zapojit do buildu a release. |

---

## K diskusi (rozhodnutí před implementací)

### i18n – rozvázání byznys hodnot od zobrazovaného textu

`MediaFormat` (a podobně `CookieSource`) používá **zobrazovaný český text jako
hodnotu** (`MediaFormat.MP3 = "Pouze zvuk (MP3)"`). Tenhle řetězec se používá
zároveň jako text v dropdownu, jako klíč v byznys logice (`core/_ytdlp.py`
kontroluje `MediaFormat.MP3.value in format_choice`) **i jako uložená hodnota
v `config.json` a historii na disku uživatelů**.

Důsledky:

- aplikace nejde jednoduše lokalizovat do jiného jazyka,
- kosmetická úprava popisku (překlep, nová formulace) je potenciálně breaking
  change pro logiku,
- **změna hodnoty by zlomila uložené `config.json`/`history.json`** – potřebovala
  by migraci (stejný vzor jako `AppConfig.migrate` / schema_version).

**Rozhodnutí:** odloženo. Udělat až ve chvíli, kdy přijde anglická verze nebo
jiná lokalizace – a pak spolu s verzovanou migrací uložených dat.

### Sestavení nativní binárky pro Android

PyInstaller binárku pro Android nelze sestavit bez cross-compilačních
toolchainů; na Termuxu se aplikace vždy spouští ze zdrojového kódu
(viz README/CONTRIBUTING). Kandidát na budoucí řešení: Termux-packages
balíček, nebo APK přes `buildozer`/Kivy port (nezkoumáno, velký rozsah).

---

## Co se nedělá

- **Bandit (SAST) v CI** – audit nenalezl žádné klasické antipatterny
  (`shell=True`, `eval`, bare `except`, hardcoded secrety), takže se samostatný
  SAST krok nepřidává. OSV-Scanner (SCA na závislosti) v CI zůstává.
- **Playlisty/fronta/resume jako součást aktuálního refaktoru** – viz tabulka
  výše, jde o samostatné produktové rozhodnutí, ne o technický dluh.
