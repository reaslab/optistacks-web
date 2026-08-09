#!/usr/bin/env python3
"""Import full A03/A05 directory and statement layers from the OptiStacks source."""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator


NEW_DOMAINS = (
    {
        "id": "variational_analysis",
        "part_id": "A03",
        "short_name": "Variational Analysis",
        "accent": "#a65f18",
    },
    {
        "id": "first_order_methods",
        "part_id": "A05",
        "short_name": "First-Order Methods",
        "accent": "#b6406a",
    },
)

DOMAIN_ORDER = (
    "convex_analysis",
    "variational_analysis",
    "nonlinear_programming",
    "first_order_methods",
    "distributed_optimization",
)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        value,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    ) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def statement_fingerprint(record: dict[str, Any], topic_id: str) -> tuple[str, ...]:
    return (
        normalize_text(topic_id),
        normalize_text(record.get("statement_title") or record.get("title")),
        normalize_text(record.get("statement_latex")),
        normalize_text(record.get("statement_plain")),
    )


def restore_full_domain(site: Path, data_url: str) -> dict[str, Any]:
    data_path = site / data_url
    data = read_json(data_path)
    if data.get("loading", {}).get("mode") != "chapter_shards":
        return data
    for root in data.get("roots", []):
        restored_children = []
        for child in root.get("children", []):
            shard_url = child.get("shard_url")
            if not shard_url:
                restored_children.append(child)
                continue
            payload = read_json(site / shard_url)
            if payload.get("chapter_id") != child.get("topic_id"):
                raise RuntimeError(f"Shard mismatch for {child.get('topic_id')}")
            restored_children.append(payload["root"])
        root["children"] = restored_children
    data.pop("loading", None)
    data.pop("node_routes", None)
    return data


