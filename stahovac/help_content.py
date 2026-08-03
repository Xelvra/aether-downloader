"""Strukturovaný obsah nápovědy aplikace.

Data jsou oddělená od vykreslování (`stahovac/gui/help_view.py`), aby se
obsah dal snadno udržovat, testovat a případně prohledávat.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpText:
    """Obyčejná sekce: titulek a odstavce."""

    title: str
    items: tuple[str, ...]


@dataclass(frozen=True)
class HelpCode:
    """Blok příkazů; řádky začínající ``#`` se vykreslí jako komentář."""

    lines: tuple[str, ...]


@dataclass(frozen=True)
class HelpQA:
    """Sekce s dotazy a odpověďmi."""

    title: str
    items: tuple[tuple[str, str], ...]


HELP_SECTIONS: tuple[HelpText | HelpCode | HelpQA, ...] = (
    HelpText(
        "Co aplikace umí",
        (
            "Stahuje videa ze stovek webů – YouTube, Kick, Twitch, Vimeo, TikTok a další.",
            "Umí stáhnout jen zvuk (MP3), jen titulky (SRT) i oříznout video na časový úsek.",
            "Po vložení odkazu sama načte název, autora a délku videa.",
            "Průběh stahování vidíš na procenta a můžeš ho kdykoli zrušit.",
            "Nastavení si pamatuje a ukládá samo.",
        ),
    ),
    HelpText(
        "Jak stáhnout první video",
        (
            "1. Na kartě Stahování vlož adresu (URL) videa do pole „Odkaz na video“.",
            "2. Počkej chvíli – aplikace sama zjistí název, autora a délku.",
            "3. Přejdi na kartu Ořez a vyber kvalitu a formát (vysvětleno v sekci níže).",
            "4. Klikni na tlačítko Stáhnout.",
            "5. Hotový soubor najdeš ve složce z karty Nastavení (výchozí je downloads vedle aplikace).",
        ),
    ),
    HelpText(
        "Jak si vybrat formát",
        (
            "Na kartě Ořez je roletka „Formát výstupu“. Na výběr jsou tři možnosti:",
            "– Video + audio (MP4): klasické video, vybereš kvalitu od 144p až po 4K.",
            "– Pouze zvuk (MP3): jen zvuk, hodí se třeba na hudbu.",
            "– Pouze titulky (SRT): textové titulky; každý jazyk se uloží jako samostatný soubor.",
        ),
    ),
    HelpText(
        "Jak oříznout video",
        (
            "Ořez využiješ, když nechceš stáhnout celé video, ale jen určitý úsek – "
            "třeba jednu minutovou část z hodinového přenosu.",
            "",
            "Postup:",
            "1. Na kartě Ořez odškrtni zaškrtávací políčko „Stáhnout celé video bez ořezu“.",
            "2. Do pole „Začátek ořezu“ zadej, od které vteřiny se má úsek vzít.",
            "3. Vyber, jak má úsek končit:",
            "   – „Do konce“ – až do samého konce videa, nebo",
            "   – „Do času“ – do konkrétní vteřiny, kterou doplníš do pole „Konec ořezu“.",
            "4. Stáhni jako obvykle.",
            "",
            "Čas se zadává ve tvaru Hodiny:Minuty:Sekundy (např. 01:20:00). "
            "Kratší zápisy fungují taky – Minuty:Sekundy (např. 05:30) nebo jen Sekundy (např. 90).",
            "",
            "Co dostaneš:",
            "Hotový soubor má v názvu časový rozsah (např. „Video [01h20m00s - 02h00m00s].mp4“), "
            "aby bylo hned jasné, o jaký úsek jde.",
            "",
            "Rychlost:",
            "– Na Kicku a Twitchi se stahuje rovnou jen vybraný úsek. Z hodinového přenosu "
            "se tak stáhne jen malý kousek a nic se nestahuje navíc.",
            "– Na YouTube a dalších webech se stáhne celé video a vybraný úsek se z něj "
            "následně vyřízne. Výsledek je stejný, jen stahování trvá déle a dočasně "
            "zabere víc místa na disku.",
            "",
            "Přesnost ořezu:",
            "– Výchozí (rychlý) ořez je přesný zhruba na pár sekund, kvalita zůstává stejná.",
            "– Potřebuješ-li úsek přesný co do vteřiny, zaškrtni na kartě Ořez možnost "
            "„Překódovat (přesnější ořez, pomalejší)“ – zpracování je pomalejší, ale výsledek je přesný.",
        ),
    ),
    HelpText(
        "Cookies pro Kick a Twitch",
        (
            "Některé weby (např. Kick a Twitch) vyžadují přihlášení, jinak stahování nefunguje.",
            "1. Přejdi na kartu Nastavení.",
            "2. V roletce „Importovat cookies z prohlížeče“ vyber svůj prohlížeč.",
            "3. Hotovo – aplikace se pak tváří jako přihlášený uživatel.",
            "Tohle pomáhá hlavně při chybě 403 (přístup odepřen).",
            "Poznámka: cookies se používají jen pro Kick a Twitch – na YouTube se záměrně neaplikují.",
        ),
    ),
    HelpText(
        "Safari na macOS (obtížné čtení cookies)",
        (
            "Pokud na macOS vybereš Safari a sub-only videa na Kicku/Twitchi nejdou stáhnout, "
            "je to skoro jistě tím, že systém brání aplikaci přečíst Safari cookies "
            "ochranou soukromí (TCC). Chrome/Firefox tímto problémem netrpí.",
            "Řešení: v Systémovém nastavení → Soukromí a zabezpečení → Plný přístup k disku "
            "přidej stahovac.app, aplikaci restartuj a zkus to znovu.",
            "Nebo prostě vyber Chrome/Firefox, případně vyexportuj cookies.txt a vyber „Vlastní soubor (cookies.txt)“.",
        ),
    ),
    HelpText(
        "Instalace FFmpeg",
        (
            "FFmpeg je malý program, který aplikace potřebuje pro ořez videa a převod na MP3.",
            "Když ho poprvé využiješ (ořez nebo MP3), aplikace si ho stáhne a nainstaluje sama – "
            "průběh uvidíš jako u běžného stahování. Nic dalšího nastavovat nemusíš.",
            "Stav FFmpeg a případné ruční stažení nebo přeinstalaci najdeš na kartě Nastavení.",
            "Chceš-li ho nainstalovat raději ručně, použij jeden z příkazů podle svého systému:",
        ),
    ),
    HelpCode(
        (
            "# Debian / Ubuntu / Linux Mint",
            "$ sudo apt install ffmpeg",
            "",
            "# Arch Linux / Manjaro",
            "$ sudo pacman -S ffmpeg",
            "",
            "# Fedora / RHEL",
            "$ sudo dnf install ffmpeg",
            "",
            "# Android (Termux)",
            "$ pkg install ffmpeg",
            "",
            "# macOS (přes Homebrew)",
            "$ brew install ffmpeg",
            "",
            "# Windows",
            "$ winget install ffmpeg",
        ),
    ),
    HelpText(
        "Licence FFmpeg",
        (
            "FFmpeg je otevřený software pod licencí LGPL/GPL.",
            "Na macOS je FFmpeg součástí aplikace – nezměněný oficiální build, "
            "který se spouští jako samostatný program.",
            "Na Windows a Linuxu ho aplikace stahuje na vyžádání, vždy oficiální build "
            "přímo od tvůrců. Podrobnosti: https://ffmpeg.org/legal.html",
        ),
    ),
    HelpQA(
        "Časté problémy",
        (
            (
                "Stahování nezačíná",
                "Zkontroluj připojení k internetu a jestli je adresa videa platná. "
                "Některá videa jsou v některých zemích blokovaná.",
            ),
            (
                "Stahování probíhá dvakrát",
                "Některá videa se stahují ve dvou krocích – nejdřív obraz, pak zvuk – "
                "a aplikace je pak sama spojí do jednoho souboru. To je normální.",
            ),
            (
                "Chyba 403 (přístup odepřen)",
                "Přejdi na kartu Nastavení a vyber svůj prohlížeč pro cookies (viz sekce Cookies).",
            ),
            (
                "Ořez není přesný",
                "Rychlý ořez může být o pár sekund vedle. Pro přesný výsledek zaškrtni "
                "na kartě Ořez možnost „Překódovat“.",
            ),
            (
                "Stahování s ořezem je pomalé (na YouTube)",
                "YouTube a některé další weby nedovolují stáhnout rovnou jen úsek, "
                "proto se stáhne celé video a teprve pak se vyřízne. Výsledek je stejný, "
                "jen to trvá déle. Na Kicku a Twitchi se stahuje rovnou jen vybraný úsek.",
            ),
            (
                "Chci stáhnout video znovu",
                "Existující soubor aplikace nikdy nepřepíše. Pokud stáhneš stejné video "
                "do stejné složky, nový soubor dostane příponu (1), (2) atd.",
            ),
            (
                "Historie je prázdná",
                "Historie ukazuje jen to, co už bylo staženo. Dokud nic nestáhneš, je prázdná – to je normální.",
            ),
            (
                "Jak aplikaci aktualizovat",
                "Stáhni si nejnovější verzi na stránce Releases projektu na GitHubu.",
            ),
        ),
    ),
    HelpText(
        "Webová verze (Android a počítače bez obrazovky)",
        (
            "Pokud aplikaci spustíš na zařízení bez obrazovky (např. Android Termux), "
            "automaticky se otevře jako webová stránka.",
            "Adresu, na které běží, najdeš v terminálu, kde jsi ji spustil – stačí ji otevřít v prohlížeči.",
            "Pozor: výchozí adresa 127.0.0.1 je přístupná jen z tohoto zařízení. "
            "Když server zpřístupníš jiným zařízením v síti (AETHER_HOST / --host), "
            "kdokoli v síti může procházet soubory a spouštět stahování – nemění adresu jen tak.",
        ),
    ),
)
