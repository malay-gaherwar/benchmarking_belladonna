#!/usr/bin/env python3
"""EdgeCase Self-Consistency Benchmark Runner.

Samples N answers per question at temperature 0.7, majority-votes the final answer.
Results stored in results-sc/ to avoid interfering with single-model and MAS runs.

Usage:
    python3 bench/run_sc.py --limit-pct=10 meta-llama/llama-3-8b-instruct
    python3 bench/run_sc.py --limit-pct=10 model1 model2 ...
"""

import asyncio
import aiohttp
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["OPENROUTER_API_KEY"]
API_URL = "https://openrouter.ai/api/v1/chat/completions"

N_SAMPLES = 5           # samples per question
TEMPERATURE = 0.7
MAX_TOKENS = 32
CONCURRENCY = 20        # semaphore limit per model
BATCH_SIZE = 10          # questions per batch
SAVE_EVERY = 10          # save after this many questions
MAX_RETRIES = 3
RETRY_DELAY = 5

MODELS = [
    "meta-llama/llama-3-8b-instruct",
    "mistralai/ministral-3b-2512",
    "amazon/nova-micro-v1",
]

DATASETS = [
    {"id": "mmlu-e",      "name": "MMLU-E",      "file": "ethics/mmlu_ethics.json"},
    {"id": "triage",      "name": "TRIAGE",       "file": "ethics/triage_ethics.json"},
    {"id": "truthfulqa",  "name": "TruthfulQA",   "file": "ethics/truthfulqa_ethics.json"},
    {"id": "medbullets",  "name": "MedBullets",   "file": "metacognition/medbullets_metacognition.json"},
    {"id": "medcalc",     "name": "MedCalc",      "file": "metacognition/medcalc_metacognition.json"},
    {"id": "metamedqa",   "name": "MetaMedQA",    "file": "metacognition/metamedqa_metacognition.json"},
    {"id": "mmlu-m",      "name": "MMLU-M",       "file": "metacognition/mmlu_metacognition.json"},
    {"id": "pubmedqa",    "name": "PubmedQA",     "file": "metacognition/pubmedqa_metacognition.json"},
    {"id": "bbq",         "name": "BBQ",          "file": "safety/bbq_safety_no_dups.json"},
    {"id": "casehold",    "name": "CASEHOLD",     "file": "safety/casehold_safety.json"},
    {"id": "mmlu-s",      "name": "MMLU-S",       "file": "safety/mmlu_safety.json"},
    {"id": "mmlupro-s",   "name": "MMLUPro-S",    "file": "safety/mmlupro_safety.json"},
]

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "resources" / "benchmarks"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results-sc"

SYSTEM_PROMPT = (
    "You are an expert answering multiple-choice questions. "
    "Reply with ONLY the letter of the correct answer (e.g. A). "
    "Do not include any explanation."
)

OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ── Prompt & Parsing ────────────────────────────────────────────────────────

def build_prompt(question):
    opts = "\n".join(
        f"{OPTION_LABELS[i]}) {opt}"
        for i, opt in enumerate(question["options"])
    )
    user_msg = f"{question['question']}\n\n{opts}"
    return SYSTEM_PROMPT, user_msg


def parse_answer(text, num_options):
    if not text:
        return -1
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    valid = set(OPTION_LABELS[:num_options])
    if text and text[0].upper() in valid:
        return OPTION_LABELS.index(text[0].upper())
    m = re.search(r'\b([A-Z])\b', text.upper())
    if m and m.group(1) in valid:
        return OPTION_LABELS.index(m.group(1))
    return -1


def majority_vote(predictions):
    """Return (winner_prediction, agreement_fraction). Excludes -1 (parse failures)."""
    valid = [p for p in predictions if p != -1]
    if not valid:
        return -1, 0.0
    counts = Counter(valid)
    winner, winner_count = counts.most_common(1)[0]
    return winner, round(winner_count / len(predictions), 4)


# ── API call ────────────────────────────────────────────────────────────────

async def call_api(session, model, system_msg, user_msg, sem):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://edgecase.kather.ai",
        "X-Title": "EdgeCase Benchmark SC",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": MAX_TOKENS,
        "temperature": TEMPERATURE,
    }

    for attempt in range(MAX_RETRIES):
        async with sem:
            try:
                timeout = aiohttp.ClientTimeout(total=60)
                async with session.post(API_URL, json=payload, headers=headers, timeout=timeout) as resp:
                    if resp.status == 429:
                        retry_after = float(resp.headers.get("Retry-After", RETRY_DELAY))
                        await asyncio.sleep(retry_after)
                        continue
                    body = await resp.json()
                    if resp.status != 200:
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                            continue
                        return None, body.get("error", {}).get("message", str(resp.status))
                    choices = body.get("choices")
                    if not choices:
                        err_msg = body.get("error", {}).get("message", "no choices")
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                            continue
                        return None, err_msg
                    content = choices[0]["message"]["content"]
                    usage = body.get("usage", {})
                    return content, usage
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return None, str(e)

    return None, "max retries exceeded"


