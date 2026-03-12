# Kwyre Domain Adapters — Training Plan & Implementation

## Architecture: Hot-Swappable LoRA

```
Customer installs:
  Base model (Qwen3-4B or Qwen3.5-9B)  →  ~2.5 GB or ~7.6 GB
  + Domain adapter (LoRA weights)        →  ~50-200 MB each

Runtime:
  POST /v1/adapter/load   { "domain": "legal" }
  POST /v1/adapter/unload
  GET  /v1/adapter/status
```

Each adapter is a PEFT LoRA checkpoint (~50-200 MB) that hot-loads onto the
base model at runtime. No restart required. Customers can switch domains or
stack adapters.

---

## 1. Server-Side: Runtime Adapter Selection

### New env variables

```
KWYRE_ADAPTER_DIR=~/.kwyre/adapters       # directory containing domain adapters
KWYRE_DEFAULT_ADAPTER=                     # auto-load on startup (optional)
KWYRE_ALLOW_ADAPTER_SWAP=1                # allow runtime swap via API
```

### Adapter directory structure

```
~/.kwyre/adapters/
├── legal/
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   └── metadata.json              # domain name, version, base model compatibility
├── insurance/
│   ├── adapter_config.json
│   ├── adapter_model.safetensors
│   └── metadata.json
├── healthcare/
│   └── ...
├── defense/
│   └── ...
├── financial-trading/
│   └── ...
└── blockchain/
    └── ...
```

### metadata.json (per adapter)

```json
{
  "domain": "legal",
  "display_name": "Legal & Compliance",
  "version": "1.0.0",
  "base_models": ["Qwen/Qwen3-4B", "Qwen/Qwen3.5-9B"],
  "lora_rank": 32,
  "training_traces": 300,
  "training_date": "2026-03-15",
  "description": "NDA analysis, contract review, privilege screening, SEC filings, FINRA compliance"
}
```

### Server code addition (serve_local_4bit.py)

Add after the existing model loading block. The key insight: PEFT's
`set_adapter` and `delete_adapter` let you swap LoRA weights without
reloading the base model.

```python
# ---------------------------------------------------------------------------
# Domain Adapter Manager (Hot-Swap LoRA)
# ---------------------------------------------------------------------------
import threading
from peft import PeftModel, PeftConfig

ADAPTER_DIR = os.environ.get("KWYRE_ADAPTER_DIR",
    os.path.join(os.path.expanduser("~"), ".kwyre", "adapters"))
ALLOW_ADAPTER_SWAP = os.environ.get("KWYRE_ALLOW_ADAPTER_SWAP", "1") == "1"

_adapter_lock = threading.Lock()
_active_adapter = None        # name of currently loaded adapter
_base_model_ref = model       # reference to the un-adapted base model
_adapted_model = None         # PeftModel wrapper (or None if no adapter)

def _list_available_adapters():
    """Scan adapter directory for valid PEFT checkpoints."""
    adapters = {}
    if not os.path.isdir(ADAPTER_DIR):
        return adapters
    for name in os.listdir(ADAPTER_DIR):
        adapter_path = os.path.join(ADAPTER_DIR, name)
        config_path = os.path.join(adapter_path, "adapter_config.json")
        if os.path.isfile(config_path):
            meta_path = os.path.join(adapter_path, "metadata.json")
            meta = {}
            if os.path.isfile(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
            adapters[name] = {
                "path": adapter_path,
                "metadata": meta,
            }
    return adapters

def load_adapter(domain_name: str) -> dict:
    """Load a domain LoRA adapter onto the base model. Thread-safe."""
    global _active_adapter, _adapted_model, model

    with _adapter_lock:
        available = _list_available_adapters()
        if domain_name not in available:
            return {"error": f"Adapter '{domain_name}' not found",
                    "available": list(available.keys())}

        adapter_path = available[domain_name]["path"]

        # If same adapter already loaded, no-op
        if _active_adapter == domain_name:
            return {"status": "already_loaded", "adapter": domain_name}

        # Unload existing adapter first
        if _adapted_model is not None:
            _adapted_model.unload()
            _adapted_model = None
            _active_adapter = None
            print(f"[Adapter] Unloaded previous adapter")

        # Load new adapter
        try:
            _adapted_model = PeftModel.from_pretrained(
                _base_model_ref, adapter_path
            )
            if os.environ.get("KWYRE_MERGE_LORA", "0") == "1":
                _adapted_model = _adapted_model.merge_and_unload()
                print(f"[Adapter] Loaded and merged: {domain_name}")
            else:
                _adapted_model.eval()
                print(f"[Adapter] Loaded in-place: {domain_name}")

            # Swap the global model reference
            model = _adapted_model
            _active_adapter = domain_name
            return {
                "status": "loaded",
                "adapter": domain_name,
                "metadata": available[domain_name].get("metadata", {}),
            }
        except Exception as e:
            # Restore base model on failure
            model = _base_model_ref
            _active_adapter = None
            return {"error": str(e)}

def unload_adapter() -> dict:
    """Remove active adapter, revert to base model."""
    global _active_adapter, _adapted_model, model

    with _adapter_lock:
        if _active_adapter is None:
            return {"status": "no_adapter_loaded"}

        prev = _active_adapter
        if _adapted_model is not None:
            _adapted_model.unload()
            _adapted_model = None
        model = _base_model_ref
        _active_adapter = None
        print(f"[Adapter] Unloaded: {prev}")
        return {"status": "unloaded", "previous": prev}


# --- API Routes ---

@app.route("/v1/adapter/list", methods=["GET"])
def adapter_list():
    available = _list_available_adapters()
    return jsonify({
        "active": _active_adapter,
        "available": {
            name: info.get("metadata", {})
            for name, info in available.items()
        }
    })

@app.route("/v1/adapter/load", methods=["POST"])
def adapter_load():
    if not ALLOW_ADAPTER_SWAP:
        return jsonify({"error": "Adapter swap disabled"}), 403
    data = request.get_json() or {}
    domain = data.get("domain", "")
    if not domain:
        return jsonify({"error": "Missing 'domain' field"}), 400
    result = load_adapter(domain)
    status_code = 200 if "error" not in result else 404
    return jsonify(result), status_code

@app.route("/v1/adapter/unload", methods=["POST"])
def adapter_unload():
    if not ALLOW_ADAPTER_SWAP:
        return jsonify({"error": "Adapter swap disabled"}), 403
    return jsonify(unload_adapter())

@app.route("/v1/adapter/status", methods=["GET"])
def adapter_status():
    return jsonify({
        "active_adapter": _active_adapter,
        "base_model": ACTIVE_TIER["name"],
        "merge_mode": os.environ.get("KWYRE_MERGE_LORA", "0") == "1",
    })


# Auto-load default adapter on startup
_default_adapter = os.environ.get("KWYRE_DEFAULT_ADAPTER", "")
if _default_adapter:
    print(f"[Adapter] Auto-loading default: {_default_adapter}")
    load_adapter(_default_adapter)
```

