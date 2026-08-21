#!/usr/bin/env python3
"""Import complete A02-A16 directories and all available statement layers."""

from __future__ import annotations

import argparse
import json
import re
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
        "short_name": "Mixed-Integer Programming",
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
DERIVATIVE_FREE_SHORTCUT_ID = "derivative_free_optimization"
MANIFOLD_SHORTCUT_ID = "manifold_optimization"
SPECIALIZED_DOMAIN_ID = "specialized_continuous_methods"
DISTRIBUTED_ROOT_ID = "A07.C03"
DOMAIN_ORDER = tuple(config["id"] for config in PART_DOMAINS)

SUBJECT_DOMAIN_CONFIG = (
    {
        "id": "continuous_optimization",
        "short_name": "Continuous Optimization",
        "accent": "#315b7d",
        "items": [
            "convex_analysis",
            "variational_analysis",
            "nonlinear_programming",
            "first_order_methods",
            "nonsmooth_optimization",
            DERIVATIVE_FREE_SHORTCUT_ID,
            MANIFOLD_SHORTCUT_ID,
            LEGACY_DOMAIN_ID,
            SPECIALIZED_DOMAIN_ID,
            "convex_programming",
            "linear_programming",
            "conic_optimization",
            "quadratic_optimization",
            "global_optimization",
            "optimization_under_uncertainty",
        ],
    },
    {
        "id": "discrete_optimization",
        "short_name": "Discrete Optimization",
        "accent": "#72558a",
        "items": [
            "integer_mixed_integer_optimization",
            "combinatorial_optimization",
            "constraint_logic_optimization",
        ],
    },
    {
        "id": "numerical_analysis",
        "short_name": "Numerical Analysis",
        "accent": "#3f7589",
        "items": [],
    },
    {
        "id": "numerical_linear_algebra",
        "short_name": "Numerical Linear Algebra",
        "accent": "#8a643b",
        "items": [],
    },
    {
        "id": "algebraic_geometry",
        "short_name": "Algebraic Geometry",
        "accent": "#855a73",
        "items": [],
    },
)

CAMPAIGN_RELATIVE_PATHS = (
    Path("0809_optimize/formal_runs/20260809_full_library_v2"),
    Path("0809_optimize/formal_runs/20260812_full_library_200_supplemental25_v1"),
)
CAMPAIGN_STAGE_PRIORITY = {
    "0809_campaign_build": 1,
    "0809_campaign_reviewed": 2,
    "0809_campaign_published": 3,
}
DEFAULT_DIRECTORY_TREE = Path(
    "/root/workspace/lcy/optistacks/outputs/releases/"
    "v62_framework_sync_candidate/opt_stacks_v62_framework_sync_candidate.json"
)
DEFAULT_CONVERGENCE_LAYERS = (
    Path(
        "/root/workspace/lcy/optistacks/0809_optimize/convergence_runs/"
        "20260818_v1_pilot16/publish/convergence_variant_candidate_layer.json"
    ),
    Path(
        "/root/workspace/lcy/optistacks/0809_optimize/convergence_runs/"
        "20260818_v2_spine_fast/publish_partial_20260819_12shards/"
        "convergence_variant_candidate_layer.json"
    ),
)
DEFAULT_SNAPSHOT_VERSION = "20260819_framework_sync_v1_4"


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


def find_node(tree: dict[str, Any], topic_id: str) -> dict[str, Any] | None:
    for root in tree.get("roots", []):
        for node in walk(root):
            if node.get("topic_id") == topic_id:
                return node
    return None


def statement_preference(record: dict[str, Any]) -> tuple[int, int, float, int, int]:
    evidence = len(record.get("source_refs") or []) + len(record.get("source_witnesses") or [])
    confidence = float(record.get("confidence") or record.get("review_confidence") or 0)
    body_length = len(str(record.get("statement_latex") or "")) + len(
        str(record.get("statement_plain") or "")
    )
    explicit_mapping = int(record.get("mapping_method") == "explicit_node_alias")
    return (int(evidence > 0), evidence, confidence, explicit_mapping, body_length)


def deduplicate_node_statements(node: dict[str, Any]) -> int:
    retained: list[dict[str, Any]] = []
    positions: dict[tuple[str, str], int] = {}
    removed = 0
    for statement in node.get("knowledge_statements", []):
        title = normalize_text(statement.get("statement_title") or statement.get("title"))
        statement_id = str(statement.get("statement_id") or statement.get("id") or "")
        key = ("title", title) if title else ("id", statement_id)
        if not key[1] or key not in positions:
            positions[key] = len(retained)
            retained.append(statement)
            continue
        position = positions[key]
        if statement_preference(statement) > statement_preference(retained[position]):
            retained[position] = statement
        removed += 1
    node["knowledge_statements"] = retained
    return removed


