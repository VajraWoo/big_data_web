"""Prepare unique negative-ABSA evidence for current-product attribution."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


def run(args):
    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    aspects = (Path(args.absa_root) / "review_aspects.parquet").as_posix().replace("'", "''")
    products = Path(args.products).as_posix().replace("'", "''")
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute(f"""
        CREATE TEMP TABLE evidence AS
        SELECT md5(a.parent_asin || '|' || a.review_id || '|' || a.sentence_id) AS evidence_id,
               a.parent_asin, a.review_id, a.sentence_id, a.sentence_text,
               p.title AS product_title, p.product_category,
               list_sort(list_distinct(list(a.aspect_id))) AS aspect_ids,
               list_sort(list_distinct(list(lower(trim(a.aspect_text))))) AS attributes
        FROM read_parquet('{aspects}') a
        JOIN read_parquet('{products}') p USING(parent_asin)
        WHERE a.aspect_sentiment='negative'
        GROUP BY a.parent_asin, a.review_id, a.sentence_id, a.sentence_text,
                 p.title, p.product_category
    """)
    counts = con.execute("""
        SELECT count(*), count(DISTINCT evidence_id), count(DISTINCT review_id),
               count(DISTINCT parent_asin), count(*) FILTER (
                   WHERE sentence_text IS NULL OR trim(sentence_text)='' OR
                         product_title IS NULL OR trim(product_title)=''
               ) FROM evidence
    """).fetchone()
    if counts[0] != counts[1] or counts[3] != 139 or counts[4] != 0:
        raise RuntimeError(f"attribution input validation failed: {counts}")
    shard_counts = []
    for shard_id in range(args.shard_count):
        target = (output / f"input-{shard_id:03d}.ndjson").as_posix().replace("'", "''")
        count = con.execute(
            f"SELECT count(*) FROM evidence WHERE hash(evidence_id)%{args.shard_count}={shard_id}"
        ).fetchone()[0]
        con.execute(f"""
            COPY (SELECT * FROM evidence
                  WHERE hash(evidence_id)%{args.shard_count}={shard_id}
                  ORDER BY parent_asin, evidence_id)
            TO '{target}' (FORMAT JSON)
        """)
        shard_counts.append({"shard_id": shard_id, "evidence_count": count})
    con.close()
    summary = {
        "status": "ready", "evidence_count": counts[0], "review_count": counts[2],
        "product_count": counts[3], "shard_count": args.shard_count,
        "elapsed_seconds": round(time.perf_counter()-started, 3), "shards": shard_counts,
    }
    (output / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "shards"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--absa-root", required=True)
    parser.add_argument("--products", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--shard-count", type=int, default=24)
    run(parser.parse_args())
