#!/usr/bin/env python3
"""Export, validate, apply, and restore OptiStacks directory names.

The site stores topic titles in a lazy catalogue plus chapter shards, with
chapter summaries repeated in the catalogue and manifest.  This script uses
stable domain/topic IDs so a title can be polished outside the repository and
then written back to every copy without changing the tree structure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


WORKBOOK_FORMAT = "optistacks-directory-name-workbook-v1"
EDITABLE_FIELD = "new_title"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any, *, pretty: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    if pretty:
        payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    else:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)


def iter_objects(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_objects(child)


def is_topic_title_object(value: dict[str, Any]) -> bool:
    """Distinguish tree/manifest topics from statement payloads with titles."""
    return (
        isinstance(value.get("topic_id"), str)
        and isinstance(value.get("title"), str)
        and (
            isinstance(value.get("topic_type"), str)
            or (
                "subtree_topic_count" in value
                and isinstance(value.get("display_number"), str)
            )
        )
    )


def protected_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != EDITABLE_FIELD}


def protected_records_hash(records: list[dict[str, Any]]) -> str:
    protected = [protected_record(record) for record in records]
    protected.sort(key=lambda record: record["stable_id"])
    payload = json.dumps(
        protected,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def topic_record(
    node: dict[str, Any],
    *,
    domain_id: str,
    parent_topic_id: str | None,
    ancestor_titles: list[str],
) -> dict[str, Any]:
    topic_id = node.get("topic_id")
    title = node.get("title")
    if not isinstance(topic_id, str) or not isinstance(title, str):
        raise ValueError(f"Invalid topic node in {domain_id}: missing topic_id/title")
    return {
        "record_type": "topic",
        "stable_id": f"topic:{topic_id}",
        "domain_id": domain_id,
        "topic_id": topic_id,
        "parent_topic_id": parent_topic_id,
        "display_number": node.get("display_number", ""),
        "depth": node.get("depth"),
        "topic_type": node.get("topic_type", ""),
        "classification_axis": node.get("classification_axis", ""),
        "path_titles": [*ancestor_titles, title],
        "child_count": len(node.get("children", [])),
        "current_title": title,
        "new_title": title,
    }


def collect_subtree_records(
    node: dict[str, Any],
    *,
    domain_id: str,
    parent_topic_id: str | None,
    ancestor_titles: list[str],
    records: list[dict[str, Any]],
) -> None:
    record = topic_record(
        node,
        domain_id=domain_id,
        parent_topic_id=parent_topic_id,
        ancestor_titles=ancestor_titles,
    )
    records.append(record)
    next_ancestors = [*ancestor_titles, record["current_title"]]
    for child in node.get("children", []):
        collect_subtree_records(
            child,
            domain_id=domain_id,
            parent_topic_id=record["topic_id"],
            ancestor_titles=next_ancestors,
            records=records,
        )


def batch_payload(batch_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "format": WORKBOOK_FORMAT,
        "batch_id": batch_id,
        "editing_rule": "Change only new_title. Keep every other field and every record unchanged.",
        "records": records,
    }


def discover_export_batches(
    site: Path,
) -> tuple[list[tuple[Path, dict[str, Any]]], list[dict[str, Any]]]:
    manifest_path = site / "data/manifest.json"
    manifest = read_json(manifest_path)
    root_records: list[dict[str, Any]] = []
    batches: list[tuple[Path, dict[str, Any]]] = []
    all_records: list[dict[str, Any]] = []
    seen_topic_ids: dict[str, str] = {}

    for domain in manifest.get("domains", []):
        domain_id = domain["id"]
        catalogue_path = site / domain["data_url"]
        catalogue = read_json(catalogue_path)
        display_name = catalogue.get("display_name")
        if not isinstance(display_name, str):
            raise ValueError(f"{catalogue_path} has no string display_name")
        if domain.get("short_name") != display_name:
            raise ValueError(
                f"Domain label mismatch for {domain_id}: manifest={domain.get('short_name')!r}, "
                f"catalogue={display_name!r}"
            )

        domain_record = {
            "record_type": "domain",
            "stable_id": f"domain:{domain_id}",
            "domain_id": domain_id,
            "current_title": display_name,
            "new_title": display_name,
        }
        root_records.append(domain_record)
        all_records.append(domain_record)

        def register_topic_records(records: list[dict[str, Any]]) -> None:
            for record in records:
                topic_id = record["topic_id"]
                title = record["current_title"]
                prior = seen_topic_ids.get(topic_id)
                if prior is not None:
                    raise ValueError(
                        f"Topic ID {topic_id} appears more than once in the exported trees "
                        f"({prior!r} and {title!r})"
                    )
                seen_topic_ids[topic_id] = title
            all_records.extend(records)

        shard_index = 0

        def collect_catalogue_node(
            node: dict[str, Any],
            *,
            parent_topic_id: str | None,
            ancestor_titles: list[str],
            destination: list[dict[str, Any]],
        ) -> None:
            nonlocal shard_index
            shard_url = node.get("shard_url")
            if shard_url:
                shard_index += 1
                shard_path = site / shard_url
                shard = read_json(shard_path)
                full_root = shard.get("root")
                if not isinstance(full_root, dict):
                    raise ValueError(f"{shard_path} has no root object")
                if full_root.get("topic_id") != node.get("topic_id"):
                    raise ValueError(
                        f"Shard root mismatch: {node.get('topic_id')} vs "
                        f"{full_root.get('topic_id')} in {shard_path}"
                    )
                if full_root.get("title") != node.get("title"):
                    raise ValueError(
                        f"Shard title mismatch for {node.get('topic_id')}: "
                        f"catalogue={node.get('title')!r}, shard={full_root.get('title')!r}"
                    )
                shard_records: list[dict[str, Any]] = []
                collect_subtree_records(
                    full_root,
                    domain_id=domain_id,
                    parent_topic_id=parent_topic_id,
                    ancestor_titles=ancestor_titles,
                    records=shard_records,
                )
                register_topic_records(shard_records)
                relative_path = Path("batches") / domain_id / (
                    f"{shard_index:02d}_{shard_path.stem}.json"
                )
                batch_id = f"{domain_id}/{shard_path.stem}"
                batches.append((relative_path, batch_payload(batch_id, shard_records)))
                return

            record = topic_record(
                node,
                domain_id=domain_id,
                parent_topic_id=parent_topic_id,
                ancestor_titles=ancestor_titles,
            )
            destination.append(record)
            next_ancestors = [*ancestor_titles, record["current_title"]]
            for child in node.get("children", []):
                collect_catalogue_node(
                    child,
                    parent_topic_id=record["topic_id"],
                    ancestor_titles=next_ancestors,
                    destination=destination,
                )

        domain_root_records: list[dict[str, Any]] = []
        for root in catalogue.get("roots", []):
            collect_catalogue_node(
                root,
                parent_topic_id=None,
                ancestor_titles=[],
                destination=domain_root_records,
            )
        register_topic_records(domain_root_records)
        root_records.extend(domain_root_records)

    batches.insert(
        0,
        (
            Path("batches/00_domains_and_roots.json"),
            batch_payload("domains_and_roots", root_records),
        ),
    )
    return batches, all_records


def prompt_text() -> str:
    return """# OptiStacks 目录名称打磨任务

