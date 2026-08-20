#!/usr/bin/env python3
"""Synchronize the v64 extracted major tracks into the checked-in web snapshot."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "site"
DEFAULT_SOURCE = Path(
    "/root/workspace/lcy/optistacks/outputs/releases/v64_extracted_major_tracks_candidate"
)
SNAPSHOT_VERSION = "20260819_v64_major_tracks_v1"
TREE_FILE = "opt_stacks_v64_extracted_major_tracks_candidate.json"

EXTRACTIONS = (
    {
        "part_id": "A25",
        "domain_id": "derivative_free_optimization",
        "title": "Derivative-Free Optimization",
        "accent": "#b2693f",
        "source_domain_id": "specialized_continuous_methods",
        "root_id": "A07.C01",
    },
    {
        "part_id": "A26",
        "domain_id": "manifold_optimization",
        "title": "Manifold Optimization",
        "accent": "#26756d",
        "source_domain_id": "specialized_continuous_methods",
        "root_id": "A07.C02",
    },
    {
        "part_id": "A27",
        "domain_id": "distributed_optimization",
        "title": "Distributed Optimization",
        "accent": "#6d5bd0",
        "source_domain_id": "specialized_continuous_methods",
        "root_id": "A07.C03",
    },
    {
        "part_id": "A28",
        "domain_id": "robust_optimization",
        "title": "Robust Optimization",
        "accent": "#88613d",
        "source_domain_id": "optimization_under_uncertainty",
        "root_id": "A16.C05",
    },
    {
        "part_id": "A29",
        "domain_id": "simulation_optimization",
        "title": "Simulation Optimization",
        "accent": "#4d718e",
        "source_domain_id": "optimization_under_uncertainty",
        "root_id": "A16.C06",
    },
)
FRONT_DOMAIN_IDS = (
    "manifold_optimization",
    "derivative_free_optimization",
    "distributed_optimization",
)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def renumber(node: dict[str, Any], old_prefix: str, new_prefix: str) -> None:
    number = str(node.get("display_number") or "")
    if number == old_prefix or number.startswith(old_prefix + "."):
        node["display_number"] = new_prefix + number[len(old_prefix):]
    for child in node.get("children") or []:
        renumber(child, old_prefix, new_prefix)


def shift_depth(node: dict[str, Any], delta: int) -> None:
    node["depth"] = max(0, int(node.get("depth") or 0) + delta)
    for child in node.get("children") or []:
        shift_depth(child, delta)


def promote_web_root(chapter: dict[str, Any], config: dict[str, str]) -> None:
    old_prefix = str(chapter.get("display_number") or "")
    new_prefix = config["part_id"][1:]
    if old_prefix != new_prefix:
        renumber(chapter, old_prefix, new_prefix)
    if int(chapter.get("depth") or 0) > 0:
        shift_depth(chapter, -int(chapter.get("depth") or 0))
    chapter.update({
        "display_number": new_prefix,
        "topic_type": "part",
        "classification_axis": "independent major optimization track",
        "published_part_id": config["part_id"],
        "presentation_policy": "promoted_root_without_wrapper",
    })


def chapter_summary(chapter: dict[str, Any], shard_url: str) -> dict[str, Any]:
    summary = {
        key: deepcopy(value)
        for key, value in chapter.items()
        if key not in {"children", "knowledge_statements", "top_down_textbook_witnesses"}
    }
    summary.update({
        "children": [],
        "knowledge_statements": [],
        "top_down_textbook_witnesses": [],
        "shard_url": shard_url,
        "lazy_content": True,
        "lazy_child_count": len(chapter.get("children") or []),
    })
    return summary


def statement_stats(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    statements = [s for node in nodes for s in node.get("knowledge_statements") or []]
    official = sum(s.get("layer_role") == "base_statement_layer" for s in statements)
    kinds = Counter(str(s.get("content_kind") or "unknown") for s in statements)
    return {
        "statements": len(statements),
        "official_statements": official,
        "intermediate_statements": len(statements) - official,
        "base_statements": official,
        "content_kinds": dict(sorted(kinds.items())),
    }


def make_domain_meta(
    config: dict[str, str],
    chapter: dict[str, Any],
    shard_url: str,
    generated_at: str,
) -> dict[str, Any]:
    nodes = list(walk(chapter))
    stats = statement_stats(nodes)
    stats.update({
        "topics": len(nodes),
        "chapters": 1,
        "leaf_topics": sum(not (node.get("children") or []) for node in nodes),
        "coverage": 1.0,
        "max_depth": max((int(node.get("depth") or 0) for node in nodes), default=0),
    })
    return {
        "id": config["domain_id"],
        "short_name": config["title"],
        "accent": config["accent"],
        "data_url": f"data/{config['domain_id']}.json",
        "generated_at": generated_at,
        "validation_status": "PASS",
        "publication_status": "v64_structural_rehome_with_v1_5_public_content_preserved",
        "stats": stats,
        "chapters": [{
            "topic_id": config["root_id"],
            "display_number": chapter.get("display_number"),
            "title": chapter.get("title"),
            "classification_axis": chapter.get("classification_axis"),
            "subtree_topic_count": len(nodes),
            "subtree_statement_count": stats["statements"],
        }],
        "loading": {
            "mode": "chapter_shards",
            "shards": 1,
            "routes": len(nodes),
            "catalog_bytes": 0,
            "shard_bytes": 0,
            "pruned_shards": 0,
        },
        "source_rehome": {
            "source_domain_id": config["source_domain_id"],
            "source_root_id": config["root_id"],
            "v64_part_id": config["part_id"],
            "statements_preserved": stats["statements"],
        },
    }


def recalculate_source_domain(
    site: Path, catalog: dict[str, Any], meta: dict[str, Any]
) -> None:
    nodes = list(catalog.get("roots") or [])
    chapter_rows = []
    for root in catalog.get("roots") or []:
        for child in root.get("children") or []:
            payload = read(site / child["shard_url"])
            chapter_nodes = list(walk(payload["root"]))
            nodes.extend(chapter_nodes)
            chapter_stats = statement_stats(chapter_nodes)
            chapter_rows.append({
                "topic_id": child["topic_id"],
                "display_number": child.get("display_number"),
                "title": child.get("title"),
                "classification_axis": child.get("classification_axis"),
                "subtree_topic_count": len(chapter_nodes),
                "subtree_statement_count": chapter_stats["statements"],
            })
    stats = statement_stats(nodes)
    stats.update({
        "topics": len(nodes),
        "chapters": len(chapter_rows),
        "leaf_topics": sum(not (node.get("children") or []) for node in nodes),
        "coverage": 1.0,
        "max_depth": max((int(node.get("depth") or 0) for node in nodes), default=0),
    })
    meta["stats"] = stats
    meta["chapters"] = chapter_rows
    meta["loading"].update({
        "shards": len(chapter_rows),
        "routes": len(catalog.get("node_routes") or {}),
        "catalog_bytes": (site / meta["data_url"]).stat().st_size,
        "shard_bytes": sum((site / row["shard_url"]).stat().st_size for root in catalog["roots"] for row in root.get("children") or []),
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--source-release", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    site = args.site.resolve()
    source_release = args.source_release.resolve()
    source_tree_path = source_release / TREE_FILE
    source_tree = read(source_tree_path)
    source_validation = read(source_release / "validation_report.json")
    if source_tree.get("tree_id") != "opt_stacks_v64_extracted_major_tracks_candidate":
        raise RuntimeError(f"Unexpected source tree: {source_tree.get('tree_id')}")
    if source_validation.get("status") != "PASS":
        raise RuntimeError("The v64 source release has not passed validation")

    manifest_path = site / "data/manifest.json"
    manifest = read(manifest_path)
    if manifest.get("snapshot_version") == SNAPSHOT_VERSION:
        domain_lookup = {row["id"]: row for row in manifest.get("domains") or []}
        collapsed_wrappers = 0
        for config in EXTRACTIONS:
            meta = domain_lookup[config["domain_id"]]
            catalog_path = site / meta["data_url"]
            catalog = read(catalog_path)
            catalog_root = catalog["roots"][0]
            if catalog_root.get("topic_id") == config["part_id"]:
                chapter_summary_row = catalog_root["children"][0]
                shard_path = site / chapter_summary_row["shard_url"]
                payload = read(shard_path)
                chapter = payload["root"]
                promote_web_root(chapter, config)
                payload["root"] = chapter
                write(shard_path, payload)
                catalog["roots"] = [chapter_summary(chapter, chapter_summary_row["shard_url"])]
                catalog["loading"]["route_count"] = len(catalog.get("node_routes") or {})
                catalog["loading"]["cache_key"] = datetime.now(timezone.utc).isoformat()
                write(catalog_path, catalog)
                nodes = list(walk(chapter))
                stats = statement_stats(nodes)
                stats.update({
                    "topics": len(nodes),
                    "chapters": len(chapter.get("children") or []),
                    "leaf_topics": sum(not (node.get("children") or []) for node in nodes),
                    "coverage": 1.0,
                    "max_depth": max((int(node.get("depth") or 0) for node in nodes), default=0),
                })
                meta["stats"] = stats
                meta["chapters"] = []
                meta["loading"]["catalog_bytes"] = catalog_path.stat().st_size
                meta["loading"]["shard_bytes"] = shard_path.stat().st_size
                meta["source_rehome"]["presentation_policy"] = "promoted_root_without_wrapper"
                collapsed_wrappers += 1
        front = [domain_lookup[domain_id] for domain_id in FRONT_DOMAIN_IDS]
        extracted_ids = {row["domain_id"] for row in EXTRACTIONS}
        rest = [row for row in manifest["domains"] if row["id"] not in extracted_ids]
        first_order_index = next(
            (index for index, row in enumerate(rest) if row.get("id") == "first_order_methods"),
            len(rest) - 1,
        )
        tail = [domain_lookup[row["domain_id"]] for row in EXTRACTIONS if row["domain_id"] not in FRONT_DOMAIN_IDS]
        rest = rest[: first_order_index + 1] + front + rest[first_order_index + 1 :]
        manifest["domains"] = rest + tail
        subjects = {row["id"]: row for row in manifest.get("subject_domains") or []}
        continuous = subjects.get("continuous_optimization")
        if continuous is not None:
            existing = [item for item in continuous.get("items") or [] if item not in extracted_ids]
            subject_anchor = existing.index("first_order_methods") if "first_order_methods" in existing else len(existing) - 1
            existing = (
                existing[: subject_anchor + 1]
                + list(FRONT_DOMAIN_IDS)
                + existing[subject_anchor + 1 :]
            )
            continuous["items"] = existing + [
                row["domain_id"] for row in EXTRACTIONS if row["domain_id"] not in FRONT_DOMAIN_IDS
            ]
            continuous["stats"]["collections"] = len(continuous["items"])
            continuous["stats"]["topics"] = sum(domain_lookup[item]["stats"]["topics"] for item in continuous["items"])
            continuous["stats"]["statements"] = sum(domain_lookup[item]["stats"]["statements"] for item in continuous["items"])
        for row in manifest.get("major_track_extraction", {}).get("records", []):
            row["wrapper_topics_added"] = 0
            row["presentation_policy"] = "promoted_root_without_wrapper"
        manifest["legacy_domain_routes"] = {
            row["domain_id"]: {"domain_id": row["domain_id"], "default_node_id": row["root_id"]}
            for row in EXTRACTIONS
        }
        manifest["totals"] = {
            "topics": sum(row["stats"]["topics"] for row in manifest["domains"]),
            "statements": sum(row["stats"]["statements"] for row in manifest["domains"]),
        }
        manifest["built_at"] = datetime.now(timezone.utc).isoformat()
        write(manifest_path, manifest, pretty=True)
        print(json.dumps({"snapshot_version": SNAPSHOT_VERSION, "domains": len(manifest["domains"]), "collapsed_wrappers": collapsed_wrappers, "mode": "reorder_and_flatten"}, ensure_ascii=False))
        return 0
    if manifest.get("snapshot_version") != "20260819_framework_sync_v1_5":
        raise RuntimeError(f"Unexpected web baseline: {manifest.get('snapshot_version')}")
    generated_at = datetime.now(timezone.utc).isoformat()
    domain_meta = {row["id"]: row for row in manifest.get("domains") or []}
    catalogs = {
        domain_id: read(site / meta["data_url"])
        for domain_id, meta in domain_meta.items()
    }
    new_domains: list[dict[str, Any]] = []
    extraction_report: list[dict[str, Any]] = []

    for config in EXTRACTIONS:
        source_domain_id = config["source_domain_id"]
        source_catalog = catalogs[source_domain_id]
        source_root = source_catalog["roots"][0]
        matches = [c for c in source_root.get("children") or [] if c.get("topic_id") == config["root_id"]]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one {config['root_id']} chapter, found {len(matches)}")
        old_summary = matches[0]
        old_shard_path = site / old_summary["shard_url"]
        payload = read(old_shard_path)
        chapter = payload["root"]
        if chapter.get("topic_id") != config["root_id"]:
            raise RuntimeError(f"Shard root mismatch: {config['root_id']}")
        old_prefix = str(chapter.get("display_number"))
        new_prefix = config["part_id"][1:]
        renumber(chapter, old_prefix, new_prefix)
        shift_depth(chapter, -int(chapter.get("depth") or 0))
        promote_web_root(chapter, config)

        new_shard_url = f"data/shards/{config['domain_id']}/{config['root_id'].lower().replace('.', '-')}.json"
        new_shard_path = site / new_shard_url
        write(new_shard_path, {
            "schema_version": "reasatlas-chapter-shard-v1",
            "domain_id": config["domain_id"],
            "chapter_id": config["root_id"],
            "root": chapter,
        })
        summary = chapter_summary(chapter, new_shard_url)
        chapter_nodes = list(walk(chapter))
        statement_count = sum(len(node.get("knowledge_statements") or []) for node in chapter_nodes)
        catalog = {
            "schema_version": "knowledge-classification-tree-v1",
            "generated_at": generated_at,
            "domain_id": config["domain_id"],
            "display_name": config["title"],
            "construction": {
                "top_down": "independent Part extracted by the validated v64 major-track directory update",
                "bottom_up": "public statements preserved exactly from the 20260819_framework_sync_v1_5 snapshot",
                "hard_boundary": "source placement and mechanical import do not certify mathematical correctness",
            },
            "roots": [summary],
            "loading": {"mode": "chapter_shards", "shard_count": 1, "route_count": len(chapter_nodes), "cache_key": generated_at},
            "node_routes": {node["topic_id"]: config["root_id"] for node in chapter_nodes},
        }
        data_path = site / f"data/{config['domain_id']}.json"
        write(data_path, catalog)
        new_meta = make_domain_meta(config, chapter, new_shard_url, generated_at)
        new_meta["loading"]["catalog_bytes"] = data_path.stat().st_size
        new_meta["loading"]["shard_bytes"] = new_shard_path.stat().st_size
        new_domains.append(new_meta)

        moved_ids = {node["topic_id"] for node in chapter_nodes}
        source_root["children"] = [c for c in source_root.get("children") or [] if c.get("topic_id") != config["root_id"]]
        source_catalog["node_routes"] = {
            node_id: route
            for node_id, route in (source_catalog.get("node_routes") or {}).items()
            if node_id not in moved_ids
        }
        source_catalog["loading"]["shard_count"] = len(source_root["children"])
        source_catalog["loading"]["route_count"] = len(source_catalog["node_routes"])
        if old_shard_path != new_shard_path:
            old_shard_path.unlink()
        extraction_report.append({
            "part_id": config["part_id"],
            "domain_id": config["domain_id"],
            "root_id": config["root_id"],
            "source_domain_id": source_domain_id,
            "topics_moved": len(chapter_nodes),
            "wrapper_topics_added": 0,
            "presentation_policy": "promoted_root_without_wrapper",
            "statements_preserved": statement_count,
            "old_display_prefix": old_prefix,
            "new_display_prefix": new_prefix,
        })

    for source_domain_id in {row["source_domain_id"] for row in EXTRACTIONS}:
        catalogs[source_domain_id]["construction"]["top_down"] = (
            "published directory subset synchronized to the validated v64 major-track candidate"
        )
        write(site / domain_meta[source_domain_id]["data_url"], catalogs[source_domain_id])
        recalculate_source_domain(site, catalogs[source_domain_id], domain_meta[source_domain_id])

    extracted_ids = {x["domain_id"] for x in EXTRACTIONS}
    existing_order = [row for row in manifest["domains"] if row["id"] not in extracted_ids]
    new_domain_lookup = {row["id"]: row for row in new_domains}
    first_order_index = next(
        (index for index, row in enumerate(existing_order) if row.get("id") == "first_order_methods"),
        len(existing_order) - 1,
    )
    existing_order = (
        existing_order[: first_order_index + 1]
        + [new_domain_lookup[domain_id] for domain_id in FRONT_DOMAIN_IDS]
        + existing_order[first_order_index + 1 :]
    )
    manifest["domains"] = existing_order + [
        row for row in new_domains if row["id"] not in FRONT_DOMAIN_IDS
    ]
    manifest["snapshot_version"] = SNAPSHOT_VERSION
    manifest["built_at"] = generated_at
    manifest["directory_snapshot"] = {
        "tree_id": source_tree.get("tree_id"),
        "path": str(source_tree_path),
        "release_version": source_tree.get("release_version"),
        "status": source_tree.get("release_status"),
        "canonical_tree_mutated": source_tree.get("canonical_tree_mutated"),
        "part_count": len(source_tree.get("parts") or []),
        "node_count": source_validation.get("node_count"),
    }
    manifest["major_track_extraction"] = {
        "schema_version": "web-v64-major-track-extraction-v1",
        "source_release": str(source_release),
        "source_validation_status": source_validation.get("status"),
        "policy": "move_published_subtrees_preserve_topics_and_statements",
        "records": extraction_report,
    }
    manifest["navigation_shortcuts"] = []
    manifest["legacy_domain_routes"] = {
        row["domain_id"]: {"domain_id": row["domain_id"], "default_node_id": row["root_id"]}
        for row in EXTRACTIONS
    }
    manifest["node_domain_redirects"] = {
        "specialized_continuous_methods": [
            {"node_prefix": row["root_id"], "domain_id": row["domain_id"]}
            for row in EXTRACTIONS if row["source_domain_id"] == "specialized_continuous_methods"
        ],
        "optimization_under_uncertainty": [
            {"node_prefix": row["root_id"], "domain_id": row["domain_id"]}
            for row in EXTRACTIONS if row["source_domain_id"] == "optimization_under_uncertainty"
        ],
    }
    distributed_aliases = (manifest.get("node_redirects") or {}).get("specialized_continuous_methods", {})
    manifest["node_redirects"] = {"distributed_optimization": distributed_aliases}
    compatibility = manifest.get("distributed_route_compatibility") or {}
    compatibility.setdefault("legacy_domain_routes", {})["distributed_optimization"] = {
        "domain_id": "distributed_optimization",
        "default_node_id": "A27",
    }
    manifest["distributed_route_compatibility"] = compatibility

    continuous_items = [
        "convex_analysis", "variational_analysis", "nonlinear_programming",
        "first_order_methods", *FRONT_DOMAIN_IDS, "nonsmooth_optimization", "specialized_continuous_methods",
        "convex_programming", "linear_programming", "conic_optimization",
        "quadratic_optimization", "global_optimization", "optimization_under_uncertainty",
        "robust_optimization", "simulation_optimization",
    ]
    subject_lookup = {row["id"]: row for row in manifest.get("subject_domains") or []}
    subject_lookup["continuous_optimization"]["items"] = continuous_items
    domain_lookup = {row["id"]: row for row in manifest["domains"]}
    for subject in subject_lookup.values():
        ids = [item for item in subject.get("items") or [] if item in domain_lookup]
        subject["stats"] = {
            "collections": len(ids),
            "topics": sum(domain_lookup[item]["stats"]["topics"] for item in ids),
            "statements": sum(domain_lookup[item]["stats"]["statements"] for item in ids),
        }
    manifest["subject_domains"] = list(subject_lookup.values())
    manifest["totals"] = {
        "topics": sum(row["stats"]["topics"] for row in manifest["domains"]),
        "statements": sum(row["stats"]["statements"] for row in manifest["domains"]),
    }
    write(manifest_path, manifest, pretty=True)
    print(json.dumps({
        "snapshot_version": SNAPSHOT_VERSION,
        "domains": len(manifest["domains"]),
        "topics": manifest["totals"]["topics"],
        "statements": manifest["totals"]["statements"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