### Chat UI integration

Add adapter selector dropdown to `chat/main.html` toolbar. On change,
POST to `/v1/adapter/load`. Show active adapter as a badge next to the
model name in the header.

---

## 2. Trace Generation — All 6 Domains

Each domain gets 300 traces via Claude claude-sonnet-4-20250514. Add these domain configs
to `generate_traces_parallel.py`:

### Domain 1: Legal & Compliance

```python
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
```

### Domain 2: Insurance & Actuarial

```python
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
```

### Domain 3: Healthcare & Life Sciences

```python
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
```

### Domain 4: Defense & Intelligence

```python
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
```

### Domain 5: Financial Trading & Algorithms

```python
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
```

### Domain 6: Blockchain & Crypto Forensics

```python
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
```

---

## 3. Training Configuration Per Domain

Each domain uses the same pipeline with minor parameter adjustments:

| Parameter | Legal | Insurance | Healthcare | Defense | Trading | Blockchain |
|-----------|-------|-----------|------------|---------|---------|------------|
| Traces | 300 | 300 | 300 | 300 | 300 | 300 |
| Distillation LoRA rank | 32 | 32 | 32 | 32 | 32 | 32 |
| Distillation epochs | 3 | 3 | 3 | 3 | 3 | 3 |
| GRPO steps | 500 | 500 | 300 | 500 | 500 | 500 |
| GRPO LoRA rank | 16 | 16 | 16 | 16 | 16 | 16 |
| Max seq length | 4096 | 4096 | 4096 | 4096 | 4096 | 4096 |
| Base models | 4B + 9B | 4B + 9B | 4B + 9B | 4B + 9B | 4B + 9B | 4B + 9B |

Healthcare gets fewer GRPO steps because we want the model to be more
conservative — less emergent creativity, more strict adherence to training data.

### GRPO Reward Functions Per Domain

Each domain needs a custom reward function pair for GRPO. Here's the pattern:

