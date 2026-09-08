"""Prepare category-level T008 candidates from T007 v2.1 outputs.

Design:
- Stream T007 JSONL; do not load all insights into memory.
- Join parent_asin -> product_category from the canonical NLP input parquet.
- Default to current_product only.
- Keep polarity as a grouping dimension for candidate discovery; this does NOT freeze
  the final mixed-polarity/taxonomy semantics.
- Produce one NDJSON candidate file per product_category.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd


ACCEPTED_STATUSES = {"success", "partial_success", "success_no_insight"}


def _slug(text: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip()).strip("-").lower()
    return value[:80] or "unknown-category"


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _candidate_text(topic_raw: str, evidence: str, mode: str) -> str:
    if mode == "topic":
        return topic_raw
    if mode == "evidence":
        return evidence
    return f"{topic_raw}: {evidence}" if topic_raw else evidence


def _load_product_map(parquet_path: Path) -> dict[str, dict[str, str]]:
    df = pd.read_parquet(parquet_path)
    required = {"parent_asin", "product_category"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"metadata parquet missing required columns: {sorted(missing)}")

    title_col = "product_title" if "product_title" in df.columns else (
        "title" if "title" in df.columns else None
    )
    result: dict[str, dict[str, str]] = {}
    for row in df.itertuples(index=False):
        parent_asin = _norm(getattr(row, "parent_asin"))
        if not parent_asin:
            continue
        result[parent_asin] = {
            "product_category": _norm(getattr(row, "product_category")),
            "product_title": _norm(getattr(row, title_col)) if title_col else "",
        }
    if not result:
        raise RuntimeError("metadata parquet produced an empty parent_asin map")
    return result


def run(args: argparse.Namespace) -> None:
    t007_path = Path(args.t007)
    metadata_path = Path(args.metadata)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    product_map = _load_product_map(metadata_path)
    handles: dict[str, Any] = {}
    category_by_slug: dict[str, str] = {}
    counters = Counter()
    category_counts = Counter()
    polarity_counts = Counter()
    scope_counts = Counter()
    status_counts = Counter()
    malformed_examples: list[dict[str, Any]] = []

    try:
        with t007_path.open("r", encoding="utf-8") as source:
            for line_no, line in enumerate(source, 1):
                if not line.strip():
                    continue
                counters["reviews_seen"] += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    counters["json_decode_failures"] += 1
                    if len(malformed_examples) < 20:
                        malformed_examples.append({"line": line_no, "error": str(exc)})
                    continue

                status = _norm(record.get("processing_status"))
                status_counts[status] += 1
                if status not in ACCEPTED_STATUSES:
                    counters["reviews_skipped_status"] += 1
                    continue

                parent_asin = _norm(record.get("parent_asin"))
                meta = product_map.get(parent_asin)
                if meta is None:
                    counters["reviews_missing_product_metadata"] += 1
                    continue

                insights = record.get("insights")
                if not isinstance(insights, list):
                    counters["reviews_non_list_insights"] += 1
                    continue

                for insight_index, insight in enumerate(insights):
                    counters["insights_seen"] += 1
                    if not isinstance(insight, dict):
                        counters["insights_non_object"] += 1
                        continue

                    target_scope = _norm(insight.get("target_scope"))
                    scope_counts[target_scope] += 1
                    if args.current_product_only and target_scope != "current_product":
                        counters["insights_skipped_scope"] += 1
                        continue

                    topic_raw = _norm(insight.get("topic_raw"))
                    evidence = _norm(insight.get("evidence"))
                    polarity = _norm(insight.get("polarity")).lower() or "unknown"
                    if polarity not in args.polarities:
                        counters["insights_skipped_polarity"] += 1
                        continue
                    if not topic_raw and not evidence:
                        counters["insights_empty_text"] += 1
                        continue

                    category = meta["product_category"] or "Unknown"
                    slug = _slug(category)
                    category_by_slug[slug] = category
                    handle = handles.get(slug)
                    if handle is None:
                        handle = (output / f"candidates-{slug}.ndjson").open(
                            "w", encoding="utf-8", newline="\n"
                        )
                        handles[slug] = handle

                    review_id = _norm(record.get("review_id"))
                    raw_key = (
                        f"{review_id}|{parent_asin}|{insight_index}|"
                        f"{topic_raw}|{evidence}|{target_scope}|{polarity}"
                    )
                    candidate_id = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
                    candidate = {
                        "candidate_id": candidate_id,
                        "review_id": review_id,
                        "parent_asin": parent_asin,
                        "product_title": meta["product_title"],
                        "product_category": category,
                        "polarity": polarity,
                        "target_scope": target_scope,
                        "topic_raw": topic_raw,
                        "evidence": evidence,
                        "candidate_text": _candidate_text(topic_raw, evidence, args.text_mode),
                        "t007_processing_status": status,
                    }
                    handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
                    counters["candidates_written"] += 1
                    category_counts[category] += 1
                    polarity_counts[polarity] += 1
    finally:
        for handle in handles.values():
            handle.close()

    manifest = {
        "stage": "t008_candidate_preparation",
        "status": "ready",
        "t007_path": str(t007_path),
        "metadata_path": str(metadata_path),
        "current_product_only": args.current_product_only,
        "text_mode": args.text_mode,
        "polarities": sorted(args.polarities),
        "accepted_t007_statuses": sorted(ACCEPTED_STATUSES),
        "counters": dict(counters),
        "t007_status_counts": dict(status_counts),
        "target_scope_counts": dict(scope_counts),
        "polarity_counts": dict(polarity_counts),
        "category_counts": dict(sorted(category_counts.items())),
        "category_files": {
            slug: {
                "product_category": category,
                "file": f"candidates-{slug}.ndjson",
                "candidate_count": category_counts[category],
            }
            for slug, category in sorted(category_by_slug.items())
        },
        "malformed_examples": malformed_examples,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--t007", required=True, help="t007_full_v2_1_1024_results.jsonl")
    parser.add_argument("--metadata", required=True, help="review_inputs.parquet")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--text-mode",
        choices=("topic_evidence", "topic", "evidence"),
        default="topic_evidence",
        help="Text sent to MiniLM. Default keeps topic label plus supporting evidence.",
    )
    parser.add_argument(
        "--polarities",
        default="positive,negative,neutral",
        help="Comma-separated polarities to retain.",
    )
    parser.add_argument(
        "--include-non-current-product",
        action="store_true",
        help="By default only target_scope=current_product enters T008 candidates.",
    )
    ns = parser.parse_args()
    ns.polarities = {x.strip().lower() for x in ns.polarities.split(",") if x.strip()}
    ns.current_product_only = not ns.include_non_current_product
    run(ns)
