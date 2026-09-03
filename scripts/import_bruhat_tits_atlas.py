#!/usr/bin/env python3
"""Publish the reviewed Bruhat--Tits textbook overlay as a compact web payload."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "optistacks"
SOURCE_LABELS = {
    "bruhat-tits-1972-groupes-reductifs-I-仅译文": "Bruhat–Tits I (1972)",
    "bruhat_tits_II_1984-仅译文": "Bruhat–Tits II (1984)",
    "kaletha-prasad-bruhat-tits": "Kaletha–Prasad",
}


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def normalized(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def stable_id(*values: object) -> str:
    material = "\x1f".join(str(value or "") for value in values)
    return sha256(material.encode()).hexdigest()[:12].upper()


def public_source(evidence: dict[str, Any] | None) -> dict[str, Any]:
    evidence = evidence or {}
    raw_path = str(evidence.get("source_path") or "")
    relative = raw_path.split("/math-building/", 1)[-1] if "/math-building/" in raw_path else ""
    path_parts = [part for part in relative.split("/") if part]
    collection_id = path_parts[0] if path_parts else ""
    chapter = path_parts[1] if len(path_parts) > 2 else ""
    document_quality = evidence.get("source_document_quality") or {}
    quality = document_quality.get("quality") or {}
    source_refs = evidence.get("source_refs") or {}
    markdown = evidence.get("markdown_evidence") or {}
    markdown_records = []
    for name, record in sorted(markdown.items()):
        if not isinstance(record, dict):
            continue
        markdown_records.append(
            {
                "name": name,
                "role": record.get("role") or "",
                "match_type": record.get("match_type") or "",
                "line_start": record.get("line_start"),
                "line_end": record.get("line_end"),
            }
        )
    return {
        "collection_id": collection_id,
        "collection": SOURCE_LABELS.get(collection_id, collection_id.replace("_", " ")),
        "chapter": chapter,
        "document": (document_quality.get("source") or {}).get("filename") or "",
        "locator": evidence.get("locator") or "",
        "environment": evidence.get("source_environment") or "",
        "raw_id": evidence.get("raw_id") or "",
        "position_confidence": source_refs.get("position_confidence") or "",
        "pages": source_refs.get("pages") or [],
        "span_ids": source_refs.get("span_ids") or [],
        "quality_status": document_quality.get("quality_status") or quality.get("quality_status") or "unknown",
        "quality_issue_count": document_quality.get("quality_issue_count") or 0,
        "source_audit_modified": bool((evidence.get("source_audit") or {}).get("modified")),
        "markdown": markdown_records,
    }


def compact_assessment(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    return {
        "status": value.get("status") or "",
        "recommendation": value.get("recommendation") or "",
        "preferred_home_node_id": value.get("preferred_home_node_id") or "",
        "affected_existing_node_ids": value.get("affected_existing_node_ids") or [],
        "rationale": value.get("rationale") or "",
    }


def compact_statement(
    record: dict[str, Any],
    *,
    placement: str,
    evidence: dict[str, Any] | None = None,
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_item_id = str(record.get("source_item_id") or "")
    return {
        "id": source_item_id,
        "title": record.get("statement_title") or "Untitled source item",
        "content_kind": record.get("content_kind") or "other",
        "statement_plain": record.get("statement_plain") or "",
        "statement_latex": record.get("statement_latex") or "",
        "assumptions_latex": record.get("assumptions_latex") or [],
        "conclusion_latex": record.get("conclusion_latex") or "",
        "scope_note": record.get("scope_note") or "",
        "review_confidence": record.get("review_confidence"),
        "review_flags": record.get("review_flags") or [],
        "placement": placement,
        "source": public_source(evidence if evidence is not None else record.get("source_evidence")),
        "directory_assessment": compact_assessment(assessment),
    }


def display_number(node_id: str, node_type: str) -> str:
    if node_type == "part":
        return "BT"
    values = re.findall(r"(?:C|S|K)(\d+)", node_id)
    return ".".join(str(int(value)) for value in values)


def child_sort_key(node: dict[str, Any]) -> tuple[int, tuple[int, ...], str]:
    """Keep the immutable seed order numerical and append proposals alphabetically."""
    if node.get("status") != "proposed":
        numbers = tuple(
            int(value) for value in re.findall(r"\d+", str(node.get("display_number") or ""))
        )
        return (0, numbers, normalized(node.get("title")))
    return (1, (), normalized(node.get("title")))


def convert_seed_node(raw: dict[str, Any]) -> dict[str, Any]:
    node_type = str(raw.get("node_type") or "topic")
    node_id = str(raw.get("node_id") or raw.get("part_id") or "")
    return {
        "id": node_id,
        "display_number": display_number(node_id, node_type),
        "title": raw.get("title") or node_id,
        "title_zh": raw.get("title_zh") or "",
        "node_type": node_type,
        "status": "canonical",
        "role": raw.get("role") or raw.get("scope_note") or "",
        "scope_note": raw.get("scope_note") or "",
        "statements": [],
        "relations": [],
        "children": [convert_seed_node(child) for child in raw.get("children") or []],
    }


def index_tree(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def visit(node: dict[str, Any]) -> None:
        node_id = str(node["id"])
        if node_id in result:
            raise ValueError(f"Duplicate node id: {node_id}")
        result[node_id] = node
        for child in node.get("children") or []:
            visit(child)

    visit(root)
    return result


def add_counts(node: dict[str, Any]) -> tuple[int, int, int]:
    direct = len(node.get("statements") or [])
    statements = direct
    proposed = 1 if node.get("status") == "proposed" else 0
    relations = len(node.get("relations") or [])
    for child in node.get("children") or []:
        child_statements, child_proposed, child_relations = add_counts(child)
        statements += child_statements
        proposed += child_proposed
        relations += child_relations
    node["direct_statement_count"] = direct
    node["descendant_statement_count"] = statements
    node["descendant_proposed_topic_count"] = proposed
    node["descendant_relation_count"] = relations
    return statements, proposed, relations


def build(source_root: Path, output: Path) -> dict[str, Any]:
    seed_path = source_root / "configs/bruhat_tits_atlas_seed_v1.json"
    run_root = source_root / "outputs/experiments/bruhat_tits_atlas/dual_evidence_full_v2"
    overlay_path = run_root / "publish/reviewed_textbook_coverage_overlay.json"
    manifest_path = run_root / "manifest.json"
    markdown_join_path = run_root / "plan/markdown_evidence_join.json"

    seed = read_json(seed_path)
    overlay = read_json(overlay_path)
    manifest = read_json(manifest_path)
    markdown_join = read_json(markdown_join_path)
    if (overlay.get("validation") or {}).get("status") != "PASS":
        raise ValueError("Reviewed overlay did not pass publication validation")
    if manifest.get("lifecycle_status") != "published":
        raise ValueError("Source Atlas run is not published")
    parts = seed.get("parts") or []
    if len(parts) != 1:
        raise ValueError(f"Expected one Bruhat--Tits part, found {len(parts)}")

    root = convert_seed_node(parts[0])
    nodes = index_tree(root)
    canonical_node_count = len(nodes)

    assessment_by_item = {
        str(row.get("source_item_id") or ""): row.get("directory_assessment") or {}
        for row in overlay.get("directory_assessment_candidates") or []
        if row.get("source_item_id")
    }
    source_item_to_node: dict[str, str] = {}
    all_sources: list[dict[str, Any]] = []

    existing_rows = overlay.get("existing_node_statement_candidates") or []
    new_rows = overlay.get("new_node_candidates") or []
    deferred_rows = overlay.get("deferred_source_items") or []
    existing_ids = {str(row.get("source_item_id") or "") for row in existing_rows}
    new_ids = {str(row.get("source_item_id") or "") for row in new_rows}
    deferred_ids = {
        str((row.get("review") or {}).get("source_item_id") or (row.get("source_evidence") or {}).get("source_item_id") or "")
        for row in deferred_rows
    }
    if (existing_ids & new_ids) or (existing_ids & deferred_ids) or (new_ids & deferred_ids):
        raise ValueError("Source-item disposition sets overlap")
    accounted_ids = existing_ids | new_ids | deferred_ids
    expected_source_items = int((overlay.get("counts") or {}).get("source_items") or 0)
    if "" in accounted_ids or len(accounted_ids) != expected_source_items:
        raise ValueError(
            f"Source-item accounting mismatch: {len(accounted_ids)} != {expected_source_items}"
        )

    for row in existing_rows:
        source_item_id = str(row["source_item_id"])
        node_id = str(row.get("source_node_id") or "")
        if node_id not in nodes:
            raise ValueError(f"Unknown existing-node placement {node_id} for {source_item_id}")
        statement = compact_statement(
            row,
            placement="existing_node",
            assessment=assessment_by_item.get(source_item_id),
        )
        nodes[node_id]["statements"].append(statement)
        source_item_to_node[source_item_id] = node_id
        all_sources.append(statement["source"])

    grouped_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    orphan_parent_count = 0
    for row in new_rows:
        source_item_id = str(row["source_item_id"])
        proposal = row.get("new_node_candidate") or {}
        requested_parents = [str(value) for value in proposal.get("parent_candidate_ids") or []]
        valid_parents = [value for value in requested_parents if value in nodes]
        parent_id = valid_parents[0] if valid_parents else root["id"]
        if not valid_parents:
            orphan_parent_count += 1
        title = str(proposal.get("title") or "Untitled proposed topic")
        key = (parent_id, normalized(title))
        group = grouped_candidates.get(key)
        if group is None:
            group = {
                "id": f"BT01.P{stable_id(parent_id, title)}",
                "display_number": "◇",
                "title": title,
                "title_zh": "",
                "node_type": proposal.get("node_type") or "topic",
                "status": "proposed",
                "role": proposal.get("scope_note") or proposal.get("reason") or "Proposed topic container",
                "scope_note": proposal.get("scope_note") or "",
                "candidate_reasons": [],
                "proposed_parent_ids": [],
                "candidate_source_count": 0,
                "statements": [],
                "relations": [],
                "children": [],
            }
            grouped_candidates[key] = group
            nodes[group["id"]] = group
            nodes[parent_id]["children"].append(group)
        for reason in [proposal.get("reason") or ""]:
            if reason and reason not in group["candidate_reasons"]:
                group["candidate_reasons"].append(reason)
        for candidate_parent in requested_parents:
            if candidate_parent and candidate_parent not in group["proposed_parent_ids"]:
                group["proposed_parent_ids"].append(candidate_parent)
        statement_record = {
            **(row.get("statement_candidate") or {}),
            "source_item_id": source_item_id,
            "review_confidence": row.get("review_confidence"),
            "review_flags": row.get("review_flags") or [],
        }
        statement = compact_statement(
            statement_record,
            placement="proposed_node",
            evidence=row.get("source_evidence") or {},
            assessment=assessment_by_item.get(source_item_id),
        )
        group["statements"].append(statement)
        group["candidate_source_count"] += 1
        source_item_to_node[source_item_id] = group["id"]
        all_sources.append(statement["source"])

    relation_rows = overlay.get("relation_candidates") or []
    unresolved_relations = []
    for row in relation_rows:
        source_item_id = str(row.get("source_item_id") or "")
        source_node_id = source_item_to_node.get(source_item_id, "")
        compact = {
            "id": row.get("relation_candidate_id") or f"REL-{stable_id(source_item_id, row.get('target_node_id'))}",
            "source_item_id": source_item_id,
            "relation_type": row.get("relation_type") or "related_to",
            "direction": row.get("direction") or "source_to_target",
            "target_node_id": row.get("target_node_id") or "",
            "rationale": row.get("rationale") or "",
            "review_confidence": row.get("review_confidence"),
            "source": public_source(row.get("source_evidence") or {}),
        }
        if source_node_id in nodes:
            nodes[source_node_id]["relations"].append(compact)
        else:
            unresolved_relations.append(compact)

    deferred = []
    for row in deferred_rows:
        review = row.get("review") or {}
        evidence = row.get("source_evidence") or {}
        source_item_id = str(review.get("source_item_id") or evidence.get("source_item_id") or "")
        statement_candidate = review.get("statement_candidate") or {}
        source = public_source(evidence)
        all_sources.append(source)
        deferred.append(
            {
                "id": source_item_id,
                "title": statement_candidate.get("statement_title") or evidence.get("locator") or "Deferred source item",
                "content_kind": statement_candidate.get("content_kind") or "other",
                "statement_plain": statement_candidate.get("statement_plain") or "",
                "statement_latex": statement_candidate.get("statement_latex") or "",
                "assumptions_latex": statement_candidate.get("assumptions_latex") or [],
                "conclusion_latex": statement_candidate.get("conclusion_latex") or "",
                "rationale": review.get("rationale") or "",
                "mapping_status": review.get("mapping_status") or "",
                "review_confidence": review.get("review_confidence"),
                "review_flags": review.get("review_flags") or [],
                "directory_assessment": compact_assessment(
                    review.get("directory_assessment") or assessment_by_item.get(source_item_id)
                ),
                "source": source,
            }
        )

    for node in nodes.values():
        node["statements"].sort(key=lambda item: (item["content_kind"], normalized(item["title"]), item["id"]))
        node["relations"].sort(key=lambda item: (item["relation_type"], item["target_node_id"], item["id"]))
        node["children"].sort(key=child_sort_key)
    add_counts(root)

    collection_counts = Counter(source.get("collection") or "Unknown source" for source in all_sources)
    kind_counts = Counter(
        statement["content_kind"]
        for node in nodes.values()
        for statement in node.get("statements") or []
    )
    deferred_quality = Counter(item["source"]["quality_status"] for item in deferred)
    chapter_rows = [
        {
            "id": chapter["id"],
            "number": chapter["display_number"],
            "title": chapter["title"],
            "title_zh": chapter.get("title_zh") or "",
            "statements": chapter["descendant_statement_count"],
            "proposed_topics": chapter["descendant_proposed_topic_count"],
        }
        for chapter in root.get("children") or []
        if chapter.get("status") == "canonical"
    ]
    counts = overlay.get("counts") or {}
    result = {
        "schema_version": "reasatlas-bruhat-tits-web-v1",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_run": {
            "run_id": manifest.get("run_id"),
            "lifecycle_status": manifest.get("lifecycle_status"),
            "plan_sha256": manifest.get("plan_sha256"),
            "model": (manifest.get("run_contract") or {}).get("model"),
            "reasoning_effort": (manifest.get("run_contract") or {}).get("reasoning_effort"),
            "publication_validation": overlay.get("validation"),
            "canonical_tree_sha256": overlay.get("canonical_tree_sha256"),
        },
        "title": seed.get("title") or "Bruhat–Tits Theory Atlas",
        "subtitle": "A reviewed map of buildings, parahorics, integral models, descent, and filtrations",
        "summary": {
            "source_items": expected_source_items,
            "canonical_nodes": canonical_node_count,
            "canonical_chapters": len(chapter_rows),
            "placed_existing": len(existing_rows),
            "proposed_topic_statements": len(new_rows),
            "proposed_topics_grouped": len(grouped_candidates),
            "relation_candidates": len(relation_rows),
            "deferred_items": len(deferred),
            "directory_assessments": len(assessment_by_item),
            "accounted_source_items": counts.get("accounted_source_items"),
            "items_with_markdown_evidence": markdown_join.get("items_with_any_markdown_evidence"),
            "items_with_all_markdown_files": markdown_join.get("items_with_all_requested_files"),
            "missing_markdown_markers": markdown_join.get("missing_marker_count"),
            "orphan_candidate_parent_count": orphan_parent_count,
            "unresolved_relation_count": len(unresolved_relations),
        },
        "source_collections": [
            {"name": name, "items": count}
            for name, count in sorted(collection_counts.items())
        ],
        "content_kinds": dict(sorted(kind_counts.items())),
        "deferred_quality": dict(sorted(deferred_quality.items())),
        "chapters": chapter_rows,
        "roots": [root],
        "deferred": sorted(deferred, key=lambda item: (item["source"]["collection"], item["source"]["locator"], item["id"])),
        "unresolved_relations": unresolved_relations,
    }
    write_json(output, result)
    return result


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--output",
        type=Path,
        default=repository / "site/bruhat-tits/data/atlas.json",
    )
    args = parser.parse_args()
    result = build(args.source_root.resolve(), args.output.resolve())
    summary = result["summary"]
    print(
        f"Published {args.output}: {summary['canonical_nodes']} canonical nodes, "
        f"{summary['placed_existing'] + summary['proposed_topic_statements']} placed items, "
        f"{summary['deferred_items']} deferred items"
    )


if __name__ == "__main__":
    main()
