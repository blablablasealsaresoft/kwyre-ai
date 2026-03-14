#!/usr/bin/env python3
"""
KWYRE — Batch Trace Generator (Anthropic Message Batches API)
=============================================================
Generates reasoning traces using the 50%-cheaper batch API instead of
real-time calls. No real-time rate limiting, async processing.

Two-phase approach:
  Phase 1: Expand 12 seed prompts per domain → TRACES_PER_DOMAIN unique prompts
  Phase 2: Generate full <think>...</think> reasoning traces for all prompts

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 generate_traces_batch.py

    # Override traces per domain (default: 1000)
    KWYRE_TRACES_PER_DOMAIN=500 python3 generate_traces_batch.py

    # Resume interrupted run (state is saved automatically)
    python3 generate_traces_batch.py

    # Skip to phase 2 if expansion already done
    KWYRE_SKIP_EXPANSION=1 python3 generate_traces_batch.py

Cost estimate (claude-sonnet-4, batch pricing):
    Phase 1 (expansion):  ~$1-2
    Phase 2 (6000 traces): ~$28-35
    Total: ~$30-37 for 6,000 traces across 6 domains
"""

import json
import os
import time
import random
from pathlib import Path

import anthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KWYRE_HOME = os.path.expanduser("~/.kwyre")
OUTPUT_DIR  = Path(KWYRE_HOME) / "training-data" / "kwyre-traces"
STATE_FILE  = Path(KWYRE_HOME) / "training-data" / "batch-state.json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TRACES_PER_DOMAIN = int(os.environ.get("KWYRE_TRACES_PER_DOMAIN", "1000"))
SKIP_EXPANSION    = os.environ.get("KWYRE_SKIP_EXPANSION", "0") == "1"
MODEL             = os.environ.get("KWYRE_MODEL_NAME", "claude-sonnet-4-20250514")
POLL_INTERVAL     = int(os.environ.get("KWYRE_POLL_INTERVAL", "60"))  # seconds

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

COT_INSTRUCTION = (
    "\n\nIMPORTANT: Show your complete reasoning process inside <think>...</think> tags FIRST, "
    "then provide your final answer AFTER the closing </think> tag. "
    "Think step by step. Be thorough in your reasoning."
)

