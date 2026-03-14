import { useState, useRef, useEffect } from "react";

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
  { id: "scouting", label: "Pre-Game Scouting Report", icon: "📋", desc: "Full matchup breakdown with tendencies, key players, and game plan" },
  { id: "playcall", label: "Situational Play Call", icon: "🎯", desc: "Best offensive play given down, distance, and defensive look" },
  { id: "blitz", label: "Blitz & Coverage Read", icon: "🔍", desc: "Predict defensive pressure, coverage, and matchup assignments" },
  { id: "player", label: "Player Movement Profile", icon: "🏃", desc: "Deep dive on a specific player's tendencies and injury impact" },
  { id: "playbook", label: "Playbook Reverse Engineer", icon: "📖", desc: "Reconstruct a team's scheme from formation and tendency data" },
  { id: "postgame", label: "Post-Game Breakdown", icon: "📊", desc: "Analyze what happened and why after a completed game" },
];

const DOWNS = ["1st", "2nd", "3rd", "4th"];
const DISTANCES = ["& 1", "& 2", "& 3", "& 4", "& 5", "& 6", "& 7", "& 8", "& 9", "& 10", "& 15", "& 20", "& Goal"];
const FIELD_POSITIONS = [
  "Own 5", "Own 10", "Own 15", "Own 20", "Own 25", "Own 30", "Own 35", "Own 40", "Own 45",
  "Midfield",
  "Opp 45", "Opp 40", "Opp 35", "Opp 30", "Opp 25", "Opp 20", "Opp 15", "Opp 10", "Opp 5", "Opp 1"
];
const QUARTERS = ["1st Quarter", "2nd Quarter", "3rd Quarter", "4th Quarter", "OT"];

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
        <span style={{ marginLeft: "auto", fontSize: 10, opacity: 0.4 }}>▼</span>
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

