"""
NFL Formations Database — 200+ formation entries with personnel groupings,
alignment details, and historical play tendency data.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Formation:
    name: str
    personnel: str
    alignment: str
    run_tendency: float
    pass_tendency: float
    screen_tendency: float
    play_action_tendency: float
    description: str = ""
    variants: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


FORMATIONS: list[Formation] = [
    # ── Shotgun Family ────────────────────────────────────────────────
    Formation("Shotgun Spread", "11", "4 WR wide, 1 RB offset", 0.18, 0.68, 0.08, 0.06, "Four-wide passing formation", ["spread", "trips-right", "trips-left"], ["passing", "spread"]),
    Formation("Shotgun Doubles", "11", "2 WR each side, 1 RB", 0.22, 0.62, 0.09, 0.07, "Balanced two-by-two receiver set", ["doubles-right", "doubles-left"], ["balanced", "spread"]),
    Formation("Shotgun Trips Right", "11", "3 WR right, 1 WR left, 1 RB", 0.17, 0.66, 0.10, 0.07, "Overload right side", [], ["passing", "overload"]),
    Formation("Shotgun Trips Left", "11", "3 WR left, 1 WR right, 1 RB", 0.17, 0.66, 0.10, 0.07, "Overload left side", [], ["passing", "overload"]),
    Formation("Shotgun Trips TE", "12", "3 WR one side, TE inline, 1 RB", 0.28, 0.52, 0.08, 0.12, "Heavy trips with tight end", [], ["balanced", "mismatch"]),
    Formation("Shotgun Empty 5-Wide", "10", "5 WR, no RB", 0.03, 0.82, 0.12, 0.03, "Maximum passing formation", ["empty-trips", "empty-doubles"], ["passing", "empty"]),
    Formation("Shotgun Empty Trips", "10", "3 WR one side, 2 WR other, no RB", 0.03, 0.80, 0.13, 0.04, "Empty with trips overload", [], ["passing", "empty", "overload"]),
    Formation("Shotgun Bunch Right", "11", "3 WR bunched right, 1 WR left, 1 RB", 0.12, 0.68, 0.14, 0.06, "Compressed receiver cluster", [], ["passing", "bunch"]),
    Formation("Shotgun Bunch Left", "11", "3 WR bunched left, 1 WR right, 1 RB", 0.12, 0.68, 0.14, 0.06, "Compressed receiver cluster left", [], ["passing", "bunch"]),
    Formation("Shotgun Wing", "12", "2 WR, TE wing, 1 RB", 0.35, 0.42, 0.05, 0.18, "Wing tight end creates run strength", [], ["balanced", "power"]),
    Formation("Shotgun Ace", "12", "2 WR split, TE inline, 1 RB", 0.30, 0.48, 0.07, 0.15, "Balanced pro-style from shotgun", [], ["balanced"]),
    Formation("Shotgun Twins Right", "11", "2 WR stacked right, 1 WR left, 1 RB", 0.20, 0.62, 0.10, 0.08, "Stacked receivers create pick routes", [], ["passing", "stack"]),
    Formation("Shotgun Twins Left", "11", "2 WR stacked left, 1 WR right, 1 RB", 0.20, 0.62, 0.10, 0.08, "Stacked receivers left", [], ["passing", "stack"]),
    Formation("Shotgun Trey", "13", "1 WR, 2 TE, FB, 1 RB", 0.48, 0.28, 0.04, 0.20, "Heavy shotgun with run emphasis", [], ["power", "heavy"]),
    Formation("Shotgun Y-Trips", "11", "3 WR trips with Y slot, 1 RB", 0.15, 0.68, 0.10, 0.07, "Y receiver in slot of trips", [], ["passing", "trips"]),
    Formation("Shotgun Flex", "11", "2 WR wide, 1 slot, TE detached, 1 RB", 0.25, 0.55, 0.08, 0.12, "Detached tight end flex position", [], ["balanced", "flex"]),
    Formation("Shotgun Cluster", "11", "3 WR clustered near LOS, 1 WR wide, 1 RB", 0.10, 0.70, 0.14, 0.06, "Three receivers near line of scrimmage", [], ["passing", "cluster"]),
    Formation("Shotgun 2x2 Tight", "12", "2 WR each side tight splits, TE, 1 RB", 0.30, 0.48, 0.07, 0.15, "Condensed formation", [], ["balanced", "tight"]),
    Formation("Shotgun Quads", "10", "4 WR one side, 1 WR other", 0.05, 0.78, 0.12, 0.05, "Extreme overload empty", [], ["passing", "overload", "empty"]),
    Formation("Shotgun Deuce", "21", "2 WR, 2 RB, TE inline", 0.38, 0.35, 0.05, 0.22, "Two-back shotgun", [], ["power", "balanced"]),

    # ── Under Center Family ───────────────────────────────────────────
    Formation("Under Center Pro", "21", "2 WR split, FB, RB behind QB", 0.45, 0.28, 0.05, 0.22, "Classic pro formation", ["pro-right", "pro-left"], ["power", "pro-style"]),
    Formation("Under Center I-Form", "21", "2 WR, FB lead, RB deep", 0.50, 0.24, 0.04, 0.22, "I-Formation with fullback lead", ["i-right", "i-left"], ["power", "goal-line"]),
    Formation("Under Center I-Form Strong", "22", "1 WR, 2 TE, FB, RB", 0.58, 0.18, 0.02, 0.22, "Heavy I with two tight ends", [], ["power", "heavy"]),
    Formation("Under Center I-Form Weak", "21", "2 WR weak side, FB, RB", 0.42, 0.32, 0.05, 0.21, "I-Form with receivers weak", [], ["balanced"]),
    Formation("Under Center Split Backs", "20", "2 WR, 2 RB flanking QB", 0.40, 0.35, 0.05, 0.20, "Two backs split behind QB", [], ["balanced", "misdirection"]),
    Formation("Under Center Ace", "12", "2 WR, TE inline, 1 RB", 0.38, 0.38, 0.05, 0.19, "Single back under center", [], ["balanced", "pro-style"]),
    Formation("Under Center Near", "21", "2 WR, FB near side, RB", 0.46, 0.28, 0.04, 0.22, "FB aligned to strong side", [], ["power"]),
    Formation("Under Center Far", "21", "2 WR, FB far side, RB", 0.40, 0.32, 0.06, 0.22, "FB aligned to weak side", [], ["misdirection"]),
    Formation("Under Center Singleback", "11", "3 WR, 1 RB behind QB", 0.32, 0.45, 0.08, 0.15, "Singleback under center", [], ["balanced"]),
    Formation("Under Center Tight", "13", "1 WR, 3 TE, 1 RB", 0.58, 0.18, 0.02, 0.22, "Heavy formation", [], ["power", "heavy", "goal-line"]),
    Formation("Under Center Jumbo", "23", "0 WR, 3 TE, 2 RB", 0.72, 0.08, 0.01, 0.19, "Maximum run personnel", [], ["power", "goal-line", "heavy"]),
    Formation("Under Center Offset", "21", "2 WR, FB offset, RB", 0.42, 0.30, 0.05, 0.23, "Fullback offset to one side", [], ["power", "misdirection"]),
    Formation("Under Center Wing T", "22", "1 WR, TE, wingback, FB, RB", 0.55, 0.18, 0.03, 0.24, "Wing-T base formation", [], ["power", "misdirection"]),
    Formation("Under Center Double TE", "12", "2 WR, 2 TE inline, 1 RB", 0.45, 0.30, 0.04, 0.21, "Two tight end base", [], ["power", "balanced"]),
    Formation("Under Center Maryland I", "22", "1 WR, 2 TE, FB, RB deep offset", 0.55, 0.20, 0.03, 0.22, "Three-back style formation", [], ["power", "heavy"]),
    Formation("Under Center Weak I", "21", "2 WR, FB weak, RB", 0.44, 0.30, 0.04, 0.22, "I-Form with FB to weak side", [], ["misdirection"]),
    Formation("Under Center Strong I", "21", "2 WR, FB strong, RB", 0.48, 0.26, 0.04, 0.22, "I-Form with FB to strong side", [], ["power"]),
    Formation("Under Center Twins", "11", "2 WR same side, 1 WR, 1 RB", 0.30, 0.48, 0.07, 0.15, "Twin receivers under center", [], ["balanced"]),
    Formation("Under Center Goal Line Heavy", "23", "0 WR, 3 TE, FB, RB", 0.75, 0.05, 0.01, 0.19, "Short yardage heavy", [], ["goal-line", "heavy"]),
    Formation("Under Center FB Dive", "22", "1 WR, 2 TE, FB ahead, RB", 0.60, 0.15, 0.02, 0.23, "FB dive formation", [], ["power", "short-yardage"]),

    # ── Pistol Family ─────────────────────────────────────────────────
    Formation("Pistol Spread", "11", "4 WR, RB behind QB (closer)", 0.28, 0.52, 0.08, 0.12, "Pistol with four receivers", [], ["spread", "RPO"]),
    Formation("Pistol Trips", "11", "3 WR trips, 1 WR, RB behind QB", 0.25, 0.55, 0.08, 0.12, "Trips from pistol alignment", [], ["passing", "RPO"]),
    Formation("Pistol Strong", "12", "2 WR, TE strong, RB behind QB", 0.38, 0.35, 0.05, 0.22, "Heavy pistol", [], ["power", "RPO"]),
    Formation("Pistol Deuce", "21", "2 WR, FB, RB behind QB", 0.42, 0.30, 0.05, 0.23, "Two-back pistol", [], ["power"]),
    Formation("Pistol Wing", "12", "2 WR, TE wing, RB behind QB", 0.40, 0.32, 0.05, 0.23, "Wing TE from pistol", [], ["power", "RPO"]),
    Formation("Pistol Doubles", "11", "2 WR each side, RB behind QB", 0.30, 0.48, 0.08, 0.14, "Balanced pistol", [], ["balanced", "RPO"]),
    Formation("Pistol Ace", "12", "2 WR, TE inline, RB behind QB", 0.35, 0.40, 0.05, 0.20, "Ace from pistol", [], ["balanced"]),
    Formation("Pistol Tight Doubles", "12", "2 WR tight, TE, RB behind QB", 0.38, 0.35, 0.05, 0.22, "Condensed pistol", [], ["balanced", "tight"]),
    Formation("Pistol Read Option", "11", "3 WR, 1 RB behind QB, read key", 0.45, 0.30, 0.05, 0.20, "Zone read base", [], ["RPO", "read-option"]),
    Formation("Pistol Power", "22", "1 WR, 2 TE, FB, RB behind QB", 0.55, 0.20, 0.03, 0.22, "Heavy pistol run", [], ["power", "heavy"]),

    # ── Empty Backfield ───────────────────────────────────────────────
    Formation("Empty Trey", "10", "3 WR right, 2 WR left, no RB", 0.03, 0.82, 0.12, 0.03, "Trips right empty", [], ["passing", "empty"]),
    Formation("Empty Deuce", "10", "2x3 or 3x2 empty look", 0.03, 0.80, 0.13, 0.04, "Empty balanced", [], ["passing", "empty"]),
    Formation("Empty Bunch Trips", "10", "Bunch one side, 2 WR other, no RB", 0.04, 0.78, 0.14, 0.04, "Bunch empty", [], ["passing", "empty", "bunch"]),
    Formation("Empty Overload", "10", "4 WR one side, 1 WR other", 0.03, 0.80, 0.13, 0.04, "Extreme overload", [], ["passing", "empty", "overload"]),
    Formation("Empty Stack", "10", "Stacked receivers both sides", 0.03, 0.80, 0.14, 0.03, "Pick route empty", [], ["passing", "empty", "stack"]),
    Formation("Empty Y-Off", "10", "TE detached as slot, 4 WR, no RB", 0.05, 0.78, 0.12, 0.05, "TE as receiver in empty", [], ["passing", "empty"]),
    Formation("Empty Nasty", "10", "5 WR tight to formation, no RB", 0.03, 0.78, 0.15, 0.04, "Compressed empty", [], ["passing", "empty"]),
    Formation("Empty Wide", "10", "5 WR max splits, no RB", 0.02, 0.84, 0.11, 0.03, "Maximum horizontal stretch", [], ["passing", "empty", "spread"]),

    # ── Singleback Family ─────────────────────────────────────────────
    Formation("Singleback Ace", "12", "2 WR, TE inline, 1 RB", 0.32, 0.45, 0.08, 0.15, "Standard singleback", [], ["balanced"]),
    Formation("Singleback Doubles", "11", "2 WR each side, 1 RB", 0.28, 0.50, 0.10, 0.12, "Balanced singleback", [], ["balanced"]),
    Formation("Singleback Trips", "11", "3 WR one side, 1 RB", 0.22, 0.58, 0.10, 0.10, "Trips singleback", [], ["passing"]),
    Formation("Singleback Bunch", "11", "3 WR bunched, 1 WR, 1 RB", 0.18, 0.60, 0.14, 0.08, "Bunch from singleback", [], ["passing", "bunch"]),
    Formation("Singleback Wing", "12", "2 WR, TE wing, 1 RB", 0.38, 0.35, 0.05, 0.22, "Wing TE singleback", [], ["power"]),
    Formation("Singleback Tight Pair", "13", "1 WR, 2 TE same side, FB, 1 RB", 0.52, 0.22, 0.03, 0.23, "Heavy singleback", [], ["power", "heavy"]),
    Formation("Singleback Spread", "11", "4 WR, 1 RB", 0.15, 0.68, 0.10, 0.07, "Singleback four-wide", [], ["passing", "spread"]),
    Formation("Singleback Jumbo", "13", "1 WR, 3 TE, 1 RB", 0.55, 0.20, 0.03, 0.22, "Jumbo singleback", [], ["power", "heavy"]),
    Formation("Singleback Flex Twins", "12", "2 WR twins, TE flex, 1 RB", 0.28, 0.50, 0.08, 0.14, "Flex twins singleback", [], ["balanced"]),
    Formation("Singleback Offset", "11", "3 WR, 1 RB offset strong", 0.25, 0.52, 0.10, 0.13, "Offset back singleback", [], ["balanced"]),

    # ── Wildcat / Special ─────────────────────────────────────────────
    Formation("Wildcat Direct Snap", "21", "Direct snap to RB, QB as WR, 2 WR", 0.75, 0.10, 0.02, 0.13, "Direct snap wildcat", [], ["wildcat", "trick"]),
    Formation("Wildcat Power", "22", "Direct snap to RB, FB lead, 2 TE, 1 WR", 0.80, 0.05, 0.01, 0.14, "Heavy wildcat", [], ["wildcat", "power"]),
    Formation("Wildcat Speed", "11", "Direct snap to RB, 4 WR", 0.55, 0.25, 0.05, 0.15, "Speed wildcat", [], ["wildcat", "spread"]),
    Formation("Philly Special", "12", "TE takes snap, QB as receiver", 0.15, 0.70, 0.05, 0.10, "Trick play formation", [], ["trick", "special"]),
    Formation("Swinging Gate", "12", "Unbalanced line, WRs offset", 0.30, 0.50, 0.05, 0.15, "Unusual alignment", [], ["trick", "special"]),
    Formation("Punt Formation", "00", "Punter deep, gunners wide", 0.05, 0.08, 0.02, 0.85, "Fake punt look", [], ["special-teams", "trick"]),
    Formation("FG Formation", "00", "Holder + kicker, wing", 0.05, 0.10, 0.02, 0.83, "Fake FG look", [], ["special-teams", "trick"]),
    Formation("Annexation of Puerto Rico", "11", "Hook and ladder trick variant", 0.05, 0.80, 0.10, 0.05, "Multi-lateral trick play", [], ["trick"]),

    # ── Goal Line ─────────────────────────────────────────────────────
    Formation("Goal Line I-Form", "22", "2 TE, FB, RB, 1 WR", 0.65, 0.15, 0.02, 0.18, "Standard goal line", [], ["goal-line", "power"]),
    Formation("Goal Line Jumbo", "23", "3 TE, FB, RB, 0 WR", 0.75, 0.05, 0.01, 0.19, "Maximum blocking", [], ["goal-line", "heavy"]),
    Formation("Goal Line Split", "12", "2 WR split wide, TE, 1 RB", 0.35, 0.45, 0.05, 0.15, "Goal line spread", [], ["goal-line", "spread"]),
    Formation("Goal Line Heavy Left", "23", "Heavy left side, 3 TE, 2 RB", 0.70, 0.08, 0.01, 0.21, "Left side power", [], ["goal-line", "heavy"]),
    Formation("Goal Line Heavy Right", "23", "Heavy right side, 3 TE, 2 RB", 0.70, 0.08, 0.01, 0.21, "Right side power", [], ["goal-line", "heavy"]),
    Formation("Goal Line Sneak", "22", "QB under center, heavy set", 0.85, 0.05, 0.01, 0.09, "QB sneak formation", [], ["goal-line", "sneak"]),
    Formation("Goal Line Fade", "12", "2 WR wide for fades, TE, 1 RB", 0.20, 0.65, 0.03, 0.12, "Fade route goal line", [], ["goal-line", "passing"]),
    Formation("Goal Line Toss", "22", "2 TE, FB, RB offset for toss", 0.60, 0.15, 0.05, 0.20, "Sweep/toss goal line", [], ["goal-line"]),

    # ── Spread Family ─────────────────────────────────────────────────
    Formation("Spread 10 Personnel", "10", "5 WR spread wide", 0.05, 0.80, 0.12, 0.03, "Pure spread empty", [], ["spread", "passing"]),
    Formation("Spread 11 Personnel", "11", "4 WR, 1 RB, spread", 0.18, 0.65, 0.10, 0.07, "Standard spread", [], ["spread"]),
    Formation("Spread Power Read", "11", "3 WR, 1 TE detached, 1 RB", 0.35, 0.40, 0.05, 0.20, "Power read option", [], ["spread", "RPO"]),
    Formation("Spread Jet Motion", "11", "4 WR, jet motion, 1 RB", 0.30, 0.48, 0.08, 0.14, "Jet sweep look", [], ["spread", "motion"]),
    Formation("Spread Zone Read", "11", "3 WR, 1 TE, 1 RB, read key", 0.40, 0.35, 0.05, 0.20, "Zone read from spread", [], ["spread", "RPO"]),
    Formation("Spread RPO", "11", "3 WR, 1 slot, 1 RB, RPO key", 0.35, 0.42, 0.08, 0.15, "Run-pass option base", [], ["spread", "RPO"]),
    Formation("Spread Quick Game", "11", "4 WR, 1 RB, quick pass concepts", 0.12, 0.72, 0.10, 0.06, "Quick-game spread", [], ["spread", "passing"]),
    Formation("Spread Heavy", "12", "2 WR spread, TE, 1 RB wide splits", 0.32, 0.45, 0.06, 0.17, "Spread with TE support", [], ["spread", "balanced"]),

    # ── Trips Variants ────────────────────────────────────────────────
    Formation("Trips Right Bunch", "11", "3 WR bunched right, 1 WR left, 1 RB", 0.12, 0.68, 0.14, 0.06, "Trips bunch right", [], ["trips", "bunch"]),
    Formation("Trips Left Bunch", "11", "3 WR bunched left, 1 WR right, 1 RB", 0.12, 0.68, 0.14, 0.06, "Trips bunch left", [], ["trips", "bunch"]),
    Formation("Trips Right Stack", "11", "3 WR stacked right, 1 WR left, 1 RB", 0.14, 0.66, 0.12, 0.08, "Stacked trips right", [], ["trips", "stack"]),
    Formation("Trips Left Stack", "11", "3 WR stacked left, 1 WR right, 1 RB", 0.14, 0.66, 0.12, 0.08, "Stacked trips left", [], ["trips", "stack"]),
    Formation("Trips TE Right", "12", "2 WR + TE right, 1 WR left, 1 RB", 0.30, 0.48, 0.07, 0.15, "TE as third in trips", [], ["trips", "balanced"]),
    Formation("Trips TE Left", "12", "2 WR + TE left, 1 WR right, 1 RB", 0.30, 0.48, 0.07, 0.15, "TE trips left", [], ["trips", "balanced"]),
    Formation("Trips Tight Right", "11", "3 WR tight splits right, 1 WR left, 1 RB", 0.15, 0.65, 0.13, 0.07, "Condensed trips right", [], ["trips", "tight"]),
    Formation("Trips Wide Right", "11", "3 WR max splits right, 1 WR left, 1 RB", 0.10, 0.72, 0.10, 0.08, "Wide trips right", [], ["trips", "spread"]),
    Formation("Trips Wing Right", "12", "2 WR + TE wing right, 1 WR left, 1 RB", 0.35, 0.40, 0.05, 0.20, "Wing trips right", [], ["trips", "power"]),

    # ── Bunch Variants ────────────────────────────────────────────────
    Formation("Bunch Right Close", "11", "3 WR bunched very tight right, 1 WR left, 1 RB", 0.10, 0.70, 0.15, 0.05, "Very tight bunch right", [], ["bunch", "pick"]),
    Formation("Bunch Left Close", "11", "3 WR bunched very tight left, 1 WR right, 1 RB", 0.10, 0.70, 0.15, 0.05, "Very tight bunch left", [], ["bunch", "pick"]),
    Formation("Bunch Right Offset RB", "11", "3 WR bunched right, 1 WR left, RB offset", 0.15, 0.65, 0.13, 0.07, "Bunch with offset back", [], ["bunch"]),
    Formation("Bunch Right TE", "12", "2 WR + TE bunched right, 1 WR left, 1 RB", 0.25, 0.52, 0.12, 0.11, "TE in bunch", [], ["bunch", "balanced"]),
    Formation("Double Bunch", "11", "2 WR bunched each side, 1 RB", 0.12, 0.68, 0.14, 0.06, "Bunches on both sides", [], ["bunch"]),

    # ── 12 Personnel Heavy ────────────────────────────────────────────
    Formation("12 Personnel Ace", "12", "2 WR, TE inline, H-back, 1 RB", 0.35, 0.40, 0.06, 0.19, "Two TE ace set", [], ["balanced", "12-personnel"]),
    Formation("12 Personnel Twins", "12", "2 WR twins, 2 TE inline, 1 RB", 0.32, 0.42, 0.07, 0.19, "Twins with two TEs", [], ["balanced", "12-personnel"]),
    Formation("12 Personnel Wing", "12", "2 WR, TE inline, TE wing, 1 RB", 0.42, 0.30, 0.05, 0.23, "Wing formation two TEs", [], ["power", "12-personnel"]),
    Formation("12 Personnel Spread", "12", "2 WR wide, 2 TE detached, 1 RB", 0.25, 0.52, 0.08, 0.15, "12 personnel spread out", [], ["spread", "12-personnel"]),
    Formation("12 Personnel Split", "12", "2 WR, TEs split each side, 1 RB", 0.35, 0.40, 0.06, 0.19, "TEs split sides", [], ["balanced", "12-personnel"]),

    # ── 13 Personnel Heavy ────────────────────────────────────────────
    Formation("13 Personnel Base", "13", "1 WR, 3 TE, 1 RB", 0.55, 0.20, 0.03, 0.22, "Three TE heavy", [], ["power", "heavy", "13-personnel"]),
    Formation("13 Personnel Strong Right", "13", "1 WR left, 3 TE right, 1 RB", 0.58, 0.18, 0.02, 0.22, "Overloaded right", [], ["power", "heavy"]),
    Formation("13 Personnel Strong Left", "13", "1 WR right, 3 TE left, 1 RB", 0.58, 0.18, 0.02, 0.22, "Overloaded left", [], ["power", "heavy"]),
    Formation("13 Personnel Spread", "13", "1 WR, 2 TE inline, 1 TE detached, 1 RB", 0.42, 0.32, 0.04, 0.22, "Spread with 3 TEs", [], ["balanced", "13-personnel"]),

    # ── 21 Personnel ──────────────────────────────────────────────────
    Formation("21 Personnel Pro Right", "21", "2 WR, FB right, RB", 0.45, 0.28, 0.05, 0.22, "Pro formation right", [], ["power", "21-personnel"]),
    Formation("21 Personnel Pro Left", "21", "2 WR, FB left, RB", 0.45, 0.28, 0.05, 0.22, "Pro formation left", [], ["power", "21-personnel"]),
    Formation("21 Personnel Split", "21", "2 WR, FB and RB split", 0.38, 0.35, 0.05, 0.22, "Split backs 21", [], ["balanced", "21-personnel"]),
    Formation("21 Personnel Far", "21", "2 WR, FB far side, RB", 0.40, 0.32, 0.06, 0.22, "Far FB alignment", [], ["misdirection"]),
    Formation("21 Personnel Near", "21", "2 WR, FB near side, RB", 0.46, 0.28, 0.04, 0.22, "Near FB alignment", [], ["power"]),
    Formation("21 Personnel I-Weak", "21", "2 WR, FB behind QB weak, RB", 0.42, 0.32, 0.05, 0.21, "Weak I alignment", [], ["misdirection"]),
    Formation("21 Personnel Twins", "21", "2 WR twins, FB, RB", 0.40, 0.34, 0.05, 0.21, "Twins with FB", [], ["balanced"]),

    # ── 22 Personnel ──────────────────────────────────────────────────
    Formation("22 Personnel Base", "22", "1 WR, 2 TE, FB, RB", 0.55, 0.18, 0.03, 0.24, "Heavy 22 base", [], ["power", "heavy"]),
    Formation("22 Personnel Power I", "22", "1 WR, 2 TE, FB lead, RB", 0.58, 0.16, 0.02, 0.24, "Power I 22 personnel", [], ["power", "goal-line"]),
    Formation("22 Personnel Split", "22", "1 WR, 2 TE, RBs split", 0.48, 0.22, 0.04, 0.26, "Split backs 22", [], ["power", "misdirection"]),
    Formation("22 Personnel Wing T", "22", "1 WR, 2 TE, wing, RB", 0.52, 0.20, 0.03, 0.25, "Wing T from 22", [], ["power", "misdirection"]),

    # ── Unbalanced Line ───────────────────────────────────────────────
    Formation("Unbalanced Right", "12", "Extra OL right, 2 WR, TE, 1 RB", 0.55, 0.25, 0.03, 0.17, "Unbalanced right line", [], ["trick", "power"]),
    Formation("Unbalanced Left", "12", "Extra OL left, 2 WR, TE, 1 RB", 0.55, 0.25, 0.03, 0.17, "Unbalanced left line", [], ["trick", "power"]),
    Formation("Unbalanced Tackle Over Right", "12", "Tackle covered right, 2 WR, TE, 1 RB", 0.52, 0.28, 0.03, 0.17, "Tackle over to right", [], ["trick", "power"]),

    # ── Motion/Shift Packages ─────────────────────────────────────────
    Formation("Jet Motion Right", "11", "Any base + jet motion right", 0.35, 0.42, 0.08, 0.15, "Jet sweep right action", [], ["motion", "misdirection"]),
    Formation("Jet Motion Left", "11", "Any base + jet motion left", 0.35, 0.42, 0.08, 0.15, "Jet sweep left action", [], ["motion", "misdirection"]),
    Formation("Orbit Motion", "11", "RB/WR orbit motion behind QB", 0.30, 0.45, 0.10, 0.15, "Orbit/fly motion", [], ["motion", "misdirection"]),
    Formation("TE Motion Across", "12", "TE motioning across formation", 0.35, 0.38, 0.05, 0.22, "TE in motion", [], ["motion"]),
    Formation("Shift to Empty", "10", "Shift from pro to empty pre-snap", 0.05, 0.78, 0.12, 0.05, "Shift package to empty", [], ["motion", "shift"]),
    Formation("Shift to Unbalanced", "12", "Shift to create unbalanced line", 0.50, 0.28, 0.04, 0.18, "Shift to unbalanced", [], ["motion", "shift", "trick"]),
    Formation("WR Crack Motion", "11", "WR motioning inside for crack block", 0.45, 0.32, 0.05, 0.18, "Crack block motion", [], ["motion"]),
    Formation("Bunch to Spread Shift", "11", "Shift from bunch to spread pre-snap", 0.15, 0.65, 0.12, 0.08, "Shift package", [], ["motion", "shift"]),

    # ── Two-Point Conversion ──────────────────────────────────────────
    Formation("2PT Spread", "11", "4 WR, 1 RB for 2-point try", 0.20, 0.70, 0.05, 0.05, "2-point spread look", [], ["2-point"]),
    Formation("2PT Heavy", "23", "3 TE, 2 RB, goal line 2-point", 0.70, 0.10, 0.02, 0.18, "2-point heavy push", [], ["2-point", "goal-line"]),
    Formation("2PT Trick", "11", "Trick play setup for 2-point", 0.15, 0.60, 0.10, 0.15, "2-point special", [], ["2-point", "trick"]),

    # ── Hail Mary / Desperation ───────────────────────────────────────
    Formation("Hail Mary", "10", "5 WR deep, no RB", 0.01, 0.95, 0.02, 0.02, "Desperation deep shot", [], ["hail-mary", "passing"]),
    Formation("Hail Mary Hook and Ladder", "10", "5 WR, lateral planned", 0.02, 0.90, 0.05, 0.03, "Lateral trick desperation", [], ["hail-mary", "trick"]),

    # ── Nickel/Dime Offensive Adjustments ─────────────────────────────
    Formation("11 vs Nickel Spread", "11", "Spread to exploit nickel DB matchups", 0.15, 0.70, 0.08, 0.07, "Anti-nickel spread", [], ["spread", "matchup"]),
    Formation("12 vs Nickel Power", "12", "12 personnel to create size mismatch vs nickel", 0.42, 0.32, 0.05, 0.21, "Anti-nickel power", [], ["power", "matchup"]),
    Formation("10 vs Dime Attack", "10", "Empty to exploit dime DBs in run support", 0.05, 0.78, 0.12, 0.05, "Anti-dime empty", [], ["passing", "matchup"]),

    # ── Play-Action Specific ──────────────────────────────────────────
    Formation("PA Boot Right", "12", "TE inline, RB fake left, QB boot right", 0.05, 0.10, 0.02, 0.83, "Bootleg right", [], ["play-action", "boot"]),
    Formation("PA Boot Left", "12", "TE inline, RB fake right, QB boot left", 0.05, 0.10, 0.02, 0.83, "Bootleg left", [], ["play-action", "boot"]),
    Formation("PA Counter Boot", "21", "FB and RB fake counter, QB boot", 0.05, 0.08, 0.02, 0.85, "Counter action boot", [], ["play-action", "boot"]),
    Formation("PA Power", "21", "FB lead fake, power run action", 0.08, 0.12, 0.02, 0.78, "Power run fake", [], ["play-action"]),
    Formation("PA Naked", "12", "No protection, all-out boot", 0.03, 0.12, 0.02, 0.83, "Naked bootleg", [], ["play-action"]),
    Formation("PA Waggle", "21", "FB weak, RB lead strong, waggle", 0.05, 0.10, 0.02, 0.83, "Waggle action", [], ["play-action"]),

    # ── Screen Specific ───────────────────────────────────────────────
    Formation("Screen Trips", "11", "Trips look, screen to RB", 0.05, 0.15, 0.72, 0.08, "Trips screen", [], ["screen"]),
    Formation("Screen Bubble", "11", "WR screen bubble pass", 0.03, 0.18, 0.72, 0.07, "Bubble screen", [], ["screen", "spread"]),
    Formation("Tunnel Screen", "11", "Inside WR tunnel screen", 0.03, 0.15, 0.75, 0.07, "Tunnel screen", [], ["screen"]),
    Formation("Jailbreak Screen", "11", "All OL release for screen", 0.03, 0.12, 0.78, 0.07, "Jailbreak screen", [], ["screen"]),
    Formation("TE Screen", "12", "Screen to tight end", 0.05, 0.18, 0.68, 0.09, "Tight end screen", [], ["screen"]),
    Formation("Slip Screen", "11", "Delayed RB screen behind LOS", 0.05, 0.15, 0.72, 0.08, "Slip/delayed screen", [], ["screen"]),

    # ── RPO Packages ──────────────────────────────────────────────────
    Formation("RPO Glance", "11", "Spread RPO with glance route", 0.35, 0.42, 0.08, 0.15, "Glance route RPO", [], ["RPO"]),
    Formation("RPO Bubble", "11", "Spread RPO with bubble screen", 0.32, 0.38, 0.18, 0.12, "Bubble RPO", [], ["RPO", "screen"]),
    Formation("RPO Pop Pass", "12", "RPO with TE pop pass", 0.38, 0.35, 0.08, 0.19, "Pop pass RPO", [], ["RPO"]),
    Formation("RPO Power Read", "11", "Power read RPO with pass option", 0.40, 0.35, 0.05, 0.20, "Power read RPO", [], ["RPO", "power"]),
    Formation("RPO Zone Read", "11", "Zone read RPO with slant option", 0.38, 0.38, 0.08, 0.16, "Zone read RPO", [], ["RPO"]),
    Formation("RPO Peek", "12", "RPO with peek at LB key", 0.35, 0.40, 0.08, 0.17, "Peek RPO", [], ["RPO"]),

    # ── Hurry-Up / No Huddle ──────────────────────────────────────────
    Formation("No Huddle Spread", "11", "Up-tempo spread", 0.20, 0.62, 0.10, 0.08, "No huddle spread", [], ["no-huddle", "spread"]),
    Formation("No Huddle Doubles", "11", "Up-tempo 2x2", 0.25, 0.55, 0.10, 0.10, "No huddle balanced", [], ["no-huddle"]),
    Formation("Hurry Up Trips", "11", "Fast trips look", 0.18, 0.62, 0.12, 0.08, "Hurry up trips", [], ["no-huddle"]),
    Formation("Sugar Huddle", "11", "Fake hurry up to catch defense", 0.25, 0.50, 0.10, 0.15, "Faked tempo", [], ["no-huddle", "trick"]),

    # ── Compressed / Tight Sets ───────────────────────────────────────
    Formation("Tight Bunch Right", "11", "All receivers within 5 yards right", 0.15, 0.62, 0.15, 0.08, "Very tight bunch", [], ["tight", "bunch"]),
    Formation("Tight Stack Right", "11", "Stacked receivers right, tight", 0.15, 0.62, 0.15, 0.08, "Tight stack", [], ["tight", "stack"]),
    Formation("Nub TE Right", "12", "TE inline with no WR to his side", 0.42, 0.32, 0.05, 0.21, "Nub tight end right", [], ["tight"]),
    Formation("Nub TE Left", "12", "TE inline with no WR to his side", 0.42, 0.32, 0.05, 0.21, "Nub tight end left", [], ["tight"]),
    Formation("Heavy Tight Right", "13", "3 TE tight right, 1 WR left", 0.55, 0.20, 0.03, 0.22, "Heavy tight formation", [], ["tight", "power"]),

    # ── Modern College-to-NFL Imports ─────────────────────────────────
    Formation("Air Raid 10 Personnel", "10", "5 WR, air raid concepts", 0.05, 0.82, 0.10, 0.03, "Air raid empty", [], ["air-raid", "passing"]),
    Formation("Air Raid Mesh", "11", "4 WR mesh concept, 1 RB", 0.10, 0.72, 0.12, 0.06, "Mesh passing concept", [], ["air-raid", "passing"]),
    Formation("Triple Option Pistol", "11", "3 WR, pistol, triple option read", 0.50, 0.25, 0.05, 0.20, "Triple option", [], ["option", "RPO"]),
    Formation("Veer Triple", "21", "FB, RB, veer triple option", 0.55, 0.20, 0.03, 0.22, "Veer option", [], ["option"]),
    Formation("Speed Option", "11", "Pitch option to outside", 0.55, 0.22, 0.05, 0.18, "Speed option", [], ["option"]),
    Formation("Bash RPO", "11", "Back away/speed option with RPO", 0.38, 0.38, 0.08, 0.16, "Bash concept", [], ["RPO", "option"]),

    # ── Trick Play Formations ─────────────────────────────────────────
    Formation("Flea Flicker", "11", "RB handoff then pitch back to QB", 0.05, 0.85, 0.02, 0.08, "Flea flicker setup", [], ["trick"]),
    Formation("Double Pass", "11", "WR receives then throws", 0.03, 0.88, 0.02, 0.07, "WR throwback pass", [], ["trick"]),
    Formation("Statue of Liberty", "11", "QB fake pass, hand off behind back", 0.82, 0.05, 0.02, 0.11, "Statue play", [], ["trick"]),
    Formation("Fumblerooski", "22", "Intentional fumble for lineman", 0.80, 0.05, 0.02, 0.13, "Fumblerooski trick", [], ["trick"]),
    Formation("Hook and Ladder", "11", "Catch and lateral sequence", 0.02, 0.85, 0.08, 0.05, "Hook and lateral", [], ["trick", "hail-mary"]),
    Formation("Reverse", "11", "End-around reverse", 0.70, 0.10, 0.05, 0.15, "Reverse play", [], ["trick", "misdirection"]),
    Formation("Double Reverse", "11", "Two handoffs in reverse sequence", 0.65, 0.12, 0.05, 0.18, "Double reverse", [], ["trick", "misdirection"]),
    Formation("QB Draw", "11", "Shotgun, fake pass, QB draw", 0.75, 0.10, 0.05, 0.10, "QB draw play", [], ["RPO"]),

    # ── Shotgun Extended ──────────────────────────────────────────────
    Formation("Shotgun Split Close", "11", "2 WR tight each side, 1 RB", 0.25, 0.55, 0.10, 0.10, "Tight split shotgun", [], ["balanced", "tight"]),
    Formation("Shotgun Trey Open", "13", "1 WR wide, 2 TE inline, FB offset, 1 RB", 0.45, 0.30, 0.04, 0.21, "Open trey from shotgun", [], ["power"]),
    Formation("Shotgun Nasty Bunch", "11", "3 WR bunched tight, 1 WR nasty split, 1 RB", 0.10, 0.70, 0.14, 0.06, "Nasty split bunch", [], ["bunch", "pick"]),
    Formation("Shotgun Offset I", "21", "2 WR, FB offset, RB deep, shotgun", 0.38, 0.35, 0.05, 0.22, "Offset I from gun", [], ["power"]),
    Formation("Shotgun Tackle Over", "12", "Unbalanced line, TE, 2 WR, 1 RB", 0.48, 0.30, 0.04, 0.18, "Unbalanced shotgun", [], ["trick", "power"]),
    Formation("Shotgun Wide Doubles", "11", "2 WR max split each side, 1 RB", 0.15, 0.68, 0.10, 0.07, "Max split doubles", [], ["spread", "passing"]),
    Formation("Shotgun H-Back", "12", "2 WR, H-back, TE, 1 RB", 0.32, 0.42, 0.06, 0.20, "H-back alignment", [], ["balanced"]),
    Formation("Shotgun Duo", "12", "2 WR, 2 TE, 1 RB duo concept", 0.40, 0.35, 0.05, 0.20, "Duo run look from gun", [], ["power"]),
    Formation("Shotgun Nub", "12", "2 WR, nub TE, 1 RB", 0.35, 0.42, 0.06, 0.17, "Nub TE shotgun", [], ["balanced"]),
    Formation("Shotgun Diamond", "21", "2 WR, FB and RB diamond behind QB", 0.40, 0.32, 0.05, 0.23, "Diamond backfield", [], ["power", "misdirection"]),

    # ── Under Center Extended ─────────────────────────────────────────
    Formation("Under Center Power Right", "21", "2 WR, FB right, pull guard right, RB", 0.55, 0.20, 0.03, 0.22, "Power right scheme", [], ["power"]),
    Formation("Under Center Power Left", "21", "2 WR, FB left, pull guard left, RB", 0.55, 0.20, 0.03, 0.22, "Power left scheme", [], ["power"]),
    Formation("Under Center Counter", "21", "2 WR, FB counter step, RB counter", 0.50, 0.22, 0.04, 0.24, "Counter run scheme", [], ["power", "misdirection"]),
    Formation("Under Center Stretch Right", "11", "3 WR, 1 RB zone stretch right", 0.48, 0.30, 0.04, 0.18, "Zone stretch right", [], ["zone"]),
    Formation("Under Center Stretch Left", "11", "3 WR, 1 RB zone stretch left", 0.48, 0.30, 0.04, 0.18, "Zone stretch left", [], ["zone"]),
    Formation("Under Center Iso", "21", "2 WR, FB lead ISO block, RB", 0.52, 0.22, 0.03, 0.23, "Isolation run", [], ["power"]),
    Formation("Under Center Trap", "21", "2 WR, FB fake, guard trap, RB", 0.55, 0.18, 0.03, 0.24, "Trap run", [], ["power", "misdirection"]),
    Formation("Under Center Sweep Right", "21", "2 WR, FB lead sweep, RB outside right", 0.50, 0.22, 0.05, 0.23, "Sweep right", [], ["outside-run"]),
    Formation("Under Center Sweep Left", "21", "2 WR, FB lead sweep, RB outside left", 0.50, 0.22, 0.05, 0.23, "Sweep left", [], ["outside-run"]),
    Formation("Under Center Inside Zone", "11", "3 WR, 1 RB inside zone read", 0.45, 0.32, 0.04, 0.19, "Inside zone", [], ["zone"]),
    Formation("Under Center Outside Zone", "11", "3 WR, 1 RB outside zone", 0.45, 0.30, 0.05, 0.20, "Outside zone", [], ["zone"]),
    Formation("Under Center Toss Crack", "21", "2 WR, FB, RB toss with WR crack", 0.52, 0.20, 0.05, 0.23, "Toss crack scheme", [], ["outside-run"]),

    # ── Pistol Extended ───────────────────────────────────────────────
    Formation("Pistol Read Zone Left", "11", "3 WR, 1 RB, zone left read", 0.42, 0.33, 0.05, 0.20, "Zone left from pistol", [], ["RPO", "zone"]),
    Formation("Pistol Read Zone Right", "11", "3 WR, 1 RB, zone right read", 0.42, 0.33, 0.05, 0.20, "Zone right from pistol", [], ["RPO", "zone"]),
    Formation("Pistol Counter", "12", "2 WR, TE, RB counter behind QB", 0.48, 0.28, 0.04, 0.20, "Counter from pistol", [], ["misdirection"]),
    Formation("Pistol Jet Sweep", "11", "3 WR, WR jet motion, RB behind QB", 0.40, 0.35, 0.08, 0.17, "Jet sweep pistol", [], ["motion", "misdirection"]),
    Formation("Pistol Y-Cross", "12", "2 WR, TE crossing, RB behind QB", 0.28, 0.48, 0.06, 0.18, "Y-cross concept pistol", [], ["passing"]),
    Formation("Pistol Power Spread", "11", "4 WR, RB behind QB, power read", 0.35, 0.42, 0.08, 0.15, "Power spread pistol", [], ["RPO", "spread"]),
    Formation("Pistol FB Lead", "21", "2 WR, FB lead, RB behind QB", 0.48, 0.25, 0.04, 0.23, "FB lead pistol", [], ["power"]),
    Formation("Pistol Outside Zone", "11", "3 WR, 1 RB, outside zone from pistol", 0.42, 0.32, 0.06, 0.20, "Outside zone pistol", [], ["zone"]),

    # ── Singleback Extended ───────────────────────────────────────────
    Formation("Singleback Y-Iso", "12", "2 WR, TE, 1 RB ISO run", 0.45, 0.32, 0.05, 0.18, "Y-Iso singleback", [], ["power"]),
    Formation("Singleback Inside Zone", "11", "3 WR, 1 RB inside zone", 0.38, 0.40, 0.06, 0.16, "Inside zone singleback", [], ["zone"]),
    Formation("Singleback Outside Zone", "11", "3 WR, 1 RB outside zone", 0.35, 0.42, 0.06, 0.17, "Outside zone singleback", [], ["zone"]),
    Formation("Singleback Power", "12", "2 WR, TE, 1 RB power run", 0.45, 0.30, 0.05, 0.20, "Power singleback", [], ["power"]),
    Formation("Singleback Slot Cross", "11", "3 WR, slot crossing, 1 RB", 0.18, 0.62, 0.10, 0.10, "Slot cross concept", [], ["passing"]),
    Formation("Singleback TE Screen", "12", "2 WR, TE screen, 1 RB", 0.08, 0.20, 0.62, 0.10, "TE screen singleback", [], ["screen"]),
    Formation("Singleback Four Verts", "11", "4 WR, 1 RB, four verticals", 0.08, 0.78, 0.06, 0.08, "Four verticals", [], ["passing", "deep"]),
    Formation("Singleback Mesh", "11", "3 WR, mesh crossing, 1 RB", 0.12, 0.68, 0.12, 0.08, "Mesh concept", [], ["passing"]),

    # ── Red Zone Specific ─────────────────────────────────────────────
    Formation("Red Zone Trips", "11", "Trips WR, 1 RB, inside 20", 0.18, 0.62, 0.10, 0.10, "Red zone trips", [], ["red-zone", "passing"]),
    Formation("Red Zone Bunch", "11", "Bunch WR, 1 RB, inside 20", 0.15, 0.62, 0.15, 0.08, "Red zone bunch", [], ["red-zone", "bunch"]),
    Formation("Red Zone Heavy", "22", "2 TE, FB, RB, inside 20", 0.55, 0.18, 0.03, 0.24, "Red zone heavy", [], ["red-zone", "power"]),
    Formation("Red Zone Fade Split", "11", "4 WR in fade positions, inside 10", 0.10, 0.78, 0.04, 0.08, "Red zone fades", [], ["red-zone", "passing"]),
    Formation("Red Zone Speed Out", "11", "4 WR, speed outs, inside 10", 0.08, 0.80, 0.06, 0.06, "Red zone quick outs", [], ["red-zone", "passing"]),
    Formation("Red Zone TE Flat", "12", "2 WR, TE flat route, inside 15", 0.20, 0.55, 0.10, 0.15, "Red zone TE flat", [], ["red-zone"]),

    # ── Third Down Specific ───────────────────────────────────────────
    Formation("3rd & Long Empty", "10", "5 WR, empty, 3rd and long", 0.03, 0.82, 0.12, 0.03, "3rd & long empty", [], ["third-down", "passing"]),
    Formation("3rd & Long Spread", "11", "4 WR, 1 RB, 3rd and long", 0.10, 0.72, 0.10, 0.08, "3rd & long spread", [], ["third-down", "passing"]),
    Formation("3rd & Short Jumbo", "23", "3 TE, 2 RB, 3rd and short", 0.70, 0.10, 0.02, 0.18, "3rd & short heavy", [], ["third-down", "short-yardage"]),
    Formation("3rd & Medium Trips", "11", "Trips WR, 1 RB, 3rd and medium", 0.15, 0.65, 0.10, 0.10, "3rd & medium trips", [], ["third-down"]),
    Formation("3rd & Short Power I", "22", "I-form, 2 TE, 3rd and short", 0.60, 0.15, 0.03, 0.22, "3rd & short power I", [], ["third-down", "short-yardage"]),
    Formation("4th & Short Sneak", "22", "QB sneak formation, 4th and short", 0.80, 0.08, 0.01, 0.11, "4th & short sneak", [], ["fourth-down", "sneak"]),
    Formation("4th & Long Desperation", "10", "5 WR, 4th and long", 0.02, 0.85, 0.10, 0.03, "4th & long empty", [], ["fourth-down", "passing"]),

    # ── Two-Minute Drill ──────────────────────────────────────────────
    Formation("2-Min Spread", "11", "4 WR, 1 RB, hurry up", 0.12, 0.70, 0.10, 0.08, "Two-minute spread", [], ["2-minute", "no-huddle"]),
    Formation("2-Min Trips", "11", "Trips WR, 1 RB, hurry up", 0.10, 0.72, 0.10, 0.08, "Two-minute trips", [], ["2-minute", "no-huddle"]),
    Formation("2-Min Empty", "10", "5 WR, no huddle, clock management", 0.03, 0.82, 0.12, 0.03, "Two-minute empty", [], ["2-minute", "no-huddle"]),
    Formation("2-Min Sideline", "11", "4 WR, sideline routes, clock stop", 0.05, 0.82, 0.08, 0.05, "Two-minute sideline", [], ["2-minute"]),
    Formation("Kill Clock Run", "22", "2 TE, FB, RB, run out clock", 0.75, 0.10, 0.02, 0.13, "Clock-killing run", [], ["clock-management"]),
    Formation("Victory Formation", "22", "QB kneel, 2 TE, FB, RB", 0.95, 0.02, 0.01, 0.02, "Victory kneel", [], ["clock-management"]),

    # ── Condensed / Jumbo Extended ────────────────────────────────────
    Formation("Jumbo 6 OL", "23", "6 OL, 2 TE, FB, RB, 0 WR", 0.80, 0.05, 0.01, 0.14, "6 OL heavy package", [], ["heavy", "goal-line"]),
    Formation("Jumbo TE Eligible", "23", "6 OL, TE eligible report, 2 RB", 0.50, 0.30, 0.02, 0.18, "Eligible TE trick", [], ["heavy", "trick"]),
    Formation("Extra OL Right Wing", "13", "Extra OL as wing right, 3 TE, 1 RB", 0.65, 0.12, 0.02, 0.21, "Extra OL wing right", [], ["heavy", "power"]),
    Formation("Extra OL Left Wing", "13", "Extra OL as wing left, 3 TE, 1 RB", 0.65, 0.12, 0.02, 0.21, "Extra OL wing left", [], ["heavy", "power"]),

    # ── Bunch Extended ────────────────────────────────────────────────
    Formation("Bunch Wing Right", "12", "2 WR + TE bunched right with wing, 1 RB", 0.25, 0.52, 0.13, 0.10, "Bunch wing right", [], ["bunch", "power"]),
    Formation("Bunch Wing Left", "12", "2 WR + TE bunched left with wing, 1 RB", 0.25, 0.52, 0.13, 0.10, "Bunch wing left", [], ["bunch", "power"]),
    Formation("Bunch Slot Right", "11", "3 WR bunch from slot right, 1 RB", 0.12, 0.68, 0.14, 0.06, "Bunch from slot right", [], ["bunch"]),
    Formation("Bunch Return Motion", "11", "Bunch with motion man returning, 1 RB", 0.15, 0.62, 0.13, 0.10, "Bunch with motion return", [], ["bunch", "motion"]),

    # ── Stack Variations ──────────────────────────────────────────────
    Formation("Stack Left", "11", "2 WR stacked left, 2 WR right, 1 RB", 0.18, 0.62, 0.12, 0.08, "Left stack", [], ["stack"]),
    Formation("Double Stack", "11", "2 WR stacked each side, 1 RB", 0.15, 0.64, 0.13, 0.08, "Double stack pick routes", [], ["stack"]),
    Formation("Stack Empty", "10", "Stacked receivers, no RB", 0.03, 0.80, 0.14, 0.03, "Stack empty", [], ["stack", "empty"]),
    Formation("Stack TE Right", "12", "2 WR stacked + TE right, 1 WR left, 1 RB", 0.28, 0.48, 0.10, 0.14, "Stack with TE right", [], ["stack"]),

    # ── Flex / Detached TE Variants ───────────────────────────────────
    Formation("Flex TE Right Slot", "12", "2 WR, TE in right slot, 1 RB", 0.22, 0.55, 0.10, 0.13, "TE as slot right", [], ["flex", "mismatch"]),
    Formation("Flex TE Left Slot", "12", "2 WR, TE in left slot, 1 RB", 0.22, 0.55, 0.10, 0.13, "TE as slot left", [], ["flex", "mismatch"]),
    Formation("Flex TE Wide Right", "12", "2 WR, TE split wide right, 1 RB", 0.18, 0.58, 0.10, 0.14, "TE as wide receiver right", [], ["flex", "mismatch"]),
    Formation("Flex TE Wide Left", "12", "2 WR, TE split wide left, 1 RB", 0.18, 0.58, 0.10, 0.14, "TE as wide receiver left", [], ["flex", "mismatch"]),
    Formation("Flex Doubles TE", "12", "2 WR doubled with detached TE, 1 RB", 0.25, 0.52, 0.08, 0.15, "Doubled TE flex", [], ["flex"]),

    # ── Compressed Red Zone ───────────────────────────────────────────
    Formation("RZ Fade Corner", "11", "4 WR, fade/corner combo, 1 RB", 0.10, 0.78, 0.04, 0.08, "Red zone fade corner", [], ["red-zone", "passing"]),
    Formation("RZ Flat Wheel", "12", "TE flat, RB wheel, 2 WR", 0.15, 0.58, 0.12, 0.15, "Flat wheel combo", [], ["red-zone"]),
    Formation("RZ Levels", "11", "3 WR levels concept, 1 RB", 0.12, 0.68, 0.08, 0.12, "Red zone levels", [], ["red-zone", "passing"]),
    Formation("RZ TE Seam", "12", "TE seam route, 2 WR, 1 RB", 0.18, 0.55, 0.08, 0.19, "TE seam red zone", [], ["red-zone"]),

    # ── Motion Package Extended ───────────────────────────────────────
    Formation("Fly Motion Left", "11", "WR fly motion left, any base", 0.35, 0.42, 0.08, 0.15, "Fly sweep left", [], ["motion"]),
    Formation("Fly Motion Right", "11", "WR fly motion right, any base", 0.35, 0.42, 0.08, 0.15, "Fly sweep right", [], ["motion"]),
    Formation("RB Motion to Flat", "11", "RB motioning out to flat", 0.12, 0.48, 0.30, 0.10, "RB flat motion", [], ["motion", "screen"]),
    Formation("TE Motion to Wing", "12", "TE motioning to wing position", 0.40, 0.32, 0.05, 0.23, "TE wing motion", [], ["motion", "power"]),
    Formation("WR Motion to Bunch", "11", "WR motioning into bunch", 0.12, 0.65, 0.15, 0.08, "Motion to bunch", [], ["motion", "bunch"]),
    Formation("Double Motion", "11", "Two players in motion simultaneously", 0.25, 0.50, 0.10, 0.15, "Double motion package", [], ["motion", "trick"]),
    Formation("Motion Check RPO", "11", "Motion to diagnose coverage, RPO", 0.32, 0.42, 0.10, 0.16, "Motion check RPO", [], ["motion", "RPO"]),

    # ── Personnel Mismatch Specials ───────────────────────────────────
    Formation("RB as WR Split", "11", "RB split out as WR, 3 WR, backup RB", 0.15, 0.68, 0.10, 0.07, "RB as WR mismatch", [], ["mismatch"]),
    Formation("TE as Flanker", "12", "TE split as flanker, 2 WR, 1 RB", 0.20, 0.58, 0.08, 0.14, "TE flanker mismatch", [], ["mismatch"]),
    Formation("6 DB Set", "10", "6 DBs on field, empty look", 0.03, 0.82, 0.12, 0.03, "6 DB speed package", [], ["mismatch", "speed"]),
    Formation("3 RB Formation", "30", "3 RBs, 2 WR", 0.55, 0.22, 0.05, 0.18, "Triple RB set", [], ["trick", "power"]),
    Formation("3 TE Wing Right", "13", "3 TE wing right, 1 WR, 1 RB", 0.58, 0.18, 0.02, 0.22, "Triple TE wing right", [], ["power", "heavy"]),
    Formation("3 TE Wing Left", "13", "3 TE wing left, 1 WR, 1 RB", 0.58, 0.18, 0.02, 0.22, "Triple TE wing left", [], ["power", "heavy"]),

    # ── Passing Concept Formations ────────────────────────────────────
    Formation("Four Verticals Spread", "11", "4 WR on go routes, 1 RB check", 0.05, 0.82, 0.05, 0.08, "Four verticals", [], ["passing", "deep"]),
    Formation("Smash Concept Right", "11", "Hitch/corner combo right, 3 WR, 1 RB", 0.10, 0.72, 0.08, 0.10, "Smash right", [], ["passing"]),
    Formation("Smash Concept Left", "11", "Hitch/corner combo left, 3 WR, 1 RB", 0.10, 0.72, 0.08, 0.10, "Smash left", [], ["passing"]),
    Formation("Curl-Flat Combo", "11", "Curl/flat route combo, 3 WR, 1 RB", 0.12, 0.65, 0.12, 0.11, "Curl flat", [], ["passing"]),
    Formation("Post-Wheel Combo", "11", "Post/wheel route combo, 3 WR, 1 RB", 0.08, 0.75, 0.05, 0.12, "Post wheel deep", [], ["passing", "deep"]),
    Formation("Dig-Out Combo", "11", "Dig/out route combo, 3 WR, 1 RB", 0.10, 0.70, 0.10, 0.10, "Dig out combo", [], ["passing"]),
    Formation("Sail Concept", "12", "TE/WR sail vertical stretch, 2 WR, 1 RB", 0.12, 0.62, 0.08, 0.18, "Sail concept", [], ["passing"]),
    Formation("Drive Concept", "11", "Shallow cross/dig combo, 3 WR, 1 RB", 0.10, 0.68, 0.12, 0.10, "Drive crossing", [], ["passing"]),
    Formation("Mills Concept", "11", "Post/dig combo, 3 WR, 1 RB", 0.08, 0.74, 0.06, 0.12, "Mills concept", [], ["passing", "deep"]),
    Formation("Scissors Concept", "11", "Corner/post scissors, 3 WR, 1 RB", 0.08, 0.76, 0.06, 0.10, "Scissors routes", [], ["passing", "deep"]),
]

_INDEX: dict[str, Formation] = {f.name.lower(): f for f in FORMATIONS}
_TAG_INDEX: dict[str, list[Formation]] = {}
for _f in FORMATIONS:
    for _t in _f.tags:
        _TAG_INDEX.setdefault(_t, []).append(_f)


def get_formation(name: str) -> Formation | None:
    return _INDEX.get(name.lower())


def search_formations(query: str) -> list[Formation]:
    q = query.lower()
    results = []
    for f in FORMATIONS:
        if q in f.name.lower() or q in f.alignment.lower() or q in f.description.lower() or q in f.personnel:
            results.append(f)
    if not results:
        for tag, fms in _TAG_INDEX.items():
            if q in tag:
                results.extend(fms)
    seen = set()
    unique = []
    for r in results:
        if r.name not in seen:
            seen.add(r.name)
            unique.append(r)
    return unique


def formation_tendencies(name: str) -> dict | None:
    f = get_formation(name)
    if not f:
        return None
    return {
        "name": f.name,
        "personnel": f.personnel,
        "alignment": f.alignment,
        "tendencies": {
            "run": f.run_tendency,
            "pass": f.pass_tendency,
            "screen": f.screen_tendency,
            "play_action": f.play_action_tendency,
        },
        "tags": f.tags,
        "description": f.description,
    }


def list_all_formations() -> list[dict]:
    return [
        {
            "name": f.name,
            "personnel": f.personnel,
            "alignment": f.alignment,
            "tags": f.tags,
        }
        for f in FORMATIONS
    ]


def formations_by_tag(tag: str) -> list[Formation]:
    return _TAG_INDEX.get(tag.lower(), [])


def formations_by_personnel(personnel: str) -> list[Formation]:
    return [f for f in FORMATIONS if f.personnel == personnel]
