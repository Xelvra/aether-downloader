import flet as ft

from stahovac.gui.theme import (
    COLOR_ACCENT,
    COLOR_SURFACE,
    COLOR_TEXT,
    COLOR_TEXT_SECONDARY,
    ICON_SIZE_LARGE,
    sz,
)


def _section(title: str, *items: str) -> ft.Column:
    return ft.Column(
        [
            ft.Text(title, size=sz(16), weight=ft.FontWeight.BOLD, color=COLOR_ACCENT),
            ft.Column(
                [ft.Text(item, size=sz(13), color=COLOR_TEXT, selectable=True) for item in items],
                spacing=sz(6),
            ),
        ],
        spacing=sz(8),
    )


_COMMENT_COLOR = "#707090"
_CMD_COLOR = COLOR_ACCENT


def _code_block(*lines: str) -> ft.Container:
    children: list[ft.Control] = []
    for line in lines:
        color = _COMMENT_COLOR if line.startswith("#") else _CMD_COLOR
        children.append(ft.Text(line, size=sz(12), color=color, font_family="monospace", selectable=True))
    return ft.Container(
        content=ft.Column(children, spacing=sz(2)),
        padding=sz(12),
        border_radius=sz(8),
        bgcolor="#1A1A2E",
    )


def _qa(question: str, answer: str) -> ft.Column:
    return ft.Column(
        [
            ft.Text(question, size=sz(13), weight=ft.FontWeight.BOLD, color=COLOR_TEXT),
            ft.Text(answer, size=sz(13), color=COLOR_TEXT, selectable=True),
        ],
        spacing=sz(2),
    )


