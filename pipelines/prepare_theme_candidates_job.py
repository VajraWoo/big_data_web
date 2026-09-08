"""Build separate evaluation and improvement candidates from approved evidence."""

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
    aspects = (Path(args.absa_root) / "review_aspects.parquet").as_posix().replace("'", "''")
    suggestions = (Path(args.nli_root) / "explicit_suggestions.parquet").as_posix().replace("'", "''")
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")
    con.execute(f"""
        CREATE TEMP TABLE raw_candidates AS
        SELECT parent_asin, review_id, sentence_text, 'evaluation' AS theme_type,
               'positive'::VARCHAR AS sentiment, [aspect_text] AS attributes,
               ['absa_positive'] AS sources
        FROM read_parquet('{aspects}') WHERE aspect_sentiment='positive'
        UNION ALL
        SELECT parent_asin, review_id, sentence_text, 'evaluation', 'negative'::VARCHAR,
               [aspect_text], ['absa_negative']
        FROM read_parquet('{aspects}') WHERE aspect_sentiment='negative'
        UNION ALL
        SELECT parent_asin, review_id, sentence_text, 'improvement', NULL::VARCHAR,
               [aspect_text], ['implicit_problem']
        FROM read_parquet('{aspects}') WHERE aspect_sentiment='negative'
        UNION ALL
        SELECT parent_asin, review_id, sentence_text, 'improvement', NULL::VARCHAR,
               []::VARCHAR[], ['explicit_suggestion']
        FROM read_parquet('{suggestions}')
    """)
    con.execute("""
        CREATE TEMP TABLE candidates AS
        SELECT md5(parent_asin || '|' || theme_type || '|' || coalesce(sentiment, 'none') ||
                   '|' || review_id || '|' || sentence_text) AS candidate_id,
               parent_asin, review_id, sentence_text, theme_type, sentiment,
               list_sort(list_distinct(flatten(list(attributes)))) AS attributes,
               list_sort(list_distinct(flatten(list(sources)))) AS sources
        FROM raw_candidates
        GROUP BY parent_asin, review_id, sentence_text, theme_type, sentiment
    """)
    totals = con.execute("""
        SELECT count(*), count(DISTINCT review_id), count(DISTINCT parent_asin),
               count(*) FILTER (WHERE theme_type='evaluation' AND sentiment='positive'),
               count(*) FILTER (WHERE theme_type='evaluation' AND sentiment='negative'),
               count(*) FILTER (WHERE theme_type='improvement'),
               count(*) FILTER (WHERE theme_type='evaluation' AND
                   ((sentiment='positive' AND NOT list_contains(sources,'absa_positive')) OR
                    (sentiment='negative' AND NOT list_contains(sources,'absa_negative')))),
               count(*) FILTER (WHERE theme_type='improvement' AND sentiment IS NOT NULL)
        FROM candidates
    """).fetchone()
    products = [row[0] for row in con.execute(
        "SELECT DISTINCT parent_asin FROM candidates ORDER BY parent_asin"
    ).fetchall()]
    if len(products) != 139 or totals[6] != 0 or totals[7] != 0:
        raise RuntimeError(f"theme candidate validation failed: {totals}")
    per_product = []
    for parent_asin in products:
        safe_asin = parent_asin.replace("/", "_")
        target = (output / f"candidates-{safe_asin}.ndjson").as_posix().replace("'", "''")
        counts = con.execute("""
            SELECT count(*), count(DISTINCT review_id),
                   count(*) FILTER (WHERE theme_type='evaluation' AND sentiment='positive'),
                   count(*) FILTER (WHERE theme_type='evaluation' AND sentiment='negative'),
                   count(*) FILTER (WHERE theme_type='improvement')
            FROM candidates WHERE parent_asin=?
        """, [parent_asin]).fetchone()
        escaped_asin = parent_asin.replace("'", "''")
        con.execute(f"""
            COPY (SELECT * FROM candidates WHERE parent_asin='{escaped_asin}'
                  ORDER BY theme_type, sentiment, candidate_id)
            TO '{target}' (FORMAT JSON)
        """)
        per_product.append({
            "parent_asin": parent_asin, "candidate_count": counts[0],
            "review_count": counts[1], "positive_evaluation_count": counts[2],
            "negative_evaluation_count": counts[3], "improvement_count": counts[4],
        })
    con.close()
    summary = {
        "status": "ready", "candidate_count": totals[0], "review_count": totals[1],
        "product_count": totals[2], "positive_evaluation_count": totals[3],
        "negative_evaluation_count": totals[4], "improvement_count": totals[5],
        "elapsed_seconds": round(time.perf_counter()-started, 3), "products": per_product,
    }
    (output / "manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "products"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--absa-root", required=True)
    parser.add_argument("--nli-root", required=True)
    parser.add_argument("--output", required=True)
    run(parser.parse_args())
