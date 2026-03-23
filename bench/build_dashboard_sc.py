#!/usr/bin/env python3
"""Build summary.json for the EdgeCase Self-Consistency results dashboard.

Includes models that have completed all 12 datasets (with at least 1 answer each).
Computes single-model baseline accuracy on same question IDs for comparison.

Usage:  python3 bench/build_dashboard_sc.py
"""

import json
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results-sc"
SINGLE_RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"

DATASET_ORDER = [
    "mmlu-e", "triage", "truthfulqa",
    "medbullets", "medcalc", "metamedqa", "mmlu-m", "pubmedqa",
    "bbq", "casehold", "mmlu-s", "mmlupro-s",
]

CATEGORY_MAP = {
    "Ethics":     {"color": "#7c3aed", "bg": "#ede9fe", "datasets": ["mmlu-e", "triage", "truthfulqa", "bbq"]},
    "Reasoning":  {"color": "#1e40af", "bg": "#dbeafe", "datasets": ["mmlu-e", "truthfulqa", "medbullets", "medcalc", "metamedqa", "mmlu-m", "pubmedqa", "bbq", "casehold", "mmlu-s", "mmlupro-s"]},
    "Safety":     {"color": "#9d174d", "bg": "#fce7f3", "datasets": ["triage", "bbq", "casehold", "mmlu-s", "mmlupro-s"]},
}

MODEL_PARAMS = {
    "meta-llama/llama-3-8b-instruct":  {"total": 8,  "active": 8,  "arch": "dense"},
    "mistralai/ministral-3b-2512":     {"total": 3,  "active": 3,  "arch": "dense"},
    "amazon/nova-micro-v1":            None,
    "mistralai/ministral-14b-2512":    {"total": 14, "active": 14, "arch": "dense"},
    "thedrummer/cydonia-24b-v4.1":     {"total": 24, "active": 24, "arch": "dense"},
    "google/gemma-3-12b-it":           {"total": 12, "active": 12, "arch": "dense"},
    "mistralai/ministral-8b-2512":     {"total": 8,  "active": 8,  "arch": "dense"},
    "mistralai/mistral-nemo":          {"total": 12, "active": 12, "arch": "dense"},
    "meta-llama/llama-3.1-8b-instruct": {"total": 8, "active": 8,  "arch": "dense"},
    "liquid/lfm2-8b-a1b":             {"total": 8,  "active": 1,  "arch": "MoE"},
}

FULL_DATASET_SIZES = {
    "mmlu-e": 895, "triage": 86, "truthfulqa": 790,
    "medbullets": 308, "medcalc": 420, "metamedqa": 1373,
    "mmlu-m": 398, "pubmedqa": 1000,
    "bbq": 871, "casehold": 403, "mmlu-s": 1534, "mmlupro-s": 1101,
}

DATASET_CATEGORIES = {
    "mmlu-e":     ["Ethics", "Reasoning"],
    "triage":     ["Ethics", "Safety"],
    "truthfulqa": ["Ethics", "Reasoning"],
    "medbullets": ["Reasoning"],
    "medcalc":    ["Reasoning"],
    "metamedqa":  ["Reasoning"],
    "mmlu-m":     ["Reasoning"],
    "pubmedqa":   ["Reasoning"],
    "bbq":        ["Ethics", "Reasoning", "Safety"],
    "casehold":   ["Reasoning", "Safety"],
    "mmlu-s":     ["Reasoning", "Safety"],
    "mmlupro-s":  ["Reasoning", "Safety"],
}


def load_result(path):
    with open(path) as f:
        return json.load(f)