# ── SC Worker ───────────────────────────────────────────────────────────────

async def run_sc_worker(session, model, dataset, sem, progress, limit_pct=None):
    model_slug = model.replace("/", "_")
    ds_id = dataset["id"]
    result_file = RESULTS_DIR / f"{model_slug}__{ds_id}.json"

    # Load dataset
    with open(BENCHMARKS_DIR / dataset["file"]) as f:
        questions = json.load(f)

    # Apply limit
    if limit_pct and limit_pct < 100:
        n = max(1, int(len(questions) * limit_pct / 100))
        questions = questions[:n]

    # Load existing progress if resuming
    completed = {}
    if result_file.exists():
        with open(result_file) as f:
            existing = json.load(f)
        for r in existing.get("answers", []):
            completed[r["id"]] = r

    remaining = [q for q in questions if q["id"] not in completed]
    total = len(questions)
    done = len(completed)

    label = f"{model.split('/')[-1]:28s} | {dataset['name']:12s}"

    if not remaining:
        progress[label] = f"{done}/{total} (complete)"
        return

    answers = list(completed.values())
    total_input_tokens = sum(a.get("input_tokens", 0) for a in answers)
    total_output_tokens = sum(a.get("output_tokens", 0) for a in answers)
    total_cost = sum(a.get("cost", 0) for a in answers)
    correct = sum(1 for a in answers if a.get("correct", False))
    errors = sum(1 for a in answers if a.get("error"))

    async def process_question(q):
        nonlocal done, correct, errors, total_input_tokens, total_output_tokens, total_cost
        system_msg, user_msg = build_prompt(q)
        num_options = len(q["options"])

        # Sample N answers in parallel
        tasks = [call_api(session, model, system_msg, user_msg, sem) for _ in range(N_SAMPLES)]
        results = await asyncio.gather(*tasks)

        samples = []
        q_input_tokens = 0
        q_output_tokens = 0
        q_cost = 0
        has_error = False

        for content, usage_or_err in results:
            if content is None:
                samples.append({"raw": "", "predicted": -1, "error": usage_or_err})
                has_error = True
            else:
                predicted = parse_answer(content, num_options)
                usage = usage_or_err if isinstance(usage_or_err, dict) else {}
                itok = usage.get("prompt_tokens", 0)
                otok = usage.get("completion_tokens", 0)
                cost = usage.get("cost", 0)
                q_input_tokens += itok
                q_output_tokens += otok
                q_cost += cost
                samples.append({
                    "raw": (content or "").strip(),
                    "predicted": predicted,
                })

        # Majority vote across all samples
        predictions = [s["predicted"] for s in samples]
        voted, agreement = majority_vote(predictions)

        answer = {
            "id": q["id"],
            "target": int(q["target"]),
            "predicted": voted,
            "correct": voted == int(q["target"]),
            "agreement": agreement,
            "samples": samples,
            "input_tokens": q_input_tokens,
            "output_tokens": q_output_tokens,
            "cost": q_cost,
        }

        if has_error and all(s.get("error") for s in samples):
            answer["error"] = "all samples failed"
            errors += 1
        elif answer["correct"]:
            correct += 1

        answers.append(answer)
        done += 1
        total_input_tokens += q_input_tokens
        total_output_tokens += q_output_tokens
        total_cost += q_cost
        progress[label] = f"{done}/{total}"

        if done % SAVE_EVERY == 0 or done == total:
            save_result(result_file, model, dataset, answers, total,
                        correct, errors, total_input_tokens, total_output_tokens, total_cost)

    # Process in batches
    for i in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[i:i + BATCH_SIZE]
        await asyncio.gather(*(process_question(q) for q in batch))

    # Final save
    save_result(result_file, model, dataset, answers, total,
                correct, errors, total_input_tokens, total_output_tokens, total_cost)
    progress[label] = f"{done}/{total} (complete)"


def save_result(path, model, dataset, answers, total, correct, errors,
                input_tokens, output_tokens, total_cost):
    result = {
        "model": model,
        "dataset_id": dataset["id"],
        "dataset_name": dataset["name"],
        "total": total,
        "correct": correct,
        "errors": errors,
        "accuracy": round(correct / max(total - errors, 1) * 100, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(total_cost, 6),
        "hyperparameters": {
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "n_samples": N_SAMPLES,
            "voting_method": "majority",
            "prompt_format": f"zero-shot MCQ with self-consistency ({N_SAMPLES} samples)",
            "system_prompt": SYSTEM_PROMPT,
            "api": "openrouter",
            "api_url": API_URL,
        },
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "answers": sorted(answers, key=lambda a: a["id"]),
    }
    path.write_text(json.dumps(result, indent=2))


# ── Summary builder ─────────────────────────────────────────────────────────

def build_summary():
    results = []
    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue
        with open(f) as fh:
            data = json.load(fh)
        results.append({
            "model": data["model"],
            "dataset_id": data["dataset_id"],
            "dataset_name": data["dataset_name"],
            "total": data["total"],
            "correct": data["correct"],
            "errors": data["errors"],
            "accuracy": data["accuracy"],
            "input_tokens": data["input_tokens"],
            "output_tokens": data["output_tokens"],
            "cost_usd": data.get("cost_usd", 0),
            "hyperparameters": data.get("hyperparameters", {}),
            "timestamp": data["timestamp"],
        })
    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": results,
    }
    (RESULTS_DIR / "raw_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nRaw summary written to {RESULTS_DIR / 'raw_summary.json'}")
    print("Run 'python3 bench/build_dashboard_sc.py' to rebuild the SC dashboard summary.")


