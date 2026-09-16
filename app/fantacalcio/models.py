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
    """Configurazione di una singola lega, caricata da config/leagues.yaml."""

    id: str
    name: str
    url: str
    season: str
    team_name: str
    session_cookie: str
    recipients: list[str]
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
