import { useState, useRef, useEffect, useCallback } from "react";

const NFL_TEAMS = [
  { abbr: "ARI", name: "Arizona Cardinals", division: "NFC West", color: "#97233F" },
  { abbr: "ATL", name: "Atlanta Falcons", division: "NFC South", color: "#A71930" },
  { abbr: "BAL", name: "Baltimore Ravens", division: "AFC North", color: "#241773" },
  { abbr: "BUF", name: "Buffalo Bills", division: "AFC East", color: "#00338D" },
  { abbr: "CAR", name: "Carolina Panthers", division: "NFC South", color: "#0085CA" },
  { abbr: "CHI", name: "Chicago Bears", division: "NFC North", color: "#0B162A" },
  { abbr: "CIN", name: "Cincinnati Bengals", division: "AFC North", color: "#FB4F14" },
  { abbr: "CLE", name: "Cleveland Browns", division: "AFC North", color: "#311D00" },
  { abbr: "DAL", name: "Dallas Cowboys", division: "NFC East", color: "#003594" },
  { abbr: "DEN", name: "Denver Broncos", division: "AFC West", color: "#FB4F14" },
  { abbr: "DET", name: "Detroit Lions", division: "NFC North", color: "#0076B6" },
  { abbr: "GB", name: "Green Bay Packers", division: "NFC North", color: "#203731" },
  { abbr: "HOU", name: "Houston Texans", division: "AFC South", color: "#03202F" },
  { abbr: "IND", name: "Indianapolis Colts", division: "AFC South", color: "#002C5F" },
  { abbr: "JAX", name: "Jacksonville Jaguars", division: "AFC South", color: "#006778" },
  { abbr: "KC", name: "Kansas City Chiefs", division: "AFC West", color: "#E31837" },
  { abbr: "LAC", name: "Los Angeles Chargers", division: "AFC West", color: "#0080C6" },
  { abbr: "LAR", name: "Los Angeles Rams", division: "NFC West", color: "#003594" },
  { abbr: "LV", name: "Las Vegas Raiders", division: "AFC West", color: "#A5ACAF" },
  { abbr: "MIA", name: "Miami Dolphins", division: "AFC East", color: "#008E97" },
  { abbr: "MIN", name: "Minnesota Vikings", division: "NFC North", color: "#4F2683" },
  { abbr: "NE", name: "New England Patriots", division: "AFC East", color: "#002244" },
  { abbr: "NO", name: "New Orleans Saints", division: "NFC South", color: "#D3BC8D" },
  { abbr: "NYG", name: "New York Giants", division: "NFC East", color: "#0B2265" },
  { abbr: "NYJ", name: "New York Jets", division: "AFC East", color: "#125740" },
  { abbr: "PHI", name: "Philadelphia Eagles", division: "NFC East", color: "#004C54" },
  { abbr: "PIT", name: "Pittsburgh Steelers", division: "AFC North", color: "#FFB612" },
  { abbr: "SEA", name: "Seattle Seahawks", division: "NFC West", color: "#002244" },
  { abbr: "SF", name: "San Francisco 49ers", division: "NFC West", color: "#AA0000" },
  { abbr: "TB", name: "Tampa Bay Buccaneers", division: "NFC South", color: "#D50A0A" },
  { abbr: "TEN", name: "Tennessee Titans", division: "AFC South", color: "#0C2340" },
  { abbr: "WAS", name: "Washington Commanders", division: "NFC East", color: "#5A1414" },
];

const ANALYSIS_TYPES = [
  { id: "scouting", label: "Pre-Game Scouting Report", icon: "\u{1F4CB}", desc: "Full matchup breakdown with tendencies, key players, and game plan" },
  { id: "playcall", label: "Situational Play Call", icon: "\u{1F3AF}", desc: "Best offensive play given down, distance, and defensive look" },
  { id: "blitz", label: "Blitz & Coverage Read", icon: "\u{1F50D}", desc: "Predict defensive pressure, coverage, and matchup assignments" },
  { id: "player", label: "Player Movement Profile", icon: "\u{1F3C3}", desc: "Deep dive on a specific player's tendencies and injury impact" },
  { id: "playbook", label: "Playbook Reverse Engineer", icon: "\u{1F4D6}", desc: "Reconstruct a team's scheme from formation and tendency data" },
  { id: "postgame", label: "Post-Game Breakdown", icon: "\u{1F4CA}", desc: "Analyze what happened and why after a completed game" },
];

const DOWNS = ["1st", "2nd", "3rd", "4th"];
const DISTANCES = ["& 1", "& 2", "& 3", "& 4", "& 5", "& 6", "& 7", "& 8", "& 9", "& 10", "& 15", "& 20", "& Goal"];
const FIELD_POSITIONS = [
  "Own 5", "Own 10", "Own 15", "Own 20", "Own 25", "Own 30", "Own 35", "Own 40", "Own 45",
  "Midfield",
  "Opp 45", "Opp 40", "Opp 35", "Opp 30", "Opp 25", "Opp 20", "Opp 15", "Opp 10", "Opp 5", "Opp 1"
];
const QUARTERS = ["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter", "OT"];

