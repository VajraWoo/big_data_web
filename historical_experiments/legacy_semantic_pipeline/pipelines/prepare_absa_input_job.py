"""Create review-stable JSONL shards consumable by the isolated XPU environment."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source = (Path(args.nlp_input) / "sentences.parquet").as_posix().replace("'", "''")
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")
    con.execute(
        f"""
        CREATE TEMP TABLE absa_input AS
        SELECT *, hash(review_id) % {args.shard_count} AS shard_id
        FROM read_parquet('{source}')
        """
    )
    totals = con.execute(
        "SELECT count(*), count(DISTINCT review_id), count(DISTINCT parent_asin) FROM absa_input"
    ).fetchone()
    if totals[1:] != (116_728, 139):
        raise RuntimeError(f"ABSA input scope mismatch: sentences/reviews/products={totals}")

    shard_counts: list[dict[str, int]] = []
    for shard_id in range(args.shard_count):
        target = (output / f"input-{shard_id:03d}.ndjson").as_posix().replace("'", "''")
        count = con.execute(
            "SELECT count(*), count(DISTINCT review_id) FROM absa_input WHERE shard_id = ?",
            [shard_id],
        ).fetchone()
        con.execute(
            f"""
            COPY (
                SELECT sentence_id, review_id, parent_asin, sentence_index,
                       sentence_text, char_start, char_end
                FROM absa_input WHERE shard_id = {shard_id}
                ORDER BY parent_asin, review_id, sentence_index
            ) TO '{target}' (FORMAT JSON)
            """
        )
        shard_counts.append(
            {"shard_id": shard_id, "sentence_count": count[0], "review_count": count[1]}
        )
    con.close()
    summary = {
        "status": "ready",
        "source": str(Path(args.nlp_input)),
        "shard_count": args.shard_count,
        "sentence_count": totals[0],
        "review_count": totals[1],
        "product_count": totals[2],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "shards": shard_counts,
    }
    (output / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nlp-input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--shard-count", type=int, default=24)
    run(parser.parse_args())