# ---------------------------------------------------------------------------
# Domain definitions (6 professional verticals)
# ---------------------------------------------------------------------------
DOMAINS = {
    "legal_compliance": {
        "system": (
            "You are an expert legal analyst specializing in corporate law, "
            "securities regulation, and compliance. You have deep expertise in "
            "NDA analysis, contract review, privilege screening, SEC filings, "
            "FINRA compliance, and regulatory citations. You reason through legal "
            "problems methodically, citing specific statutes, rules, and case law. "
            "You understand the practical implications for small to mid-size firms."
        ),
        "prompts": [
            "Analyze this NDA clause for enforceability issues: a 5-year non-compete with a 200-mile radius for a software engineer in California. Identify the specific legal problems and cite relevant case law.",
            "Walk through the complete process of screening a document production for attorney-client privilege. What are the markers, how do you handle borderline cases, and what's the FRE 502(b) analysis for inadvertent disclosure?",
            "Review a mutual NDA between a SaaS company and a potential acquirer. Identify the 10 most critical clauses, flag common traps, and suggest redlines.",
            "Analyze the SEC Item 105 risk factor disclosure requirements. How do you identify when a company has added risk factors only after adverse events occurred?",
            "Explain FINRA Rule 3110 supervisory requirements for a small broker-dealer. What written supervisory procedures are required and how should a 20-person firm structure compliance?",
            "Evaluate a software licensing agreement for IP assignment vs license scope issues. What are the key differences and how does termination affect IP rights?",
            "Walk through analyzing a merger agreement's MAC clause. What events typically qualify as a Material Adverse Change and how has Delaware Chancery Court interpreted these?",
            "Design a document retention policy for a mid-size law firm. Address ethical obligations, litigation hold procedures, and e-discovery obligations.",
            "Analyze the enforceability of a forum selection clause in a commercial contract. When can these be challenged and how do state-level variations affect enforcement?",
            "Evaluate an employment agreement's non-solicitation clause. Compare enforceability across California, New York, and Texas.",
            "Walk through conducting a conflicts check for a mid-size firm taking on a new M&A client. What databases do you check and when must you decline?",
            "Analyze a SPAC merger proxy statement for SEC compliance. What are the key Regulation S-K disclosure requirements and what red flags suggest inadequate disclosure?",
        ],
    },
    "insurance_actuarial": {
        "system": (
            "You are an expert insurance and reinsurance analyst with deep knowledge "
            "of actuarial science, underwriting, claims processing, treaty structures, "
            "and regulatory compliance. You understand loss development triangles, "
            "reserving methodologies, catastrophe modeling, and Solvency II/RBC frameworks."
        ),
        "prompts": [
            "Analyze a quota share reinsurance treaty with a 40% cession rate and a 35% provisional commission. Walk through how losses, premiums, and commissions flow between cedent and reinsurer.",
            "Walk through building a loss development triangle from raw claims data. Explain link ratios, the chain ladder method, and how to identify development factor anomalies.",
            "Evaluate IBNR reserving methodology for a long-tail casualty book. Compare Bornhuetter-Ferguson vs chain ladder vs Cape Cod methods.",
            "Analyze a catastrophe excess of loss treaty with an annual aggregate deductible. How do reinstatement premiums work and how do you calculate total cost to the cedent?",
            "Design a compliant data handling procedure for cedent PII in a reinsurance due diligence context. How do GDPR and CCPA apply to reinsurance data flows?",
            "Walk through a Solvency II SCR calculation for a mid-size European insurer. Explain the standard formula modules and how to compute the diversification benefit.",
            "Evaluate a P&C insurer's loss reserves where paid-to-incurred ratio has been declining over 3 years while case reserve development has been adverse. What does this pattern suggest?",
            "Analyze a commutation agreement between a cedent and reinsurer. What are the key economic considerations and how do you determine fair value of reserves being commuted?",
            "Design a risk-based capital analysis for a mid-size US insurer. Walk through NAIC RBC formula components and what triggers regulatory action.",
            "Evaluate a reinsurance broker's slip for a property catastrophe program. What terms should the cedent scrutinize and how do hours clauses affect recovery?",
            "Walk through subrogation analysis for a large property loss. How do you evaluate subrogation potential and how does reinsurance affect the cedent's recovery strategy?",
            "Analyze the impact of social inflation on a general liability book. What claim trends signal social inflation and how should reserving actuaries adjust their selections?",
        ],
    },
    "healthcare_lifesciences": {
        "system": (
            "You are an expert healthcare compliance analyst and clinical research specialist. "
            "You understand HIPAA Privacy and Security Rules, clinical trial regulations "
            "(21 CFR Parts 11, 50, 56, 312), FDA submission requirements, medical coding "
            "(ICD-10, CPT), and IRB procedures. You frame all outputs as compliance analysis, "
            "never as medical advice."
        ),
        "prompts": [
            "Analyze a HIPAA Privacy Rule compliance scenario: a mid-size clinic wants to use a cloud-based AI tool for clinical note summarization. Walk through BAA requirements, minimum necessary standard, and de-identification options.",
            "Review a clinical trial protocol for a Phase II oncology study. What are the key elements the IRB will scrutinize and what informed consent requirements apply under 21 CFR 50?",
            "Walk through 21 CFR Part 11 compliance for electronic records in a clinical trial. What system validation requirements apply and what are common FDA 483 observations?",
            "Analyze drug interaction risks for a patient on warfarin, metformin, and lisinopril who is starting amoxicillin. Walk through the CYP450 interactions and monitoring recommendations.",
            "Design a HIPAA breach response plan for a 200-person healthcare organization. Walk through risk assessment, notification timelines (45 CFR 164.408), and OCR reporting thresholds.",
            "Evaluate a 510(k) premarket notification submission for a software as medical device (SaMD). What classification applies, what are the predicate device requirements, and what clinical evidence is needed?",
            "Walk through medical coding validation for a complex surgical case. How do you select ICD-10-PCS codes and what are the common audit triggers?",
            "Analyze informed consent requirements for a multi-site clinical trial enrolling pediatric patients. What additional protections apply under Subpart D and how do assent requirements vary by age?",
            "Design a data governance framework for a health system implementing AI-assisted diagnostic tools. Address HIPAA, state privacy laws, and algorithm transparency requirements.",
            "Evaluate the FDA's approach to real-world evidence for regulatory decision-making. What data sources qualify and what study designs are acceptable?",
            "Walk through CDISC data standard compliance for submitting clinical trial data to the FDA. What are SDTM and ADaM requirements and common validation errors?",
            "Analyze a Stark Law compliance scenario for a physician-owned ASC that refers patients to an imaging center in which the physicians hold equity. Walk through the exceptions and safe harbors.",
        ],
    },
    "defense_intelligence": {
        "system": (
            "You are an expert in defense and intelligence analysis, specializing in "
            "CUI handling procedures, OSINT collection methodology, threat assessment, "
            "and NIST 800-171 compliance. You understand intelligence product formats "
            "(ICD 203, 206), MITRE ATT&CK framework mapping, and OPSEC review procedures. "
            "You never handle classified information but are expert in the unclassified-sensitive space."
        ),
        "prompts": [
            "Walk through CUI marking and handling procedures for a defense subcontractor receiving controlled technical information. What NIST 800-171 controls must be in place and what are the incident reporting requirements?",
            "Design an OSINT collection plan for monitoring a foreign adversary's military buildup. What open sources do you leverage and how do you structure an intelligence product per ICD 203?",
            "Walk through a MITRE ATT&CK framework mapping for a suspected APT campaign targeting defense industrial base contractors. How do you correlate observed TTPs to known threat groups?",
            "Evaluate a supply chain risk assessment for a defense program sourcing electronic components from a country with known counterfeiting issues. What SCRM framework applies?",
            "Design an OPSEC review procedure for a defense contractor's public communications. What information could be aggregated to reveal CUI and how do you evaluate social media policies?",
            "Walk through writing an intelligence assessment on a cyber threat actor targeting the DIB. Structure it per ICD 206 analytic standards: sourcing, confidence levels, alternative analysis.",
            "Analyze NIST 800-171 Rev 3 assessment requirements for a small defense contractor (50 employees). What are the priority controls and how does CMMC Level 2 map to 800-171?",
            "Design a counterintelligence awareness briefing for engineers at a defense subcontractor. What indicators of foreign intelligence targeting should they recognize?",
            "Walk through processing publicly available satellite imagery to assess infrastructure changes at a military facility. What tools apply and how do you communicate uncertainty?",
            "Evaluate the security implications of a defense contractor's use of open-source software components. How does SBOM analysis apply and how does this interact with DFARS 252.204-7012?",
            "Design a threat assessment for a defense industry conference. What physical and cyber threats should organizers consider and what counter-surveillance measures are appropriate?",
            "Walk through declassification review procedures for a historical defense program. What executive orders govern declassification and how do Kyl-Bingaman restrictions apply to imagery?",
        ],
    },
    "financial_trading": {
        "system": (
            "You are an expert quantitative finance analyst specializing in trading strategy "
            "analysis, algorithmic trading systems, market microstructure, risk management, "
            "and regulatory compliance. You understand options pricing, statistical arbitrage, "
            "HFT infrastructure, portfolio optimization, and execution algorithms."
        ),
        "prompts": [
            "Walk through validating a Black-Scholes options pricing model implementation. What are the key assumptions to verify, how do you test for Greeks accuracy, and what market conditions cause the model to break down?",
            "Analyze the market microstructure of a TWAP execution algorithm. How should the algo handle fragmented liquidity across venues and how do you benchmark execution quality against arrival price?",
            "Design a risk management framework for a statistical arbitrage strategy running 500 pairs. What risk metrics should be monitored in real-time and what circuit breakers should auto-flatten positions?",
            "Walk through a Fama-French factor decomposition of a long-short equity portfolio. How do you attribute returns to market, size, value, momentum, and quality factors?",
            "Evaluate a mean reversion strategy's backtest for common pitfalls. Walk through lookahead bias, survivorship bias, transaction cost modeling, and capacity constraints.",
            "Analyze the regulatory requirements for an algorithmic trading firm under Reg SCI and MiFID II. What testing, monitoring, and kill-switch requirements apply?",
            "Design a VaR and CVaR risk monitoring system for a multi-strategy hedge fund. Compare parametric, historical, and Monte Carlo approaches and when does each fail?",
            "Walk through order book dynamics and how a market maker manages inventory risk. How do HFT firms use queue position, adverse selection models, and spread optimization?",
            "Evaluate execution algorithm selection: TWAP vs VWAP vs Implementation Shortfall for a $50M block trade in a mid-cap stock. What are the tradeoffs between market impact and timing risk?",
            "Design a model validation framework for a proprietary trading system. What documentation is required and what statistical tests distinguish a genuinely predictive model from a curve-fit?",
            "Walk through constructing a pairs trading strategy from scratch. How do you screen for cointegrated pairs, set entry/exit thresholds, and handle regime breaks?",
            "Analyze the compliance requirements for a crypto-native trading firm that also trades traditional equities. How do the SEC, CFTC, and FinCEN requirements intersect?",
        ],
    },
    "blockchain_crypto": {
        "system": (
            "You are an expert blockchain forensic analyst, cryptocurrency fraud investigator, "
            "and on-chain intelligence specialist. You combine the analytical precision of a "
            "federal investigator with deep technical knowledge of blockchain protocols, DeFi "
            "mechanics, and cross-chain tracing. You understand wallet graph analysis, token "
            "flow patterns, MEV extraction, and the legal frameworks for building federal "
            "prosecution cases (RICO, wire fraud, BSA/AML)."
        ),
        "prompts": [
            "Walk through the complete methodology for tracing a cryptocurrency money laundering scheme involving chain-hopping from Ethereum to Tron to a no-KYC exchange. What tools do you use at each step and how do you handle mixers?",
            "Analyze a smart contract for rug pull indicators. Walk through bytecode decompilation, identifying hidden mint functions, owner-only withdrawal mechanisms, and liquidity removal patterns.",
            "Build a RICO case framework for a cryptocurrency criminal enterprise operating through multiple shell companies and DeFi protocols. What predicate acts qualify and what on-chain evidence supports the pattern?",
            "Walk through de-anonymizing a Tornado Cash user using timing analysis, deposit-withdrawal correlation, and relay fee patterns. What statistical confidence level do you need for federal court?",
            "Analyze MEV sandwich attacks and front-running on Ethereum. How do searchers monitor the mempool, construct profitable bundles, and interact with block builders?",
            "Design a rug pull detection system that monitors newly deployed tokens in real-time. What contract patterns do you flag, what liquidity metrics trigger alerts, and how do you reduce false positives?",
            "Walk through cross-chain tracing from Ethereum through a bridge to Solana to a DEX to a CEX off-ramp. What tools handle each chain and how do you document the trace for a federal case?",
            "Analyze BSA/AML red flags for a VASP compliance program. Walk through structuring detection, shell company identification, and SAR filing obligations. Reference FinCEN guidance.",
            "Walk through wallet clustering techniques for identifying related addresses controlled by the same entity. Compare common-input-ownership heuristics, behavioral analysis, and timing patterns.",
            "Evaluate a DeFi protocol's smart contracts for flash loan attack vulnerabilities. Walk through the attack vector, price oracle manipulation, and how protocol developers should implement safeguards.",
            "Design an on-chain monitoring system for a fraud investigation tracking $50M across 200+ wallets. What graph database do you use and how do you visualize the flow for a jury?",
            "Walk through building an expert witness report for a cryptocurrency fraud case. What methodology section is required and what are the Daubert standard requirements for blockchain analysis testimony?",
        ],
    },
}

