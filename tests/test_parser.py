from __future__ import annotations

from datetime import datetime

from app.fantacalcio import parser
from conftest import read_fixture


def test_parse_matchday_status_calculated():
    html = read_fixture("classifica_calculated.html")
    status = parser.parse_matchday_status(html, league_id="mantra-cormolittoriano")

    assert status.matchday == 4
    assert status.calculated is True
    assert status.calculated_at == datetime(2024, 10, 1, 20, 15, 0)
    assert status.next_matchday == 5
    assert status.next_deadline_at == datetime(2024, 10, 6, 18, 30, 0)


def test_parse_matchday_status_not_calculated():
    html = read_fixture("classifica_not_calculated.html")
    status = parser.parse_matchday_status(html, league_id="mantra-cormolittoriano")

    assert status.matchday == 5
    assert status.calculated is False


def test_parse_results():
    html = read_fixture("risultati_giornata4.html")
    results = parser.parse_results(html)

    assert len(results) == 2
    assert results[0].home_team == "I Fenomeni"
    assert results[0].away_team == "Real Cormolò"
    assert results[0].home_score == 68.5
    assert results[0].away_score == 61.0


def test_parse_team_status_found_in_standings_and_results():
    standings_html = read_fixture("classifica_calculated.html")
    results_html = read_fixture("risultati_giornata4.html")

    status = parser.parse_team_status(standings_html, results_html, "I Fenomeni")

    assert status.league_position == 1
    assert status.league_points == 24
    assert status.score == 68.5
    assert status.opponent_name == "Real Cormolò"
    assert status.opponent_score == 61.0


def test_parse_team_status_not_in_standings():
    standings_html = read_fixture("classifica_calculated.html")
    status = parser.parse_team_status(standings_html, None, "Squadra Inesistente")

    assert status.league_position is None
    assert status.league_points is None


def test_parse_matchday_status_raises_when_nothing_found():
    import pytest

    with pytest.raises(ValueError):
        parser.parse_matchday_status("<html><body>pagina vuota</body></html>", "lega-x")
