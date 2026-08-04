# Pravidla vývoje (regresní ochrana)

Tohle jsou **pevná pravidla**, přes která nejede vlak. Jejich smysl je jediný:
zabránit regresím – tedy tomu, aby se opravou nebo novou funkcí rozbilo něco,
co dřív fungovalo. Dodržují se při každé změně kódu, bez výjimky.

---

## 1. Red-Green-Refactor

Nejdřív test, pak kód. Při každé nové funkci nebo opravě bugu:

1. **Napiš test, který selže** – ověřuje novou funkci, nebo reprodukuje bug.
2. **Teprve pak uprav kód aplikace**, aby tento test prošel.
3. **Nakonec** spusť celý test suite – musí zůstat zelený.

Test, který selže PŘED opravou, se smí smazat jen tehdy, když prokazatelně
netestuje skutečné chování (nebo bylo chování záměrně změněno).

## 2. Každý bug nese regresní test

Když je nalezena a opravena chyba (hlášená uživatelem, z CI, z auditu…), musí
s opravou přibýt **samostatný test**, který tu chybu reprodukuje. Test patří do
souboru odpovídajícího dotčenému modulu a má popisný název odkazující na
problém (např. `test_real_auto_install_does_not_crash`, `test_opts_built_after_ffmpeg_becomes_ready`).

Bez regresního testu se oprava nepovažuje za hotovou.

## 3. Gate před commitem

Před každým commitem musí projít **všechny** tyto kontroly:

```bash
uv run --extra dev ruff check .            # lint
uv run --extra dev ruff format --check .   # formátování
uv run --extra dev mypy stahovac/          # statická typová kontrola
uv run --extra dev pytest --cov            # celý suite, pokrytí ≥ 80 %
```

Kterýkoliv červený výsledek → opravit, teprve pak commit.

## 4. Determinismus a nezávislost testů

- Testy **nesmí záviset na síti** – síťové volání se mockuje (`yt_dlp`,
  `urllib`, `ffmpeg`, `MetadataService`).
- Testy **nesmí záviset na reálném čase** – `time.time()` se monkeypatchuje,
  debounce/force-stop Timery se v testu ruší nebo volají přímo.
- Žádné sdílené měnitelné globální stavy mezi testy; soubory se vytvářejí
  přes fixture `tmp_path`; proměnné prostředí přes `monkeypatch`.
- Každý test je **nezávislý** – dá se spustit samostatně i v libovolném pořadí.

## 5. Logika vs. UI

- **Logika** (bez Fletu: `core/`, `config/`, `models.py`, `state.py`,
  `storage/`, `utils/`, `downloader.py`, `platforms/`) se testuje unit testy
  bez flet závislosti.
- **UI** (`gui/`) jen čte/zapisuje props Flet widgetů a volá logiku přes
  `DownloadManager`/`MetadataService`/`AppConfig`. UI testy konstruují widgety
  bez běžícího Fletu, volají event handlery a tvrdí změny props + volané
  callbacky. Žádné byznys validace v UI vrstvě (viz §6).
- Byznys validace stahování žije v `core/validator.py` /
  `DownloadManager.validate()` – do GUI se nekopíruje.

## 6. Rozsah změn

- Jeden PR/commit = jedna změna. Menší změna se líp kontroluje i testuje.
- Bez nové závislosti bez diskuze – každá knihovna zvětšuje binárku.
- `uv.lock` se mění jen tehdy, když se záměrně mění závislosti
  (`uv lock`, ne ruční editace).
- GUI zůstává vyloučené z coverage gate (widgety mají mnoho větví), ale
  **musí mít unit testy** – nepřidávej do `gui/*` metodu bez testu.

---

*Pravidla vycházejí z auditu `tool/audit-aether-downloader.md` (sekce Testy) –
konvence testů najdeš v `tests/README.md`.*
