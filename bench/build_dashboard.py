#!/usr/bin/env python3
"""Build summary.json for the EdgeCase dashboard.

Features:
- reads result files from results/
- skips aggregate files like raw_summary.json / summary.json
- supports wrapped dataset files: {meta, questions}
- derives dataset metadata from dataset JSON instead of hardcoding
- computes per-kind accuracy breakdown
- builds heatmap columns dynamically:
    - one overall column per dataset
    - one column per kind within each dataset
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT_DIR / "results"
BENCHMARKS_DIR = ROOT_DIR / "resources" / "benchmarks"

# Optional model metadata only for prettier labels.
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


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def display_name(model_name: str) -> str:
    return model_name.split("/")[-1]


def parse_filename(filename: str):
    """Parse result filename.

    Supported patterns:
      modelslug__reasoning-on-medium__datasetid.json
      modelslug__reasoning-on__datasetid.json
      modelslug__reasoning-off__datasetid.json
      modelslug__datasetid.json
    """
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


def find_dataset_file(dataset_id: str) -> Path | None:
    """Find the dataset JSON file by meta.id or fallback filename match."""
    candidates = list(BENCHMARKS_DIR.rglob("*.json"))

    # First try reading wrapped files and matching meta.id
    for path in candidates:
        try:
            raw = load_json(path)
        except Exception:
            continue

        if isinstance(raw, dict):
            meta = raw.get("meta", {})
            if meta.get("id") == dataset_id:
                return path

    # Fallback: filename contains dataset_id
    for path in candidates:
        if dataset_id in path.name:
            return path

    return None


def load_dataset_bundle(dataset_id: str):
    """Return (meta, questions) for a dataset id."""
    path = find_dataset_file(dataset_id)
    if path is None:
        return None, []

    raw = load_json(path)

    if isinstance(raw, dict):
        meta = raw.get("meta", {}) or {}
        questions = raw.get("questions", []) or []
        return meta, questions

    if isinstance(raw, list):
        meta = {
            "id": dataset_id,
            "name": dataset_id,
            "abbrev": dataset_id,
            "source": dataset_id,
            "sourceNote": "",
            "license": "—",
            "description": dataset_id,
            "taskType": "Multiple-choice benchmark",
            "categories": [],
        }
        return meta, raw

    return None, []


def build_kind_breakdown(questions: list[dict], result_data: dict):
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
    result_files = [
        f for f in sorted(RESULTS_DIR.glob("*.json"))
        if f.name not in ("summary.json", "raw_summary.json")
    ]

    model_results: dict[tuple, dict] = {}
    dataset_meta_by_id: dict[str, dict] = {}
    dataset_questions_by_id: dict[str, list] = {}

    # Read results and gather dataset ids
    for f in result_files:
        data = load_json(f)
        if "model" not in data or "dataset_id" not in data:
            print(f"SKIP non-result file: {f.name}")
            continue

        ds_id = data["dataset_id"]
        model = data["model"]

        hyper = data.get("hyperparameters", {})
        reasoning = hyper.get("reasoning", None)
        effort = hyper.get("reasoning_effort", None)

        if "hyperparameters" not in data:
            _, reasoning_from_file, effort_from_file, _ = parse_filename(f.name)
            reasoning = reasoning_from_file
            effort = effort_from_file

        key = (model, reasoning, effort)
        model_results.setdefault(key, {})[ds_id] = data

        if ds_id not in dataset_meta_by_id:
            meta, questions = load_dataset_bundle(ds_id)
            dataset_meta_by_id[ds_id] = meta or {
                "id": ds_id,
                "name": data.get("dataset_name", ds_id),
                "abbrev": ds_id,
                "source": data.get("dataset_name", ds_id),
                "sourceNote": "",
                "license": "—",
                "description": data.get("dataset_name", ds_id),
                "taskType": "Multiple-choice benchmark",
                "categories": [],
            }
            dataset_questions_by_id[ds_id] = questions or []

    dataset_order = sorted(dataset_meta_by_id.keys())

    # Build category map dynamically from dataset meta.categories
    category_names = set()
    for meta in dataset_meta_by_id.values():
        for c in meta.get("categories", []):
            category_names.add(c)

    default_palette = [
        ("#0f766e", "#ccfbf1"),
        ("#1d4ed8", "#dbeafe"),
        ("#9d174d", "#fce7f3"),
        ("#92400e", "#fef3c7"),
        ("#166534", "#dcfce7"),
        ("#6d28d9", "#ede9fe"),
    ]
    category_map = {}
    for i, cat in enumerate(sorted(category_names)):
        color, bg = default_palette[i % len(default_palette)]
        category_map[cat] = {"color": color, "bg": bg}

    complete_models = {}
    required_datasets = set(dataset_order)

    for (model, reasoning, effort), datasets in model_results.items():
        tag = display_name(model)
        if reasoning is True:
            tag += f" (think{',' + effort if effort else ''})"
        elif reasoning is False:
            tag += " (no-think)"

        if set(datasets.keys()) != required_datasets:
            missing = required_datasets - set(datasets.keys())
            print(f"SKIP {tag}: missing datasets {missing}")
            continue

        all_complete = True
        for ds_id in dataset_order:
            data = datasets[ds_id]
            n_answers = len(data.get("answers", []))
            if n_answers < data["total"]:
                print(f"SKIP {tag}: {ds_id} incomplete ({n_answers}/{data['total']})")
                all_complete = False
                break

        if all_complete:
            complete_models[(model, reasoning, effort)] = datasets

    print(f"\n{len(complete_models)} complete model config(s) out of {len(model_results)} total\n")

    models_out = []
    heatmap_columns = []
    seen_kind_columns = set()

    # Add one overall column per dataset
    for ds_id in dataset_order:
        meta = dataset_meta_by_id[ds_id]
        heatmap_columns.append({
            "id": ds_id,
            "label": meta.get("name", ds_id),
            "type": "dataset",
            "dataset_id": ds_id,
        })

    for (model, reasoning, effort), datasets in complete_models.items():
        slug = model.replace("/", "_")
        if reasoning is True:
            slug += "__reasoning-on"
            if effort:
                slug += f"-{effort}"
        elif reasoning is False:
            slug += "__reasoning-off"

        name = display_name(model)
        first_ds = datasets[dataset_order[0]]

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

        category_stats = {}

        for ds_id in dataset_order:
            d = datasets[ds_id]
            meta = dataset_meta_by_id[ds_id]
            questions = dataset_questions_by_id[ds_id]
            cost = d.get("cost_usd", 0) or 0
            kind_breakdown = build_kind_breakdown(questions, d)

            for kb in kind_breakdown:
                col_id = f"{ds_id}::kind::{kb['kind']}"
                if col_id not in seen_kind_columns:
                    heatmap_columns.append({
                        "id": col_id,
                        "label": kb["kind"],
                        "type": "kind",
                        "dataset_id": ds_id,
                    })
                    seen_kind_columns.add(col_id)

            per_dataset.append({
                "dataset_id": ds_id,
                "dataset_name": meta.get("name", d["dataset_name"]),
                "total": d["total"],
                "correct": d["correct"],
                "errors": d["errors"],
                "accuracy": d["accuracy"],
                "input_tokens": d["input_tokens"],
                "output_tokens": d["output_tokens"],
                "cost_usd": cost,
                "categories": meta.get("categories", []),
                "kind_breakdown": kind_breakdown,
            })

            total_correct += d["correct"]
            total_questions += d["total"]
            total_errors += d["errors"]
            total_input_tokens += d["input_tokens"]
            total_output_tokens += d["output_tokens"]
            total_cost += cost

            for cat in meta.get("categories", []):
                category_stats.setdefault(cat, {"correct": 0, "total": 0, "errors": 0})
                category_stats[cat]["correct"] += d["correct"]
                category_stats[cat]["total"] += d["total"]
                category_stats[cat]["errors"] += d["errors"]

        for cat, stats in category_stats.items():
            stats["accuracy"] = round(
                stats["correct"] / max(stats["total"] - stats["errors"], 1) * 100, 2
            )

        overall_accuracy = round(total_correct / max(total_questions - total_errors, 1) * 100, 2)

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

    models_out.sort(key=lambda m: m["overall_accuracy"], reverse=True)
    for i, m in enumerate(models_out):
        m["rank"] = i + 1

    summary = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset_order": dataset_order,
        "datasets": [
            dataset_meta_by_id[ds_id] for ds_id in dataset_order
        ],
        "category_map": category_map,
        "heatmap_columns": heatmap_columns,
        "models": models_out,
    }

    out_path = RESULTS_DIR / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
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