```python
# Legal: reward for citing specific statutes and structured analysis
def legal_correctness_reward(completions, **kwargs):
    """Reward citations of specific legal authorities."""
    rewards = []
    legal_patterns = [
        r"(?:Section|§)\s*\d+",           # statute citations
        r"\d+\s+(?:U\.S\.C\.|C\.F\.R\.)", # federal code
        r"(?:FRE|FRCP|FINRA)\s+\d+",      # rules
        r"v\.\s+\w+",                      # case citations
    ]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        for pattern in legal_patterns:
            if re.search(pattern, text):
                score += 0.3
        score = min(score, 1.0)
        rewards.append(score)
    return rewards

# Insurance: reward for numerical precision and correct terminology
def insurance_correctness_reward(completions, **kwargs):
    rewards = []
    terms = ["cedent", "retrocession", "IBNR", "loss development",
             "chain ladder", "RBC", "solvency", "cession", "layer"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in terms if t.lower() in text.lower())
        score += min(term_count * 0.15, 0.6)
        if re.search(r"\d+\.?\d*%", text):  # numerical percentages
            score += 0.2
        if "<think>" in text and "</think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

# Healthcare: reward for conservative hedging and compliance framing
def healthcare_correctness_reward(completions, **kwargs):
    rewards = []
    compliance_terms = ["HIPAA", "21 CFR", "PHI", "BAA", "minimum necessary",
                        "de-identification", "IRB", "informed consent"]
    hedge_phrases = ["compliance analysis", "consult with", "verify with",
                     "subject to", "may require", "recommend reviewing"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in compliance_terms if t in text)
        score += min(term_count * 0.15, 0.5)
        hedge_count = sum(1 for h in hedge_phrases if h.lower() in text.lower())
        score += min(hedge_count * 0.1, 0.3)
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

# Defense: reward for structured intel product format
def defense_correctness_reward(completions, **kwargs):
    rewards = []
    structure_markers = ["confidence:", "source:", "assessment:", "alternative",
                        "assumption", "NIST", "CUI", "MITRE", "TTP"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        marker_count = sum(1 for m in structure_markers if m.lower() in text.lower())
        score += min(marker_count * 0.15, 0.6)
        if "<think>" in text:
            score += 0.2
        if any(w in text.lower() for w in ["low confidence", "moderate confidence", "high confidence"]):
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

# Trading: reward for mathematical precision and proper methodology
def trading_correctness_reward(completions, **kwargs):
    rewards = []
    quant_terms = ["VaR", "CVaR", "Sharpe", "alpha", "beta", "volatility",
                   "correlation", "cointegration", "mean reversion", "VWAP"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        term_count = sum(1 for t in quant_terms if t in text)
        score += min(term_count * 0.15, 0.5)
        if re.search(r"[\$€]\s*[\d,]+\.?\d*", text):  # dollar amounts
            score += 0.15
        if re.search(r"\d+\.?\d*[%σ]", text):  # percentages or sigma
            score += 0.15
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards

# Blockchain: reward for on-chain precision and forensic methodology
def blockchain_correctness_reward(completions, **kwargs):
    rewards = []
    forensic_terms = ["wallet", "transaction", "hash", "on-chain", "off-chain",
                      "mixer", "bridge", "DEX", "CEX", "clustering", "trace"]
    legal_terms = ["RICO", "BSA", "AML", "SAR", "FinCEN", "wire fraud",
                   "chain of custody", "evidence"]
    for texts in completions:
        text = texts[0]["content"] if isinstance(texts, list) else texts
        score = 0.0
        f_count = sum(1 for t in forensic_terms if t.lower() in text.lower())
        l_count = sum(1 for t in legal_terms if t in text)
        score += min(f_count * 0.1, 0.4)
        score += min(l_count * 0.1, 0.3)
        if re.search(r"0x[a-fA-F0-9]{6,}", text):  # address patterns
            score += 0.1
        if "<think>" in text:
            score += 0.2
        rewards.append(min(score, 1.0))
    return rewards
```

All domains also share the existing `reasoning_reward` function that checks
for `<think>` tag presence and quality of step-by-step reasoning.

---

## 4. Execution Plan

### Phase 1: Trace Generation (Day 1)

```bash
# Set traces per domain
export KWYRE_TRACES_PER_DOMAIN=300
export ANTHROPIC_API_KEY=sk-ant-...

# Run all 6 domains (parallel, 2 at a time)
python3 training/scripts/generate_traces_parallel.py

# Output: ~/.kwyre/training-data/kwyre-traces/
#   legal_compliance.jsonl         (300 traces)
#   insurance_actuarial.jsonl      (300 traces)
#   healthcare_lifesciences.jsonl  (300 traces)
#   defense_intelligence.jsonl     (300 traces)
#   financial_trading.jsonl        (300 traces)
#   blockchain_crypto.jsonl        (300 traces)
#   kwyre-all-traces.jsonl         (1800 combined)
```

Estimated: 6-8 hours, ~$60-80 API cost.

### Phase 2: Distillation (Days 2-4)

