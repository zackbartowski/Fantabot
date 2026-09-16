"""Client HTTP per Leghe Fantacalcio.

Isola completamente il resto dell'app dai dettagli di trasporto
(HTTP, cookie, retry) e di formato (HTML) del sito. Nessun altro modulo
deve importare `requests` o conoscere gli URL delle pagine.

Autenticazione
---------------
Leghe Fantacalcio richiede un login. Per evitare di automatizzare il
login (fragile, rischio CAPTCHA/blocchi, e comunque non verificabile in
questo ambiente perche' privo di accesso di rete al sito), il bot NON fa
login autonomamente: riusa un cookie di sessione che l'utente ottiene
autenticandosi normalmente nel proprio browser.

Vedi README, sezione "Autenticazione", per come estrarre il cookie.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.fantacalcio import parser
from app.fantacalcio.models import LeagueConfig, MatchResult, MatchdayStatus, TeamStatus

logger = logging.getLogger(__name__)

USER_AGENT = "FantacalcioWhatsAppBot/1.0 (+https://github.com/; contatto: configurabile)"

DEFAULT_TIMEOUT_SECONDS = 15

# Percorsi relativi delle pagine usate. NON VERIFICATI (vedi parser.py):
# ipotesi basata su pattern comuni di Leghe Fantacalcio, da correggere
# con l'osservazione del sito reale.
PATH_CLASSIFICA = "classifica"
PATH_RISULTATI = "risultati"


class FantacalcioClientError(Exception):
    """Errore recuperabile nel comunicare con Leghe Fantacalcio."""


class FantacalcioAuthError(FantacalcioClientError):
    """Il cookie di sessione sembra mancante, scaduto o non valido."""


def _build_session(league: LeagueConfig) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "it-IT,it;q=0.9",
        }
    )
    session.cookies.update(_parse_cookie_string(league.session_cookie))

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


def _parse_cookie_string(raw: str) -> dict[str, str]:
    """Converte 'NOME=valore; ALTRO=valore2' (formato copiato da DevTools)
    in un dict di cookie. Accetta anche un singolo valore senza nome,
    che viene mappato sul cookie generico PHPSESSID.
    """
    raw = (raw or "").strip()
    if not raw:
        return {}
    if "=" not in raw:
        return {"PHPSESSID": raw}
    cookies: dict[str, str] = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, _, value = part.partition("=")
        cookies[name.strip()] = value.strip()
    return cookies


class FantacalcioClient:
    """Recupera lo stato normalizzato di una lega da Leghe Fantacalcio."""

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

    def _get(self, relative_path: str) -> str:
        url = urljoin(self.league.url.rstrip("/") + "/", relative_path)
        try:
            response = self._session.get(url, timeout=self.timeout)
        except requests.Timeout as exc:
            raise FantacalcioClientError(f"Timeout su {url}") from exc
        except requests.RequestException as exc:
            raise FantacalcioClientError(f"Errore di rete su {url}: {exc}") from exc

        if response.status_code in (401, 403):
            raise FantacalcioAuthError(
                f"Accesso negato ({response.status_code}) su {url}: "
                "il cookie di sessione potrebbe essere scaduto o non valido."
            )
        if response.status_code >= 400:
            raise FantacalcioClientError(
                f"Risposta HTTP inattesa {response.status_code} da {url}"
            )
        return response.text

    def get_matchday_status(self) -> MatchdayStatus:
        html = self._get(PATH_CLASSIFICA)
        return parser.parse_matchday_status(html, self.league.id)

    def get_results(self, matchday: int) -> list[MatchResult]:
        html = self._get(f"{PATH_RISULTATI}?giornata={matchday}")
        return parser.parse_results(html)

    def get_team_status(self, matchday: int, team_name: str) -> TeamStatus:
        html_standings = self._get(PATH_CLASSIFICA)
        try:
            html_results = self._get(f"{PATH_RISULTATI}?giornata={matchday}")
        except FantacalcioClientError:
            logger.warning(
                "Impossibile recuperare i risultati della giornata %s per lo "
                "stato squadra; procedo solo con la classifica.",
                matchday,
            )
            html_results = None
        return parser.parse_team_status(html_standings, html_results, team_name)
