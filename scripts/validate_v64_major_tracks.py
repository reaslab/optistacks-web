#!/usr/bin/env python3
"""Validate the v64 major-track website synchronization."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SNAPSHOT = "20260819_v64_major_tracks_v1"
EXPECTED_TREE = "opt_stacks_v64_extracted_major_tracks_candidate"
EXPECTED_TOTALS = {"topics": 75699, "statements": 94171}
FORBIDDEN_TEXT = "formal statements are stored in a later sidecar layer"
TARGETS = {
    "derivative_free_optimization": ("A25", "A07.C01", "specialized_continuous_methods"),
    "manifold_optimization": ("A26", "A07.C02", "specialized_continuous_methods"),
    "distributed_optimization": ("A27", "A07.C03", "specialized_continuous_methods"),
        "robust_optimization": ("A28", "A16.C05", "optimization_under_uncertainty"),
        "simulation_optimization": ("A29", "A16.C06", "optimization_under_uncertainty"),
}
EXPECTED_FRONT_DOMAINS = [
    "manifold_optimization",
    "derivative_free_optimization",
    "distributed_optimization",
]


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def domain_nodes(site: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = read(site / meta["data_url"])
    nodes: list[dict[str, Any]] = []
    for root in catalog.get("roots") or []:
        if root.get("shard_url"):
            nodes.extend(walk(read(site / root["shard_url"])["root"]))
            continue
        nodes.append(root)
        for chapter in root.get("children") or []:
            if chapter.get("shard_url"):
                nodes.extend(walk(read(site / chapter["shard_url"])["root"]))
            else:
                nodes.extend(walk(chapter))
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    site = args.site.resolve()
    manifest = read(site / "data/manifest.json")
    failures: list[str] = []

    def require(value: bool, code: str) -> None:
        if not value:
            failures.append(code)

    require(manifest.get("snapshot_version") == EXPECTED_SNAPSHOT, "snapshot_version")
    release_directories = sorted(path.name for path in (ROOT / "releases").iterdir() if path.is_dir())
    require(release_directories == [EXPECTED_SNAPSHOT], "release_retention")
    require((manifest.get("directory_snapshot") or {}).get("tree_id") == EXPECTED_TREE, "tree_id")
    require(len(manifest.get("domains") or []) == 20, "domain_count")
    require(manifest.get("totals") == EXPECTED_TOTALS, "totals")
    require(not (manifest.get("navigation_shortcuts") or []), "legacy_shortcuts_present")
    domain_ids = [row.get("id") for row in (manifest.get("domains") or [])]
    first_order_index = domain_ids.index("first_order_methods")
    require(domain_ids[first_order_index + 1 : first_order_index + 4] == EXPECTED_FRONT_DOMAINS, "front_domain_order")
    continuous = next(
        (row for row in manifest.get("subject_domains") or [] if row.get("id") == "continuous_optimization"),
        {},
    )
    continuous_items = continuous.get("items") or []
    first_order_subject_index = continuous_items.index("first_order_methods")
    require(continuous_items[first_order_subject_index + 1 : first_order_subject_index + 4] == EXPECTED_FRONT_DOMAINS, "front_navigation_order")

    all_ids: list[str] = []
    all_statement_ids: list[str] = []
    domain_counts: dict[str, dict[str, int]] = {}
    domain_lookup = {row["id"]: row for row in manifest.get("domains") or []}
    for domain_id, meta in domain_lookup.items():
        nodes = domain_nodes(site, meta)
        statements = [s for node in nodes for s in node.get("knowledge_statements") or []]
        all_ids.extend(str(node.get("topic_id") or "") for node in nodes)
        all_statement_ids.extend(str(s.get("id") or s.get("statement_id") or "") for s in statements)
        domain_counts[domain_id] = {"topics": len(nodes), "statements": len(statements)}
        require(meta.get("stats", {}).get("topics") == len(nodes), f"{domain_id}:topic_stats")
        require(meta.get("stats", {}).get("statements") == len(statements), f"{domain_id}:statement_stats")
        for node in nodes:
            text = " ".join(str(node.get(key) or "") for key in ("title", "top_down_role"))
            require(FORBIDDEN_TEXT not in text, f"{domain_id}:forbidden_text")

    require(len(all_ids) == len(set(all_ids)), "duplicate_topic_ids")
    require(len(all_statement_ids) == len(set(all_statement_ids)), "duplicate_statement_ids")
    require(sum(row["topics"] for row in domain_counts.values()) == EXPECTED_TOTALS["topics"], "computed_topics")
    require(sum(row["statements"] for row in domain_counts.values()) == EXPECTED_TOTALS["statements"], "computed_statements")

    for domain_id, (part_id, root_id, old_domain_id) in TARGETS.items():
        require(domain_id in domain_lookup, f"{domain_id}:missing")
        nodes = domain_nodes(site, domain_lookup[domain_id])
        ids = {str(node.get("topic_id")) for node in nodes}
        require(part_id not in ids and root_id in ids, f"{domain_id}:single_root")
        promoted_root = next(node for node in nodes if node.get("topic_id") == root_id)
        require(promoted_root.get("published_part_id") == part_id, f"{domain_id}:part_label")
        require(promoted_root.get("presentation_policy") == "promoted_root_without_wrapper", f"{domain_id}:presentation")
        old_ids = {str(node.get("topic_id")) for node in domain_nodes(site, domain_lookup[old_domain_id])}
        require(root_id not in old_ids, f"{domain_id}:still_in_old_domain")
        route = (manifest.get("legacy_domain_routes") or {}).get(domain_id, {})
        require(route.get("domain_id") == domain_id and route.get("default_node_id") == root_id, f"{domain_id}:route")

    duplicate_counts = [key for key, count in Counter(all_ids).items() if count > 1]
    report = {
        "schema_version": "web-v64-major-tracks-validation-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_version": manifest.get("snapshot_version"),
        "release_directories": release_directories,
        "directory_tree_id": (manifest.get("directory_snapshot") or {}).get("tree_id"),
        "domain_count": len(domain_lookup),
        "totals": manifest.get("totals"),
        "duplicate_topic_ids": duplicate_counts,
        "failure_codes": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    report_path = args.report or ROOT / "releases/20260819_v64_major_tracks_v1/live_validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
