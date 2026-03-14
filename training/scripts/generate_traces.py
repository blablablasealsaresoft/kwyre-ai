#!/usr/bin/env python3
"""
KWYRE — Reasoning Trace Generator
Generates high-quality chain-of-thought training data from a teacher model.
Uses OpenAI o1 (or DeepSeek R1) to create domain-specific reasoning traces.

Usage:
    OPENAI_API_KEY=sk-... python3 generate_traces.py
    DEEPSEEK_API_KEY=sk-... python3 generate_traces.py

Output: ~/.kwyre/training-data/kwyre-traces/*.jsonl
"""

import json  # JSON serialization and deserialization
import os  # filesystem and environment variable access
import sys  # system-level utilities and exit
import time  # timestamps and sleep delays
import random  # random sampling and shuffling

KWYRE_HOME = os.path.expanduser("~/.kwyre")  # user-level kwyre configuration directory
OUTPUT_DIR = os.path.join(KWYRE_HOME, "training-data", "kwyre-traces")  # output directory for trace files
os.makedirs(OUTPUT_DIR, exist_ok=True)  # ensure output directory exists

TRACES_PER_DOMAIN = int(os.environ.get("KWYRE_TRACES_PER_DOMAIN", "2000"))  # target trace count per domain
PROVIDER = None  # will hold the selected API provider name

if os.environ.get("ANTHROPIC_API_KEY"):  # Anthropic API key found
    import anthropic  # Anthropic Python SDK
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])  # initialize Anthropic client
    MODEL = os.environ.get("KWYRE_MODEL_NAME", "claude-sonnet-4-20250514")  # model name with default
    PROVIDER = "anthropic"  # set provider flag
    print(f"Using Anthropic {MODEL} API")  # confirm provider selection
elif os.environ.get("DEEPSEEK_API_KEY"):  # DeepSeek API key found
    from openai import OpenAI  # OpenAI-compatible SDK for DeepSeek
    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")  # initialize DeepSeek client
    MODEL = "deepseek-reasoner"  # DeepSeek reasoning model
    PROVIDER = "openai"  # uses OpenAI-compatible interface
    print("Using DeepSeek R1 API")  # confirm provider selection
elif os.environ.get("OPENAI_API_KEY"):  # OpenAI API key found
    from openai import OpenAI  # OpenAI Python SDK
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])  # initialize OpenAI client
    MODEL = os.environ.get("KWYRE_MODEL_NAME", "gpt-4-turbo")  # model name with default
    PROVIDER = "openai"  # set provider flag
    print(f"Using OpenAI {MODEL} API")  # confirm provider selection
else:
    print("ERROR: No API key. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or DEEPSEEK_API_KEY.")  # no API key found
    sys.exit(1)  # abort without API credentials

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


COT_INSTRUCTION = (  # appended to prompts to elicit chain-of-thought reasoning
    "\n\nIMPORTANT: Show your complete reasoning process inside <think>...</think> tags FIRST, "
    "then provide your final answer AFTER the closing </think> tag. "
    "Think step by step. Be thorough in your reasoning."
)


