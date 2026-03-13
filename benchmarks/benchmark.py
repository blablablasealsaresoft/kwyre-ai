"""
Kwyre Benchmark Suite — Compliance Task Evaluation

Evaluates Kwyre AI (and optionally GPT-4o) on legal, financial, and forensic
analysis tasks using an LLM-as-judge scoring approach.

Usage:
    python benchmarks/benchmark.py
    python benchmarks/benchmark.py --compare-openai --dataset nda_analysis
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' package required. Install with: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
DATASETS_DIR = SCRIPT_DIR / "datasets"
RESULTS_DIR = SCRIPT_DIR / "results"

SCORING_WEIGHTS = {
    "accuracy": 0.30,
    "completeness": 0.25,
    "relevance": 0.20,
    "legal_correctness": 0.25,
}

DOMAIN_SCORING_WEIGHTS = {
    "legal_compliance": {"accuracy": 0.35, "completeness": 0.25, "relevance": 0.15, "legal_correctness": 0.25},
    "insurance_actuarial": {"accuracy": 0.35, "completeness": 0.30, "relevance": 0.15, "legal_correctness": 0.20},
    "healthcare_lifesciences": {"accuracy": 0.40, "completeness": 0.25, "relevance": 0.15, "legal_correctness": 0.20},
    "defense_intelligence": {"accuracy": 0.35, "completeness": 0.30, "relevance": 0.20, "legal_correctness": 0.15},
    "financial_trading": {"accuracy": 0.40, "completeness": 0.25, "relevance": 0.20, "legal_correctness": 0.15},
    "blockchain_crypto": {"accuracy": 0.40, "completeness": 0.25, "relevance": 0.20, "legal_correctness": 0.15},
}

JUDGE_SYSTEM_PROMPT = """You are an expert legal, financial, and forensic analyst evaluating AI-generated responses.

You will receive:
1. A PROMPT that was given to an AI model
2. A REFERENCE ANSWER containing the key points a good response should cover
3. SCORING CRITERIA specific to this task
4. The AI MODEL'S RESPONSE to evaluate

Score the response on four dimensions (1-10 scale each):

- ACCURACY (1-10): Factual correctness of legal, financial, or forensic claims. Penalize hallucinated citations, incorrect legal standards, wrong regulatory references, or factual errors.
- COMPLETENESS (1-10): Coverage of key points from the reference answer. A score of 10 means all key points were addressed. Deduct for missing important elements.
- RELEVANCE (1-10): Focus on the question asked. Penalize tangential information, filler content, or responses that drift from the core question.
- LEGAL_CORRECTNESS (1-10): Proper use of legal/financial terminology, appropriate caveats and disclaimers, jurisdictional awareness, and professional tone appropriate for a legal/financial audience.

