from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field, asdict

from fastapi import WebSocket

from server.analysis import AnalysisEngine
from server.teams import get_team


@dataclass
class GameState:
    home_team: str = "KC"
    away_team: str = "SF"
    home_score: int = 0
    away_score: int = 0
    quarter: int = 1
    clock: str = "15:00"
    down: int = 1
    distance: int = 10
    yard_line: int = 25
    possession: str = "KC"
    is_halftime: bool = False
    is_final: bool = False
    last_play: str = ""
    drive_plays: int = 0
    drive_yards: int = 0

    @property
    def situation_str(self) -> str:
        side = "Own" if self.yard_line <= 50 else "Opp"
        yl = self.yard_line if self.yard_line <= 50 else 100 - self.yard_line
        pos = get_team(self.possession)
        pos_name = pos["name"] if pos else self.possession
        return f"{pos_name} ball — {self._ordinal(self.down)} & {self.distance} at {side} {yl}"

    @staticmethod
    def _ordinal(n: int) -> str:
        return {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(n, f"{n}th")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["situation"] = self.situation_str
        return d


PLAY_OUTCOMES = [
    {"type": "run", "desc": "run up the middle", "yards": lambda: random.choice([-1, 0, 1, 2, 3, 4, 5, 6, 8, 12])},
    {"type": "run", "desc": "outside zone left", "yards": lambda: random.choice([-2, 0, 1, 3, 4, 5, 7, 9, 15])},
    {"type": "run", "desc": "sweep right", "yards": lambda: random.choice([-3, 0, 2, 4, 6, 8, 11, 18])},
    {"type": "pass", "desc": "short pass complete", "yards": lambda: random.choice([3, 4, 5, 6, 7, 8, 9, 10])},
    {"type": "pass", "desc": "deep pass complete", "yards": lambda: random.choice([15, 18, 22, 25, 30, 35, 45])},
    {"type": "pass", "desc": "pass incomplete", "yards": lambda: 0},
    {"type": "pass", "desc": "pass intercepted", "yards": lambda: 0},
    {"type": "penalty", "desc": "offensive holding", "yards": lambda: -10},
    {"type": "penalty", "desc": "defensive pass interference", "yards": lambda: random.choice([10, 15, 20, 30])},
    {"type": "sack", "desc": "quarterback sacked", "yards": lambda: random.choice([-5, -7, -8, -10])},
]


class LiveGameManager:
    def __init__(self, engine: AnalysisEngine | None = None):
        self.engine = engine or AnalysisEngine()
        self.state = GameState()
        self.connections: list[WebSocket] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._clock_seconds = 900

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        await ws.send_json({"type": "state", "data": self.state.to_dict()})

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, message: dict):
        dead: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)

    def update_state(self, event: dict):
        for key, val in event.items():
            if hasattr(self.state, key):
                setattr(self.state, key, val)

    def get_situation(self) -> dict:
        return self.state.to_dict()

    async def auto_suggest_play(self) -> str:
        opp = self.state.away_team if self.state.possession == self.state.home_team else self.state.home_team
        params = {
            "offense": self.state.possession,
            "defense": opp,
            "down": GameState._ordinal(self.state.down),
            "distance": f"& {self.state.distance}",
            "field_position": self.state.situation_str.split(" at ")[-1] if " at " in self.state.situation_str else "",
            "quarter": f"{GameState._ordinal(self.state.quarter)} Quarter",
            "score": f"{self.state.home_team} {self.state.home_score} - {self.state.away_team} {self.state.away_score}",
        }
        try:
            return await self.engine.run("playcall", params)
        except Exception as e:
            return f"[Auto-suggest unavailable: {e}]"

    def _advance_clock(self, seconds: int):
        self._clock_seconds = max(0, self._clock_seconds - seconds)
        mins = self._clock_seconds // 60
        secs = self._clock_seconds % 60
        self.state.clock = f"{mins}:{secs:02d}"

    def _simulate_play(self) -> dict:
        play = random.choice(PLAY_OUTCOMES)
        yards = play["yards"]()
        result = {
            "play_type": play["type"],
            "description": play["desc"],
            "yards": yards,
        }

        if play["desc"] == "pass intercepted":
            self._turnover()
            result["turnover"] = True
            self.state.last_play = f"INTERCEPTED! Turnover."
            self.state.drive_plays = 0
            self.state.drive_yards = 0
            return result

        self.state.yard_line += yards
        self.state.drive_plays += 1
        self.state.drive_yards += yards

        if self.state.yard_line >= 100:
            self._score_touchdown()
            result["touchdown"] = True
            self.state.last_play = f"TOUCHDOWN! {play['desc']} for {yards} yards."
            return result

        if self.state.yard_line <= 0:
            self.state.yard_line = 20
            self._turnover()
            result["safety"] = True
            opp = self.state.away_team if self.state.possession == self.state.home_team else self.state.home_team
            if self.state.possession == self.state.home_team:
                self.state.away_score += 2
            else:
                self.state.home_score += 2
            self.state.last_play = "SAFETY!"
            return result

        if yards >= self.state.distance:
            self.state.down = 1
            self.state.distance = min(10, 100 - self.state.yard_line)
            self.state.last_play = f"{play['desc'].capitalize()} for {yards} yards. First down!"
        else:
            self.state.distance -= yards
            if self.state.down >= 4:
                if self.state.yard_line >= 60 and random.random() < 0.5:
                    if random.random() < 0.7:
                        self._score_field_goal(result)
                    else:
                        self.state.last_play = f"Field goal MISSED."
                        self._turnover()
                        self.state.yard_line = max(20, 100 - self.state.yard_line)
                else:
                    self.state.last_play = f"Punt. {play['desc']} on 4th down."
                    self._turnover()
                    self.state.yard_line = max(20, 100 - self.state.yard_line - random.randint(30, 50))
                self.state.drive_plays = 0
                self.state.drive_yards = 0
            else:
                self.state.down += 1
                self.state.last_play = f"{play['desc'].capitalize()} for {yards} yards."

        return result

    def _score_touchdown(self):
        if self.state.possession == self.state.home_team:
            self.state.home_score += 7
        else:
            self.state.away_score += 7
        self._turnover()
        self.state.yard_line = 25
        self.state.down = 1
        self.state.distance = 10
        self.state.drive_plays = 0
        self.state.drive_yards = 0

    def _score_field_goal(self, result: dict):
        if self.state.possession == self.state.home_team:
            self.state.home_score += 3
        else:
            self.state.away_score += 3
        result["field_goal"] = True
        self.state.last_play = "Field goal is GOOD!"
        self._turnover()
        self.state.yard_line = 25
        self.state.down = 1
        self.state.distance = 10
        self.state.drive_plays = 0
        self.state.drive_yards = 0

    def _turnover(self):
        self.state.possession = (
            self.state.away_team
            if self.state.possession == self.state.home_team
            else self.state.home_team
        )

    async def start_demo(self, home: str = "KC", away: str = "SF"):
        if self._running:
            return
        self._running = True
        self.state = GameState(home_team=home, away_team=away, possession=home)
        self._clock_seconds = 900
        self._task = asyncio.create_task(self._demo_loop())

    async def stop_demo(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _demo_loop(self):
        await self.broadcast({"type": "state", "data": self.state.to_dict()})
        while self._running and not self.state.is_final:
            await asyncio.sleep(random.uniform(4, 8))
            if not self._running:
                break

            self._advance_clock(random.randint(15, 45))
            result = self._simulate_play()

            if self._clock_seconds <= 0:
                if self.state.quarter < 4:
                    self.state.quarter += 1
                    self._clock_seconds = 900
                    self.state.clock = "15:00"
                    if self.state.quarter == 3:
                        self.state.is_halftime = False
                        self._turnover()
                        self.state.yard_line = 25
                        self.state.down = 1
                        self.state.distance = 10
                else:
                    self.state.is_final = True

            await self.broadcast({
                "type": "play",
                "data": {**self.state.to_dict(), "play_result": result},
            })

            if self.state.down == 1 and random.random() < 0.3:
                suggestion = await self.auto_suggest_play()
                await self.broadcast({
                    "type": "suggestion",
                    "data": {"text": suggestion, "situation": self.state.situation_str},
                })

        if self.state.is_final:
            await self.broadcast({"type": "final", "data": self.state.to_dict()})
