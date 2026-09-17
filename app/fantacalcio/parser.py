"""Parsing delle risposte JSON dell'API di Leghe Fantacalcio verso i
modelli normalizzati.

============================================================================
VERIFICATO CONTRO CHIAMATE REALI (HAR)
============================================================================
A differenza di una prima versione basata su scraping HTML (poi scartata),
questi endpoint e questi campi sono stati osservati direttamente in due
export HAR di richieste reali fatte dal browser dell'utente verso
https://apileague.fantacalcio.it, con risposte 200 e corpo JSON completo:

- GET /onboarding/v1/league/status
  -> {"sto": bool, "activ": bool, "sId": int, "mday": int, "mstr": "ISO"}
  "mday" = numero di giornata di Serie A della PROSSIMA giornata della
  lega da giocare/calcolare; "mstr" = data/ora di inizio (= deadline
  formazioni) di quella giornata.

- GET /gaming/v1/teamLineup/visualizza/{division}/{competitionId}
  -> {"teamLineupDto": {"mday": int, "cmday": int, "tid": int, ...}}
  "mday" qui e' il numero di GIORNATA INTERNA DELLA LEGA (1, 2, 3, ...)
  corrispondente a "cmday" = numero di giornata di Serie A. Usato per
  mappare giornata-lega <-> giornata-Serie A (l'offset e' costante per
  competizione, es. giornata lega 2 = giornata Serie A 5).

- GET /onboarding/v1/league/teams?page=1&division={division}
  -> {"data": [{"id": int, "n": "nome squadra", "nu": "username", ...}]}
  Usato per risalire all'ID squadra a partire dal nome configurato
  (FANTACALCIO_TEAM_NAME).

- GET /gaming/v1/teamLineup/{competitionId}/{round}/{serieAMday}/{teamA}/{teamB}
  -> {"cal": bool, "mday": round, "cmday": serieAMday,
      "home": {"tid": int, "tot": float, "points": int, ...},
      "away": {"tid": int, "tot": float, "points": int, ...}}
  "cal" e' il campo booleano ESPLICITO "giornata calcolata" fornito
  dall'API (non serve dedurlo dal testo). "tot" e' il punteggio fantasy
  della squadra in quella giornata.

============================================================================
DA COMPLETARE
============================================================================
Non e' stato ancora possibile osservare una risposta 200 (non da cache,
vedi README) per:
  - GET /onboarding/v1/league/competition/calendar/{competitionId}
    (calendario/accoppiamenti per ogni giornata: necessario per sapere
    CHI ha affrontato la squadra configurata in una data giornata, dato
    che l'endpoint del risultato richiede l'ID di ENTRAMBE le squadre)
  - GET /onboarding/v1/league/competition/teams?...&competitionId=...
    (classifica: posizione e punti in classifica)

Finche' questi due endpoint non sono verificati, `get_results` e
`get_team_status` restituiscono solo i dati che si possono ottenere senza
di essi (per `get_team_status`: nessuno, se non si conosce l'avversario).

IMPORTANTE - rilevazione "giornata calcolata" TEMPORANEAMENTE DISABILITATA:
il calcolo di una giornata su Leghe Fantacalcio e' un'azione MANUALE
dell'admin di lega, scollegata dal momento in cui si apre l'inserimento
formazioni per il turno successivo (segnalato in review, vedi PR #1). Non
si puo' quindi dedurre in modo affidabile "la giornata N-1 e' stata
calcolata" dal solo fatto che l'inserimento formazioni per la giornata N
sia aperto (teamLineupDto.mday == N): l'admin potrebbe non aver ancora
calcolato N-1. Finche' non e' disponibile il flag esplicito `cal`
dell'endpoint di dettaglio partita (che richiede il calendario per sapere
l'ID avversario, vedi sopra), `parse_matchday_status` ritorna sempre
`calculated=False` per evitare falsi positivi (notifica inviata PRIMA del
calcolo reale, poi mai piu' inviata perche' gia' marcata "notificata").
I promemoria deadline formazione (`next_deadline_at`/`next_matchday`) non
sono affetti da questo problema e restano pienamente funzionanti.
============================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.fantacalcio.models import MatchResult, MatchdayStatus, TeamStatus

logger = logging.getLogger(__name__)


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        logger.warning("Impossibile interpretare la data/ora ISO: %r", text)
        return None


def parse_matchday_status(
    league_id: str,
    status_json: dict,
    lineup_json: dict,
) -> MatchdayStatus:
    """Combina /league/status e /teamLineup/visualizza per ottenere la
    giornata-lega corrente e la mappatura verso la giornata di Serie A.

    status_json: corpo di GET /onboarding/v1/league/status
    lineup_json: corpo di GET /gaming/v1/teamLineup/visualizza/{div}/{compId}
    """
    next_serie_a_mday = status_json.get("mday")
    deadline = _parse_iso(status_json.get("mstr"))

    dto = lineup_json.get("teamLineupDto", {})
    next_round = dto.get("mday")
    lineup_serie_a_mday = dto.get("cmday")

    if next_round is None:
        raise ValueError(
            f"Impossibile determinare la giornata-lega corrente per {league_id}: "
            "campo 'mday' mancante in teamLineupDto. Verificare lo schema "
            "dell'endpoint teamLineup/visualizza."
        )

    if (
        next_serie_a_mday is not None
        and lineup_serie_a_mday is not None
        and next_serie_a_mday != lineup_serie_a_mday
    ):
        logger.warning(
            "Lega %s: la giornata di Serie A da /league/status (%s) non "
            "corrisponde a quella da /teamLineup/visualizza (%s); uso "
            "comunque il round da teamLineup/visualizza.",
            league_id,
            next_serie_a_mday,
            lineup_serie_a_mday,
        )

    last_calculated_round = next_round - 1

    return MatchdayStatus(
        league_id=league_id,
        matchday=last_calculated_round,
        # calculated e' sempre False per ora: vedi "IMPORTANTE" nel
        # docstring del modulo. Il campo esplicito "cal" dell'endpoint di
        # dettaglio partita richiede l'ID avversario (endpoint calendario,
        # non ancora integrato), quindi non possiamo confermare in modo
        # affidabile che last_calculated_round sia stata davvero calcolata.
        calculated=False,
        calculated_at=None,
        next_deadline_at=deadline,
        next_matchday=next_round,
    )


def parse_team_id(teams_json: dict, team_name: str) -> int | None:
    """Trova l'ID squadra a partire dal nome, nella risposta di
    GET /onboarding/v1/league/teams?page=1&division={division}.
    """
    for team in teams_json.get("data", []):
        if str(team.get("n", "")).strip().casefold() == team_name.strip().casefold():
            return team.get("id")
    logger.warning(
        "Squadra %r non trovata tra le squadre della lega. Verificare che "
        "team_name in config/leagues.yaml corrisponda esattamente al nome "
        "visualizzato sul sito.",
        team_name,
    )
    return None


def parse_match_detail(match_json: dict, team_id: int, team_name: str) -> tuple[TeamStatus, MatchResult] | None:
    """Estrae TeamStatus/MatchResult da GET
    /gaming/v1/teamLineup/{competitionId}/{round}/{serieAMday}/{teamA}/{teamB}

    Ritorna None se la giornata non risulta ancora calcolata (campo "cal").
    """
    if not match_json.get("cal", False):
        return None

    home = match_json.get("home", {})
    away = match_json.get("away", {})

    if home.get("tid") == team_id:
        mine, opponent = home, away
    elif away.get("tid") == team_id:
        mine, opponent = away, home
    else:
        logger.warning(
            "L'ID squadra %s non compare ne' in home ne' in away nella "
            "risposta del dettaglio partita.",
            team_id,
        )
        return None

    team_status = TeamStatus(
        team_name=team_name,
        score=mine.get("tot"),
        opponent_score=opponent.get("tot"),
    )
    result = MatchResult(
        home_team=team_name if mine is home else "",
        away_team=team_name if mine is away else "",
        home_score=home.get("tot"),
        away_score=away.get("tot"),
    )
    return team_status, result
