#!/usr/bin/env python3
"""Import complete A02-A16 directories and all available statement layers."""

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


PART_DOMAINS = (
    {
        "id": "convex_analysis",
        "part_id": "A02",
        "short_name": "Convex Analysis",
        "accent": "#315b7d",
    },
    {
        "id": "variational_analysis",
        "part_id": "A03",
        "short_name": "Variational Analysis",
        "accent": "#a65f18",
    },
    {
        "id": "nonlinear_programming",
        "part_id": "A04",
        "short_name": "Nonlinear Programming",
        "accent": "#316a5c",
    },
    {
        "id": "first_order_methods",
        "part_id": "A05",
        "short_name": "First-Order Methods",
        "accent": "#b6406a",
    },
    {
        "id": "nonsmooth_optimization",
        "part_id": "A06",
        "short_name": "Nonsmooth Optimization",
        "accent": "#72558a",
    },
    {
        "id": "specialized_continuous_methods",
        "part_id": "A07",
        "short_name": "Specialized Continuous and Large-Scale Methods",
        "accent": "#3f7589",
    },
    {
        "id": "convex_programming",
        "part_id": "A08",
        "short_name": "Convex Programming",
        "accent": "#8a643b",
    },
    {
        "id": "linear_programming",
        "part_id": "A09",
        "short_name": "Linear Programming",
        "accent": "#4f6f46",
    },
    {
        "id": "conic_optimization",
        "part_id": "A10",
        "short_name": "Conic Optimization",
        "accent": "#855a73",
    },
    {
        "id": "quadratic_optimization",
        "part_id": "A11",
        "short_name": "Quadratic Optimization",
        "accent": "#536d91",
    },
    {
        "id": "integer_mixed_integer_optimization",
        "part_id": "A12",
        "short_name": "Integer and Mixed-Integer Optimization",
        "accent": "#84623d",
    },
    {
        "id": "combinatorial_optimization",
        "part_id": "A13",
        "short_name": "Combinatorial Optimization",
        "accent": "#3e7565",
    },
    {
        "id": "constraint_logic_optimization",
        "part_id": "A14",
        "short_name": "Constraint and Logic-Based Optimization",
        "accent": "#765e87",
    },
    {
        "id": "global_optimization",
        "part_id": "A15",
        "short_name": "Global Optimization",
        "accent": "#9a5948",
    },
    {
        "id": "optimization_under_uncertainty",
        "part_id": "A16",
        "short_name": "Optimization under Uncertainty",
        "accent": "#497286",
    },
)

LEGACY_DOMAIN_ID = "distributed_optimization"
DOMAIN_ORDER = tuple(config["id"] for config in PART_DOMAINS) + (LEGACY_DOMAIN_ID,)

CAMPAIGN_RELATIVE_PATHS = (
    Path("0809_optimize/formal_runs/20260809_full_library_v2"),
    Path("0809_optimize/formal_runs/20260812_full_library_200_supplemental25_v1"),
)
CAMPAIGN_STAGE_PRIORITY = {
    "0809_campaign_build": 1,
    "0809_campaign_reviewed": 2,
    "0809_campaign_published": 3,
}


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


def statement_has_body(record: dict[str, Any]) -> bool:
    return bool(
        (record.get("statement_title") or record.get("title"))
        and (record.get("statement_latex") or record.get("statement_plain"))
    )


