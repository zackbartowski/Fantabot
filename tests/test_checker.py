from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.fantacalcio.models import LeagueConfig, MatchdayStatus, TeamStatus
from app.monitoring.checker import MatchdayChecker
from app.storage.state import Storage
from app.whatsapp.client import SendResult


@pytest.fixture
def league() -> LeagueConfig:
    return LeagueConfig(
        id="mantra-cormolittoriano",
        name="Mantra Cormolittoriano",
        url="https://leghe.fantacalcio.it/mantra-cormolittoriano/",
        season="2024-25",
        team_name="I Fenomeni",
        session_cookie="PHPSESSID=fake",
        recipients=["393331234567"],
    )


@pytest.fixture
def storage(tmp_path) -> Storage:
    s = Storage(str(tmp_path / "test.sqlite"))
    yield s
    s.close()


def _make_fake_client(status: MatchdayStatus, team_status: TeamStatus | None = None):
    fake_client = MagicMock()
    fake_client.get_matchday_status.return_value = status
    fake_client.get_team_status.return_value = team_status or TeamStatus(team_name="I Fenomeni")
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    return fake_client


def test_new_matchday_triggers_notification(league, storage):
    status = MatchdayStatus(
        league_id=league.id, matchday=5, calculated=True, calculated_at=datetime.now()
    )
    fake_client = _make_fake_client(status)
    fake_whatsapp = MagicMock()
    fake_whatsapp.send_text_to_all.return_value = [
        SendResult(recipient="393331234567", success=True)
    ]

    checker = MatchdayChecker(fake_whatsapp, storage)
    with patch("app.monitoring.checker.FantacalcioClient", return_value=fake_client):
        checker.check(league)

    fake_whatsapp.send_text_to_all.assert_called_once()
    assert storage.was_notified(league.id, 5) is True


def test_idempotent_no_duplicate_notification(league, storage):
    storage.mark_notified(league.id, 4, calculated_at=None)
    status = MatchdayStatus(league_id=league.id, matchday=4, calculated=True)
    fake_client = _make_fake_client(status)
    fake_whatsapp = MagicMock()

    checker = MatchdayChecker(fake_whatsapp, storage)
    with patch("app.monitoring.checker.FantacalcioClient", return_value=fake_client):
        checker.check(league)

    fake_whatsapp.send_text_to_all.assert_not_called()


def test_whatsapp_failure_does_not_mark_notified(league, storage):
    status = MatchdayStatus(league_id=league.id, matchday=6, calculated=True)
    fake_client = _make_fake_client(status)
    fake_whatsapp = MagicMock()
    fake_whatsapp.send_text_to_all.return_value = [
        SendResult(recipient="393331234567", success=False, error="http_500:boom")
    ]

    checker = MatchdayChecker(fake_whatsapp, storage)
    with patch("app.monitoring.checker.FantacalcioClient", return_value=fake_client):
        checker.check(league)

    assert storage.was_notified(league.id, 6) is False


def test_not_calculated_sends_nothing(league, storage):
    status = MatchdayStatus(league_id=league.id, matchday=7, calculated=False)
    fake_client = _make_fake_client(status)
    fake_whatsapp = MagicMock()

    checker = MatchdayChecker(fake_whatsapp, storage)
    with patch("app.monitoring.checker.FantacalcioClient", return_value=fake_client):
        checker.check(league)

    fake_whatsapp.send_text_to_all.assert_not_called()
    assert storage.was_notified(league.id, 7) is False


def test_restart_recovers_state_from_sqlite(league, tmp_path):
    db_path = str(tmp_path / "restart.sqlite")

    storage1 = Storage(db_path)
    storage1.mark_notified(league.id, 4, calculated_at=None)
    storage1.close()

    # Simula un riavvio: nuova istanza di Storage sullo stesso file.
    storage2 = Storage(db_path)
    status = MatchdayStatus(league_id=league.id, matchday=4, calculated=True)
    fake_client = _make_fake_client(status)
    fake_whatsapp = MagicMock()

    checker = MatchdayChecker(fake_whatsapp, storage2)
    with patch("app.monitoring.checker.FantacalcioClient", return_value=fake_client):
        checker.check(league)

    fake_whatsapp.send_text_to_all.assert_not_called()
    storage2.close()
