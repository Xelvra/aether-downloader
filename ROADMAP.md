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
| **Světlý motiv** | `theme_mode = DARK` je natvrdo v `gui/app.py`. | Nízké | Vyžaduje rozvázání barev v `theme.py` **a navrženou světlou paletu s hloubkou** (ne „bílý papír") – viz sekci k diskusi níže. |
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
Postup najdeš v sekci **„i18n – jak správně (návrat k úkolu)"** níže.

### i18n – jak správně (návrat k úkolu)

Jeden pokus už proběhl a **byl revertovaný** – výsledek byl nepoužitelný
(„50 % anglicky, 50 % česky"). Zápis chyb, ať se neopakují:

**Co se pokazilo:**
- **Víceřádkové řetězce se překládaly po fragmentech** – `tr()` se zavolal na
  každý kus zřetězení zvlášť, ale anglická tabulka měla klíče jen pro fragmenty.
  Při renderu se zavolalo `tr()` na **celý** zřetězený řetězec → klíč v tabulce
  neexistoval → fallback na češtinu. Výsledek: polovina nápovědy anglicky,
  polovina česky.
- **Nekonzistentní pokrytí** – část statusů (např. „Stahuji FFmpeg…" v progress
  baru) zůstala česky, i když okolní UI bylo anglicky.
- Chyběl **nástroj, který ověří úplnost** – nebylo kontrolováno, že každý
  použitý `tr()` klíč má překlad.

**Jak to udělat správně:**
1. **Jeden klíč = celý řetězec.** `tr()` se volá na **úplný, zřetězený** řetězec
   (buď `tr("... " "...")`, nebo řetězec předem spojit a pak přeložit). Nikdy
   ne `tr()` na fragmenty, které se později zřetězí.
2. **Kompletní pokrytí najednou.** Před zapnutím angličtiny musí mít **všechny**
   uživatelské řetězce překlad – GUI, nápověda, statusy stahování, progress bar,
   validace, CLI. Žádný jazyk se nemíchá v jednom UI.
3. **Automatická kontrola úplnosti:** test/skript, který projde `tr("...")`
   klíče v kódu a ověří, že každý má záznam v anglické tabulce (fail, když
   chybí). Tím se patchwork už nikdy nevrátí.
4. **Mechanika (ta fungovala a zůstává):** `stahovac/i18n.py` s `tr()`/`label()`,
   kanonické identifikátory enumů (`mp4`/`mp3`/`srt`, `none`/`chrome`/…,
   `full`/`end`, `best`), migrace configu `schema_version 2 → 3` (labely →
   identifikátory, nové klíče `language`/`theme`), živé přepnutí jazyka
   v Nastavení s rebuildem UI.
5. **Po dokončení:** ruční průchod appky v češtině i angličtině + screenshoty;
   výchozí jazyk zůstává čeština (Playwright baseline beze změny).

### Světlý theme – ne jako „bílý papír"

První pokus byl taky revertovaný: pouhá výměna palety za `#FFFFFF`/šedou dala
**plochý, papírový vzhled** bez hloubky. Požadavek:

**Co se pokazilo:**
- Světlá paleta jen z rovných barev (`surface = #FFFFFF`, `bg = #F3F4F6`) bez
  jakéhokoli odlišení vrstev → celé UI splývá, není vidět, co je karta, co
  pozadí, co tlačítko.

**Jak to udělat správně:**
1. **Navržená paleta, ne jen inverze.** Světlá varianta potřebuje vlastní,
  odladěnou sadu: mírně off-white pozadí (`#FAFAFB`/`#F3F4F6`), povrch karet
  v bílé s **jemnými stíny** (elevation) a **1px hranami** (border), akcentní
  barvy dostatečně kontrastní na bílém.
2. **Hloubka vrstev:** karty/panely odlišit stínem a zaoblením, ne jen barvou.
   Flet podporuje `shadow`/`elevation` – využít je i ve světlé variantě.
3. **Glass efekt** (pokud Flet/Flutter umožní): průsvitné panely
   (`Colors.with_opacity`) přes jemné pozadí, případně backdrop blur – aspoň
   jako cílový stav; minimálně měkké stíny a kontrastní hrany.
4. **Mechanika (fungovala a zůstává):** palety v `theme.py`, barvy přes funkce
   (`color_surface()` aj.), `set_theme()` + `page.theme_mode`, živý přepínač
   v Nastavení, klíč `theme` v configu (migrace v3).
5. **Vizuální verifikace:** screenshoty obou motivů (desktop + mobile) před
   vydáním – světlý motiv musí vypadat jako záměrný design, ne jako „papír".

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