def install_revised_distributed_subtree(
    specialized_tree: dict[str, Any],
    revised_root: dict[str, Any],
    node_redirects: dict[str, str] | None = None,
) -> dict[str, int]:
    """Replace canonical A07.C03 with its reviewed revision without losing statements."""
    node_redirects = node_redirects or {}
    root = specialized_tree["roots"][0]
    old_index = {node["topic_id"]: node for node in walk(root)}
    old_distributed_root = old_index.get(DISTRIBUTED_ROOT_ID)
    if old_distributed_root is None:
        raise RuntimeError(f"{DISTRIBUTED_ROOT_ID} is missing from {SPECIALIZED_DOMAIN_ID}")
    old_distributed_nodes = list(walk(old_distributed_root))
    old_statements = [
        statement
        for node in old_distributed_nodes
        for statement in node.get("knowledge_statements", [])
    ]
    replacement = deepcopy(revised_root)
    revised_index = {node["topic_id"]: node for node in walk(replacement)}
    relocated_statements = 0
    for source_node in list(revised_index.values()):
        retained: list[dict[str, Any]] = []
        for statement in source_node.get("knowledge_statements", []):
            statement_node = str(
                statement.get("node_id")
                or statement.get("source_node_id")
                or statement.get("original_topic_id")
                or ""
            )
            target_id = node_redirects.get(statement_node)
            if not target_id or target_id == source_node["topic_id"]:
                retained.append(statement)
                continue
            target = revised_index.get(target_id)
            if target is None:
                raise RuntimeError(
                    f"Statement redirect target is absent from revised A07.C03: {target_id}"
                )
            relocated = deepcopy(statement)
            relocated["original_source_node_id"] = statement_node
            if "node_id" in relocated:
                relocated["node_id"] = target_id
            if "source_node_id" in relocated:
                relocated["source_node_id"] = target_id
            relocated["original_topic_id"] = statement_node
            relocated["mapped_topic_ids"] = [target_id]
            relocated["mapping_method"] = "explicit_node_alias"
            target.setdefault("knowledge_statements", []).append(relocated)
            relocated_statements += 1
        source_node["knowledge_statements"] = retained
    revised_title_index: dict[str, list[dict[str, Any]]] = {}
    for node in revised_index.values():
        revised_title_index.setdefault(normalize_text(node.get("title")), []).append(node)

    preserved_statements = 0
    duplicate_statements = 0
    unmapped_topics = 0
    for source_node in old_distributed_nodes:
        topic_id = source_node["topic_id"]
        if topic_id == DISTRIBUTED_ROOT_ID:
            continue
        target = revised_index.get(topic_id)
        if target is None:
            same_title = revised_title_index.get(normalize_text(source_node.get("title")), [])
            target = same_title[0] if len(same_title) == 1 else None
        if target is None:
            unmapped_topics += 1
            continue

        existing_titles = {
            normalize_text(statement.get("statement_title") or statement.get("title"))
            for statement in target.get("knowledge_statements", [])
        }
        existing_ids = {
            statement.get("statement_id") or statement.get("id")
            for statement in target.get("knowledge_statements", [])
        }
        for statement in source_node.get("knowledge_statements", []):
            title = normalize_text(statement.get("statement_title") or statement.get("title"))
            statement_id = statement.get("statement_id") or statement.get("id")
            if (title and title in existing_titles) or (statement_id and statement_id in existing_ids):
                duplicate_statements += 1
                continue
            target.setdefault("knowledge_statements", []).append(deepcopy(statement))
            if title:
                existing_titles.add(title)
            if statement_id:
                existing_ids.add(statement_id)
            preserved_statements += 1

    replaced = False
    for index, child in enumerate(root.get("children", [])):
        if child.get("topic_id") == DISTRIBUTED_ROOT_ID:
            root["children"][index] = replacement
            replaced = True
            break
    if not replaced:
        raise RuntimeError(f"{DISTRIBUTED_ROOT_ID} is missing from {SPECIALIZED_DOMAIN_ID}")

    duplicate_statements_removed = sum(
        deduplicate_node_statements(node) for node in revised_index.values()
    )
    revised_statements = [
        statement
        for node in walk(replacement)
        for statement in node.get("knowledge_statements", [])
    ]
    previous_base = sum(
        statement.get("layer_role") == "base_statement_layer" for statement in old_statements
    )
    revised_base = sum(
        statement.get("layer_role") == "base_statement_layer" for statement in revised_statements
    )
    return {
        "previous_topics": len(old_distributed_nodes),
        "revised_topics": sum(1 for _ in walk(replacement)),
        "previous_statements": len(old_statements),
        "revised_statements": len(revised_statements),
        "base_statement_delta": revised_base - previous_base,
        "intermediate_statement_delta": (
            len(revised_statements) - revised_base - (len(old_statements) - previous_base)
        ),
        "preserved_statements_added": preserved_statements,
        "duplicate_statements_skipped": duplicate_statements,
        "unmapped_topics_with_statements": unmapped_topics,
        "alias_relocated_statements": relocated_statements,
        "duplicate_statements_removed": duplicate_statements_removed,
    }


def relocate_aliased_statements(
    root: dict[str, Any], node_redirects: dict[str, str]
) -> dict[str, int]:
    """Canonicalize statement ownership after all preservation/import passes."""
    index = {node["topic_id"]: node for node in walk(root)}
    pending: list[tuple[str, dict[str, Any]]] = []
    relocated = 0
    for node in index.values():
        retained = []
        for statement in node.get("knowledge_statements") or []:
            source_id = str(
                statement.get("node_id")
                or statement.get("source_node_id")
                or statement.get("original_topic_id")
                or ""
            )
            target_id = node_redirects.get(source_id)
            if not target_id or target_id == node["topic_id"]:
                retained.append(statement)
                continue
            if target_id not in index:
                raise RuntimeError(f"Missing statement alias target: {source_id} -> {target_id}")
            updated = deepcopy(statement)
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
        index[target_id].setdefault("knowledge_statements", []).append(statement)
    duplicates_removed = sum(deduplicate_node_statements(node) for node in index.values())
    return {"relocated": relocated, "duplicates_removed": duplicates_removed}


