"""Modelli normalizzati per i dati di Leghe Fantacalcio.

Questi modelli sono l'unico contratto che il resto dell'applicazione
(monitoring, notifications, whatsapp) conosce. Nessun altro modulo deve
sapere come i dati sono stati ottenuti (HTML scraping, API, ecc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class LeagueConfig:
    """Configurazione di una singola lega, caricata da config/leagues.yaml.

    api_key e' il valore dell'header `app_key` usato dall'app ufficiale di
    Leghe Fantacalcio per chiamare apileague.fantacalcio.it (vedi
    app/fantacalcio/client.py per come viene estratto/usato).
    competition_id e division identificano la competizione all'interno
    della lega (visibili nell'URL quando si apre la Classifica sul sito,
    es. .../view/competition/706778/standings -> competition_id=706778).
    """

    id: str
    name: str
    url: str
    season: str
    team_name: str
    api_key: str
    competition_id: int
    recipients: list[str]
    division: str = "A"
    poll_interval_seconds: int = 300
    reminder_offsets_hours: list[int] = field(default_factory=lambda: [24, 1])


@dataclass
class MatchdayStatus:
    """Stato dell'ultima giornata nota per una lega."""

    league_id: str
    matchday: int
    calculated: bool
    calculated_at: datetime | None = None
    # Orario di deadline per l'inserimento formazioni della PROSSIMA
    # giornata non ancora giocata/calcolata (se disponibile).
    next_deadline_at: datetime | None = None
    next_matchday: int | None = None


@dataclass
class MatchResult:
    home_team: str
    away_team: str
    home_score: float | None
    away_score: float | None


@dataclass
class TeamStatus:
    team_name: str
    score: float | None = None
    league_position: int | None = None
    league_points: float | None = None
    opponent_name: str | None = None
    opponent_score: float | None = None