export default function NFLPlaycaller() {
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
    { delay: 300, type: "header", text: "APOLLO CYBERSENTINEL — OPERATION BRIEFING" },
    { delay: 800, type: "classified", text: `CLASSIFICATION: EYES ONLY` },
    { delay: 1200, type: "meta", text: `MATCHUP: ${offTeamData?.name || "---"} vs ${defTeamData?.name || "---"}` },
    { delay: 1600, type: "meta", text: `ANALYSIS: ${ANALYSIS_TYPES.find(a => a.id === analysis)?.label?.toUpperCase() || "FULL SPECTRUM"}` },
    { delay: 2200, type: "divider", text: "" },
    { delay: 2600, type: "section", text: "RULES OF ENGAGEMENT:" },
    { delay: 3100, type: "rule", text: "1. Pull ALL available intelligence — scores, stats, tendencies." },
    { delay: 3700, type: "rule", text: "2. Cross-reference formation data against 5-year tendency baseline." },
    { delay: 4300, type: "rule", text: "3. Identify defensive alignment tells BEFORE predicting coverage." },
    { delay: 4900, type: "rule", text: "4. Probability over certainty. Show confidence levels on every read." },
    { delay: 5500, type: "rule", text: "5. Chain of analysis: Shell → Blitz → Coverage → Matchup → Play call." },
    { delay: 6200, type: "divider", text: "" },
    { delay: 6600, type: "section", text: "INTELLIGENCE COLLECTION:" },
    { delay: 7100, type: "status", text: "Pulling live data feeds..." },
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

  const buildPrompt = () => {
    const off = offTeamData?.name || "Offense";
    const def = defTeamData?.name || "Defense";

    let prompt = "";
    switch (analysis) {
      case "scouting":
        prompt = `Generate a comprehensive NFL pre-game scouting report for ${off} (offense) vs ${def} (defense). Cover: offensive tendencies and key playmakers, defensive scheme and blitz tendencies, head-to-head matchup advantages, recommended game plans for both sides, and situational strategy (red zone, 3rd down, 2-minute). Use the last 5 years of data to identify patterns. Include probability breakdowns for blitz rates and coverage tendencies.`;
        break;
      case "playcall":
        prompt = `NFL situational play call analysis:\n\nOFFENSE: ${off}\nDEFENSE: ${def}\n${down ? `DOWN: ${down} ${distance}` : ""}\n${fieldPos ? `FIELD POSITION: ${fieldPos}` : ""}\n${quarter ? `GAME CLOCK: ${quarter}` : ""}\n${score ? `SCORE: ${score}` : ""}\n${defLook ? `DEFENSIVE LOOK: ${defLook}` : ""}\n${notes ? `ADDITIONAL CONTEXT: ${notes}` : ""}\n\nAnalyze the defensive alignment, predict blitz probability and coverage type, then recommend the optimal offensive play call with full reasoning. Include primary read, hot read, EV estimate, and clock impact. Also provide 2 alternative play calls.`;
        break;
      case "blitz":
        prompt = `NFL defensive read and blitz prediction:\n\nOFFENSE: ${off}\nDEFENSE: ${def}\n${down ? `SITUATION: ${down} ${distance}` : ""}\n${fieldPos ? `FIELD POSITION: ${fieldPos}` : ""}\n${quarter ? `${quarter}` : ""}\n${score ? `SCORE: ${score}` : ""}\n${defLook ? `DEFENSIVE ALIGNMENT: ${defLook}` : ""}\n${notes ? `NOTES: ${notes}` : ""}\n\nPredict: (1) Blitz probability with reasoning based on ${def}'s DC tendencies, (2) Most likely coverage shell, (3) Type of pressure if blitzing, (4) Individual matchup assignments, (5) Where the vulnerability is for the offense to exploit.`;
        break;
      case "player":
        prompt = `Deep player movement profile for ${playerName || "[specify player]"} on the ${off}. Cover: route tree distribution (or pass rush move set for defenders), tendencies by down/distance, red zone behavior, how their movement patterns change when dealing with injuries (especially lower body), athletic measurables and how they show up on film, and how ${def}'s defense should plan to contain them (or how ${off} should scheme around them). Use the last 5 seasons of data.`;
        break;
      case "playbook":
        prompt = `Reverse-engineer the ${off}'s offensive playbook based on the last 5 seasons of data. Cover: base formations and personnel grouping frequencies, run/pass splits by formation and down, motion and shift patterns (and what they signal), tendency-breakers and constraint plays, red zone package, 2-minute offense approach, and how the scheme has evolved year over year. Then project how ${def}'s defense should game-plan against these tendencies.`;
        break;
      case "postgame":
        prompt = `Post-game analytical breakdown of ${off} vs ${def}. Pull the most recent game data between these teams. Analyze: what offensive scheme worked/didn't, defensive adjustments made throughout the game, key matchups that decided the outcome, play-calling tendencies that were exploited, and what each team should adjust for the next meeting. Include drive-by-drive analysis of critical sequences.`;
        break;
      default:
        prompt = `Analyze ${off} vs ${def}.`;
    }
    return prompt;
  };

  const runAnalysis = async () => {
    if (!offTeam || !defTeam) return;
    setLoading(true);
    setResult(null);
    setError(null);

    const prompt = buildPrompt();

    try {
      const response = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-20250514",
          max_tokens: 4000,
          system: `You are an elite NFL offensive coordinator and defensive analyst AI with deep knowledge of every NFL team's scheme, personnel, and tendencies from 2021-2025. You provide analysis at a professional coaching staff level. Use specific player names, formation tendencies, and statistical context. Format output with clear headers and structured sections. Be probabilistic — use percentages and confidence levels. Think one step ahead and factor in how the defense adjusts. When recommending plays, stay within the team's actual schematic framework.`,
          messages: [{ role: "user", content: prompt }],
          tools: [{ type: "web_search_20250305", name: "web_search" }],
        }),
      });

      const data = await response.json();
      if (data.error) throw new Error(data.error.message);

      const text = data.content
        ?.filter(b => b.type === "text")
        .map(b => b.text)
        .join("\n") || "No analysis generated.";
      setResult(text);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
    } catch (err) {
      setError(err.message || "Analysis failed. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const canRun = offTeam && defTeam && (!needsPlayer || playerName);

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
          {/* Scanline overlay */}
          <div style={{
            position: "absolute", inset: 0, opacity: 0.03,
            backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.05) 2px, rgba(255,255,255,0.05) 4px)",
            pointerEvents: "none"
          }} />

          {/* Corner brackets */}
          <div style={{ position: "absolute", top: 20, left: 20, width: 40, height: 40, borderTop: "2px solid #d4c89644", borderLeft: "2px solid #d4c89644" }} />
          <div style={{ position: "absolute", top: 20, right: 20, width: 40, height: 40, borderTop: "2px solid #d4c89644", borderRight: "2px solid #d4c89644" }} />
          <div style={{ position: "absolute", bottom: 20, left: 20, width: 40, height: 40, borderBottom: "2px solid #d4c89644", borderLeft: "2px solid #d4c89644" }} />
          <div style={{ position: "absolute", bottom: 20, right: 20, width: 40, height: 40, borderBottom: "2px solid #d4c89644", borderRight: "2px solid #d4c89644" }} />

          <div style={{ width: "100%", maxWidth: 640, padding: "0 32px" }}>
            {BRIEFING_LINES.slice(0, loadingPhase).map((line, i) => {
              const age = elapsed - line.delay;
              const opacity = Math.min(1, age / 400);

              if (line.type === "header") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 700,
                  letterSpacing: 4, color: "#d4c896", marginBottom: 16, opacity,
                  textShadow: "0 0 20px rgba(212,200,150,0.3)",
                  transition: "opacity 0.3s"
                }}>{line.text}</div>
              );

              if (line.type === "classified") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                  color: "#c44", letterSpacing: 3, marginBottom: 6, opacity,
                  display: "flex", alignItems: "center", gap: 8,
                  transition: "opacity 0.3s"
                }}>
                  <span style={{ display: "inline-block", width: 6, height: 6, background: "#c44", borderRadius: "50%", animation: "pulse 1.5s ease-in-out infinite" }} />
                  {line.text}
                </div>
              );

              if (line.type === "meta") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
                  color: "#8a8a7a", marginBottom: 4, opacity,
                  transition: "opacity 0.3s"
                }}>{line.text}</div>
              );

              if (line.type === "divider") return (
                <div key={i} style={{
                  height: 1, margin: "16px 0",
                  background: "linear-gradient(90deg, transparent, rgba(212,200,150,0.15), transparent)",
                  opacity, transition: "opacity 0.3s"
                }} />
              );

              if (line.type === "section") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 12, fontWeight: 600,
                  color: "#d4c896", letterSpacing: 2, marginBottom: 10, opacity,
                  transition: "opacity 0.3s"
                }}>{line.text}</div>
              );

              if (line.type === "rule") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
                  color: "#bbb8a8", marginBottom: 6, paddingLeft: 16, opacity,
                  lineHeight: 1.5, transition: "opacity 0.3s"
                }}>{line.text}</div>
              );

              if (line.type === "status") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                  color: "#6a9955", marginBottom: 5, opacity,
                  display: "flex", alignItems: "center", gap: 8,
                  transition: "opacity 0.3s"
                }}>
                  <span style={{ color: "#6a9955" }}>{">"}</span>
                  {line.text}
                  {i === loadingPhase - 1 && <span style={{ display: "inline-block", width: 6, height: 12, background: "#6a9955", animation: "blink 0.8s step-end infinite" }} />}
                </div>
              );

              if (line.type === "waiting") return (
                <div key={i} style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 12, fontWeight: 600,
                  color: "#d4c896", marginTop: 12, opacity,
                  animation: "pulse 2s ease-in-out infinite",
                  transition: "opacity 0.3s"
                }}>{line.text}</div>
              );

              return null;
            })}

            {/* Progress bar at bottom */}
            <div style={{ marginTop: 28, height: 2, background: "rgba(255,255,255,0.04)", borderRadius: 1, overflow: "hidden" }}>
              <div style={{
                height: "100%", background: "linear-gradient(90deg, #d4c896, #a89860)",
                width: `${Math.min(95, (loadingPhase / BRIEFING_LINES.length) * 100)}%`,
                transition: "width 0.5s ease-out", borderRadius: 1,
                boxShadow: "0 0 8px rgba(212,200,150,0.3)"
              }} />
            </div>

            {/* Timer */}
            <div style={{
              marginTop: 10, fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
              color: "#555", letterSpacing: 1, display: "flex", justifyContent: "space-between"
            }}>
              <span>ELAPSED: {(elapsed / 1000).toFixed(1)}s</span>
              <span>APOLLO CYBERSENTINEL v2.1</span>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{
        padding: "32px 24px 24px", borderBottom: "1px solid rgba(255,255,255,0.04)",
        background: "linear-gradient(180deg, rgba(200,180,120,0.03) 0%, transparent 100%)"
      }}>
        <div style={{ maxWidth: 800, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
            <span style={{ fontSize: 10, fontFamily: "monospace", letterSpacing: 3, color: "#8a8a7a", textTransform: "uppercase" }}>Apollo CyberSentinel</span>
          </div>
          <h1 style={{
            fontSize: 32, fontWeight: 700, margin: 0, letterSpacing: -0.5,
            background: "linear-gradient(135deg, #d4c896, #a89860)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent"
          }}>NFL Playcaller AI</h1>
          <p style={{ color: "#666", fontSize: 13, marginTop: 6, fontWeight: 300 }}>
            Offensive coordinator intelligence — blitz reads, play optimization, scouting reports
          </p>
        </div>
      </div>

      {/* Body */}
      <div style={{ maxWidth: 800, margin: "0 auto", padding: "24px 24px 80px" }}>

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
              Analyzing matchup...
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
            </div>
            <div style={{
              fontSize: 14, lineHeight: 1.75, color: "#ccc", fontFamily: "'IBM Plex Sans', sans-serif",
              whiteSpace: "pre-wrap", wordBreak: "break-word"
            }}>
              {result.split('\n').map((line, i) => {
                if (line.startsWith('# ')) return <h2 key={i} style={{ fontSize: 20, fontWeight: 700, color: "#e8e8d8", margin: "24px 0 12px", borderBottom: "1px solid rgba(255,255,255,0.06)", paddingBottom: 8 }}>{line.slice(2)}</h2>;
                if (line.startsWith('## ')) return <h3 key={i} style={{ fontSize: 16, fontWeight: 600, color: "#d4c896", margin: "20px 0 8px" }}>{line.slice(3)}</h3>;
                if (line.startsWith('### ')) return <h4 key={i} style={{ fontSize: 14, fontWeight: 600, color: "#bbb", margin: "16px 0 6px" }}>{line.slice(4)}</h4>;
                if (line.startsWith('- ')) return <div key={i} style={{ paddingLeft: 16, position: "relative", marginBottom: 4 }}><span style={{ position: "absolute", left: 0, color: "#d4c896" }}>•</span>{line.slice(2)}</div>;
                if (line.startsWith('**') && line.endsWith('**')) return <div key={i} style={{ fontWeight: 600, color: "#e8e8d8", marginTop: 8 }}>{line.slice(2, -2)}</div>;
                if (line.trim() === '') return <div key={i} style={{ height: 8 }} />;
                return <div key={i}>{line}</div>;
              })}
            </div>
          </div>
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
