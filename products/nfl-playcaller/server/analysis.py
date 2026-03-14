import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from products._shared.ai_engine import AIEngine
from .teams import get_team, get_team_stats

SYSTEM_PROMPT = (
    "You are an elite NFL offensive coordinator and defensive analyst AI with deep "
    "knowledge of every NFL team's scheme, personnel, and tendencies from 2021-2025. "
    "You provide analysis at a professional coaching staff level. Use specific player "
    "names, formation tendencies, and statistical context. Format output with clear "
    "headers and structured sections. Be probabilistic — use percentages and confidence "
    "levels. Think one step ahead and factor in how the defense adjusts. When recommending "
    "plays, stay within the team's actual schematic framework."
)


class AnalysisEngine:
    def __init__(self):
        self.ai = AIEngine(default_system=SYSTEM_PROMPT)

    def build_prompt(self, analysis_type: str, params: dict) -> str:
        off_abbr = params.get("offense", "")
        def_abbr = params.get("defense", "")
        off_team = get_team(off_abbr)
        def_team = get_team(def_abbr)
        off = off_team["name"] if off_team else "Offense"
        defen = def_team["name"] if def_team else "Defense"

        off_stats = get_team_stats(off_abbr)
        def_stats = get_team_stats(def_abbr)

        down = params.get("down", "")
        distance = params.get("distance", "")
        field_pos = params.get("field_position", "")
        quarter = params.get("quarter", "")
        score = params.get("score", "")
        def_look = params.get("defensive_look", "")
        notes = params.get("notes", "")
        player_name = params.get("player_name", "")

        tendency_ctx = (
            f"\n\nTENDENCY DATA:\n"
            f"{off} offense — run/pass ratio: {off_stats['run_pass']:.0%}/{1 - off_stats['run_pass']:.0%}, "
            f"tempo: {off_stats['tempo']}\n"
            f"{defen} defense — blitz rate: {def_stats['blitz_rate']:.0%}, "
            f"coverage base: {def_stats['coverage_base']}, tempo: {def_stats['tempo']}"
        )

        builders = {
            "scouting": self._build_scouting,
            "playcall": self._build_playcall,
            "blitz": self._build_blitz,
            "player": self._build_player,
            "playbook": self._build_playbook,
            "postgame": self._build_postgame,
        }
        builder = builders.get(analysis_type, self._build_scouting)
        return builder(
            off=off, defen=defen, tendency_ctx=tendency_ctx,
            down=down, distance=distance, field_pos=field_pos,
            quarter=quarter, score=score, def_look=def_look,
            notes=notes, player_name=player_name,
        )

    def _build_scouting(self, *, off, defen, tendency_ctx, **_) -> str:
        return (
            f"Generate a comprehensive NFL pre-game scouting report for {off} (offense) "
            f"vs {defen} (defense). Cover: offensive tendencies and key playmakers, "
            f"defensive scheme and blitz tendencies, head-to-head matchup advantages, "
            f"recommended game plans for both sides, and situational strategy (red zone, "
            f"3rd down, 2-minute). Use the last 5 years of data to identify patterns. "
            f"Include probability breakdowns for blitz rates and coverage tendencies."
            f"{tendency_ctx}"
        )

    def _build_playcall(self, *, off, defen, tendency_ctx,
                        down, distance, field_pos, quarter, score,
                        def_look, notes, **_) -> str:
        lines = [f"NFL situational play call analysis:", "", f"OFFENSE: {off}", f"DEFENSE: {defen}"]
        if down:
            lines.append(f"DOWN: {down} {distance}")
        if field_pos:
            lines.append(f"FIELD POSITION: {field_pos}")
        if quarter:
            lines.append(f"GAME CLOCK: {quarter}")
        if score:
            lines.append(f"SCORE: {score}")
        if def_look:
            lines.append(f"DEFENSIVE LOOK: {def_look}")
        if notes:
            lines.append(f"ADDITIONAL CONTEXT: {notes}")
        lines.append(tendency_ctx)
        lines.append(
            "\nAnalyze the defensive alignment, predict blitz probability and coverage type, "
            "then recommend the optimal offensive play call with full reasoning. Include "
            "primary read, hot read, EV estimate, and clock impact. Also provide 2 alternative play calls."
        )
        return "\n".join(lines)

    def _build_blitz(self, *, off, defen, tendency_ctx,
                     down, distance, field_pos, quarter, score,
                     def_look, notes, **_) -> str:
        lines = [f"NFL defensive read and blitz prediction:", "", f"OFFENSE: {off}", f"DEFENSE: {defen}"]
        if down:
            lines.append(f"SITUATION: {down} {distance}")
        if field_pos:
            lines.append(f"FIELD POSITION: {field_pos}")
        if quarter:
            lines.append(quarter)
        if score:
            lines.append(f"SCORE: {score}")
        if def_look:
            lines.append(f"DEFENSIVE ALIGNMENT: {def_look}")
        if notes:
            lines.append(f"NOTES: {notes}")
        lines.append(tendency_ctx)
        lines.append(
            f"\nPredict: (1) Blitz probability with reasoning based on {defen}'s DC tendencies, "
            f"(2) Most likely coverage shell, (3) Type of pressure if blitzing, "
            f"(4) Individual matchup assignments, (5) Where the vulnerability is for the offense to exploit."
        )
        return "\n".join(lines)

    def _build_player(self, *, off, defen, tendency_ctx,
                      player_name, **_) -> str:
        name = player_name or "[specify player]"
        return (
            f"Deep player movement profile for {name} on the {off}. "
            f"Cover: route tree distribution (or pass rush move set for defenders), "
            f"tendencies by down/distance, red zone behavior, how their movement patterns "
            f"change when dealing with injuries (especially lower body), athletic measurables "
            f"and how they show up on film, and how {defen}'s defense should plan to contain "
            f"them (or how {off} should scheme around them). Use the last 5 seasons of data."
            f"{tendency_ctx}"
        )

    def _build_playbook(self, *, off, defen, tendency_ctx, **_) -> str:
        return (
            f"Reverse-engineer the {off}'s offensive playbook based on the last 5 seasons "
            f"of data. Cover: base formations and personnel grouping frequencies, run/pass "
            f"splits by formation and down, motion and shift patterns (and what they signal), "
            f"tendency-breakers and constraint plays, red zone package, 2-minute offense "
            f"approach, and how the scheme has evolved year over year. Then project how "
            f"{defen}'s defense should game-plan against these tendencies."
            f"{tendency_ctx}"
        )

    def _build_postgame(self, *, off, defen, tendency_ctx, **_) -> str:
        return (
            f"Post-game analytical breakdown of {off} vs {defen}. "
            f"Pull the most recent game data between these teams. Analyze: what offensive "
            f"scheme worked/didn't, defensive adjustments made throughout the game, key "
            f"matchups that decided the outcome, play-calling tendencies that were exploited, "
            f"and what each team should adjust for the next meeting. Include drive-by-drive "
            f"analysis of critical sequences."
            f"{tendency_ctx}"
        )

    async def run(self, analysis_type: str, params: dict) -> str:
        prompt = self.build_prompt(analysis_type, params)
        resp = await self.ai.complete(prompt)
        if resp.ok:
            return resp.text
        return resp.error or "No analysis generated."
