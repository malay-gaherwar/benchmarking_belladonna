#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path

INPUT_FILE = Path("205.json")
OUTPUT_FILE = Path("205expertquestions.json")

META = {
    "id": "expert205",
    "name": "Expert205",
    "abbrev": "EXP205",
    "source": "Expert-curated benchmark",
    "sourceNote": "",
    "license": "CC BY 4.0",
    "description": "Expert breast imaging and screening benchmark",
    "taskType": "Medical MCQ reasoning",
    "categories": ["Human Expert"],
}

OPTION_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def clean_text(text: str) -> str:
    text = str(text)
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = text.replace("\\<", "<").replace("\\>", ">")
    text = text.replace("\\*", "*")
    text = text.replace("\\_", "_")
    text = text.replace("\\~", "~")
    text = text.replace("\\.", ".")
    text = text.replace("**", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def answer_letter_to_index(letter: str) -> int:
    letter = letter.strip().upper()
    idx = ord(letter) - ord("A")
    if idx < 0:
        raise ValueError(f"Invalid answer letter: {letter}")
    return idx


def normalize_options(options_raw) -> list[str]:
    if isinstance(options_raw, dict):
        ordered = []
        for label in OPTION_LABELS:
            if label in options_raw:
                ordered.append(clean_text(options_raw[label]))
        if not ordered:
            raise ValueError("Options dict was empty or had no A/B/C... keys")
        return ordered

    if isinstance(options_raw, list):
        return [clean_text(x) for x in options_raw]

    raise ValueError("Unsupported options format; expected dict or list")


def convert_question(item: dict, new_id: int | None = None) -> dict:
    if "question" not in item:
        raise ValueError(f"Missing 'question' in item: {item}")

    if "options" not in item:
        raise ValueError(f"Missing 'options' in item: {item}")

    if "answer" not in item:
        raise ValueError(f"Missing 'answer' in item: {item}")

    options = normalize_options(item["options"])
    target = answer_letter_to_index(str(item["answer"]))

    if target >= len(options):
        raise ValueError(
            f"Answer '{item['answer']}' is out of range for {len(options)} options in question {item.get('id')}"
        )

    qid = new_id if new_id is not None else item.get("id")
    if qid is None:
        raise ValueError(f"Missing question id in item: {item}")

    kind = item.get("category") or item.get("kind") or "Uncategorized"

    return {
        "id": int(qid),
        "question": clean_text(item["question"]),
        "options": options,
        "target": target,
        "kind": clean_text(kind),
    }


def main() -> None:
    raw = json.loads(INPUT_FILE.read_text(encoding="utf-8"))

    if not isinstance(raw, list):
        raise ValueError("Input JSON must be a top-level list of questions")

    questions = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Question at position {i} is not an object")
        questions.append(convert_question(item, new_id=i))

    output = {
        "meta": META,
        "questions": questions,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Wrote {len(questions)} questions to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()