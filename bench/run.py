#!/usr/bin/env python3
"""EdgeCase Benchmark Runner — parallel workers via asyncio + aiohttp."""

import asyncio
import aiohttp
import json
import os
import re
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.environ["OPENROUTER_API_KEY"]
API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Each entry: (model_id, reasoning_enabled, effort)
# reasoning=None means model doesn't support reasoning (use default behavior)
# reasoning=True means run with thinking on
# reasoning=False means run with thinking off
# effort=None means no effort limit; "low"/"medium"/"high" caps reasoning budget
MODELS = [
    ("qwen/qwen3.5-flash-02-23", True, None),
    ("qwen/qwen3.5-flash-02-23", False, None),
    ("google/gemini-3.1-flash-lite-preview", None, None),
    ("amazon/nova-micro-v1", None, None),
    ("mistralai/mistral-nemo", None, None),
    ("bytedance-seed/seed-2.0-mini", True, None),
    ("bytedance-seed/seed-2.0-mini", False, None),
    ("mistralai/ministral-8b-2512", None, None),
    ("mistralai/ministral-3b-2512", None, None),
    ("google/gemma-3-12b-it", None, None),
    ("z-ai/glm-4.7-flash", True, None),
    ("z-ai/glm-4.7-flash", False, None),
    ("liquid/lfm2-8b-a1b", None, None),
]

DATASETS = [
    {"id": "expert205", "name": "Expert205", "file": "expert/205expertquestions.json"},
]

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent / "resources" / "benchmarks"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

SYSTEM_PROMPT = (
    "You are an expert answering multiple-choice questions. "
    "Reply with ONLY the letter of the correct answer (e.g. A). "
    "Do not include any explanation."
)


def get_hyperparameters(model, reasoning, effort=None):
    """Return the hyperparameters used for a given model run."""
    return {
        "temperature": 0.7,
        "max_tokens": 4096 if reasoning is True else 32,
        "reasoning": reasoning,
        "reasoning_effort": effort,
        "system_prompt": SYSTEM_PROMPT,
        "prompt_format": "zero-shot MCQ",
        "api": "openrouter",
        "api_url": API_URL,
    }


# ── Prompt ──────────────────────────────────────────────────────────────────

OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def build_prompt(question):
    """Build a zero-shot MCQ prompt. Returns (system_msg, user_msg)."""
    opts = "\n".join(
        f"{OPTION_LABELS[i]}) {opt}"
        for i, opt in enumerate(question["options"])
    )
    user_msg = f"{question['question']}\n\n{opts}"
    return SYSTEM_PROMPT, user_msg


def parse_answer(text, num_options):
    """Extract the answer letter from model response. Returns index or -1."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    valid = set(OPTION_LABELS[:num_options])

    if text and text[0].upper() in valid:
        return OPTION_LABELS.index(text[0].upper())

    m = re.search(r"\b([A-Z])\b", text.upper())
    if m and m.group(1) in valid:
        return OPTION_LABELS.index(m.group(1))

    return -1


def load_dataset_questions(dataset_file: str) -> list[dict]:
    """Load benchmark questions from either a plain list or a wrapped object."""
    with open(BENCHMARKS_DIR / dataset_file, encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        questions = raw.get("questions")
        if not isinstance(questions, list):
            raise ValueError(
                f"Dataset {dataset_file} is a JSON object but has no valid 'questions' list"
            )
        return questions

    if isinstance(raw, list):
        return raw

    raise ValueError(f"Unsupported dataset format in {dataset_file}")


# ── API call ────────────────────────────────────────────────────────────────

async def call_api(session, model, system_msg, user_msg, sem, reasoning=None, effort=None):
    """Call OpenRouter API with retry logic."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://edgecase.kather.ai",
        "X-Title": "EdgeCase Benchmark",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 4096 if reasoning is True else 32,
        "temperature": 0.7,
    }
    if reasoning is not None:
        reasoning_cfg = {"enabled": reasoning}
        if effort and reasoning:
            reasoning_cfg["effort"] = effort
        payload["reasoning"] = reasoning_cfg

    for attempt in range(MAX_RETRIES):
        async with sem:
            try:
                timeout = aiohttp.ClientTimeout(total=120 if reasoning is True else 60)
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
                        err_msg = body.get("error", {}).get("message", "no choices in response")
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


# ── Worker ──────────────────────────────────────────────────────────────────

