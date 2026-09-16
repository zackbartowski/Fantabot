from __future__ import annotations

from app.storage.state import Storage


def test_notification_idempotent_unique_constraint(tmp_path):
    storage = Storage(str(tmp_path / "s.sqlite"))
    storage.mark_notified("lega1", 4, calculated_at=None)
    storage.mark_notified("lega1", 4, calculated_at=None)  # non deve sollevare errori

    assert storage.was_notified("lega1", 4) is True
    assert storage.was_notified("lega1", 5) is False
    storage.close()


def test_reminder_tracking(tmp_path):
    storage = Storage(str(tmp_path / "s.sqlite"))
    assert storage.was_reminder_sent("lega1", 5, 24) is False

    storage.mark_reminder_sent("lega1", 5, 24)
    assert storage.was_reminder_sent("lega1", 5, 24) is True
    assert storage.was_reminder_sent("lega1", 5, 1) is False
    storage.close()


def test_health_recording(tmp_path):
    storage = Storage(str(tmp_path / "s.sqlite"))
    storage.record_check("lega1", 4)
    health = storage.get_health("lega1")

    assert health["last_calculated_matchday"] == 4
    assert health["last_error"] is None
    storage.close()