def update_revision_import_report(domain: dict[str, Any], report: dict[str, int]) -> None:
    intermediate_report = domain.get("intermediate_result_report")
    if not intermediate_report:
        return
    base_delta = report["base_statement_delta"]
    intermediate_delta = report["intermediate_statement_delta"]
    intermediate_report["official_statement_count"] += base_delta
    intermediate_report["added_intermediate_count"] += intermediate_delta
    intermediate_report["total_statement_count"] += base_delta + intermediate_delta
    intermediate_report.setdefault("sources", {})[
        "distributed_revision_overlay_net"
    ] = intermediate_delta


def distributed_route_compatibility(
    source: Path, revised_root: dict[str, Any]
) -> dict[str, Any]:
    """Build audited redirects for links into the former standalone domain."""
    mapping_path = source / "distributed/distributed_optimization_node_mapping.json"
    mapping = read_json(mapping_path)
    revised_ids = {str(node["topic_id"]) for node in walk(revised_root)}
    redirects: dict[str, str] = {}
    rows = list(mapping.get("primary_source_mapping") or [])
    rows.extend(mapping.get("primary_cross_reference_mapping") or [])
    rows.extend(mapping.get("external_cross_reference_mapping") or [])
    for row in rows:
        source_id = str(row.get("source_node_id") or "")
        target_id = str(
            row.get("primary_target_node_id")
            or row.get("target_node_id")
            or ((row.get("target_node_ids") or [""])[0])
        )
        if not source_id or not target_id or source_id == target_id:
            continue
        if target_id not in revised_ids:
            raise RuntimeError(
                "Distributed redirect target is absent from revised A07.C03: "
                f"{source_id} -> {target_id}"
            )
        redirects[source_id] = target_id
    return {
        "legacy_domain_id": LEGACY_DOMAIN_ID,
        "domain_id": SPECIALIZED_DOMAIN_ID,
        "default_node_id": DISTRIBUTED_ROOT_ID,
        "node_redirects": dict(sorted(redirects.items())),
        "mapping_path": str(mapping_path.relative_to(source)),
        "mapping_sha256": sha256(mapping_path.read_bytes()).hexdigest(),
    }


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


def is_regenerated_statement(statement: dict[str, Any]) -> bool:
    stage = str((statement.get("intermediate_metadata") or {}).get("stage") or "")
    return stage.startswith("0809_campaign_") or stage in {
        "convergence_fast_candidate_unreviewed",
        "convergence_partial_fast_candidate_unreviewed",
    }


