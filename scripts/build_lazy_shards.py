#!/usr/bin/env python3
"""Split ReasAtlas domain payloads into lightweight catalogues and chapter shards."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("children", []):
        yield from walk(child)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(compact_json(value), encoding="utf-8")
    temporary.replace(path)


def write_pretty_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


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
            "lazy_child_count": len(chapter.get("children", [])),
        }
    )
    return summary


def shard_domain(data_path: Path, domain_id: str) -> dict[str, int | str]:
    data = json.loads(data_path.read_text(encoding="utf-8"))
    if data.get("loading", {}).get("mode") == "chapter_shards":
        raise RuntimeError(
            f"{data_path} is already sharded; regenerate the full domain JSON before running this script again"
        )

    shard_directory = data_path.parent / "shards" / domain_id
    existing_shards = set(shard_directory.glob("*.json"))
    written_shards: set[Path] = set()
    routes: dict[str, str] = {}
    shard_count = 0
    total_shard_bytes = 0

    for root in data.get("roots", []):
        summaries = []
        for chapter in root.get("children", []):
            chapter_id = chapter["topic_id"]
            slug = re.sub(r"[^a-z0-9]+", "-", chapter_id.lower()).strip("-")
            shard_path = shard_directory / f"{slug}.json"
            shard_url = f"data/shards/{domain_id}/{shard_path.name}"
            payload = {
                "schema_version": "reasatlas-chapter-shard-v1",
                "domain_id": domain_id,
                "chapter_id": chapter_id,
                "root": chapter,
            }
            write_json(shard_path, payload)
            written_shards.add(shard_path)
            total_shard_bytes += shard_path.stat().st_size
            shard_count += 1
            for node in walk(chapter):
                routes[node["topic_id"]] = chapter_id
            summaries.append(chapter_summary(chapter, shard_url))
        root["children"] = summaries

    pruned_shards = 0
    for orphan in sorted(existing_shards - written_shards):
        if orphan.is_symlink() or not orphan.is_file() or orphan.parent.resolve() != shard_directory.resolve():
            raise RuntimeError(f"Refusing to remove unexpected shard path: {orphan}")
        orphan.unlink()
        pruned_shards += 1

    data["loading"] = {
        "mode": "chapter_shards",
        "shard_count": shard_count,
        "route_count": len(routes),
        "cache_key": data.get("generated_at"),
    }
    data["node_routes"] = routes
    write_json(data_path, data)
    return {
        "mode": "chapter_shards",
        "shards": shard_count,
        "routes": len(routes),
        "catalog_bytes": data_path.stat().st_size,
        "shard_bytes": total_shard_bytes,
        "pruned_shards": pruned_shards,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--site",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "site",
        help="Path to the static site directory",
    )
    args = parser.parse_args()
    data_directory = args.site.resolve() / "data"
    manifest_path = data_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for domain in manifest["domains"]:
        data_path = args.site.resolve() / domain["data_url"]
        report = shard_domain(data_path, domain["id"])
        domain["loading"] = report
        print(
            f"{domain['id']}: {report['shards']} shards, "
            f"catalog {report['catalog_bytes']:,} bytes, payloads {report['shard_bytes']:,} bytes, "
            f"pruned {report['pruned_shards']} stale shards"
        )

    manifest["loading"] = {
        "mode": "chapter_shards",
        "cache_strategy": "versioned_url_memory_and_http_cache",
    }
    manifest["built_at"] = datetime.now(timezone.utc).isoformat()
    write_pretty_json(manifest_path, manifest)


if __name__ == "__main__":
    main()
