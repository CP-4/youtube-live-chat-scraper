#!/usr/bin/env python3
"""Compare deterministic labels with an existing AI-labeled CSV.

This is an offline audit helper. It does not call Gemini. Use the app's
explicit AI checkbox for a bounded provider pass, then run this report against
the resulting export and a separate raw extraction to inspect rule coverage.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

try:
    from .conversation_analyzer import normalize_record, normalize_records
except ImportError:
    from conversation_analyzer import normalize_record, normalize_records


LABEL_FIELDS = {
    "category", "subcategory", "is_question", "answered", "starred", "notes", "importance",
    "is_superchat", "synthetic", "category_source", "ai_excluded", "record_id",
    "classification_confidence", "classification_reason", "message_length", "word_count",
    "question_mark_count", "emoji_count", "mention_count", "has_url",
}


def deterministic_copy(row: dict[str, str]) -> dict:
    raw = dict(row)
    for field in LABEL_FIELDS:
        raw.pop(field, None)
    return normalize_record(raw)


def report_labeled(path: Path) -> None:
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    comparisons = []
    for row in rows:
        if row.get("category_source") != "ai":
            continue
        comparisons.append((deterministic_copy(row), row))
    agreement = sum(det["category"] == labeled.get("category") for det, labeled in comparisons)
    print(f"labeled_file={path}")
    print(f"rows={len(rows)} ai_rows={len(comparisons)} category_agreement={agreement}/{len(comparisons)}")
    print("pairs=")
    for (deterministic, ai), count in Counter((det["category"], labeled.get("category", "")) for det, labeled in comparisons).most_common():
        print(f"  {count:4d} {deterministic} -> {ai}")


def report_extracted(paths: list[Path]) -> None:
    for path in paths:
        raw = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
        rows, warnings = normalize_records(raw)
        lengths = [row["message_length"] for row in rows]
        print(f"extracted_file={path} rows={len(rows)} categories={dict(Counter(row['category'] for row in rows))}")
        if lengths:
            print(f"  length_min={min(lengths)} length_max={max(lengths)} length_mean={sum(lengths)/len(lengths):.1f}")
        if warnings:
            print(f"  warnings={len(warnings)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labeled-csv", type=Path)
    parser.add_argument("--extracted-csv", type=Path, action="append", default=[])
    args = parser.parse_args()
    if not args.labeled_csv and not args.extracted_csv:
        parser.error("provide --labeled-csv and/or --extracted-csv")
    if args.labeled_csv:
        report_labeled(args.labeled_csv)
    if args.extracted_csv:
        report_extracted(args.extracted_csv)


if __name__ == "__main__":
    main()
