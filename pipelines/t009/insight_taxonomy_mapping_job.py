from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


MAPPED = "mapped_by_cluster"
UNMAPPED = "unmapped_no_cluster"


def read_ndjson(path: Path) -> Iterator[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            yield line_number, row


def ndjson_files(directory: Path, pattern: str) -> list[Path]:
    files = sorted(directory.glob(pattern))
    if not files:
        raise ValueError(f"no files matching {pattern!r} under {directory}")
    return files


def required(row: dict, field: str, source: Path, line_number: int) -> str:
    value = row.get(field)
    if value is None or str(value) == "":
        raise ValueError(f"missing {field} at {source}:{line_number}")
    return str(value)


def load_taxonomy(taxonomy_dir: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    taxonomy: dict[str, dict] = {}
    taxonomy_path = taxonomy_dir / "taxonomy.ndjson"
    for line_number, row in read_ndjson(taxonomy_path):
        taxonomy_id = required(row, "taxonomy_id", taxonomy_path, line_number)
        if taxonomy_id in taxonomy:
            raise ValueError(f"duplicate taxonomy_id: {taxonomy_id}")
        taxonomy[taxonomy_id] = row

    cluster_map: dict[str, dict] = {}
    mapping_path = taxonomy_dir / "cluster-to-taxonomy.ndjson"
    for line_number, row in read_ndjson(mapping_path):
        cluster_id = required(row, "first_level_cluster_id", mapping_path, line_number)
        taxonomy_id = required(row, "taxonomy_id", mapping_path, line_number)
        if cluster_id in cluster_map:
            raise ValueError(f"duplicate first_level_cluster_id: {cluster_id}")
        if taxonomy_id not in taxonomy:
            raise ValueError(f"unknown taxonomy_id {taxonomy_id} for cluster {cluster_id}")
        if row.get("product_category") != taxonomy[taxonomy_id].get("product_category"):
            raise ValueError(f"category mismatch between cluster mapping {cluster_id} and taxonomy {taxonomy_id}")
        cluster_map[cluster_id] = row
    return taxonomy, cluster_map


def load_members(cluster_dir: Path, cluster_map: dict[str, dict]) -> dict[str, dict]:
    members: dict[str, dict] = {}
    for path in ndjson_files(cluster_dir, "members-*.ndjson"):
        for line_number, row in read_ndjson(path):
            candidate_id = required(row, "candidate_id", path, line_number)
            cluster_id = required(row, "cluster_id", path, line_number)
            if candidate_id in members:
                raise ValueError(f"duplicate candidate_id in cluster members: {candidate_id}")
            if cluster_id not in cluster_map:
                raise ValueError(f"cluster member references unmapped cluster_id: {cluster_id}")
            if row.get("product_category") != cluster_map[cluster_id].get("product_category"):
                raise ValueError(f"category mismatch for cluster member {candidate_id}")
            members[candidate_id] = row
    return members


def validate_candidates(candidate_files: list[Path], members: dict[str, dict]) -> tuple[set[str], Counter, dict[str, Counter]]:
    candidate_ids: set[str] = set()
    polarity_counts: Counter = Counter()
    category_counts: dict[str, Counter] = defaultdict(Counter)
    identity_fields = ("review_id", "parent_asin", "product_category", "polarity")

    for path in candidate_files:
        for line_number, row in read_ndjson(path):
            candidate_id = required(row, "candidate_id", path, line_number)
            if candidate_id in candidate_ids:
                raise ValueError(f"duplicate candidate_id in candidates: {candidate_id}")
            candidate_ids.add(candidate_id)
            category = required(row, "product_category", path, line_number)
            polarity = required(row, "polarity", path, line_number)
            status = MAPPED if candidate_id in members else UNMAPPED
            polarity_counts[(polarity, status)] += 1
            category_counts[category][status] += 1

            member = members.get(candidate_id)
            if member:
                for field in identity_fields:
                    if row.get(field) != member.get(field):
                        raise ValueError(f"{field} mismatch for candidate/member {candidate_id}")

    orphan_members = set(members).difference(candidate_ids)
    if orphan_members:
        example = sorted(orphan_members)[0]
        raise ValueError(f"orphan cluster member candidate_id: {example}")
    return candidate_ids, polarity_counts, category_counts


def build_mappings(candidate_dir: Path, cluster_dir: Path, taxonomy_dir: Path, output_dir: Path) -> dict:
    candidate_dir = Path(candidate_dir)
    cluster_dir = Path(cluster_dir)
    taxonomy_dir = Path(taxonomy_dir)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")

    candidate_files = ndjson_files(candidate_dir, "candidates-*.ndjson")
    taxonomy, cluster_map = load_taxonomy(taxonomy_dir)
    members = load_members(cluster_dir, cluster_map)
    candidate_ids, polarity_counts, category_counts = validate_candidates(candidate_files, members)

    status_counts = {
        MAPPED: len(members),
        UNMAPPED: len(candidate_ids) - len(members),
    }
    report = {
        "stage": "t009_insight_taxonomy_mapping",
        "status": "ready",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": len(candidate_ids),
        "mapped_count": len(members),
        "unmapped_count": len(candidate_ids) - len(members),
        "taxonomy_theme_count": len(taxonomy),
        "first_level_cluster_count": len(cluster_map),
        "mapping_status_counts": status_counts,
        "candidate_duplicate_count": 0,
        "member_duplicate_count": 0,
        "orphan_member_count": 0,
        "identity_mismatch_count": 0,
        "inputs": {
            "candidate_dir": str(candidate_dir),
            "cluster_dir": str(cluster_dir),
            "taxonomy_dir": str(taxonomy_dir),
        },
    }

    temp_dir = output_dir.with_name(output_dir.name + ".tmp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    try:
        output_path = temp_dir / "insight-taxonomy-mappings.ndjson"
        with output_path.open("w", encoding="utf-8", newline="\n") as handle:
            for path in candidate_files:
                for line_number, candidate in read_ndjson(path):
                    candidate_id = required(candidate, "candidate_id", path, line_number)
                    member = members.get(candidate_id)
                    if member is None:
                        cluster_id = taxonomy_id = canonical_name = None
                        center_similarity = None
                        mapping_status = UNMAPPED
                    else:
                        cluster_id = str(member["cluster_id"])
                        mapped = cluster_map[cluster_id]
                        taxonomy_id = str(mapped["taxonomy_id"])
                        canonical_name = taxonomy[taxonomy_id].get("canonical_theme_name")
                        center_similarity = member.get("center_similarity")
                        mapping_status = MAPPED
                    output = dict(candidate)
                    output.update(
                        {
                            "cluster_id": cluster_id,
                            "taxonomy_id": taxonomy_id,
                            "canonical_theme_name": canonical_name,
                            "center_similarity": center_similarity,
                            "mapping_status": mapping_status,
                        }
                    )
                    handle.write(json.dumps(output, ensure_ascii=False) + "\n")

        with (temp_dir / "category-summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["product_category", "candidate_count", "mapped_by_cluster", "unmapped_no_cluster", "coverage_pct"],
            )
            writer.writeheader()
            for category in sorted(category_counts):
                counts = category_counts[category]
                total = counts[MAPPED] + counts[UNMAPPED]
                writer.writerow(
                    {
                        "product_category": category,
                        "candidate_count": total,
                        "mapped_by_cluster": counts[MAPPED],
                        "unmapped_no_cluster": counts[UNMAPPED],
                        "coverage_pct": round(100 * counts[MAPPED] / total, 2),
                    }
                )

        polarity_summary = []
        for polarity in sorted({key[0] for key in polarity_counts}):
            mapped_count = polarity_counts[(polarity, MAPPED)]
            unmapped_count = polarity_counts[(polarity, UNMAPPED)]
            polarity_summary.append(
                {
                    "polarity": polarity,
                    "candidate_count": mapped_count + unmapped_count,
                    MAPPED: mapped_count,
                    UNMAPPED: unmapped_count,
                }
            )
        report["polarity_summary"] = polarity_summary
        (temp_dir / "validation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temp_dir.rename(output_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic T009 insight-to-taxonomy mappings.")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--clusters", type=Path, required=True)
    parser.add_argument("--taxonomy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_mappings(args.candidates, args.clusters, args.taxonomy, args.output)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
