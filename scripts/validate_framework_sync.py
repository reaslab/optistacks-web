#!/usr/bin/env python3
"""Validate the v62 framework and convergence snapshot installed in ReasAtlas."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterator


EXPECTED_TREE_ID = "opt_stacks_v62_framework_sync_candidate"
EXPECTED_SNAPSHOT_VERSION = "20260819_framework_sync_v1_4"
EXPECTED_CONVERGENCE = 115
EXPECTED_NEW_NODES = {
    "A05.C04.NA8EECF91A4D2",
    "A11.C01.BAL06",
    "A11.C01.BAL07",
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def domain_nodes(site: Path, domain: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = read(site / domain["data_url"])
    result: list[dict[str, Any]] = []
    for root in catalog.get("roots") or []:
        result.append(root)
        for chapter in root.get("children") or []:
            shard_url = chapter.get("shard_url")
            if shard_url:
                shard = read(site / shard_url)
                result.extend(walk(shard["root"]))
            else:
                result.extend(walk(chapter))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=Path(__file__).resolve().parents[1] / "site")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    site = args.site.resolve()
    manifest = read(site / "data/manifest.json")
    failures: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            failures.append(code)

    require(len(manifest.get("domains") or []) == 15, "domain_count")
    require(manifest.get("snapshot_version") == EXPECTED_SNAPSHOT_VERSION, "snapshot_version")
    require(
        (manifest.get("directory_snapshot") or {}).get("tree_id") == EXPECTED_TREE_ID,
        "directory_tree_id",
    )
    convergence = manifest.get("convergence_candidate_snapshot") or {}
    require(convergence.get("source_record_count") == EXPECTED_CONVERGENCE, "source_convergence_count")
    require(convergence.get("added_statement_count") == EXPECTED_CONVERGENCE, "added_convergence_count")
    require(convergence.get("unmapped_count") == 0, "unmapped_convergence")
    require(convergence.get("layer_count") == 2, "convergence_layer_count")
    require(convergence.get("partial_layer_count") == 1, "partial_convergence_layer_count")

    node_index: dict[str, dict[str, Any]] = {}
    parents: dict[str, str | None] = {}
    duplicate_nodes: list[str] = []
    convergence_records: list[tuple[str, dict[str, Any]]] = []
    all_statement_ids: list[str] = []
    render_field_failures: list[str] = []
    public_campaign_records: list[dict[str, Any]] = []
    unsafe_public_campaign_records: list[str] = []
    topic_counts = Counter()
    statement_counts = Counter()
    for domain in manifest.get("domains") or []:
        nodes = domain_nodes(site, domain)
        topic_counts[domain["id"]] = len(nodes)
        for node in nodes:
            topic_id = str(node.get("topic_id") or "")
            if topic_id in node_index:
                duplicate_nodes.append(topic_id)
            node_index[topic_id] = node
            for child in node.get("children") or []:
                if child.get("topic_id"):
                    parents[str(child["topic_id"])] = topic_id
            statements = node.get("knowledge_statements") or []
            statement_counts[domain["id"]] += len(statements)
            for statement in statements:
                statement_id = str(statement.get("id") or statement.get("statement_id") or "")
                all_statement_ids.append(statement_id)
                if not (statement.get("title") or statement.get("statement_title")):
                    render_field_failures.append(f"{topic_id}:{statement_id}:title")
                if not (statement.get("statement_plain") or statement.get("statement_latex")):
                    render_field_failures.append(f"{topic_id}:{statement_id}:body")
                if not isinstance(statement.get("assumptions_latex") or [], list):
                    render_field_failures.append(f"{topic_id}:{statement_id}:assumptions")
                if not isinstance(statement.get("source_refs") or [], list):
                    render_field_failures.append(f"{topic_id}:{statement_id}:sources")
                metadata = statement.get("intermediate_metadata") or {}
                stage = str(metadata.get("stage") or "")
                if stage.startswith("0809_campaign_"):
                    public_campaign_records.append(statement)
                    mapping_method = str(statement.get("mapping_method") or metadata.get("placement_method") or "")
                    allowed = (
                        stage == "0809_campaign_published"
                        and mapping_method
                        in {
                            "campaign_existing_node",
                            "explicit_node_alias",
                            "campaign_exact_sibling_title",
                            "campaign_cross_source_candidate_container",
                            "campaign_unique_same_part_title",
                        }
                    ) or (
                        stage == "0809_campaign_reviewed"
                        and mapping_method
                        in {
                            "campaign_existing_node",
                            "campaign_preferred_home",
                            "explicit_node_alias",
                            "campaign_exact_sibling_title",
                            "campaign_cross_source_candidate_container",
                            "campaign_unique_same_part_title",
                        }
                    )
                    if not allowed:
                        unsafe_public_campaign_records.append(statement_id)
                if metadata.get("stage") in {
                    "convergence_fast_candidate_unreviewed",
                    "convergence_partial_fast_candidate_unreviewed",
                }:
                    convergence_records.append((topic_id, statement))

    require(not duplicate_nodes, "duplicate_topic_ids")
    require(all(all_statement_ids), "missing_statement_ids")
    require(len(all_statement_ids) == len(set(all_statement_ids)), "duplicate_statement_ids")
    require(not render_field_failures, "statement_render_contract")
    require(not unsafe_public_campaign_records, "unsafe_campaign_public_placement")
    require(EXPECTED_NEW_NODES <= set(node_index), "missing_new_framework_nodes")
    require(
        node_index.get("A04.C06", {}).get("title")
        == "Constrained NLP Optimality, Regularity, and Sensitivity Theory",
        "a04_c06_title",
    )
    require(
        parents.get("A11.C01.BAL03.NBFBD2755D2A4") == "A11.C01.BAL06",
        "qp_active_set_parent",
    )
    require(
        parents.get("A11.C01.BAL03.N01D3ED16EC7D") == "A11.C01.BAL07",
        "qp_ipm_parent",
    )
    require(
        node_index.get("A04.C01.N241340C2494F", {}).get("title")
        == "Nonlinear CG: NLP Specializations and Cross-Index",
        "ncg_cross_index_title",
    )
    require(
        node_index.get("A05.C05.ND1D789A6315B", {}).get("title")
        == "Douglas-Rachford–ADMM Correspondence Interface",
        "admm_interface_title",
    )
    a07_nodes = list(walk(node_index["A07.C03"])) if "A07.C03" in node_index else []
    require(len(a07_nodes) == 543, "a07_node_count")

    convergence_ids = [
        str(statement.get("id") or statement.get("statement_id") or "")
        for _, statement in convergence_records
    ]
    require(len(convergence_records) == EXPECTED_CONVERGENCE, "installed_convergence_count")
    require(len(set(convergence_ids)) == len(convergence_ids), "duplicate_convergence_ids")
    require(all(statement.get("review_status") == "candidate" for _, statement in convergence_records), "convergence_review_status")
    require(all(statement.get("source_refs") for _, statement in convergence_records), "convergence_source_refs")
    require(all(topic_id in node_index for topic_id, _ in convergence_records), "convergence_topic_fk")
    require(
        all(
            isinstance(statement.get("conclusion"), dict)
            and isinstance(statement.get("variant_dimensions"), dict)
            and isinstance(statement.get("boundary_notes"), list)
            and isinstance(statement.get("relations"), list)
            and isinstance(statement.get("review_flags"), list)
            for _, statement in convergence_records
        ),
        "convergence_render_contract",
    )
    partial_convergence = [
        statement
        for _, statement in convergence_records
        if (statement.get("intermediate_metadata") or {}).get("partial_run") is True
    ]
    require(len(partial_convergence) == 41, "partial_convergence_render_count")
    campaign_report = manifest.get("source_campaign_snapshot") or {}
    quarantine_path = site / str(campaign_report.get("quarantine_data_url") or "")
    require(quarantine_path.is_file(), "campaign_quarantine_missing")
    quarantine = read(quarantine_path) if quarantine_path.is_file() else {"records": []}
    quarantine_records = quarantine.get("records") or []
    require(
        quarantine.get("record_count") == len(quarantine_records) == campaign_report.get("quarantined_count"),
        "campaign_quarantine_count",
    )
    require(
        len(public_campaign_records) == campaign_report.get("added_statement_count"),
        "public_campaign_count",
    )
    require(
        int(campaign_report.get("candidates_with_body") or 0)
        == len(public_campaign_records)
        + len(quarantine_records)
        + int(campaign_report.get("duplicate_title_count") or 0),
        "campaign_candidate_accounting",
    )
    materialization = campaign_report.get("candidate_container_materialization") or {}
    materialized_nodes = materialization.get("materialized_nodes") or []
    require(
        materialization.get("materialized_node_count") == len(materialized_nodes),
        "campaign_materialized_node_count",
    )
    require(
        all(
            row.get("topic_id") in node_index
            and row.get("parent_topic_id") in node_index
            and int(row.get("independent_campaign_count") or 0) >= 2
            for row in materialized_nodes
        ),
        "campaign_materialized_node_contract",
    )
    shortcuts = {item.get("id"): item for item in manifest.get("navigation_shortcuts") or []}
    require(
        {
            "derivative_free_optimization": "A07.C01",
            "manifold_optimization": "A07.C02",
            "distributed_optimization": "A07.C03",
        }
        == {key: value.get("default_node_id") for key, value in shortcuts.items()},
        "a07_shortcut_split",
    )

    manifest_topics = sum(int(domain["stats"]["topics"]) for domain in manifest["domains"])
    manifest_statements = sum(int(domain["stats"]["statements"]) for domain in manifest["domains"])
    require(manifest_topics == sum(topic_counts.values()), "manifest_topic_totals")
    require(manifest_statements == sum(statement_counts.values()), "manifest_statement_totals")
    require((manifest.get("totals") or {}).get("topics") == manifest_topics, "global_topic_total")
    require((manifest.get("totals") or {}).get("statements") == manifest_statements, "global_statement_total")

    report = {
        "schema_version": "reasatlas-framework-sync-validation-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "directory_tree_id": (manifest.get("directory_snapshot") or {}).get("tree_id"),
        "domain_count": len(manifest.get("domains") or []),
        "topic_count": sum(topic_counts.values()),
        "statement_count": sum(statement_counts.values()),
        "convergence_candidate_count": len(convergence_records),
        "partial_convergence_candidate_count": len(partial_convergence),
        "statement_render_contract_count": len(all_statement_ids),
        "statement_render_contract_failures": render_field_failures[:20],
        "public_campaign_statement_count": len(public_campaign_records),
        "quarantined_campaign_candidate_count": len(quarantine_records),
        "unsafe_public_campaign_placement_count": len(unsafe_public_campaign_records),
        "materialized_campaign_candidate_node_count": len(materialized_nodes),
        "a07_c03_node_count": len(a07_nodes),
        "expected_new_nodes_present": sorted(EXPECTED_NEW_NODES & set(node_index)),
        "duplicate_topic_ids": sorted(set(duplicate_nodes)),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.report.with_suffix(args.report.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(args.report)
    print(text, end="")
    if failures:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
