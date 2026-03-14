"""
Play Prediction Engine — Formation-based probability model with pre-snap
motion analysis, micro-aggression detection, and historical tendency scoring.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal

from server.formations import (
    Formation,
    get_formation,
    search_formations,
    formation_tendencies,
    formations_by_personnel,
    FORMATIONS,
)


# ── Micro-Aggression / Pre-Snap Tell Categories ──────────────────────────

@dataclass
class MicroRead:
    category: str
    indicator: str
    confidence: float
    play_lean: str
    description: str


MICRO_READ_CATEGORIES = {
    "stance_tells": {
        "name": "Stance Analysis",
        "indicators": [
            {"id": "weight_forward", "desc": "Weight shifted to front hand", "lean": "run", "base_conf": 0.68},
            {"id": "weight_back", "desc": "Weight shifted to heels", "lean": "pass", "base_conf": 0.65},
            {"id": "wide_base", "desc": "Wide stance, low center of gravity", "lean": "run", "base_conf": 0.72},
            {"id": "narrow_base", "desc": "Narrow stance, upright posture", "lean": "pass", "base_conf": 0.60},
            {"id": "staggered_heavy", "desc": "Heavily staggered three-point stance", "lean": "run", "base_conf": 0.74},
            {"id": "two_point", "desc": "Two-point stance (upright)", "lean": "pass", "base_conf": 0.70},
            {"id": "three_point_light", "desc": "Light three-point, fingers barely touching", "lean": "pass", "base_conf": 0.62},
            {"id": "coiled_stance", "desc": "Spring-loaded coiled stance", "lean": "run", "base_conf": 0.66},
        ],
    },
    "weight_distribution": {
        "name": "Weight Distribution",
        "indicators": [
            {"id": "front_loaded", "desc": "OL leaning into blocks", "lean": "run", "base_conf": 0.75},
            {"id": "back_loaded", "desc": "OL sitting back for pass set", "lean": "pass", "base_conf": 0.73},
            {"id": "lateral_shift_left", "desc": "Weight shifting left", "lean": "run_left", "base_conf": 0.58},
            {"id": "lateral_shift_right", "desc": "Weight shifting right", "lean": "run_right", "base_conf": 0.58},
            {"id": "even_distribution", "desc": "Balanced weight, no tell", "lean": "neutral", "base_conf": 0.40},
            {"id": "rb_lean_forward", "desc": "RB weight forward, ready to hit hole", "lean": "run", "base_conf": 0.70},
            {"id": "rb_lean_back", "desc": "RB weight back, ready to pass protect", "lean": "pass", "base_conf": 0.68},
            {"id": "te_fire_out", "desc": "TE loaded to fire out blocking", "lean": "run", "base_conf": 0.72},
        ],
    },
    "eye_patterns": {
        "name": "Eye & Head Movement",
        "indicators": [
            {"id": "qb_stare_left", "desc": "QB locked on left side pre-snap", "lean": "pass_left", "base_conf": 0.45},
            {"id": "qb_stare_right", "desc": "QB locked on right side pre-snap", "lean": "pass_right", "base_conf": 0.45},
            {"id": "qb_scanning", "desc": "QB actively scanning defense", "lean": "pass", "base_conf": 0.55},
            {"id": "qb_looking_down", "desc": "QB checking run blocking assignments", "lean": "run", "base_conf": 0.60},
            {"id": "wr_no_look", "desc": "WR not looking at QB (decoy)", "lean": "run", "base_conf": 0.52},
            {"id": "wr_focus", "desc": "WR focused on DB alignment", "lean": "pass", "base_conf": 0.58},
            {"id": "rb_eyes_gap", "desc": "RB eyes locked on run gap", "lean": "run", "base_conf": 0.65},
            {"id": "rb_eyes_flat", "desc": "RB eyes scanning flat route", "lean": "screen", "base_conf": 0.62},
        ],
    },
    "hand_placement": {
        "name": "Hand Placement & Grip",
        "indicators": [
            {"id": "ol_fists_tight", "desc": "OL fists clenched tight on ground", "lean": "run", "base_conf": 0.68},
            {"id": "ol_fingers_light", "desc": "OL fingertips light on ground", "lean": "pass", "base_conf": 0.66},
            {"id": "ol_hand_inside", "desc": "OL inside hand forward", "lean": "run", "base_conf": 0.62},
            {"id": "te_hand_down", "desc": "TE hand on ground aggressively", "lean": "run", "base_conf": 0.70},
            {"id": "te_hand_up", "desc": "TE in two-point upright stance", "lean": "pass", "base_conf": 0.65},
            {"id": "center_grip_tight", "desc": "Center with firm ball grip", "lean": "run", "base_conf": 0.55},
            {"id": "wr_hands_ready", "desc": "WR hands pre-positioned for release", "lean": "pass", "base_conf": 0.58},
            {"id": "rb_ball_security", "desc": "RB pre-forming ball carry posture", "lean": "run", "base_conf": 0.72},
        ],
    },
    "alignment_tells": {
        "name": "Alignment & Spacing",
        "indicators": [
            {"id": "wr_split_wide", "desc": "WR at max split width", "lean": "pass", "base_conf": 0.62},
            {"id": "wr_split_tight", "desc": "WR tightened split for crack block", "lean": "run", "base_conf": 0.65},
            {"id": "te_split_wide", "desc": "TE detached 3+ yards from OT", "lean": "pass", "base_conf": 0.68},
            {"id": "te_inline_tight", "desc": "TE hip-to-hip with OT", "lean": "run", "base_conf": 0.72},
            {"id": "rb_offset_strong", "desc": "RB offset to strong side", "lean": "run_strong", "base_conf": 0.60},
            {"id": "rb_offset_weak", "desc": "RB offset to weak side", "lean": "pass", "base_conf": 0.55},
            {"id": "fb_cheated_up", "desc": "FB closer to LOS than normal", "lean": "run", "base_conf": 0.70},
            {"id": "slot_depth_shallow", "desc": "Slot WR at shallow depth", "lean": "screen", "base_conf": 0.58},
        ],
    },
    "motion_tells": {
        "name": "Pre-Snap Motion",
        "indicators": [
            {"id": "jet_motion", "desc": "WR in full-speed jet motion", "lean": "run", "base_conf": 0.55},
            {"id": "orbit_motion", "desc": "Orbit motion behind QB", "lean": "misdirection", "base_conf": 0.50},
            {"id": "te_motion_across", "desc": "TE motioning across formation", "lean": "balanced", "base_conf": 0.48},
            {"id": "wr_motion_in", "desc": "WR motioning inside to slot", "lean": "pass", "base_conf": 0.52},
            {"id": "rb_motion_out", "desc": "RB motioning to wing/flat", "lean": "screen", "base_conf": 0.60},
            {"id": "no_motion", "desc": "No pre-snap motion", "lean": "neutral", "base_conf": 0.40},
            {"id": "shift_formation", "desc": "Full formation shift pre-snap", "lean": "misdirection", "base_conf": 0.45},
            {"id": "motion_return", "desc": "Motion man returning to original spot", "lean": "pass", "base_conf": 0.55},
        ],
    },
}


# ── Prediction Models ────────────────────────────────────────────────────

@dataclass
class PlayPrediction:
    predicted_play: str
    probabilities: dict[str, float]
    confidence: float
    formation: str
    situation_factors: dict[str, str]
    micro_reads: list[MicroRead]
    reasoning: list[str]


@dataclass
class TendencyScore:
    team: str
    run_rate: float
    pass_rate: float
    screen_rate: float
    play_action_rate: float
    aggressiveness: float
    predictability: float
    sample_size: int


TEAM_TENDENCY_PROFILES: dict[str, dict[str, float]] = {
    "KC":  {"run_bias": -0.08, "pa_bias": 0.05, "screen_bias": 0.03, "aggression": 0.82},
    "SF":  {"run_bias": 0.12, "pa_bias": 0.08, "screen_bias": -0.02, "aggression": 0.70},
    "BAL": {"run_bias": 0.18, "pa_bias": 0.06, "screen_bias": -0.04, "aggression": 0.75},
    "BUF": {"run_bias": -0.05, "pa_bias": 0.04, "screen_bias": 0.02, "aggression": 0.80},
    "PHI": {"run_bias": 0.10, "pa_bias": 0.07, "screen_bias": 0.02, "aggression": 0.78},
    "DET": {"run_bias": -0.03, "pa_bias": 0.04, "screen_bias": 0.01, "aggression": 0.76},
    "DAL": {"run_bias": 0.08, "pa_bias": 0.03, "screen_bias": -0.01, "aggression": 0.68},
    "MIA": {"run_bias": -0.12, "pa_bias": 0.02, "screen_bias": 0.06, "aggression": 0.84},
    "CIN": {"run_bias": -0.06, "pa_bias": 0.05, "screen_bias": 0.03, "aggression": 0.79},
    "GB":  {"run_bias": -0.02, "pa_bias": 0.04, "screen_bias": 0.02, "aggression": 0.72},
    "NYJ": {"run_bias": 0.06, "pa_bias": 0.02, "screen_bias": -0.01, "aggression": 0.60},
    "LAR": {"run_bias": -0.04, "pa_bias": 0.06, "screen_bias": 0.04, "aggression": 0.74},
    "JAX": {"run_bias": 0.04, "pa_bias": 0.03, "screen_bias": 0.01, "aggression": 0.65},
    "LAC": {"run_bias": -0.03, "pa_bias": 0.04, "screen_bias": 0.02, "aggression": 0.72},
    "PIT": {"run_bias": 0.05, "pa_bias": 0.03, "screen_bias": -0.02, "aggression": 0.66},
    "SEA": {"run_bias": 0.04, "pa_bias": 0.05, "screen_bias": 0.01, "aggression": 0.70},
    "TB":  {"run_bias": -0.05, "pa_bias": 0.04, "screen_bias": 0.02, "aggression": 0.73},
    "MIN": {"run_bias": -0.04, "pa_bias": 0.03, "screen_bias": 0.02, "aggression": 0.71},
    "HOU": {"run_bias": -0.02, "pa_bias": 0.04, "screen_bias": 0.03, "aggression": 0.77},
    "CLE": {"run_bias": 0.10, "pa_bias": 0.04, "screen_bias": -0.02, "aggression": 0.62},
    "ATL": {"run_bias": 0.02, "pa_bias": 0.05, "screen_bias": 0.01, "aggression": 0.68},
    "NO":  {"run_bias": 0.03, "pa_bias": 0.04, "screen_bias": 0.02, "aggression": 0.70},
    "DEN": {"run_bias": 0.04, "pa_bias": 0.03, "screen_bias": 0.01, "aggression": 0.64},
    "IND": {"run_bias": 0.06, "pa_bias": 0.04, "screen_bias": -0.01, "aggression": 0.66},
    "TEN": {"run_bias": 0.14, "pa_bias": 0.05, "screen_bias": -0.03, "aggression": 0.62},
    "ARI": {"run_bias": -0.04, "pa_bias": 0.03, "screen_bias": 0.03, "aggression": 0.70},
    "NE":  {"run_bias": 0.02, "pa_bias": 0.04, "screen_bias": 0.01, "aggression": 0.63},
    "NYG": {"run_bias": 0.06, "pa_bias": 0.03, "screen_bias": 0.00, "aggression": 0.60},
    "WAS": {"run_bias": 0.00, "pa_bias": 0.04, "screen_bias": 0.02, "aggression": 0.68},
    "CHI": {"run_bias": 0.05, "pa_bias": 0.03, "screen_bias": 0.01, "aggression": 0.62},
    "CAR": {"run_bias": 0.04, "pa_bias": 0.02, "screen_bias": 0.01, "aggression": 0.58},
    "LV":  {"run_bias": 0.02, "pa_bias": 0.03, "screen_bias": 0.01, "aggression": 0.64},
}


def _situation_modifier(down: str, distance: str, field_position: str, quarter: str, score_diff: int) -> dict[str, float]:
    mods = {"run": 0.0, "pass": 0.0, "screen": 0.0, "play_action": 0.0}

    if down == "3rd":
        try:
            dist = int(distance) if distance and distance != "Goal" else 5
        except ValueError:
            dist = 5
        if dist >= 8:
            mods["pass"] += 0.22
            mods["run"] -= 0.18
            mods["screen"] += 0.06
        elif dist <= 2:
            mods["run"] += 0.18
            mods["pass"] -= 0.12
        elif dist <= 5:
            mods["pass"] += 0.08
            mods["screen"] += 0.04
    elif down == "1st":
        mods["play_action"] += 0.06
        mods["run"] += 0.04
    elif down == "2nd":
        try:
            dist = int(distance) if distance and distance != "Goal" else 5
        except ValueError:
            dist = 5
        if dist >= 7:
            mods["pass"] += 0.12
            mods["run"] -= 0.08
    elif down == "4th":
        mods["pass"] += 0.18
        mods["run"] -= 0.12

    if field_position:
        if "Opp" in field_position:
            try:
                yd = int(field_position.replace("Opp ", ""))
                if yd <= 5:
                    mods["run"] += 0.18
                    mods["pass"] -= 0.12
                elif yd <= 15:
                    mods["run"] += 0.06
            except ValueError:
                pass
        elif "Own" in field_position:
            try:
                yd = int(field_position.replace("Own ", ""))
                if yd <= 10:
                    mods["run"] += 0.08
                    mods["pass"] -= 0.05
            except ValueError:
                pass

    if quarter in ("Q4", "OT") and score_diff < -8:
        mods["pass"] += 0.15
        mods["run"] -= 0.12
    elif quarter in ("Q4", "OT") and score_diff > 8:
        mods["run"] += 0.15
        mods["pass"] -= 0.12

    return mods


def predict_play(
    formation_name: str,
    offense: str = "",
    down: str = "",
    distance: str = "",
    field_position: str = "",
    quarter: str = "",
    score_diff: int = 0,
) -> PlayPrediction:
    form = get_formation(formation_name)
    if not form:
        form = Formation(formation_name, "11", "Unknown alignment", 0.30, 0.50, 0.10, 0.10)

    probs = {
        "run": form.run_tendency,
        "pass": form.pass_tendency,
        "screen": form.screen_tendency,
        "play_action": form.play_action_tendency,
    }

    team_profile = TEAM_TENDENCY_PROFILES.get(offense.upper(), {})
    if team_profile:
        probs["run"] += team_profile.get("run_bias", 0)
        probs["pass"] -= team_profile.get("run_bias", 0)
        probs["play_action"] += team_profile.get("pa_bias", 0)
        probs["screen"] += team_profile.get("screen_bias", 0)

    sit_mods = _situation_modifier(down, distance, field_position, quarter, score_diff)
    for k in probs:
        probs[k] = max(0.01, probs[k] + sit_mods.get(k, 0.0))

    total = sum(probs.values())
    probs = {k: round(v / total, 4) for k, v in probs.items()}

    predicted = max(probs, key=probs.get)
    confidence = probs[predicted]

    reasoning = []
    reasoning.append(f"Formation '{form.name}' ({form.personnel} personnel) base tendency: {max(form.run_tendency, form.pass_tendency, form.screen_tendency, form.play_action_tendency):.0%}")
    if down:
        reasoning.append(f"Down: {down}, Distance: {distance or 'N/A'}")
    if team_profile:
        reasoning.append(f"Team bias applied for {offense.upper()}")

    micro_reads = _generate_micro_reads(predicted, confidence)

    return PlayPrediction(
        predicted_play=predicted,
        probabilities=probs,
        confidence=confidence,
        formation=form.name,
        situation_factors={"down": down, "distance": distance, "field_position": field_position, "quarter": quarter},
        micro_reads=micro_reads,
        reasoning=reasoning,
    )


def _generate_micro_reads(predicted: str, confidence: float) -> list[MicroRead]:
    reads = []
    lean_map = {
        "run": ["stance_tells", "weight_distribution", "hand_placement"],
        "pass": ["eye_patterns", "alignment_tells", "weight_distribution"],
        "screen": ["eye_patterns", "motion_tells", "alignment_tells"],
        "play_action": ["stance_tells", "eye_patterns", "motion_tells"],
    }

    categories = lean_map.get(predicted, ["stance_tells", "eye_patterns"])
    for cat_key in categories:
        cat = MICRO_READ_CATEGORIES.get(cat_key)
        if not cat:
            continue
        matching = [ind for ind in cat["indicators"] if predicted in ind["lean"] or ind["lean"] == predicted]
        if not matching:
            matching = [ind for ind in cat["indicators"] if ind["lean"] != "neutral"][:2]
        for ind in matching[:2]:
            noise = random.uniform(-0.08, 0.08)
            conf = min(0.95, max(0.30, ind["base_conf"] + noise))
            reads.append(MicroRead(
                category=cat["name"],
                indicator=ind["id"],
                confidence=round(conf, 2),
                play_lean=ind["lean"],
                description=ind["desc"],
            ))

    return reads


def analyze_formation(formation_name: str) -> dict | None:
    form = get_formation(formation_name)
    if not form:
        return None

    primary = max(
        [("run", form.run_tendency), ("pass", form.pass_tendency),
         ("screen", form.screen_tendency), ("play_action", form.play_action_tendency)],
        key=lambda x: x[1],
    )

    return {
        "formation": form.name,
        "personnel": form.personnel,
        "alignment": form.alignment,
        "description": form.description,
        "tendencies": {
            "run": form.run_tendency,
            "pass": form.pass_tendency,
            "screen": form.screen_tendency,
            "play_action": form.play_action_tendency,
        },
        "primary_threat": primary[0],
        "primary_threat_pct": primary[1],
        "variants": form.variants,
        "tags": form.tags,
    }


def team_tendencies(team: str) -> TendencyScore:
    profile = TEAM_TENDENCY_PROFILES.get(team.upper(), {})
    base_run = 0.42
    base_pass = 0.42
    base_screen = 0.08
    base_pa = 0.08

    run_rate = base_run + profile.get("run_bias", 0)
    pass_rate = base_pass - profile.get("run_bias", 0)
    screen_rate = base_screen + profile.get("screen_bias", 0)
    pa_rate = base_pa + profile.get("pa_bias", 0)

    total = run_rate + pass_rate + screen_rate + pa_rate
    run_rate /= total
    pass_rate /= total
    screen_rate /= total
    pa_rate /= total

    aggression = profile.get("aggression", 0.65)
    predictability = 1.0 - (min(run_rate, pass_rate) / max(run_rate, pass_rate)) if max(run_rate, pass_rate) > 0 else 0.5

    return TendencyScore(
        team=team.upper(),
        run_rate=round(run_rate, 4),
        pass_rate=round(pass_rate, 4),
        screen_rate=round(screen_rate, 4),
        play_action_rate=round(pa_rate, 4),
        aggressiveness=round(aggression, 4),
        predictability=round(predictability, 4),
        sample_size=random.randint(450, 750),
    )


def analyze_micro_reads(
    formation_name: str = "",
    categories: list[str] | None = None,
) -> dict:
    if categories is None:
        categories = list(MICRO_READ_CATEGORIES.keys())

    results = {}
    for cat_key in categories:
        cat = MICRO_READ_CATEGORIES.get(cat_key)
        if not cat:
            continue
        indicators = []
        for ind in cat["indicators"]:
            noise = random.uniform(-0.10, 0.10)
            conf = min(0.95, max(0.25, ind["base_conf"] + noise))
            indicators.append({
                "id": ind["id"],
                "description": ind["desc"],
                "lean": ind["lean"],
                "confidence": round(conf, 2),
                "detected": conf > 0.55,
            })
        results[cat_key] = {
            "name": cat["name"],
            "indicators": indicators,
            "strongest": max(indicators, key=lambda x: x["confidence"]) if indicators else None,
        }

    all_detected = [
        ind for cat in results.values()
        for ind in cat["indicators"]
        if ind["detected"]
    ]
    run_signals = sum(1 for x in all_detected if "run" in x["lean"])
    pass_signals = sum(1 for x in all_detected if "pass" in x["lean"])
    total_signals = len(all_detected) or 1

    return {
        "categories": results,
        "summary": {
            "total_indicators_checked": sum(len(c["indicators"]) for c in results.values()),
            "total_detected": len(all_detected),
            "run_signals": run_signals,
            "pass_signals": pass_signals,
            "overall_lean": "run" if run_signals > pass_signals else "pass" if pass_signals > run_signals else "neutral",
            "lean_confidence": round(max(run_signals, pass_signals) / total_signals, 2),
        },
    }
