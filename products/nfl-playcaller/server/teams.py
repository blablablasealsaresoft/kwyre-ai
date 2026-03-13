NFL_TEAMS = [
    {"abbr": "ARI", "name": "Arizona Cardinals", "division": "NFC West", "color": "#97233F"},
    {"abbr": "ATL", "name": "Atlanta Falcons", "division": "NFC South", "color": "#A71930"},
    {"abbr": "BAL", "name": "Baltimore Ravens", "division": "AFC North", "color": "#241773"},
    {"abbr": "BUF", "name": "Buffalo Bills", "division": "AFC East", "color": "#00338D"},
    {"abbr": "CAR", "name": "Carolina Panthers", "division": "NFC South", "color": "#0085CA"},
    {"abbr": "CHI", "name": "Chicago Bears", "division": "NFC North", "color": "#0B162A"},
    {"abbr": "CIN", "name": "Cincinnati Bengals", "division": "AFC North", "color": "#FB4F14"},
    {"abbr": "CLE", "name": "Cleveland Browns", "division": "AFC North", "color": "#311D00"},
    {"abbr": "DAL", "name": "Dallas Cowboys", "division": "NFC East", "color": "#003594"},
    {"abbr": "DEN", "name": "Denver Broncos", "division": "AFC West", "color": "#FB4F14"},
    {"abbr": "DET", "name": "Detroit Lions", "division": "NFC North", "color": "#0076B6"},
    {"abbr": "GB", "name": "Green Bay Packers", "division": "NFC North", "color": "#203731"},
    {"abbr": "HOU", "name": "Houston Texans", "division": "AFC South", "color": "#03202F"},
    {"abbr": "IND", "name": "Indianapolis Colts", "division": "AFC South", "color": "#002C5F"},
    {"abbr": "JAX", "name": "Jacksonville Jaguars", "division": "AFC South", "color": "#006778"},
    {"abbr": "KC", "name": "Kansas City Chiefs", "division": "AFC West", "color": "#E31837"},
    {"abbr": "LAC", "name": "Los Angeles Chargers", "division": "AFC West", "color": "#0080C6"},
    {"abbr": "LAR", "name": "Los Angeles Rams", "division": "NFC West", "color": "#003594"},
    {"abbr": "LV", "name": "Las Vegas Raiders", "division": "AFC West", "color": "#A5ACAF"},
    {"abbr": "MIA", "name": "Miami Dolphins", "division": "AFC East", "color": "#008E97"},
    {"abbr": "MIN", "name": "Minnesota Vikings", "division": "NFC North", "color": "#4F2683"},
    {"abbr": "NE", "name": "New England Patriots", "division": "AFC East", "color": "#002244"},
    {"abbr": "NO", "name": "New Orleans Saints", "division": "NFC South", "color": "#D3BC8D"},
    {"abbr": "NYG", "name": "New York Giants", "division": "NFC East", "color": "#0B2265"},
    {"abbr": "NYJ", "name": "New York Jets", "division": "AFC East", "color": "#125740"},
    {"abbr": "PHI", "name": "Philadelphia Eagles", "division": "NFC East", "color": "#004C54"},
    {"abbr": "PIT", "name": "Pittsburgh Steelers", "division": "AFC North", "color": "#FFB612"},
    {"abbr": "SEA", "name": "Seattle Seahawks", "division": "NFC West", "color": "#002244"},
    {"abbr": "SF", "name": "San Francisco 49ers", "division": "NFC West", "color": "#AA0000"},
    {"abbr": "TB", "name": "Tampa Bay Buccaneers", "division": "NFC South", "color": "#D50A0A"},
    {"abbr": "TEN", "name": "Tennessee Titans", "division": "AFC South", "color": "#0C2340"},
    {"abbr": "WAS", "name": "Washington Commanders", "division": "NFC East", "color": "#5A1414"},
]

