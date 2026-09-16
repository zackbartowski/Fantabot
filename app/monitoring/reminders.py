"""Promemoria per l'inserimento della formazione (24h / 1h prima del turno).

Richiede che FantacalcioClient sia in grado di fornire la prossima
deadline di chiusura formazioni (MatchdayStatus.next_deadline_at /
next_matchday). Se la lega non espone questo dato in modo strutturato,
i promemoria vengono semplicemente saltati (loggando un warning) senza
bloccare il resto del bot: la notifica di giornata calcolata resta
comunque funzionante.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.fantacalcio.client import FantacalcioClient, FantacalcioClientError
from app.fantacalcio.models import LeagueConfig, MatchdayStatus
from app.notifications.formatter import build_deadline_reminder_message
from app.storage.state import Storage
from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)


def _as_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class DeadlineReminderChecker:
    def __init__(self, whatsapp: WhatsAppClient, storage: Storage):
        self._whatsapp = whatsapp
        self._storage = storage

    def check(self, league: LeagueConfig, status: MatchdayStatus | None = None) -> None:
        try:
            if status is None:
                with FantacalcioClient(league) as client:
                    status = client.get_matchday_status()
        except FantacalcioClientError as exc:
            logger.error(
                "Lega %s: impossibile recuperare la deadline formazione: %s",
                league.id,
                exc,
            )
            return

        if status.next_deadline_at is None or status.next_matchday is None:
            logger.debug(
                "Lega %s: nessuna deadline formazione disponibile, promemoria saltati.",
                league.id,
            )
            return

        deadline = _as_aware_utc(status.next_deadline_at)
        now = datetime.now(timezone.utc)
        if now >= deadline:
            return

        matchday = status.next_matchday
        for offset_hours in sorted(league.reminder_offsets_hours, reverse=True):
            trigger_at = deadline.timestamp() - offset_hours * 3600
            if now.timestamp() < trigger_at:
                continue
            if self._storage.was_reminder_sent(league.id, matchday, offset_hours):
                continue

            message = build_deadline_reminder_message(league, matchday, offset_hours)
            logger.info(
                "Lega %s: invio promemoria formazione (%sh) per giornata %s...",
                league.id,
                offset_hours,
                matchday,
            )
            results = self._whatsapp.send_text_to_all(league.recipients, message)
            if any(not r.success for r in results):
                logger.error(
                    "Lega %s: invio promemoria (%sh) fallito per almeno un "
                    "destinatario, ritento al prossimo ciclo.",
                    league.id,
                    offset_hours,
                )
                continue

            self._storage.mark_reminder_sent(league.id, matchday, offset_hours)
            logger.info(
                "Lega %s: promemoria (%sh) giornata %s inviato", league.id, offset_hours, matchday
            )