async def run_worker(session, model, dataset, sem, progress, reasoning=None, effort=None):
    """Benchmark one model on one dataset."""
    model_slug = model.replace("/", "_")
    if reasoning is True:
        model_slug += "__reasoning-on"
        if effort:
            model_slug += f"-{effort}"
    elif reasoning is False:
        model_slug += "__reasoning-off"

    ds_id = dataset["id"]
    result_file = RESULTS_DIR / f"{model_slug}__{ds_id}.json"

    questions = load_dataset_questions(dataset["file"])

    completed = {}
    if result_file.exists():
        with open(result_file, encoding="utf-8") as f:
            existing = json.load(f)
        for r in existing.get("answers", []):
            completed[r["id"]] = r

    remaining = [q for q in questions if q["id"] not in completed]
    total = len(questions)
    done = len(completed)

    reasoning_tag = ""
    if reasoning is True:
        reasoning_tag = f" (think,{effort})" if effort else " (think)"
    elif reasoning is False:
        reasoning_tag = " (no-think)"
    label = f"{model.split('/')[-1] + reasoning_tag:28s} | {dataset['name']:12s}"

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
        content, usage_or_err = await call_api(session, model, system_msg, user_msg, sem, reasoning, effort)

        answer = {
            "id": q["id"],
            "target": q["target"],
        }

        if content is None:
            answer["error"] = usage_or_err
            answer["correct"] = False
            answer["predicted"] = -1
            errors += 1
        else:
            predicted = parse_answer(content, len(q["options"]))
            answer["predicted"] = predicted
            answer["correct"] = predicted == int(q["target"])
            answer["raw"] = content.strip()
            answer["input_tokens"] = usage_or_err.get("prompt_tokens", 0)
            answer["output_tokens"] = usage_or_err.get("completion_tokens", 0)
            answer["cost"] = usage_or_err.get("cost", 0)
            total_input_tokens += answer["input_tokens"]
            total_output_tokens += answer["output_tokens"]
            total_cost += answer.get("cost", 0)
            if answer["correct"]:
                correct += 1

        answers.append(answer)
        done += 1
        progress[label] = f"{done}/{total}"

        if done % 50 == 0 or done == total:
            save_result(
                result_file,
                model,
                dataset,
                answers,
                total,
                correct,
                errors,
                total_input_tokens,
                total_output_tokens,
                total_cost,
                reasoning,
                effort,
            )

    batch_size = 20 if reasoning is True else 10
    for i in range(0, len(remaining), batch_size):
        batch = remaining[i:i + batch_size]
        await asyncio.gather(*(process_question(q) for q in batch))

    save_result(
        result_file,
        model,
        dataset,
        answers,
        total,
        correct,
        errors,
        total_input_tokens,
        total_output_tokens,
        total_cost,
        reasoning,
        effort,
    )
    progress[label] = f"{done}/{total} (complete)"


def save_result(path, model, dataset, answers, total, correct, errors,
                input_tokens, output_tokens, total_cost=0, reasoning=None, effort=None):
    """Save results to JSON."""
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
        "hyperparameters": get_hyperparameters(model, reasoning, effort),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "answers": sorted(answers, key=lambda a: a["id"]),
    }
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")


# ── Summary builder ─────────────────────────────────────────────────────────

def build_summary():
    """Build raw_summary.json from all result files for the web frontend."""
    results = []
    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue
        with open(f, encoding="utf-8") as fh:
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
    (RESULTS_DIR / "raw_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nRaw summary written to {RESULTS_DIR / 'raw_summary.json'}")
    print("Run 'python3 bench/build_dashboard.py' to rebuild the dashboard summary.")


# ── Progress display ────────────────────────────────────────────────────────

def progress_bar(done, total, width=20):
    """Render an ASCII progress bar."""
    if total == 0:
        return f"[{'?' * width}]"
    filled = int(width * done / total)
    bar = "█" * filled + "░" * (width - filled)
    pct = done / total * 100
    return f"[{bar}] {pct:5.1f}%  {done}/{total}"


async def print_progress(progress, interval=5):
    """Periodically print progress with ASCII bars."""
    while True:
        await asyncio.sleep(interval)
        models = {}
        for label, status in sorted(progress.items()):
            model = label.split("|")[0].strip()
            if model not in models:
                models[model] = {"done": 0, "total": 0, "datasets": []}
            parts = status.strip().split("/")
            d = int(parts[0])
            t = int(parts[1].split()[0])
            models[model]["done"] += d
            models[model]["total"] += t
            models[model]["datasets"].append((label.split("|")[1].strip(), d, t))

        print(f"\n{'═' * 60}")
        print(f"  BENCHMARK PROGRESS  {time.strftime('%H:%M:%S')}")
        print(f"{'═' * 60}")
        for model, info in models.items():
            print(f"\n  {model}")
            print(f"  {progress_bar(info['done'], info['total'], 30)}")
            complete = sum(1 for _, d, t in info["datasets"] if d == t)
            print(f"  Datasets: {complete}/{len(info['datasets'])} complete")
        all_done = sum(m["done"] for m in models.values())
        all_total = sum(m["total"] for m in models.values())
        print(f"\n  {'─' * 40}")
        print(f"  OVERALL  {progress_bar(all_done, all_total, 30)}")
        print(f"{'═' * 60}")
        sys.stdout.flush()


# ── Main ────────────────────────────────────────────────────────────────────

async def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    model_filter = set(sys.argv[1:]) if len(sys.argv) > 1 else None
    models = MODELS
    if model_filter:
        models = [(m, r, e) for m, r, e in MODELS if m in model_filter]
        if not models:
            print(f"No matching models for filter: {model_filter}")
            return

    def sem_size(reasoning):
        return 30 if reasoning is True else 20

    model_sems = {
        (model, reasoning): asyncio.Semaphore(sem_size(reasoning))
        for model, reasoning, effort in models
    }

    progress = {}
    progress_task = asyncio.create_task(print_progress(progress))

    connector = aiohttp.TCPConnector(limit=200)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = []
        for model, reasoning, effort in models:
            for dataset in DATASETS:
                workers.append(
                    run_worker(session, model, dataset, model_sems[(model, reasoning)], progress, reasoning, effort)
                )

        print(f"Starting {len(workers)} workers ({len(models)} model configs x {len(DATASETS)} datasets)")
        print(
            "Models: "
            + ", ".join(
                m.split("/")[-1]
                + (" (think" + (",effort=" + e if e else "") + ")" if r is True else " (no-think)" if r is False else "")
                for m, r, e in models
            )
        )
        print(f"Total questions per model: {sum(len(load_dataset_questions(d['file'])) for d in DATASETS)}")
        sys.stdout.flush()

        await asyncio.gather(*workers)

    progress_task.cancel()

    build_summary()

    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        model_short = data["model"].split("/")[-1]
        print(
            f"  {model_short:20s} | {data['dataset_name']:12s} | "
            f"Acc: {data['accuracy']:6.2f}% | "
            f"{data['correct']}/{data['total']} correct | "
            f"{data['errors']} errors"
        )


if __name__ == "__main__":
    asyncio.run(main())