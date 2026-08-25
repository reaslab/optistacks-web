#!/usr/bin/env python3
"""Publish the PIC knowledge graph as an independent ReasAtlas domain.

The PIC source intentionally separates its reader-facing navigation tree,
concept registry, and extracted statement graph.  This importer preserves that
separation: the v2.1 tree becomes the website catalogue, while sanitized copies
of all three source artifacts remain downloadable sidecars.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ID = "positive_isotropic_curvature"
DOMAIN_TITLE = "Positive Isotropic Curvature"
DOMAIN_ACCENT = "#8b5e3c"
SUBJECT_ID = "geometric_analysis"
SNAPSHOT_VERSION = "20260825_v65_pic_domain_v1"
SOURCE_RELATIVE = Path("output/pic_knowledge_graph")

TREE_FILENAME = "pic_detailed_tree_v2.json"
REGISTRY_FILENAME = "pic_concept_registry_v2.json"
GRAPH_FILENAME = "pic_knowledge_graph.json"
AUDIT_FILENAME = "pic_detailed_tree_v2_report.json"
SEMANTIC_TITLES_PATH = ROOT / "scripts" / "pic_semantic_titles.json"

PUBLIC_ARTIFACT_DIRECTORY = Path("data/pic")
PUBLIC_ARTIFACTS = {
    "navigation_view": "navigation_view_v2.json",
    "concept_registry": "concept_registry_v2.json",
    "statement_graph": "statement_graph.json",
    "navigation_audit": "navigation_audit_v2.json",
}

CONTENT_KIND = {
    "algorithm": "algorithm",
    "assumption": "assumption",
    "claim": "claim",
    "conjecture": "conjecture",
    "cor": "corollary",
    "def": "definition",
    "example": "example",
    "exercise": "exercise",
    "lemma": "lemma",
    "notation": "notation",
    "problem": "problem",
    "prop": "proposition",
    "remark": "remark",
    "thm": "theorem",
}

SOURCE_HEADING_KIND = (
    r"(?:assumption|claim|corollary|definition|example|exercise|lemma|notation|"
    r"problem|proposition|remark|theorem)"
)
SOURCE_HEADING_NUMBER = (
    r"(?:[A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)*(?:-extra-\d+)?)"
)
SOURCE_HEADING_PATTERNS = (
    re.compile(
        rf"^\s*{SOURCE_HEADING_KIND}\s+\(?{SOURCE_HEADING_NUMBER}\)?\s*\.?\s*",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*{SOURCE_HEADING_NUMBER}\s+{SOURCE_HEADING_KIND}\s*\.?\s*",
        re.IGNORECASE,
    ),
    re.compile(rf"^\s*{SOURCE_HEADING_KIND}\s*\.\s*", re.IGNORECASE),
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(value, ensure_ascii=False, indent=2)
        if pretty
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    ) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strip_leading_source_heading(value: str) -> str:
    """Remove a source environment label without touching the mathematical body.

    The extracted corpus uses both ``LEMMA 3.2.`` and ``3.2 LEMMA.`` forms,
    plus an occasional unnumbered ``Theorem.``.  Only a heading at the start of
    the field is removed; references such as ``by Lemma 3.2`` remain intact.
    """

    for pattern in SOURCE_HEADING_PATTERNS:
        stripped, replacement_count = pattern.subn("", value, count=1)
        if replacement_count:
            return stripped.lstrip()
    return value


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def node_count(node: dict[str, Any]) -> int:
    return sum(1 for _ in walk(node))


def statement_count(node: dict[str, Any]) -> int:
    return sum(len(item.get("knowledge_statements") or []) for item in walk(node))


def display_number(node_id: str) -> str:
    if node_id == "PIC":
        return "PIC"
    pieces: list[str] = []
    for component in node_id.removeprefix("PIC.").split("."):
        digits = "".join(character for character in component if character.isdigit())
        pieces.append(str(int(digits)) if digits else component)
    return ".".join(pieces)


def sanitize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(graph)
    sanitized["source_root"] = "PIC-md2json"
    sanitized_nodes: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        item = dict(node)
        if item.get("type") == "document" and item.get("relative_path"):
            item["source_path"] = f"PIC-md2json/{item['relative_path']}/result.json"
        sanitized_nodes.append(item)
    sanitized["nodes"] = sanitized_nodes
    return sanitized


def sanitize_tree(tree: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(tree)
    sanitized["source_graph"] = f"{PUBLIC_ARTIFACT_DIRECTORY.as_posix()}/{PUBLIC_ARTIFACTS['statement_graph']}"
    return sanitized


def load_semantic_titles(path: Path) -> dict[str, str]:
    payload = read_json(path)
    if payload.get("schema_version") != "reasatlas-pic-semantic-titles-v1":
        raise RuntimeError("Unexpected PIC semantic-title schema")
    titles = payload.get("titles")
    if not isinstance(titles, dict):
        raise RuntimeError("PIC semantic-title payload has no title mapping")
    return {str(statement_id): str(title).strip() for statement_id, title in titles.items()}


def ensure_semantic_title_coverage(
    tree: dict[str, Any], semantic_titles: dict[str, str]
) -> None:
    tree_nodes = [node for part in tree.get("parts") or [] for node in walk(part)]
    attached_ids = {
        str(node["source_statement_id"])
        for node in tree_nodes
        if node.get("source_statement_id")
    }
    title_ids = set(semantic_titles)
    if title_ids != attached_ids:
        missing = sorted(attached_ids - title_ids)
        extra = sorted(title_ids - attached_ids)
        raise RuntimeError(
            f"PIC semantic-title coverage mismatch: missing={missing}, extra={extra}"
        )
    generic_title = re.compile(
        r"^(?:assumption|claim|corollary|definition|example|exercise|lemma|notation|problem|proposition|remark|theorem)\s+[A-Z]?(?:\d|[.-])+(?:-extra-\d+)?$",
        re.IGNORECASE,
    )
    invalid = [
        statement_id
        for statement_id, title in semantic_titles.items()
        if not title or generic_title.fullmatch(title)
    ]
    if invalid:
        raise RuntimeError(f"PIC semantic titles are empty or generic: {invalid}")
    if len(set(semantic_titles.values())) != len(semantic_titles):
        raise RuntimeError("PIC semantic titles must be unique across source statements")


def semanticize_tree(
    tree: dict[str, Any], semantic_titles: dict[str, str]
) -> dict[str, Any]:
    published = copy.deepcopy(tree)

    def revise(node: dict[str, Any], parent_path: list[str]) -> None:
        source_statement_id = node.get("source_statement_id")
        if source_statement_id:
            semantic_title = semantic_titles[str(source_statement_id)]
            node["title"] = semantic_title
            node["role"] = ""
            node["keywords"] = list(
                dict.fromkeys([semantic_title, *(node.get("keywords") or [])])
            )
        node["path"] = [*parent_path, node["title"]]
        for child in node.get("children") or []:
            revise(child, node["path"])

    for part in published.get("parts") or []:
        revise(part, [])
    return sanitize_tree(published)


def semanticize_registry(
    registry: dict[str, Any], semantic_titles: dict[str, str]
) -> dict[str, Any]:
    published = copy.deepcopy(registry)
    for concept in published.get("concepts") or []:
        source_statement_id = concept.get("source_statement_id")
        if not source_statement_id:
            continue
        semantic_title = semantic_titles[str(source_statement_id)]
        concept["preferred_label"] = semantic_title
        concept["sense_definition"] = ""
        concept["aliases"] = list(
            dict.fromkeys([semantic_title, *(concept.get("aliases") or [])])
        )
        path = str(concept.get("primary_view_path") or "").split(" / ")
        if path:
            path[-1] = semantic_title
            concept["primary_view_path"] = " / ".join(path)
    return published


def relation_index(
    graph: dict[str, Any], node_lookup: dict[str, dict[str, Any]]
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    indexed: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for edge in graph.get("edges") or []:
        edge_type = edge.get("type")
        if edge_type not in {"depends_on", "depends_on_unresolved", "mentions"}:
            continue
        source = str(edge.get("source") or "")
        target_id = str(edge.get("target") or "")
        target = node_lookup.get(target_id, {})
        relation = {"target_id": target_id}
        if edge_type == "depends_on":
            relation["label"] = target.get("label") or target_id
            relation["document_title"] = target.get("document_title")
        elif edge_type == "depends_on_unresolved":
            relation["label"] = target.get("label") or target_id
            relation["resolution_status"] = target.get("resolution_status")
            relation["candidate_count"] = target.get("candidate_count")
        else:
            relation["name"] = target.get("name") or target_id
            relation["count"] = int(edge.get("count") or 0)
        indexed[source][edge_type].append(relation)
    return indexed


def make_statement(
    tree_node: dict[str, Any],
    source: dict[str, Any],
    proof: dict[str, Any] | None,
    relations: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    placement_id = tree_node["node_id"]
    locator = " / ".join(
        part
        for part in (source.get("section_title"), source.get("label"))
        if part
    )
    graph_relations = {
        "depends_on": relations.get("depends_on", []),
        "depends_on_unresolved": relations.get("depends_on_unresolved", []),
        "mentions": relations.get("mentions", []),
    }
    graph_relations = {key: value for key, value in graph_relations.items() if value}
    statement = {
        "id": f"pic-placement:{placement_id}",
        "statement_id": f"pic-placement:{placement_id}",
        "node_type": "knowledge_statement",
        "title": tree_node.get("title") or source.get("label") or "Untitled statement",
        "statement_title": tree_node.get("title") or source.get("label") or "Untitled statement",
        "content_kind": CONTENT_KIND.get(str(source.get("env") or ""), source.get("env") or "statement"),
        "statement_latex": strip_leading_source_heading(
            source.get("content") or tree_node.get("source_content_excerpt") or ""
        ),
        "source_graph_statement_id": source["id"],
        "source_environment": source.get("env"),
        "formula_count": int(source.get("formula_count") or 0),
        "mapping_method": "pic_v2_keyword_attachment",
        "original_topic_id": placement_id,
        "mapped_topic_ids": [placement_id],
        "proof_included": bool(proof and proof.get("proof")),
        "source_refs": [
            {
                "source_graph_id": source["id"],
                "source_title": source.get("document_title"),
                "source_item_id": source["id"],
                "locator": locator,
                "source_environment": source.get("env"),
                "fulltext_span_verified": False,
            }
        ],
        "review_flags": [
            "source-grounded extraction",
            "v2 keyword attachment requires mathematical placement review",
        ],
        "graph_relations": graph_relations,
    }
    if proof and proof.get("proof"):
        statement["proof_latex"] = proof["proof"]
        statement["proof_id"] = proof.get("id")
        statement["proof_length"] = int(proof.get("proof_length") or 0)
    return statement


def convert_tree_node(
    source_node: dict[str, Any],
    *,
    depth: int,
    statement_lookup: dict[str, dict[str, Any]],
    proof_lookup: dict[str, dict[str, Any]],
    relations: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    children = [
        convert_tree_node(
            child,
            depth=depth + 1,
            statement_lookup=statement_lookup,
            proof_lookup=proof_lookup,
            relations=relations,
        )
        for child in source_node.get("children") or []
    ]
    source_statement_id = source_node.get("source_statement_id")
    knowledge_statements: list[dict[str, Any]] = []
    if source_statement_id:
        source_statement = statement_lookup[source_statement_id]
        knowledge_statements.append(
            make_statement(
                source_node,
                source_statement,
                proof_lookup.get(source_statement_id),
                relations.get(source_statement_id, {}),
            )
        )

    descendant_statements = sum(
        len(child.get("knowledge_statements") or [])
        + int(child.get("descendant_statement_count") or 0)
        for child in children
    )
    kind_counts = Counter(
        statement.get("content_kind") for statement in knowledge_statements
    )
    node_type = source_node.get("node_type") or "topic"
    return {
        "topic_id": source_node["node_id"],
        "display_number": display_number(source_node["node_id"]),
        "title": source_node["title"],
        "topic_type": node_type,
        "depth": depth,
        "classification_axis": node_type,
        "top_down_role": source_node.get("role") or ("" if source_statement_id else "PIC navigation topic."),
        "keywords": source_node.get("keywords") or [],
        "knowledge_status": (
            "source_anchored_statement_placement"
            if knowledge_statements
            else "structural_container_with_descendant_knowledge"
        ),
        "direct_statement_count": len(knowledge_statements),
        "direct_base_statement_count": len(knowledge_statements),
        "direct_enrichment_statement_count": 0,
        "descendant_statement_count": descendant_statements,
        "descendant_base_statement_count": descendant_statements,
        "descendant_enrichment_statement_count": 0,
        "direct_content_kind_counts": dict(sorted(kind_counts.items())),
        "subtree_topic_count": 1 + sum(int(child["subtree_topic_count"]) for child in children),
        "pic_attachment_evidence_count": int(source_node.get("attached_statement_count") or 0),
        "children": children,
        "knowledge_statements": knowledge_statements,
        "top_down_textbook_witnesses": [],
    }


def chapter_summary(chapter: dict[str, Any], shard_url: str) -> dict[str, Any]:
    summary = {
        key: value
        for key, value in chapter.items()
        if key not in {"children", "knowledge_statements", "top_down_textbook_witnesses"}
    }
    summary.update(
        {
            "children": [],
            "knowledge_statements": [],
            "top_down_textbook_witnesses": [],
            "shard_url": shard_url,
            "lazy_content": True,
            "lazy_child_count": len(chapter.get("children") or []),
        }
    )
    return summary


def source_artifact(
    *, kind: str, title: str, url: str, source_path: Path, description: str, stats: dict[str, Any]
) -> dict[str, Any]:
    return {
        "kind": kind,
        "title": title,
        "url": url,
        "description": description,
        "source_sha256": file_sha256(source_path),
        "stats": stats,
    }


def public_artifacts(
    source_directory: Path,
    tree: dict[str, Any],
    registry: dict[str, Any],
    graph: dict[str, Any],
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        source_artifact(
            kind="navigation_view",
            title="PIC navigation view v2.1",
            url=f"{PUBLIC_ARTIFACT_DIRECTORY.as_posix()}/{PUBLIC_ARTIFACTS['navigation_view']}",
            source_path=source_directory / TREE_FILENAME,
            description="Reader-facing variable-depth tree with semantic leaf titles and source-anchored statement placements.",
            stats={"nodes": audit.get("node_count"), "leaves": audit.get("leaf_count"), "semantic_titles": 166},
        ),
        source_artifact(
            kind="concept_registry",
            title="PIC concept registry v2",
            url=f"{PUBLIC_ARTIFACT_DIRECTORY.as_posix()}/{PUBLIC_ARTIFACTS['concept_registry']}",
            source_path=source_directory / REGISTRY_FILENAME,
            description="Canonical concepts and primary navigation homes, with semantic titles for statement-backed leaves.",
            stats={"concepts": len(registry.get("concepts") or [])},
        ),
        source_artifact(
            kind="statement_graph",
            title="PIC extracted statement graph",
            url=f"{PUBLIC_ARTIFACT_DIRECTORY.as_posix()}/{PUBLIC_ARTIFACTS['statement_graph']}",
            source_path=source_directory / GRAPH_FILENAME,
            description="Source-grounded statements, proofs, explicit dependencies, unresolved references, and literal term mentions.",
            stats={
                "nodes": len(graph.get("nodes") or []),
                "edges": len(graph.get("edges") or []),
                "statements": graph.get("stats", {}).get("node_type_counts", {}).get("statement"),
                "proofs": graph.get("stats", {}).get("node_type_counts", {}).get("proof"),
            },
        ),
        source_artifact(
            kind="navigation_audit",
            title="PIC navigation audit v2.1",
            url=f"{PUBLIC_ARTIFACT_DIRECTORY.as_posix()}/{PUBLIC_ARTIFACTS['navigation_audit']}",
            source_path=source_directory / AUDIT_FILENAME,
            description="Structural audit of the scaffold, including overload and attachment diagnostics.",
            stats={
                "nodes_without_statement_attachments": audit.get("no_attachment_count"),
                "overloaded_nodes": audit.get("overloaded_node_count"),
            },
        ),
    ]


def update_manifest(
    manifest: dict[str, Any], domain_meta: dict[str, Any], *, built_at: str
) -> dict[str, Any]:
    manifest["domains"] = [
        domain for domain in manifest.get("domains") or [] if domain.get("id") != DOMAIN_ID
    ]
    manifest["domains"].append(domain_meta)

    subjects = [
        dict(subject)
        for subject in manifest.get("subject_domains") or []
        if subject.get("id") != SUBJECT_ID
    ]
    for subject in subjects:
        subject["items"] = [item for item in subject.get("items") or [] if item != DOMAIN_ID]
    geometric = {
        "id": SUBJECT_ID,
        "short_name": "Geometric Analysis",
        "accent": DOMAIN_ACCENT,
        "items": [DOMAIN_ID],
    }
    algebraic_position = next(
        (index for index, subject in enumerate(subjects) if subject.get("id") == "algebraic_geometry"),
        len(subjects),
    )
    subjects.insert(algebraic_position, geometric)

    lookup = {domain["id"]: domain for domain in manifest["domains"]}
    for subject in subjects:
        rows = [lookup[item] for item in subject.get("items") or [] if item in lookup]
        subject["stats"] = {
            "collections": len(rows),
            "topics": sum(int(row.get("stats", {}).get("topics") or 0) for row in rows),
            "statements": sum(int(row.get("stats", {}).get("statements") or 0) for row in rows),
        }
    manifest["subject_domains"] = subjects
    manifest["totals"] = {
        "topics": sum(int(domain.get("stats", {}).get("topics") or 0) for domain in manifest["domains"]),
        "statements": sum(int(domain.get("stats", {}).get("statements") or 0) for domain in manifest["domains"]),
    }
    manifest["snapshot_version"] = SNAPSHOT_VERSION
    manifest["built_at"] = built_at
    manifest["pic_domain_import"] = {
        "domain_id": DOMAIN_ID,
        "subject_domain_id": SUBJECT_ID,
        "source_tree_id": "pic_detailed_tree_v2",
        "source_tree_version": "v2.1",
        "source_graph_schema_version": "0.1.0",
        "publication_boundary": "navigation scaffold placements require mathematical review; the extracted graph is source-grounded but does not certify correctness",
    }
    return manifest


def ensure_source_integrity(
    tree: dict[str, Any], registry: dict[str, Any], graph: dict[str, Any], audit: dict[str, Any]
) -> None:
    if tree.get("tree_id") != "pic_detailed_tree_v2" or tree.get("tree_version") != "v2.1":
        raise RuntimeError("Unexpected PIC navigation tree identity or version")
    if registry.get("registry_id") != "pic_concept_registry_v2":
        raise RuntimeError("Unexpected PIC concept registry identity")
    if graph.get("schema_version") != "0.1.0":
        raise RuntimeError("Unexpected PIC statement graph schema")
    if audit.get("node_count") != 530 or audit.get("leaf_count") != 415:
        raise RuntimeError("PIC navigation audit counts drifted from the reviewed v2.1 scaffold")

    graph_nodes = graph.get("nodes") or []
    graph_edges = graph.get("edges") or []
    node_ids = [str(node.get("id") or "") for node in graph_nodes]
    edge_ids = [str(edge.get("id") or "") for edge in graph_edges]
    if not all(node_ids) or len(node_ids) != len(set(node_ids)):
        raise RuntimeError("PIC graph node IDs are empty or duplicated")
    if not all(edge_ids) or len(edge_ids) != len(set(edge_ids)):
        raise RuntimeError("PIC graph edge IDs are empty or duplicated")
    node_id_set = set(node_ids)
    if any(edge.get("source") not in node_id_set or edge.get("target") not in node_id_set for edge in graph_edges):
        raise RuntimeError("PIC graph contains an edge with a missing endpoint")

    statement_ids = {
        node["id"] for node in graph_nodes if node.get("type") == "statement"
    }
    tree_nodes = [node for part in tree.get("parts") or [] for node in walk(part)]
    attached_ids = [node.get("source_statement_id") for node in tree_nodes if node.get("source_statement_id")]
    if any(statement_id not in statement_ids for statement_id in attached_ids):
        raise RuntimeError("PIC navigation tree references a missing graph statement")
    if len(tree_nodes) != audit.get("node_count") or len(attached_ids) != audit.get("leaf_count"):
        raise RuntimeError("PIC navigation tree no longer matches its audit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path.home() / "Desktop/ebooks-content",
        help="Path containing output/pic_knowledge_graph",
    )
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    args = parser.parse_args()

    source_directory = args.source_root.resolve() / SOURCE_RELATIVE
    site = args.site.resolve()
    data_directory = site / "data"
    tree_path = source_directory / TREE_FILENAME
    registry_path = source_directory / REGISTRY_FILENAME
    graph_path = source_directory / GRAPH_FILENAME
    audit_path = source_directory / AUDIT_FILENAME

    tree = read_json(tree_path)
    registry = read_json(registry_path)
    graph = read_json(graph_path)
    audit = read_json(audit_path)
    ensure_source_integrity(tree, registry, graph, audit)
    semantic_titles = load_semantic_titles(SEMANTIC_TITLES_PATH)
    ensure_semantic_title_coverage(tree, semantic_titles)
    published_tree = semanticize_tree(tree, semantic_titles)
    published_registry = semanticize_registry(registry, semantic_titles)

    node_lookup = {node["id"]: node for node in graph["nodes"]}
    statement_lookup = {
        node["id"]: node for node in graph["nodes"] if node.get("type") == "statement"
    }
    proof_lookup = {
        node["statement_id"]: node for node in graph["nodes"] if node.get("type") == "proof"
    }
    relations = relation_index(graph, node_lookup)

    parts = [
        convert_tree_node(
            part,
            depth=1,
            statement_lookup=statement_lookup,
            proof_lookup=proof_lookup,
            relations=relations,
        )
        for part in published_tree["parts"]
    ]
    root = {
        "topic_id": "PIC",
        "display_number": "PIC",
        "title": DOMAIN_TITLE,
        "topic_type": "domain",
        "depth": 0,
        "classification_axis": "geometric analysis domain",
        "top_down_role": "Positive isotropic curvature, Ricci flow, pinching families, surgery, ancient solutions, comparison machinery, and topological consequences. The v2.1 navigation is a reviewable scaffold; use the source-grounded graph sidecar for extracted proof and dependency evidence.",
        "knowledge_status": "v2_navigation_scaffold_with_source_grounded_sidecars",
        "direct_statement_count": 0,
        "direct_base_statement_count": 0,
        "direct_enrichment_statement_count": 0,
        "descendant_statement_count": sum(statement_count(part) for part in parts),
        "descendant_base_statement_count": sum(statement_count(part) for part in parts),
        "descendant_enrichment_statement_count": 0,
        "direct_content_kind_counts": {},
        "subtree_topic_count": 1 + sum(node_count(part) for part in parts),
        "children": parts,
        "knowledge_statements": [],
        "top_down_textbook_witnesses": [],
    }

    artifacts = public_artifacts(source_directory, published_tree, published_registry, graph, audit)
    artifact_directory = site / PUBLIC_ARTIFACT_DIRECTORY
    write_json(artifact_directory / PUBLIC_ARTIFACTS["navigation_view"], published_tree)
    write_json(artifact_directory / PUBLIC_ARTIFACTS["concept_registry"], published_registry)
    write_json(artifact_directory / PUBLIC_ARTIFACTS["statement_graph"], sanitize_graph(graph))
    write_json(artifact_directory / PUBLIC_ARTIFACTS["navigation_audit"], audit, pretty=True)

    shard_directory = data_directory / "shards" / DOMAIN_ID
    existing_shards = set(shard_directory.glob("*.json"))
    written_shards: set[Path] = set()
    summaries: list[dict[str, Any]] = []
    routes: dict[str, str] = {}
    total_shard_bytes = 0
    for part in parts:
        slug = part["topic_id"].lower().replace(".", "-")
        shard_path = shard_directory / f"{slug}.json"
        shard_url = f"data/shards/{DOMAIN_ID}/{shard_path.name}"
        payload = {
            "schema_version": "reasatlas-chapter-shard-v1",
            "domain_id": DOMAIN_ID,
            "chapter_id": part["topic_id"],
            "root": part,
        }
        write_json(shard_path, payload)
        written_shards.add(shard_path)
        total_shard_bytes += shard_path.stat().st_size
        for node in walk(part):
            routes[node["topic_id"]] = part["topic_id"]
        summaries.append(chapter_summary(part, shard_url))
    for stale in sorted(existing_shards - written_shards):
        stale.unlink()

    root["children"] = summaries
    built_at = datetime.now(timezone.utc).isoformat()
    domain_data = {
        "schema_version": "knowledge-classification-tree-v1",
        "generated_at": tree.get("generated_at"),
        "domain_id": DOMAIN_ID,
        "display_name": DOMAIN_TITLE,
        "construction": {
            "navigation": "PIC detailed navigation tree v2.1",
            "editorial_titles": "Stable source-statement-ID mapping with complete coverage of all 166 attached statements",
            "concepts": "PIC concept registry v2 sidecar",
            "statements": "PIC extracted statement graph schema 0.1.0 sidecar",
            "hard_boundary": "keyword-attached navigation placements require mathematical review; extracted source content is not a correctness certification",
        },
        "artifacts": artifacts,
        "roots": [root],
        "loading": {
            "mode": "chapter_shards",
            "shard_count": len(parts),
            "route_count": len(routes),
            "cache_key": built_at,
        },
        "node_routes": routes,
    }
    domain_path = data_directory / f"{DOMAIN_ID}.json"
    write_json(domain_path, domain_data)

    all_nodes = [root] + [node for part in parts for node in walk(part)]
    all_statements = [
        statement
        for node in all_nodes
        for statement in node.get("knowledge_statements") or []
    ]
    unique_source_statement_ids = {
        statement["source_graph_statement_id"] for statement in all_statements
    }
    content_kinds = Counter(statement["content_kind"] for statement in all_statements)
    graph_type_counts = Counter(node.get("type") for node in graph["nodes"])
    edge_type_counts = Counter(edge.get("type") for edge in graph["edges"])
    domain_meta = {
        "id": DOMAIN_ID,
        "short_name": DOMAIN_TITLE,
        "accent": DOMAIN_ACCENT,
        "data_url": f"data/{DOMAIN_ID}.json",
        "generated_at": tree.get("generated_at"),
        "validation_status": "PASS",
        "publication_status": "source_grounded_v2_scaffold_requires_mathematical_placement_review",
        "stats": {
            "topics": len(all_nodes),
            "statements": len(all_statements),
            "unique_source_statements": len(unique_source_statement_ids),
            "source_graph_statements": graph_type_counts["statement"],
            "source_graph_proofs": graph_type_counts["proof"],
            "source_graph_nodes": len(graph["nodes"]),
            "source_graph_edges": len(graph["edges"]),
            "resolved_dependency_edges": edge_type_counts["depends_on"],
            "unresolved_dependency_edges": edge_type_counts["depends_on_unresolved"],
            "chapters": len(parts),
            "leaf_topics": sum(1 for node in all_nodes if not node.get("children")),
            "base_statements": len(all_statements),
            "official_statements": len(all_statements),
            "intermediate_statements": 0,
            "coverage": 1.0,
            "max_depth": max(int(node.get("depth") or 0) for node in all_nodes),
            "content_kinds": dict(sorted(content_kinds.items())),
        },
        "chapters": [
            {
                "topic_id": part["topic_id"],
                "display_number": part["display_number"],
                "title": part["title"],
                "classification_axis": part["classification_axis"],
                "subtree_topic_count": part["subtree_topic_count"],
                "subtree_statement_count": statement_count(part),
            }
            for part in parts
        ],
        "source_artifacts": artifacts,
        "loading": {
            "mode": "chapter_shards",
            "shards": len(parts),
            "routes": len(routes),
            "catalog_bytes": domain_path.stat().st_size,
            "shard_bytes": total_shard_bytes,
            "pruned_shards": len(existing_shards - written_shards),
        },
    }

    manifest_path = data_directory / "manifest.json"
    manifest = update_manifest(read_json(manifest_path), domain_meta, built_at=built_at)
    write_json(manifest_path, manifest, pretty=True)

    print(
        json.dumps(
            {
                "snapshot_version": SNAPSHOT_VERSION,
                "domain_id": DOMAIN_ID,
                "topics": len(all_nodes),
                "statement_placements": len(all_statements),
                "unique_source_statements": len(unique_source_statement_ids),
                "source_graph_nodes": len(graph["nodes"]),
                "source_graph_edges": len(graph["edges"]),
                "concepts": len(registry.get("concepts") or []),
                "shards": len(parts),
                "totals": manifest["totals"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
