#!/usr/bin/env python3
"""Shared readers for the ReasAtlas theorem-search pilot."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterator


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "site" / "data"
ARTIFACT_ROOT = EXPERIMENT_ROOT / "artifacts"

TARGET_KINDS = ("theorem", "definition", "algorithm")
KIND_ORDER = {kind: index for index, kind in enumerate(TARGET_KINDS)}
EXCLUDED_DOMAINS = {"positive_isotropic_curvature"}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def record_uid(domain: str, shard: str, topic_id: str, statement_id: str, index: int) -> str:
    payload = "\0".join((domain, shard, topic_id, statement_id, str(index)))
    return "rec_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def stable_key(seed: int, value: str) -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest()


def manifest_domains() -> list[dict]:
    manifest = read_json(DATA_ROOT / "manifest.json")
    return [domain for domain in manifest["domains"] if domain["id"] not in EXCLUDED_DOMAINS]


def iter_nodes() -> Iterator[dict]:
    """Yield compact topic records while retaining direct statement payloads."""
    for domain_info in manifest_domains():
        domain = domain_info["id"]
        shard_dir = DATA_ROOT / "shards" / domain
        for shard_path in sorted(shard_dir.glob("*.json")):
            root = read_json(shard_path)["root"]
            stack = [(root, [], None)]
            while stack:
                node, ancestor_titles, parent_topic_id = stack.pop()
                title = str(node.get("title") or "").strip()
                topic_id = str(node.get("topic_id") or "").strip()
                path_titles = ancestor_titles + ([title] if title else [])
                yield {
                    "domain": domain,
                    "domain_name": domain_info.get("short_name", domain),
                    "shard": shard_path.name,
                    "topic_id": topic_id,
                    "parent_topic_id": parent_topic_id,
                    "title": title,
                    "depth": int(node.get("depth") or len(path_titles)),
                    "path_titles": path_titles,
                    "classification_axis": str(node.get("classification_axis") or ""),
                    "top_down_role": str(node.get("top_down_role") or ""),
                    "child_titles": [
                        str(child.get("title") or "").strip()
                        for child in (node.get("children") or [])
                        if str(child.get("title") or "").strip()
                    ],
                    "statements": node.get("knowledge_statements") or [],
                }
                for child in reversed(node.get("children") or []):
                    stack.append((child, path_titles, topic_id))


def compact_statement(node: dict, statement: dict, local_index: int) -> dict:
    statement_id = str(statement.get("statement_id") or statement.get("id") or "").strip()
    title = str(statement.get("statement_title") or statement.get("title") or "").strip()
    refs = statement.get("source_refs") or statement.get("source_witnesses") or []
    confidence = statement.get("confidence", statement.get("review_confidence", 0)) or 0
    uid = record_uid(node["domain"], node["shard"], node["topic_id"], statement_id, local_index)
    return {
        "record_uid": uid,
        "statement_id": statement_id,
        "domain": node["domain"],
        "domain_name": node["domain_name"],
        "shard": node["shard"],
        "topic_id": node["topic_id"],
        "topic_depth": node["depth"],
        "topic_path": node["path_titles"],
        "content_kind": str(statement.get("content_kind") or "").strip(),
        "title": title,
        "statement_plain": str(statement.get("statement_plain") or "").strip(),
        "statement_latex": str(statement.get("statement_latex") or "").strip(),
        "scope_note": str(statement.get("scope_note") or "").strip(),
        "assumptions_latex": [str(item) for item in (statement.get("assumptions_latex") or [])],
        "conclusion_latex": str(statement.get("conclusion_latex") or "").strip(),
        "prerequisite_node_ids": [str(item) for item in (statement.get("prerequisite_node_ids") or [])],
        "original_topic_id": str(statement.get("original_topic_id") or "").strip(),
        "mapped_topic_ids": [str(item) for item in (statement.get("mapped_topic_ids") or [])],
        "mapping_method": str(statement.get("mapping_method") or "").strip(),
        "layer_role": str(statement.get("layer_role") or "").strip(),
        "confidence": float(confidence),
        "review_status": str(statement.get("review_status") or "").strip(),
        "review_flags": [str(item) for item in (statement.get("review_flags") or [])],
        "source_ref_count": len(refs),
        "source_locators": [
            str(ref.get("locator") or ref.get("url_or_path") or ref.get("source_path") or "")
            for ref in refs[:3]
            if isinstance(ref, dict)
        ],
    }


def iter_statements() -> Iterator[dict]:
    for node in iter_nodes():
        for index, statement in enumerate(node["statements"]):
            yield compact_statement(node, statement, index)

