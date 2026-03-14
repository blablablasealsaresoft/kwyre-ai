"""
MarchMind — Tournament Prediction Engine

Matchup simulation, upset probability, bracket generation, and
historical tendency analysis for March Madness prediction.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .brackets import (
    Team,
    get_team,
    get_teams_by_seed,
    TEAMS,
    REGIONS,
    HISTORICAL_UPSET_RATES,
    get_region_bracket,
)


@dataclass
class MatchupResult:
    team_a: str
    team_b: str
    win_prob_a: float
    win_prob_b: float
    predicted_winner: str
    upset: bool
    margin: float
    key_factors: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class BracketPick:
    round_name: str
    matchup: str
    winner: str
    seed: int
    confidence: float
    upset: bool


def matchup_win_probability(team_a: Team, team_b: Team) -> float:
    """KenPom-style win probability based on adjusted efficiency margin."""
    eff_diff = team_a.adj_efficiency - team_b.adj_efficiency
    avg_tempo = (team_a.adj_tempo + team_b.adj_tempo) / 2.0
    tempo_factor = avg_tempo / 67.5

    off_edge = (team_a.adj_offense - team_b.adj_defense) - (team_b.adj_offense - team_a.adj_defense)
    combined = (eff_diff * 0.6 + off_edge * 0.4) * tempo_factor

    home_court = 0.0  # neutral site

    log_odds = (combined + home_court) / 10.0
    prob = 1.0 / (1.0 + math.exp(-log_odds))
    return round(max(0.02, min(0.98, prob)), 4)


def predict_matchup(team_a_name: str, team_b_name: str) -> MatchupResult | None:
    a = get_team(team_a_name)
    b = get_team(team_b_name)
    if not a or not b:
        return None

    prob_a = matchup_win_probability(a, b)
    prob_b = 1.0 - prob_a

    higher_seed = a if a.seed <= b.seed else b
    lower_seed = b if a.seed <= b.seed else a
    predicted = a.name if prob_a >= prob_b else b.name
    upset = (predicted == lower_seed.name) and (lower_seed.seed - higher_seed.seed >= 3)

    eff_diff = abs(a.adj_efficiency - b.adj_efficiency)
    margin = round(eff_diff * 0.15 * ((a.adj_tempo + b.adj_tempo) / 2.0 / 67.5), 1)

    factors = []
    if a.adj_offense - b.adj_offense > 5:
        factors.append(f"{a.name} offensive edge (+{a.adj_offense - b.adj_offense:.1f} AdjO)")
    elif b.adj_offense - a.adj_offense > 5:
        factors.append(f"{b.name} offensive edge (+{b.adj_offense - a.adj_offense:.1f} AdjO)")

    if a.adj_defense < b.adj_defense - 3:
        factors.append(f"{a.name} defensive edge ({a.adj_defense:.1f} vs {b.adj_defense:.1f} AdjD)")
    elif b.adj_defense < a.adj_defense - 3:
        factors.append(f"{b.name} defensive edge ({b.adj_defense:.1f} vs {a.adj_defense:.1f} AdjD)")

    tempo_diff = abs(a.adj_tempo - b.adj_tempo)
    if tempo_diff > 5:
        fast = a if a.adj_tempo > b.adj_tempo else b
        slow = b if a.adj_tempo > b.adj_tempo else a
        factors.append(f"Tempo clash: {fast.name} ({fast.adj_tempo:.0f}) vs {slow.name} ({slow.adj_tempo:.0f})")

    if a.tournament_wins_5yr > b.tournament_wins_5yr + 3:
        factors.append(f"{a.name} tournament experience ({a.tournament_wins_5yr} wins in 5yr)")
    elif b.tournament_wins_5yr > a.tournament_wins_5yr + 3:
        factors.append(f"{b.name} tournament experience ({b.tournament_wins_5yr} wins in 5yr)")

    seed_pair = tuple(sorted([a.seed, b.seed]))
    hist_rate = HISTORICAL_UPSET_RATES.get(seed_pair)
    if hist_rate and hist_rate > 0.25:
        factors.append(f"Historical upset rate for {seed_pair[0]} vs {seed_pair[1]}: {hist_rate:.0%}")

    if a.sos > b.sos + 3:
        factors.append(f"{a.name} tougher schedule (SOS {a.sos:.1f} vs {b.sos:.1f})")
    elif b.sos > a.sos + 3:
        factors.append(f"{b.name} tougher schedule (SOS {b.sos:.1f} vs {a.sos:.1f})")

    confidence = min(0.95, abs(prob_a - 0.5) * 2 + 0.3)

    return MatchupResult(
        team_a=a.name, team_b=b.name,
        win_prob_a=prob_a, win_prob_b=prob_b,
        predicted_winner=predicted, upset=upset,
        margin=margin, key_factors=factors,
        confidence=round(confidence, 3),
    )


def upset_radar(top_n: int = 10) -> list[dict]:
    """Find the most likely first-round upsets across all regions."""
    upsets = []
    for region in REGIONS:
        bracket = get_region_bracket(region)
        if len(bracket) < 16:
            continue
        matchups = [(bracket[i], bracket[15 - i]) for i in range(8)]
        for high, low in matchups:
            if high.seed >= low.seed:
                continue
            prob_low = 1.0 - matchup_win_probability(high, low)
            if prob_low > 0.15:
                upsets.append({
                    "region": region,
                    "favored": {"name": high.name, "seed": high.seed},
                    "underdog": {"name": low.name, "seed": low.seed},
                    "upset_probability": round(prob_low, 3),
                    "historical_rate": HISTORICAL_UPSET_RATES.get(
                        tuple(sorted([high.seed, low.seed])), None
                    ),
                })
    upsets.sort(key=lambda x: x["upset_probability"], reverse=True)
    return upsets[:top_n]


def simulate_bracket(region: str, runs: int = 10000) -> list[dict]:
    """Monte Carlo bracket simulation for a region. Returns champion probabilities."""
    bracket = get_region_bracket(region)
    if len(bracket) < 8:
        return []

    seeds = [(bracket[i], bracket[min(15 - i, len(bracket) - 1)]) for i in range(min(8, len(bracket) // 2))]
    champ_counts: dict[str, int] = {}

    for _ in range(runs):
        round_teams = []
        for high, low in seeds:
            prob = matchup_win_probability(high, low)
            winner = high if random.random() < prob else low
            round_teams.append(winner)

        while len(round_teams) > 1:
            next_round = []
            for i in range(0, len(round_teams) - 1, 2):
                prob = matchup_win_probability(round_teams[i], round_teams[i + 1])
                winner = round_teams[i] if random.random() < prob else round_teams[i + 1]
                next_round.append(winner)
            if len(round_teams) % 2 == 1:
                next_round.append(round_teams[-1])
            round_teams = next_round

        if round_teams:
            champ = round_teams[0].name
            champ_counts[champ] = champ_counts.get(champ, 0) + 1

    results = [
        {"team": name, "seed": next((t.seed for t in bracket if t.name == name), 0),
         "probability": round(count / runs, 4), "simulations": count}
        for name, count in sorted(champ_counts.items(), key=lambda x: -x[1])
    ]
    return results


def conference_strength() -> list[dict]:
    """Rank conferences by average adjusted efficiency of tournament teams."""
    conf_teams: dict[str, list[Team]] = {}
    for t in TEAMS:
        conf_teams.setdefault(t.conference, []).append(t)

    results = []
    for conf, teams in conf_teams.items():
        avg_eff = sum(t.adj_efficiency for t in teams) / len(teams)
        avg_seed = sum(t.seed for t in teams) / len(teams)
        results.append({
            "conference": conf,
            "teams_in_tournament": len(teams),
            "avg_efficiency": round(avg_eff, 1),
            "avg_seed": round(avg_seed, 1),
            "best_team": max(teams, key=lambda t: t.adj_efficiency).name,
        })
    results.sort(key=lambda x: -x["avg_efficiency"])
    return results