# ---------------------------------------------------------------------------
# State persistence (allows resuming interrupted runs)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}

def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))

# ---------------------------------------------------------------------------
# Batch API helpers
# ---------------------------------------------------------------------------

def submit_batch(requests: list[dict]) -> str:
    """Submit a list of batch requests and return the batch ID."""
    print(f"  Submitting batch with {len(requests):,} requests...")
    response = client.messages.batches.create(requests=requests)
    batch_id = response.id
    print(f"  Batch ID: {batch_id}")
    print(f"  Status: {response.processing_status}")
    return batch_id


def poll_until_done(batch_id: str, label: str = "Batch") -> None:
    """Poll until batch processing_status == 'ended'."""
    print(f"\n  Polling {label} [{batch_id}] every {POLL_INTERVAL}s...")
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        total = counts.processing + counts.succeeded + counts.errored + counts.canceled + counts.expired
        done  = counts.succeeded + counts.errored + counts.canceled + counts.expired
        print(
            f"  [{time.strftime('%H:%M:%S')}] {batch.processing_status} — "
            f"{done}/{total} done "
            f"(ok={counts.succeeded} err={counts.errored} cancel={counts.canceled} exp={counts.expired})"
        )
        if batch.processing_status == "ended":
            break
        time.sleep(POLL_INTERVAL)


