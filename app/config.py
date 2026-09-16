"""Caricamento e validazione della configurazione.

Due sorgenti:
- Variabili d'ambiente (.env): credenziali WhatsApp e impostazioni globali.
- File YAML (config/leagues.yaml): elenco delle leghe monitorate, per
  poter aggiungere/rimuovere leghe senza toccare le variabili globali e
  per assegnare destinatari/intervalli diversi a ciascuna.

La configurazione viene validata all'avvio: un errore qui blocca lo
startup con un messaggio chiaro, invece di fallire silenziosamente dopo.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

from app.fantacalcio.models import LeagueConfig

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Configurazione mancante o non valida."""


@dataclass
class GlobalConfig:
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    whatsapp_api_version: str
    database_path: str
    log_level: str
    dry_run: bool
    health_check_port: int
    leagues: list[LeagueConfig]


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _load_leagues(path: str) -> list[LeagueConfig]:
    league_file = Path(path)
    if not league_file.exists():
        raise ConfigError(
            f"File di configurazione leghe non trovato: {path}. "
            "Copia config/leagues.example.yaml in config/leagues.yaml e compilalo."
        )

    with league_file.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    raw_leagues = data.get("leagues")
    if not raw_leagues:
        raise ConfigError(f"Nessuna lega definita in {path} (chiave 'leagues' mancante o vuota).")

    leagues: list[LeagueConfig] = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(raw_leagues):
        prefix = f"leagues[{i}]"
        league_id = entry.get("id")
        if not league_id:
            raise ConfigError(f"{prefix}.id mancante.")
        if league_id in seen_ids:
            raise ConfigError(f"League id duplicato: {league_id!r}.")
        seen_ids.add(league_id)

        url = entry.get("url")
        if not url:
            raise ConfigError(f"{prefix}.url mancante per la lega {league_id!r}.")

        team_name = entry.get("team_name")
        if not team_name:
            raise ConfigError(f"{prefix}.team_name mancante per la lega {league_id!r}.")

        recipients = entry.get("recipients") or []
        if not recipients:
            raise ConfigError(
                f"{prefix}.recipients vuoto per la lega {league_id!r}: "
                "nessun destinatario WhatsApp configurato."
            )

        competition_id = entry.get("competition_id")
        if not competition_id:
            raise ConfigError(
                f"{prefix}.competition_id mancante per la lega {league_id!r}. "
                "Visibile nell'URL quando apri la Classifica sul sito "
                "(es. .../view/competition/706778/standings -> 706778)."
            )

        api_key = entry.get("api_key", "")
        api_key_env_name = entry.get("api_key_env")
        if api_key_env_name:
            api_key = os.getenv(api_key_env_name, "")
        if not api_key:
            raise ConfigError(
                f"api_key mancante per la lega {league_id!r}. "
                f"Imposta la variabile d'ambiente {api_key_env_name!r} "
                "(vedi README, sezione Autenticazione)."
                if api_key_env_name
                else f"{prefix}: specificare 'api_key' o 'api_key_env'."
            )

        leagues.append(
            LeagueConfig(
                id=league_id,
                name=entry.get("name", league_id),
                url=url,
                season=str(entry.get("season", "")),
                team_name=team_name,
                api_key=api_key,
                competition_id=int(competition_id),
                division=str(entry.get("division", "A")),
                recipients=[str(r).strip() for r in recipients],
                poll_interval_seconds=int(entry.get("poll_interval_seconds", 300)),
                reminder_offsets_hours=list(entry.get("reminder_offsets_hours", [24, 1])),
            )
        )

    return leagues


def load_config(env_file: str | None = ".env") -> GlobalConfig:
    if env_file and Path(env_file).exists():
        load_dotenv(env_file)

    dry_run = _bool_env("DRY_RUN", False)

    whatsapp_access_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    whatsapp_phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    if not dry_run and (not whatsapp_access_token or not whatsapp_phone_number_id):
        raise ConfigError(
            "WHATSAPP_ACCESS_TOKEN e WHATSAPP_PHONE_NUMBER_ID sono obbligatori "
            "(oppure imposta DRY_RUN=true per testare senza inviare messaggi reali)."
        )

    leagues_path = os.getenv("LEAGUES_CONFIG_PATH", "config/leagues.yaml")
    leagues = _load_leagues(leagues_path)

    return GlobalConfig(
        whatsapp_access_token=whatsapp_access_token,
        whatsapp_phone_number_id=whatsapp_phone_number_id,
        whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v21.0"),
        database_path=os.getenv("DATABASE_PATH", "./data/bot.sqlite"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        dry_run=dry_run,
        health_check_port=int(os.getenv("HEALTH_CHECK_PORT", "8080")),
        leagues=leagues,
    )
