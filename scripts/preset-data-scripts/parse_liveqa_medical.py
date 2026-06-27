#!/usr/bin/env python3
"""
Parse LiveQA Medical (TREC 2017) dataset and save QA pairs to preset-data.

Dataset source: https://github.com/abachaa/LiveQA_MedicalTask_TREC2017

LiveQA Medical (TREC 2017) is a dataset of consumer health questions received
by the U.S. National Library of Medicine (NLM), with reference answers and
annotations prepared for the TREC 2017 LiveQA Medical Task.

The test set contains 104 questions. Each question has:
  - An original consumer question (subject + message)
  - A NIST paraphrase / NLM summary
  - Annotations: focus entities, question types, keywords
  - One or more reference answers with source URLs and reviewer comments

XML structure:
  <NLM-QUESTION qid="TQ1">
    <Original-Question qfile="...">
      <SUBJECT>...</SUBJECT>
      <MESSAGE>...</MESSAGE>
    </Original-Question>
    <NIST-PARAPHRASE>...</NIST-PARAPHRASE>
    <NLM-Summary>...</NLM-Summary>      (present in -w-summaries file)
    <ANNOTATIONS>
      <FOCUS fid="..." fcategory="...">...</FOCUS>
      <TYPE tid="..." hasFocus="..." hasKeyword="...">...</TYPE>
      <KEYWORD kid="..." kcategory="...">...</KEYWORD>
    </ANNOTATIONS>
    <ReferenceAnswers>
      <RefAnswer aid="...">
        <ANSWER>...</ANSWER>
        <AnswerURL>...</AnswerURL>
        <COMMENT>...</COMMENT>
      </RefAnswer>
    </ReferenceAnswers>
  </NLM-QUESTION>

Output structure per sample:
  preset-data/liveqa-medical/[qid]/question.txt   (consumer health question)
  preset-data/liveqa-medical/[qid]/answer.txt     (concatenated reference answers)
  preset-data/liveqa-medical/[qid]/metadata.txt  (qid, subject, paraphrase,
                                                   annotations, answer URLs)

Reference:
  Asma Ben Abacha, Eugene Agichtein, Yuval Pinter and Dina Demner-Fushman.
  "Overview of the Medical Question Answering Task at TREC 2017 LiveQA."
  TREC 2017.
"""

import os
import sys
import xml.etree.ElementTree as ET

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Primary file: test set with reference answers and NLM summaries
PRIMARY_URL = (
    "https://raw.githubusercontent.com/abachaa/LiveQA_MedicalTask_TREC2017"
    "/master/TestDataset/TREC-2017-LiveQA-Medical-Test-Questions-w-summaries.xml"
)

# Fallback file: test set without NLM summaries (same questions, slightly less data)
FALLBACK_URL = (
    "https://raw.githubusercontent.com/abachaa/LiveQA_MedicalTask_TREC2017"
    "/master/TestDataset/TREC-2017-LiveQA-Medical-Test.xml"
)

GITHUB_REPO = "https://github.com/abachaa/LiveQA_MedicalTask_TREC2017"

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "preset-data",
    "liveqa-medical",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_xml(url: str) -> str:
    """Download XML content from *url* and return as string."""
    print(f"Downloading dataset from {url} ...")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.text


def clean(text: str | None) -> str:
    """Strip whitespace from a string; return empty string if None."""
    if text is None:
        return ""
    return " ".join(text.split())


