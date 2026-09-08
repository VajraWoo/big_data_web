"""Convert revised theme shards and facet states to validated Parquet."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import duckdb


def run(args):
    started = time.perf_counter()
    root = Path(args.cluster_root)
    status = json.loads((root / "status.json").read_text(encoding="utf-8"))
    if status.get("status") != "ready":
        raise RuntimeError(f"theme clustering is not complete: {status.get('status')}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    for table, pattern in {
        "themes": root / "themes-*.ndjson", "theme_members": root / "members-*.ndjson",
        "product_analysis_facets": root / "facets-*.ndjson",
    }.items():
        source = pattern.as_posix().replace("'", "''")
        con.execute(f"CREATE TEMP TABLE {table} AS SELECT * FROM read_json_auto('{source}', format='newline_delimited')")
    validation = con.execute("""
        SELECT count(*), count(DISTINCT t.theme_id),
               count(*) FILTER (WHERE t.review_count<10 OR t.name IS NULL OR trim(t.name)='' OR
                   t.naming_method NOT IN ('template','center_phrase') OR
                   t.clustering_method<>'fast_community_detection' OR
                   (t.theme_type='evaluation' AND t.sentiment NOT IN ('positive','negative')) OR
                   (t.theme_type='improvement' AND t.sentiment IS NOT NULL) OR
                   t.theme_type NOT IN ('evaluation','improvement')),
               count(*) FILTER (WHERE t.review_count<>m.member_count)
        FROM themes t JOIN (
            SELECT theme_id, count(DISTINCT review_id) AS member_count
            FROM theme_members GROUP BY theme_id
        ) m USING(theme_id)
    """).fetchone()
    invalid_members = con.execute("""
        SELECT count(*) FROM theme_members m LEFT JOIN themes t USING(theme_id)
        WHERE t.theme_id IS NULL OR m.parent_asin<>t.parent_asin OR
              m.theme_type<>t.theme_type OR m.sentiment IS DISTINCT FROM t.sentiment OR
              m.review_id IS NULL OR m.evidence_sentence IS NULL
    """).fetchone()[0]
    facets = con.execute("""
        SELECT count(*), count(DISTINCT parent_asin),
               count(*) FILTER (WHERE status<>'ready' OR
                   (theme_count=0 AND reason<>'no_qualified_theme') OR
                   (theme_count>0 AND reason IS NOT NULL)),
               count(*) FILTER (WHERE theme_type='evaluation' AND sentiment='positive'),
               count(*) FILTER (WHERE theme_type='evaluation' AND sentiment='negative'),
               count(*) FILTER (WHERE theme_type='improvement' AND sentiment IS NULL)
        FROM product_analysis_facets
    """).fetchone()
    facet_mismatches = con.execute("""
        SELECT count(*) FROM product_analysis_facets f LEFT JOIN (
            SELECT parent_asin, theme_type, sentiment, count(*) AS actual_count
            FROM themes GROUP BY parent_asin, theme_type, sentiment
        ) t ON f.parent_asin=t.parent_asin AND f.theme_type=t.theme_type
           AND f.sentiment IS NOT DISTINCT FROM t.sentiment
        WHERE f.theme_count<>coalesce(t.actual_count,0)
    """).fetchone()[0]
    if validation[0] != validation[1] or validation[2] or validation[3] or invalid_members:
        raise RuntimeError(f"theme validation failed: {validation}, members={invalid_members}")
    if facets != (417, 139, 0, 139, 139, 139) or facet_mismatches:
        raise RuntimeError(f"facet validation failed: {facets}, mismatches={facet_mismatches}")
    for table, filename in (
        ("themes", "themes.parquet"), ("theme_members", "theme_members.parquet"),
        ("product_analysis_facets", "product_analysis_facets.parquet"),
    ):
        target = (output / filename).as_posix().replace("'", "''")
        con.execute(f"COPY {table} TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    member_count = con.execute("SELECT count(*) FROM theme_members").fetchone()[0]
    con.close()
    summary = {
        "status": "ready", "theme_count": validation[0], "member_count": member_count,
        "product_count": facets[1], "facet_count": facets[0],
        "invalid_theme_count": validation[2], "count_mismatch_count": validation[3],
        "invalid_member_count": invalid_members, "facet_mismatch_count": facet_mismatches,
        "elapsed_seconds": round(time.perf_counter()-started, 3),
        "outputs": ["themes.parquet", "theme_members.parquet", "product_analysis_facets.parquet"],
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-root", required=True)
    parser.add_argument("--output", required=True)
    run(parser.parse_args())
