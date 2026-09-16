"""Client per l'API di Leghe Fantacalcio (apileague.fantacalcio.it).

Isola completamente il resto dell'app dai dettagli di trasporto e dal
formato JSON dell'API. Nessun altro modulo deve importare `requests` o
conoscere gli endpoint.

Vedi app/fantacalcio/parser.py per la provenienza (verificata via HAR) di
ogni campo usato qui.
"""
from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.fantacalcio import parser
from app.fantacalcio.models import LeagueConfig, MatchResult, MatchdayStatus, TeamStatus

logger = logging.getLogger(__name__)

API_BASE_URL = "https://apileague.fantacalcio.it"
USER_AGENT = "FantacalcioWhatsAppBot/1.0"
DEFAULT_TIMEOUT_SECONDS = 15


class FantacalcioClientError(Exception):
    """Errore recuperabile nel comunicare con l'API di Leghe Fantacalcio."""


class FantacalcioAuthError(FantacalcioClientError):
    """L'api_key sembra mancante, scaduta o non valida."""


def _build_session(league: LeagueConfig) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "app_key": league.api_key,
            "Origin": "https://leghe.fantacalcio.it",
            "Referer": "https://leghe.fantacalcio.it/",
        }
    )

    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class FantacalcioClient:
    def __init__(self, league: LeagueConfig, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.league = league
        self.timeout = timeout
        self._session = _build_session(league)

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "FantacalcioClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _get(self, path: str) -> dict:
        url = f"{API_BASE_URL}{path}"
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.Timeout as exc:
            raise FantacalcioClientError(f"Timeout su {url}") from exc
        except requests.RequestException as exc:
            raise FantacalcioClientError(f"Errore di rete su {url}: {exc}") from exc

        if response.status_code in (401, 403):
            raise FantacalcioAuthError(
                f"Accesso negato ({response.status_code}) su {url}: "
                "l'api_key potrebbe essere scaduta o non valida."
            )
        if response.status_code >= 400:
            raise FantacalcioClientError(
                f"Risposta HTTP inattesa {response.status_code} da {url}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise FantacalcioClientError(f"Risposta non-JSON da {url}") from exc

    def get_matchday_status(self) -> MatchdayStatus:
        status_json = self._get("/onboarding/v1/league/status")
        lineup_json = self._get(
            f"/gaming/v1/teamLineup/visualizza/{self.league.division}/{self.league.competition_id}"
        )
        return parser.parse_matchday_status(self.league.id, status_json, lineup_json)

    def get_team_id(self, team_name: str) -> int | None:
        teams_json = self._get(
            f"/onboarding/v1/league/teams?page=1&division={self.league.division}"
        )
        return parser.parse_team_id(teams_json, team_name)

    def get_results(self, matchday: int) -> list[MatchResult]:
        # Richiede la lista degli accoppiamenti (calendario) per sapere
        # contro chi ha giocato ogni squadra nella giornata `matchday`.
        # Endpoint non ancora verificato: vedi TODO in parser.py.
        logger.warning(
            "get_results non ancora implementato: manca la verifica "
            "dell'endpoint calendario. Nessun risultato restituito."
        )
        return []

    def get_team_status(self, matchday: int, team_name: str) -> TeamStatus:
        # Come get_results: senza il calendario non conosciamo l'ID
        # dell'avversario, necessario per chiamare l'endpoint di dettaglio
        # partita (/gaming/v1/teamLineup/{compId}/{round}/{serieAMday}/{a}/{b}).
        # Ritorniamo comunque un TeamStatus minimale (solo nome) cosi' il
        # resto del bot continua a funzionare; il messaggio WhatsApp
        # ometterà punteggio/classifica finche' non implementato.
        logger.warning(
            "get_team_status non ancora completo: manca la verifica "
            "dell'endpoint calendario/classifica. Nessun punteggio incluso "
            "nella notifica per la giornata %s.",
            matchday,
        )
        return TeamStatus(team_name=team_name)
