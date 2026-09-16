#!/usr/bin/env python3
"""Utility di debug: scarica le risposte JSON usate dal bot per una lega e
le salva su disco, cosi' da poter verificare/completare il parsing in
app/fantacalcio/parser.py con dati reali.

Va eseguito da una macchina che HA accesso di rete a
apileague.fantacalcio.it (in questo ambiente di sviluppo l'accesso e'
bloccato dal proxy).

Uso:
    python scripts/dump_pages.py <league_id> [--out DIR]

Richiede che config/leagues.yaml e la relativa api_key in .env siano gia'
configurati (vedi README).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import ConfigError, load_config  # noqa: E402
from app.fantacalcio.client import FantacalcioClient  # noqa: E402

ENDPOINTS = {
    "league_status": "/onboarding/v1/league/status",
    "team_lineup_visualizza": "/gaming/v1/teamLineup/visualizza/{division}/{competition_id}",
    "teams": "/onboarding/v1/league/teams?page=1&division={division}",
    "calendar": "/onboarding/v1/league/competition/calendar/{competition_id}",
    "competition_teams": (
        "/onboarding/v1/league/competition/teams"
        "?page=1&pageSize=50&competitionId={competition_id}"
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("league_id", help="ID della lega, come in config/leagues.yaml")
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
        for name, path_template in ENDPOINTS.items():
            path = path_template.format(
                division=league.division, competition_id=league.competition_id
            )
            try:
                data = client._get(path)  # noqa: SLF001 (script di debug)
            except Exception as exc:  # noqa: BLE001
                print(f"[{name}] Errore: {exc}", file=sys.stderr)
                continue
            out_file = out_dir / f"{name}.json"
            out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Salvato {out_file}")

    print(
        "\nOra confronta questi file con gli schemi attesi in "
        "app/fantacalcio/parser.py e completa il parsing di 'calendar' e "
        "'competition_teams' se mancante."
    )


if __name__ == "__main__":
    main()
