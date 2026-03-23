#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path

INPUT_FILE = Path("200.md")
OUTPUT_FILE = Path("200expertquestions.json")

SECTION_RE = re.compile(r"^###\s+\*\*(.*?)\*\*\s*$")
BULLET_RE = re.compile(r"^\*\s+(.*)$")

# Top-level question must start at left margin
TOP_Q_RE = re.compile(r"^(\d+)\.\s+(.*)$")

# Option must be indented
OPT_RE = re.compile(r"^\s+(\d+)\.\s+(.*)$")

ANSWER_RE = re.compile(r"^\s*Answer\s*:\s*([A-Za-z])\s*$", re.IGNORECASE)


def clean_text(text: str) -> str:
    text = text.replace("\u200b", "")
    text = text.replace("\ufeff", "")
    text = text.replace("\\<", "<").replace("\\>", ">")
    text = text.replace("\\*", "*")
    text = text.replace("\\_", "_")
    text = text.replace("\\~", "~")
    text = text.replace("**", "")
    text = re.sub(r"(?<!\*)\*(?!\*)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def split_sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    current_title = "Unknown"
    current_body: list[str] = []

    for line in lines:
        m = SECTION_RE.match(line.strip())
        if m:
            if current_body:
                sections.append((current_title, current_body))
            current_title = clean_text(m.group(1))
            current_body = []
        else:
            current_body.append(line)

    if current_body:
        sections.append((current_title, current_body))

    return sections


def extract_topics_and_body(lines: list[str]) -> tuple[list[str], list[str]]:
    topics: list[str] = []
    i = 0

    while i < len(lines) and not lines[i].strip():
        i += 1

    while i < len(lines):
        m = BULLET_RE.match(lines[i].strip())
        if m:
            topics.append(clean_text(m.group(1)))
            i += 1
            continue
        if not lines[i].strip():
            i += 1
            continue
        break

    return topics, lines[i:]


def answer_letter_to_index(letter: str) -> int:
    return ord(letter.upper()) - ord("A")


def parse_question_block(block_lines: list[str], qid: int, kind: str, topics: list[str]) -> dict:
    if not block_lines:
        raise ValueError(f"Empty block for question {qid}")

    m = TOP_Q_RE.match(block_lines[0].rstrip())
    if not m or int(m.group(1)) != qid:
        raise ValueError(f"Question {qid} does not start correctly")

    stem_lines = [m.group(2).rstrip()]
    options: list[str] = []
    answer_letter: str | None = None

    current_option_lines: list[str] | None = None
    in_options = False

    def flush_option() -> None:
        nonlocal current_option_lines
        if current_option_lines is not None:
            options.append(clean_text("\n".join(current_option_lines)))
            current_option_lines = None

    for raw_line in block_lines[1:]:
        line = raw_line.rstrip()

        ans = ANSWER_RE.match(line)
        if ans:
            flush_option()
            answer_letter = ans.group(1).upper()
            continue

        m_opt = OPT_RE.match(line)
        if m_opt:
            in_options = True
            flush_option()
            current_option_lines = [m_opt.group(2).rstrip()]
            continue

        if in_options and current_option_lines is not None:
            current_option_lines.append(line)
        else:
            stem_lines.append(line)

    flush_option()

    if answer_letter is None:
        raise ValueError(f"No answer line found for question {qid}")
    if len(options) < 2:
        raise ValueError(f"Too few parsed options for question {qid}")

    target = answer_letter_to_index(answer_letter)
    if target < 0 or target >= len(options):
        raise ValueError(
            f"Question {qid} answer '{answer_letter}' is out of range for {len(options)} options"
        )

    item = {
        "id": qid,
        "question": clean_text("\n".join(stem_lines)),
        "options": options,
        "target": target,
        "kind": kind,
    }
    if topics:
        item["topics"] = topics
    return item


def parse_section(kind: str, topics: list[str], lines: list[str], start_qid: int) -> tuple[list[dict], int]:
    results: list[dict] = []
    qid = start_qid
    i = 0
    n = len(lines)

    while i < n:
        while i < n and not lines[i].strip():
            i += 1
        if i >= n:
            break

        # IMPORTANT: use raw line, not stripped line, so indented options are not mistaken for questions
        m = TOP_Q_RE.match(lines[i].rstrip())
        if not (m and int(m.group(1)) == qid):
            i += 1
            continue

        block = [lines[i]]
        i += 1

        while i < n:
            # IMPORTANT: same here
            next_top = TOP_Q_RE.match(lines[i].rstrip())
            if next_top and int(next_top.group(1)) == qid + 1:
                break
            block.append(lines[i])
            i += 1

        try:
            results.append(parse_question_block(block, qid, kind, topics))
        except Exception:
            print(f"\nERROR while parsing question {qid} in section '{kind}'")
            print("----- QUESTION BLOCK START -----")
            print("\n".join(block))
            print("----- QUESTION BLOCK END -----\n")
            raise

        qid += 1

    return results, qid


def main() -> None:
    lines = INPUT_FILE.read_text(encoding="utf-8").splitlines()
    sections = split_sections(lines)

    data: list[dict] = []
    next_qid = 1

    for kind, section_lines in sections:
        topics, body_lines = extract_topics_and_body(section_lines)
        parsed, next_qid = parse_section(kind, topics, body_lines, next_qid)
        data.extend(parsed)

    OUTPUT_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(data)} questions to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()