# Licence třetích stran

Tento dokument shrnuje licence softwaru, který aplikace **Aether Downloader** distribuuje nebo ke své funkci používá. Úplná znění licencí jsou dostupná na odkazovaných stránkách.

## FFmpeg

Aplikace **Aether Downloader** ke své funkci (ořez videa, převod na MP3) využívá nástroj **FFmpeg** (https://ffmpeg.org/).

**macOS:** aplikace **distribuuje** FFmpeg jako součást release balíčku – jedná se o **nezměněnou binárku oficiálního statického buildu** přímo od jeho autorů (žádný zásah do zdrojového kódu, žádné statické linkování do vlastního programu aplikace; FFmpeg se spouští jako samostatný podproces).

**Windows a Linux:** aplikace FFmpeg nedistribuuje v instalačním balíčku. Při prvním použití (ořez, MP3) ho stáhne – **primárně z GitHub Releases mirroru** (release assety se **SHA256 ověřením**), a pokud mirror není k dispozici, z **oficiálního upstreamu** autorů. Tlačítko „Stáhnout FFmpeg“ v Nastavení zůstává jako fallback pro sestavení ze zdrojového kódu.

| Platforma | Primární zdroj (mirror) | Oficiální upstream |
|-----------|-------------------------|--------------------|
| Windows   | GitHub Releases (release asset `ffmpeg-windows-x86_64-essentials.zip`) | https://www.gyan.dev/ffmpeg/builds/ |
| Linux     | GitHub Releases (release asset `ffmpeg-linux-x86_64-static.tar.xz`) | https://johnvansickle.com/ffmpeg/ |
| macOS     | GitHub Releases (release asset `ffmpeg-macos.zip`) | https://evermeet.cx/ |

FFmpeg je volně šiřitelný software pod licencí **LGPL 2.1+** nebo **GPL 2+** (podle konfigurace konkrétního buildu). Oficiální znění licencí a informace o kompilaci najdeš na:

- https://ffmpeg.org/legal.html
- https://www.gnu.org/licenses/lgpl-2.1.html
- https://www.gnu.org/licenses/gpl-2.0.html

Zdrojové kódy statických buildů a konfigurace najdeš u příslušných autorů (odkazy výše).

## Zabalené Python závislosti

Release binárka (PyInstaller) zabaluje Python runtime a níže uvedené balíčky. Licenční údaje jsou ověřené podle metadat distribucí:

| Balíček | Licence | Zdroj |
|---------|---------|-------|
| Python (runtime + standardní knihovna) | PSF License | https://docs.python.org/3/license.html |
| Flet (`flet`, `flet-desktop`, `flet-web`) | Apache-2.0 | https://github.com/flet-dev/flet |
| yt-dlp | Unlicense | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | Unlicense AND MIT AND ISC | https://github.com/yt-dlp/ejs |
| curl-cffi | MIT | https://github.com/lexiforest/curl_cffi |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |

> Apache-2.0 (Flet) při redistribuci vyžaduje zachování licenčních údajů a případných NOTICE souborů – tyto údaje jsou součástí balíčku Flet. MPL-2.0 (certifi) je slabě copyleftová licence; její znění najdeš na odkazu výše.

PyInstaller (použitý jen při sestavení binárky, není součástí distribuce) je pod licencí **GPL-2.0-or-later se zvláštní výjimkou**, která povoluje použití PyInstalleru k sestavení binárek: https://github.com/pyinstaller/pyinstaller
