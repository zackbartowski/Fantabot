"""Parsing dell'HTML di Leghe Fantacalcio verso i modelli normalizzati.

============================================================================
ATTENZIONE - SELETTORI NON VERIFICATI
============================================================================
Questo ambiente di sviluppo non ha accesso di rete a leghe.fantacalcio.it
(bloccato dal proxy di rete) e la lega richiede comunque un login, quindi
non e' stato possibile ispezionare l'HTML/le richieste reali della lega
durante lo sviluppo iniziale.

I selettori CSS qui sotto sono un'ipotesi ragionevole basata sulla
struttura tipica delle pagine "Classifica" e "Risultati" di Leghe
Fantacalcio, MA VANNO VERIFICATI con l'HTML reale prima di andare in
produzione.

Per validarli/correggerli:
  1. Configura FANTACALCIO_SESSION_COOKIE_<LEGA> con un cookie di sessione
     valido (vedi README, sezione "Autenticazione").
  2. Esegui `python scripts/dump_pages.py <league_id>` da una macchina che
     ha accesso a leghe.fantacalcio.it: salva le pagine HTML reali in
     tests/fixtures/.
  3. Aggiorna le costanti *_SELECTOR sotto finche' i test in
     tests/test_parser.py (eseguiti sulle fixture reali) non passano.

Il resto dell'applicazione non dipende da questi dettagli: consuma solo
i modelli normalizzati restituiti dalle funzioni pubbliche qui sotto.
============================================================================
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from app.fantacalcio.models import MatchResult, MatchdayStatus, TeamStatus

logger = logging.getLogger(__name__)

# --- Selettori CSS (DA VERIFICARE con HTML reale, vedi header sopra) ------

# Pagina "classifica"/dashboard: elemento che riporta l'ultima giornata
# calcolata, es. <div class="last-matchday" data-matchday="4" data-calculated-at="2024-10-01T20:15:00">
MATCHDAY_STATUS_SELECTOR = "[data-matchday]"
MATCHDAY_ATTR = "data-matchday"
CALCULATED_AT_ATTR = "data-calculated-at"
CALCULATED_FLAG_ATTR = "data-calculated"

# Fallback testuale se non esiste un dato strutturato: testo tipo
# "Giornata 4 calcolata" vs "Giornata 5 in corso" / "non ancora calcolata"
MATCHDAY_TEXT_PATTERN = re.compile(
    r"giornata\s*(\d+)", re.IGNORECASE
)
CALCULATED_TEXT_PATTERN = re.compile(
    r"\bcalcolat[ao]\b", re.IGNORECASE
)
NOT_CALCULATED_TEXT_PATTERN = re.compile(
    r"non\s+ancora\s+calcolat[ao]|in\s+corso|da\s+calcolare", re.IGNORECASE
)

# Prossima deadline formazioni: <div class="deadline" data-deadline="2024-10-05T18:30:00">
DEADLINE_SELECTOR = "[data-deadline]"
DEADLINE_ATTR = "data-deadline"

# Righe risultati partite: <tr class="match-row"><td class="home-team">...
MATCH_ROW_SELECTOR = "tr.match-row, tr[data-match]"
HOME_TEAM_SELECTOR = ".home-team, .team-home"
AWAY_TEAM_SELECTOR = ".away-team, .team-away"
HOME_SCORE_SELECTOR = ".home-score, .score-home"
AWAY_SCORE_SELECTOR = ".away-score, .score-away"

# Righe classifica: <tr class="standings-row" data-team="Nome"><td class="position">1</td>...
STANDINGS_ROW_SELECTOR = "tr.standings-row, tr[data-team]"
POSITION_SELECTOR = ".position"
TEAM_NAME_SELECTOR = ".team-name"
POINTS_SELECTOR = ".points"


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    text = text.strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return int(re.sub(r"[^\d-]", "", text) or "0")
    except ValueError:
        return None


def _parse_datetime(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    logger.warning("Impossibile interpretare la data/ora: %r", text)
    return None


def parse_matchday_status(html: str, league_id: str) -> MatchdayStatus:
    """Estrae lo stato dell'ultima giornata calcolata da una pagina lega.

    Preferisce dati strutturati (attributi data-*) al testo visualizzato,
    come richiesto dalla specifica. Se non trova nulla di strutturato,
    tenta un fallback testuale best-effort e lo segnala nei log.
    """
    soup = BeautifulSoup(html, "lxml")

    node = soup.select_one(MATCHDAY_STATUS_SELECTOR)
    if node is not None and node.get(MATCHDAY_ATTR):
        matchday = _parse_int(node.get(MATCHDAY_ATTR))
        calculated = node.get(CALCULATED_FLAG_ATTR, "true").lower() not in (
            "false",
            "0",
        )
        calculated_at = _parse_datetime(node.get(CALCULATED_AT_ATTR))
        if matchday is not None:
            status = MatchdayStatus(
                league_id=league_id,
                matchday=matchday,
                calculated=calculated,
                calculated_at=calculated_at,
            )
            _attach_deadline(soup, status)
            return status

    logger.warning(
        "Nessun dato strutturato trovato per lo stato giornata (lega=%s); "
        "uso fallback testuale, meno affidabile. Verificare i selettori "
        "in app/fantacalcio/parser.py con l'HTML reale.",
        league_id,
    )
    text = soup.get_text(" ", strip=True)
    match = MATCHDAY_TEXT_PATTERN.search(text)
    if not match:
        raise ValueError(
            f"Impossibile determinare la giornata dalla pagina della lega {league_id}: "
            "nessun dato strutturato ne' testo riconoscibile. Verificare i selettori."
        )
    matchday = int(match.group(1))
    calculated = bool(CALCULATED_TEXT_PATTERN.search(text)) and not bool(
        NOT_CALCULATED_TEXT_PATTERN.search(text)
    )
    status = MatchdayStatus(
        league_id=league_id,
        matchday=matchday,
        calculated=calculated,
        calculated_at=None,
    )
    _attach_deadline(soup, status)
    return status


def _attach_deadline(soup: BeautifulSoup, status: MatchdayStatus) -> None:
    deadline_node = soup.select_one(DEADLINE_SELECTOR)
    if deadline_node is not None:
        status.next_deadline_at = _parse_datetime(deadline_node.get(DEADLINE_ATTR))
        next_md = deadline_node.get(MATCHDAY_ATTR)
        if next_md:
            status.next_matchday = _parse_int(next_md)
        elif status.next_deadline_at is not None:
            status.next_matchday = status.matchday + 1


def parse_results(html: str) -> list[MatchResult]:
    """Estrae i risultati delle partite di una giornata."""
    soup = BeautifulSoup(html, "lxml")
    results: list[MatchResult] = []

    for row in soup.select(MATCH_ROW_SELECTOR):
        home_el = row.select_one(HOME_TEAM_SELECTOR)
        away_el = row.select_one(AWAY_TEAM_SELECTOR)
        if home_el is None or away_el is None:
            continue
        home_score_el = row.select_one(HOME_SCORE_SELECTOR)
        away_score_el = row.select_one(AWAY_SCORE_SELECTOR)
        results.append(
            MatchResult(
                home_team=home_el.get_text(strip=True),
                away_team=away_el.get_text(strip=True),
                home_score=_parse_float(
                    home_score_el.get_text(strip=True) if home_score_el else None
                ),
                away_score=_parse_float(
                    away_score_el.get_text(strip=True) if away_score_el else None
                ),
            )
        )

    if not results:
        logger.warning(
            "Nessun risultato estratto dalla pagina risultati: verificare "
            "i selettori MATCH_ROW_SELECTOR/HOME_TEAM_SELECTOR/... "
            "in app/fantacalcio/parser.py."
        )
    return results


def parse_team_status(
    html_standings: str, html_results: str | None, team_name: str
) -> TeamStatus:
    """Estrae posizione/punti in classifica ed eventuale risultato della
    squadra configurata, incrociando classifica e risultati della giornata.
    """
    soup = BeautifulSoup(html_standings, "lxml")
    status = TeamStatus(team_name=team_name)

    for row in soup.select(STANDINGS_ROW_SELECTOR):
        name_el = row.select_one(TEAM_NAME_SELECTOR)
        if name_el is None:
            continue
        if name_el.get_text(strip=True).casefold() != team_name.casefold():
            continue
        position_el = row.select_one(POSITION_SELECTOR)
        points_el = row.select_one(POINTS_SELECTOR)
        status.league_position = _parse_int(
            position_el.get_text(strip=True) if position_el else None
        )
        status.league_points = _parse_float(
            points_el.get_text(strip=True) if points_el else None
        )
        break
    else:
        logger.warning(
            "Squadra %r non trovata in classifica: verificare "
            "STANDINGS_ROW_SELECTOR/TEAM_NAME_SELECTOR o il nome squadra "
            "configurato (FANTACALCIO_TEAM_NAME).",
            team_name,
        )

    if html_results:
        for result in parse_results(html_results):
            if result.home_team.casefold() == team_name.casefold():
                status.score = result.home_score
                status.opponent_name = result.away_team
                status.opponent_score = result.away_score
                break
            if result.away_team.casefold() == team_name.casefold():
                status.score = result.away_score
                status.opponent_name = result.home_team
                status.opponent_score = result.home_score
                break

    return status
