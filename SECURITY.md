# Bezpečnost

Aplikace pracuje s cookies, tokeny a stahuje obsah z webů – bezpečnost bereme
vážně a zranitelnosti řešíme přednostně.

## Podporované verze

Bezpečnostní opravy vydáváme pro **nejnovější release**. Starší verze nejsou
podporované – prosím aktualizuj na nejnovější verzi z
[Releases](https://github.com/Xelvra/aether-downloader/releases).

## Hlášení zranitelnosti

Zranitelnost nahlas **soukromě** – nezakládej veřejné issue a nediskutuj ji
veřejně, dokud nevyjde oprava. Použij GitHub Private Vulnerability Reporting:

- https://github.com/Xelvra/aether-downloader/security/advisories/new

## Co hlášení obsahuje

- typ problému (např. únik dat, RCE, XSS, injekce příkazu),
- ovlivněná verze a platforma,
- kroky k reprodukci (bez citlivých údajů, jako jsou cookies nebo tokeny),
- dopad a případně návrh opravy.

## Proces

1. Potvrzení přijetí hlášení do 72 hodin.
2. Vyhodnocení závažnosti a dopadu.
3. Oprava v hlavní větvi a vydání release.
4. Zveřejnění zranitelnosti až po vydání opravy (advisory).

## Bezpečné používání aplikace

- Webový režim nemá žádné přihlášení. Výchozí adresa `127.0.0.1` je přístupná
  jen z daného zařízení – neměň `AETHER_HOST` / `--host`, jinak bude mít
  k souborům a stahování přístup kdokoli v síti.
- Cookies a tokeny se používají jen pro konkrétní stahování a neunikají do
  logů.
