# Licence třetích stran

## FFmpeg

Aplikace **Aether Downloader** ke své funkci (ořez videa, převod na MP3) využívá nástroj **FFmpeg** (https://ffmpeg.org/).

**macOS:** aplikace **distribuuje** FFmpeg jako součást release balíčku – jedná se o **nezměněnou binárku oficiálního statického buildu** přímo od jeho autorů (žádný zásah do zdrojového kódu, žádné statické linkování do vlastního programu aplikace; FFmpeg se spouští jako samostatný podproces).

**Windows a Linux:** aplikace FFmpeg nedistribuuje. Buď ho použije, pokud je už nainstalovaný v systému (systémová instalace uživatele), nebo na požádání stáhne **oficiální statický build** přímo od jeho autorů. Tlačítko „Stáhnout FFmpeg“ v Nastavení zůstává jako fallback pro sestavení ze zdrojového kódu.

| Platforma | Zdroj |
|-----------|-------|
| Windows   | https://www.gyan.dev/ffmpeg/builds/ |
| Linux     | https://johnvansickle.com/ffmpeg/ |
| macOS     | https://evermeet.cx/ |

FFmpeg je volně šiřitelný software pod licencí **LGPL 2.1+** nebo **GPL 2+** (podle konfigurace konkrétního buildu). Oficiální znění licencí a informace o kompilaci najdeš na:

- https://ffmpeg.org/legal.html
- https://www.gnu.org/licenses/lgpl-2.1.html
- https://www.gnu.org/licenses/gpl-2.0.html

Zdrojové kódy statických buildů a konfigurace najdeš u příslušných autorů (odkazy výše).
