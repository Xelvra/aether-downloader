# Aether Downloader

> Jednoduchá aplikace na stahování videí z YouTube, Kicku, Twitche a mnoha dalších webů.

**Žádný terminál, žádné příkazy, žádné technické znalosti** (na počítači — Windows, Linux i macOS). Vložíš odkaz, klikneš na tlačítko a video se ti uloží do počítače. Android se spouští ze zdrojového kódu, proto vyžaduje terminál — viz [sekce níže](#-android-pro-pokročilejší-uživatele).

> ℹ️ Aplikace se uživatelsky jmenuje **Aether Downloader**, ale soubory, binárky i balíček se vnitřně jmenují **`stahovac`** — je to jen interní název, jde o stejnou aplikaci.

[![Licence: MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
![Platformy](https://img.shields.io/badge/platformy-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20Android-blue)

---

## Obsah

- [Rychlý start](#rychlý-start-3-kroky)
- [Instalace](#instalace-a-spuštění)
- [FFmpeg](#ffmpeg-instaluje-se-automaticky)
- [Jak stáhnout první video](#jak-stáhnout-první-video)
- [Co všechno aplikace umí](#co-všechno-aplikace-umí)
- [Nápověda přímo v aplikaci](#nápověda-přímo-v-aplikaci)
- [Potřebuješ pomoct?](#potřebuješ-pomoct)
- [Podporované systémy](#podporované-systémy)
- [Historie verzí](#historie-verzí)
- [Pro vývojáře](#pro-vývojáře)
- [Licence](#licence)

---

## Rychlý start (3 kroky)

1. Stáhni si aplikaci pro svůj počítač ze sekce [Releases](https://github.com/Xelvra/aether-downloader/releases).
2. Spusť aplikaci, vlož odkaz na video a klikni na **Stáhnout**. K ořezu a MP3 je potřeba **FFmpeg** — na macOS je už součástí aplikace, na Windows/Linuxu si ho aplikace sama stáhne při prvním použití.
3. Hotovo — video je tvoje.

Podrobný postup pro konkrétní systém najdeš níže (Android viz [zde](#-android-pro-pokročilejší-uživatele)).

---

## Instalace a spuštění

### 🪟 Windows

1. Na [stránce Releases](https://github.com/Xelvra/aether-downloader/releases) stáhni nejnovější verzi souboru **`stahovac-windows-x86_64.exe`**.
2. Soubor se nemusí rozbalovat — stačí na něj poklepat.
3. Windows pravděpodobně zobrazí modrou obrazovku s varováním — to je normální, protože aplikace nemá placený certifikát od Microsoftu. Klikni na **Další informace** → **Přesto spustit**.

> ⚠️ K ořezu a MP3 si aplikace **FFmpeg** při prvním použití stáhne sama (viz [FFmpeg](#ffmpeg-instaluje-se-automaticky)).

### 🐧 Linux

1. Na [stránce Releases](https://github.com/Xelvra/aether-downloader/releases) stáhni nejnovější verzi souboru **`stahovac-linux-x86_64`**.
2. Soubor je potřeba nejdřív „odemknout" pro spuštění:

   **Přes grafické rozhraní:**
   Pravé tlačítko na `stahovac-linux-x86_64` → **Vlastnosti** → záložka **Oprávnění** → zaškrtni **Povolit spouštění souboru jako programu**.

   **Přes terminál:**
   ```bash
   chmod +x stahovac-linux-x86_64
   ./stahovac-linux-x86_64
   ```
3. Poklepej na soubor `stahovac-linux-x86_64` a aplikace se spustí.

> ⚠️ K ořezu a MP3 si aplikace **FFmpeg** při prvním použití stáhne sama (viz [FFmpeg](#ffmpeg-instaluje-se-automaticky)).

### 🍎 macOS

1. Na [stránce Releases](https://github.com/Xelvra/aether-downloader/releases) stáhni nejnovější verzi **podle procesoru svého Macu**:
   - **Apple Silicon** (M1, M2, M3, M4 a novější) → soubor **`stahovac-macos-arm64.app.zip`**
   - **Intel** → soubor **`stahovac-macos-x86_64.app.zip`**

   > Nevíš, jaký procesor máš? Otevři **menu  (vlevo nahoře) → O tomto Macu**. U Apple Silicon je uvedeno „Apple M1/M2/M3/M4…", u Intelu „Intel…".
2. Rozbal stažený ZIP (poklepej na něj) a přesuň aplikaci **`stahovac.app`** do složky **Aplikace**.
3. Při prvním spuštění systém aplikaci zablokuje, protože pochází od neznámého vývojáře — to je normální:
   - **Pravé tlačítko na `stahovac.app` → Otevřít → Otevřít**, nebo
   - **Nastavení systému → Soukromí a zabezpečení** → sjeď dolů, najdi hlášku o zablokované aplikaci a klikni na **Otevřít přesto**.

> ✅ **FFmpeg je součástí aplikace** — na macOS se přibaluje přímo do `.app`, takže ho nemusíš stahovat ani instalovat.

> 📂 Stažená videa a nastavení se ukládají do **`~/Library/Application Support/AetherDownloader/`** — ne do samotné aplikace. Složku si můžeš změnit v Nastavení.

> ⚠️ **Safari a cookies:** pokud na Kicku/Twitchi nefungují sub-only videa a v Nastavení máš vybraný **Safari**, systém nejspíš brání aplikaci přečíst Safari cookies. Povol v **Systémové nastavení → Soukromí a zabezpečení → Plný přístup k disku** aplikaci `stahovac.app` a restartuj ji, nebo vyber Chrome/Firefox či `cookies.txt`.

### 📱 Android (pro pokročilejší uživatele)

Pro Android neexistuje hotová aplikace ke stažení — spouští se přes Termux ze zdrojového kódu a otevírá se v prohlížeči.

```bash
# 1. Nainstaluj potřebné nástroje
pkg install ffmpeg python uv

# 2. Stáhni si projekt
git clone https://github.com/Xelvra/aether-downloader.git
cd aether-downloader
uv sync --extra dev

# 3. Spusť aplikaci
uv run python main.py
```

Termux vypíše webovou adresu — otevři ji v prohlížeči telefonu. Podrobnosti najdeš v [CONTRIBUTING.md](CONTRIBUTING.md).

> ⚠️ **Webový režim** běží ve výchozím nastavení jen na adrese `127.0.0.1` (přístupný pouze z daného zařízení). Server nemá žádné přihlášení — pokud ho zpřístupníš jiným zařízením v síti (`AETHER_HOST` / `--host`), **kdokoli v síti může procházet soubory a spouštět stahování**. Výchozí nastavení neměň, pokud si jsi jistý, co děláš.

---

## FFmpeg (instaluje se automaticky)

Aplikace potřebuje **FFmpeg** k ořezu videa nebo převodu na MP3.

- **macOS** — FFmpeg je **přibalený přímo v aplikaci**, nic se nestahuje ani nenastavuje.
- **Windows a Linux** — k ořezu nebo MP3 si aplikace **FFmpeg sama stáhne a nainstaluje** při prvním použití (průběh uvidíš jako u běžného stahování). Stav FFmpeg a případné ruční stažení/přeinstalaci najdeš v aplikaci na kartě **Nastavení**.

Pro ruční instalaci zkopíruj příkaz podle svého systému do terminálu (Windows: PowerShell, macOS/Linux: Terminál):

| Systém | Příkaz |
|---|---|
| Windows | `winget install ffmpeg` |
| Debian / Ubuntu / Mint | `sudo apt install ffmpeg` |
| Arch / Manjaro | `sudo pacman -S ffmpeg` |
| Fedora / RHEL | `sudo dnf install ffmpeg` |
| macOS (Homebrew) | `brew install ffmpeg` |
| Android (Termux) | `pkg install ffmpeg` |

Nevíš si rady s příkazovým řádkem? V aplikaci v nápovědě (ikona ❓) najdeš podrobný návod krok za krokem pro každý systém.

---

## Jak stáhnout první video

1. **Vlož odkaz** — zkopíruj URL videa (např. z YouTube) do pole nahoře v aplikaci. Název a náhled se načtou automaticky.
2. **Vyber si možnosti:**
   - **Kvalita** — v jakém rozlišení chceš video stáhnout
   - **Formát** — celé video, nebo jen zvuk jako MP3
   - **Ořez** *(volitelné)* — pokud chceš jen část videa, odškrtni „Stáhnout celé video bez ořezu" a zadej začátek a konec. Na Kicku a Twitchi se stáhne rovnou jen ten úsek, na YouTube se stáhne celé video a pak ořízne
3. **Klikni na Stáhnout** — uvidíš procenta, rychlost a zbývající čas.
4. **Hotovo** — video najdeš ve zvolené složce (lze změnit v nastavení) a záznam zůstane v historii aplikace.

Stahování lze kdykoliv zrušit tlačítkem **Zrušit**.

---

## Co všechno aplikace umí

| Funkce | Co to znamená |
|---|---|
| Stáhnout video | Vložíš odkaz, vybereš kvalitu, klikneš na **Stáhnout** |
| Stáhnout jen zvuk | Přepneš formát na MP3, zbytek zůstává stejný |
| Ořezat video | Zadáš začátek a konec — stáhne se jen ta část (na Kicku a Twitchi rovnou jen úsek, YouTube stáhne celé a pak ořízne) |
| Automatický náhled | Po vložení odkazu se sám načte název a obrázek videa |
| Průběh stahování | Vidíš procenta, rychlost a zbývající čas |
| Zrušení stahování | Jedním kliknutím stahování kdykoliv zastavíš |
| Výběr složky | Sám si zvolíš, kam se má video uložit |
| Kick a Twitch | Vyžaduje jednorázové nastavení cookies v Nastavení (návod v nápovědě) |
| Automatické stažení FFmpeg | Na Windows/Linuxu si aplikace FFmpeg sama stáhne a nainstaluje při prvním použití (na macOS je přibalený) |
| Ukládání nastavení | Vše se ukládá automaticky, není potřeba nic potvrzovat |

---

## Nápověda přímo v aplikaci

V horní liště najdeš ikonku otazníku (**❓**) — po kliknutí se otevře nápověda s odpověďmi na časté otázky (na mobilu je v hamburger menu). Obsahuje:

- Jak aplikaci používat krok za krokem
- Jak stáhnout video i jen jeho část
- Jak nastavit cookies pro Kick a Twitch
- Jak nainstalovat FFmpeg na tvém systému
- Řešení nejčastějších problémů

---

## Potřebuješ pomoct?

Máš problém s aplikací nebo dotaz? Nejrychlejší pomoc najdeš na Discordu:

👉 **[Discord komunita](https://discord.gg/5Jcz5RA7E2)**

Prosím nepiš přímo do soukromých zpráv — na Discordu ti pomůže komunita i autoři rychleji a odpověď uvidí i další lidi s podobným problémem.

---

## Podporované systémy

| Systém | Podpora |
|---|---|
| Windows | 10/11 (x86_64) |
| Linux | x86_64 (hotová binárka z Releases); ARM64/ARMv7 (např. Raspberry Pi) ze zdrojového kódu |
| macOS | 12+ (Intel i Apple Silicon) |
| Android | přes Termux, spuštění ze zdrojového kódu |

> **Testování platforem:** vývoj a hlavní testování probíhá na **Linuxu (100 %)**. **Windows** se ověřuje přes **Wine**, **macOS** a ostatní buildy testuje **komunita** — při problému nahlas chybu na [GitHub Issues](https://github.com/Xelvra/aether-downloader/issues).

---

## Historie verzí

Přehled změn v jednotlivých verzích najdeš v [CHANGELOG.md](CHANGELOG.md).

---

## Pro vývojáře

Chceš aplikaci spustit ze zdrojového kódu, upravovat ji nebo si sestavit vlastní binárku? Postup najdeš v [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Licence

Aplikace je pod licencí **MIT** — volně k použití, šíření i úpravám. Plné znění je v [LICENSE](LICENSE).

Přehled licencí závislostí a informace o FFmpeg najdeš v [LICENSE-THIRD-PARTY.md](LICENSE-THIRD-PARTY.md).

---

*Vytvořeno s ❤️ v Pythonu na ~~kulaté~~ ploché zemi.* 🛸
