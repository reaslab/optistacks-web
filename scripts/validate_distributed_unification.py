#!/usr/bin/env python3
"""Validate (and optionally repair) the unified website A07.C03 projection."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "site"
DEFAULT_MAPPING = Path(
    "/root/workspace/lcy/optistacks/distributed/"
    "distributed_optimization_node_mapping.json"
)
DOMAIN_ID = "specialized_continuous_methods"
LEGACY_DOMAIN_ID = "distributed_optimization"
ROOT_ID = "A07.C03"
BASE_REVISION_STATEMENT_COUNT = 876
HARD_ALIAS_SOURCE = "A07.C03.NC77ECCB1B848.AND6C2C62B88F"


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    temporary.replace(path)


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def redirects(mapping: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in mapping.get("primary_cross_reference_mapping") or []:
        result[str(row["source_node_id"])] = str(row["primary_target_node_id"])
    for row in mapping.get("external_cross_reference_mapping") or []:
        result[str(row["source_node_id"])] = str(row["target_node_id"])
    return result


def statement_node(statement: dict[str, Any]) -> str:
    return str(
        statement.get("node_id")
        or statement.get("source_node_id")
        or statement.get("original_topic_id")
        or ""
    )


def update_counts(node: dict[str, Any]) -> tuple[int, int, int, int]:
    statements = node.get("knowledge_statements") or []
    direct_base = sum(item.get("layer_role") == "base_statement_layer" for item in statements)
    total = len(statements)
    base = direct_base
    enrichment = total - direct_base
    topics = 1
    for child in node.get("children") or []:
        child_total, child_base, child_enrichment, child_topics = update_counts(child)
        total += child_total
        base += child_base
        enrichment += child_enrichment
        topics += child_topics
    node["direct_statement_count"] = len(statements)
    node["direct_base_statement_count"] = direct_base
    node["direct_enrichment_statement_count"] = len(statements) - direct_base
    node["descendant_statement_count"] = total
    node["descendant_base_statement_count"] = base
    node["descendant_enrichment_statement_count"] = enrichment
    node["direct_content_kind_counts"] = dict(
        sorted(Counter(item.get("content_kind", "unknown") for item in statements).items())
    )
    node["subtree_topic_count"] = topics
    return total, base, enrichment, topics


def repair_statement_aliases(root: dict[str, Any], alias_map: dict[str, str]) -> int:
    nodes = {node["topic_id"]: node for node in walk(root)}
    pending: list[tuple[str, dict[str, Any]]] = []
    relocated = 0
    for node in nodes.values():
        retained: list[dict[str, Any]] = []
        for statement in node.get("knowledge_statements") or []:
            source_id = statement_node(statement)
            target_id = alias_map.get(source_id)
            if not target_id or target_id == node["topic_id"]:
                retained.append(statement)
                continue
            if target_id not in nodes:
                raise RuntimeError(f"Statement alias target is missing: {source_id} -> {target_id}")
            updated = dict(statement)
            updated["original_source_node_id"] = source_id
            if "node_id" in updated:
                updated["node_id"] = target_id
            if "source_node_id" in updated:
                updated["source_node_id"] = target_id
            updated["original_topic_id"] = source_id
            updated["mapped_topic_ids"] = [target_id]
            updated["mapping_method"] = "explicit_node_alias"
            pending.append((target_id, updated))
            relocated += 1
        node["knowledge_statements"] = retained
    for target_id, statement in pending:
        nodes[target_id].setdefault("knowledge_statements", []).append(statement)
    update_counts(root)
    return relocated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--repair-statement-aliases", action="store_true")
    args = parser.parse_args()

    manifest_path = args.site / "data/manifest.json"
    catalog_path = args.site / f"data/{DOMAIN_ID}.json"
    shard_path = args.site / f"data/shards/{DOMAIN_ID}/a07-c03.json"
    manifest = read_json(manifest_path)
    catalog = read_json(catalog_path)
    shard = read_json(shard_path)
    mapping = read_json(args.mapping)
    alias_map = redirects(mapping)

    relocated = 0
    if args.repair_statement_aliases:
        relocated = repair_statement_aliases(shard["root"], alias_map)
        atomic_write(shard_path, shard)

    nodes = list(walk(shard["root"]))
    node_index = {node["topic_id"]: node for node in nodes}
    statements = [
        (node["topic_id"], statement)
        for node in nodes
        for statement in node.get("knowledge_statements") or []
    ]
    duplicate_statement_titles = []
    for node in nodes:
        titles = [
            " ".join(str(statement.get("statement_title") or statement.get("title") or "").split()).casefold()
            for statement in node.get("knowledge_statements") or []
        ]
        duplicate_statement_titles.extend(
            (node["topic_id"], title)
            for title, count in Counter(titles).items()
            if title and count > 1
        )
    statement_ids = [
        str(statement.get("id") or statement.get("statement_id") or "")
        for _, statement in statements
    ]
    leaves = sum(not (node.get("children") or []) for node in nodes)
    domain_ids = [domain["id"] for domain in manifest.get("domains") or []]
    specialized = next(domain for domain in manifest["domains"] if domain["id"] == DOMAIN_ID)
    a07 = next(root for root in catalog["roots"] if root["topic_id"] == "A07")
    chapter_occurrences = sum(child["topic_id"] == ROOT_ID for child in a07["children"])
    manifest_aliases = manifest.get("node_redirects", {}).get(DOMAIN_ID, {})
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(LEGACY_DOMAIN_ID not in domain_ids, "Standalone distributed domain is still published")
    require(len(domain_ids) == 15, f"Manifest has {len(domain_ids)} domains, expected 15")
    require(chapter_occurrences == 1, f"A07 catalog contains A07.C03 {chapter_occurrences} times")
    require(shard["root"]["topic_id"] == ROOT_ID, "A07.C03 shard has the wrong root")
    require(len(nodes) == 543, f"A07.C03 contains {len(nodes)} topics, expected 543")
    require(len(node_index) == len(nodes), "A07.C03 topic IDs are not unique")
    require(leaves == 397, f"A07.C03 has {leaves} leaves, expected 397")
    require(len(shard["root"].get("children") or []) == 9, "A07.C03 does not have nine top-level themes")
    require(
        len(statements) >= BASE_REVISION_STATEMENT_COUNT,
        f"A07.C03 contains {len(statements)} statements, below the reviewed revision baseline "
        f"of {BASE_REVISION_STATEMENT_COUNT}",
    )
    require(len(set(statement_ids)) == len(statement_ids), "Statement IDs are not unique")
    require(
        not duplicate_statement_titles,
        f"A07.C03 contains duplicate statement titles: {duplicate_statement_titles[:3]}",
    )
    require(HARD_ALIAS_SOURCE not in node_index, "Merged old A07 node is still materialized")
    require(set(alias_map.values()) <= set(node_index), "At least one redirect target is absent from A07.C03")
    require(manifest_aliases == dict(sorted(alias_map.items())), "Manifest redirect map differs from reviewed mapping")
    route = manifest.get("legacy_domain_routes", {}).get(LEGACY_DOMAIN_ID, {})
    require(route.get("domain_id") == DOMAIN_ID, "Legacy domain does not route to A07 domain")
    require(route.get("default_node_id") == ROOT_ID, "Legacy domain does not default to A07.C03")
    shortcuts = manifest.get("navigation_shortcuts") or []
    distributed_shortcuts = [item for item in shortcuts if item.get("id") == LEGACY_DOMAIN_ID]
    require(len(distributed_shortcuts) == 1, "Distributed navigation shortcut is missing or duplicated")
    if distributed_shortcuts:
        shortcut = distributed_shortcuts[0]
        require(shortcut.get("position") == 5, "Distributed navigation shortcut is not fifth")
        require(shortcut.get("domain_id") == DOMAIN_ID, "Distributed shortcut targets the wrong domain")
        require(shortcut.get("default_node_id") == ROOT_ID, "Distributed shortcut targets the wrong node")
        require(shortcut.get("stats", {}).get("topics") == 543, "Distributed shortcut topic count is stale")
        require(
            shortcut.get("stats", {}).get("statements") == len(statements),
            "Distributed shortcut statement count is stale",
        )
    require(
        manifest.get("distributed_route_compatibility", {}).get("mapping_sha256")
        == sha256(args.mapping.read_bytes()).hexdigest(),
        "Manifest mapping SHA is stale",
    )
    require(
        not any(alias_map.get(statement_node(statement)) not in (None, topic_id) for topic_id, statement in statements),
        "A statement remains attached through a stale aliased node",
    )
    require(
        not any("nearest_canonical_ancestor" in str(statement.get("mapping_method")) for _, statement in statements),
        "A07.C03 still contains nearest-ancestor statement placement",
    )
    require(
        specialized["stats"]["topics"] >= 543
        and next(item for item in specialized["chapters"] if item["topic_id"] == ROOT_ID)["subtree_topic_count"] == 543,
        "Manifest A07.C03 topic accounting is stale",
    )
    require(
        next(item for item in specialized["chapters"] if item["topic_id"] == ROOT_ID)["subtree_statement_count"]
        == len(statements),
        "Manifest A07.C03 statement accounting is stale",
    )
    require(not (args.site / "data/distributed_optimization.json").exists(), "Legacy domain payload still exists")
    require(
        not (args.site / "data/shards/distributed_optimization").exists(),
        "Legacy domain shard directory still exists",
    )
    if failures:
        raise RuntimeError("Distributed unification validation failed:\n- " + "\n- ".join(failures))
    report = {
        "status": "PASS",
        "domains": len(domain_ids),
        "a07_c03_topics": len(nodes),
        "a07_c03_leaves": leaves,
        "a07_c03_statements": len(statements),
        "top_level_themes": len(shard["root"]["children"]),
        "node_redirects": len(alias_map),
        "statement_aliases_relocated": relocated,
        "nearest_ancestor_placements": 0,
        "standalone_domain_entries": 0,
        "navigation_shortcuts": len(distributed_shortcuts),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