const API_BASE = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/live-game";

function TeamSelector({ label, value, onChange, otherTeam }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef(null);
  const team = NFL_TEAMS.find(t => t.abbr === value);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const divisions = {};
  NFL_TEAMS.filter(t => t.abbr !== otherTeam && t.name.toLowerCase().includes(search.toLowerCase()))
    .forEach(t => { if (!divisions[t.division]) divisions[t.division] = []; divisions[t.division].push(t); });

  return (
    <div ref={ref} style={{ position: "relative", flex: 1, minWidth: 220 }}>
      <label style={{ display: "block", fontSize: 11, fontFamily: "'Courier Prime', monospace", letterSpacing: 2, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 6 }}>{label}</label>
      <button onClick={() => setOpen(!open)} style={{
        width: "100%", padding: "12px 16px", background: team ? `linear-gradient(135deg, ${team.color}22, ${team.color}08)` : "rgba(255,255,255,0.03)",
        border: `1px solid ${team ? team.color + "44" : "rgba(255,255,255,0.08)"}`, borderRadius: 8, cursor: "pointer",
        display: "flex", alignItems: "center", gap: 10, color: "#e8e8d8", fontSize: 15, fontFamily: "'IBM Plex Sans', sans-serif",
        transition: "all 0.2s", outline: "none"
      }}>
        {team ? (
          <>
            <span style={{ width: 28, height: 28, borderRadius: 6, background: team.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#fff", fontFamily: "monospace", flexShrink: 0 }}>{team.abbr}</span>
            <span style={{ fontWeight: 600 }}>{team.name}</span>
          </>
        ) : <span style={{ color: "#666" }}>Select team...</span>}
        <span style={{ marginLeft: "auto", fontSize: 10, opacity: 0.4 }}>{"\u25BC"}</span>
      </button>

      {open && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 100, marginTop: 4,
          background: "#1a1a16", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10,
          boxShadow: "0 20px 60px rgba(0,0,0,0.7)", maxHeight: 360, overflow: "hidden", display: "flex", flexDirection: "column"
        }}>
          <div style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <input
              autoFocus placeholder="Search teams..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: "100%", padding: "8px 12px", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6, color: "#e8e8d8", fontSize: 13, outline: "none", fontFamily: "'IBM Plex Sans', sans-serif", boxSizing: "border-box" }}
            />
          </div>
          <div style={{ overflowY: "auto", padding: "4px 0" }}>
            {Object.entries(divisions).sort().map(([div, teams]) => (
              <div key={div}>
                <div style={{ padding: "6px 14px", fontSize: 10, fontFamily: "monospace", letterSpacing: 1.5, color: "#666", textTransform: "uppercase" }}>{div}</div>
                {teams.map(t => (
                  <button key={t.abbr} onClick={() => { onChange(t.abbr); setOpen(false); setSearch(""); }}
                    style={{
                      width: "100%", padding: "8px 14px", background: "none", border: "none", cursor: "pointer",
                      display: "flex", alignItems: "center", gap: 10, color: "#ccc", fontSize: 13,
                      fontFamily: "'IBM Plex Sans', sans-serif", transition: "background 0.15s"
                    }}
                    onMouseEnter={e => e.target.style.background = "rgba(255,255,255,0.05)"}
                    onMouseLeave={e => e.target.style.background = "none"}
                  >
                    <span style={{ width: 22, height: 22, borderRadius: 4, background: t.color, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "#fff", fontFamily: "monospace", flexShrink: 0 }}>{t.abbr}</span>
                    {t.name}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AnalysisCard({ type, selected, onClick }) {
  const active = selected === type.id;
  return (
    <button onClick={() => onClick(type.id)} style={{
      padding: "14px 16px", background: active ? "rgba(200,180,120,0.08)" : "rgba(255,255,255,0.02)",
      border: `1px solid ${active ? "rgba(200,180,120,0.3)" : "rgba(255,255,255,0.06)"}`,
      borderRadius: 10, cursor: "pointer", textAlign: "left", transition: "all 0.2s", outline: "none",
      display: "flex", gap: 12, alignItems: "flex-start"
    }}>
      <span style={{ fontSize: 22, lineHeight: 1 }}>{type.icon}</span>
      <div>
        <div style={{ color: active ? "#d4c896" : "#bbb", fontSize: 14, fontWeight: 600, fontFamily: "'IBM Plex Sans', sans-serif" }}>{type.label}</div>
        <div style={{ color: "#666", fontSize: 11, marginTop: 3, lineHeight: 1.4, fontFamily: "'IBM Plex Sans', sans-serif" }}>{type.desc}</div>
      </div>
    </button>
  );
}

function SelectInput({ label, value, onChange, options, placeholder }) {
  return (
    <div style={{ flex: 1, minWidth: 120 }}>
      <label style={{ display: "block", fontSize: 10, fontFamily: "monospace", letterSpacing: 1.5, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 4 }}>{label}</label>
      <select value={value} onChange={e => onChange(e.target.value)} style={{
        width: "100%", padding: "10px 12px", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 6, color: "#e8e8d8", fontSize: 13, fontFamily: "'IBM Plex Sans', sans-serif", outline: "none",
        cursor: "pointer", appearance: "none"
      }}>
        <option value="" style={{ background: "#1a1a16" }}>{placeholder || "Select..."}</option>
        {options.map(o => <option key={o} value={o} style={{ background: "#1a1a16" }}>{o}</option>)}
      </select>
    </div>
  );
}

function TextInput({ label, value, onChange, placeholder }) {
  return (
    <div style={{ flex: 1, minWidth: 200 }}>
      <label style={{ display: "block", fontSize: 10, fontFamily: "monospace", letterSpacing: 1.5, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 4 }}>{label}</label>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={{
        width: "100%", padding: "10px 12px", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 6, color: "#e8e8d8", fontSize: 13, fontFamily: "'IBM Plex Sans', sans-serif", outline: "none", boxSizing: "border-box"
      }} />
    </div>
  );
}

// ── Live Game Panel ───────────────────────────────────────────────────────────

function LiveGamePanel() {
  const [connected, setConnected] = useState(false);
  const [gameState, setGameState] = useState(null);
  const [plays, setPlays] = useState([]);
  const [suggestions, setSuggestions] = useState([]);
  const [homeTeam, setHomeTeam] = useState("KC");
  const [awayTeam, setAwayTeam] = useState("SF");
  const [running, setRunning] = useState(false);
  const wsRef = useRef(null);
  const feedRef = useRef(null);

  const connectWs = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => { setConnected(false); setRunning(false); };
    ws.onerror = () => setConnected(false);

    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === "state" || msg.type === "play" || msg.type === "final") {
        setGameState(msg.data);
        if (msg.type === "play") {
          setPlays(prev => [...prev.slice(-50), msg.data]);
        }
        if (msg.type === "final") setRunning(false);
      }
      if (msg.type === "suggestion") {
        setSuggestions(prev => [...prev.slice(-10), msg.data]);
      }
    };
  }, []);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  const startGame = () => {
    if (!connected) connectWs();
    setTimeout(() => {
      wsRef.current?.send(JSON.stringify({ action: "start", home: homeTeam, away: awayTeam }));
      setRunning(true);
      setPlays([]);
      setSuggestions([]);
    }, connected ? 0 : 1000);
  };

  const stopGame = () => {
    wsRef.current?.send(JSON.stringify({ action: "stop" }));
    setRunning(false);
  };

  const requestSuggestion = () => {
    wsRef.current?.send(JSON.stringify({ action: "suggest" }));
  };

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [plays]);

  const homeData = NFL_TEAMS.find(t => t.abbr === (gameState?.home_team || homeTeam));
  const awayData = NFL_TEAMS.find(t => t.abbr === (gameState?.away_team || awayTeam));

  return (
    <div>
      {/* Team selection for live game */}
      {!running && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 20, alignItems: "flex-end" }}>
          <TeamSelector label="Home Team" value={homeTeam} onChange={setHomeTeam} otherTeam={awayTeam} />
          <div style={{ display: "flex", alignItems: "center", padding: "0 4px", paddingTop: 20 }}>
            <span style={{ fontSize: 18, color: "#555", fontWeight: 300 }}>vs</span>
          </div>
          <TeamSelector label="Away Team" value={awayTeam} onChange={setAwayTeam} otherTeam={homeTeam} />
        </div>
      )}

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        {!running ? (
          <button onClick={startGame} style={{
            padding: "12px 24px", background: "linear-gradient(135deg, #2a9d2a, #1a7a1a)", border: "none",
            borderRadius: 8, color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer",
            fontFamily: "'IBM Plex Sans', sans-serif", letterSpacing: 0.5
          }}>
            {"\u{1F3C8}"} START LIVE GAME (Demo)
          </button>
        ) : (
          <>
            <button onClick={stopGame} style={{
              padding: "12px 24px", background: "linear-gradient(135deg, #c44, #922)", border: "none",
              borderRadius: 8, color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer",
              fontFamily: "'IBM Plex Sans', sans-serif"
            }}>
              STOP GAME
            </button>
            <button onClick={requestSuggestion} style={{
              padding: "12px 24px", background: "linear-gradient(135deg, #c8b478, #a89860)", border: "none",
              borderRadius: 8, color: "#111", fontSize: 14, fontWeight: 700, cursor: "pointer",
              fontFamily: "'IBM Plex Sans', sans-serif"
            }}>
              {"\u{1F3AF}"} GET PLAY SUGGESTION
            </button>
          </>
        )}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            width: 8, height: 8, borderRadius: "50%",
            background: connected ? "#2a9d2a" : "#c44",
            boxShadow: connected ? "0 0 8px #2a9d2a" : "0 0 8px #c44",
          }} />
          <span style={{ fontSize: 11, fontFamily: "monospace", color: "#8a8a7a" }}>
            {connected ? "CONNECTED" : "DISCONNECTED"}
          </span>
        </div>
      </div>

      {/* Scoreboard */}
      {gameState && (
        <div style={{
          padding: 20, borderRadius: 12, marginBottom: 20,
          background: "linear-gradient(135deg, rgba(200,180,120,0.06), rgba(255,255,255,0.02))",
          border: "1px solid rgba(200,180,120,0.15)"
        }}>
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 32, marginBottom: 12 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{
                width: 48, height: 48, borderRadius: 10, background: homeData?.color || "#333",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, fontWeight: 700, color: "#fff", fontFamily: "monospace", margin: "0 auto 6px"
              }}>{gameState.home_team}</div>
              <div style={{ fontSize: 36, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", color: "#e8e8d8" }}>
                {gameState.home_score}
              </div>
              <div style={{ fontSize: 11, color: "#8a8a7a" }}>{homeData?.name}</div>
            </div>

            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 11, fontFamily: "monospace", color: "#d4c896", letterSpacing: 2, marginBottom: 4 }}>
                {gameState.is_final ? "FINAL" : `Q${gameState.quarter}`}
              </div>
              <div style={{ fontSize: 24, fontFamily: "'JetBrains Mono', monospace", color: "#d4c896" }}>
                {gameState.clock}
              </div>
              <div style={{ fontSize: 10, color: "#666", marginTop: 4 }}>
                {gameState.is_final ? "" : gameState.situation}
              </div>
            </div>

            <div style={{ textAlign: "center" }}>
              <div style={{
                width: 48, height: 48, borderRadius: 10, background: awayData?.color || "#333",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16, fontWeight: 700, color: "#fff", fontFamily: "monospace", margin: "0 auto 6px"
              }}>{gameState.away_team}</div>
              <div style={{ fontSize: 36, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace", color: "#e8e8d8" }}>
                {gameState.away_score}
              </div>
              <div style={{ fontSize: 11, color: "#8a8a7a" }}>{awayData?.name}</div>
            </div>
          </div>

          {gameState.last_play && (
            <div style={{
              textAlign: "center", padding: "8px 12px", borderRadius: 6,
              background: "rgba(255,255,255,0.03)", fontSize: 13, color: "#ccc",
              fontFamily: "'IBM Plex Sans', sans-serif"
            }}>
              {gameState.last_play}
            </div>
          )}
        </div>
      )}

      {/* Play-by-Play Feed */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, color: "#8a8a7a", marginBottom: 8 }}>PLAY-BY-PLAY FEED</div>
          <div ref={feedRef} style={{
            height: 300, overflowY: "auto", padding: 12, borderRadius: 10,
            background: "rgba(0,0,0,0.3)", border: "1px solid rgba(255,255,255,0.05)"
          }}>
            {plays.length === 0 && (
              <div style={{ color: "#555", fontSize: 12, fontFamily: "monospace", textAlign: "center", paddingTop: 40 }}>
                Waiting for game to start...
              </div>
            )}
            {plays.map((p, i) => (
              <div key={i} style={{
                padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.03)",
                fontSize: 12, fontFamily: "'JetBrains Mono', monospace", color: "#aaa"
              }}>
                <span style={{ color: "#d4c896" }}>Q{p.quarter} {p.clock}</span>{" "}
                <span style={{ color: p.possession === p.home_team ? (homeData?.color || "#fff") : (awayData?.color || "#fff") }}>{p.possession}</span>{" "}
                {p.last_play}
              </div>
            ))}
          </div>
        </div>

        <div>
          <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, color: "#8a8a7a", marginBottom: 8 }}>AI PLAY SUGGESTIONS</div>
          <div style={{
            height: 300, overflowY: "auto", padding: 12, borderRadius: 10,
            background: "rgba(0,0,0,0.3)", border: "1px solid rgba(200,180,120,0.1)"
          }}>
            {suggestions.length === 0 && (
              <div style={{ color: "#555", fontSize: 12, fontFamily: "monospace", textAlign: "center", paddingTop: 40 }}>
                AI suggestions appear here during live play...
              </div>
            )}
            {suggestions.map((s, i) => (
              <div key={i} style={{
                padding: "10px 12px", marginBottom: 8, borderRadius: 8,
                background: "rgba(200,180,120,0.05)", border: "1px solid rgba(200,180,120,0.1)",
                fontSize: 12, color: "#ccc", lineHeight: 1.5
              }}>
                <div style={{ fontSize: 10, color: "#d4c896", fontFamily: "monospace", marginBottom: 4 }}>
                  {s.situation}
                </div>
                <div style={{ whiteSpace: "pre-wrap" }}>{s.text}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}


// ── Main App ──────────────────────────────────────────────────────────────────

export default function NFLPlaycaller() {
  const [activeTab, setActiveTab] = useState("analysis");
  const [offTeam, setOffTeam] = useState("");
  const [defTeam, setDefTeam] = useState("");
  const [analysis, setAnalysis] = useState("scouting");
  const [down, setDown] = useState("");
  const [distance, setDistance] = useState("");
  const [fieldPos, setFieldPos] = useState("");
  const [quarter, setQuarter] = useState("");
  const [score, setScore] = useState("");
  const [defLook, setDefLook] = useState("");
  const [playerName, setPlayerName] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingPhase, setLoadingPhase] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const resultRef = useRef(null);
  const timerRef = useRef(null);

  const offTeamData = NFL_TEAMS.find(t => t.abbr === offTeam);
  const defTeamData = NFL_TEAMS.find(t => t.abbr === defTeam);

  const needsSituation = ["playcall", "blitz"].includes(analysis);
  const needsPlayer = analysis === "player";

  const BRIEFING_LINES = [
    { delay: 300, type: "header", text: "APOLLO CYBERSENTINEL \u2014 OPERATION BRIEFING" },
    { delay: 800, type: "classified", text: "CLASSIFICATION: EYES ONLY" },
    { delay: 1200, type: "meta", text: `MATCHUP: ${offTeamData?.name || "---"} vs ${defTeamData?.name || "---"}` },
    { delay: 1600, type: "meta", text: `ANALYSIS: ${ANALYSIS_TYPES.find(a => a.id === analysis)?.label?.toUpperCase() || "FULL SPECTRUM"}` },
    { delay: 2200, type: "divider", text: "" },
    { delay: 2600, type: "section", text: "RULES OF ENGAGEMENT:" },
    { delay: 3100, type: "rule", text: "1. Pull ALL available intelligence \u2014 scores, stats, tendencies." },
    { delay: 3700, type: "rule", text: "2. Cross-reference formation data against 5-year tendency baseline." },
    { delay: 4300, type: "rule", text: "3. Identify defensive alignment tells BEFORE predicting coverage." },
    { delay: 4900, type: "rule", text: "4. Probability over certainty. Show confidence levels on every read." },
    { delay: 5500, type: "rule", text: "5. Chain of analysis: Shell \u2192 Blitz \u2192 Coverage \u2192 Matchup \u2192 Play call." },
    { delay: 6200, type: "divider", text: "" },
    { delay: 6600, type: "section", text: "INTELLIGENCE COLLECTION:" },
    { delay: 7100, type: "status", text: "Connecting to Claude inference engine..." },
    { delay: 8000, type: "status", text: "Scanning defensive coordinator tendencies..." },
    { delay: 9200, type: "status", text: "Reverse-engineering playbook from alignment data..." },
    { delay: 10500, type: "status", text: "Mapping player movement profiles..." },
    { delay: 12000, type: "status", text: "Computing optimal play sequences..." },
    { delay: 14000, type: "waiting", text: "STANDING BY FOR ANALYSIS COMPLETE..." },
  ];

  useEffect(() => {
    if (loading) {
      setElapsed(0);
      setLoadingPhase(0);
      const start = Date.now();
      timerRef.current = setInterval(() => {
        const now = Date.now() - start;
        setElapsed(now);
        const nextPhase = BRIEFING_LINES.filter(l => l.delay <= now).length;
        setLoadingPhase(nextPhase);
      }, 100);
      return () => clearInterval(timerRef.current);
    } else {
      clearInterval(timerRef.current);
    }
  }, [loading]);

  const runAnalysis = async () => {
    if (!offTeam || !defTeam) return;
    setLoading(true);
    setResult(null);
    setError(null);

    const body = {
      offense: offTeam,
      defense: defTeam,
      notes,
    };

    if (needsSituation) {
      body.down = down;
      body.distance = distance;
      body.field_position = fieldPos;
      body.quarter = quarter;
      body.score = score;
      body.defensive_look = defLook;
    }
    if (needsPlayer) {
      body.player_name = playerName;
    }

    try {
      const response = await fetch(`${API_BASE}/v1/analysis/${analysis}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      const data = await response.json();
      if (data.error) throw new Error(data.error);

      setResult(data.result || "No analysis generated.");
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err) {
      setError(err.message || "Analysis failed. Ensure the PlayCaller API server is running.");
    } finally {
      setLoading(false);
    }
  };

  const canRun = offTeam && defTeam && (!needsPlayer || playerName);

  const tabStyle = (id) => ({
    padding: "10px 20px", fontSize: 13, fontWeight: 600,
    fontFamily: "'IBM Plex Sans', sans-serif", cursor: "pointer",
    background: activeTab === id ? "rgba(200,180,120,0.1)" : "transparent",
    border: "none", borderBottom: activeTab === id ? "2px solid #d4c896" : "2px solid transparent",
    color: activeTab === id ? "#d4c896" : "#888",
    transition: "all 0.2s",
  });

  return (
    <div style={{
      minHeight: "100vh", background: "#111110", color: "#e8e8d8",
      fontFamily: "'IBM Plex Sans', -apple-system, sans-serif",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=Courier+Prime:wght@400;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />

      {/* TACTICAL BRIEFING LOADING OVERLAY */}
      {loading && (
        <div style={{
          position: "fixed", inset: 0, zIndex: 9999,
          background: "linear-gradient(180deg, #0a0a08 0%, #0d0d0a 40%, #0a0a08 100%)",
          display: "flex", alignItems: "center", justifyContent: "center",
          animation: "fadeIn 0.3s ease-out"
        }}>
          <div style={{
            position: "absolute", inset: 0, opacity: 0.03,
            backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.05) 2px, rgba(255,255,255,0.05) 4px)",
            pointerEvents: "none"
          }} />
          <div style={{ position: "absolute", top: 20, left: 20, width: 40, height: 40, borderTop: "2px solid #d4c89644", borderLeft: "2px solid #d4c89644" }} />
          <div style={{ position: "absolute", top: 20, right: 20, width: 40, height: 40, borderTop: "2px solid #d4c89644", borderRight: "2px solid #d4c89644" }} />
          <div style={{ position: "absolute", bottom: 20, left: 20, width: 40, height: 40, borderBottom: "2px solid #d4c89644", borderLeft: "2px solid #d4c89644" }} />
          <div style={{ position: "absolute", bottom: 20, right: 20, width: 40, height: 40, borderBottom: "2px solid #d4c89644", borderRight: "2px solid #d4c89644" }} />

          <div style={{ width: "100%", maxWidth: 640, padding: "0 32px" }}>
            {BRIEFING_LINES.slice(0, loadingPhase).map((line, i) => {
              const age = elapsed - line.delay;
              const opacity = Math.min(1, age / 400);
              const style = { opacity, transition: "opacity 0.3s", fontFamily: "'JetBrains Mono', monospace" };

              if (line.type === "header") return <div key={i} style={{ ...style, fontSize: 13, fontWeight: 700, letterSpacing: 4, color: "#d4c896", marginBottom: 16, textShadow: "0 0 20px rgba(212,200,150,0.3)" }}>{line.text}</div>;
              if (line.type === "classified") return <div key={i} style={{ ...style, fontSize: 11, color: "#c44", letterSpacing: 3, marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}><span style={{ display: "inline-block", width: 6, height: 6, background: "#c44", borderRadius: "50%", animation: "pulse 1.5s ease-in-out infinite" }} />{line.text}</div>;
              if (line.type === "meta") return <div key={i} style={{ ...style, fontSize: 12, color: "#8a8a7a", marginBottom: 4 }}>{line.text}</div>;
              if (line.type === "divider") return <div key={i} style={{ ...style, height: 1, margin: "16px 0", background: "linear-gradient(90deg, transparent, rgba(212,200,150,0.15), transparent)" }} />;
              if (line.type === "section") return <div key={i} style={{ ...style, fontSize: 12, fontWeight: 600, color: "#d4c896", letterSpacing: 2, marginBottom: 10 }}>{line.text}</div>;
              if (line.type === "rule") return <div key={i} style={{ ...style, fontSize: 12, color: "#bbb8a8", marginBottom: 6, paddingLeft: 16, lineHeight: 1.5 }}>{line.text}</div>;
              if (line.type === "status") return <div key={i} style={{ ...style, fontSize: 11, color: "#6a9955", marginBottom: 5, display: "flex", alignItems: "center", gap: 8 }}><span style={{ color: "#6a9955" }}>{">"}</span>{line.text}{i === loadingPhase - 1 && <span style={{ display: "inline-block", width: 6, height: 12, background: "#6a9955", animation: "blink 0.8s step-end infinite" }} />}</div>;
              if (line.type === "waiting") return <div key={i} style={{ ...style, fontSize: 12, fontWeight: 600, color: "#d4c896", marginTop: 12, animation: "pulse 2s ease-in-out infinite" }}>{line.text}</div>;
              return null;
            })}
            <div style={{ marginTop: 28, height: 2, background: "rgba(255,255,255,0.04)", borderRadius: 1, overflow: "hidden" }}>
              <div style={{ height: "100%", background: "linear-gradient(90deg, #d4c896, #a89860)", width: `${Math.min(95, (loadingPhase / BRIEFING_LINES.length) * 100)}%`, transition: "width 0.5s ease-out", borderRadius: 1, boxShadow: "0 0 8px rgba(212,200,150,0.3)" }} />
            </div>
            <div style={{ marginTop: 10, fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: "#555", letterSpacing: 1, display: "flex", justifyContent: "space-between" }}>
              <span>ELAPSED: {(elapsed / 1000).toFixed(1)}s</span>
              <span>CLAUDE AI INFERENCE</span>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{
        padding: "32px 24px 0", borderBottom: "1px solid rgba(255,255,255,0.04)",
        background: "linear-gradient(180deg, rgba(200,180,120,0.03) 0%, transparent 100%)"
      }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
            <span style={{ fontSize: 10, fontFamily: "monospace", letterSpacing: 3, color: "#8a8a7a", textTransform: "uppercase" }}>Apollo CyberSentinel</span>
            <span style={{ fontSize: 9, fontFamily: "monospace", color: "#555", marginLeft: "auto" }}>POWERED BY CLAUDE AI</span>
          </div>
          <h1 style={{
            fontSize: 32, fontWeight: 700, margin: 0, letterSpacing: -0.5,
            background: "linear-gradient(135deg, #d4c896, #a89860)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent"
          }}>NFL PlayCaller AI</h1>
          <p style={{ color: "#666", fontSize: 13, marginTop: 6, fontWeight: 300, marginBottom: 20 }}>
            AI Offensive Coordinator Intelligence — blitz reads, play optimization, scouting reports, live game analysis
          </p>

          {/* Tabs */}
          <div style={{ display: "flex", gap: 0 }}>
            <button onClick={() => setActiveTab("analysis")} style={tabStyle("analysis")}>
              {"\u{1F3AF}"} ANALYSIS
            </button>
            <button onClick={() => setActiveTab("live")} style={tabStyle("live")}>
              {"\u{1F3C8}"} LIVE GAME
            </button>
          </div>
        </div>
      </div>

      {/* Body */}
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "24px 24px 80px" }}>

        {activeTab === "live" ? (
          <LiveGamePanel />
        ) : (
          <>
            {/* Team Selection */}
            <section style={{ marginBottom: 28 }}>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
                <TeamSelector label="Offense" value={offTeam} onChange={setOffTeam} otherTeam={defTeam} />
                <div style={{ display: "flex", alignItems: "center", padding: "0 4px", paddingTop: 20 }}>
                  <span style={{ fontSize: 18, color: "#555", fontWeight: 300 }}>vs</span>
                </div>
                <TeamSelector label="Defense" value={defTeam} onChange={setDefTeam} otherTeam={offTeam} />
              </div>
              {offTeam && defTeam && (
                <div style={{
                  marginTop: 12, padding: "10px 14px", borderRadius: 8,
                  background: `linear-gradient(135deg, ${offTeamData.color}15, ${defTeamData.color}15)`,
                  border: "1px solid rgba(255,255,255,0.04)", display: "flex", alignItems: "center", gap: 8
                }}>
                  <span style={{ color: offTeamData.color, fontWeight: 700, fontSize: 14 }}>{offTeamData.abbr}</span>
                  <span style={{ color: "#555", fontSize: 11 }}>offense vs</span>
                  <span style={{ color: defTeamData.color, fontWeight: 700, fontSize: 14 }}>{defTeamData.abbr}</span>
                  <span style={{ color: "#555", fontSize: 11 }}>defense</span>
                </div>
              )}
            </section>

            {/* Analysis Type */}
            <section style={{ marginBottom: 28 }}>
              <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 10 }}>Analysis Type</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", gap: 8 }}>
                {ANALYSIS_TYPES.map(t => <AnalysisCard key={t.id} type={t} selected={analysis} onClick={setAnalysis} />)}
              </div>
            </section>

            {/* Situational Inputs */}
            {needsSituation && (
              <section style={{
                marginBottom: 28, padding: 20, borderRadius: 12,
                background: "rgba(255,255,255,0.015)", border: "1px solid rgba(255,255,255,0.05)"
              }}>
                <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 14 }}>Game Situation</div>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
                  <SelectInput label="Down" value={down} onChange={setDown} options={DOWNS} placeholder="Down" />
                  <SelectInput label="Distance" value={distance} onChange={setDistance} options={DISTANCES} placeholder="Distance" />
                  <SelectInput label="Field Position" value={fieldPos} onChange={setFieldPos} options={FIELD_POSITIONS} placeholder="Field pos" />
                  <SelectInput label="Quarter" value={quarter} onChange={setQuarter} options={QUARTERS} placeholder="Quarter" />
                </div>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                  <TextInput label="Score" value={score} onChange={setScore} placeholder="e.g. KC 21 - BAL 17" />
                  <TextInput label="Defensive Look (optional)" value={defLook} onChange={setDefLook} placeholder="e.g. Nickel, 2-high, LBs walked up" />
                </div>
              </section>
            )}

            {/* Player Input */}
            {needsPlayer && (
              <section style={{
                marginBottom: 28, padding: 20, borderRadius: 12,
                background: "rgba(255,255,255,0.015)", border: "1px solid rgba(255,255,255,0.05)"
              }}>
                <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 14 }}>Player</div>
                <TextInput label="Player Name" value={playerName} onChange={setPlayerName} placeholder="e.g. Tyreek Hill, Micah Parsons" />
              </section>
            )}

            {/* Additional Notes */}
            <section style={{ marginBottom: 28 }}>
              <div style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, textTransform: "uppercase", color: "#8a8a7a", marginBottom: 6 }}>Additional Context (optional)</div>
              <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Any extra info — injuries, specific things you want analyzed, custom scenarios..."
                rows={3} style={{
                  width: "100%", padding: "12px 14px", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8, color: "#e8e8d8", fontSize: 13, fontFamily: "'IBM Plex Sans', sans-serif", outline: "none",
                  resize: "vertical", boxSizing: "border-box", lineHeight: 1.5
                }} />
            </section>

            {/* Run Button */}
            <button onClick={runAnalysis} disabled={!canRun || loading} style={{
              width: "100%", padding: "16px 24px",
              background: canRun && !loading ? "linear-gradient(135deg, #c8b478, #a89860)" : "rgba(255,255,255,0.05)",
              border: "none", borderRadius: 10, cursor: canRun && !loading ? "pointer" : "not-allowed",
              color: canRun && !loading ? "#111" : "#555", fontSize: 15, fontWeight: 700,
              fontFamily: "'IBM Plex Sans', sans-serif", letterSpacing: 0.5,
              transition: "all 0.3s", transform: "scale(1)",
              boxShadow: canRun && !loading ? "0 4px 20px rgba(200,180,120,0.2)" : "none"
            }}
              onMouseEnter={e => { if (canRun && !loading) e.target.style.transform = "scale(1.01)"; }}
              onMouseLeave={e => e.target.style.transform = "scale(1)"}
            >
              {loading ? (
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                  <span style={{ display: "inline-block", width: 16, height: 16, border: "2px solid rgba(0,0,0,0.2)", borderTopColor: "#111", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                  Analyzing matchup via Claude...
                </span>
              ) : `Run ${ANALYSIS_TYPES.find(a => a.id === analysis)?.label || "Analysis"}`}
            </button>

            {/* Error */}
            {error && (
              <div style={{ marginTop: 16, padding: "14px 18px", borderRadius: 10, background: "rgba(220,50,50,0.08)", border: "1px solid rgba(220,50,50,0.2)", color: "#e88", fontSize: 13 }}>
                {error}
              </div>
            )}

            {/* Results */}
            {result && (
              <div ref={resultRef} style={{
                marginTop: 28, padding: "28px 24px", borderRadius: 14,
                background: "linear-gradient(180deg, rgba(200,180,120,0.04) 0%, rgba(255,255,255,0.01) 100%)",
                border: "1px solid rgba(200,180,120,0.12)"
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 18 }}>
                  <span style={{ fontSize: 11, fontFamily: "monospace", letterSpacing: 2, textTransform: "uppercase", color: "#d4c896" }}>Analysis Complete</span>
                  <div style={{ flex: 1, height: 1, background: "rgba(200,180,120,0.15)" }} />
                  <span style={{ fontSize: 9, fontFamily: "monospace", color: "#555" }}>via Claude AI</span>
                </div>
                <div style={{
                  fontSize: 14, lineHeight: 1.75, color: "#ccc", fontFamily: "'IBM Plex Sans', sans-serif",
                  whiteSpace: "pre-wrap", wordBreak: "break-word"
                }}>
                  {result.split('\n').map((line, i) => {
                    if (line.startsWith('# ')) return <h2 key={i} style={{ fontSize: 20, fontWeight: 700, color: "#e8e8d8", margin: "24px 0 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: 8 }}>{line.slice(2)}</h2>;
                    if (line.startsWith('## ')) return <h3 key={i} style={{ fontSize: 16, fontWeight: 600, color: "#d4c896", margin: "20px 0 8px" }}>{line.slice(3)}</h3>;
                    if (line.startsWith('### ')) return <h4 key={i} style={{ fontSize: 14, fontWeight: 600, color: "#bbb", margin: "16px 0 6px" }}>{line.slice(4)}</h4>;
                    if (line.startsWith('- ')) return <div key={i} style={{ paddingLeft: 16, position: "relative", marginBottom: 4 }}><span style={{ position: "absolute", left: 0, color: "#d4c896" }}>{"\u2022"}</span>{line.slice(2)}</div>;
                    if (line.startsWith('**') && line.endsWith('**')) return <div key={i} style={{ fontWeight: 600, color: "#e8e8d8", marginTop: 8 }}>{line.slice(2, -2)}</div>;
                    if (line.trim() === '') return <div key={i} style={{ height: 8 }} />;
                    return <div key={i}>{line}</div>;
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
        * { box-sizing: border-box; }
        select option { background: #1a1a16; color: #e8e8d8; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
      `}</style>
    </div>
  );
}
