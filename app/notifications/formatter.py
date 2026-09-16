"""Costruzione dei testi dei messaggi WhatsApp.

Non conosce nulla dell'HTML/API di Leghe Fantacalcio: lavora solo sui
modelli normalizzati (app.fantacalcio.models). I campi non disponibili
vengono omessi dal messaggio, come richiesto dalla specifica.
"""
from __future__ import annotations

from app.fantacalcio.models import LeagueConfig, MatchdayStatus, MatchResult, TeamStatus


def build_matchday_message(
    league: LeagueConfig,
    status: MatchdayStatus,
    team_status: TeamStatus | None,
) -> str:
    lines = [f"⚽ Giornata {status.matchday} calcolata! ({league.name})", ""]

    if team_status is not None and team_status.score is not None:
        lines.append(f"🏆 {team_status.team_name}: {team_status.score}")
        if team_status.opponent_name is not None:
            opp_score = (
                f": {team_status.opponent_score}"
                if team_status.opponent_score is not None
                else ""
            )
            lines.append(f"🆚 {team_status.opponent_name}{opp_score}")
        lines.append("")

        if team_status.score is not None and team_status.opponent_score is not None:
            if team_status.score > team_status.opponent_score:
                risultato = "Vittoria 🟢"
            elif team_status.score < team_status.opponent_score:
                risultato = "Sconfitta 🔴"
            else:
                risultato = "Pareggio ⚪"
            lines.append(f"📊 Risultato: {risultato}")
            lines.append("")

    if team_status is not None and team_status.league_position is not None:
        punti = (
            f" – {team_status.league_points} punti"
            if team_status.league_points is not None
            else ""
        )
        lines.append(f"🔢 Classifica: {team_status.league_position}° posto{punti}")
        lines.append("")

    lines.append("🔔 Risultati della giornata disponibili.")
    return "\n".join(lines)


def build_deadline_reminder_message(
    league: LeagueConfig, matchday: int, hours_before: int
) -> str:
    if hours_before >= 24:
        tempo = f"{hours_before // 24}g" if hours_before % 24 == 0 else f"{hours_before}h"
    else:
        tempo = f"{hours_before}h"
    return (
        f"⏰ Promemoria formazione – {league.name}\n\n"
        f"Mancano circa {tempo} alla chiusura delle formazioni per la "
        f"giornata {matchday}.\n\n"
        f"📝 Non dimenticare di inserire la formazione di {league.team_name}!"
    )
