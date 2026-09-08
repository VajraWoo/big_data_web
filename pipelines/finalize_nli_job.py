"""Merge explicit-suggestion NLI shards and reconcile every sentence."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


MODEL_REVISION = "b95119ce93d3e065de6214e38cd4a97b0f2f2c6d"
DECISION_RULE = "entailment > neutral AND entailment > contradiction"
CLASSIFICATION_REVISION = "explicit-suggestion-rule-v2"


def run(args):
    started = time.perf_counter()
    root = Path(args.shard_root)
    run_status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    if run_status.get("status") not in {"ready", "completed_with_failures"}:
        raise RuntimeError(f"NLI shards are not complete: {run_status.get('status')}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    results = (root / "sentence-nli-*.ndjson").as_posix().replace("'", "''")
    suggestions = (root / "suggestions-*.ndjson").as_posix().replace("'", "''")
    con = duckdb.connect()
    con.execute(f"CREATE TEMP TABLE sentence_nli AS SELECT * FROM read_json_auto('{results}', format='newline_delimited')")
    con.execute(f"CREATE TEMP TABLE explicit_suggestions AS SELECT * FROM read_json_auto('{suggestions}', format='newline_delimited')")
    counts = con.execute("""
        SELECT count(*), count(DISTINCT sentence_id), count(DISTINCT review_id),
               count(DISTINCT parent_asin),
               count(*) FILTER (WHERE processing_status='suggestion'),
               count(*) FILTER (WHERE processing_status='not_suggestion'),
               count(*) FILTER (WHERE processing_status='failed'),
               count(*) FILTER (WHERE processing_status<>'failed' AND
                   (entailment IS NULL OR neutral IS NULL OR contradiction IS NULL OR
                    sentence_text IS NULL OR model_revision<>'b95119ce93d3e065de6214e38cd4a97b0f2f2c6d')),
               count(*) FILTER (WHERE processing_status='suggestion' AND NOT
                   (entailment>neutral AND entailment>contradiction)),
               count(*) FILTER (WHERE processing_status='not_suggestion' AND
                   entailment>neutral AND entailment>contradiction)
        FROM sentence_nli
    """).fetchone()
    if counts[0:4] != (459_186, 459_186, 116_728, 139):
        raise RuntimeError(f"NLI input reconciliation failed: {counts}")
    if counts[0] != counts[4] + counts[5] + counts[6] or any(counts[index] != 0 for index in (7, 8, 9)):
        raise RuntimeError(f"NLI status/field validation failed: {counts}")
    suggestion_count = con.execute("""
        SELECT count(*) FROM explicit_suggestions
        WHERE confirmed_label=true AND entailment>neutral AND entailment>contradiction
    """).fetchone()[0]
    if suggestion_count != counts[4]:
        raise RuntimeError(f"suggestion mapping mismatch: {suggestion_count} != {counts[4]}")
    for table, filename in (("sentence_nli", "sentence_nli.parquet"), ("explicit_suggestions", "explicit_suggestions.parquet")):
        target = (output / filename).as_posix().replace("'", "''")
        con.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    summary = {
        "status": "ready" if counts[6] == 0 else "completed_with_failures",
        "model_revision": run_status["model_revision"], "device": run_status["device"],
        "decision_rule": DECISION_RULE,
        "classification_revision": CLASSIFICATION_REVISION,
        "sentence_count": counts[0], "distinct_sentence_count": counts[1],
        "review_count": counts[2], "product_count": counts[3],
        "suggestion_count": counts[4], "not_suggestion_count": counts[5],
        "failed_count": counts[6], "elapsed_seconds": round(time.perf_counter()-started, 3),
        "outputs": ["sentence_nli.parquet", "explicit_suggestions.parquet"],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-root", required=True)
    parser.add_argument("--output", required=True)
    run(parser.parse_args())