你是优化与变分分析领域的学术目录编辑。请打磨我上传的一个 JSON 批次中的英文目录名称。

必须遵守：

1. 只修改每条记录的 `new_title`；其余字段、记录数量、记录顺序和 JSON 结构一律不动。
2. `current_title` 是原名，不能修改。若原名已经合适，令 `new_title` 与它完全相同。
3. 名称要准确反映该节点的数学范围，不得改变概念强弱、假设、对象类别或父子层级含义。
4. 结合 `path_titles`、`parent_topic_id`、`topic_type` 和相邻记录保持层级命名一致；同一父节点下避免同名。
5. 使用简洁、自然、专业的英文 Title Case；保留必要的标准术语、连字符、数学符号和专名。
6. 不要添加解释、注释或新字段，不要删除任何记录。
7. 返回完整、有效的 UTF-8 JSON 文件，不要放进 Markdown 代码块。

处理前请先通读整个批次，统一术语后再逐项填写 `new_title`。
"""


def workbook_readme(record_count: int, topic_count: int, batch_count: int) -> str:
    return f"""# OptiStacks directory-name workbook

This workbook contains {record_count:,} visible names: {topic_count:,} topic-directory
names plus {record_count - topic_count:,} domain labels, split into {batch_count:,} upload-sized
JSON batches. Stable IDs and the original hierarchy are retained so polished names can
be applied to every catalogue, shard, and manifest copy safely.

