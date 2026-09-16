from __future__ import annotations

from datetime import datetime

from app.fantacalcio import parser
from conftest import read_json_fixture


def test_parse_matchday_status_calculated():
    status_json = read_json_fixture("league_status.json")
    lineup_json = read_json_fixture("team_lineup_visualizza.json")

    status = parser.parse_matchday_status("mantra-cormolittoriano", status_json, lineup_json)

    # teamLineupDto.mday=2 (giornata-lega prossima) -> ultima calcolata = 1
    assert status.matchday == 1
    assert status.calculated is True
    assert status.next_matchday == 2
    assert status.next_deadline_at == datetime(2026, 9, 18, 18, 45, 0)


def test_parse_matchday_status_no_previous_round():
    status_json = {"mday": 1, "mstr": "2026-08-20T18:30:00"}
    lineup_json = {"teamLineupDto": {"mday": 1, "cmday": 1}}

    status = parser.parse_matchday_status("lega-x", status_json, lineup_json)

    assert status.matchday == 0
    assert status.calculated is False


def test_parse_team_id_found():
    teams_json = read_json_fixture("teams.json")
    assert parser.parse_team_id(teams_json, "Hello Spence") == 16130306


def test_parse_team_id_case_insensitive():
    teams_json = read_json_fixture("teams.json")
    assert parser.parse_team_id(teams_json, "hello spence") == 16130306


def test_parse_team_id_not_found():
    teams_json = read_json_fixture("teams.json")
    assert parser.parse_team_id(teams_json, "Squadra Inesistente") is None


def test_parse_match_detail_calculated():
    match_json = read_json_fixture("match_detail_calculated.json")

    result = parser.parse_match_detail(match_json, team_id=16130306, team_name="Hello Spence")

    assert result is not None
    team_status, match_result = result
    assert team_status.score == 87.5
    assert team_status.opponent_score == 63
    assert match_result.away_score == 87.5
    assert match_result.home_score == 63


def test_parse_match_detail_not_calculated_returns_none():
    match_json = read_json_fixture("match_detail_not_calculated.json")

    result = parser.parse_match_detail(match_json, team_id=16130306, team_name="Hello Spence")

    assert result is None
