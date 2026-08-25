#!/usr/bin/env python3
"""Validate and normalize generated query rewrites."""

from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

from common import ARTIFACT_ROOT, normalized_text


WORD_RANGES = {
    "short": (5, 12),
    "medium": (18, 35),
    "long": (45, 80),
}
BANNED = (
    "reasatlas",
    "sample id",
    "topic path",
    "database record",
    "source book",
)


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text.strip()))


def ordinary_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[index : index + n]) for index in range(max(0, len(tokens) - n + 1))}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=ARTIFACT_ROOT / "rewrite_inputs.jsonl")
    parser.add_argument("--out", type=Path, default=ARTIFACT_ROOT / "query_variants.jsonl")
    parser.add_argument("--report", type=Path, default=ARTIFACT_ROOT / "rewrite_validation.json")
    args = parser.parse_args()

    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    generated = raw.get("rewrites") if isinstance(raw, dict) else None
    if not isinstance(generated, list):
        raise SystemExit("raw rewrite output must be an object containing a rewrites array")
    inputs = load_jsonl(args.inputs)
    expected_ids = [item["sample_id"] for item in inputs]
    actual_ids = [item.get("sample_id") for item in generated]
    errors = []
    warnings = []
    if actual_ids != expected_ids:
        missing = sorted(set(expected_ids) - set(actual_ids))
        extra = sorted(set(actual_ids) - set(expected_ids))
        errors.append({"code": "id_order_or_coverage", "missing": missing, "extra": extra})

    input_by_id = {item["sample_id"]: item for item in inputs}
    rows = []
    pair_keys = set()
    for item in generated:
        sample_id = item.get("sample_id")
        source = input_by_id.get(sample_id)
        if source is None:
            continue
        source_ngrams = ngrams(
            ordinary_tokens(source["statement_title"] + " " + source["statement_plain"]), 4
        )
        for variant in ("short", "medium", "long"):
            query = str(item.get(f"{variant}_query") or "").strip()
            key = (sample_id, variant)
            if key in pair_keys:
                errors.append({"code": "duplicate_pair", "sample_id": sample_id, "variant": variant})
            pair_keys.add(key)
            count = word_count(query)
            low, high = WORD_RANGES[variant]
            if not (low <= count <= high):
                errors.append(
                    {
                        "code": "word_count",
                        "sample_id": sample_id,
                        "variant": variant,
                        "observed": count,
                        "expected": [low, high],
                    }
                )
            lowered = query.lower()
            banned_hits = [term for term in BANNED if term in lowered]
            if re.search(r"\bQ\d{4}\b", query, flags=re.IGNORECASE):
                banned_hits.append("sample_id_literal")
            if banned_hits:
                errors.append(
                    {
                        "code": "metadata_leakage",
                        "sample_id": sample_id,
                        "variant": variant,
                        "hits": banned_hits,
                    }
                )
            overlap = source_ngrams & ngrams(ordinary_tokens(query), 4)
            if overlap:
                warnings.append(
                    {
                        "code": "fourgram_overlap",
                        "sample_id": sample_id,
                        "variant": variant,
                        "examples": [" ".join(words) for words in sorted(overlap)[:3]],
                    }
                )
            rows.append(
                {
                    "sample_id": sample_id,
                    "variant": variant,
                    "query": query,
                    "word_count": count,
                    "query_normalized": normalized_text(query),
                }
            )

    duplicates = [
        text for text, count in collections.Counter(row["query_normalized"] for row in rows).items() if count > 1
    ]
    if duplicates:
        errors.append({"code": "duplicate_queries", "count": len(duplicates), "examples": duplicates[:5]})
    expected_pairs = len(inputs) * 3
    if len(rows) != expected_pairs:
        errors.append({"code": "query_count", "observed": len(rows), "expected": expected_pairs})

    report = {
        "input_count": len(inputs),
        "generated_item_count": len(generated),
        "query_count": len(rows),
        "errors": errors,
        "warnings": warnings,
        "status": "PASS" if not errors else "FAIL",
        "semantic_validation": "not_established_by_automatic_checks",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if errors:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "query_count": len(rows), "warning_count": len(warnings)}, indent=2))


if __name__ == "__main__":
    main()
