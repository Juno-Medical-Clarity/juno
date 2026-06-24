#!/usr/bin/env python3
# Dataset source: https://github.com/chaojiang06/medreadme
# Paper: "MedReadMe: A Systematic Study for Fine-grained Sentence Readability in Medical Domain"
# EMNLP 2024 — Chao Jiang et al.
#
# Dataset contains:
#   readability.csv — sentence-level readability scores (columns: Sentence, Source, Side, Readability, Split)
#   jargon.json    — token-level span annotations for jargon/complexity categories
#
# Output layout:
#   preset-data/medreadme/<sample-id>/text.txt        — the medical sentence
#   preset-data/medreadme/<sample-id>/annotations.txt — readability score + jargon span annotations

import csv
import json
import os
import io
import urllib.request

READABILITY_URL = "https://raw.githubusercontent.com/chaojiang06/medreadme/main/dataset/readability.csv"
JARGON_URL = "https://raw.githubusercontent.com/chaojiang06/medreadme/main/dataset/jargon.json"

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "preset-data", "medreadme")
OUTPUT_DIR = os.path.normpath(OUTPUT_DIR)


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def load_readability(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({
            "sentence": row["Sentence"].strip(),
            "source": row["Source"].strip(),
            "side": row["Side"].strip(),
            "readability": row["Readability"].strip(),
            "split": row["split"].strip(),
        })
    return rows


def load_jargon(text: str) -> list[dict]:
    data = json.loads(text)
    # Top-level may be a list or a dict with entries
    if isinstance(data, list):
        return data
    # Fallback: try common wrapper keys
    for key in ("data", "entries", "sentences"):
        if key in data:
            return data[key]
    return list(data.values())


import re as _re

def sentence_key(sentence: str) -> str:
    """Normalise a sentence for matching across both datasets.

    jargon.json tokens use PTB-style tokenization:
      - spaces before punctuation: "malaria , which"
      - spaces around hyphens: "malaria - endemic"
      - spaces inside parentheses: "( or error"
    We normalise both the CSV sentence and the reconstructed jargon sentence
    to the same form so they can be compared.
    """
    s = sentence.strip().lower()
    # Remove spaces immediately before closing punctuation
    s = _re.sub(r'\s+([,\.;:\?\!\)\]])', r'\1', s)
    # Remove spaces after opening brackets
    s = _re.sub(r'([\(\[])\s+', r'\1', s)
    # Collapse spaces around hyphens (tokenizer splits hyphenated words)
    s = _re.sub(r'\s*-\s*', r'-', s)
    # Collapse remaining whitespace
    return " ".join(s.split())


def format_annotations(row: dict, jargon_entry: dict | None) -> str:
    lines = []
    lines.append(f"source:      {row['source']}")
    lines.append(f"side:        {row['side']}")
    lines.append(f"readability: {row['readability']}")
    lines.append(f"split:       {row['split']}")

    if jargon_entry:
        entities = jargon_entry.get("entities", [])
        if entities:
            lines.append("")
            lines.append("jargon_spans:")
            for ent in entities:
                start, end, category, span_tokens = ent
                span_text = " ".join(span_tokens)
                lines.append(f"  [{start}:{end}] {category!r} -> {span_text!r}")
        else:
            lines.append("")
            lines.append("jargon_spans: (none)")
    else:
        lines.append("")
        lines.append("jargon_spans: (no jargon annotation found for this sentence)")

    return "\n".join(lines) + "\n"


def slugify(index: int) -> str:
    return f"{index:05d}"


def write_sample(sample_id: str, sentence: str, annotation_text: str) -> None:
    sample_dir = os.path.join(OUTPUT_DIR, sample_id)
    os.makedirs(sample_dir, exist_ok=True)

    with open(os.path.join(sample_dir, "text.txt"), "w", encoding="utf-8") as f:
        f.write(sentence + "\n")

    with open(os.path.join(sample_dir, "annotations.txt"), "w", encoding="utf-8") as f:
        f.write(annotation_text)


def main():
    print("Fetching readability.csv …")
    readability_text = fetch_text(READABILITY_URL)
    rows = load_readability(readability_text)
    print(f"  Loaded {len(rows)} sentences from readability.csv")

    print("Fetching jargon.json …")
    jargon_text = fetch_text(JARGON_URL)
    jargon_entries = load_jargon(jargon_text)
    print(f"  Loaded {len(jargon_entries)} entries from jargon.json")

    # Build a text-key index from jargon.json.
    # jargon.json uses PTB-style tokenization (spaces before punctuation,
    # spaces around hyphens) so we normalise both sides with sentence_key().
    text_key_index: dict[str, dict] = {}
    for entry in jargon_entries:
        tokens = entry.get("tokens", [])
        if tokens:
            k = sentence_key(" ".join(tokens))
            text_key_index.setdefault(k, entry)
    print(f"  Built text-key index with {len(text_key_index)} unique sentence keys")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    written = 0
    jargon_matched = 0
    for i, row in enumerate(rows):
        sample_id = slugify(i)
        sentence = row["sentence"]
        jargon_entry = text_key_index.get(sentence_key(sentence))
        if jargon_entry:
            jargon_matched += 1
        annotation_text = format_annotations(row, jargon_entry)
        write_sample(sample_id, sentence, annotation_text)
        written += 1

        if written % 500 == 0:
            print(f"  … wrote {written} samples so far")

    print(f"\nDone. Wrote {written} samples to {OUTPUT_DIR}")
    print(f"Jargon annotations matched for {jargon_matched}/{written} samples.")


if __name__ == "__main__":
    main()
