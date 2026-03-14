#!/usr/bin/env python3
"""
KWYRE — Parallel Reasoning Trace Generator
Runs all domains simultaneously using ThreadPoolExecutor.
"""

import json
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

KWYRE_HOME = os.path.expanduser("~/.kwyre")
OUTPUT_DIR = os.path.join(KWYRE_HOME, "training-data", "kwyre-traces")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TRACES_PER_DOMAIN = int(os.environ.get("KWYRE_TRACES_PER_DOMAIN", "50"))

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = os.environ.get("KWYRE_MODEL_NAME", "claude-sonnet-4-20250514")
print(f"Using Anthropic {MODEL} API (parallel mode)")
print(f"Traces per domain: {TRACES_PER_DOMAIN}")

COT_INSTRUCTION = (
    "\n\nIMPORTANT: Show your complete reasoning process inside <think>...</think> tags FIRST, "
    "then provide your final answer AFTER the closing </think> tag. "
    "Think step by step. Be thorough in your reasoning."
)

_print_lock = threading.Lock()

def log(domain, msg):
    with _print_lock:
        print(f"  [{domain}] {msg}", flush=True)


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
            "Analyze the SEC Item 105 risk factor disclosure requirements. How do you identify when a company has added risk factors only after adverse events occurred? What's the framework for evaluating belated disclosure?",
            "Explain FINRA Rule 3110 supervisory requirements for a small broker-dealer. What written supervisory procedures are required, what are common exam findings, and how should a 20-person firm structure compliance?",
            "Evaluate a software licensing agreement for IP assignment vs license scope issues. What are the key differences, what should the licensee watch for, and how does termination affect IP rights?",
            "Walk through analyzing a merger agreement's MAC clause. What events typically qualify as a Material Adverse Change, how has Delaware Chancery Court interpreted these, and what should a buyer negotiate?",
            "Design a document retention policy for a mid-size law firm. Address ethical obligations, litigation hold procedures, and the intersection with e-discovery obligations.",
            "Analyze the enforceability of a forum selection clause in a commercial contract. When can these be challenged, what's the Bremen v. Zapata framework, and how do state-level variations affect enforcement?",
            "Evaluate an employment agreement's non-solicitation clause. Compare enforceability across California, New York, and Texas. What are the practical implications for a departing employee at a 50-person firm?",
            "Walk through conducting a conflicts check for a mid-size firm taking on a new M&A client. What databases do you check, what are the ethical walls requirements, and when must you decline?",
            "Analyze a SPAC merger proxy statement for SEC compliance. What are the key disclosure requirements under Regulation S-K, and what red flags suggest inadequate disclosure?",
        ]
    },
    "insurance_actuarial": {
        "system": (
            "You are an expert insurance and reinsurance analyst with deep knowledge "
            "of actuarial science, underwriting, claims processing, treaty structures, "
            "and regulatory compliance. You understand loss development triangles, "
            "reserving methodologies, catastrophe modeling, and Solvency II/RBC frameworks. "
            "You speak the language of cedents, retrocessionaires, and reinsurance brokers. "
            "You handle PII with extreme care and understand compliance requirements."
        ),
        "prompts": [
            "Analyze a quota share reinsurance treaty with a 40% cession rate and a 35% provisional commission. Walk through how losses, premiums, and commissions flow between cedent and reinsurer. When does the sliding scale commission adjust?",
            "Walk through building a loss development triangle from raw claims data. Explain link ratios, the chain ladder method, and how to identify development factor anomalies that suggest reserve manipulation.",
            "Evaluate IBNR reserving methodology for a long-tail casualty book. Compare Bornhuetter-Ferguson vs chain ladder vs Cape Cod methods. When is each appropriate and what are the failure modes?",
            "Analyze a catastrophe excess of loss treaty with an annual aggregate deductible. How do reinstatement premiums work, what happens after the first event exhausts the layer, and how do you calculate the total cost to the cedent?",
            "Design a compliant data handling procedure for cedent PII in a reinsurance due diligence context. What data can be shared, what must be anonymized, and how do GDPR and CCPA apply to reinsurance data flows?",
            "Walk through a Solvency II Solvency Capital Requirement calculation for a mid-size European insurer. Explain the standard formula modules, how to compute the diversification benefit, and common pitfalls.",
            "Evaluate the adequacy of a P&C insurer's loss reserves given that their paid-to-incurred ratio has been declining over 3 years while their case reserve development has been adverse. What does this pattern suggest?",
            "Analyze a commutation agreement between a cedent and reinsurer. What are the key economic considerations, how do you determine fair value of reserves being commuted, and what are the accounting implications?",
            "Design a risk-based capital analysis for a mid-size US insurer. Walk through the NAIC RBC formula components, what triggers regulatory action, and how management should respond to a declining RBC ratio.",
            "Evaluate a reinsurance broker's slip for a property catastrophe program. What terms should the cedent scrutinize, what are common coverage gaps in cat XL programs, and how do hours clauses affect recovery?",
            "Walk through subrogation analysis for a large property loss. How do you evaluate subrogation potential, what are the common barriers, and how does the presence of reinsurance affect the cedent's recovery strategy?",
            "Analyze the impact of social inflation on a general liability book. What claim trends signal social inflation, how should reserving actuaries adjust their selections, and what should underwriters do about pricing?",
        ]
    },
    "healthcare_lifesciences": {
        "system": (
            "You are an expert healthcare compliance analyst and clinical research "
            "specialist. You understand HIPAA Privacy and Security Rules, clinical "
            "trial regulations (21 CFR Parts 11, 50, 56, 312), FDA submission "
            "requirements, medical coding (ICD-10, CPT), drug interaction analysis, "
            "and IRB procedures. You frame all outputs as compliance analysis, never "
            "as medical advice. You handle PHI with extreme sensitivity."
        ),
        "prompts": [
            "Analyze a HIPAA Privacy Rule compliance scenario: a mid-size clinic wants to use a cloud-based AI tool for clinical note summarization. Walk through the Business Associate Agreement requirements, minimum necessary standard, and de-identification options under Safe Harbor and Expert Determination methods.",
            "Review a clinical trial protocol for a Phase II oncology study. What are the key elements the IRB will scrutinize, what informed consent requirements apply under 21 CFR 50, and how should adverse events be reported?",
            "Walk through 21 CFR Part 11 compliance for electronic records in a clinical trial. What system validation requirements apply, how must audit trails be maintained, and what are common FDA 483 observations?",
            "Analyze drug interaction risks for a patient on warfarin, metformin, and lisinopril who is starting amoxicillin. Walk through the pharmacological mechanisms, CYP450 interactions, and monitoring recommendations.",
            "Design a HIPAA breach response plan for a 200-person healthcare organization. Walk through the risk assessment, notification timelines (45 CFR 164.408), breach documentation requirements, and OCR reporting thresholds.",
            "Evaluate a 510(k) premarket notification submission for a software as medical device (SaMD). What classification does it fall under, what are the predicate device requirements, and what clinical evidence is needed?",
            "Walk through medical coding validation for a complex surgical case. How do you select appropriate ICD-10-PCS codes, what documentation supports medical necessity, and what are the common audit triggers?",
            "Analyze informed consent requirements for a multi-site clinical trial enrolling pediatric patients. What additional protections apply under Subpart D (21 CFR 50), and how do assent requirements vary by age?",
            "Design a data governance framework for a health system implementing AI-assisted diagnostic tools. Address HIPAA, state privacy laws, algorithm transparency requirements, and clinician liability.",
            "Evaluate the FDA's approach to real-world evidence for regulatory decision-making. What data sources qualify, what study designs are acceptable, and how does this apply to post-market surveillance?",
            "Walk through CDISC data standard compliance for submitting clinical trial data to the FDA. What are the SDTM and ADaM requirements, common validation errors, and the review division's expectations?",
            "Analyze a Stark Law compliance scenario for a physician-owned ASC that refers patients to an imaging center in which the physicians hold equity. Walk through the exceptions and safe harbors.",
        ]
    },
    "defense_intelligence": {
        "system": (
            "You are an expert in defense and intelligence analysis, specializing in "
            "CUI handling procedures, OSINT collection methodology, threat assessment, "
            "and NIST 800-171 compliance. You understand intelligence product formats "
            "(ICD 203, 206), MITRE ATT&CK framework mapping, OPSEC review procedures, "
            "and supply chain risk assessment. You never handle classified information "
            "but are expert in the unclassified-but-sensitive space where most defense "
            "contractors and analysts operate."
        ),
        "prompts": [
            "Walk through CUI marking and handling procedures for a defense subcontractor receiving controlled technical information from a prime. What NIST 800-171 controls must be in place, how should documents be marked, and what are the incident reporting requirements?",
            "Design an OSINT collection plan for monitoring a foreign adversary's military buildup along a contested border. What open sources do you leverage, how do you validate satellite imagery claims on social media, and how do you structure an intelligence product per ICD 203?",
            "Walk through a MITRE ATT&CK framework mapping for a suspected APT campaign targeting defense industrial base contractors. How do you correlate observed TTPs to known threat groups, and what defensive recommendations follow?",
            "Evaluate a supply chain risk assessment for a defense program that sources electronic components from a country with known counterfeiting issues. What SCRM framework applies, what testing should be performed, and how do SAM entity validation requirements factor in?",
            "Design an OPSEC review procedure for a defense contractor's public communications. What information could be aggregated to reveal CUI, how do you evaluate social media policies, and what training should employees receive?",
            "Walk through writing an intelligence assessment on a cyber threat actor targeting the DIB. Structure it per ICD 206 analytic standards: sourcing, confidence levels, alternative analysis, and key assumptions.",
            "Analyze NIST 800-171 Rev 3 assessment requirements for a small defense contractor (50 employees). What are the priority controls, how does CMMC Level 2 map to 800-171, and what's the realistic timeline and cost for compliance?",
            "Design a counterintelligence awareness briefing for engineers at a defense subcontractor. What indicators of foreign intelligence targeting should they recognize, and what reporting procedures apply?",
            "Walk through processing publicly available satellite imagery to assess infrastructure changes at a military facility. What tools and techniques apply, how do you estimate dimensions and capabilities, and how do you communicate uncertainty?",
            "Evaluate the security implications of a defense contractor's use of open-source software components. How does SBOM analysis apply, what are the known-vulnerability scanning requirements, and how does this interact with DFARS 252.204-7012?",
            "Design a threat assessment for a defense industry conference. What physical and cyber threats should organizers consider, how do you evaluate attendee risks, and what counter-surveillance measures are appropriate?",
            "Walk through declassification review procedures for a historical defense program. What executive orders govern declassification, how do Kyl-Bingaman restrictions apply to imagery, and what equity reviews are required?",
        ]
    },
    "financial_trading": {
        "system": (
            "You are an expert quantitative finance analyst specializing in trading "
            "strategy analysis, algorithmic trading systems, market microstructure, "
            "risk management, and regulatory compliance. You understand options "
            "pricing, statistical arbitrage, HFT infrastructure, portfolio "
            "optimization, and execution algorithms. You help firms analyze, document, "
            "and validate their existing strategies without ever seeing the actual "
            "proprietary code. You focus on methodology review and risk assessment."
        ),
        "prompts": [
            "Walk through validating a Black-Scholes options pricing model implementation. What are the key assumptions to verify, how do you test for Greeks accuracy, and what market conditions cause the model to break down? Focus on what a quant fund's compliance review should check.",
            "Analyze the market microstructure of a TWAP execution algorithm. How should the algo handle fragmented liquidity across venues, what anti-gaming measures should be implemented, and how do you benchmark execution quality against arrival price?",
            "Design a risk management framework for a statistical arbitrage strategy running 500 pairs. What risk metrics should be monitored in real-time, how do you detect regime changes, and what circuit breakers should auto-flatten positions?",
            "Walk through a Fama-French factor decomposition of a long-short equity portfolio. How do you attribute returns to market, size, value, momentum, and quality factors? What residual alpha is statistically significant?",
            "Evaluate a mean reversion strategy's backtest for common pitfalls. Walk through lookahead bias, survivorship bias, transaction cost modeling, capacity constraints, and the difference between in-sample and out-of-sample performance.",
            "Analyze the regulatory requirements for an algorithmic trading firm under Reg SCI and MiFID II. What testing, monitoring, and kill-switch requirements apply? How should the firm document its algorithms for regulatory examination?",
            "Design a VaR and CVaR risk monitoring system for a multi-strategy hedge fund. Compare parametric, historical, and Monte Carlo approaches. When does each fail, and how should the risk team supplement VaR with stress testing?",
            "Walk through order book dynamics and how a market maker manages inventory risk. How do HFT firms use queue position, adverse selection models, and spread optimization? What does the academic literature say about optimal market making?",
            "Evaluate execution algorithm selection: TWAP vs VWAP vs Implementation Shortfall for a $50M block trade in a mid-cap stock. What are the tradeoffs between market impact, timing risk, and opportunity cost?",
            "Design a model validation framework for a proprietary trading system. What documentation is required, how should you structure independent review, and what statistical tests distinguish a genuinely predictive model from a curve-fit?",
            "Walk through constructing a pairs trading strategy from scratch. How do you screen for cointegrated pairs, set entry/exit thresholds, handle regime breaks, and size positions to control for correlation risk?",
            "Analyze the compliance requirements for a crypto-native trading firm that also trades traditional equities. How do the SEC, CFTC, and FinCEN requirements intersect? What record-keeping and surveillance obligations apply?",
        ]
    },
    "blockchain_crypto": {
        "system": (
            "You are an expert blockchain forensic analyst, cryptocurrency fraud "
            "investigator, and on-chain intelligence specialist. You combine the "
            "analytical precision of a federal investigator with deep technical "
            "knowledge of blockchain protocols, DeFi mechanics, and cross-chain "
            "tracing. You understand wallet graph analysis, token flow patterns, "
            "MEV extraction, and the legal frameworks for building federal "
            "prosecution cases (RICO, wire fraud, BSA/AML). You are technically "
            "precise and forensically rigorous."
        ),
        "prompts": [
            "Walk through the complete methodology for tracing a cryptocurrency money laundering scheme involving chain-hopping from Ethereum to Tron to a no-KYC exchange. What tools do you use at each step, how do you handle mixers, and what evidence preservation is required?",
            "Analyze a smart contract for rug pull indicators. Walk through bytecode decompilation, identifying hidden mint functions, owner-only withdrawal mechanisms, and liquidity removal patterns. What on-chain signals appear before the pull?",
            "Build a RICO case framework for a cryptocurrency criminal enterprise operating through multiple shell companies and DeFi protocols. What predicate acts qualify, how do you establish the enterprise element, and what on-chain evidence supports the pattern of racketeering?",
            "Walk through de-anonymizing a Tornado Cash user using timing analysis, deposit-withdrawal correlation, relay fee patterns, and cross-referencing with CEX deposits. What statistical confidence level do you need for federal court?",
            "Analyze MEV sandwich attacks and front-running on Ethereum. How do searchers monitor the mempool, construct profitable bundles, and interact with block builders? What on-chain evidence identifies a sandwich attacker?",
            "Design a rug pull detection system that monitors newly deployed tokens in real-time. What contract patterns do you flag, what liquidity metrics trigger alerts, and how do you reduce false positives on legitimate launches?",
            "Walk through cross-chain tracing from Ethereum through a bridge to Solana to a DEX to a CEX off-ramp. What tools handle each chain, where do you lose the trail, and how do you document the trace for a federal case?",
            "Analyze BSA/AML red flags for a VASP compliance program. Walk through structuring detection, shell company identification, transaction monitoring rules, and SAR filing obligations. Reference FinCEN guidance specifically.",
            "Walk through wallet clustering techniques for identifying related addresses controlled by the same entity. Compare common-input-ownership heuristics, behavioral analysis, and timing patterns. When do these methods fail?",
            "Evaluate a DeFi protocol's smart contracts for flash loan attack vulnerabilities. Walk through the attack vector, price oracle manipulation, and how protocol developers should implement safeguards.",
            "Design an on-chain monitoring system for a fraud investigation tracking $50M across 200+ wallets. What graph database do you use, how do you handle the data pipeline, and how do you visualize the flow for a jury?",
            "Walk through building an expert witness report for a cryptocurrency fraud case. What methodology section is required, how do you present on-chain evidence to a non-technical jury, and what are the Daubert standard requirements for blockchain analysis testimony?",
        ]
    },
    "sports_analytics": {
        "system": "You are an expert sports analytics professional specializing in NFL play calling, coverage and blitz prediction, scouting reports, player movement profiling, playbook analysis, and situational game theory. You provide data-driven analysis with statistical rigor.",
        "prompts": [
            "Walk through the decision framework for a 4th-and-2 at midfield in the first quarter. What situational factors matter, and how do analytics models weigh go vs punt vs field goal?",
            "Explain how to build a blitz prediction model using pre-snap alignment, formation tendencies, and down-and-distance. What features have the highest predictive value?",
            "Analyze a scouting report on a college quarterback. What metrics and film markers should you prioritize for projecting NFL success?",
            "Describe the methodology for identifying coverage shells (Cover 0, 1, 2, 3, 4) from all-22 film. What alignment and rotation cues matter most?",
            "Walk through player tracking data analysis for route efficiency. How do you measure separation, yards after catch potential, and route depth consistency?",
            "Explain situational game theory for two-minute drill play calling. How do clock management, timeouts, and field position interact?",
            "Design a playbook analysis framework for identifying tendencies by formation, personnel, and field zone. What sample sizes are needed for reliable inference?",
            "Walk through building a run/pass tendency model for a specific defensive coordinator. What historical data do you need and how do you weight recent vs older games?",
            "Analyze the tradeoffs between man and zone coverage in red zone situations. What personnel and formation factors drive the optimal choice?",
            "Explain how to profile edge rushers using pressure rate, win rate, and double-team frequency. What metrics predict sack production?",
            "Walk through third-down conversion optimization. How do you balance run vs pass, play-action frequency, and target distribution by down and distance?",
            "Design a player movement profiling system for identifying route concepts from tracking data. How do you cluster similar routes and detect route variations?",
        ]
    },
    "relationship_matching": {
        "system": "You are an expert in personality psychology and relationship science. You specialize in Big Five personality analysis, attachment style detection, love language identification, compatibility scoring, and evidence-based relationship coaching. You provide nuanced, research-backed analysis.",
        "prompts": [
            "Walk through administering and interpreting a Big Five personality assessment. What do high vs low scores on each dimension indicate, and how do you communicate results sensitively?",
            "Explain the four attachment styles (secure, anxious, avoidant, fearful-avoidant) and how they manifest in dating and long-term relationships.",
            "Analyze compatibility between two profiles: one high in Openness and Neuroticism, the other high in Conscientiousness and low in Neuroticism. What strengths and friction points would you predict?",
            "Describe the five love languages and how to identify a person's primary language from behavior and self-report.",
            "Walk through evidence-based relationship coaching for a couple with mismatched attachment styles. What interventions are supported by research?",
            "Explain how to generate conversation starters that align with someone's personality profile. What topics and framing work for high vs low Openness?",
            "Analyze the research on personality similarity vs complementarity in long-term relationship satisfaction. When does each matter more?",
            "Walk through designing a compatibility scoring algorithm. What dimensions should be weighted, and how do you handle missing or inconsistent data?",
            "Describe the signs of anxious-avoidant trap dynamics and how to coach both partners toward more secure functioning.",
            "Explain how attachment style affects conflict resolution. What communication patterns are typical for each style, and how can partners adapt?",
            "Walk through assessing relationship readiness. What psychological and situational factors indicate someone is prepared for commitment?",
            "Analyze the role of shared values vs personality fit in long-term compatibility. How do you help clients prioritize when these conflict?",
        ]
    },
}