def stream_results(batch_id: str) -> list[dict]:
    """Stream and collect all batch results."""
    results = []
    for result in client.messages.batches.results(batch_id):
        results.append(result)
    print(f"  Retrieved {len(results):,} results")
    return results

# ---------------------------------------------------------------------------
# Phase 1: Prompt expansion
# ---------------------------------------------------------------------------

def build_expansion_requests(domains: dict, target_per_domain: int) -> list[dict]:
    """
    Build batch requests to expand 12 seed prompts into target_per_domain unique prompts.
    Each expansion request asks for 12 variations of one seed prompt.
    We need ceil(target_per_domain / 12) expansion calls per seed prompt.
    """
    requests = []
    # variations_per_call * 12 seeds = total prompts; aim slightly above target
    variations_per_call = max(1, (target_per_domain // 12) + 2)

    for domain_name, cfg in domains.items():
        seeds = cfg["prompts"]
        for seed_idx, seed_prompt in enumerate(seeds):
            custom_id = f"exp_{domain_name[:20]}_{seed_idx:02d}"
            requests.append({
                "custom_id": custom_id,
                "params": {
                    "model": MODEL,
                    "max_tokens": 2048,
                    "temperature": 0.95,
                    "system": (
                        "You generate diverse, specific, expert-level question variations "
                        "for professional training data. Each variation must be concrete, "
                        "detailed, and different in focus from the original."
                    ),
                    "messages": [{
                        "role": "user",
                        "content": (
                            f"Generate {variations_per_call} diverse expert-level variations of "
                            f"this question for the domain: {domain_name.replace('_', ' ')}.\n\n"
                            f"Original: {seed_prompt}\n\n"
                            f"Rules:\n"
                            f"- Each variation must be substantively different (different scenario, entity, jurisdiction, or technical focus)\n"
                            f"- Keep professional expert difficulty\n"
                            f"- Return ONLY the questions, one per line, numbered 1-{variations_per_call}.\n"
                            f"- No intro text, no explanations, just the numbered questions."
                        ),
                    }],
                },
            })

    return requests


def parse_expansion_results(
    results: list, domains: dict, target_per_domain: int
) -> dict[str, list[str]]:
    """
    Parse expansion batch results into a dict of domain -> [prompt, ...].
    Falls back to seed prompts for any failed requests.
    """
    # Build lookup: custom_id -> content
    result_map: dict[str, str] = {}
    for r in results:
        if r.result.type == "succeeded":
            result_map[r.custom_id] = r.result.message.content[0].text
        else:
            print(f"  WARNING: expansion request {r.custom_id} failed: {r.result.type}")

    expanded: dict[str, list[str]] = {d: list(cfg["prompts"]) for d, cfg in domains.items()}

    for domain_name, cfg in domains.items():
        seeds = cfg["prompts"]
        for seed_idx in range(len(seeds)):
            custom_id = f"exp_{domain_name[:20]}_{seed_idx:02d}"
            if custom_id not in result_map:
                continue
            raw = result_map[custom_id]
            new_prompts = []
            for line in raw.strip().split("\n"):
                line = line.strip().lstrip("0123456789.)- ").strip()
                if line and len(line) > 20:
                    new_prompts.append(line)
            expanded[domain_name].extend(new_prompts)

        # Shuffle and trim to target
        random.shuffle(expanded[domain_name])
        # If still short, cycle through what we have
        while len(expanded[domain_name]) < target_per_domain:
            expanded[domain_name].extend(expanded[domain_name])
        expanded[domain_name] = expanded[domain_name][:target_per_domain]

    for domain_name, prompts in expanded.items():
        print(f"  {domain_name}: {len(prompts)} prompts ready")

    return expanded

# ---------------------------------------------------------------------------
# Phase 2: Trace generation
# ---------------------------------------------------------------------------

def build_trace_requests(expanded_prompts: dict[str, list[str]], domains: dict) -> list[dict]:
    """Build batch requests for all trace generations."""
    requests = []
    for domain_name, prompts in expanded_prompts.items():
        system_prompt = domains[domain_name]["system"]
        for idx, prompt in enumerate(prompts):
            custom_id = f"tr_{domain_name[:22]}_{idx:04d}"
            requests.append({
                "custom_id": custom_id,
                "params": {
                    "model": MODEL,
                    "max_tokens": 4096,
                    "temperature": 0.7,
                    "system": system_prompt,
                    "messages": [{
                        "role": "user",
                        "content": prompt + COT_INSTRUCTION,
                    }],
                },
            })
    return requests


def parse_trace_results(
    results: list, expanded_prompts: dict[str, list[str]], domains: dict
) -> dict[str, list[dict]]:
    """Parse trace batch results into per-domain trace lists."""
    # Build lookup: custom_id -> message content
    result_map: dict[str, str] = {}
    error_count = 0
    for r in results:
        if r.result.type == "succeeded":
            result_map[r.custom_id] = r.result.message.content[0].text
        else:
            error_count += 1

    if error_count:
        print(f"  WARNING: {error_count} trace requests failed (not billed)")

    traces_by_domain: dict[str, list[dict]] = {d: [] for d in domains}

    for domain_name, prompts in expanded_prompts.items():
        system_prompt = domains[domain_name]["system"]
        for idx, prompt in enumerate(prompts):
            custom_id = f"tr_{domain_name[:22]}_{idx:04d}"
            if custom_id not in result_map:
                continue

            content = result_map[custom_id]
            # Ensure <think> tags present
            if "<think>" not in content:
                lines = content.strip().split("\n")
                last_line = lines[-1] if lines else content
                content = f"<think>\n{content}\n</think>\n\n{last_line}"

            traces_by_domain[domain_name].append({
                "messages": [
                    {"role": "system",    "content": system_prompt},
                    {"role": "user",      "content": prompt},
                    {"role": "assistant", "content": content},
                ]
            })

    return traces_by_domain


def save_traces(traces_by_domain: dict[str, list[dict]]) -> None:
    """Write per-domain JSONL files and combined file."""
    all_traces = []
    for domain_name, traces in traces_by_domain.items():
        out_path = OUTPUT_DIR / f"{domain_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for t in traces:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        print(f"  {domain_name}: {len(traces)} traces → {out_path}")
        all_traces.extend(traces)

    random.shuffle(all_traces)
    combined = OUTPUT_DIR / "kwyre-all-traces.jsonl"
    with open(combined, "w", encoding="utf-8") as f:
        for t in all_traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"\n  Combined: {len(all_traces)} traces → {combined}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*62}")
    print("  KWYRE — Batch Trace Generator (Message Batches API)")
    print(f"  Domains:          {len(DOMAINS)}")
    print(f"  Traces per domain: {TRACES_PER_DOMAIN:,}")
    print(f"  Total targets:    {len(DOMAINS) * TRACES_PER_DOMAIN:,}")
    print(f"  Model:            {MODEL}")
    print(f"  Est. cost:        ~${len(DOMAINS) * TRACES_PER_DOMAIN * 0.006:.0f} (batch pricing)")
    print(f"{'='*62}\n")

    state = load_state()

    # ------------------------------------------------------------------
    # Phase 1: Expand prompts
    # ------------------------------------------------------------------
    expanded_prompts: dict[str, list[str]] | None = None

    if SKIP_EXPANSION and "expanded_prompts" in state:
        print("[Phase 1] SKIPPED — using saved expanded prompts")
        expanded_prompts = state["expanded_prompts"]

    elif "expanded_prompts" in state and state.get("expansion_done"):
        print("[Phase 1] Already complete — loading saved expanded prompts")
        expanded_prompts = state["expanded_prompts"]

    else:
        print("[Phase 1] Building expansion batch...")
        expansion_requests = build_expansion_requests(DOMAINS, TRACES_PER_DOMAIN)
        print(f"  {len(expansion_requests)} expansion requests ({len(DOMAINS)} domains × {len(list(DOMAINS.values())[0]['prompts'])} seeds)")

        if "expansion_batch_id" in state and not state.get("expansion_done"):
            expansion_batch_id = state["expansion_batch_id"]
            print(f"  Resuming existing expansion batch: {expansion_batch_id}")
        else:
            expansion_batch_id = submit_batch(expansion_requests)
            state["expansion_batch_id"] = expansion_batch_id
            state["expansion_done"] = False
            save_state(state)

        poll_until_done(expansion_batch_id, "Phase 1 — Expansion")

        print("\n  Downloading expansion results...")
        expansion_results = stream_results(expansion_batch_id)
        expanded_prompts = parse_expansion_results(expansion_results, DOMAINS, TRACES_PER_DOMAIN)

        state["expanded_prompts"] = expanded_prompts
        state["expansion_done"] = True
        save_state(state)
        print("[Phase 1] Complete.\n")

    # ------------------------------------------------------------------
    # Phase 2: Generate traces
    # ------------------------------------------------------------------
    if state.get("trace_done"):
        print("[Phase 2] Already complete — loading saved traces")
        # Re-parse from the stored batch if needed
        trace_batch_id = state.get("trace_batch_id")
        if trace_batch_id:
            print(f"  Re-downloading results from {trace_batch_id} ...")
            trace_results = stream_results(trace_batch_id)
            traces_by_domain = parse_trace_results(trace_results, expanded_prompts, DOMAINS)
            save_traces(traces_by_domain)
    else:
        print("[Phase 2] Building trace generation batch...")
        trace_requests = build_trace_requests(expanded_prompts, DOMAINS)
        total_req = len(trace_requests)
        print(f"  {total_req:,} trace requests across {len(DOMAINS)} domains")

        if "trace_batch_id" in state and not state.get("trace_done"):
            trace_batch_id = state["trace_batch_id"]
            print(f"  Resuming existing trace batch: {trace_batch_id}")
        else:
            trace_batch_id = submit_batch(trace_requests)
            state["trace_batch_id"] = trace_batch_id
            state["trace_done"] = False
            save_state(state)

        poll_until_done(trace_batch_id, "Phase 2 — Traces")

        print("\n  Downloading trace results...")
        trace_results = stream_results(trace_batch_id)
        traces_by_domain = parse_trace_results(trace_results, expanded_prompts, DOMAINS)
        save_traces(traces_by_domain)

        state["trace_done"] = True
        save_state(state)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    total = sum(
        sum(1 for _ in open(OUTPUT_DIR / f"{d}.jsonl"))
        for d in DOMAINS
        if (OUTPUT_DIR / f"{d}.jsonl").exists()
    )
    print(f"\n{'='*62}")
    print("  COMPLETE")
    print(f"  Total traces written: {total:,}")
    print(f"  Output directory: {OUTPUT_DIR}")
    print(f"  State file: {STATE_FILE}")
    print("")
    print("  Next step — train domain adapters:")
    print("    bash training/scripts/run_all_domains.sh")
    print(f"{'='*62}\n")


if __name__ == "__main__":
    main()
