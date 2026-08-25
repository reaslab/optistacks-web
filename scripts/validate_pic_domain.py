#!/usr/bin/env python3
"""Validate the PIC domain import and the complete ReasAtlas site catalogue."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_VERSION = "20260825_v65_pic_domain_v1"
DOMAIN_ID = "positive_isotropic_curvature"
EXPECTED_TOTALS = {"topics": 76230, "statements": 94586}
EXPECTED_GRAPH_TYPES = {
    "dependency_ref": 35,
    "document": 14,
    "proof": 1348,
    "section": 486,
    "statement": 2980,
    "term": 32,
}
EXPECTED_EDGE_TYPES = {
    "contains": 3466,
    "covers": 1292,
    "depends_on": 1088,
    "depends_on_unresolved": 57,
    "has_proof": 1348,
    "mentions": 2554,
}

SOURCE_HEADING_KIND = (
    r"(?:assumption|claim|corollary|definition|example|exercise|lemma|notation|"
    r"problem|proposition|remark|theorem)"
)
SOURCE_HEADING_NUMBER = (
    r"(?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)*(?:-extra-\d+)?)"
)
LEADING_SOURCE_HEADING = re.compile(
    rf"^\s*(?:{SOURCE_HEADING_KIND}\s+\(?{SOURCE_HEADING_NUMBER}\)?|"
    rf"{SOURCE_HEADING_NUMBER}\s+{SOURCE_HEADING_KIND}|{SOURCE_HEADING_KIND}\s*\.)",
    re.IGNORECASE,
)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def formula_environment_issues(value: str) -> list[str]:
    issues: list[str] = []
    inline_open = len(re.findall(r"(?<!\\)\\\(", value))
    inline_close = len(re.findall(r"(?<!\\)\\\)", value))
    display_open = len(re.findall(r"(?<!\\)\\\[", value))
    display_close = len(re.findall(r"(?<!\\)\\\]", value))
    if inline_open != inline_close:
        issues.append("unbalanced_inline_delimiters")
    if display_open != display_close:
        issues.append("unbalanced_display_delimiters")
    display_dollars = len(re.findall(r"(?<!\\)\$\$", value))
    without_display_dollars = re.sub(r"(?<!\\)\$\$", "", value)
    inline_dollars = len(re.findall(r"(?<!\\)\$", without_display_dollars))
    if display_dollars % 2:
        issues.append("unbalanced_display_dollars")
    if inline_dollars % 2:
        issues.append("unbalanced_inline_dollars")
    begin_environments = Counter(re.findall(r"\\begin\s*\{([^}]+)\}", value))
    end_environments = Counter(re.findall(r"\\end\s*\{([^}]+)\}", value))
    if begin_environments != end_environments:
        issues.append("unbalanced_tex_environments")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        issues.append("control_character")
    return issues


def domain_nodes(site: Path, meta: dict[str, Any]) -> list[dict[str, Any]]:
    catalog = read(site / meta["data_url"])
    nodes: list[dict[str, Any]] = []
    for root in catalog.get("roots") or []:
        if root.get("shard_url"):
            payload = read(site / root["shard_url"])
            if payload.get("chapter_id") != root.get("topic_id"):
                raise RuntimeError(f"Shard identity mismatch: {root['shard_url']}")
            nodes.extend(walk(payload["root"]))
            continue
        nodes.append(root)
        for chapter in root.get("children") or []:
            if chapter.get("shard_url"):
                payload = read(site / chapter["shard_url"])
                if payload.get("chapter_id") != chapter.get("topic_id"):
                    raise RuntimeError(f"Shard identity mismatch: {chapter['shard_url']}")
                nodes.extend(walk(payload["root"]))
            else:
                nodes.extend(walk(chapter))
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    site = args.site.resolve()
    manifest = read(site / "data/manifest.json")
    failures: list[str] = []

    def require(value: bool, code: str) -> None:
        if not value:
            failures.append(code)

    require(manifest.get("snapshot_version") == SNAPSHOT_VERSION, "snapshot_version")
    require(len(manifest.get("domains") or []) == 21, "domain_count")
    require(manifest.get("totals") == EXPECTED_TOTALS, "manifest_totals")
    release_directories = sorted(path.name for path in (ROOT / "releases").iterdir() if path.is_dir())
    require(release_directories == [SNAPSHOT_VERSION], "release_retention")

    domain_lookup = {domain["id"]: domain for domain in manifest.get("domains") or []}
    require(DOMAIN_ID in domain_lookup, "pic_domain_missing")
    geometric = next(
        (subject for subject in manifest.get("subject_domains") or [] if subject.get("id") == "geometric_analysis"),
        {},
    )
    require(geometric.get("items") == [DOMAIN_ID], "geometric_analysis_membership")
    require(geometric.get("stats") == {"collections": 1, "topics": 531, "statements": 415}, "geometric_analysis_stats")

    all_topic_ids: list[str] = []
    all_statement_ids: list[str] = []
    computed_totals = {"topics": 0, "statements": 0}
    loaded_domains: dict[str, list[dict[str, Any]]] = {}
    for domain_id, meta in domain_lookup.items():
        try:
            nodes = domain_nodes(site, meta)
        except Exception as error:  # record the domain-specific load failure
            failures.append(f"{domain_id}:load:{error}")
            continue
        loaded_domains[domain_id] = nodes
        statements = [
            statement
            for node in nodes
            for statement in node.get("knowledge_statements") or []
        ]
        topic_ids = [str(node.get("topic_id") or "") for node in nodes]
        statement_ids = [str(statement.get("id") or statement.get("statement_id") or "") for statement in statements]
        require(all(topic_ids), f"{domain_id}:empty_topic_id")
        require(all(statement_ids), f"{domain_id}:empty_statement_id")
        require(meta.get("stats", {}).get("topics") == len(nodes), f"{domain_id}:topic_stats")
        require(meta.get("stats", {}).get("statements") == len(statements), f"{domain_id}:statement_stats")
        all_topic_ids.extend(topic_ids)
        all_statement_ids.extend(statement_ids)
        computed_totals["topics"] += len(nodes)
        computed_totals["statements"] += len(statements)

    require(len(all_topic_ids) == len(set(all_topic_ids)), "duplicate_topic_ids")
    require(len(all_statement_ids) == len(set(all_statement_ids)), "duplicate_statement_ids")
    require(computed_totals == EXPECTED_TOTALS, "computed_totals")

    pic_meta = domain_lookup.get(DOMAIN_ID, {})
    pic_nodes = loaded_domains.get(DOMAIN_ID, [])
    pic_statements = [
        statement
        for node in pic_nodes
        for statement in node.get("knowledge_statements") or []
    ]
    pic_ids = {str(node.get("topic_id")) for node in pic_nodes}
    require(len(pic_nodes) == 531 and len(pic_ids) == 531, "pic_topic_count")
    require(len(pic_statements) == 415, "pic_placement_count")
    require(len({statement.get("source_graph_statement_id") for statement in pic_statements}) == 166, "pic_unique_source_statement_count")
    require({f"PIC.A0{index}" for index in range(1, 8)}.issubset(pic_ids), "pic_part_ids")
    require(pic_meta.get("publication_status") == "source_grounded_v2_scaffold_requires_mathematical_placement_review", "pic_publication_boundary")

    catalog_path = site / str(pic_meta.get("data_url") or "")
    catalog = read(catalog_path) if catalog_path.is_file() else {}
    routes = catalog.get("node_routes") or {}
    require(len(routes) == 530, "pic_route_count")
    require(set(routes) == pic_ids - {"PIC"}, "pic_route_coverage")
    require((catalog.get("loading") or {}).get("shard_count") == 7, "pic_shard_count")

    artifacts = {artifact.get("kind"): artifact for artifact in catalog.get("artifacts") or []}
    require(set(artifacts) == {"navigation_view", "concept_registry", "statement_graph", "navigation_audit"}, "pic_artifact_set")
    artifact_payloads: dict[str, Any] = {}
    for kind, artifact in artifacts.items():
        path = site / str(artifact.get("url") or "")
        require(path.is_file(), f"pic_artifact_missing:{kind}")
        if path.is_file():
            try:
                artifact_payloads[kind] = read(path)
            except Exception as error:
                failures.append(f"pic_artifact_json:{kind}:{error}")

    navigation = artifact_payloads.get("navigation_view", {})
    registry = artifact_payloads.get("concept_registry", {})
    graph = artifact_payloads.get("statement_graph", {})
    audit = artifact_payloads.get("navigation_audit", {})
    require(navigation.get("tree_id") == "pic_detailed_tree_v2" and navigation.get("tree_version") == "v2.1", "navigation_identity")
    require(len(registry.get("concepts") or []) == 498, "concept_count")
    require(audit.get("node_count") == 530 and audit.get("leaf_count") == 415, "navigation_audit_counts")

    semantic_title_payload = read(ROOT / "scripts/pic_semantic_titles.json")
    semantic_titles = semantic_title_payload.get("titles") or {}
    generic_title = re.compile(
        r"^(?:assumption|claim|corollary|definition|example|exercise|lemma|notation|problem|proposition|remark|theorem)\s+[A-Z]?(?:\d|[.-])+(?:-extra-\d+)?$",
        re.IGNORECASE,
    )
    require(
        semantic_title_payload.get("schema_version") == "reasatlas-pic-semantic-titles-v1",
        "semantic_title_schema",
    )
    require(len(semantic_titles) == 166, "semantic_title_count")
    require(len(set(semantic_titles.values())) == 166, "semantic_title_uniqueness")
    require(not any(generic_title.fullmatch(title) for title in semantic_titles.values()), "generic_semantic_title")

    placement_nodes = [node for node in pic_nodes if node.get("knowledge_statements")]
    require(len(placement_nodes) == 415, "semantic_placement_node_count")
    require(
        all(
            node.get("title") == semantic_titles.get(statement.get("source_graph_statement_id"))
            and statement.get("title") == node.get("title")
            and statement.get("statement_title") == node.get("title")
            for node in placement_nodes
            for statement in node.get("knowledge_statements") or []
        ),
        "semantic_placement_title_mapping",
    )
    require(
        not any((node.get("top_down_role") or "").strip() for node in placement_nodes),
        "leaf_role_not_omitted",
    )
    require(
        not any(
            LEADING_SOURCE_HEADING.match(str(statement.get("statement_latex") or ""))
            for statement in pic_statements
        ),
        "leading_source_heading_in_statement",
    )
    pic_formula_issues = [
        {
            "statement_id": statement.get("id"),
            "field": field,
            "issues": formula_environment_issues(str(statement.get(field) or "")),
        }
        for statement in pic_statements
        for field in ("statement_latex", "proof_latex")
        if statement.get(field) and formula_environment_issues(str(statement.get(field) or ""))
    ]
    require(not pic_formula_issues, "pic_formula_environments")
    require(
        not any(
            "source-anchored" in str(node.get("top_down_role") or "").lower()
            for node in pic_nodes
        ),
        "source_anchored_template_in_catalog",
    )
    require(
        all(
            len([child.get("title") for child in node.get("children") or []])
            == len(set(child.get("title") for child in node.get("children") or []))
            for node in pic_nodes
        ),
        "duplicate_sibling_titles",
    )

    navigation_nodes = [
        node for part in navigation.get("parts") or [] for node in walk(part)
    ]
    navigation_leaves = [node for node in navigation_nodes if node.get("source_statement_id")]
    require(len(navigation_leaves) == 415, "semantic_navigation_leaf_count")
    require(
        all(
            node.get("title") == semantic_titles.get(node.get("source_statement_id"))
            and not (node.get("role") or "").strip()
            for node in navigation_leaves
        ),
        "semantic_navigation_leaf_mapping",
    )
    statement_concepts = [
        concept for concept in registry.get("concepts") or [] if concept.get("source_statement_id")
    ]
    require(len(statement_concepts) == 415, "semantic_concept_count")
    require(
        all(
            concept.get("preferred_label")
            == semantic_titles.get(concept.get("source_statement_id"))
            and not (concept.get("sense_definition") or "").strip()
            for concept in statement_concepts
        ),
        "semantic_concept_mapping",
    )

    graph_nodes = graph.get("nodes") or []
    graph_edges = graph.get("edges") or []
    graph_node_ids = [str(node.get("id") or "") for node in graph_nodes]
    graph_edge_ids = [str(edge.get("id") or "") for edge in graph_edges]
    graph_type_counts = {
        kind: sum(node.get("type") == kind for node in graph_nodes)
        for kind in EXPECTED_GRAPH_TYPES
    }
    edge_type_counts = {
        kind: sum(edge.get("type") == kind for edge in graph_edges)
        for kind in EXPECTED_EDGE_TYPES
    }
    require(graph.get("schema_version") == "0.1.0", "graph_schema")
    require(graph_type_counts == EXPECTED_GRAPH_TYPES, "graph_node_type_counts")
    require(edge_type_counts == EXPECTED_EDGE_TYPES, "graph_edge_type_counts")
    require(len(graph_node_ids) == len(set(graph_node_ids)) and all(graph_node_ids), "graph_node_ids")
    require(len(graph_edge_ids) == len(set(graph_edge_ids)) and all(graph_edge_ids), "graph_edge_ids")
    graph_node_id_set = set(graph_node_ids)
    require(
        all(edge.get("source") in graph_node_id_set and edge.get("target") in graph_node_id_set for edge in graph_edges),
        "graph_edge_endpoints",
    )
    require(
        {statement.get("source_graph_statement_id") for statement in pic_statements}.issubset(graph_node_id_set),
        "placement_graph_references",
    )
    graph_node_lookup = {node.get("id"): node for node in graph_nodes}
    require(
        all(
            str(graph_node_lookup.get(statement.get("source_graph_statement_id"), {}).get("label") or "")
            in str((statement.get("source_refs") or [{}])[0].get("locator") or "")
            for statement in pic_statements
        ),
        "source_label_provenance",
    )

    pic_paths = [catalog_path]
    pic_paths.extend((site / "data/shards" / DOMAIN_ID).glob("*.json"))
    pic_paths.extend((site / "data/pic").glob("*.json"))
    private_path_hits = [
        str(path.relative_to(site))
        for path in pic_paths
        if "/Users/" in path.read_text(encoding="utf-8") or "/root/" in path.read_text(encoding="utf-8")
    ]
    require(not private_path_hits, "private_absolute_paths")

    if args.source_root:
        source_directory = args.source_root.resolve() / "output/pic_knowledge_graph"
        source_files = {
            "navigation_view": source_directory / "pic_detailed_tree_v2.json",
            "concept_registry": source_directory / "pic_concept_registry_v2.json",
            "statement_graph": source_directory / "pic_knowledge_graph.json",
            "navigation_audit": source_directory / "pic_detailed_tree_v2_report.json",
        }
        for kind, path in source_files.items():
            require(path.is_file(), f"source_artifact_missing:{kind}")
            if path.is_file():
                require(artifacts.get(kind, {}).get("source_sha256") == file_sha256(path), f"source_hash:{kind}")

    report = {
        "schema_version": "reasatlas-pic-domain-validation-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_version": manifest.get("snapshot_version"),
        "release_directories": release_directories,
        "domain_count": len(domain_lookup),
        "totals": manifest.get("totals"),
        "pic": {
            "topics": len(pic_nodes),
            "statement_placements": len(pic_statements),
            "unique_source_statements": len({statement.get("source_graph_statement_id") for statement in pic_statements}),
            "concepts": len(registry.get("concepts") or []),
            "graph_nodes": len(graph_nodes),
            "graph_edges": len(graph_edges),
            "shards": (catalog.get("loading") or {}).get("shard_count"),
            "semantic_titles": len(semantic_titles),
            "template_leaf_descriptions": sum(
                bool((node.get("top_down_role") or "").strip()) for node in placement_nodes
            ),
            "leading_source_headings": sum(
                bool(LEADING_SOURCE_HEADING.match(str(statement.get("statement_latex") or "")))
                for statement in pic_statements
            ),
            "formula_environment_issues": len(pic_formula_issues),
        },
        "duplicate_topic_ids": len(all_topic_ids) - len(set(all_topic_ids)),
        "duplicate_statement_ids": len(all_statement_ids) - len(set(all_statement_ids)),
        "private_absolute_path_files": private_path_hits,
        "failure_codes": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    report_path = args.report or ROOT / f"releases/{SNAPSHOT_VERSION}/live_validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