def validation_passes(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return read_json(path).get("status") == "PASS"
    except (OSError, ValueError, TypeError):
        return False


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


def strip_campaign_statements(tree: dict[str, Any]) -> None:
    for root in tree.get("roots", []):
        for node in walk(root):
            node["knowledge_statements"] = [
                statement
                for statement in node.get("knowledge_statements", [])
                if not str((statement.get("intermediate_metadata") or {}).get("stage") or "").startswith(
                    "0809_campaign_"
                )
            ]


def collect_preserved_nodes(
    site: Path,
    manifest: dict[str, Any],
    *,
    excluded_domain_ids: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    excluded_domain_ids = excluded_domain_ids or set()
    preserved: dict[str, dict[str, Any]] = {}
    report: dict[str, Any] = {
        "domains": 0,
        "topics": 0,
        "statements": 0,
        "duplicate_topic_occurrences": 0,
    }
    for domain in manifest.get("domains", []):
        if domain["id"] in excluded_domain_ids:
            continue
        tree = restore_full_domain(site, domain["data_url"])
        report["domains"] += 1
        for root in tree.get("roots", []):
            for node in walk(root):
                topic_id = node["topic_id"]
                statements = deepcopy(node.get("knowledge_statements", []))
                if topic_id not in preserved:
                    preserved[topic_id] = {
                        "title": node.get("title"),
                        "statements": statements,
                    }
                else:
                    report["duplicate_topic_occurrences"] += 1
                    preserved[topic_id]["statements"].extend(statements)
                report["statements"] += len(statements)
    report["topics"] = len(preserved)
    return preserved, report


def merge_preserved_statements(
    tree: dict[str, Any], preserved_nodes: dict[str, dict[str, Any]]
) -> dict[str, int]:
    report = {
        "matched_topics": 0,
        "added_statements": 0,
        "duplicate_titles": 0,
        "duplicate_ids": 0,
    }
    statement_ids = {
        str(statement.get("id") or statement.get("statement_id"))
        for root in tree["roots"]
        for node in walk(root)
        for statement in node.get("knowledge_statements", [])
        if statement.get("id") or statement.get("statement_id")
    }
    for root in tree["roots"]:
        for node in walk(root):
            old = preserved_nodes.get(node["topic_id"])
            if not old:
                continue
            report["matched_topics"] += 1
            if old.get("title"):
                node["title"] = old["title"]
            titles = {
                normalize_text(statement.get("statement_title") or statement.get("title"))
                for statement in node["knowledge_statements"]
                if statement.get("statement_title") or statement.get("title")
            }
            for statement in old["statements"]:
                title_key = normalize_text(statement.get("statement_title") or statement.get("title"))
                if title_key and title_key in titles:
                    report["duplicate_titles"] += 1
                    continue
                statement = deepcopy(statement)
                statement_id = str(statement.get("id") or statement.get("statement_id") or "")
                if statement_id and statement_id in statement_ids:
                    report["duplicate_ids"] += 1
                    statement["id"] = "stmt_preserved_" + sha256(
                        repr(statement_fingerprint(statement, node["topic_id"])).encode()
                    ).hexdigest()[:20]
                    statement_id = statement["id"]
                if statement_id:
                    statement_ids.add(statement_id)
                node["knowledge_statements"].append(statement)
                if title_key:
                    titles.add(title_key)
                report["added_statements"] += 1
    return report


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


def read_validated_phase(campaign: Path, phase: str) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    shard_dir = campaign / phase / "by_shard"
    validation_dir = campaign / phase / "validation"
    for shard_path in sorted(shard_dir.glob("*.json")):
        validation_path = validation_dir / shard_path.name
        if not validation_passes(validation_path):
            continue
        payload_bytes = shard_path.read_bytes()
        try:
            payload = json.loads(payload_bytes)
        except (ValueError, TypeError):
            continue
        if payload.get("shard_id") != shard_path.stem:
            continue
        for item in payload.get("items", []):
            source_item_id = str(item.get("source_item_id") or "")
            if source_item_id:
                records[source_item_id] = item
    return records


def campaign_source_evidence(campaign: Path) -> dict[str, dict[str, Any]]:
    ledger_path = campaign / "plan/source_item_ledger.json"
    if not ledger_path.exists():
        return {}
    ledger = read_json(ledger_path)
    evidence = {}
    for item in ledger.get("source_items", []):
        source_item_id = str(item.get("source_item_id") or "")
        if not source_item_id:
            continue
        evidence[source_item_id] = {
            "source_item_id": source_item_id,
            "source_path": item.get("source_path"),
            "source_file_sha256": item.get("source_file_sha256"),
            "content_sha256": item.get("content_sha256"),
            "locator": item.get("locator"),
            "source_environment": item.get("source_environment"),
        }
    return evidence


def campaign_placement_hints(item: dict[str, Any]) -> list[tuple[str, str]]:
    hints: list[tuple[str, str]] = []

    def extend(method: str, values: Any) -> None:
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, list):
            return
        for value in values:
            value = str(value or "").strip()
            if value:
                hints.append((method, value))

    extend("campaign_existing_node", item.get("source_node_id"))
    extend("campaign_existing_node", item.get("existing_node_id"))
    directory = item.get("directory_assessment") or {}
    extend("campaign_preferred_home", directory.get("preferred_home_node_id"))
    new_node = item.get("new_node_candidate") or {}
    extend("campaign_parent_fallback", new_node.get("parent_candidate_ids"))
    if not hints:
        affected = directory.get("affected_existing_node_ids") or []
        if len(affected) == 1:
            extend("campaign_single_affected_node", affected)
    return hints


def prepare_campaign_record(
    item: dict[str, Any],
    candidate: dict[str, Any],
    campaign_root: Path,
    campaign_name: str,
    stage: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    record = deepcopy(candidate)
    source_item_id = str(item.get("source_item_id") or record.get("source_item_id") or "")
    record["source_item_id"] = source_item_id
    record["statement_id"] = "stmt_0809_" + sha256(source_item_id.encode()).hexdigest()[:20]
    record["source_evidence"] = deepcopy(evidence)
    if evidence:
        record["source_refs"] = [
            {
                "source": campaign_name,
                "source_title": Path(str(evidence.get("source_path") or campaign_name)).stem,
                **evidence,
            }
        ]
    record["review_confidence"] = item.get("review_confidence")
    record["review_flags"] = item.get("review_flags") or []
    return {
        "source_item_id": source_item_id,
        "campaign_root": campaign_root,
        "campaign": campaign_name,
        "stage": stage,
        "record": record,
        "placement_hints": campaign_placement_hints({**item, **record}),
        "context": {
            "campaign": campaign_name,
            "source_item_id": source_item_id,
            "review_decision": item.get("review_decision"),
            "primary_disposition": item.get("primary_disposition"),
            "directory_assessment": item.get("directory_assessment") or {},
        },
    }


def collect_campaign_candidates(source: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    report: dict[str, Any] = {
        "campaign_roots": [str(path) for path in CAMPAIGN_RELATIVE_PATHS],
        "campaigns_scanned": 0,
        "validated_build_items": 0,
        "validated_review_items": 0,
        "published_items": 0,
        "candidates_with_body": 0,
    }

    def select(entry: dict[str, Any]) -> None:
        if not entry["source_item_id"] or not statement_has_body(entry["record"]):
            return
        current = selected.get(entry["source_item_id"])
        if current is None or CAMPAIGN_STAGE_PRIORITY[entry["stage"]] > CAMPAIGN_STAGE_PRIORITY[current["stage"]]:
            selected[entry["source_item_id"]] = entry

    available_roots = [path for path in CAMPAIGN_RELATIVE_PATHS if (source / path).exists()]
    if not available_roots:
        report["status"] = "campaign_not_found"
        return [], report

    for relative_root in available_roots:
        campaign_root = source / relative_root
        for campaign in sorted(path for path in campaign_root.iterdir() if path.is_dir()):
            ledger_evidence = campaign_source_evidence(campaign)
            if not ledger_evidence and not (campaign / "build").exists():
                continue
            report["campaigns_scanned"] += 1

            build_items = read_validated_phase(campaign, "build")
            review_items = read_validated_phase(campaign, "review")
            report["validated_build_items"] += len(build_items)
            report["validated_review_items"] += len(review_items)

            for source_item_id, item in build_items.items():
                candidate = item.get("statement_candidate") or {}
                select(
                    prepare_campaign_record(
                        item,
                        candidate,
                        relative_root,
                        campaign.name,
                        "0809_campaign_build",
                        ledger_evidence.get(source_item_id, {}),
                    )
                )

            for source_item_id, item in review_items.items():
                candidate = item.get("statement_candidate") or {}
                select(
                    prepare_campaign_record(
                        item,
                        candidate,
                        relative_root,
                        campaign.name,
                        "0809_campaign_reviewed",
                        ledger_evidence.get(source_item_id, {}),
                    )
                )

            overlay_path = campaign / "publish/reviewed_textbook_coverage_overlay.json"
            if overlay_path.exists():
                overlay = read_json(overlay_path)
                for record in overlay.get("existing_node_statement_candidates", []):
                    source_item_id = str(record.get("source_item_id") or "")
                    report["published_items"] += 1
                    select(
                        prepare_campaign_record(
                            record,
                            record,
                            relative_root,
                            campaign.name,
                            "0809_campaign_published",
                            record.get("source_evidence") or ledger_evidence.get(source_item_id, {}),
                        )
                    )
                for wrapper in overlay.get("new_node_candidates", []):
                    source_item_id = str(wrapper.get("source_item_id") or "")
                    report["published_items"] += 1
                    select(
                        prepare_campaign_record(
                            wrapper,
                            wrapper.get("statement_candidate") or {},
                            relative_root,
                            campaign.name,
                            "0809_campaign_published",
                            wrapper.get("source_evidence") or ledger_evidence.get(source_item_id, {}),
                        )
                    )

    candidates = [selected[key] for key in sorted(selected)]
    report["candidates_with_body"] = len(candidates)
    report["stage_counts"] = dict(sorted(Counter(item["stage"] for item in candidates).items()))
    report["status"] = "snapshot_collected"
    return candidates, report


def update_tree_counts(node: dict[str, Any]) -> tuple[int, int, int, int]:
    statements = node["knowledge_statements"]
    direct_base = sum(item.get("layer_role") == "base_statement_layer" for item in statements)
    direct_intermediate = len(statements) - direct_base
    subtree_statements = len(statements)
    subtree_base = direct_base
    subtree_intermediate = direct_intermediate
    subtree_topics = 1
    for child in node["children"]:
        child_statements, child_base, child_intermediate, child_topics = update_tree_counts(child)
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


def update_tree_statement_totals(node: dict[str, Any]) -> int:
    direct_count = len(node["knowledge_statements"])
    descendant_count = direct_count + sum(
        update_tree_statement_totals(child) for child in node["children"]
    )
    node["direct_statement_count"] = direct_count
    node["descendant_statement_count"] = descendant_count
    node["direct_content_kind_counts"] = dict(
        sorted(
            Counter(
                statement.get("content_kind", "unknown")
                for statement in node["knowledge_statements"]
            ).items()
        )
    )
    return descendant_count


def refresh_domain_metadata(tree: dict[str, Any], domain: dict[str, Any]) -> None:
    for root in tree["roots"]:
        update_tree_statement_totals(root)
    nodes = [node for root in tree["roots"] for node in walk(root)]
    statements = [item for node in nodes for item in node["knowledge_statements"]]
    leaves = [node for node in nodes if not node["children"]]
    base_count = sum(item.get("layer_role") == "base_statement_layer" for item in statements)
    domain["stats"].update(
        {
            "topics": len(nodes),
            "statements": len(statements),
            "official_statements": base_count,
            "intermediate_statements": len(statements) - base_count,
            "leaf_topics": len(leaves),
            "base_statements": base_count,
            "coverage": sum(bool(node["knowledge_statements"]) for node in leaves) / len(leaves) if leaves else 0.0,
            "max_depth": max((node["depth"] for node in nodes), default=0),
            "content_kinds": dict(
                sorted(Counter(item.get("content_kind", "unknown") for item in statements).items())
            ),
        }
    )
    root = tree["roots"][0]
    domain["chapters"] = [
        {
            "topic_id": chapter["topic_id"],
            "display_number": chapter["display_number"],
            "title": chapter["title"],
            "classification_axis": chapter["classification_axis"],
            "subtree_topic_count": sum(1 for _ in walk(chapter)),
            "subtree_statement_count": chapter["descendant_statement_count"],
        }
        for chapter in root["children"]
    ]


def merge_campaign_candidates(
    source: Path,
    trees: dict[str, dict[str, Any]],
    domains: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    candidates, report = collect_campaign_candidates(source)
    topic_index: dict[str, tuple[str, dict[str, Any]]] = {}
    title_index: dict[str, set[str]] = {}
    statement_id_index: dict[str, set[str]] = {}
    for domain_id, tree in trees.items():
        statement_id_index.setdefault(domain_id, set())
        for root in tree["roots"]:
            for node in walk(root):
                topic_id = node["topic_id"]
                if domain_id == LEGACY_DOMAIN_ID and topic_id in topic_index:
                    continue
                topic_index[topic_id] = (domain_id, node)
                title_index[topic_id] = {
                    normalize_text(item.get("statement_title") or item.get("title"))
                    for item in node["knowledge_statements"]
                    if item.get("statement_title") or item.get("title")
                }
                statement_id_index[domain_id].update(
                    str(item.get("id") or item.get("statement_id"))
                    for item in node["knowledge_statements"]
                    if item.get("id") or item.get("statement_id")
                )

    report["added_by_domain"] = Counter()
    report["added_by_stage"] = Counter()
    report["placement_methods"] = Counter()
    report["duplicate_title_count"] = 0
    report["versioned_duplicate_id_count"] = 0
    report["unmapped_count"] = 0

    for entry in candidates:
        placement: tuple[str, str, str] | None = None
        for method, original_hint in entry["placement_hints"]:
            topic_id = original_hint
            while topic_id not in topic_index and "." in topic_id:
                topic_id = topic_id.rsplit(".", 1)[0]
            if topic_id in topic_index:
                placement = (topic_id, method if topic_id == original_hint else f"{method}_ancestor", original_hint)
                break
        if placement is None:
            report["unmapped_count"] += 1
            continue

        topic_id, mapping_method, original_hint = placement
        domain_id, node = topic_index[topic_id]
        record = entry["record"]
        title_key = normalize_text(record.get("statement_title") or record.get("title"))
        if title_key and title_key in title_index[topic_id]:
            report["duplicate_title_count"] += 1
            continue

        normalized = normalize_statement(
            record,
            topic_id,
            "intermediate_result",
            entry["stage"],
            str(entry["campaign_root"] / entry["campaign"]),
            {
                **entry["context"],
                "placement_hint": original_hint,
                "placement_method": mapping_method,
            },
        )
        normalized["mapping_method"] = mapping_method
        normalized["original_topic_id"] = original_hint
        normalized["mapped_topic_ids"] = [topic_id]
        if normalized["id"] in statement_id_index[domain_id]:
            report["versioned_duplicate_id_count"] += 1
            normalized["id"] = "stmt_0809_version_" + sha256(
                repr(
                    (
                        entry["source_item_id"],
                        topic_id,
                        title_key,
                        entry["stage"],
                        normalize_text(normalized.get("statement_latex")),
                    )
                ).encode()
            ).hexdigest()[:20]
        statement_id_index[domain_id].add(normalized["id"])
        node["knowledge_statements"].append(normalized)
        if title_key:
            title_index[topic_id].add(title_key)
        report["added_by_domain"][domain_id] += 1
        report["added_by_stage"][entry["stage"]] += 1
        report["placement_methods"][mapping_method] += 1

    for domain_id, tree in trees.items():
        if domain_id == LEGACY_DOMAIN_ID:
            domains[domain_id]["campaign_snapshot_statement_count"] = 0
            continue
        refresh_domain_metadata(tree, domains[domain_id])
        domains[domain_id]["campaign_snapshot_statement_count"] = report["added_by_domain"][domain_id]

    for key in ("added_by_domain", "added_by_stage", "placement_methods"):
        report[key] = dict(sorted(report[key].items()))
    report["added_statement_count"] = sum(report["added_by_domain"].values())
    report["captured_at"] = datetime.now(timezone.utc).isoformat()
    return report


def convert_part(
    source: Path,
    raw_part: dict[str, Any],
    config: dict[str, str],
    preserved_nodes: dict[str, dict[str, Any]],
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
            "title": (preserved_nodes.get(topic_id) or {}).get("title") or raw.get("title") or topic_id,
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
    tree = {
        "schema_version": "knowledge-classification-tree-v1",
        "generated_at": generated_at,
        "domain_id": config["id"],
        "display_name": config["short_name"],
        "construction": {
            "top_down": "complete A02-A16 directory from the source v57 full-depth snapshot",
            "bottom_up": "previous ReasAtlas content, v58 published statements, topic-complete accepted and deferred records, and validated textbook campaign snapshots",
            "hard_boundary": "source placement and mechanical import do not certify mathematical correctness",
        },
        "roots": [root],
    }
    preserved_report = merge_preserved_statements(tree, preserved_nodes)
    update_tree_counts(root)
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
        "preserved_content_report": preserved_report,
        "chapters": chapter_summaries,
    }
    return tree, domain


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("/root/workspace/lcy/optistacks"))
    parser.add_argument("--site", type=Path, default=Path(__file__).resolve().parents[1] / "site")
    parser.add_argument(
        "--previous-site",
        type=Path,
        help="Optional clean previous snapshot used to preserve existing content",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    site = args.site.resolve()
    previous_site = (args.previous_site or site).resolve()
    manifest_path = site / "data/manifest.json"
    previous_manifest = read_json(previous_site / "data/manifest.json")
    manifest = deepcopy(previous_manifest)

    preserved_nodes, preserved_report = collect_preserved_nodes(
        previous_site,
        previous_manifest,
        excluded_domain_ids={LEGACY_DOMAIN_ID},
    )
    print(
        f"Previous snapshot: {preserved_report['topics']:,} topics, "
        f"{preserved_report['statements']:,} statements preserved"
    )
    trees: dict[str, dict[str, Any]] = {}

    legacy_meta = next(
        (deepcopy(domain) for domain in previous_manifest["domains"] if domain["id"] == LEGACY_DOMAIN_ID),
        None,
    )
    if legacy_meta is None:
        raise RuntimeError(f"Previous snapshot is missing required compatibility domain {LEGACY_DOMAIN_ID}")
    legacy_tree = restore_full_domain(previous_site, legacy_meta["data_url"])
    legacy_meta.pop("loading", None)
    legacy_meta.pop("campaign_snapshot_statement_count", None)

    package = source / "outputs/packages/optistacks_tree_graph_corrected_v27.zip"
    with zipfile.ZipFile(package) as archive:
        source_tree = json.loads(archive.read("snapshot/tree.json"))
    parts = {part["part_id"]: part for part in source_tree["parts"]}

    domains: dict[str, dict[str, Any]] = {}
    for config in PART_DOMAINS:
        tree, domain = convert_part(
            source, parts[config["part_id"]], config, preserved_nodes
        )
        domains[domain["id"]] = domain
        trees[domain["id"]] = tree
        print(
            f"{domain['short_name']}: {domain['stats']['topics']:,} topics, "
            f"{domain['stats']['statements']:,} statements"
        )

    domains[LEGACY_DOMAIN_ID] = legacy_meta
    trees[LEGACY_DOMAIN_ID] = legacy_tree

    campaign_report = merge_campaign_candidates(source, trees, domains)
    for domain_id, tree in trees.items():
        write_json(site / domains[domain_id]["data_url"], tree)
    print(
        f"0809 campaign snapshot: {campaign_report['added_statement_count']:,} statements added, "
        f"{campaign_report['unmapped_count']:,} candidates unmapped"
    )

    manifest["domains"] = [domains[domain_id] for domain_id in DOMAIN_ORDER]
    manifest["built_at"] = datetime.now(timezone.utc).isoformat()
    manifest["preserved_snapshot"] = preserved_report
    manifest["source_campaign_snapshot"] = campaign_report
    manifest["totals"] = {
        "topics": sum(item["stats"]["topics"] for item in manifest["domains"]),
        "statements": sum(item["stats"]["statements"] for item in manifest["domains"]),
    }
    manifest.pop("loading", None)
    write_json(manifest_path, manifest, pretty=True)
    print(f"Total: {manifest['totals']['topics']:,} topics, {manifest['totals']['statements']:,} statements")


if __name__ == "__main__":
    main()