TEAM_STATS = {
    "ARI": {"run_pass": 0.42, "blitz_rate": 0.28, "coverage_base": "Cover 3", "tempo": "up-tempo"},
    "ATL": {"run_pass": 0.46, "blitz_rate": 0.25, "coverage_base": "Cover 3", "tempo": "moderate"},
    "BAL": {"run_pass": 0.55, "blitz_rate": 0.38, "coverage_base": "Cover 1", "tempo": "moderate"},
    "BUF": {"run_pass": 0.40, "blitz_rate": 0.30, "coverage_base": "Cover 2", "tempo": "up-tempo"},
    "CAR": {"run_pass": 0.44, "blitz_rate": 0.26, "coverage_base": "Cover 3", "tempo": "moderate"},
    "CHI": {"run_pass": 0.45, "blitz_rate": 0.29, "coverage_base": "Cover 3", "tempo": "slow"},
    "CIN": {"run_pass": 0.41, "blitz_rate": 0.24, "coverage_base": "Cover 3", "tempo": "moderate"},
    "CLE": {"run_pass": 0.50, "blitz_rate": 0.27, "coverage_base": "Cover 3", "tempo": "slow"},
    "DAL": {"run_pass": 0.43, "blitz_rate": 0.32, "coverage_base": "Cover 3", "tempo": "moderate"},
    "DEN": {"run_pass": 0.44, "blitz_rate": 0.30, "coverage_base": "Cover 2", "tempo": "moderate"},
    "DET": {"run_pass": 0.42, "blitz_rate": 0.22, "coverage_base": "Cover 3", "tempo": "up-tempo"},
    "GB": {"run_pass": 0.43, "blitz_rate": 0.26, "coverage_base": "Cover 2", "tempo": "moderate"},
    "HOU": {"run_pass": 0.42, "blitz_rate": 0.33, "coverage_base": "Cover 1", "tempo": "moderate"},
    "IND": {"run_pass": 0.47, "blitz_rate": 0.25, "coverage_base": "Cover 2", "tempo": "moderate"},
    "JAX": {"run_pass": 0.45, "blitz_rate": 0.28, "coverage_base": "Cover 3", "tempo": "moderate"},
    "KC": {"run_pass": 0.41, "blitz_rate": 0.34, "coverage_base": "Cover 2", "tempo": "up-tempo"},
    "LAC": {"run_pass": 0.43, "blitz_rate": 0.29, "coverage_base": "Cover 2", "tempo": "moderate"},
    "LAR": {"run_pass": 0.44, "blitz_rate": 0.31, "coverage_base": "Cover 3", "tempo": "moderate"},
    "LV": {"run_pass": 0.44, "blitz_rate": 0.27, "coverage_base": "Cover 3", "tempo": "slow"},
    "MIA": {"run_pass": 0.39, "blitz_rate": 0.36, "coverage_base": "Cover 1", "tempo": "up-tempo"},
    "MIN": {"run_pass": 0.43, "blitz_rate": 0.31, "coverage_base": "Cover 2", "tempo": "moderate"},
    "NE": {"run_pass": 0.46, "blitz_rate": 0.33, "coverage_base": "Cover 1", "tempo": "slow"},
    "NO": {"run_pass": 0.44, "blitz_rate": 0.28, "coverage_base": "Cover 3", "tempo": "moderate"},
    "NYG": {"run_pass": 0.45, "blitz_rate": 0.30, "coverage_base": "Cover 3", "tempo": "slow"},
    "NYJ": {"run_pass": 0.44, "blitz_rate": 0.35, "coverage_base": "Cover 1", "tempo": "moderate"},
    "PHI": {"run_pass": 0.48, "blitz_rate": 0.27, "coverage_base": "Cover 2", "tempo": "up-tempo"},
    "PIT": {"run_pass": 0.44, "blitz_rate": 0.37, "coverage_base": "Cover 3", "tempo": "moderate"},
    "SEA": {"run_pass": 0.45, "blitz_rate": 0.26, "coverage_base": "Cover 3", "tempo": "moderate"},
    "SF": {"run_pass": 0.48, "blitz_rate": 0.24, "coverage_base": "Cover 3", "tempo": "moderate"},
    "TB": {"run_pass": 0.42, "blitz_rate": 0.32, "coverage_base": "Cover 2", "tempo": "moderate"},
    "TEN": {"run_pass": 0.52, "blitz_rate": 0.26, "coverage_base": "Cover 3", "tempo": "slow"},
    "WAS": {"run_pass": 0.44, "blitz_rate": 0.29, "coverage_base": "Cover 3", "tempo": "moderate"},
}


def get_team(abbr: str) -> dict | None:
    for t in NFL_TEAMS:
        if t["abbr"] == abbr:
            return t
    return None


def get_team_stats(abbr: str) -> dict:
    return TEAM_STATS.get(abbr, {
        "run_pass": 0.44,
        "blitz_rate": 0.28,
        "coverage_base": "Cover 3",
        "tempo": "moderate",
    })


def get_divisions() -> dict[str, list[dict]]:
    divs: dict[str, list[dict]] = {}
    for t in NFL_TEAMS:
        divs.setdefault(t["division"], []).append(t)
    return divs
