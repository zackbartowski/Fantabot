"""Logica di rilevazione del calcolo giornata e invio notifica.

Implementa lo pseudo-codice della specifica: la giornata viene marcata
come notificata SOLO dopo un invio WhatsApp riuscito, per garantire che
un fallimento nell'invio comporti un retry al ciclo successivo e non una
notifica persa silenziosamente.
"""
from __future__ import annotations

import logging

from app.fantacalcio.client import FantacalcioClient, FantacalcioClientError
from app.fantacalcio.models import LeagueConfig
from app.notifications.formatter import build_matchday_message
from app.storage.state import Storage
from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)


class MatchdayChecker:
    def __init__(self, whatsapp: WhatsAppClient, storage: Storage):
        self._whatsapp = whatsapp
        self._storage = storage

    def check(self, league: LeagueConfig) -> None:
        logger.info("Controllo lega %s...", league.id)
        try:
            with FantacalcioClient(league) as client:
                status = client.get_matchday_status()

                if not status.calculated:
                    logger.info(
                        "Lega %s: giornata %s non ancora calcolata.",
                        league.id,
                        status.matchday,
                    )
                    self._storage.record_check(league.id, None)
                    return

                logger.info(
                    "Lega %s: ultima giornata calcolata: %s",
                    league.id,
                    status.matchday,
                )
                self._storage.record_check(league.id, status.matchday)

                if self._storage.was_notified(league.id, status.matchday):
                    logger.info(
                        "Lega %s: giornata %s gia' notificata, nessun invio.",
                        league.id,
                        status.matchday,
                    )
                    return

                logger.info(
                    "Lega %s: nuova giornata calcolata: %s", league.id, status.matchday
                )

                team_status = None
                try:
                    team_status = client.get_team_status(status.matchday, league.team_name)
                except FantacalcioClientError:
                    logger.warning(
                        "Lega %s: impossibile recuperare lo stato squadra per la "
                        "giornata %s; invio comunque una notifica minimale.",
                        league.id,
                        status.matchday,
                    )

                message = build_matchday_message(league, status, team_status)
                self._send_and_mark(league, status.matchday, status.calculated_at, message)

        except FantacalcioClientError as exc:
            logger.error(
                "Lega %s: impossibile recuperare lo stato della lega: %s", league.id, exc
            )
            self._storage.record_check(league.id, None, error=str(exc))
        except Exception:
            logger.exception("Lega %s: errore inatteso durante il controllo", league.id)
            self._storage.record_check(league.id, None, error="errore inatteso")

    def _send_and_mark(self, league: LeagueConfig, matchday: int, calculated_at, message: str) -> None:
        logger.info("Lega %s: invio notifica WhatsApp...", league.id)
        results = self._whatsapp.send_text_to_all(league.recipients, message)
        failures = [r for r in results if not r.success]

        if failures:
            logger.error(
                "Lega %s: invio WhatsApp fallito per %d/%d destinatari "
                "(giornata %s NON marcata come notificata, ritento al prossimo ciclo).",
                league.id,
                len(failures),
                len(results),
                matchday,
            )
            return

        # Marcata come notificata solo dopo che TUTTI gli invii sono
        # riusciti. Vedi README per la discussione del trade-off legato al
        # rischio di duplicazione se il salvataggio su SQLite fallisse
        # subito dopo un invio riuscito (evento estremamente raro e
        # comunque non distruttivo: nel peggiore dei casi si rimanda
        # un'unica notifica).
        self._storage.mark_notified(league.id, matchday, calculated_at)
        logger.info("Lega %s: notifica giornata %s inviata", league.id, matchday)