def call_api(system_prompt, user_prompt, max_tokens=2048, temperature=0.6, retries=3):
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e):
                wait = 30 * (attempt + 1)
                log("API", f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise Exception("Max retries exceeded")


def expand_prompts(domain_name, prompts, count):
    if count <= len(prompts):
        return prompts[:count]
    expanded = list(prompts)
    while len(expanded) < count:
        seed = random.choice(prompts)
        try:
            content = call_api(
                "You generate diverse question variations.",
                f"Generate 5 diverse variations of this problem/question. Make them progressively harder. Return ONLY the questions, one per line, numbered 1-5.\n\nOriginal: {seed}",
                max_tokens=2048, temperature=0.9,
            )
            new_prompts = [
                line.strip().lstrip("0123456789.)- ")
                for line in content.strip().split("\n")
                if line.strip() and len(line.strip()) > 20
            ]
            expanded.extend(new_prompts)
            log(domain_name, f"Expanded: {len(expanded)}/{count} prompts")
        except Exception as e:
            log(domain_name, f"Expansion error: {e}")
            time.sleep(2)
    return expanded[:count]


def generate_single_trace(system_prompt, user_prompt):
    enhanced_prompt = user_prompt + COT_INSTRUCTION
    content = call_api(system_prompt, enhanced_prompt)
    if "<think>" in content and "</think>" in content:
        formatted = content
    else:
        lines = content.strip().split("\n")
        last_line = lines[-1] if lines else content
        formatted = f"<think>\n{content}\n</think>\n\n{last_line}"
    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": formatted},
        ]
    }