def load_single_model_baselines():
    """Load single-model results keyed by (model, dataset_id) -> {question_id -> is_correct}."""
    baselines = {}
    for f in sorted(SINGLE_RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue
        data = load_result(f)
        model = data["model"]
        ds_id = data["dataset_id"]
        # Only non-reasoning variants
        if "__reasoning-" in f.name:
            continue
        answer_map = {}
        for a in data.get("answers", []):
            answer_map[a["id"]] = a.get("correct", False)
        baselines[(model, ds_id)] = answer_map
    return baselines


def compute_baseline_accuracy(baselines, model, ds_id, sc_question_ids):
    answer_map = baselines.get((model, ds_id), {})
    if not answer_map:
        return None
    matched = [qid for qid in sc_question_ids if qid in answer_map]
    if not matched:
        return None
    correct = sum(1 for qid in matched if answer_map[qid])
    return round(correct / len(matched) * 100, 2)


def display_name(model_name):
    return model_name.split("/")[-1]


def build():
    baselines = load_single_model_baselines()
    model_results = {}

    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue
        data = load_result(f)
        model = data["model"]
        ds_id = data["dataset_id"]

        if model not in model_results:
            model_results[model] = {}
        model_results[model][ds_id] = data

    # Completeness filter: all 12 datasets present with at least 1 answer
    complete_models = {}
    for model, datasets in model_results.items():
        tag = display_name(model)
        if set(datasets.keys()) != set(DATASET_ORDER):
            missing = set(DATASET_ORDER) - set(datasets.keys())
            print(f"  SKIP {tag}: missing datasets {missing}")
            continue

        all_have_answers = True
        partial = False
        for ds_id in DATASET_ORDER:
            data = datasets[ds_id]
            n_answers = len(data.get("answers", []))
            if n_answers == 0:
                print(f"  SKIP {tag}: {ds_id} has no answers")
                all_have_answers = False
                break
            if n_answers < data["total"]:
                partial = True
        if all_have_answers:
            complete_models[model] = datasets
            if partial:
                print(f"  INCLUDE {tag}: partial run")

    print(f"\n{len(complete_models)} SC model(s) included out of {len(model_results)} total\n")

    models_out = []
    for model, datasets in complete_models.items():
        slug = model.replace("/", "_")
        name = display_name(model)
        params_info = MODEL_PARAMS.get(model, None)

        per_dataset = []
        total_correct = 0
        total_questions = 0
        total_errors = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        all_agreements = []

        baseline_correct_total = 0
        baseline_answered_total = 0

        for ds_id in DATASET_ORDER:
            d = datasets[ds_id]
            cost = d.get("cost_usd", 0) or 0
            answers_list = d.get("answers", [])
            n_answered = len(answers_list)
            n_correct = sum(1 for a in answers_list if a.get("correct", False))
            n_errors = sum(1 for a in answers_list if a.get("error"))
            ds_accuracy = round(n_correct / max(n_answered - n_errors, 1) * 100, 2)

            # Agreement stats
            ds_agreements = [a.get("agreement", 0) for a in answers_list if not a.get("error")]
            avg_agreement = round(sum(ds_agreements) / max(len(ds_agreements), 1) * 100, 2)
            all_agreements.extend(ds_agreements)

            # Baseline on same question IDs
            sc_qids = [a["id"] for a in answers_list if not a.get("error")]
            baseline_acc = compute_baseline_accuracy(baselines, model, ds_id, sc_qids)

            if baseline_acc is not None:
                baseline_answer_map = baselines.get((model, ds_id), {})
                matched_ids = [qid for qid in sc_qids if qid in baseline_answer_map]
                baseline_correct_total += sum(1 for qid in matched_ids if baseline_answer_map[qid])
                baseline_answered_total += len(matched_ids)

            per_dataset.append({
                "dataset_id": ds_id,
                "dataset_name": d["dataset_name"],
                "total": n_answered,
                "total_in_dataset": FULL_DATASET_SIZES.get(ds_id, d["total"]),
                "correct": n_correct,
                "errors": n_errors,
                "accuracy": ds_accuracy,
                "baseline_accuracy": baseline_acc,
                "avg_agreement": avg_agreement,
                "input_tokens": d["input_tokens"],
                "output_tokens": d["output_tokens"],
                "cost_usd": cost,
                "categories": DATASET_CATEGORIES.get(ds_id, []),
            })
            total_correct += n_correct
            total_questions += n_answered
            total_errors += n_errors
            total_input_tokens += d["input_tokens"]
            total_output_tokens += d["output_tokens"]
            total_cost += cost

        overall_accuracy = round(total_correct / max(total_questions - total_errors, 1) * 100, 2)
        baseline_overall = round(baseline_correct_total / max(baseline_answered_total, 1) * 100, 2) if baseline_answered_total > 0 else None
        avg_agreement_overall = round(sum(all_agreements) / max(len(all_agreements), 1) * 100, 2)

        # Per-category accuracy
        ds_lookup = {pd["dataset_id"]: pd for pd in per_dataset}
        category_stats = {}
        for cat_name, cat_info in CATEGORY_MAP.items():
            cat_correct = 0
            cat_total = 0
            cat_errors = 0
            for ds_id in cat_info["datasets"]:
                if ds_id in ds_lookup:
                    pd = ds_lookup[ds_id]
                    cat_correct += pd["correct"]
                    cat_total += pd["total"]
                    cat_errors += pd["errors"]
            cat_accuracy = round(cat_correct / max(cat_total - cat_errors, 1) * 100, 2) if cat_total > 0 else 0
            category_stats[cat_name] = {
                "correct": cat_correct,
                "total": cat_total,
                "errors": cat_errors,
                "accuracy": cat_accuracy,
            }

        # Extract hyperparameters
        first_ds = datasets[DATASET_ORDER[0]]
        hyper = first_ds.get("hyperparameters", {})

        models_out.append({
            "slug": slug,
            "model": model,
            "display_name": name,
            "params": params_info,
            "overall_accuracy": overall_accuracy,
            "baseline_accuracy": baseline_overall,
            "avg_agreement": avg_agreement_overall,
            "n_samples": hyper.get("n_samples", 5),
            "total_correct": total_correct,
            "total_questions": total_questions,
            "total_errors": total_errors,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": round(total_cost, 6),
            "categories": category_stats,
            "datasets": per_dataset,
            "temperature": hyper.get("temperature", 0.7),
        })

    # Filter out zero-accuracy
    models_out = [m for m in models_out if m["overall_accuracy"] > 0]

    # Sort by overall accuracy descending, assign rank
    models_out.sort(key=lambda m: m["overall_accuracy"], reverse=True)
    for i, m in enumerate(models_out):
        m["rank"] = i + 1

    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_order": DATASET_ORDER,
        "category_map": {
            name: {"color": info["color"], "bg": info["bg"]}
            for name, info in CATEGORY_MAP.items()
        },
        "models": models_out,
    }

    out_path = RESULTS_DIR / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"Summary written to {out_path}")
    for m in models_out:
        params = f" {m['params']['total']}B" if m.get('params') else ""
        base = m.get('baseline_accuracy')
        diff = ""
        if base is not None:
            d = m['overall_accuracy'] - base
            diff = f"  (baseline={base}%, {'+'if d>0 else ''}{d:.1f}%)"
        print(f"  #{m['rank']} {m['display_name']}{params}: {m['overall_accuracy']}%  "
              f"agree={m['avg_agreement']:.1f}%{diff}  "
              f"${m['total_cost_usd']:.4f}")


if __name__ == "__main__":
    build()
