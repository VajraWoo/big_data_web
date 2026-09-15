"""Reclassify existing NLI scores without repeating Transformer inference."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


MODEL_REVISION = "b95119ce93d3e065de6214e38cd4a97b0f2f2c6d"
DECISION_RULE = "entailment > neutral AND entailment > contradiction"
CLASSIFICATION_REVISION = "explicit-suggestion-rule-v2"
EXPECTED_SENTENCES = 459_186
EXPECTED_REVIEWS = 116_728
EXPECTED_PRODUCTS = 139


def _sql_path(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "''")


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    input_path = Path(args.input)
    if not input_path.is_file():
        raise FileNotFoundError(f"NLI score file not found: {input_path}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    try:
        con.execute(f"""
            CREATE TEMP TABLE sentence_nli AS
            SELECT
                sentence_id,
                review_id,
                parent_asin,
                sentence_text,
                entailment,
                neutral,
                contradiction,
                CASE
                    WHEN processing_status = 'failed' THEN 'failed'
                    WHEN entailment > neutral AND entailment > contradiction THEN 'suggestion'
                    ELSE 'not_suggestion'
                END AS processing_status,
                error,
                model_revision,
                '{DECISION_RULE}' AS decision_rule,
                '{CLASSIFICATION_REVISION}' AS classification_revision
            FROM read_parquet('{_sql_path(input_path)}')
        """)
        con.execute("""
            CREATE TEMP TABLE explicit_suggestions AS
            SELECT
                sentence_id AS suggestion_id,
                review_id,
                parent_asin,
                sentence_id,
                sentence_text,
                entailment,
                neutral,
                contradiction,
                true AS confirmed_label,
                'explicit_suggestion' AS source_type,
                model_revision,
                decision_rule,
                classification_revision
            FROM sentence_nli
            WHERE processing_status = 'suggestion'
        """)

        counts = con.execute(f"""
            SELECT
                count(*),
                count(DISTINCT sentence_id),
                count(DISTINCT review_id),
                count(DISTINCT parent_asin),
                count(*) FILTER (WHERE processing_status = 'suggestion'),
                count(*) FILTER (WHERE processing_status = 'not_suggestion'),
                count(*) FILTER (WHERE processing_status = 'failed'),
                count(*) FILTER (
                    WHERE processing_status <> 'failed' AND (
                        sentence_text IS NULL OR entailment IS NULL OR neutral IS NULL OR
                        contradiction IS NULL OR model_revision <> '{MODEL_REVISION}'
                    )
                ),
                count(*) FILTER (
                    WHERE processing_status = 'suggestion' AND NOT (
                        entailment > neutral AND entailment > contradiction
                    )
                )
            FROM sentence_nli
        """).fetchone()

        expected_identity = (
            EXPECTED_SENTENCES,
            EXPECTED_SENTENCES,
            EXPECTED_REVIEWS,
            EXPECTED_PRODUCTS,
        )
        if counts[0:4] != expected_identity:
            raise RuntimeError(f"NLI input identity reconciliation failed: {counts[0:4]}")
        if counts[0] != counts[4] + counts[5] + counts[6]:
            raise RuntimeError(f"NLI status reconciliation failed: {counts}")
        if counts[7] != 0 or counts[8] != 0:
            raise RuntimeError(f"NLI field/rule validation failed: {counts}")

        suggestion_mapping = con.execute("""
            SELECT
                count(*),
                count(DISTINCT suggestion_id),
                count(*) FILTER (
                    WHERE confirmed_label <> true OR source_type <> 'explicit_suggestion' OR
                          NOT (entailment > neutral AND entailment > contradiction)
                )
            FROM explicit_suggestions
        """).fetchone()
        if suggestion_mapping != (counts[4], counts[4], 0):
            raise RuntimeError(
                f"explicit suggestion mapping mismatch: {suggestion_mapping} != {counts[4]}"
            )

        for table, filename in (
            ("sentence_nli", "sentence_nli.parquet"),
            ("explicit_suggestions", "explicit_suggestions.parquet"),
        ):
            con.execute(
                f"COPY {table} TO '{_sql_path(output / filename)}' "
                "(FORMAT PARQUET, COMPRESSION ZSTD)"
            )
    finally:
        con.close()

    summary = {
        "status": "ready" if counts[6] == 0 else "completed_with_failures",
        "source": str(input_path),
        "device": "CPU (DuckDB; existing NLI scores reused)",
        "model_revision": MODEL_REVISION,
        "decision_rule": DECISION_RULE,
        "classification_revision": CLASSIFICATION_REVISION,
        "sentence_count": counts[0],
        "distinct_sentence_count": counts[1],
        "review_count": counts[2],
        "product_count": counts[3],
        "suggestion_count": counts[4],
        "not_suggestion_count": counts[5],
        "failed_count": counts[6],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "outputs": ["sentence_nli.parquet", "explicit_suggestions.parquet"],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Existing sentence_nli.parquet with 3-class scores")
    parser.add_argument("--output", required=True, help="New output directory; must not already exist")
    run(parser.parse_args())