def process_domain(domain_name, domain_config):
    """Process one domain end-to-end. Called in parallel."""
    output_file = os.path.join(OUTPUT_DIR, f"{domain_name}.jsonl")
    log(domain_name, f"Starting ({TRACES_PER_DOMAIN} traces)")

    prompts = expand_prompts(domain_name, domain_config["prompts"], TRACES_PER_DOMAIN)
    log(domain_name, f"Got {len(prompts)} prompts. Generating traces...")

    traces = []
    for i, prompt in enumerate(prompts):
        t0 = time.time()
        try:
            trace = generate_single_trace(domain_config["system"], prompt)
            elapsed = time.time() - t0
            traces.append(trace)
            content_len = len(trace["messages"][-1]["content"])
            log(domain_name, f"[{i+1}/{len(prompts)}] OK ({elapsed:.0f}s, {content_len} chars)")
        except Exception as e:
            elapsed = time.time() - t0
            log(domain_name, f"[{i+1}/{len(prompts)}] FAILED ({elapsed:.0f}s): {e}")

        if (i + 1) % 5 == 0:
            with open(output_file, "w", encoding="utf-8") as f:
                for t in traces:
                    f.write(json.dumps(t, ensure_ascii=False) + "\n")
        time.sleep(3)

    with open(output_file, "w", encoding="utf-8") as f:
        for t in traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    log(domain_name, f"COMPLETE: {len(traces)} traces saved")
    return domain_name, traces