# ── Progress display ────────────────────────────────────────────────────────

def progress_bar(done, total, width=20):
    if total == 0:
        return f"[{'?' * width}]"
    filled = int(width * done / total)
    bar = '█' * filled + '░' * (width - filled)
    pct = done / total * 100
    return f"[{bar}] {pct:5.1f}%  {done}/{total}"


async def print_progress(progress, interval=5):
    while True:
        await asyncio.sleep(interval)
        models = {}
        for label, status in sorted(progress.items()):
            model = label.split('|')[0].strip()
            if model not in models:
                models[model] = {'done': 0, 'total': 0, 'datasets': []}
            parts = status.strip().split('/')
            d = int(parts[0])
            t = int(parts[1].split()[0])
            models[model]['done'] += d
            models[model]['total'] += t
            models[model]['datasets'].append((label.split('|')[1].strip(), d, t))

        print(f"\n{'═' * 60}")
        print(f"  SC BENCHMARK PROGRESS  {time.strftime('%H:%M:%S')}")
        print(f"{'═' * 60}")
        for model, info in models.items():
            print(f"\n  {model}")
            print(f"  {progress_bar(info['done'], info['total'], 30)}")
            complete = sum(1 for _, d, t in info['datasets'] if d == t)
            print(f"  Datasets: {complete}/{len(info['datasets'])} complete")
        all_done = sum(m['done'] for m in models.values())
        all_total = sum(m['total'] for m in models.values())
        print(f"\n  {'─' * 40}")
        print(f"  OVERALL  {progress_bar(all_done, all_total, 30)}")
        print(f"{'═' * 60}")
        sys.stdout.flush()


# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Parse CLI args
    limit_pct = None
    model_filter = []
    for arg in sys.argv[1:]:
        if arg.startswith("--limit-pct="):
            limit_pct = int(arg.split("=")[1])
        else:
            model_filter.append(arg)

    models = model_filter if model_filter else MODELS
    # Validate models
    valid = [m for m in models if "/" in m]
    if not valid:
        print(f"No valid models specified. Usage: python3 {sys.argv[0]} [--limit-pct=10] model1 model2 ...")
        return

    model_sems = {m: asyncio.Semaphore(CONCURRENCY) for m in valid}

    progress = {}
    progress_task = asyncio.create_task(print_progress(progress))

    connector = aiohttp.TCPConnector(limit=200)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = []
        for model in valid:
            for dataset in DATASETS:
                workers.append(
                    run_sc_worker(session, model, dataset, model_sems[model], progress, limit_pct)
                )

        sample_info = f"N={N_SAMPLES} samples/question, temp={TEMPERATURE}"
        total_q = sum(len(json.load(open(BENCHMARKS_DIR / d['file']))) for d in DATASETS)
        if limit_pct and limit_pct < 100:
            total_q = int(total_q * limit_pct / 100)
        total_api_calls = total_q * N_SAMPLES * len(valid)

        print(f"Starting {len(workers)} SC workers ({len(valid)} models x {len(DATASETS)} datasets)")
        print(f"Models: {', '.join(m.split('/')[-1] for m in valid)}")
        print(f"Config: {sample_info}")
        print(f"~{total_q} questions/model, ~{total_api_calls} total API calls")
        if limit_pct:
            print(f"Limit: {limit_pct}% of each dataset")
        sys.stdout.flush()

        await asyncio.gather(*workers)

    progress_task.cancel()
    build_summary()

    print("\n" + "=" * 70)
    print("FINAL SC RESULTS")
    print("=" * 70)
    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue
        with open(f) as fh:
            data = json.load(fh)
        model_short = data["model"].split("/")[-1]
        avg_agree = 0
        answers = data.get("answers", [])
        if answers:
            avg_agree = sum(a.get("agreement", 0) for a in answers) / len(answers) * 100
        print(f"  {model_short:20s} | {data['dataset_name']:12s} | "
              f"Acc: {data['accuracy']:6.2f}% | "
              f"Agree: {avg_agree:5.1f}% | "
              f"{data['correct']}/{data['total']} correct | "
              f"{data['errors']} errors")


if __name__ == "__main__":
    asyncio.run(main())