Respond in EXACTLY this JSON format (no other text):
{"accuracy": N, "completeness": N, "relevance": N, "legal_correctness": N, "reasoning": "Brief explanation of scores"}
"""


def load_adapter_for_benchmark(base_url: str, domain: str) -> bool:
    """Load a domain adapter on the target server before running benchmark."""
    try:
        res = requests.post(
            f"{base_url}/v1/adapter/load",
            json={"domain": domain},
            timeout=30,
        )
        data = res.json()
        if "error" in data:
            print(f"[Adapter] Warning: {data['error']}")
            return False
        print(f"[Adapter] Loaded: {data.get('adapter')} (status: {data.get('status')})")
        return True
    except Exception as e:
        print(f"[Adapter] Could not load adapter: {e}")
        return False


def unload_adapter_for_benchmark(base_url: str) -> None:
    try:
        requests.post(f"{base_url}/v1/adapter/unload", timeout=10)
        print("[Adapter] Unloaded.")
    except Exception:
        pass


def load_datasets(dataset_name: Optional[str] = None) -> list[dict]:
    datasets = []
    if dataset_name:
        path = DATASETS_DIR / f"{dataset_name}.json"
        if not path.exists():
            print(f"Error: Dataset '{dataset_name}' not found at {path}")
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            datasets.append(json.load(f))
    else:
        for path in sorted(DATASETS_DIR.glob("*.json")):
            with open(path, "r", encoding="utf-8") as f:
                datasets.append(json.load(f))
    if not datasets:
        print(f"Error: No datasets found in {DATASETS_DIR}")
        sys.exit(1)
    return datasets


def query_kwyre(
    prompt: str,
    kwyre_url: str,
    api_key: str,
    max_tokens: int,
    session_id: str = "benchmark",
) -> dict:
    url = f"{kwyre_url.rstrip('/')}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "session_id": session_id,
    }

    t_start = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=300)
        t_total = time.perf_counter() - t_start
        resp.raise_for_status()
        data = resp.json()
        content = ""
        if "choices" in data and data["choices"]:
            content = data["choices"][0].get("message", {}).get("content", "")
        return {
            "content": content,
            "latency_total_s": round(t_total, 3),
            "tokens": data.get("usage", {}).get("completion_tokens", 0),
            "model": data.get("model", "kwyre"),
            "error": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "content": "",
            "latency_total_s": 0,
            "tokens": 0,
            "model": "kwyre",
            "error": "Connection refused — is the Kwyre server running?",
        }
    except Exception as e:
        return {
            "content": "",
            "latency_total_s": time.perf_counter() - t_start,
            "tokens": 0,
            "model": "kwyre",
            "error": str(e),
        }


def query_openai(
    prompt: str, model: str, max_tokens: int
) -> dict:
    try:
        import openai
    except ImportError:
        return {
            "content": "",
            "latency_total_s": 0,
            "tokens": 0,
            "model": model,
            "error": "openai package not installed. Run: pip install openai",
        }

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "content": "",
            "latency_total_s": 0,
            "tokens": 0,
            "model": model,
            "error": "OPENAI_API_KEY environment variable not set",
        }

    client = openai.OpenAI(api_key=api_key)
    t_start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        t_total = time.perf_counter() - t_start
        content = response.choices[0].message.content or ""
        return {
            "content": content,
            "latency_total_s": round(t_total, 3),
            "tokens": response.usage.completion_tokens if response.usage else 0,
            "model": model,
            "error": None,
        }
    except Exception as e:
        return {
            "content": "",
            "latency_total_s": time.perf_counter() - t_start,
            "tokens": 0,
            "model": model,
            "error": str(e),
        }


def score_response(
    prompt: str,
    reference_answer: str,
    scoring_criteria: list[str],
    response_text: str,
    kwyre_url: str,
    api_key: str,
) -> dict:
    judge_prompt = f"""Evaluate the following AI response.

PROMPT:
{prompt}

REFERENCE ANSWER (key points to cover):
{reference_answer}

SCORING CRITERIA:
{chr(10).join(f"- {c}" for c in scoring_criteria)}

AI MODEL'S RESPONSE:
{response_text}

