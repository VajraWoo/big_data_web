from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


MAPPED = "mapped_by_cluster"
SUPPORTED_POLARITIES = {"negative", "mixed"}


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


def required(row: dict, field: str, source: Path, line_number: int) -> str:
    value = row.get(field)
    if value is None or str(value) == "":
        raise ValueError(f"missing {field} at {source}:{line_number}")
    return str(value)


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction)))
    return ordered[index]


def prepare_inputs(source: Path, output_dir: Path) -> dict:
    source = Path(source)
    output_dir = Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")

    candidate_ids: set[str] = set()
    groups: dict[tuple[str, str], dict] = {}
    mapped_polarities: Counter = Counter()
    missing_input_fields: Counter = Counter()

    for line_number, row in read_ndjson(source):
        candidate_id = required(row, "candidate_id", source, line_number)
        if candidate_id in candidate_ids:
            raise ValueError(f"duplicate candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)

        if row.get("mapping_status") != MAPPED:
            continue

        polarity = required(row, "polarity", source, line_number)
        mapped_polarities[polarity] += 1
        if polarity not in SUPPORTED_POLARITIES:
            continue

        parent_asin = required(row, "parent_asin", source, line_number)
        taxonomy_id = required(row, "taxonomy_id", source, line_number)
        review_id = required(row, "review_id", source, line_number)
        product_title = required(row, "product_title", source, line_number)
        product_category = required(row, "product_category", source, line_number)
        theme_name = required(row, "canonical_theme_name", source, line_number)

        key = (parent_asin, taxonomy_id)
        metadata = (product_title, product_category, theme_name)
        group = groups.setdefault(
            key,
            {
                "metadata": metadata,
                "negative": [],
                "mixed": [],
            },
        )
        if group["metadata"] != metadata:
            raise ValueError(f"inconsistent metadata for parent_asin/taxonomy_id: {key}")

        insight = {
            "candidate_id": candidate_id,
            "review_id": review_id,
            "polarity": polarity,
            "topic_raw": row.get("topic_raw"),
            "evidence": row.get("evidence"),
            "candidate_text": row.get("candidate_text"),
        }
        for field in ("topic_raw", "evidence", "candidate_text"):
            value = insight[field]
            if value is None or not str(value).strip():
                missing_input_fields[field] += 1
        group[polarity].append(insight)

    triggered = [
        (key, group)
        for key, group in groups.items()
        if group["negative"]
    ]
    triggered.sort(key=lambda item: (item[1]["metadata"][1], item[0][0], item[0][1]))

    output_dir.mkdir(parents=True)
    output_path = output_dir / "input.ndjson"
    category_stats: dict[str, Counter] = defaultdict(Counter)
    group_sizes: list[int] = []
    negative_total = 0
    mixed_total = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for (parent_asin, taxonomy_id), group in triggered:
            product_title, product_category, theme_name = group["metadata"]
            negative = sorted(group["negative"], key=lambda row: row["candidate_id"])
            mixed = sorted(group["mixed"], key=lambda row: row["candidate_id"])
            insights = negative + mixed
            review_ids = sorted({row["review_id"] for row in insights})
            input_id = hashlib.sha256(
                f"{parent_asin}\0{taxonomy_id}".encode("utf-8")
            ).hexdigest()[:24]

            record = {
                "input_id": input_id,
                "parent_asin": parent_asin,
                "product_title": product_title,
                "product_category": product_category,
                "taxonomy_id": taxonomy_id,
                "canonical_theme_name": theme_name,
                "negative_insight_count": len(negative),
                "mixed_insight_count": len(mixed),
                "support_insight_count": len(insights),
                "support_review_count": len(review_ids),
                "insights": insights,
            }
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

            negative_total += len(negative)
            mixed_total += len(mixed)
            group_sizes.append(len(insights))
            category_stats[product_category]["trigger_groups"] += 1
            category_stats[product_category]["negative_insights"] += len(negative)
            category_stats[product_category]["usable_mixed_insights"] += len(mixed)

    created_at = datetime.now(timezone.utc).isoformat()
    report = {
        "stage": "t011_input_preparation",
        "status": "ready",
        "created_at": created_at,
        "source": str(source),
        "source_candidate_count": len(candidate_ids),
        "mapped_polarity_counts": dict(sorted(mapped_polarities.items())),
        "trigger_group_count": len(triggered),
        "negative_insight_count": negative_total,
        "all_mapped_mixed_insight_count": mapped_polarities["mixed"],
        "usable_mixed_insight_count": mixed_total,
        "unused_mixed_insight_count": mapped_polarities["mixed"] - mixed_total,
        "missing_input_field_counts": dict(sorted(missing_input_fields.items())),
        "group_support_size": {
            "min": min(group_sizes),
            "median": percentile(group_sizes, 0.5),
            "p90": percentile(group_sizes, 0.9),
            "p95": percentile(group_sizes, 0.95),
            "p99": percentile(group_sizes, 0.99),
            "max": max(group_sizes),
        },
        "exact_once_key": ["parent_asin", "taxonomy_id"],
        "output_file": "input.ndjson",
    }

    (output_dir / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "batch.json").write_text(
        json.dumps(
            {
                "stage": "t011_input_preparation",
                "schema_version": "t011-input-v1",
                "created_at": created_at,
                "input_file": "input.ndjson",
                "input_record_count": len(triggered),
                "generation_unit": ["parent_asin", "taxonomy_id"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (output_dir / "category-summary.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["product_category", "trigger_groups", "negative_insights", "usable_mixed_insights"]
        )
        for category in sorted(category_stats):
            counts = category_stats[category]
            writer.writerow(
                [
                    category,
                    counts["trigger_groups"],
                    counts["negative_insights"],
                    counts["usable_mixed_insights"],
                ]
            )

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare deterministic T011 product-theme inputs")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = prepare_inputs(args.source, args.output_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
