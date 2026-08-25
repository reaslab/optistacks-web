#!/usr/bin/env python3
"""Build a deterministic 200-record, domain-balanced ReasAtlas sample."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from common import (
    ARTIFACT_ROOT,
    KIND_ORDER,
    TARGET_KINDS,
    iter_statements,
    manifest_domains,
    normalized_text,
    stable_key,
)


DEFAULT_SAMPLE_PER_DOMAIN = 10
DOMAIN_SAMPLE_OVERRIDES = {
    # Only eight records survive all provenance, placement, uniqueness, depth,
    # and length gates in this small domain. Keep the gate fixed and reassign
    # the two-record shortfall to an algorithm-rich small domain.
    "constraint_logic_optimization": 8,
    "distributed_optimization": 12,
}
GLOBAL_KIND_TARGETS = {"theorem": 80, "definition": 60, "algorithm": 60}
DEV_KIND_TARGETS = {"theorem": 16, "definition": 12, "algorithm": 12}
DEV_PER_DOMAIN = 2


def eligible(record: dict, id_counts: collections.Counter, title_counts: collections.Counter) -> bool:
    plain_words = len(record["statement_plain"].split())
    return all(
        (
            record["content_kind"] in TARGET_KINDS,
            bool(record["statement_id"]),
            bool(record["title"]),
            bool(record["statement_plain"]),
            8 <= plain_words <= 80,
            record["confidence"] >= 0.9,
            record["source_ref_count"] > 0,
            record["original_topic_id"] == record["topic_id"],
            record["topic_id"] in record["mapped_topic_ids"],
            record["topic_depth"] >= 3,
            id_counts[record["statement_id"]] == 1,
            title_counts[normalized_text(record["title"])] == 1,
        )
    )


def domain_allocations(capacities: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """Solve the exact global quotas with minimum deviation from 4/3/3 per domain."""
    domains = [item["id"] for item in manifest_domains()]
    ideal = {"theorem": 4, "definition": 3, "algorithm": 3}
    states: dict[tuple[int, int], tuple[int, list[dict[str, int]]]] = {(0, 0): (0, [])}
    for domain_index, domain in enumerate(domains):
        sample_target = DOMAIN_SAMPLE_OVERRIDES.get(domain, DEFAULT_SAMPLE_PER_DOMAIN)
        next_states: dict[tuple[int, int], tuple[int, list[dict[str, int]]]] = {}
        capacity = capacities[domain]
        choices = []
        for theorem_n in range(min(sample_target, capacity["theorem"]) + 1):
            for definition_n in range(min(sample_target - theorem_n, capacity["definition"]) + 1):
                algorithm_n = sample_target - theorem_n - definition_n
                if algorithm_n > capacity["algorithm"]:
                    continue
                allocation = {
                    "theorem": theorem_n,
                    "definition": definition_n,
                    "algorithm": algorithm_n,
                }
                cost = sum((allocation[kind] - ideal[kind]) ** 2 for kind in TARGET_KINDS)
                choices.append((cost, allocation))
        if not choices:
            raise RuntimeError(f"Domain {domain} cannot supply {sample_target} eligible records")
        for (theorem_total, definition_total), (old_cost, path) in states.items():
            used = sum(
                DOMAIN_SAMPLE_OVERRIDES.get(previous, DEFAULT_SAMPLE_PER_DOMAIN)
                for previous in domains[:domain_index]
            )
            algorithm_total = used - theorem_total - definition_total
            for choice_cost, allocation in choices:
                new_theorem = theorem_total + allocation["theorem"]
                new_definition = definition_total + allocation["definition"]
                new_algorithm = algorithm_total + allocation["algorithm"]
                if (
                    new_theorem > GLOBAL_KIND_TARGETS["theorem"]
                    or new_definition > GLOBAL_KIND_TARGETS["definition"]
                    or new_algorithm > GLOBAL_KIND_TARGETS["algorithm"]
                ):
                    continue
                key = (new_theorem, new_definition)
                candidate = (old_cost + choice_cost, path + [allocation])
                incumbent = next_states.get(key)
                candidate_tie = tuple(tuple(item[k] for k in TARGET_KINDS) for item in candidate[1])
                incumbent_tie = (
                    tuple(tuple(item[k] for k in TARGET_KINDS) for item in incumbent[1])
                    if incumbent
                    else ()
                )
                if incumbent is None or (candidate[0], candidate_tie) < (incumbent[0], incumbent_tie):
                    next_states[key] = candidate
        states = next_states
    target_key = (GLOBAL_KIND_TARGETS["theorem"], GLOBAL_KIND_TARGETS["definition"])
    if target_key not in states:
        raise RuntimeError("No exact 80/60/60 allocation satisfies all domain capacities")
    path = states[target_key][1]
    if len(domains) != len(path):
        raise RuntimeError("Internal allocation length mismatch")
    return dict(zip(domains, path))


def dev_allocations(sample_allocations: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    domains = [item["id"] for item in manifest_domains()]
    states: dict[tuple[int, int], tuple[int, list[dict[str, int]]]] = {(0, 0): (0, [])}
    for domain_index, domain in enumerate(domains):
        next_states = {}
        capacity = sample_allocations[domain]
        choices = []
        for theorem_n in range(min(DEV_PER_DOMAIN, capacity["theorem"]) + 1):
            for definition_n in range(min(DEV_PER_DOMAIN - theorem_n, capacity["definition"]) + 1):
                algorithm_n = DEV_PER_DOMAIN - theorem_n - definition_n
                if algorithm_n > capacity["algorithm"]:
                    continue
                allocation = {
                    "theorem": theorem_n,
                    "definition": definition_n,
                    "algorithm": algorithm_n,
                }
                proportional_cost = sum(
                    (5 * allocation[kind] - sample_allocations[domain][kind]) ** 2
                    for kind in TARGET_KINDS
                )
                choices.append((proportional_cost, allocation))
        for (theorem_total, definition_total), (old_cost, path) in states.items():
            used = domain_index * DEV_PER_DOMAIN
            algorithm_total = used - theorem_total - definition_total
            for choice_cost, allocation in choices:
                new_theorem = theorem_total + allocation["theorem"]
                new_definition = definition_total + allocation["definition"]
                new_algorithm = algorithm_total + allocation["algorithm"]
                if (
                    new_theorem > DEV_KIND_TARGETS["theorem"]
                    or new_definition > DEV_KIND_TARGETS["definition"]
                    or new_algorithm > DEV_KIND_TARGETS["algorithm"]
                ):
                    continue
                key = (new_theorem, new_definition)
                candidate = (old_cost + choice_cost, path + [allocation])
                incumbent = next_states.get(key)
                if incumbent is None or candidate[0] < incumbent[0]:
                    next_states[key] = candidate
        states = next_states
    target_key = (DEV_KIND_TARGETS["theorem"], DEV_KIND_TARGETS["definition"])
    if target_key not in states:
        raise RuntimeError("No exact 16/12/12 development split satisfies domain allocations")
    path = states[target_key][1]
    if len(domains) != len(path):
        raise RuntimeError("Internal development allocation length mismatch")
    return dict(zip(domains, path))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260825)
    parser.add_argument("--out", type=Path, default=ARTIFACT_ROOT)
    args = parser.parse_args()

    records = list(iter_statements())
    id_counts = collections.Counter(row["statement_id"] for row in records if row["statement_id"])
    title_counts = collections.Counter(normalized_text(row["title"]) for row in records if row["title"])
    candidates = [row for row in records if eligible(row, id_counts, title_counts)]

    by_domain_kind: dict[str, dict[str, list[dict]]] = {
        domain["id"]: {kind: [] for kind in TARGET_KINDS} for domain in manifest_domains()
    }
    for record in candidates:
        by_domain_kind[record["domain"]][record["content_kind"]].append(record)
    for domain in by_domain_kind.values():
        for rows in domain.values():
            rows.sort(key=lambda row: stable_key(args.seed, row["record_uid"]))

    capacities = {
        domain: {kind: len(rows[kind]) for kind in TARGET_KINDS}
        for domain, rows in by_domain_kind.items()
    }
    allocations = domain_allocations(capacities)
    development_allocations = dev_allocations(allocations)

    selected = []
    for domain_info in manifest_domains():
        domain = domain_info["id"]
        for kind in TARGET_KINDS:
            need = allocations[domain][kind]
            rows = by_domain_kind[domain][kind]
            # Prefer topic diversity before taking a second record from the same leaf.
            chosen = []
            deferred = []
            seen_topics = set()
            for row in rows:
                if row["topic_id"] in seen_topics:
                    deferred.append(row)
                else:
                    chosen.append(row)
                    seen_topics.add(row["topic_id"])
                if len(chosen) == need:
                    break
            if len(chosen) < need:
                chosen.extend(deferred[: need - len(chosen)])
            if len(chosen) != need:
                raise RuntimeError(f"Sampling underflow for {domain}/{kind}: {len(chosen)} < {need}")
            dev_need = development_allocations[domain][kind]
            for index, row in enumerate(chosen):
                row = dict(row)
                row["split"] = "dev" if index < dev_need else "test"
                selected.append(row)

    selected.sort(
        key=lambda row: (
            [item["id"] for item in manifest_domains()].index(row["domain"]),
            KIND_ORDER[row["content_kind"]],
            row["split"] != "dev",
            stable_key(args.seed, row["record_uid"]),
        )
    )
    for index, row in enumerate(selected, start=1):
        row["sample_id"] = f"Q{index:04d}"

    rewrite_inputs = []
    for row in selected:
        rewrite_inputs.append(
            {
                "sample_id": row["sample_id"],
                "content_kind": row["content_kind"],
                "statement_title": row["title"],
                "statement_plain": row["statement_plain"],
                "statement_latex": row["statement_latex"],
                "scope_note": row["scope_note"],
                "assumptions_latex": row["assumptions_latex"],
                "conclusion_latex": row["conclusion_latex"],
            }
        )

    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "sample_200.jsonl", selected)
    write_jsonl(args.out / "rewrite_inputs.jsonl", rewrite_inputs)

    kind_counts = collections.Counter(row["content_kind"] for row in selected)
    split_counts = collections.Counter(row["split"] for row in selected)
    split_kind_counts = collections.Counter((row["split"], row["content_kind"]) for row in selected)
    report = {
        "seed": args.seed,
        "source_manifest_totals": json.loads((Path(__file__).resolve().parents[3] / "site/data/manifest.json").read_text())["totals"],
        "excluded_domains": ["positive_isotropic_curvature"],
        "corpus_statement_count_optimization_only": len(records),
        "eligible_count": len(candidates),
        "eligibility": {
            "content_kinds": list(TARGET_KINDS),
            "confidence_min": 0.9,
            "requires_source_reference": True,
            "requires_exact_current_topic_mapping": True,
            "topic_depth_min": 3,
            "plain_word_range": [8, 80],
            "requires_unique_statement_id": True,
            "requires_unique_normalized_title": True,
        },
        "sample_size": len(selected),
        "default_sample_per_domain": DEFAULT_SAMPLE_PER_DOMAIN,
        "domain_sample_overrides": DOMAIN_SAMPLE_OVERRIDES,
        "kind_counts": dict(kind_counts),
        "split_counts": dict(split_counts),
        "split_kind_counts": {f"{split}/{kind}": count for (split, kind), count in split_kind_counts.items()},
        "capacities": capacities,
        "sample_allocations": allocations,
        "dev_allocations": development_allocations,
    }
    (args.out / "sampling_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: report[key] for key in ("sample_size", "eligible_count", "kind_counts", "split_counts", "split_kind_counts")}, indent=2))


if __name__ == "__main__":
    main()
