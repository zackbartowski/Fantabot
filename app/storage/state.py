"""Stato persistente (SQLite) per idempotenza delle notifiche.

Usa SQLite per evitare problemi di corruzione/concorrenza (vedi spec) e
per sopravvivere ai riavvii del bot.
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id TEXT NOT NULL,
    matchday INTEGER NOT NULL,
    calculated_at TEXT,
    notified_at TEXT NOT NULL,
    UNIQUE(league_id, matchday)
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    league_id TEXT NOT NULL,
    matchday INTEGER NOT NULL,
    offset_hours INTEGER NOT NULL,
    sent_at TEXT NOT NULL,
    UNIQUE(league_id, matchday, offset_hours)
);

CREATE TABLE IF NOT EXISTS league_health (
    league_id TEXT PRIMARY KEY,
    last_check_at TEXT,
    last_error TEXT,
    last_calculated_matchday INTEGER
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    """Wrapper thread-safe minimale attorno a SQLite.

    Una connessione per thread (check_same_thread=False + lock) e'
    sufficiente per il volume di scritture di questo bot (poche al minuto).
    """

    def __init__(self, database_path: str):
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(database_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _cursor(self):
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            finally:
                cur.close()

    # --- Notifiche giornata calcolata ------------------------------------

    def was_notified(self, league_id: str, matchday: int) -> bool:
        with self._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM notifications WHERE league_id = ? AND matchday = ?",
                (league_id, matchday),
            )
            return cur.fetchone() is not None

    def mark_notified(
        self, league_id: str, matchday: int, calculated_at: datetime | None
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO notifications (league_id, matchday, calculated_at, notified_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(league_id, matchday) DO NOTHING
                """,
                (
                    league_id,
                    matchday,
                    calculated_at.isoformat() if calculated_at else None,
                    _now_iso(),
                ),
            )

    def last_notified_matchday(self, league_id: str) -> int | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT MAX(matchday) AS m FROM notifications WHERE league_id = ?",
                (league_id,),
            )
            row = cur.fetchone()
            return row["m"] if row and row["m"] is not None else None

    # --- Reminder deadline formazione -------------------------------------

    def was_reminder_sent(self, league_id: str, matchday: int, offset_hours: int) -> bool:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM reminders
                WHERE league_id = ? AND matchday = ? AND offset_hours = ?
                """,
                (league_id, matchday, offset_hours),
            )
            return cur.fetchone() is not None

    def mark_reminder_sent(self, league_id: str, matchday: int, offset_hours: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO reminders (league_id, matchday, offset_hours, sent_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(league_id, matchday, offset_hours) DO NOTHING
                """,
                (league_id, matchday, offset_hours, _now_iso()),
            )

    # --- Health check -------------------------------------------------

    def record_check(
        self,
        league_id: str,
        last_calculated_matchday: int | None,
        error: str | None = None,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO league_health (league_id, last_check_at, last_error, last_calculated_matchday)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(league_id) DO UPDATE SET
                    last_check_at = excluded.last_check_at,
                    last_error = excluded.last_error,
                    last_calculated_matchday = COALESCE(
                        excluded.last_calculated_matchday, league_health.last_calculated_matchday
                    )
                """,
                (league_id, _now_iso(), error, last_calculated_matchday),
            )

    def get_health(self, league_id: str) -> dict | None:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM league_health WHERE league_id = ?", (league_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_all_health(self) -> list[dict]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM league_health")
            return [dict(row) for row in cur.fetchall()]