def main():
    target_domain = os.environ.get("KWYRE_DOMAIN", "").strip()
    if target_domain and target_domain in DOMAINS:
        active_domains = {target_domain: DOMAINS[target_domain]}
    else:
        active_domains = DOMAINS

    print(f"\n{'='*60}")
    print("  KWYRE — Parallel Trace Generation")
    print(f"  Domains: {len(active_domains)}" + (f" (filtered: {target_domain})" if target_domain and target_domain in DOMAINS else ""))
    print(f"  Traces/domain: {TRACES_PER_DOMAIN}")
    print(f"  Total: ~{len(active_domains) * TRACES_PER_DOMAIN} traces")
    print(f"{'='*60}\n")

    all_traces = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(process_domain, name, config): name
            for name, config in active_domains.items()
        }
        for future in as_completed(futures):
            domain_name = futures[future]
            try:
                name, traces = future.result()
                all_traces.extend(traces)
                log(name, f"Finished with {len(traces)} traces")
            except Exception as e:
                log(domain_name, f"DOMAIN FAILED: {e}")

    elapsed = time.time() - t0
    combined_file = os.path.join(OUTPUT_DIR, "kwyre-all-traces.jsonl")
    random.shuffle(all_traces)
    with open(combined_file, "w", encoding="utf-8") as f:
        for t in all_traces:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"  COMPLETE: {len(all_traces)} traces in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Combined: {combined_file}")
    print(f"  Est cost: ~${len(all_traces) * 0.01:.2f}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