def strip_campaign_statements(tree: dict[str, Any]) -> None:
    for root in tree.get("roots", []):
        for node in walk(root):
            node["knowledge_statements"] = [
                statement
                for statement in node.get("knowledge_statements", [])
                if not is_regenerated_statement(statement)
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
        "excluded_campaign_statements": 0,
        "excluded_convergence_candidates": 0,
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
                statements = []
                for statement in node.get("knowledge_statements", []):
                    stage = str((statement.get("intermediate_metadata") or {}).get("stage") or "")
                    if stage.startswith("0809_campaign_"):
                        report["excluded_campaign_statements"] += 1
                        continue
                    if stage in {
                        "convergence_fast_candidate_unreviewed",
                        "convergence_partial_fast_candidate_unreviewed",
                    }:
                        report["excluded_convergence_candidates"] += 1
                        continue
                    statements.append(deepcopy(statement))
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
            if old.get("title") and not node.get("framework_adjustment"):
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
            "new_node_candidate": item.get("new_node_candidate") or {},
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
    node_redirects: dict[str, str] | None = None,
) -> dict[str, Any]:
    node_redirects = node_redirects or {}
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

    proposal_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    proposal_titles: dict[tuple[str, str], str] = {}
    proposal_scopes: dict[tuple[str, str], list[str]] = {}
    for entry in candidates:
        if entry["stage"] not in {"0809_campaign_reviewed", "0809_campaign_published"}:
            continue
        proposal = entry["context"].get("new_node_candidate") or {}
        title = str(proposal.get("title") or proposal.get("proposed_title") or "").strip()
        if not title:
            continue
        parent_ids = proposal.get("parent_candidate_ids") or []
        if isinstance(parent_ids, str):
            parent_ids = [parent_ids]
        parent_id = ""
        for candidate_parent in parent_ids:
            candidate_parent = str(candidate_parent or "").strip()
            resolved_parent = node_redirects.get(candidate_parent, candidate_parent)
            if resolved_parent in topic_index:
                parent_id = resolved_parent
                break
        title_key = normalize_text(title)
        if not parent_id or not title_key:
            continue
        group_key = (parent_id, title_key)
        proposal_groups.setdefault(group_key, []).append(entry)
        proposal_titles.setdefault(group_key, title)
        scope = str(proposal.get("scope_note") or "").strip()
        if scope:
            proposal_scopes.setdefault(group_key, []).append(scope)

    direct_child_titles: dict[str, dict[str, list[str]]] = {}
    for topic_id, (_, node) in topic_index.items():
        children: dict[str, list[str]] = {}
        for child in node.get("children") or []:
            key = normalize_text(child.get("title"))
            if key:
                children.setdefault(key, []).append(str(child["topic_id"]))
        direct_child_titles[topic_id] = children

    proposal_destinations: dict[str, tuple[str, str]] = {}
    materialized_nodes: list[dict[str, Any]] = []
    exact_sibling_group_count = 0
    exact_sibling_candidate_count = 0
    cross_source_group_count = 0
    cross_source_candidate_count = 0
    for group_key in sorted(proposal_groups):
        parent_id, title_key = group_key
        entries = proposal_groups[group_key]
        matching_children = direct_child_titles.get(parent_id, {}).get(title_key) or []
        if len(matching_children) == 1:
            destination_id = matching_children[0]
            method = "campaign_exact_sibling_title"
            exact_sibling_group_count += 1
            exact_sibling_candidate_count += len(entries)
        else:
            source_campaigns = sorted({entry["campaign"] for entry in entries})
            if matching_children or len(source_campaigns) < 2:
                continue
            parent_domain_id, parent = topic_index[parent_id]
            destination_id = parent_id + ".WEB" + sha256(
                f"{parent_id}\n{title_key}".encode()
            ).hexdigest()[:12].upper()
            if destination_id in topic_index:
                raise RuntimeError(f"Duplicate web candidate topic id: {destination_id}")
            scopes = proposal_scopes.get(group_key) or []
            scope_note = Counter(scopes).most_common(1)[0][0] if scopes else ""
            witnesses = []
            seen_witnesses: set[tuple[str, str]] = set()
            for entry in entries:
                evidence = entry["record"].get("source_evidence") or {}
                witness_key = (
                    str(entry["campaign"]),
                    str(evidence.get("locator") or evidence.get("source_path") or ""),
                )
                if witness_key in seen_witnesses:
                    continue
                seen_witnesses.add(witness_key)
                witnesses.append(
                    {
                        "source": entry["campaign"],
                        "locator": witness_key[1],
                        "evidence_role": "independent_textbook_candidate_container_support",
                    }
                )
            destination = {
                "topic_id": destination_id,
                "display_number": "",
                "title": proposal_titles[group_key],
                "topic_type": "topic",
                "depth": int(parent.get("depth") or 0) + 1,
                "classification_axis": "textbook_candidate_topic",
                "top_down_role": scope_note,
                "knowledge_status": "statement_attached",
                "top_down_textbook_witnesses": witnesses,
                "knowledge_statements": [],
                "children": [],
                "web_candidate_container": {
                    "status": "cross_source_supported",
                    "parent_topic_id": parent_id,
                    "normalized_title": title_key,
                    "independent_campaign_count": len(source_campaigns),
                    "source_campaigns": source_campaigns,
                    "source_item_ids": sorted(entry["source_item_id"] for entry in entries),
                },
            }
            parent.setdefault("children", []).append(destination)
            topic_index[destination_id] = (parent_domain_id, destination)
            title_index[destination_id] = set()
            direct_child_titles.setdefault(parent_id, {}).setdefault(title_key, []).append(
                destination_id
            )
            materialized_nodes.append(
                {
                    "topic_id": destination_id,
                    "parent_topic_id": parent_id,
                    "title": proposal_titles[group_key],
                    "domain_id": parent_domain_id,
                    "independent_campaign_count": len(source_campaigns),
                    "source_campaigns": source_campaigns,
                    "candidate_count": len(entries),
                }
            )
            method = "campaign_cross_source_candidate_container"
            cross_source_group_count += 1
            cross_source_candidate_count += len(entries)
        for entry in entries:
            proposal_destinations[entry["source_item_id"]] = (destination_id, method)

    global_topic_titles: dict[str, list[str]] = {}
    for topic_id, (_, node) in topic_index.items():
        title_key = normalize_text(node.get("title"))
        if title_key:
            global_topic_titles.setdefault(title_key, []).append(topic_id)
    unique_same_part_group_keys: set[tuple[str, str]] = set()
    unique_same_part_candidate_count = 0
    for group_key in sorted(proposal_groups):
        parent_id, title_key = group_key
        entries = proposal_groups[group_key]
        matches = global_topic_titles.get(title_key) or []
        if len(matches) != 1:
            continue
        destination_id = matches[0]
        if destination_id.split(".", 1)[0] != parent_id.split(".", 1)[0]:
            continue
        newly_mapped = 0
        for entry in entries:
            if entry["source_item_id"] in proposal_destinations:
                continue
            proposal_destinations[entry["source_item_id"]] = (
                destination_id,
                "campaign_unique_same_part_title",
            )
            newly_mapped += 1
        if newly_mapped:
            unique_same_part_group_keys.add(group_key)
            unique_same_part_candidate_count += newly_mapped

    report["added_by_domain"] = Counter()
    report["added_by_stage"] = Counter()
    report["placement_methods"] = Counter()
    report["duplicate_title_count"] = 0
    report["versioned_duplicate_id_count"] = 0
    report["unmapped_count"] = 0
    report["quarantined_by_reason"] = Counter()
    report["quarantined_by_stage"] = Counter()
    report["quarantined_by_method"] = Counter()
    report["candidate_container_materialization"] = {
        "policy": (
            "Reviewed or published new-topic proposals are mounted only when their title "
            "matches one direct existing child exactly, or when at least two source campaigns "
            "independently propose the same normalized title under the same live parent."
        ),
        "eligible_proposal_group_count": len(proposal_groups),
        "eligible_proposal_candidate_count": sum(len(rows) for rows in proposal_groups.values()),
        "exact_existing_sibling_group_count": exact_sibling_group_count,
        "exact_existing_sibling_candidate_count": exact_sibling_candidate_count,
        "cross_source_new_group_count": cross_source_group_count,
        "cross_source_new_candidate_count": cross_source_candidate_count,
        "unique_same_part_title_group_count": len(unique_same_part_group_keys),
        "unique_same_part_title_candidate_count": unique_same_part_candidate_count,
        "materialized_node_count": len(materialized_nodes),
        "materialized_nodes": materialized_nodes,
    }
    quarantined_records: list[dict[str, Any]] = []

    def quarantine(
        entry: dict[str, Any],
        reason: str,
        *,
        topic_id: str = "",
        mapping_method: str = "",
        original_hint: str = "",
    ) -> None:
        report["quarantined_by_reason"][reason] += 1
        report["quarantined_by_stage"][entry["stage"]] += 1
        report["quarantined_by_method"][mapping_method or "unmapped"] += 1
        record = entry["record"]
        quarantined_records.append(
            {
                "source_item_id": entry["source_item_id"],
                "campaign": entry["campaign"],
                "stage": entry["stage"],
                "reason": reason,
                "mapping_method": mapping_method,
                "attempted_topic_id": topic_id,
                "original_placement_hint": original_hint,
                "statement_title": record.get("statement_title") or record.get("title") or "",
                "placement_hints": entry["placement_hints"],
                "review_confidence": record.get("review_confidence"),
                "new_node_candidate": entry["context"].get("new_node_candidate") or {},
                "directory_assessment": entry["context"].get("directory_assessment") or {},
            }
        )

    for entry in candidates:
        placement: tuple[str, str, str] | None = None
        proposal_destination = proposal_destinations.get(entry["source_item_id"])
        if proposal_destination is not None:
            topic_id, method = proposal_destination
            placement = (topic_id, method, topic_id)
        else:
            for method, original_hint in entry["placement_hints"]:
                topic_id = node_redirects.get(original_hint, original_hint)
                if topic_id != original_hint:
                    method = "explicit_node_alias"
                while topic_id not in topic_index and "." in topic_id:
                    topic_id = topic_id.rsplit(".", 1)[0]
                if topic_id in topic_index:
                    placement = (topic_id, method if topic_id == original_hint else f"{method}_ancestor", original_hint)
                    break
        if placement is None:
            report["unmapped_count"] += 1
            quarantine(entry, "no_live_target")
            continue

        topic_id, mapping_method, original_hint = placement
        stage = entry["stage"]
        quarantine_reason = ""
        if stage == "0809_campaign_build":
            quarantine_reason = "builder_only_not_independently_reviewed"
        elif "ancestor" in mapping_method or mapping_method == "campaign_parent_fallback":
            quarantine_reason = "missing_or_unresolved_specific_container"
        elif mapping_method == "campaign_single_affected_node":
            quarantine_reason = "affected_node_is_not_a_confirmed_primary_owner"
        elif not (
            (stage == "0809_campaign_published" and mapping_method in {"campaign_existing_node", "explicit_node_alias"})
            or (
                stage == "0809_campaign_reviewed"
                and mapping_method in {
                    "campaign_existing_node",
                    "campaign_preferred_home",
                    "explicit_node_alias",
                    "campaign_exact_sibling_title",
                    "campaign_cross_source_candidate_container",
                    "campaign_unique_same_part_title",
                }
            )
            or (
                stage == "0809_campaign_published"
                and mapping_method in {
                    "campaign_exact_sibling_title",
                    "campaign_cross_source_candidate_container",
                    "campaign_unique_same_part_title",
                }
            )
        ):
            quarantine_reason = "placement_not_in_public_allowlist"
        if quarantine_reason:
            quarantine(
                entry,
                quarantine_reason,
                topic_id=topic_id,
                mapping_method=mapping_method,
                original_hint=original_hint,
            )
            continue

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

    for key in (
        "added_by_domain",
        "added_by_stage",
        "placement_methods",
        "quarantined_by_reason",
        "quarantined_by_stage",
        "quarantined_by_method",
    ):
        report[key] = dict(sorted(report[key].items()))
    report["added_statement_count"] = sum(report["added_by_domain"].values())
    report["quarantined_count"] = len(quarantined_records)
    report["_quarantined_records"] = quarantined_records
    report["captured_at"] = datetime.now(timezone.utc).isoformat()
    return report


