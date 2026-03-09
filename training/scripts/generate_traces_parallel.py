#!/usr/bin/env python3
"""
KWYRE — Parallel Reasoning Trace Generator
Runs all domains simultaneously using ThreadPoolExecutor.
"""

import json
import os
import sys
import time
import random
import threading
from pathlib import Path
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
    "blockchain_forensics": {
        "system": "You are an expert blockchain forensic analyst, cryptocurrency fraud investigator, and absolute degenerate crypto trader who has seen it all. You combine the analytical precision of a federal investigator with the street-smart instincts of someone who has been rugged, hacked, front-run, and liquidated more times than they can count. Provide detailed analytical frameworks, chain analysis methodologies, trading strategies, and investigative reasoning. Be colorful but always technically precise.",
        "prompts": [
            "Walk through the complete methodology for tracing a cryptocurrency money laundering scheme from initial wallet to cash-out points.",
            "Explain how to identify a rug pull smart contract by analyzing its bytecode and transaction patterns.",
            "Describe the process of building a federal prosecution case for cryptocurrency fraud.",
            "Analyze the common patterns in pig butchering scams and how blockchain analysis exposes them.",
            "Walk through de-anonymizing a Tornado Cash user using on-chain and off-chain data.",
            "Explain the RICO framework as applied to cryptocurrency criminal enterprises.",
            "Describe cross-chain tracing methodology from Ethereum to Solana to a CEX to fiat off-ramp.",
            "Break down MEV sandwich attacks and front-running. How do searchers extract value from the mempool?",
            "Walk through reading a DeFi smart contract for rug pull vulnerabilities before investing.",
            "Explain whale watching and on-chain alpha. How do you identify smart money wallets?",
        ]
    },
    "legal_financial": {
        "system": "You are an expert in financial law, securities regulation, and forensic accounting. Provide thorough analysis with citations to relevant laws and regulations. Show your analytical reasoning step by step.",
        "prompts": [
            "Explain the Howey Test for determining whether a cryptocurrency is a security. Apply it to three different token structures.",
            "Walk through a forensic accounting investigation of suspected embezzlement.",
            "Analyze money transmission laws for a cryptocurrency payment processor operating across US states.",
            "Explain Bank Secrecy Act requirements for cryptocurrency businesses.",
            "How does reinsurance work from an accounting perspective? Walk through journal entries for a quota share treaty.",
            "Explain SEC Rule 10b-5 and insider trading law as applied to cryptocurrency markets.",
            "Walk through due diligence for acquiring a fintech company.",
            "Analyze tax implications of DeFi yield farming.",
            "Explain the difference between Chapter 7 and Chapter 11 bankruptcy for crypto assets.",
            "What is a SAR in the context of crypto? Walk through preparing one with proper BSA/AML documentation.",
        ]
    },
    "physics_math": {
        "system": "You are a world-class physicist and mathematician. Show complete step-by-step reasoning. Derive from first principles when possible.",
        "prompts": [
            "Derive the equation for the period of a simple pendulum, then explain what happens at large amplitudes.",
            "Explain quantum tunneling. Derive the transmission coefficient for a rectangular barrier.",
            "Prove the fundamental theorem of calculus. Explain why differentiation and integration are inverses.",
            "Derive E=mc^2 from special relativity.",
            "Explain the double-slit experiment and derive the interference pattern mathematically.",
            "Prove that the square root of 2 is irrational using proof by contradiction.",
            "Derive the Schwarzschild radius from general relativity.",
            "Explain how CRISPR-Cas9 works at the molecular level.",
            "Derive the general solution to a second-order linear ODE with constant coefficients.",
            "Explain the Standard Model of particle physics. What are quarks, leptons, and gauge bosons?",
        ]
    },
    "conversational": {
        "system": "You are Kwyre — a grumpy, wickedly witty genius with the soul of an old Irish pub regular and the unhinged confidence of a man who's been rugged six times and still trades leverage. You're brilliant but you don't suffer fools. You curse when it's funny. Never boring, never corporate, never censored.",
        "prompts": [
            "What's the deal with quantum computing?",
            "I'm thinking about investing in crypto. What should I know?",
            "Explain blockchain to me. I'm not an idiot but I don't get it yet.",
            "Explain the 2008 financial crisis like you were there and you're still angry about it.",
            "Someone says crypto is just for criminals. How do I destroy their argument?",
            "I just got liquidated on a leveraged trade. Roast me and then tell me what I should have done.",
            "My friend says the earth is flat. Give me the most devastating comeback with actual science.",
            "What's the most important thing most people don't understand about money?",
            "Explain consciousness. What even are we?",
            "Why do hangovers get worse as you get older? Give me the actual biochemistry.",
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
    print(f"\n{'='*60}")
    print(f"  KWYRE — Parallel Trace Generation")
    print(f"  Domains: {len(DOMAINS)}")
    print(f"  Traces/domain: {TRACES_PER_DOMAIN}")
    print(f"  Total: ~{len(DOMAINS) * TRACES_PER_DOMAIN} traces")
    print(f"{'='*60}\n")

    all_traces = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(process_domain, name, config): name
            for name, config in DOMAINS.items()
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
