#!/usr/bin/env python3
"""Utility di debug: scarica le pagine usate dal bot per una lega e le
salva su disco, cosi' da poter verificare/correggere i selettori in
app/fantacalcio/parser.py con l'HTML reale.

Va eseguito da una macchina che HA accesso di rete a
leghe.fantacalcio.it (in questo ambiente di sviluppo l'accesso e'
bloccato dal proxy).

Uso:
    python scripts/dump_pages.py <league_id> [--matchday N] [--out DIR]

Richiede che config/leagues.yaml e il relativo cookie di sessione in
.env siano gia' configurati (vedi README).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_config  # noqa: E402
from app.fantacalcio.client import FantacalcioClient, PATH_CLASSIFICA, PATH_RISULTATI  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("league_id", help="ID della lega, come in config/leagues.yaml")
    parser.add_argument("--matchday", type=int, default=1, help="Giornata per la pagina risultati")
    parser.add_argument("--out", default="tests/fixtures/dump", help="Cartella di output")
    args = parser.parse_args()

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Errore di configurazione: {exc}", file=sys.stderr)
        sys.exit(1)

    league = next((l for l in config.leagues if l.id == args.league_id), None)
    if league is None:
        print(f"Lega '{args.league_id}' non trovata.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with FantacalcioClient(league) as client:
        classifica_html = client._get(PATH_CLASSIFICA)  # noqa: SLF001 (script di debug)
        (out_dir / "classifica.html").write_text(classifica_html, encoding="utf-8")
        print(f"Salvato {out_dir / 'classifica.html'}")

        try:
            risultati_html = client._get(f"{PATH_RISULTATI}?giornata={args.matchday}")  # noqa: SLF001
            (out_dir / f"risultati_giornata{args.matchday}.html").write_text(
                risultati_html, encoding="utf-8"
            )
            print(f"Salvato {out_dir / f'risultati_giornata{args.matchday}.html'}")
        except Exception as exc:  # noqa: BLE001
            print(f"Impossibile scaricare la pagina risultati: {exc}", file=sys.stderr)

    print(
        "\nOra confronta questi file con i selettori in "
        "app/fantacalcio/parser.py e correggili di conseguenza."
    )


if __name__ == "__main__":
    main()
