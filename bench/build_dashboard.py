#!/usr/bin/env python3
"""Build summary.json for the EdgeCase dashboard.

Current setup:
- focuses on the Expert200 dataset
- skips aggregate files like raw_summary.json / summary.json
- computes per-kind accuracy breakdown from dataset question metadata
- keeps reasoning-on / reasoning-off variants separate

Usage:
    python3 bench/build_dashboard.py
"""

import json
import re
import time
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
ROOT_DIR = Path(__file__).resolve().parent.parent

DATASET_ORDER = [
    "expert200",
]

CATEGORY_MAP = {
    "Expert": {
        "color": "#0f766e",
        "bg": "#ccfbf1",
        "datasets": ["expert200"],
    },
}

MODEL_PARAMS = {
    "liquid/lfm2-8b-a1b": {"total": 8, "active": 1, "arch": "MoE"},
    "mistralai/ministral-14b-2512": {"total": 14, "active": 14, "arch": "dense"},
    "mistralai/ministral-8b-2512": {"total": 8, "active": 8, "arch": "dense"},
    "qwen/qwen3.5-flash-02-23": {"total": 35, "active": 3, "arch": "MoE"},
    "google/gemini-3.1-flash-lite-preview": None,
    "bytedance-seed/seed-2.0-mini": None,
    "aion-labs/aion-2.0": {"total": 671, "active": 37, "arch": "MoE"},
    "thedrummer/cydonia-24b-v4.1": {"total": 24, "active": 24, "arch": "dense"},
    "google/gemma-3-12b-it": {"total": 12, "active": 12, "arch": "dense"},
    "z-ai/glm-4.7-flash": {"total": 30, "active": 3, "arch": "MoE"},
    "meta-llama/llama-3-8b-instruct": {"total": 8, "active": 8, "arch": "dense"},
    "google/gemini-3.1-pro-preview": None,
    "mistralai/mistral-nemo": {"total": 12, "active": 12, "arch": "dense"},
    "meta-llama/llama-3.1-8b-instruct": {"total": 8, "active": 8, "arch": "dense"},
    "amazon/nova-micro-v1": None,
    "mistralai/ministral-3b-2512": {"total": 3, "active": 3, "arch": "dense"},
}

DATASET_CATEGORIES = {
    "expert200": ["Expert"],
}

DATASET_FILE_MAP = {
    "expert200": ROOT_DIR / "resources" / "benchmarks" / "expert" / "200expertquestions.json",
}


def load_result(path):
    with open(path) as f:
        return json.load(f)


def parse_filename(filename):
    """Parse result filename to extract model_slug, reasoning flag, effort, and dataset_id."""
    name = filename.removesuffix(".json")

    m = re.match(r"^(.+)__(reasoning-(on|off)(?:-(\w+))?)__(.+)$", name)
    if m:
        slug = m.group(1)
        on_off = m.group(3)
        effort = m.group(4)
        ds_id = m.group(5)
        reasoning = True if on_off == "on" else False
        return slug, reasoning, effort, ds_id

    parts = name.rsplit("__", 1)
    if len(parts) == 2:
        return parts[0], None, None, parts[1]

    return name, None, None, None


def display_name(model_name):
    return model_name.split("/")[-1]


def load_dataset_questions(dataset_id):
    path = DATASET_FILE_MAP.get(dataset_id)
    if not path or not path.exists():
        return []

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "questions" in raw:
        return raw["questions"]
    if isinstance(raw, list):
        return raw
    return []


def build_kind_breakdown(dataset_id, result_data):
    """Compute per-kind accuracy using dataset file + saved answers."""
    questions = load_dataset_questions(dataset_id)
    if not questions:
        return []

    id_to_kind = {}
    for q in questions:
        qid = q.get("id")
        kind = (q.get("kind") or "Uncategorized").strip()
        if qid is not None:
            id_to_kind[qid] = kind

    stats = {}
    for ans in result_data.get("answers", []):
        qid = ans.get("id")
        if qid not in id_to_kind:
            continue

        kind = id_to_kind[qid]
        if kind not in stats:
            stats[kind] = {"kind": kind, "correct": 0, "total": 0, "errors": 0}

        stats[kind]["total"] += 1
        if ans.get("error"):
            stats[kind]["errors"] += 1
        if ans.get("correct", False):
            stats[kind]["correct"] += 1

    out = []
    for kind in sorted(stats.keys()):
        s = stats[kind]
        accuracy = round(s["correct"] / max(s["total"] - s["errors"], 1) * 100, 2)
        out.append({
            "kind": s["kind"],
            "correct": s["correct"],
            "total": s["total"],
            "errors": s["errors"],
            "accuracy": accuracy,
        })
    return out