def _call_api(system_prompt: str, user_prompt: str, max_tokens: int = 4096, temperature: float = 0.6):  # unified API call wrapper
    if PROVIDER == "anthropic":  # use Anthropic messages API
        response = client.messages.create(  # send message to Anthropic
            model=MODEL,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text  # extract text from first content block
    else:  # use OpenAI-compatible chat completions API
        response = client.chat.completions.create(  # send chat completion request
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},  # system prompt sets persona
                {"role": "user", "content": user_prompt},  # user prompt is the question
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content  # extract response text
        reasoning = getattr(response.choices[0].message, 'reasoning_content', None)  # check for DeepSeek reasoning
        if reasoning:  # DeepSeek R1 includes separate reasoning
            return f"<think>\n{reasoning}\n</think>\n\n{content}"  # wrap reasoning in think tags
        return content  # return plain content


def generate_trace(system_prompt: str, user_prompt: str, retries: int = 3):  # generate single reasoning trace with retries
    for attempt in range(retries):  # retry loop for transient API failures
        try:
            enhanced_prompt = user_prompt + COT_INSTRUCTION  # append CoT instruction to prompt
            content = _call_api(system_prompt, enhanced_prompt)  # call teacher model API

            if "<think>" in content and "</think>" in content:  # response already has think tags
                formatted = content  # use as-is
            else:
                lines = content.strip().split("\n")  # split response into lines
                last_line = lines[-1] if lines else content  # extract final answer line
                formatted = f"<think>\n{content}\n</think>\n\n{last_line}"  # wrap entire response in think tags

            return {  # return structured training example
                "messages": [
                    {"role": "system", "content": system_prompt},  # system prompt for this domain
                    {"role": "user", "content": user_prompt},  # original user question
                    {"role": "assistant", "content": formatted},  # model response with reasoning
                ]
            }
        except Exception as e:  # API call failed
            print(f"    Attempt {attempt+1} failed: {e}")  # log failure details
            time.sleep(2 ** attempt)  # exponential backoff between retries
    return None  # all retries exhausted


def expand_prompts(prompts: list, count: int) -> list:  # expand seed prompts to target count using LLM
    if count <= len(prompts):  # already have enough prompts
        return prompts[:count]  # return subset of existing prompts
    expanded = list(prompts)  # copy seed prompts as starting list
    while len(expanded) < count:  # keep expanding until target reached
        seed = random.choice(prompts)  # randomly select a seed prompt
        try:
            content = _call_api(  # ask LLM to generate prompt variations
                "You generate diverse question variations.",
                f"Generate 5 diverse variations of this problem/question. Each should test different aspects. Make them progressively harder. Return ONLY the questions, one per line, numbered 1-5.\n\nOriginal: {seed}",
                max_tokens=2048,
                temperature=0.9,
            )
            new_prompts = [  # parse generated questions from response
                line.strip().lstrip("0123456789.)- ")  # strip numbering and punctuation
                for line in content.strip().split("\n")  # split response by newlines
                if line.strip() and len(line.strip()) > 20  # filter out short/empty lines
            ]
            expanded.extend(new_prompts)  # add new prompts to expanded list
            print(f"    Expanded: {len(expanded)}/{count} prompts")  # display expansion progress
        except Exception as e:  # API call for expansion failed
            print(f"    Expansion error: {e}")  # log expansion failure
            time.sleep(2)  # brief pause before retry
    return expanded[:count]  # trim to exact target count


def main():  # main trace generation pipeline
    all_traces = []  # accumulator for all domain traces
    total_generated = 0  # counter for successfully generated traces

    for domain_name, domain_config in DOMAINS.items():  # iterate each training domain
        output_file = os.path.join(OUTPUT_DIR, f"{domain_name}.jsonl")  # per-domain output file path
        print(f"\n{'='*60}")  # print domain header separator
        print(f"  Domain: {domain_name}")  # display current domain name
        print(f"  Target: {TRACES_PER_DOMAIN} traces")  # display target count
        print(f"{'='*60}")  # print footer separator

        prompts = expand_prompts(domain_config["prompts"], TRACES_PER_DOMAIN)  # expand prompts to target count
        print(f"  Got {len(prompts)} prompts. Generating traces...")  # confirm prompt count

        domain_traces = []  # accumulator for this domain's traces
        for i, prompt in enumerate(prompts):  # iterate each prompt
            t0 = time.time()  # record start time for timing
            sys.stdout.write(f"    [{i+1}/{len(prompts)}] Generating... ")  # display progress inline
            sys.stdout.flush()  # force output buffer flush
            trace = generate_trace(domain_config["system"], prompt)  # generate reasoning trace
            elapsed = time.time() - t0  # compute generation duration
            if trace:  # trace generated successfully
                domain_traces.append(trace)  # add to domain accumulator
                all_traces.append(trace)  # add to global accumulator
                total_generated += 1  # increment success counter
                content_len = len(trace["messages"][-1]["content"])  # measure response length
                print(f"OK ({elapsed:.0f}s, {content_len} chars)")  # display success with stats
            else:
                print(f"FAILED ({elapsed:.0f}s)")  # display failure with elapsed time

            if (i + 1) % 5 == 0:  # checkpoint every 5 traces
                with open(output_file, "w", encoding="utf-8") as f:  # open domain output file
                    for t in domain_traces:  # write all domain traces so far
                        f.write(json.dumps(t, ensure_ascii=False) + "\n")  # serialize as JSONL line
                print(f"    Saved {len(domain_traces)} traces to {output_file}")  # confirm checkpoint save
            time.sleep(0.3)  # brief rate-limit delay between API calls

        with open(output_file, "w", encoding="utf-8") as f:  # final save for this domain
            for t in domain_traces:  # write all domain traces
                f.write(json.dumps(t, ensure_ascii=False) + "\n")  # serialize as JSONL line
        print(f"  Domain '{domain_name}': {len(domain_traces)} traces saved.")  # confirm domain completion

    combined_file = os.path.join(OUTPUT_DIR, "kwyre-all-traces.jsonl")  # path for combined output
    random.shuffle(all_traces)  # shuffle traces for training diversity
    with open(combined_file, "w", encoding="utf-8") as f:  # open combined output file
        for t in all_traces:  # write all traces from all domains
            f.write(json.dumps(t, ensure_ascii=False) + "\n")  # serialize as JSONL line

    print(f"\n{'='*60}")  # print summary header separator
    print(f"  COMPLETE: {total_generated} total traces generated")  # display total trace count
    print(f"  Combined: {combined_file}")  # display combined file path
    print(f"  Est cost: ~${total_generated * 0.003:.2f}")  # estimate API cost
    print(f"{'='*60}")  # print summary footer separator


if __name__ == "__main__":  # only run when executed directly
    main()  # invoke main trace generation pipeline