def merge_convergence_candidates(
    layer_path: Path,
    trees: dict[str, dict[str, Any]],
    domains: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Attach the completed core convergence layer as unreviewed enrichment."""
    layer = read_json(layer_path)
    publication_status = str(layer.get("publication_status") or "")
    allowed_statuses = {
        "SHADOW_FAST_CANDIDATE_UNREVIEWED",
        "SHADOW_PARTIAL_FAST_CANDIDATE_UNREVIEWED",
    }
    if publication_status not in allowed_statuses:
        raise RuntimeError("Convergence layer is not the expected fast shadow candidate")
    if layer.get("canonical_tree_mutated") is not False:
        raise RuntimeError("Convergence candidate unexpectedly claims a canonical mutation")
    records = layer.get("records") or []
    if int(layer.get("record_count") or -1) != len(records):
        raise RuntimeError("Convergence candidate record count is inconsistent")

    topic_index: dict[str, tuple[str, dict[str, Any]]] = {}
    title_index: dict[str, set[str]] = {}
    statement_ids: set[str] = set()
    for domain_id, tree in trees.items():
        for root in tree["roots"]:
            for node in walk(root):
                topic_index[node["topic_id"]] = (domain_id, node)
                title_index[node["topic_id"]] = {
                    normalize_text(item.get("statement_title") or item.get("title"))
                    for item in node.get("knowledge_statements") or []
                }
                statement_ids.update(
                    str(item.get("id") or item.get("statement_id"))
                    for item in node.get("knowledge_statements") or []
                    if item.get("id") or item.get("statement_id")
                )

    report: dict[str, Any] = {
        "schema_version": "web-convergence-snapshot-report-v1",
        "source_path": str(layer_path),
        "source_publication_status": publication_status,
        "partial_run": bool(layer.get("partial_run")),
        "planned_shard_count": layer.get("planned_shard_count"),
        "passed_shard_count": layer.get("passed_shard_count"),
        "failed_shard_count": layer.get("failed_shard_count"),
        "unstarted_shard_count": layer.get("unstarted_shard_count"),
        "source_record_count": len(records),
        "added_statement_count": 0,
        "duplicate_title_count": 0,
        "duplicate_id_count": 0,
        "unmapped_count": 0,
        "ancestor_mapped_count": 0,
        "added_by_domain": Counter(),
        "review_status": "candidate_unreviewed",
    }
    for record in records:
        original_topic_id = str(record.get("algorithm_topic_id") or "")
        topic_id = original_topic_id
        while topic_id not in topic_index and "." in topic_id:
            topic_id = topic_id.rsplit(".", 1)[0]
        if topic_id not in topic_index:
            report["unmapped_count"] += 1
            continue
        if topic_id != original_topic_id:
            report["ancestor_mapped_count"] += 1
        domain_id, node = topic_index[topic_id]
        title = str(record.get("statement_title") or record.get("variant_id") or "Convergence variant")
        title_key = normalize_text(title)
        if title_key and title_key in title_index[topic_id]:
            report["duplicate_title_count"] += 1
            continue
        statement_id = "stmt_" + str(record["variant_id"]).lower().replace("-", "_")
        if statement_id in statement_ids:
            report["duplicate_id_count"] += 1
            continue
        conclusion = deepcopy(record.get("conclusion") or {})
        boundary_notes = list(record.get("boundary_notes") or [])
        is_boundary = bool(boundary_notes) and any(
            token in " ".join(boundary_notes).lower()
            for token in ("failure", "not guaranteed", "counterexample", "diverg")
        )
        has_rate = bool(
            conclusion.get("rate_class") not in {None, "", "none"}
            or conclusion.get("nonasymptotic_bound_latex")
            or conclusion.get("epsilon_complexity_latex")
        )
        normalized = {
            "id": statement_id,
            "statement_id": statement_id,
            "node_type": "knowledge_statement",
            "title": title,
            "statement_title": title,
            "content_kind": "failure_boundary" if is_boundary else "complexity_bound" if has_rate else "theorem",
            "statement_latex": str(record.get("statement_latex") or conclusion.get("conclusion_latex") or ""),
            "statement_plain": str(record.get("statement_plain") or ""),
            "assumptions_latex": list(record.get("assumptions_latex") or []),
            "conclusion_latex": str(conclusion.get("conclusion_latex") or ""),
            "conclusion": conclusion,
            "variant_dimensions": deepcopy(record.get("variant_dimensions") or {}),
            "equivalent_formulations_latex": list(record.get("equivalent_formulations_latex") or []),
            "boundary_notes": boundary_notes,
            "relations": deepcopy(record.get("relations") or []),
            "source_refs": deepcopy(record.get("source_refs") or []),
            "source_witnesses": deepcopy(record.get("source_refs") or []),
            "review_status": "candidate",
            "review_flags": list(record.get("review_flags") or []),
            "proof_included": False,
            "original_topic_id": original_topic_id,
            "mapped_topic_ids": [topic_id],
            "mapping_method": "exact_topic_id" if topic_id == original_topic_id else "nearest_canonical_ancestor",
            "layer_role": "intermediate_result",
            "intermediate_metadata": {
                "stage": (
                    "convergence_partial_fast_candidate_unreviewed"
                    if layer.get("partial_run")
                    else "convergence_fast_candidate_unreviewed"
                ),
                "source_path": str(layer_path),
                "source_publication_status": publication_status,
                "partial_run": bool(layer.get("partial_run")),
                "variant_id": record.get("variant_id"),
                "theorem_family_id": record.get("theorem_family_id"),
            },
        }
        node.setdefault("knowledge_statements", []).append(normalized)
        statement_ids.add(statement_id)
        if title_key:
            title_index[topic_id].add(title_key)
        report["added_statement_count"] += 1
        report["added_by_domain"][domain_id] += 1

    for domain_id, tree in trees.items():
        refresh_domain_metadata(tree, domains[domain_id])
        domains[domain_id]["convergence_candidate_statement_count"] = (
            int(domains[domain_id].get("convergence_candidate_statement_count") or 0)
            + report["added_by_domain"][domain_id]
        )
    report["added_by_domain"] = dict(sorted(report["added_by_domain"].items()))
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
        preserved_title = (preserved_nodes.get(topic_id) or {}).get("title")
        title = raw.get("title") if raw.get("structural_adjustment") else preserved_title or raw.get("title")
        node = {
            "topic_id": topic_id,
            "display_number": number,
            "title": title or topic_id,
            "topic_type": raw.get("node_type") or raw.get("navigation_kind") or "topic",
            "depth": depth,
            "classification_axis": raw.get("navigation_kind") or "pedagogical dependency",
            "top_down_role": raw.get("role") or raw.get("scope_note") or "",
            "knowledge_status": "statement_attached" if statements else "structural_container_with_descendant_knowledge" if children else "structural_leaf",
            "top_down_textbook_witnesses": source_witnesses(raw.get("source_refs", [])),
            "knowledge_statements": statements,
            "children": children,
        }
        if raw.get("structural_adjustment"):
            node["framework_adjustment"] = deepcopy(raw["structural_adjustment"])
        return node

    root_number = re.sub(r"\D", "", config["part_id"]).lstrip("0") or "0"
    root = convert(raw_part, config["part_id"], root_number, 0)
    tree = {
        "schema_version": "knowledge-classification-tree-v1",
        "generated_at": generated_at,
        "domain_id": config["id"],
        "display_name": config["short_name"],
        "construction": {
            "top_down": "complete A02-A16 directory from the validated v62 framework-sync candidate",
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
    parser.add_argument("--directory-tree", type=Path, default=DEFAULT_DIRECTORY_TREE)
    parser.add_argument(
        "--convergence-layer",
        type=Path,
        action="append",
        help="Repeat to install several convergence candidate layers; defaults to the stable core and validated partial broad layer.",
    )
    parser.add_argument("--snapshot-version", default=DEFAULT_SNAPSHOT_VERSION)
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
    if legacy_meta is not None:
        legacy_tree = restore_full_domain(previous_site, legacy_meta["data_url"])
        revised_distributed_root = deepcopy(legacy_tree["roots"][0])
    else:
        previous_specialized_meta = next(
            (
                domain
                for domain in previous_manifest["domains"]
                if domain["id"] == SPECIALIZED_DOMAIN_ID
            ),
            None,
        )
        if previous_specialized_meta is None:
            raise RuntimeError("Previous snapshot has no revised distributed optimization subtree")
        previous_specialized_tree = restore_full_domain(
            previous_site, previous_specialized_meta["data_url"]
        )
        revised_distributed_root = find_node(previous_specialized_tree, DISTRIBUTED_ROOT_ID)
        if revised_distributed_root is None:
            raise RuntimeError("Previous snapshot is missing revised A07.C03")
        revised_distributed_root = deepcopy(revised_distributed_root)
    strip_campaign_statements({"roots": [revised_distributed_root]})

    directory_tree = args.directory_tree.resolve()
    source_tree = read_json(directory_tree)
    if source_tree.get("tree_id") != "opt_stacks_v62_framework_sync_candidate":
        raise RuntimeError(f"Unexpected directory tree: {source_tree.get('tree_id')}")
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

    route_compatibility = distributed_route_compatibility(
        source, revised_distributed_root
    )
    revision_report = install_revised_distributed_subtree(
        trees[SPECIALIZED_DOMAIN_ID],
        revised_distributed_root,
        route_compatibility["node_redirects"],
    )
    domains[SPECIALIZED_DOMAIN_ID]["distributed_revision_merge_report"] = revision_report
    update_revision_import_report(domains[SPECIALIZED_DOMAIN_ID], revision_report)
    domains[SPECIALIZED_DOMAIN_ID]["publication_status"] = (
        "source_snapshot_with_revised_distributed_overlay_and_unverified_intermediate_results_exposed"
    )
    refresh_domain_metadata(trees[SPECIALIZED_DOMAIN_ID], domains[SPECIALIZED_DOMAIN_ID])
    print(
        "Distributed Optimization revision: "
        f"{revision_report['revised_topics']:,} topics, "
        f"{revision_report['preserved_statements_added']:,} prior statements added"
    )

    campaign_report = merge_campaign_candidates(
        source, trees, domains, route_compatibility["node_redirects"]
    )
    quarantined_campaign_records = campaign_report.pop("_quarantined_records")
    quarantine_data_url = "data/campaign_placement_quarantine.json"
    write_json(
        site / quarantine_data_url,
        {
            "schema_version": "web-campaign-placement-quarantine-v2",
            "snapshot_version": args.snapshot_version,
            "policy": (
                "Public nodes admit exact reviewed placements, exact direct-child title matches, "
                "and cross-source-supported candidate containers. Broad parent fallbacks, "
                "single affected nodes, builder-only rows, and unresolved targets remain quarantined."
            ),
            "record_count": len(quarantined_campaign_records),
            "records": quarantined_campaign_records,
        },
    )
    campaign_report["quarantine_data_url"] = quarantine_data_url
    convergence_layers = args.convergence_layer or list(DEFAULT_CONVERGENCE_LAYERS)
    convergence_layer_reports = [
        merge_convergence_candidates(layer.resolve(), trees, domains)
        for layer in convergence_layers
    ]
    convergence_report = {
        "schema_version": "web-convergence-snapshot-report-v2",
        "layer_count": len(convergence_layer_reports),
        "partial_layer_count": sum(bool(row.get("partial_run")) for row in convergence_layer_reports),
        "source_record_count": sum(int(row["source_record_count"]) for row in convergence_layer_reports),
        "added_statement_count": sum(int(row["added_statement_count"]) for row in convergence_layer_reports),
        "duplicate_title_count": sum(int(row["duplicate_title_count"]) for row in convergence_layer_reports),
        "duplicate_id_count": sum(int(row["duplicate_id_count"]) for row in convergence_layer_reports),
        "unmapped_count": sum(int(row["unmapped_count"]) for row in convergence_layer_reports),
        "ancestor_mapped_count": sum(int(row["ancestor_mapped_count"]) for row in convergence_layer_reports),
        "review_status": "candidate_unreviewed",
        "layers": convergence_layer_reports,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    alias_repair_report = relocate_aliased_statements(
        trees[SPECIALIZED_DOMAIN_ID]["roots"][0],
        route_compatibility["node_redirects"],
    )
    refresh_domain_metadata(trees[SPECIALIZED_DOMAIN_ID], domains[SPECIALIZED_DOMAIN_ID])
    for domain_id, tree in trees.items():
        write_json(site / domains[domain_id]["data_url"], tree)
    print(
        f"0809 campaign snapshot: {campaign_report['added_statement_count']:,} statements added, "
        f"{campaign_report['unmapped_count']:,} candidates unmapped"
    )
    print(
        f"Core convergence snapshot: {convergence_report['added_statement_count']:,} statements added, "
        f"{convergence_report['unmapped_count']:,} candidates unmapped"
    )

    manifest["domains"] = [domains[domain_id] for domain_id in DOMAIN_ORDER]
    manifest["snapshot_version"] = args.snapshot_version
    manifest["built_at"] = datetime.now(timezone.utc).isoformat()
    manifest["preserved_snapshot"] = preserved_report
    manifest["source_campaign_snapshot"] = campaign_report
    manifest["convergence_candidate_snapshot"] = convergence_report
    manifest["directory_snapshot"] = {
        "tree_id": source_tree.get("tree_id"),
        "path": str(directory_tree),
        "status": source_tree.get("status"),
        "canonical_tree_mutated": source_tree.get("canonical_tree_mutated"),
        "framework_sync": source_tree.get("framework_sync"),
    }
    manifest["distributed_revision"] = {
        "status": "installed_at_A07.C03",
        **revision_report,
        "post_import_alias_repair": alias_repair_report,
    }
    shortcut_specs = (
        (DERIVATIVE_FREE_SHORTCUT_ID, "Derivative-Free Optimization", "#b2693f", "A07.C01"),
        (MANIFOLD_SHORTCUT_ID, "Manifold Optimization", "#26756d", "A07.C02"),
        (LEGACY_DOMAIN_ID, "Distributed Optimization", "#6d5bd0", DISTRIBUTED_ROOT_ID),
    )
    manifest["legacy_domain_routes"] = {
        shortcut_id: {
            "domain_id": SPECIALIZED_DOMAIN_ID,
            "default_node_id": root_id,
        }
        for shortcut_id, _, _, root_id in shortcut_specs
    }
    specialized_chapters = {
        chapter["topic_id"]: chapter
        for chapter in domains[SPECIALIZED_DOMAIN_ID]["chapters"]
    }
    manifest["navigation_shortcuts"] = []
    for offset, (shortcut_id, short_name, accent, root_id) in enumerate(shortcut_specs, start=6):
        chapter = specialized_chapters[root_id]
        root_node = find_node(trees[SPECIALIZED_DOMAIN_ID], root_id)
        if root_node is None:
            raise RuntimeError(f"Specialized-method shortcut root is missing: {root_id}")
        manifest["navigation_shortcuts"].append(
            {
                "id": shortcut_id,
                "short_name": short_name,
                "accent": accent,
                "position": offset,
                "domain_id": SPECIALIZED_DOMAIN_ID,
                "default_node_id": root_id,
                "stats": {
                    "topics": chapter["subtree_topic_count"],
                    "statements": chapter["subtree_statement_count"],
                    "chapters": len(root_node.get("children", [])),
                },
            }
        )
    domain_lookup = {domain["id"]: domain for domain in manifest["domains"]}
    shortcut_lookup = {
        shortcut["id"]: shortcut for shortcut in manifest["navigation_shortcuts"]
    }
    manifest["subject_domains"] = []
    for config in SUBJECT_DOMAIN_CONFIG:
        resolved_domain_ids = {
            shortcut_lookup[item]["domain_id"] if item in shortcut_lookup else item
            for item in config["items"]
        }
        manifest["subject_domains"].append(
            {
                **config,
                "stats": {
                    "collections": len(config["items"]),
                    "topics": sum(
                        domain_lookup[domain_id]["stats"]["topics"]
                        for domain_id in resolved_domain_ids
                    ),
                    "statements": sum(
                        domain_lookup[domain_id]["stats"]["statements"]
                        for domain_id in resolved_domain_ids
                    ),
                },
            }
        )
    manifest["node_redirects"] = {
        SPECIALIZED_DOMAIN_ID: route_compatibility["node_redirects"]
    }
    manifest["distributed_route_compatibility"] = route_compatibility
    manifest["totals"] = {
        "topics": sum(item["stats"]["topics"] for item in manifest["domains"]),
        "statements": sum(item["stats"]["statements"] for item in manifest["domains"]),
    }
    manifest.pop("loading", None)
    write_json(manifest_path, manifest, pretty=True)
    print(f"Total: {manifest['totals']['topics']:,} topics, {manifest['totals']['statements']:,} statements")


if __name__ == "__main__":
    main()