def build_help_content(dismiss_callback) -> ft.Container:
    scrollable = ft.Container(
        content=ft.Column(
            [
                ft.Text("Nápověda", size=sz(20), weight=ft.FontWeight.BOLD, color=COLOR_TEXT),
                ft.Divider(color=COLOR_SURFACE),
                _section(
                    "Co aplikace umí",
                    "Stahuje videa ze stovek webů – YouTube, Kick, Twitch, Vimeo, TikTok a další.",
                    "Umí stáhnout jen zvuk (MP3), jen titulky (SRT) i oříznout video na časový úsek.",
                    "Po vložení odkazu sama načte název, autora a délku videa.",
                    "Průběh stahování vidíš na procenta a můžeš ho kdykoli zrušit.",
                    "Nastavení si pamatuje a ukládá samo.",
                ),
                _section(
                    "Jak stáhnout první video",
                    "1. Na kartě Stahování vlož adresu (URL) videa do pole „Odkaz na video“.",
                    "2. Počkej chvíli – aplikace sama zjistí název, autora a délku.",
                    "3. Přejdi na kartu Ořez a vyber kvalitu a formát (vysvětleno v sekci níže).",
                    "4. Klikni na tlačítko Stáhnout.",
                    "5. Hotový soubor najdeš ve složce z karty Nastavení (výchozí je downloads vedle aplikace).",
                ),
                _section(
                    "Jak si vybrat formát",
                    "Na kartě Ořez je roletka „Formát výstupu“. Na výběr jsou tři možnosti:",
                    "– Video + audio (MP4): klasické video, vybereš kvalitu od 144p až po 4K.",
                    "– Pouze zvuk (MP3): jen zvuk, hodí se třeba na hudbu.",
                    "– Pouze titulky (SRT): textové titulky; každý jazyk se uloží jako samostatný soubor.",
                ),
                _section(
                    "Jak oříznout video",
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
                _section(
                    "Cookies pro Kick a Twitch",
                    "Některé weby (např. Kick a Twitch) vyžadují přihlášení, jinak stahování nefunguje.",
                    "1. Přejdi na kartu Nastavení.",
                    "2. V roletce „Importovat cookies z prohlížeče“ vyber svůj prohlížeč.",
                    "3. Hotovo – aplikace se pak tváří jako přihlášený uživatel.",
                    "Tohle pomáhá hlavně při chybě 403 (přístup odepřen).",
                    "Poznámka: cookies se používají jen pro Kick a Twitch – na YouTube se záměrně neaplikují.",
                ),
                _section(
                    "Instalace FFmpeg",
                    "FFmpeg je malý program, který aplikace potřebuje pro ořez videa a převod na MP3.",
                    "Pokud není nainstalovaný, uvidíš u spodního okraje oranžové upozornění "
                    "s tlačítkem „Stáhnout FFmpeg“.",
                    "Nejjednodušší je na to tlačítko kliknout – aplikace FFmpeg stáhne "
                    "a nainstaluje sama, nic dalšího nastavovat nemusíš.",
                    "Chceš-li ho nainstalovat raději ručně, použij jeden z příkazů podle svého systému:",
                ),
                _code_block(
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
                _section(
                    "Licence FFmpeg",
                    "FFmpeg je otevřený software pod licencí LGPL/GPL.",
                    "Aplikace sama FFmpeg nedistribuuje – když ho stáhneš tlačítkem, "
                    "stahuješ oficiální build přímo od jeho tvůrců. "
                    "Podrobnosti: https://ffmpeg.org/legal.html",
                ),
                _section("Časté problémy"),
                _qa(
                    "Stahování nezačíná",
                    "Zkontroluj připojení k internetu a jestli je adresa videa platná. "
                    "Některá videa jsou v některých zemích blokovaná.",
                ),
                _qa(
                    "Stahování probíhá dvakrát",
                    "Některá videa se stahují ve dvou krocích – nejdřív obraz, pak zvuk – "
                    "a aplikace je pak sama spojí do jednoho souboru. To je normální.",
                ),
                _qa(
                    "Chyba 403 (přístup odepřen)",
                    "Přejdi na kartu Nastavení a vyber svůj prohlížeč pro cookies (viz sekce Cookies).",
                ),
                _qa(
                    "Ořez není přesný",
                    "Rychlý ořez může být o pár sekund vedle. Pro přesný výsledek zaškrtni "
                    "na kartě Ořez možnost „Překódovat“.",
                ),
                _qa(
                    "Stahování s ořezem je pomalé (na YouTube)",
                    "YouTube a některé další weby nedovolují stáhnout rovnou jen úsek, "
                    "proto se stáhne celé video a teprve pak se vyřízne. Výsledek je stejný, "
                    "jen to trvá déle. Na Kicku a Twitchi se stahuje rovnou jen vybraný úsek.",
                ),
                _qa(
                    "Chci stáhnout video znovu",
                    "Existující soubor aplikace nikdy nepřepíše. Pokud stáhneš stejné video "
                    "do stejné složky, nový soubor dostane příponu (1), (2) atd.",
                ),
                _qa(
                    "Historie je prázdná",
                    "Historie ukazuje jen to, co už bylo staženo. Dokud nic nestáhneš, je prázdná – to je normální.",
                ),
                _qa(
                    "Jak aplikaci aktualizovat",
                    "Stáhni si nejnovější verzi na stránce Releases projektu na GitHubu.",
                ),
                _section(
                    "Webová verze (Android a počítače bez obrazovky)",
                    "Pokud aplikaci spustíš na zařízení bez obrazovky (např. Android Termux), "
                    "automaticky se otevře jako webová stránka.",
                    "Adresu, na které běží, najdeš v terminálu, kde jsi ji spustil – stačí ji otevřít v prohlížeči.",
                    "Pozor: výchozí adresa 127.0.0.1 je přístupná jen z tohoto zařízení. "
                    "Když server zpřístupníš jiným zařízením v síti (AETHER_HOST / --host), "
                    "kdokoli v síti může procházet soubory a spouštět stahování – nemění adresu jen tak.",
                ),
                ft.Divider(color=COLOR_SURFACE),
                ft.Text(
                    "Další informace najdeš v README nebo na GitHub Issues.",
                    size=sz(12),
                    color=COLOR_TEXT_SECONDARY,
                    italic=True,
                ),
            ],
            spacing=sz(16),
            scroll=ft.ScrollMode.ALWAYS,
        ),
        padding=ft.Padding(sz(48), sz(20), sz(20), sz(20)),
        expand=True,
    )

    close_btn = ft.Container(
        content=ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_color=COLOR_TEXT_SECONDARY,
            icon_size=ICON_SIZE_LARGE,
            on_click=lambda e: dismiss_callback(),
        ),
        right=sz(8),
        top=sz(8),
    )

    return ft.Container(
        content=ft.Stack([scrollable, close_btn]),
        bgcolor=COLOR_SURFACE,
        border_radius=sz(12),
        expand=True,
    )
