"""Finalize current-product attribution and retain qualified negative ABSA rows."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


def run(args):
    started = time.perf_counter()
    input_root, shard_root = Path(args.input_root), Path(args.shard_root)
    manifest = json.loads((input_root / "manifest.json").read_text(encoding="utf-8"))
    status = json.loads((shard_root / "status.json").read_text(encoding="utf-8"))
    if status.get("status") not in {"ready", "completed_with_failures"}:
        raise RuntimeError(f"attribution inference is not complete: {status.get('status')}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    decisions = (shard_root / "decisions-*.ndjson").as_posix().replace("'", "''")
    aspects = (Path(args.absa_root) / "review_aspects.parquet").as_posix().replace("'", "''")
    con = duckdb.connect()
    con.execute(f"CREATE TEMP TABLE attribution_decisions AS SELECT * FROM read_json_auto('{decisions}', format='newline_delimited')")
    counts = con.execute("""
        SELECT count(*), count(DISTINCT evidence_id), count(DISTINCT review_id),
               count(DISTINCT parent_asin),
               count(*) FILTER (WHERE processing_status='attributed'),
               count(*) FILTER (WHERE processing_status='not_attributed'),
               count(*) FILTER (WHERE processing_status='failed'),
               count(*) FILTER (WHERE processing_status='attributed' AND NOT
                   (entailment>neutral AND entailment>contradiction))
        FROM attribution_decisions
    """).fetchone()
    if counts[0] != manifest["evidence_count"] or counts[0] != counts[1] or counts[3] != 139:
        raise RuntimeError(f"attribution identity mismatch: {counts}")
    if counts[0] != counts[4]+counts[5]+counts[6] or counts[7] != 0:
        raise RuntimeError(f"attribution decision mismatch: {counts}")
    con.execute(f"""
        CREATE TEMP TABLE qualified_negative_aspects AS
        SELECT a.*, d.evidence_id, d.entailment AS attribution_entailment,
               d.neutral AS attribution_neutral,
               d.contradiction AS attribution_contradiction,
               d.classification_revision AS attribution_revision
        FROM read_parquet('{aspects}') a
        JOIN attribution_decisions d
          ON a.parent_asin=d.parent_asin AND a.review_id=d.review_id
         AND a.sentence_id=d.sentence_id
        WHERE a.aspect_sentiment='negative' AND d.processing_status='attributed'
    """)
    qualified = con.execute("""
        SELECT count(*), count(DISTINCT evidence_id), count(DISTINCT review_id),
               count(DISTINCT parent_asin), count(*) FILTER (
                   WHERE aspect_sentiment<>'negative' OR attribution_entailment<=attribution_neutral
                      OR attribution_entailment<=attribution_contradiction
               ) FROM qualified_negative_aspects
    """).fetchone()
    if qualified[1] != counts[4] or qualified[4] != 0:
        raise RuntimeError(f"qualified ABSA mapping mismatch: {qualified}")
    for table, filename in (("attribution_decisions", "attribution_decisions.parquet"),
                            ("qualified_negative_aspects", "qualified_negative_aspects.parquet")):
        target = (output / filename).as_posix().replace("'", "''")
        con.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    summary = {
        "status": "ready" if counts[6] == 0 else "completed_with_failures",
        "evidence_count": counts[0], "attributed_count": counts[4],
        "not_attributed_count": counts[5], "failed_count": counts[6],
        "qualified_aspect_count": qualified[0], "qualified_review_count": qualified[2],
        "product_count": qualified[3], "elapsed_seconds": round(time.perf_counter()-started, 3),
        "outputs": ["attribution_decisions.parquet", "qualified_negative_aspects.parquet"],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--shard-root", required=True)
    parser.add_argument("--absa-root", required=True)
    parser.add_argument("--output", required=True)
    run(parser.parse_args())
