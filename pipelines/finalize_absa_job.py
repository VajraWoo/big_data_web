"""Merge completed ABSA shards into validated Parquet outputs."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    shard_root = Path(args.shard_root)
    run_status = json.loads((shard_root / "status.json").read_text(encoding="utf-8"))
    if run_status.get("status") not in {"ready", "completed_with_failures"}:
        raise RuntimeError(f"ABSA shards are not complete: {run_status.get('status')}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    reviews_glob = (shard_root / "reviews-*.ndjson").as_posix().replace("'", "''")
    aspects_glob = (shard_root / "aspects-*.ndjson").as_posix().replace("'", "''")
    reviews_target = (output / "review_status.parquet").as_posix().replace("'", "''")
    aspects_target = (output / "review_aspects.parquet").as_posix().replace("'", "''")

    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")
    con.execute(
        f"CREATE TEMP TABLE raw_review_status AS "
        f"SELECT * FROM read_json_auto('{reviews_glob}', format='newline_delimited')"
    )
    con.execute(
        f"CREATE TEMP TABLE review_aspects AS "
        f"SELECT * FROM read_json_auto('{aspects_glob}', format='newline_delimited') "
        f"WHERE aspect_text IS NOT NULL AND trim(aspect_text) <> ''"
    )
    con.execute(
        """
        CREATE TEMP TABLE review_status AS
        SELECT r.* EXCLUDE (aspect_count, processing_status),
               coalesce(a.aspect_count, 0) AS aspect_count,
               CASE
                   WHEN r.processing_status = 'failed' THEN 'failed'
                   WHEN coalesce(a.aspect_count, 0) > 0 THEN 'success'
                   ELSE 'no_attribute'
               END AS processing_status
        FROM raw_review_status r
        LEFT JOIN (
            SELECT review_id, count(*) AS aspect_count
            FROM review_aspects GROUP BY review_id
        ) a USING (review_id)
        """
    )
    counts = con.execute(
        """
        SELECT count(*) AS review_count,
               count(DISTINCT review_id) AS distinct_review_count,
               count(DISTINCT parent_asin) AS product_count,
               count(*) FILTER (WHERE processing_status = 'success') AS success_count,
               count(*) FILTER (WHERE processing_status = 'no_attribute') AS no_attribute_count,
               count(*) FILTER (WHERE processing_status = 'failed') AS failed_count
        FROM review_status
        """
    ).fetchone()
    if counts[0:3] != (116_728, 116_728, 139):
        raise RuntimeError(f"ABSA review reconciliation failed: {counts}")
    if counts[0] != counts[3] + counts[4] + counts[5]:
        raise RuntimeError(f"ABSA statuses do not reconcile: {counts}")

    aspect_validation = con.execute(
        """
        SELECT count(*) AS aspect_count,
               count(*) FILTER (
                   WHERE aspect_id IS NULL OR review_id IS NULL OR parent_asin IS NULL
                      OR sentence_text IS NULL OR aspect_text IS NULL OR trim(aspect_text) = ''
                      OR aspect_start < sentence_start OR aspect_end > sentence_end
                      OR aspect_end <= aspect_start
                      OR substr(sentence_text, aspect_start - sentence_start + 1,
                                aspect_end - aspect_start) <> aspect_text
                      OR aspect_sentiment NOT IN ('positive', 'neutral', 'negative', 'unknown')
                      OR model_revision <> '23e6d43431a5f96d8a7b7b9721d59bbda30cc63d'
               ) AS invalid_aspect_count
        FROM review_aspects
        """
    ).fetchone()
    if aspect_validation[1] != 0:
        raise RuntimeError(f"invalid ABSA aspect rows: {aspect_validation[1]}")

    con.execute(f"COPY review_status TO '{reviews_target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(f"COPY review_aspects TO '{aspects_target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    summary = {
        "status": "ready" if counts[5] == 0 else "completed_with_failures",
        "model_revision": run_status["model_revision"],
        "device": run_status["device"],
        "review_count": counts[0],
        "distinct_review_count": counts[1],
        "product_count": counts[2],
        "success_count": counts[3],
        "no_attribute_count": counts[4],
        "failed_count": counts[5],
        "aspect_count": aspect_validation[0],
        "invalid_aspect_count": aspect_validation[1],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "outputs": ["review_status.parquet", "review_aspects.parquet"],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-root", required=True)
    parser.add_argument("--output", required=True)
    run(parser.parse_args())
