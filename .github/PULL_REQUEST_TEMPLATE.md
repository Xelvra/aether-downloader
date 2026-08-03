## Popis změny

Stručně popiš, co tahle změna dělá a proč je potřeba.

## Typ změny

- [ ] Oprava (bug fix)
- [ ] Nová funkce
- [ ] Dokumentace
- [ ] CI / nástroje
- [ ] Jiné

## Testování

Před odesláním PR spusť (viz [CONTRIBUTING.md](CONTRIBUTING.md)):

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy stahovac`
- [ ] `uv run pytest --cov` (práh ≥ 80 %)

## Kontrolní seznam

- [ ] Jeden PR = jedna změna
- [ ] Bez zbytečných nových závislostí
- [ ] Funguje na Windows, Linuxu i macOS (nebo je to v popisu označeno)