Train each domain adapter on both base models.
Run sequentially on a single H100, or parallel on 2-3 GPUs:

```bash
# For each domain × base model combination:
KWYRE_DOMAIN=legal KWYRE_BASE=Qwen/Qwen3-4B   bash run_domain_training.sh
KWYRE_DOMAIN=legal KWYRE_BASE=Qwen/Qwen3.5-9B bash run_domain_training.sh
# ... repeat for all 6 domains

# Output: ~/.kwyre/adapters/
#   legal-4b/adapter_config.json + adapter_model.safetensors
#   legal-9b/adapter_config.json + adapter_model.safetensors
#   insurance-4b/ ...
#   insurance-9b/ ...
#   ... (12 adapters total)
```

Estimated: ~3 hours per adapter × 12 = 36 GPU hours.

### Phase 3: GRPO (Days 4-6)

Apply domain-specific GRPO with custom reward functions:

```bash
KWYRE_DOMAIN=legal KWYRE_REWARD=legal_correctness bash run_domain_grpo.sh
# ... repeat for all 12 adapters
```

Estimated: ~3 hours per adapter × 12 = 36 GPU hours.

### Phase 4: Export & Package (Day 7)

For each adapter, export as standalone PEFT checkpoint (not merged).
Package with metadata.json for the adapter directory.

```bash
# Each adapter is ~50-200 MB as PEFT checkpoint
# Total storage: ~1-2 GB for all 12 adapters
# Distribution: host on kwyre.com CDN alongside base model downloads
```

### Total Cost Estimate

| Resource | Cost |
|----------|------|
| Claude API (1800 traces) | ~$70 |
| H100 GPU (72 hours @ $3/hr) | ~$216 |
| **Total** | **~$286** |

---

## 5. Distribution & Pricing

### Adapter pricing

Adapters ship as part of the license tier:

- **Personal ($299):** Base model + 1 domain adapter of choice
- **Professional ($799):** Base model + all 6 domain adapters
- **Air-Gapped Kit ($1,499):** Everything + offline adapter installer

### Download sizes

| Component | Size |
|-----------|------|
| Base Qwen3-4B (NF4) | ~2.5 GB |
| Base Qwen3.5-9B (NF4) | ~7.6 GB |
| Single domain adapter | ~50-200 MB |
| All 6 adapters | ~600 MB - 1.2 GB |

### Adapter download flow

```
1. Customer installs Kwyre → downloads base model
2. Customer selects domain → downloads adapter (~100 MB)
3. Kwyre auto-loads adapter on startup
4. Customer can swap adapters at runtime via API or UI
```

---

## 6. CDN Deployment Workflow

### Prerequisites

- Cloudflare R2 bucket `kwyre-adapters` set up
- `rclone` or `wrangler` CLI configured
- Training completed on GPU droplet

### Step 1: Pull adapters from GPU droplet

```bash
scp -r root@<droplet-ip>:~/.kwyre/adapters/ ~/.kwyre/adapters/
scp -r root@<droplet-ip>:~/.kwyre/lora-adapters/ ~/.kwyre/lora-adapters/
```

### Step 2: Package each adapter

```bash
bash scripts/package_adapter.sh blockchain_crypto 1.0.0 4b
bash scripts/package_adapter.sh legal_compliance 1.0.0 4b
bash scripts/package_adapter.sh insurance_actuarial 1.0.0 4b
bash scripts/package_adapter.sh defense_intelligence 1.0.0 4b
bash scripts/package_adapter.sh financial_trading 1.0.0 4b
bash scripts/package_adapter.sh healthcare_lifesciences 1.0.0 4b
```

### Step 3: Upload to R2

```bash
rclone copy ~/.kwyre/adapter-packages/ r2:kwyre-adapters/
# or: for f in ~/.kwyre/adapter-packages/*.zip; do wrangler r2 object put kwyre-adapters/$(basename $f) --file $f; done
```

### Step 4: Update manifest

- Copy SHA-256 hashes from package_adapter.sh output
- Update `chat/adapters/manifest.json` with real sha256 values
- Verify URLs resolve

### Step 5: Deploy

```bash
npx wrangler pages deploy chat/ --project-name kwyre-ai
```

### Step 6: Verify

- Check manifest: `curl https://kwyre.com/adapters/manifest.json`
- Test download: `curl -I https://cdn.kwyre.com/adapters/blockchain-crypto-4b-v1.0.0.zip`

### Version bumps

To release adapter updates: increment the version (e.g. 1.0.0 → 1.0.1), re-package each updated adapter with the new version, re-upload the new zip files to R2, update `chat/adapters/manifest.json` with the new version, url, and sha256 values, then redeploy with `npx wrangler pages deploy chat/ --project-name kwyre-ai`.