def save_text(path: str, content: str) -> None:
    """Write *content* to *path*, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_question(elem: ET.Element) -> dict:
    """Extract all fields from a single <NLM-QUESTION> element."""
    qid = elem.get("qid", "")

    # Original consumer question
    orig = elem.find("Original-Question")
    qfile = orig.get("qfile", "") if orig is not None else ""
    subject = clean(orig.findtext("SUBJECT")) if orig is not None else ""
    message = clean(orig.findtext("MESSAGE")) if orig is not None else ""

    # Paraphrase / summary
    paraphrase = clean(elem.findtext("NIST-PARAPHRASE"))
    nlm_summary = clean(elem.findtext("NLM-Summary"))

    # Annotations
    ann = elem.find("ANNOTATIONS")
    focuses = []
    keywords = []
    types = []
    if ann is not None:
        for focus in ann.findall("FOCUS"):
            focuses.append({
                "fid": focus.get("fid", ""),
                "fcategory": focus.get("fcategory", ""),
                "text": clean(focus.text),
            })
        for kw in ann.findall("KEYWORD"):
            keywords.append({
                "kid": kw.get("kid", ""),
                "kcategory": kw.get("kcategory", ""),
                "text": clean(kw.text),
            })
        for qt in ann.findall("TYPE"):
            types.append({
                "tid": qt.get("tid", ""),
                "hasFocus": qt.get("hasFocus", ""),
                "hasKeyword": qt.get("hasKeyword", ""),
                "text": clean(qt.text),
            })

    # Reference answers
    ref_answers_elem = elem.find("ReferenceAnswers")
    answers = []
    if ref_answers_elem is not None:
        for ref in ref_answers_elem.findall("RefAnswer"):
            answer_text = clean(ref.findtext("ANSWER"))
            answer_url = clean(ref.findtext("AnswerURL"))
            comment = clean(ref.findtext("COMMENT"))
            if answer_text:
                answers.append({
                    "aid": ref.get("aid", ""),
                    "answer": answer_text,
                    "url": answer_url,
                    "comment": comment,
                })

    return {
        "qid": qid,
        "qfile": qfile,
        "subject": subject,
        "message": message,
        "paraphrase": paraphrase,
        "nlm_summary": nlm_summary,
        "focuses": focuses,
        "keywords": keywords,
        "types": types,
        "answers": answers,
    }


def build_question_text(q: dict) -> str:
    """Build the question.txt content from a parsed question dict."""
    lines = []
    if q["subject"]:
        lines.append(f"Subject: {q['subject']}")
        lines.append("")
    if q["message"]:
        lines.append(q["message"])
    return "\n".join(lines)


def build_answer_text(q: dict) -> str:
    """Build the answer.txt content: concatenate all reference answers."""
    if not q["answers"]:
        return ""
    parts = []
    for i, ans in enumerate(q["answers"], start=1):
        parts.append(f"[Answer {i}]")
        parts.append(ans["answer"])
        if ans["url"]:
            parts.append(f"Source: {ans['url']}")
        parts.append("")
    return "\n".join(parts).strip()


def build_metadata_text(q: dict) -> str:
    """Build the metadata.txt content."""
    lines = []
    lines.append(f"qid: {q['qid']}")
    lines.append(f"source_file: {q['qfile']}")
    lines.append(f"dataset: LiveQA Medical (TREC 2017)")
    lines.append(f"dataset_url: {GITHUB_REPO}")
    lines.append("")

    if q["paraphrase"]:
        lines.append(f"paraphrase: {q['paraphrase']}")
    if q["nlm_summary"]:
        lines.append(f"nlm_summary: {q['nlm_summary']}")
    lines.append("")

    if q["focuses"]:
        lines.append("focus_entities:")
        for f in q["focuses"]:
            lines.append(f"  [{f['fid']}] ({f['fcategory']}) {f['text']}")

    if q["types"]:
        lines.append("question_types:")
        for t in q["types"]:
            lines.append(f"  [{t['tid']}] {t['text']}")

    if q["keywords"]:
        lines.append("keywords:")
        for k in q["keywords"]:
            lines.append(f"  [{k['kid']}] ({k['kcategory']}) {k['text']}")

    lines.append("")
    if q["answers"]:
        lines.append(f"num_reference_answers: {len(q['answers'])}")
        lines.append("answer_urls:")
        for ans in q["answers"]:
            if ans["url"]:
                lines.append(f"  [{ans['aid']}] {ans['url']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    # Download XML
    try:
        xml_text = fetch_xml(PRIMARY_URL)
        source_label = "w-summaries"
    except Exception as e:
        print(f"Primary URL failed ({e}), trying fallback ...", file=sys.stderr)
        xml_text = fetch_xml(FALLBACK_URL)
        source_label = "no-summaries"

    # Parse XML
    root = ET.fromstring(xml_text)
    questions_elems = root.findall("NLM-QUESTION")
    print(f"Found {len(questions_elems)} questions in XML ({source_label})")

    saved = 0
    skipped = 0

    for elem in questions_elems:
        q = parse_question(elem)
        qid = q["qid"]

        if not qid:
            print(f"  WARNING: question with empty qid — skipping", file=sys.stderr)
            skipped += 1
            continue

        question_text = build_question_text(q)
        answer_text = build_answer_text(q)
        metadata_text = build_metadata_text(q)

        if not question_text.strip():
            print(f"  WARNING: {qid} has empty question — skipping", file=sys.stderr)
            skipped += 1
            continue

        sample_dir = os.path.join(OUTPUT_DIR, qid)
        save_text(os.path.join(sample_dir, "question.txt"), question_text)
        save_text(os.path.join(sample_dir, "answer.txt"), answer_text)
        save_text(os.path.join(sample_dir, "metadata.txt"), metadata_text)

        saved += 1
        if saved <= 5 or saved % 20 == 0:
            print(f"  Saved {qid}: {q['subject'][:60]}")

    print(f"\nDone. Saved {saved} samples to {OUTPUT_DIR}")
    if skipped:
        print(f"Skipped {skipped} samples (missing qid or question text)")


if __name__ == "__main__":
    main()