## Web GPT workflow

1. Upload `PROMPT_FOR_WEB_GPT.md` and one file from `batches/`.
2. Ask GPT to return the complete JSON file after changing only `new_title`.
3. Replace the original batch file with the returned file. Keep its path and filename.
4. Repeat for the remaining batches. Unprocessed batches are safe because every
   `new_title` initially equals `current_title`.

Do not edit `current_title`, IDs, hierarchy/context fields, or `workbook_manifest.json`.
The validator hashes every protected field and rejects accidental structural edits.

## Validate and write back

Run from the repository root:

```bash
python3 scripts/manage_directory_names.py validate \\
  --workbook directory_names_workbook
python3 scripts/manage_directory_names.py apply \\
  --workbook directory_names_workbook
python3 scripts/manage_directory_names.py apply \\
  --workbook directory_names_workbook --write
```

The first `apply` is a dry run. The write step changes title fields only, synchronizes
all repeated copies, and refreshes `site/data/manifest.json`'s cache timestamp.

## Restore the exported names

Preview and then restore every original `current_title` from this workbook:

```bash
python3 scripts/manage_directory_names.py restore \\
  --workbook directory_names_workbook
python3 scripts/manage_directory_names.py restore \\
  --workbook directory_names_workbook --write
```

Restoration changes only the same name fields. Git remains an additional independent
rollback mechanism.
"""


def export_workbook(site: Path, output: Path, make_zip: bool) -> None:
    if output.exists():
        raise ValueError(
            f"Refusing to overwrite existing workbook directory: {output}. "
            "Move it aside or choose another --output path."
        )
    zip_path = output.with_suffix(".zip")
    if make_zip and zip_path.exists():
        raise ValueError(f"Refusing to overwrite existing archive: {zip_path}")

    batches, all_records = discover_export_batches(site)
    topic_count = sum(record["record_type"] == "topic" for record in all_records)
    domain_count = sum(record["record_type"] == "domain" for record in all_records)
    output.mkdir(parents=True)
    batch_files: list[str] = []
    for relative_path, payload in batches:
        write_json_atomic(output / relative_path, payload, pretty=True)
        batch_files.append(relative_path.as_posix())

    workbook_manifest = {
        "format": WORKBOOK_FORMAT,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "site": str(site),
        "record_count": len(all_records),
        "topic_count": topic_count,
        "domain_count": domain_count,
        "batch_count": len(batches),
        "batch_files": batch_files,
        "protected_fields_sha256": protected_records_hash(all_records),
    }
    write_json_atomic(output / "workbook_manifest.json", workbook_manifest, pretty=True)
    (output / "PROMPT_FOR_WEB_GPT.md").write_text(prompt_text(), encoding="utf-8")
    (output / "README.md").write_text(
        workbook_readme(len(all_records), topic_count, len(batches)),
        encoding="utf-8",
    )

    if make_zip:
        shutil.make_archive(
            str(output),
            "zip",
            root_dir=output.parent,
            base_dir=output.name,
        )

    print(
        f"Exported {topic_count:,} topics and {domain_count:,} domain labels "
        f"to {len(batches):,} batches in {output}"
    )
    if make_zip:
        print(f"Created upload archive: {zip_path}")


def load_workbook(workbook: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = workbook / "workbook_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Missing workbook manifest: {manifest_path}")
    manifest = read_json(manifest_path)
    if manifest.get("format") != WORKBOOK_FORMAT:
        raise ValueError(f"Unsupported workbook format in {manifest_path}")

    records: list[dict[str, Any]] = []
    for relative_name in manifest.get("batch_files", []):
        batch_path = workbook / relative_name
        if not batch_path.is_file():
            raise ValueError(f"Missing batch file: {batch_path}")
        batch = read_json(batch_path)
        if batch.get("format") != WORKBOOK_FORMAT:
            raise ValueError(f"Unsupported batch format in {batch_path}")
        batch_records = batch.get("records")
        if not isinstance(batch_records, list):
            raise ValueError(f"Batch has no records list: {batch_path}")
        records.extend(batch_records)

    if len(records) != manifest.get("record_count"):
        raise ValueError(
            f"Workbook record count changed: expected {manifest.get('record_count')}, "
            f"found {len(records)}"
        )
    stable_ids = [record.get("stable_id") for record in records]
    if any(not isinstance(stable_id, str) for stable_id in stable_ids):
        raise ValueError("Every workbook record must retain its string stable_id")
    if len(stable_ids) != len(set(stable_ids)):
        raise ValueError("Workbook contains duplicate stable_id values")

    actual_hash = protected_records_hash(records)
    expected_hash = manifest.get("protected_fields_sha256")
    if actual_hash != expected_hash:
        raise ValueError(
            "A protected field was changed. Only new_title may be edited "
            f"(expected hash {expected_hash}, found {actual_hash})."
        )

    for record in records:
        new_title = record.get("new_title")
        if not isinstance(new_title, str) or not new_title:
            raise ValueError(f"{record['stable_id']} has an empty or non-string new_title")
        if new_title != new_title.strip():
            raise ValueError(f"{record['stable_id']} new_title has leading/trailing whitespace")
        if "\n" in new_title or "\r" in new_title:
            raise ValueError(f"{record['stable_id']} new_title must be one line")

    return manifest, records


def live_name_occurrences(
    site: Path,
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[Path]]:
    data_directory = site / "data"
    json_paths = sorted(data_directory.rglob("*.json"))
    topic_titles: dict[str, set[str]] = defaultdict(set)
    domain_titles: dict[str, set[str]] = defaultdict(set)

    for path in json_paths:
        value = read_json(path)
        for obj in iter_objects(value):
            if is_topic_title_object(obj):
                topic_titles[obj["topic_id"]].add(obj["title"])

        if path.name == "manifest.json":
            for domain in value.get("domains", []):
                if isinstance(domain.get("id"), str) and isinstance(
                    domain.get("short_name"), str
                ):
                    domain_titles[domain["id"]].add(domain["short_name"])
        elif isinstance(value, dict):
            domain_id = value.get("domain_id")
            display_name = value.get("display_name")
            if isinstance(domain_id, str) and isinstance(display_name, str):
                domain_titles[domain_id].add(display_name)

    return topic_titles, domain_titles, json_paths


def validate_against_site(
    site: Path, records: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[Path]]:
    topic_records: dict[str, dict[str, Any]] = {}
    domain_records: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("record_type") == "topic":
            topic_records[record["topic_id"]] = record
        elif record.get("record_type") == "domain":
            domain_records[record["domain_id"]] = record
        else:
            raise ValueError(f"Unknown record_type for {record.get('stable_id')}")

    topic_titles, domain_titles, json_paths = live_name_occurrences(site)
    if set(topic_records) != set(topic_titles):
        missing = sorted(set(topic_titles) - set(topic_records))[:10]
        extra = sorted(set(topic_records) - set(topic_titles))[:10]
        raise ValueError(
            f"Workbook/site topic coverage differs; missing={missing}, extra={extra}"
        )
    if set(domain_records) != set(domain_titles):
        missing = sorted(set(domain_titles) - set(domain_records))[:10]
        extra = sorted(set(domain_records) - set(domain_titles))[:10]
        raise ValueError(
            f"Workbook/site domain coverage differs; missing={missing}, extra={extra}"
        )

    for topic_id, record in topic_records.items():
        allowed = {record["current_title"], record["new_title"]}
        unexpected = topic_titles[topic_id] - allowed
        if unexpected:
            raise ValueError(
                f"Live title drift for topic:{topic_id}: {sorted(unexpected)!r}; "
                f"expected original/proposed {sorted(allowed)!r}"
            )
    for domain_id, record in domain_records.items():
        allowed = {record["current_title"], record["new_title"]}
        unexpected = domain_titles[domain_id] - allowed
        if unexpected:
            raise ValueError(
                f"Live title drift for domain:{domain_id}: {sorted(unexpected)!r}; "
                f"expected original/proposed {sorted(allowed)!r}"
            )

    sibling_titles: dict[tuple[str, str | None, str], list[str]] = defaultdict(list)
    for topic_id, record in topic_records.items():
        key = (
            record["domain_id"],
            record.get("parent_topic_id"),
            record["new_title"].casefold(),
        )
        sibling_titles[key].append(topic_id)
    collisions = [
        (key, ids) for key, ids in sibling_titles.items() if len(ids) > 1
    ]
    if collisions:
        key, ids = collisions[0]
        raise ValueError(
            "Proposed sibling-title collision: "
            f"domain={key[0]}, parent={key[1]}, title={key[2]!r}, topic_ids={ids}"
        )

    return topic_records, domain_records, json_paths


def validate_workbook(site: Path, workbook: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    manifest, records = load_workbook(workbook)
    _, _, json_paths = validate_against_site(site, records)
    rename_count = sum(
        record["new_title"] != record["current_title"] for record in records
    )
    print(
        f"VALID: {manifest['record_count']:,} records across {manifest['batch_count']:,} "
        f"batches; {rename_count:,} proposed renames; site coverage is exact"
    )
    return records, json_paths


def rewrite_names(
    site: Path,
    records: list[dict[str, Any]],
    json_paths: list[Path],
    *,
    restore: bool,
    write: bool,
) -> None:
    topic_records = {
        record["topic_id"]: record
        for record in records
        if record["record_type"] == "topic"
    }
    domain_records = {
        record["domain_id"]: record
        for record in records
        if record["record_type"] == "domain"
    }
    target_field = "current_title" if restore else "new_title"
    touched_payloads: dict[Path, Any] = {}
    changed_occurrences = 0

    for path in json_paths:
        value = read_json(path)
        changed = False
        for obj in iter_objects(value):
            topic_id = obj.get("topic_id")
            if is_topic_title_object(obj) and topic_id in topic_records:
                target = topic_records[topic_id][target_field]
                if obj["title"] != target:
                    obj["title"] = target
                    changed = True
                    changed_occurrences += 1

        if path.name == "manifest.json":
            for domain in value.get("domains", []):
                domain_id = domain.get("id")
                if domain_id in domain_records:
                    target = domain_records[domain_id][target_field]
                    if domain.get("short_name") != target:
                        domain["short_name"] = target
                        changed = True
                        changed_occurrences += 1
        elif isinstance(value, dict):
            domain_id = value.get("domain_id")
            if domain_id in domain_records and isinstance(value.get("display_name"), str):
                target = domain_records[domain_id][target_field]
                if value.get("display_name") != target:
                    value["display_name"] = target
                    changed = True
                    changed_occurrences += 1

        if changed:
            touched_payloads[path] = value

    operation = "restore" if restore else "apply"
    print(
        f"{operation.upper()} {'WRITE' if write else 'DRY RUN'}: "
        f"{changed_occurrences:,} title occurrences in {len(touched_payloads):,} files"
    )
    if not write or not touched_payloads:
        return

    manifest_path = site / "data/manifest.json"
    if manifest_path not in touched_payloads:
        touched_payloads[manifest_path] = read_json(manifest_path)
    touched_payloads[manifest_path]["built_at"] = datetime.now(timezone.utc).isoformat()

    for path, value in touched_payloads.items():
        write_json_atomic(path, value, pretty=path == manifest_path)
    print(f"Wrote {len(touched_payloads):,} files and refreshed manifest built_at")


def parse_args() -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Create a Web-GPT workbook")
    export_parser.add_argument("--site", type=Path, default=repository / "site")
    export_parser.add_argument(
        "--output", type=Path, default=repository / "directory_names_workbook"
    )
    export_parser.add_argument("--zip", action="store_true", help="Also create a ZIP archive")

    for command in ("validate", "apply", "restore"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--site", type=Path, default=repository / "site")
        subparser.add_argument(
            "--workbook", type=Path, default=repository / "directory_names_workbook"
        )
        if command in {"apply", "restore"}:
            subparser.add_argument(
                "--write",
                action="store_true",
                help="Write changes; without this flag the command is a dry run",
            )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "export":
            export_workbook(args.site.resolve(), args.output.resolve(), args.zip)
            return 0

        records, json_paths = validate_workbook(
            args.site.resolve(), args.workbook.resolve()
        )
        if args.command == "validate":
            return 0
        rewrite_names(
            args.site.resolve(),
            records,
            json_paths,
            restore=args.command == "restore",
            write=args.write,
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