def build():
    model_results = {}

    for f in sorted(RESULTS_DIR.glob("*.json")):
        if f.name in ("summary.json", "raw_summary.json"):
            continue

        data = load_result(f)
        if "model" not in data or "dataset_id" not in data:
            print(f"  SKIP non-result file: {f.name}")
            continue

        ds_id = data["dataset_id"]
        if ds_id not in DATASET_ORDER:
            print(f"  SKIP {f.name}: dataset '{ds_id}' not in dashboard dataset list")
            continue

        model = data["model"]

        hyper = data.get("hyperparameters", {})
        reasoning = hyper.get("reasoning", None)
        effort = hyper.get("reasoning_effort", None)

        if "hyperparameters" not in data:
            _, reasoning_from_file, effort_from_file, _ = parse_filename(f.name)
            reasoning = reasoning_from_file
            effort = effort_from_file

        key = (model, reasoning, effort)
        if key not in model_results:
            model_results[key] = {}
        model_results[key][ds_id] = data

    complete_models = {}
    for (model, reasoning, effort), datasets in model_results.items():
        tag = display_name(model)
        if reasoning is True:
            tag += f" (think{',' + effort if effort else ''})"
        elif reasoning is False:
            tag += " (no-think)"

        if set(datasets.keys()) != set(DATASET_ORDER):
            missing = set(DATASET_ORDER) - set(datasets.keys())
            print(f"  SKIP {tag}: missing datasets {missing}")
            continue

        all_complete = True
        for ds_id in DATASET_ORDER:
            data = datasets[ds_id]
            n_answers = len(data.get("answers", []))
            if n_answers < data["total"]:
                print(f"  SKIP {tag}: {ds_id} incomplete ({n_answers}/{data['total']})")
                all_complete = False
                break

        if all_complete:
            complete_models[(model, reasoning, effort)] = datasets

    print(f"\n{len(complete_models)} complete model config(s) out of {len(model_results)} total\n")

    models_out = []
    all_kinds = set()

    for (model, reasoning, effort), datasets in complete_models.items():
        slug = model.replace("/", "_")
        if reasoning is True:
            slug += "__reasoning-on"
            if effort:
                slug += f"-{effort}"
        elif reasoning is False:
            slug += "__reasoning-off"

        name = display_name(model)
        first_ds = datasets[DATASET_ORDER[0]]

        hyper = first_ds.get("hyperparameters", {})
        max_tokens = hyper.get("max_tokens", None)
        temperature = hyper.get("temperature", None)
        params_info = MODEL_PARAMS.get(model, None)

        per_dataset = []
        total_correct = 0
        total_questions = 0
        total_errors = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0

        for ds_id in DATASET_ORDER:
            d = datasets[ds_id]
            cost = d.get("cost_usd", 0) or 0
            kind_breakdown = build_kind_breakdown(ds_id, d)

            for kb in kind_breakdown:
                all_kinds.add(kb["kind"])

            per_dataset.append({
                "dataset_id": ds_id,
                "dataset_name": d["dataset_name"],
                "total": d["total"],
                "correct": d["correct"],
                "errors": d["errors"],
                "accuracy": d["accuracy"],
                "input_tokens": d["input_tokens"],
                "output_tokens": d["output_tokens"],
                "cost_usd": cost,
                "categories": DATASET_CATEGORIES.get(ds_id, []),
                "kind_breakdown": kind_breakdown,
            })

            total_correct += d["correct"]
            total_questions += d["total"]
            total_errors += d["errors"]
            total_input_tokens += d["input_tokens"]
            total_output_tokens += d["output_tokens"]
            total_cost += cost

        overall_accuracy = round(total_correct / max(total_questions - total_errors, 1) * 100, 2)

        category_stats = {}
        for cat_name, cat_info in CATEGORY_MAP.items():
            cat_correct = 0
            cat_total = 0
            cat_errors = 0

            for ds_id in cat_info["datasets"]:
                if ds_id in datasets:
                    d = datasets[ds_id]
                    cat_correct += d["correct"]
                    cat_total += d["total"]
                    cat_errors += d["errors"]

            cat_accuracy = round(cat_correct / max(cat_total - cat_errors, 1) * 100, 2) if cat_total > 0 else 0
            category_stats[cat_name] = {
                "correct": cat_correct,
                "total": cat_total,
                "errors": cat_errors,
                "accuracy": cat_accuracy,
            }

        models_out.append({
            "slug": slug,
            "model": model,
            "display_name": name,
            "reasoning": reasoning,
            "reasoning_effort": effort,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "params": params_info,
            "overall_accuracy": overall_accuracy,
            "total_correct": total_correct,
            "total_questions": total_questions,
            "total_errors": total_errors,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost_usd": round(total_cost, 6),
            "categories": category_stats,
            "datasets": per_dataset,
        })

    models_out = [m for m in models_out if m["total_questions"] > 0]
    models_out.sort(key=lambda m: m["overall_accuracy"], reverse=True)

    for i, m in enumerate(models_out):
        m["rank"] = i + 1

    heatmap_columns = [{"id": "expert200", "label": "Expert200", "type": "dataset"}]
    for kind in sorted(all_kinds):
        heatmap_columns.append({
            "id": f"kind::{kind}",
            "label": kind,
            "type": "kind",
        })

    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_order": DATASET_ORDER,
        "category_map": {
            name: {"color": info["color"], "bg": info["bg"]}
            for name, info in CATEGORY_MAP.items()
        },
        "heatmap_columns": heatmap_columns,
        "models": models_out,
    }

    out_path = RESULTS_DIR / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"Summary written to {out_path}")

    for m in models_out:
        tag = ""
        if m["reasoning"] is True:
            tag = f" (think{',' + m['reasoning_effort'] if m['reasoning_effort'] else ''})"
        elif m["reasoning"] is False:
            tag = " (no-think)"

        params = f" {m['params']['total']}B" if m.get("params") else ""
        print(f"  #{m['rank']} {m['display_name']}{tag}{params}: {m['overall_accuracy']}%  ${m['total_cost_usd']:.4f}")


if __name__ == "__main__":
    build()