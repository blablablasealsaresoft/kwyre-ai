"""
MarchMind — College Basketball Tournament Data

Team database with KenPom-style metrics, historical tournament performance,
conference data, and bracket seeding for March Madness simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Team:
    name: str
    seed: int
    conference: str
    record: str
    adj_efficiency: float
    adj_offense: float
    adj_defense: float
    adj_tempo: float
    sos: float
    tournament_wins_5yr: int = 0
    final_four_appearances: int = 0
    description: str = ""
    tags: list[str] = field(default_factory=list)


REGIONS = ["East", "West", "South", "Midwest"]

CONFERENCES = [
    "ACC", "Big 12", "Big East", "Big Ten", "SEC", "Pac-12", "AAC",
    "Mountain West", "WCC", "A-10", "Missouri Valley", "Colonial",
    "Ivy League", "MAAC", "Horizon", "WAC", "Sun Belt", "CUSA",
]

TEAMS: list[Team] = [
    # East Region
    Team("UConn", 1, "Big East", "31-3", 32.5, 123.1, 90.6, 68.2, 11.2, 12, 3, "Back-to-back champions, elite defense", ["powerhouse", "defense"]),
    Team("Marquette", 2, "Big East", "27-7", 26.8, 118.5, 91.7, 69.1, 9.8, 4, 1, "Guard-heavy, high-tempo offense", ["offense", "tempo"]),
    Team("Illinois", 3, "Big Ten", "26-8", 25.1, 116.2, 91.1, 70.5, 10.5, 3, 0, "Physical interior play, strong rebounding", ["big-ten", "physical"]),
    Team("Auburn", 4, "SEC", "27-7", 24.3, 117.8, 93.5, 72.1, 9.1, 5, 2, "High-scoring SEC champion", ["sec", "offense"]),
    Team("San Diego St", 5, "Mountain West", "26-7", 20.1, 109.2, 89.1, 64.8, 6.2, 3, 1, "Defensive identity, slow pace", ["defense", "mid-major"]),
    Team("BYU", 6, "Big 12", "24-9", 18.5, 112.8, 94.3, 68.9, 8.4, 2, 0, "Three-point shooting threat", ["shooting"]),
    Team("Washington St", 7, "WCC", "25-8", 17.2, 111.5, 94.3, 66.7, 5.8, 1, 0, "Transfer portal rebuild success", ["mid-major"]),
    Team("Florida Atlantic", 8, "AAC", "26-7", 16.8, 110.1, 93.3, 68.5, 4.9, 2, 1, "Final Four darling 2023", ["cinderella"]),
    Team("Northwestern", 9, "Big Ten", "22-10", 15.5, 108.9, 93.4, 65.2, 8.9, 1, 0, "Low-turnover, disciplined offense", ["big-ten"]),
    Team("Drake", 10, "Missouri Valley", "28-5", 18.9, 112.1, 93.2, 66.1, 3.5, 1, 0, "MVC champion, experienced guard play", ["mid-major"]),
    Team("Duquesne", 11, "A-10", "24-8", 14.2, 107.5, 93.3, 67.8, 3.1, 0, 0, "A-10 tournament champion", ["mid-major", "cinderella"]),
    Team("Vermont", 12, "America East", "28-5", 13.5, 106.8, 93.3, 65.9, 1.2, 1, 0, "Consistent mid-major contender", ["mid-major"]),
    Team("Samford", 13, "SoCon", "29-5", 11.8, 108.2, 96.4, 71.5, 0.8, 0, 0, "High-scoring upset threat", ["cinderella"]),
    Team("Morehead St", 14, "OVC", "26-7", 8.5, 105.1, 96.6, 69.2, -0.5, 0, 0, "OVC champion", ["auto-bid"]),
    Team("S Dakota St", 15, "Summit", "22-12", 5.2, 103.2, 98.0, 66.8, -2.1, 0, 0, "Summit League champion", ["auto-bid"]),
    Team("Stetson", 16, "ASUN", "22-11", 1.5, 100.1, 98.6, 68.5, -5.2, 0, 0, "ASUN conference champion", ["auto-bid"]),

    # West Region
    Team("Houston", 1, "Big 12", "30-4", 33.1, 119.5, 86.4, 64.5, 12.1, 8, 2, "Elite defense, Kelvin Sampson system", ["defense", "powerhouse"]),
    Team("Tennessee", 2, "SEC", "27-7", 27.5, 115.8, 88.3, 66.2, 10.8, 5, 0, "Suffocating half-court defense", ["defense", "sec"]),
    Team("Creighton", 3, "Big East", "25-8", 24.8, 117.2, 92.4, 69.8, 9.2, 4, 0, "Efficient motion offense", ["offense", "big-east"]),
    Team("Duke", 4, "ACC", "26-8", 23.9, 118.1, 94.2, 71.5, 8.5, 6, 3, "Blue blood, one-and-done talent", ["blueblood", "acc"]),
    Team("Wisconsin", 5, "Big Ten", "24-9", 21.2, 112.5, 91.3, 62.8, 9.5, 4, 1, "Swing offense, rebounding edge", ["big-ten", "defense"]),
    Team("Texas Tech", 6, "Big 12", "23-10", 19.8, 110.8, 91.0, 65.5, 9.1, 3, 1, "Defensive powerhouse under Adams", ["defense"]),
    Team("Dayton", 7, "A-10", "25-7", 18.1, 113.5, 95.4, 69.2, 4.5, 2, 0, "Anthony Grant's balanced attack", ["mid-major"]),
    Team("Nevada", 8, "Mountain West", "26-7", 17.5, 111.2, 93.7, 68.1, 5.1, 1, 0, "MWC contender, veteran roster", ["mid-major"]),
    Team("Texas A&M", 9, "SEC", "22-11", 16.2, 109.8, 93.6, 67.5, 9.2, 2, 0, "SEC depth, physical play", ["sec"]),
    Team("Colorado St", 10, "Mountain West", "25-8", 15.8, 110.5, 94.7, 66.8, 4.8, 1, 0, "MWC runner-up", ["mid-major"]),
    Team("Oregon", 11, "Big Ten", "23-10", 15.1, 111.8, 96.7, 70.2, 7.5, 2, 1, "Transition offense, athleticism", ["big-ten"]),
    Team("Grand Canyon", 12, "WAC", "27-6", 14.5, 108.5, 94.0, 67.5, 1.5, 0, 0, "WAC champion, strong guard play", ["mid-major"]),
    Team("Charleston", 13, "Colonial", "28-5", 12.2, 107.8, 95.6, 68.8, 0.2, 1, 0, "Colonial champion, upset history", ["cinderella"]),
    Team("Colgate", 14, "Patriot", "26-7", 9.1, 106.2, 97.1, 69.5, -1.8, 0, 0, "Patriot League champion", ["auto-bid"]),
    Team("Long Beach St", 15, "Big West", "21-12", 4.8, 102.5, 97.7, 67.2, -3.5, 0, 0, "Big West champion", ["auto-bid"]),
    Team("Wagner", 16, "NEC", "20-13", 0.5, 99.8, 99.3, 70.1, -6.8, 0, 0, "NEC tournament champion", ["auto-bid"]),

    # South Region
    Team("Purdue", 1, "Big Ten", "29-4", 31.8, 124.5, 92.7, 67.8, 11.5, 7, 2, "Zach Edey era, dominant post play", ["powerhouse", "big-ten"]),
    Team("North Carolina", 2, "ACC", "27-7", 28.1, 120.2, 92.1, 73.5, 9.8, 8, 4, "Blue blood, up-tempo attack", ["blueblood", "tempo"]),
    Team("Baylor", 3, "Big 12", "24-9", 23.5, 116.8, 93.3, 68.2, 9.5, 5, 1, "National champion 2021, athletic wings", ["big-12"]),
    Team("Alabama", 4, "SEC", "25-9", 22.8, 118.5, 95.7, 74.8, 8.8, 4, 1, "Fastest tempo in SEC, three-point barrage", ["tempo", "sec"]),
    Team("St. Mary's", 5, "WCC", "26-6", 21.5, 114.2, 92.7, 61.5, 5.2, 3, 0, "WCC power, Randy Bennett's system", ["defense", "mid-major"]),
    Team("Clemson", 6, "ACC", "24-9", 19.1, 112.5, 93.4, 66.8, 7.8, 2, 0, "Brad Brownell's best team", ["acc"]),
    Team("New Mexico", 7, "Mountain West", "26-7", 18.5, 113.8, 95.3, 72.1, 5.5, 1, 0, "The Pit advantage, high altitude", ["mid-major"]),
    Team("Mississippi St", 8, "SEC", "23-10", 16.9, 110.5, 93.6, 68.5, 8.5, 2, 0, "SEC tournament run", ["sec"]),

    # Midwest Region
    Team("Kansas", 1, "Big 12", "28-5", 30.5, 121.8, 91.3, 69.5, 11.8, 10, 5, "Allen Fieldhouse dominance, Bill Self", ["blueblood", "powerhouse"]),
    Team("Arizona", 2, "Pac-12", "27-7", 27.8, 119.5, 91.7, 72.5, 9.5, 5, 2, "Tommy Lloyd's motion offense", ["offense", "pac-12"]),
    Team("Gonzaga", 3, "WCC", "26-6", 25.2, 120.1, 94.9, 72.8, 6.5, 8, 3, "WCC perennial power, Few era", ["offense"]),
    Team("Kentucky", 4, "SEC", "25-8", 22.5, 117.2, 94.7, 71.2, 8.2, 7, 4, "Blue blood revival under Calipari", ["blueblood", "sec"]),
    Team("Gonzaga", 5, "WCC", "26-6", 25.2, 120.1, 94.9, 72.8, 6.5, 8, 3, "WCC perennial power, Few era", ["offense"]),
    Team("Michigan St", 5, "Big Ten", "23-10", 20.8, 113.5, 92.7, 67.8, 9.8, 6, 2, "Izzo tournament pedigree", ["big-ten"]),
    Team("South Carolina", 6, "SEC", "26-7", 19.5, 114.2, 94.7, 67.5, 8.1, 2, 1, "Frank Martin's defense", ["sec"]),
    Team("TCU", 7, "Big 12", "23-10", 17.8, 111.5, 93.7, 68.2, 8.5, 1, 0, "Jamie Dixon's rebuild", ["big-12"]),
    Team("Utah St", 8, "Mountain West", "27-6", 17.2, 112.8, 95.6, 66.5, 4.5, 1, 0, "MWC contender", ["mid-major"]),
]


def get_team(name: str) -> Team | None:
    name_lower = name.lower().strip()
    for t in TEAMS:
        if t.name.lower() == name_lower or t.name.lower().replace(" ", "") == name_lower.replace(" ", ""):
            return t
    return None


def search_teams(query: str) -> list[Team]:
    q = query.lower()
    return [t for t in TEAMS if q in t.name.lower() or q in t.conference.lower() or q in " ".join(t.tags)]


def get_teams_by_seed(seed: int) -> list[Team]:
    return [t for t in TEAMS if t.seed == seed]


def get_teams_by_conference(conf: str) -> list[Team]:
    conf_lower = conf.lower()
    return [t for t in TEAMS if t.conference.lower() == conf_lower]


def get_region_bracket(region: str) -> list[Team]:
    idx = next((i for i, r in enumerate(REGIONS) if r.lower() == region.lower()), -1)
    if idx < 0:
        return []
    start = idx * 16
    return TEAMS[start:start + 16] if start + 16 <= len(TEAMS) else TEAMS[start:]


HISTORICAL_UPSET_RATES = {
    (1, 16): 0.01, (2, 15): 0.06, (3, 14): 0.15, (4, 13): 0.21,
    (5, 12): 0.35, (6, 11): 0.37, (7, 10): 0.39, (8, 9): 0.48,
}
