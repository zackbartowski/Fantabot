"""Entrypoint del bot: avvia lo scheduler di polling e l'health check HTTP."""
from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import ConfigError, GlobalConfig, load_config
from app.monitoring.checker import MatchdayChecker
from app.monitoring.reminders import DeadlineReminderChecker
from app.notifications.formatter import build_deadline_reminder_message
from app.storage.state import Storage
from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger("fantacalcio_bot")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _make_health_handler(storage: Storage):
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nome imposto da BaseHTTPRequestHandler)
            if self.path != "/health":
                self.send_response(404)
                self.end_headers()
                return

            leagues_health = storage.get_all_health()
            body = json.dumps(
                {
                    "status": "ok",
                    "leagues": leagues_health,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            logger.debug("health check: " + format, *args)

    return HealthHandler


def _start_health_server(port: int, storage: Storage) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_health_handler(storage))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check disponibile su http://0.0.0.0:%d/health", port)
    return server


def run(config: GlobalConfig) -> None:
    storage = Storage(config.database_path)
    whatsapp = WhatsAppClient(
        access_token=config.whatsapp_access_token,
        phone_number_id=config.whatsapp_phone_number_id,
        api_version=config.whatsapp_api_version,
        dry_run=config.dry_run,
    )
    matchday_checker = MatchdayChecker(whatsapp, storage)
    reminder_checker = DeadlineReminderChecker(whatsapp, storage)

    def run_league_cycle(league):
        matchday_checker.check(league)
        reminder_checker.check(league)

    health_server = _start_health_server(config.health_check_port, storage)

    scheduler = BackgroundScheduler(timezone="UTC")
    for league in config.leagues:
        # next_run_time esplicito: senza, IntervalTrigger attende un
        # intero poll_interval_seconds prima del primo run.
        scheduler.add_job(
            run_league_cycle,
            "interval",
            seconds=league.poll_interval_seconds,
            args=[league],
            id=f"league-{league.id}",
            next_run_time=datetime.now(timezone.utc),
            max_instances=1,
            coalesce=True,
        )

    logger.info("Bot avviato (%d leghe configurate, dry_run=%s)", len(config.leagues), config.dry_run)
    scheduler.start()

    stop_event = threading.Event()

    def _handle_shutdown(signum, frame):
        logger.info("Segnale di arresto ricevuto, spegnimento in corso...")
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    try:
        stop_event.wait()
    finally:
        scheduler.shutdown(wait=False)
        health_server.shutdown()
        storage.close()
        logger.info("Bot arrestato.")


def send_test_notification(config: GlobalConfig, league_id: str | None) -> None:
    whatsapp = WhatsAppClient(
        access_token=config.whatsapp_access_token,
        phone_number_id=config.whatsapp_phone_number_id,
        api_version=config.whatsapp_api_version,
        dry_run=config.dry_run,
    )
    leagues = config.leagues
    if league_id:
        leagues = [l for l in config.leagues if l.id == league_id]
        if not leagues:
            print(f"Lega '{league_id}' non trovata in configurazione.", file=sys.stderr)
            sys.exit(1)

    for league in leagues:
        message = build_deadline_reminder_message(league, matchday=1, hours_before=24)
        message = (
            "🧪 Messaggio di TEST dal bot Fantacalcio WhatsApp.\n\n" + message
        )
        results = whatsapp.send_text_to_all(league.recipients, message)
        for result in results:
            status = "OK" if result.success else f"FALLITO ({result.error})"
            print(f"[{league.id}] -> {result.recipient}: {status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot WhatsApp per notifiche Leghe Fantacalcio")
    parser.add_argument(
        "--test-notification",
        nargs="?",
        const="__all__",
        default=None,
        metavar="LEAGUE_ID",
        help="Invia una notifica di prova (a tutte le leghe, o a quella indicata) ed esce.",
    )
    parser.add_argument("--env-file", default=".env", help="Percorso del file .env")
    args = parser.parse_args()

    try:
        config = load_config(args.env_file)
    except ConfigError as exc:
        print(f"Errore di configurazione: {exc}", file=sys.stderr)
        sys.exit(1)

    _configure_logging(config.log_level)

    if args.test_notification is not None:
        league_id = None if args.test_notification == "__all__" else args.test_notification
        send_test_notification(config, league_id)
        return

    run(config)


if __name__ == "__main__":
    main()