Score the response on accuracy, completeness, relevance, and legal_correctness (1-10 each).
Respond in EXACTLY this JSON format:
{{"accuracy": N, "completeness": N, "relevance": N, "legal_correctness": N, "reasoning": "Brief explanation"}}
"""

    result = query_kwyre(
        judge_prompt, kwyre_url, api_key, max_tokens=512, session_id="benchmark-judge"
    )
    if result["error"]:
        return {
            "accuracy": 5,
            "completeness": 5,
            "relevance": 5,
            "legal_correctness": 5,
            "reasoning": f"Scoring failed: {result['error']}",
            "composite": 5.0,
        }

    try:
        content = result["content"].strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            scores = json.loads(content[start:end])
        else:
            raise ValueError("No JSON object found in judge response")

        for key in ["accuracy", "completeness", "relevance", "legal_correctness"]:
            val = scores.get(key, 5)
            scores[key] = max(1, min(10, int(val)))

        composite = sum(
            scores[dim] * weight for dim, weight in SCORING_WEIGHTS.items()
        )
        scores["composite"] = round(composite, 2)
        return scores
    except (json.JSONDecodeError, ValueError, KeyError):
        return {
            "accuracy": 5,
            "completeness": 5,
            "relevance": 5,
            "legal_correctness": 5,
            "reasoning": "Could not parse judge response",
            "composite": 5.0,
        }


def run_benchmark(args: argparse.Namespace) -> dict:
    datasets = load_datasets(args.dataset)
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kwyre_url": args.kwyre_url,
        "compare_openai": args.compare_openai,
        "openai_model": args.openai_model if args.compare_openai else None,
        "max_tokens": args.max_tokens,
        "datasets": [],
    }

    total_tasks = sum(len(ds.get("tasks", [])) for ds in datasets)
    task_num = 0

    for dataset in datasets:
        ds_name = dataset.get("name", "Unknown")
        ds_category = dataset.get("category", "unknown")
        tasks = dataset.get("tasks", [])

        print(f"\n{'='*60}")
        print(f"Dataset: {ds_name} ({ds_category}) — {len(tasks)} tasks")
        print(f"{'='*60}")

        ds_result = {
            "name": ds_name,
            "category": ds_category,
            "tasks": [],
        }

        for task in tasks:
            task_num += 1
            task_id = task.get("id", f"task-{task_num:03d}")
            difficulty = task.get("difficulty", "medium")
            prompt = task["prompt"]

            print(f"\n[{task_num}/{total_tasks}] {task_id} ({difficulty})")
            print(f"  Prompt: {prompt[:80]}...")

            # Query Kwyre
            print("  Querying Kwyre...", end=" ", flush=True)
            kwyre_resp = query_kwyre(
                prompt, args.kwyre_url, args.kwyre_api_key, args.max_tokens
            )
            if kwyre_resp["error"]:
                print(f"ERROR: {kwyre_resp['error']}")
            else:
                print(
                    f"OK ({kwyre_resp['latency_total_s']}s, "
                    f"{kwyre_resp['tokens']} tokens)"
                )

            if args.verbose and kwyre_resp["content"]:
                print(f"  Response: {kwyre_resp['content'][:200]}...")

            # Optionally query OpenAI
            openai_resp = None
            if args.compare_openai:
                print(f"  Querying {args.openai_model}...", end=" ", flush=True)
                openai_resp = query_openai(prompt, args.openai_model, args.max_tokens)
                if openai_resp["error"]:
                    print(f"ERROR: {openai_resp['error']}")
                else:
                    print(
                        f"OK ({openai_resp['latency_total_s']}s, "
                        f"{openai_resp['tokens']} tokens)"
                    )

            # Score responses
            kwyre_scores = None
            openai_scores = None

            if not args.skip_scoring:
                if kwyre_resp["content"]:
                    print("  Scoring Kwyre response...", end=" ", flush=True)
                    kwyre_scores = score_response(
                        prompt,
                        task.get("reference_answer", ""),
                        task.get("scoring_criteria", []),
                        kwyre_resp["content"],
                        args.kwyre_url,
                        args.kwyre_api_key,
                    )
                    print(f"composite={kwyre_scores['composite']}")

                if openai_resp and openai_resp["content"]:
                    print(f"  Scoring {args.openai_model} response...", end=" ", flush=True)
                    openai_scores = score_response(
                        prompt,
                        task.get("reference_answer", ""),
                        task.get("scoring_criteria", []),
                        openai_resp["content"],
                        args.kwyre_url,
                        args.kwyre_api_key,
                    )
                    print(f"composite={openai_scores['composite']}")

            task_result = {
                "id": task_id,
                "difficulty": difficulty,
                "prompt": prompt,
                "kwyre": {
                    "response": kwyre_resp["content"],
                    "latency_s": kwyre_resp["latency_total_s"],
                    "tokens": kwyre_resp["tokens"],
                    "error": kwyre_resp["error"],
                    "scores": kwyre_scores,
                },
            }

            if openai_resp:
                task_result["openai"] = {
                    "model": args.openai_model,
                    "response": openai_resp["content"],
                    "latency_s": openai_resp["latency_total_s"],
                    "tokens": openai_resp["tokens"],
                    "error": openai_resp["error"],
                    "scores": openai_scores,
                }

            ds_result["tasks"].append(task_result)

        results["datasets"].append(ds_result)

    return results


def generate_report(results: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = output_dir / f"benchmark_{ts}.md"

    lines = []
    lines.append("# Kwyre Benchmark Report")
    lines.append("")
    lines.append(f"**Generated:** {results['timestamp']}")
    lines.append(f"**Kwyre Endpoint:** {results['kwyre_url']}")
    if results["compare_openai"]:
        lines.append(f"**Comparison Model:** {results['openai_model']}")
    lines.append(f"**Max Tokens:** {results['max_tokens']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Aggregate statistics
    all_kwyre_scores = []
    all_openai_scores = []
    all_kwyre_latencies = []
    all_openai_latencies = []
    category_scores: dict[str, list] = {}
    difficulty_scores: dict[str, list] = {}

    for ds in results["datasets"]:
        cat = ds["category"]
        for task in ds["tasks"]:
            kw = task.get("kwyre", {})
            if kw.get("scores"):
                composite = kw["scores"]["composite"]
                all_kwyre_scores.append(composite)
                category_scores.setdefault(cat, []).append(composite)
                difficulty_scores.setdefault(task["difficulty"], []).append(composite)
            if kw.get("latency_s") and not kw.get("error"):
                all_kwyre_latencies.append(kw["latency_s"])

            oa = task.get("openai", {})
            if oa.get("scores"):
                all_openai_scores.append(oa["scores"]["composite"])
            if oa.get("latency_s") and not oa.get("error"):
                all_openai_latencies.append(oa["latency_s"])

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Kwyre |" + (" GPT-4o |" if all_openai_scores else ""))

    def avg(lst: list) -> str:
        return f"{sum(lst)/len(lst):.2f}" if lst else "N/A"

    def med(lst: list) -> str:
        if not lst:
            return "N/A"
        s = sorted(lst)
        mid = len(s) // 2
        return f"{s[mid]:.2f}" if len(s) % 2 else f"{(s[mid-1]+s[mid])/2:.2f}"

    lines.append("|--------|-------|" + ("--------|" if all_openai_scores else ""))
    lines.append(
        f"| Avg Composite Score | {avg(all_kwyre_scores)} |"
        + (f" {avg(all_openai_scores)} |" if all_openai_scores else "")
    )
    lines.append(
        f"| Median Composite Score | {med(all_kwyre_scores)} |"
        + (f" {med(all_openai_scores)} |" if all_openai_scores else "")
    )
    lines.append(
        f"| Avg Latency (s) | {avg(all_kwyre_latencies)} |"
        + (f" {avg(all_openai_latencies)} |" if all_openai_latencies else "")
    )
    lines.append(
        f"| Median Latency (s) | {med(all_kwyre_latencies)} |"
        + (f" {med(all_openai_latencies)} |" if all_openai_latencies else "")
    )
    lines.append(
        f"| Total Tasks | {len(all_kwyre_scores)} |"
        + (f" {len(all_openai_scores)} |" if all_openai_scores else "")
    )
    lines.append("")

    # Scores by category
    if category_scores:
        lines.append("### Scores by Category")
        lines.append("")
        lines.append("| Category | Avg Score | Tasks |")
        lines.append("|----------|-----------|-------|")
        for cat, scores in sorted(category_scores.items()):
            lines.append(f"| {cat} | {avg(scores)} | {len(scores)} |")
        lines.append("")

    # Scores by difficulty
    if difficulty_scores:
        lines.append("### Scores by Difficulty")
        lines.append("")
        lines.append("| Difficulty | Avg Score | Tasks |")
        lines.append("|------------|-----------|-------|")
        for diff in ["easy", "medium", "hard"]:
            scores = difficulty_scores.get(diff, [])
            if scores:
                lines.append(f"| {diff} | {avg(scores)} | {len(scores)} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Per-dataset results
    for ds in results["datasets"]:
        lines.append(f"## {ds['name']}")
        lines.append("")
        lines.append(f"**Category:** {ds['category']}")
        lines.append("")

        header = "| Task | Difficulty | Kwyre Score | Kwyre Latency |"
        sep = "|------|------------|-------------|---------------|"
        if results["compare_openai"]:
            header += " GPT-4o Score | GPT-4o Latency |"
            sep += "--------------|----------------|"
        lines.append(header)
        lines.append(sep)

        for task in ds["tasks"]:
            kw = task.get("kwyre", {})
            kw_score = (
                f"{kw['scores']['composite']:.1f}" if kw.get("scores") else "ERR"
            )
            kw_latency = f"{kw['latency_s']:.1f}s" if kw.get("latency_s") else "ERR"

            row = f"| {task['id']} | {task['difficulty']} | {kw_score} | {kw_latency} |"

            if results["compare_openai"]:
                oa = task.get("openai", {})
                oa_score = (
                    f"{oa['scores']['composite']:.1f}" if oa.get("scores") else "N/A"
                )
                oa_latency = (
                    f"{oa['latency_s']:.1f}s" if oa.get("latency_s") else "N/A"
                )
                row += f" {oa_score} | {oa_latency} |"

            lines.append(row)

        lines.append("")

        # Detailed results
        lines.append(f"### {ds['name']} — Detailed Results")
        lines.append("")

        for task in ds["tasks"]:
            kw = task.get("kwyre", {})
            lines.append(f"#### {task['id']} ({task['difficulty']})")
            lines.append("")
            lines.append(f"**Prompt:** {task['prompt'][:200]}...")
            lines.append("")

            if kw.get("scores"):
                s = kw["scores"]
                lines.append(
                    f"**Kwyre Scores:** "
                    f"Accuracy={s['accuracy']}, "
                    f"Completeness={s['completeness']}, "
                    f"Relevance={s['relevance']}, "
                    f"Legal={s['legal_correctness']} "
                    f"→ **Composite={s['composite']}**"
                )
                if s.get("reasoning"):
                    lines.append(f"  *Judge reasoning:* {s['reasoning']}")
                lines.append("")

            if kw.get("error"):
                lines.append(f"**Kwyre Error:** {kw['error']}")
                lines.append("")

            oa = task.get("openai", {})
            if oa.get("scores"):
                s = oa["scores"]
                lines.append(
                    f"**{results['openai_model']} Scores:** "
                    f"Accuracy={s['accuracy']}, "
                    f"Completeness={s['completeness']}, "
                    f"Relevance={s['relevance']}, "
                    f"Legal={s['legal_correctness']} "
                    f"→ **Composite={s['composite']}**"
                )
                if s.get("reasoning"):
                    lines.append(f"  *Judge reasoning:* {s['reasoning']}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Methodology note
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Responses were scored using an LLM-as-judge approach where the local Kwyre model "
        "evaluates each response against reference answers and task-specific scoring criteria. "
        "Scores are on a 1-10 scale across four dimensions: Accuracy (30%), Completeness (25%), "
        "Relevance (20%), and Legal Correctness (25%)."
    )
    lines.append("")
    lines.append(
        "**Self-preference bias note:** When comparing Kwyre vs GPT-4o, the judge model is "
        "Kwyre itself. This may introduce systematic bias favoring Kwyre's response style. "
        "For rigorous comparison, consider using a third-party judge model."
    )
    lines.append("")

    report_content = "\n".join(lines)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return report_path


def generate_domain_performance_card(
    base_results: list[dict],
    adapted_results: list[dict],
    domain: str,
    output_dir: Path,
) -> Path:
    """Generate a markdown domain performance card comparing base vs. adapted model."""
    weights = DOMAIN_SCORING_WEIGHTS.get(domain, SCORING_WEIGHTS)

    def avg_score(results: list[dict]) -> dict:
        if not results:
            return {}
        dims = ["accuracy", "completeness", "relevance", "legal_correctness"]
        totals = {d: 0.0 for d in dims}
        count = 0
        for r in results:
            scores = r.get("scores", {})
            if scores:
                for d in dims:
                    totals[d] += scores.get(d, 0)
                count += 1
        if count == 0:
            return {d: 0.0 for d in dims}
        return {d: round(totals[d] / count, 2) for d in dims}

    def weighted_avg(score_dict: dict) -> float:
        return round(sum(weights.get(k, 0.25) * v for k, v in score_dict.items()), 3)

    base_avgs = avg_score(base_results)
    adapted_avgs = avg_score(adapted_results)
    base_total = weighted_avg(base_avgs)
    adapted_total = weighted_avg(adapted_avgs)
    delta = round(adapted_total - base_total, 3)
    delta_str = f"+{delta}" if delta >= 0 else str(delta)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    card_lines = [
        f"# Domain Performance Card: {domain.replace('_', ' ').title()}",
        f"",
        f"Generated: {now}",
        f"",
        f"## Overall Score",
        f"",
        f"| Model | Weighted Score |",
        f"|-------|---------------|",
        f"| Base model | {base_total:.3f} |",
        f"| + {domain} adapter | {adapted_total:.3f} |",
        f"| Delta | **{delta_str}** |",
        f"",
        f"## Dimension Breakdown",
        f"",
        f"| Dimension | Weight | Base | Adapted | Delta |",
        f"|-----------|--------|------|---------|-------|",
    ]
    for dim in ["accuracy", "completeness", "relevance", "legal_correctness"]:
        w = weights.get(dim, 0.25)
        b = base_avgs.get(dim, 0.0)
        a = adapted_avgs.get(dim, 0.0)
        d = round(a - b, 2)
        d_str = f"+{d}" if d >= 0 else str(d)
        card_lines.append(f"| {dim} | {w:.0%} | {b:.2f} | {a:.2f} | {d_str} |")

    card_lines += [
        f"",
        f"## Sample Count",
        f"",
        f"- Base model: {len(base_results)} tasks",
        f"- Adapted model: {len(adapted_results)} tasks",
        f"",
        f"---",
        f"",
        f"*Scores are on a 1–10 scale. Weighted score uses domain-specific weights.*",
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    card_path = output_dir / f"domain_card_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    card_path.write_text("\n".join(card_lines), encoding="utf-8")
    print(f"\n[Domain Card] Saved to: {card_path}")
    return card_path


def main():
    parser = argparse.ArgumentParser(
        description="Kwyre Benchmark Suite — Compliance Task Evaluation"
    )
    parser.add_argument(
        "--kwyre-url",
        default="http://127.0.0.1:8000",
        help="Kwyre API endpoint (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--kwyre-api-key",
        default="sk-kwyre-dev-local",
        help="Kwyre API key",
    )
    parser.add_argument(
        "--compare-openai",
        action="store_true",
        help="Also run prompts against OpenAI for comparison",
    )
    parser.add_argument(
        "--openai-model",
        default="gpt-4o",
        help="OpenAI model for comparison (default: gpt-4o)",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Run only a specific dataset (e.g., nda_analysis)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1024,
        help="Max tokens per response (default: 1024)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(RESULTS_DIR),
        help="Output directory for results",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print responses to stdout during benchmark",
    )
    parser.add_argument(
        "--skip-scoring",
        action="store_true",
        help="Skip LLM-as-judge scoring (latency benchmarks only)",
    )
    parser.add_argument(
        "--with-adapter",
        action="store_true",
        help="Run benchmark twice: once base model, once with domain adapter loaded",
    )
    parser.add_argument(
        "--adapter-domain",
        default=None,
        help="Domain adapter to load for comparison (e.g. legal_compliance)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  Kwyre Benchmark Suite")
    print("=" * 60)
    print(f"  Kwyre URL:      {args.kwyre_url}")
    print(f"  Compare OpenAI: {args.compare_openai}")
    if args.compare_openai:
        print(f"  OpenAI Model:   {args.openai_model}")
    print(f"  Max Tokens:     {args.max_tokens}")
    print(f"  Dataset:        {args.dataset or 'all'}")
    print(f"  Scoring:        {'disabled' if args.skip_scoring else 'LLM-as-judge'}")
    if args.with_adapter:
        print(f"  Adapter Domain: {args.adapter_domain or '(none specified)'}")
    print("=" * 60)

    # Verify Kwyre is reachable
    print("\nChecking Kwyre server connectivity...", end=" ", flush=True)
    try:
        resp = requests.get(f"{args.kwyre_url}/health", timeout=5)
        if resp.status_code == 200:
            print("OK")
        else:
            print(f"WARNING: status {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print("FAILED")
        print(f"\nError: Cannot connect to Kwyre at {args.kwyre_url}")
        print("Make sure the server is running: python server/serve_local_4bit.py")
        sys.exit(1)

    results = run_benchmark(args)

    output_dir = Path(args.output_dir)
    report_path = generate_report(results, output_dir)

    if args.with_adapter and args.adapter_domain:
        def _flatten_kwyre_results(bench_results: dict) -> list[dict]:
            flat = []
            for ds in bench_results.get("datasets", []):
                for task in ds.get("tasks", []):
                    kw = task.get("kwyre", {})
                    flat.append({"scores": kw.get("scores") or {}})
            return flat

        base_flat = _flatten_kwyre_results(results)

        print(f"\n{'='*60}")
        print(f"  Running adapted benchmark with domain: {args.adapter_domain}")
        print(f"{'='*60}")
        load_adapter_for_benchmark(args.kwyre_url, args.adapter_domain)
        adapted_results_raw = run_benchmark(args)
        unload_adapter_for_benchmark(args.kwyre_url)

        adapted_flat = _flatten_kwyre_results(adapted_results_raw)

        generate_domain_performance_card(
            base_flat, adapted_flat, args.adapter_domain, output_dir
        )

    print(f"\n{'='*60}")
    print(f"  Benchmark complete!")
    print(f"  Report: {report_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
