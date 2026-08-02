# Aether Downloader

> Jednoduchá aplikace na stahování videí z YouTube, Kicku, Twitche a mnoha dalších webů.

**Žádný terminál, žádné příkazy, žádné technické znalosti.** Vložíš odkaz, klikneš na tlačítko a video se ti uloží do počítače.

[![Licence: MIT](https://img.shields.io/badge/licence-MIT-green.svg)](LICENSE)
![Platformy](https://img.shields.io/badge/platformy-Windows%20%7C%20Linux%20%7C%20macOS%20%7C%20Android-blue)

---

## Obsah

- [Rychlý start](#rychlý-start-3-kroky)
- [Instalace](#instalace-a-spuštění)
- [Instalace FFmpeg](#instalace-ffmpeg-nutný-krok)
- [Jak stáhnout první video](#jak-stáhnout-první-video)
- [Přehled funkcí](#co-všechno-aplikace-umí)
- [Nápověda v aplikaci](#nápověda-přímo-v-aplikaci)
- [Potřebuješ pomoct?](#potřebuješ-pomoct)
- [Podporované systémy](#podporované-systémy)
- [Pro vývojáře](#pro-vývojáře)
- [Licence](#licence)

---

## Rychlý start (3 kroky)

1. Stáhni si aplikaci pro svůj počítač ze sekce [Releases](https://github.com/Xelvra/aether-downloader/releases).
2. Spusť aplikaci, vlož odkaz na video a klikni na **Stáhnout**. Pokud aplikace potřebuje **FFmpeg** a nemá ho, nabídne ti ho ke stažení jedním tlačítkem.
3. Hotovo — video je tvoje.

Podrobný postup pro konkrétní systém najdeš níže.

---

## Instalace a spuštění

### 🪟 Windows

1. Na [stránce Releases](https://github.com/Xelvra/aether-downloader/releases) stáhni nejnovější `.zip` pro Windows.
2. Rozbal ho (pravé tlačítko myši → **Rozbalit vše**).
3. V rozbalené složce spusť `stahovac.exe`.
4. Windows pravděpodobně zobrazí modrou obrazovku s varováním — to je normální, protože aplikace nemá placený certifikát od Microsoftu. Klikni na **Další informace** → **Přesto spustit**.

> ⚠️ Před prvním stahováním ještě nainstaluj FFmpeg — viz [sekce níže](#instalace-ffmpeg-nutný-krok). Nejjednodušší je kliknout v aplikaci na tlačítko **Stáhnout FFmpeg**.

### 🐧 Linux

1. Na [stránce Releases](https://github.com/Xelvra/aether-downloader/releases) stáhni verzi pro Linux a rozbal archiv.
2. Soubor `stahovac` je potřeba nejdřív „odemknout" pro spuštění:

   **Přes grafické rozhraní:**
   Pravé tlačítko na `stahovac` → **Vlastnosti** → záložka **Oprávnění** → zaškrtni **Povolit spouštění souboru jako programu**.

   **Přes terminál:**
   ```bash
   chmod +x stahovac
   ./stahovac
   ```
3. Poklepej na soubor `stahovac` a aplikace se spustí.

> ⚠️ Před prvním stahováním ještě nainstaluj FFmpeg — viz [sekce níže](#instalace-ffmpeg-nutný-krok).

### 🍎 macOS

1. Na [stránce Releases](https://github.com/Xelvra/aether-downloader/releases) stáhni verzi pro macOS a rozbal archiv.
2. Systém aplikaci při prvním spuštění zablokuje, protože pochází od neznámého vývojáře — to je normální:
   - **Nastavení systému → Soukromí a zabezpečení**
   - Sjeď dolů, najdi hlášku o zablokované aplikaci a klikni na **Otevřít přesto**.

> ⚠️ Před prvním stahováním ještě nainstaluj FFmpeg — viz [sekce níže](#instalace-ffmpeg-nutný-krok).

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

---

## Instalace FFmpeg (nutný krok)

Aplikace potřebuje **FFmpeg** k ořezu videa nebo převodu na MP3. Bez něj se při spuštění zobrazí upozornění a některé funkce nebudou fungovat.

**Nejjednodušší varianta:** klikni v aplikaci na oranžové upozornění s tlačítkem **Stáhnout FFmpeg** — aplikace ho sama stáhne, nainstaluje do složky `bin/` a použije. Žádný terminál není potřeba.

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
| Automatické stažení FFmpeg | Chybí-li FFmpeg, aplikace ho jedním kliknutím sama stáhne a nainstaluje |
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
| Linux | x86_64, ARM64, ARMv7 (např. Raspberry Pi) |
| macOS | 12+ (Intel i Apple Silicon) |
| Android | přes Termux, spuštění ze zdrojového kódu |

---

## Pro vývojáře

Chceš aplikaci spustit ze zdrojového kódu, upravovat ji nebo si sestavit vlastní binárku? Postup najdeš v [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Licence

Aplikace je pod licencí **MIT** — volně k použití, šíření i úpravám. Plné znění je v [LICENSE](LICENSE).

Přehled licencí závislostí a informace o FFmpeg najdeš v [LICENSE-THIRD-PARTY.md](LICENSE-THIRD-PARTY.md).

---

*Vytvořeno s ❤️ v Pythonu na ~~kulaté~~ ploché zemi.* 🛸