def source_witnesses(raw_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    witnesses = []
    for reference in raw_refs:
        witness = deepcopy(reference)
        witness.setdefault("source_title", witness.get("source"))
        witnesses.append(witness)
    return witnesses


def normalize_statement(
    record: dict[str, Any],
    topic_id: str,
    layer_role: str,
    stage: str,
    source_path: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = deepcopy(record)
    fingerprint = statement_fingerprint(record, topic_id)
    normalized["id"] = normalized.get("statement_id") or normalized.get("id") or (
        "stmt_" + sha256(repr(fingerprint).encode()).hexdigest()[:20]
    )
    normalized["node_type"] = "knowledge_statement"
    normalized["title"] = normalized.get("statement_title") or normalized.get("title") or "Untitled statement"
    normalized["original_topic_id"] = topic_id
    normalized["mapped_topic_ids"] = [topic_id]
    normalized["mapping_method"] = "exact_topic_id"
    normalized["layer_role"] = layer_role
    normalized["source_witnesses"] = normalized.get("source_witnesses") or normalized.get("source_refs", [])
    normalized.setdefault("assumptions_latex", [])
    normalized.setdefault("notation", [])
    normalized.setdefault("prerequisite_node_ids", [])
    normalized.setdefault("review_flags", [])
    normalized.setdefault("proof_included", False)
    if layer_role == "intermediate_result":
        normalized["intermediate_metadata"] = {
            "stage": stage,
            "source_path": source_path,
            **(context or {}),
        }
    return normalized


def collect_statements(
    source: Path,
    part_id: str,
    topic_ids: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any], str]:
    code = part_id.lower()
    run = source / "outputs/runs/output_topic_complete_expansion" / f"topic_complete_{code}_full"
    current_path = run / "current_statement_layer.json"
    deferred_path = run / "deferred_ledger.json"
    run_manifest = read_json(run / "manifest.json")
    current = read_json(current_path)
    deferred = read_json(deferred_path)
    seed_count = int(current.get("seed_record_count", 0))

    records_by_topic: dict[str, list[dict[str, Any]]] = {topic_id: [] for topic_id in topic_ids}
    seen: set[tuple[str, ...]] = set()
    seen_titles: dict[str, set[str]] = {topic_id: set() for topic_id in topic_ids}
    report: dict[str, Any] = {
        "official_statement_count": 0,
        "added_intermediate_count": 0,
        "unmapped_intermediate_count": 0,
        "ancestor_mapped_intermediate_count": 0,
        "duplicate_intermediate_count": 0,
        "duplicate_official_title_count": 0,
        "duplicate_intermediate_title_count": 0,
        "sources": Counter(),
    }

    def attach(
        record: dict[str, Any],
        fallback_topic_id: str,
        layer_role: str,
        stage: str,
        source_path: Path,
        context: dict[str, Any] | None = None,
    ) -> None:
        original_topic_id = str(
            record.get("source_node_id")
            or record.get("node_id")
            or record.get("original_topic_id")
            or fallback_topic_id
        )
        if not original_topic_id.upper().startswith(part_id):
            return
        topic_id = original_topic_id
        while topic_id not in topic_ids and "." in topic_id:
            topic_id = topic_id.rsplit(".", 1)[0]
        if topic_id not in topic_ids:
            report["unmapped_intermediate_count"] += 1
            return
        mapped = topic_id != original_topic_id
        if mapped:
            report["ancestor_mapped_intermediate_count"] += 1
        title_key = normalize_text(record.get("statement_title") or record.get("title"))
        if title_key and title_key in seen_titles[topic_id]:
            if layer_role == "base_statement_layer":
                report["duplicate_official_title_count"] += 1
            else:
                report["duplicate_intermediate_count"] += 1
                report["duplicate_intermediate_title_count"] += 1
            return
        fingerprint = statement_fingerprint(record, topic_id)
        if fingerprint in seen:
            if layer_role != "base_statement_layer":
                report["duplicate_intermediate_count"] += 1
            return
        seen.add(fingerprint)
        if title_key:
            seen_titles[topic_id].add(title_key)
        normalized_context = dict(context or {})
        if mapped:
            normalized_context["mapped_from_topic_id"] = original_topic_id
        normalized = normalize_statement(
            record,
            topic_id,
            layer_role,
            stage,
            str(source_path.relative_to(source)),
            normalized_context,
        )
        if mapped:
            normalized["mapping_method"] = "nearest_canonical_ancestor"
        records_by_topic[topic_id].append(normalized)
        if layer_role == "base_statement_layer":
            report["official_statement_count"] += 1
        else:
            report["added_intermediate_count"] += 1
            report["sources"][stage] += 1

    for index, record in enumerate(current.get("records", [])):
        if not isinstance(record, dict):
            continue
        is_seed = index < seed_count
        attach(
            record,
            "",
            "base_statement_layer" if is_seed else "intermediate_result",
            "v58_published" if is_seed else "topic_complete_current",
            current_path,
        )

    for ledger_name in ("seed_deferred", "new_deferred"):
        for item in deferred.get(ledger_name, []):
            candidate = item.get("candidate_record")
            if not isinstance(candidate, dict):
                continue
            attach(
                candidate,
                item.get("topic_id") or item.get("node_id") or "",
                "intermediate_result",
                f"topic_complete_{ledger_name}",
                deferred_path,
                {
                    "reason": item.get("reason"),
                    "issue_codes": item.get("issue_codes", []),
                    "review_comment": item.get("review_comment"),
                },
            )

    report["total_statement_count"] = report["official_statement_count"] + report["added_intermediate_count"]
    report["sources"] = dict(sorted(report["sources"].items()))
    return records_by_topic, report, str(run_manifest.get("created_at") or "")


def convert_part(
    source: Path,
    raw_part: dict[str, Any],
    config: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    topic_ids = {raw_part["part_id"]}
    for raw in raw_part.get("children", []):
        topic_ids.update(node["node_id"] for node in walk(raw))
    statements_by_topic, intermediate_report, generated_at = collect_statements(
        source, config["part_id"], topic_ids
    )

    def convert(raw: dict[str, Any], topic_id: str, number: str, depth: int) -> dict[str, Any]:
        children = [
            convert(child, child["node_id"], f"{number}.{index}", depth + 1)
            for index, child in enumerate(raw.get("children", []), 1)
        ]
        statements = statements_by_topic.get(topic_id, [])
        node = {
            "topic_id": topic_id,
            "display_number": number,
            "title": raw.get("title") or topic_id,
            "topic_type": raw.get("node_type") or raw.get("navigation_kind") or "topic",
            "depth": depth,
            "classification_axis": raw.get("navigation_kind") or "pedagogical dependency",
            "top_down_role": raw.get("role") or raw.get("scope_note") or "",
            "knowledge_status": "statement_attached" if statements else "structural_container_with_descendant_knowledge" if children else "structural_leaf",
            "top_down_textbook_witnesses": source_witnesses(raw.get("source_refs", [])),
            "knowledge_statements": statements,
            "children": children,
        }
        return node

    root_number = re.sub(r"\D", "", config["part_id"]).lstrip("0") or "0"
    root = convert(raw_part, config["part_id"], root_number, 0)

    def update_counts(node: dict[str, Any]) -> tuple[int, int, int, int]:
        statements = node["knowledge_statements"]
        direct_base = sum(item.get("layer_role") == "base_statement_layer" for item in statements)
        direct_intermediate = len(statements) - direct_base
        subtree_statements = len(statements)
        subtree_base = direct_base
        subtree_intermediate = direct_intermediate
        subtree_topics = 1
        for child in node["children"]:
            child_statements, child_base, child_intermediate, child_topics = update_counts(child)
            subtree_statements += child_statements
            subtree_base += child_base
            subtree_intermediate += child_intermediate
            subtree_topics += child_topics
        node["direct_statement_count"] = len(statements)
        node["direct_base_statement_count"] = direct_base
        node["direct_enrichment_statement_count"] = direct_intermediate
        node["descendant_statement_count"] = subtree_statements
        node["descendant_base_statement_count"] = subtree_base
        node["descendant_enrichment_statement_count"] = subtree_intermediate
        node["direct_content_kind_counts"] = dict(
            sorted(Counter(item.get("content_kind", "unknown") for item in statements).items())
        )
        node["subtree_topic_count"] = subtree_topics
        return subtree_statements, subtree_base, subtree_intermediate, subtree_topics

    update_counts(root)
    nodes = list(walk(root))
    statements = [item for node in nodes for item in node["knowledge_statements"]]
    leaves = [node for node in nodes if not node["children"]]
    covered_leaves = sum(bool(node["knowledge_statements"]) for node in leaves)
    content_kinds = Counter(item.get("content_kind", "unknown") for item in statements)
    chapter_summaries = [
        {
            "topic_id": chapter["topic_id"],
            "display_number": chapter["display_number"],
            "title": chapter["title"],
            "classification_axis": chapter["classification_axis"],
            "subtree_topic_count": chapter["subtree_topic_count"],
            "subtree_statement_count": chapter["descendant_statement_count"],
        }
        for chapter in root["children"]
    ]
    tree = {
        "schema_version": "knowledge-classification-tree-v1",
        "generated_at": generated_at,
        "domain_id": config["id"],
        "display_name": config["short_name"],
        "construction": {
            "top_down": "complete A03/A05 directory from the source v57 full-depth snapshot",
            "bottom_up": "v58 published statements plus topic-complete accepted and deferred records",
            "hard_boundary": "source placement and mechanical import do not certify mathematical correctness",
        },
        "roots": [root],
    }
    domain = {
        "id": config["id"],
        "short_name": config["short_name"],
        "accent": config["accent"],
        "data_url": f"data/{config['id']}.json",
        "generated_at": generated_at,
        "validation_status": "PASS",
        "publication_status": "source_snapshot_with_unverified_intermediate_results_exposed",
        "stats": {
            "topics": len(nodes),
            "statements": len(statements),
            "official_statements": intermediate_report["official_statement_count"],
            "intermediate_statements": intermediate_report["added_intermediate_count"],
            "chapters": len(root["children"]),
            "leaf_topics": len(leaves),
            "base_statements": intermediate_report["official_statement_count"],
            "coverage": covered_leaves / len(leaves) if leaves else 0.0,
            "max_depth": max(node["depth"] for node in nodes),
            "content_kinds": dict(sorted(content_kinds.items())),
        },
        "intermediate_result_report": intermediate_report,
        "chapters": chapter_summaries,
    }
    return tree, domain


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/root/workspace/lcy/optistacks"))
    parser.add_argument("--site", type=Path, default=Path(__file__).resolve().parents[1] / "site")
    args = parser.parse_args()
    source = args.source.resolve()
    site = args.site.resolve()
    manifest_path = site / "data/manifest.json"
    manifest = read_json(manifest_path)

    existing_domains: dict[str, dict[str, Any]] = {}
    for domain in manifest["domains"]:
        if domain["id"] in {item["id"] for item in NEW_DOMAINS}:
            continue
        full_data = restore_full_domain(site, domain["data_url"])
        write_json(site / domain["data_url"], full_data)
        preserved = deepcopy(domain)
        preserved.pop("loading", None)
        existing_domains[domain["id"]] = preserved

    package = source / "outputs/packages/optistacks_tree_graph_corrected_v27.zip"
    with zipfile.ZipFile(package) as archive:
        source_tree = json.loads(archive.read("snapshot/tree.json"))
    parts = {part["part_id"]: part for part in source_tree["parts"]}

    imported_domains: dict[str, dict[str, Any]] = {}
    for config in NEW_DOMAINS:
        tree, domain = convert_part(source, parts[config["part_id"]], config)
        write_json(site / domain["data_url"], tree)
        imported_domains[domain["id"]] = domain
        print(
            f"{domain['short_name']}: {domain['stats']['topics']:,} topics, "
            f"{domain['stats']['statements']:,} statements"
        )

    domains = {**existing_domains, **imported_domains}
    manifest["domains"] = [domains[domain_id] for domain_id in DOMAIN_ORDER]
    manifest["built_at"] = datetime.now(timezone.utc).isoformat()
    manifest["totals"] = {
        "topics": sum(item["stats"]["topics"] for item in manifest["domains"]),
        "statements": sum(item["stats"]["statements"] for item in manifest["domains"]),
    }
    manifest.pop("loading", None)
    write_json(manifest_path, manifest, pretty=True)
    print(f"Total: {manifest['totals']['topics']:,} topics, {manifest['totals']['statements']:,} statements")


if __name__ == "__main__":
    main()
