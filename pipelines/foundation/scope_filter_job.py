"""Compute the proposed front-end/full-NLP product scope without running NLP models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

from pipelines.foundation.scope_filter import WHOLE_APPLIANCE_CATEGORIES


def sql_list(values: set[str]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in sorted(values))


def run(args: argparse.Namespace) -> None:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")

    products = args.silver_root + "/products/*.parquet"
    reviews = args.silver_root + "/reviews/*.parquet"
    sentiment = args.sentiment_root + "/reviews/*.parquet"
    categories = sql_list(WHOLE_APPLIANCE_CATEGORIES)

    con.execute(f"""
        CREATE TEMP TABLE product_metadata AS
        SELECT parent_asin, any_value(title) AS title, any_value(categories) AS categories,
               list_last(any_value(categories)) AS product_category
        FROM read_parquet('{products}')
        WHERE parent_asin IS NOT NULL
        GROUP BY parent_asin
    """)
    con.execute(f"""
        CREATE TEMP TABLE eligible_reviews AS
        SELECT s.review_id, s.parent_asin, s.review_month, s.sentiment
        FROM read_parquet('{sentiment}') s
        JOIN read_parquet('{reviews}') r USING (review_id)
        WHERE coalesce(r.exact_duplicate, false) = false
          AND s.review_month IS NOT NULL
          AND s.review_month <= '{args.end_month}'
    """)
    con.execute(f"""
        CREATE TEMP TABLE product_stats AS
        SELECT e.parent_asin, p.title, p.product_category, p.categories,
               count(*) AS review_count,
               count(DISTINCT e.review_month) AS active_months,
               max(e.review_month) AS last_review_month,
               count(*) FILTER (WHERE e.sentiment = 'positive') AS positive_count,
               count(*) FILTER (WHERE e.sentiment = 'negative') AS negative_count,
               count(*) FILTER (WHERE e.sentiment = 'neutral') AS neutral_count
        FROM eligible_reviews e
        JOIN product_metadata p USING (parent_asin)
        WHERE p.title IS NOT NULL AND trim(p.title) <> ''
          AND p.product_category IN ({categories})
        GROUP BY e.parent_asin, p.title, p.product_category, p.categories
    """)
    con.execute(f"""
        CREATE TEMP TABLE selected_products AS
        SELECT * FROM product_stats
        WHERE review_count >= {args.minimum_reviews}
          AND active_months >= {args.minimum_active_months}
          AND last_review_month >= '{args.active_since_month}'
    """)
    con.execute("""
        CREATE TEMP TABLE category_summary AS
        SELECT product_category, count(*) AS product_count,
               sum(review_count) AS review_count,
               sum(positive_count) AS positive_count,
               sum(negative_count) AS negative_count,
               min(review_count) AS minimum_product_reviews,
               max(review_count) AS maximum_product_reviews
        FROM selected_products
        GROUP BY product_category
        ORDER BY review_count DESC, product_category
    """)

    con.execute(f"COPY selected_products TO '{output.as_posix()}/selected_products.parquet' (FORMAT PARQUET)")
    con.execute(f"COPY selected_products TO '{output.as_posix()}/selected_products.csv' (HEADER, DELIMITER ',')")
    con.execute(f"COPY category_summary TO '{output.as_posix()}/category_summary.csv' (HEADER, DELIMITER ',')")
    totals = con.execute("""
        SELECT count(*) AS product_count, coalesce(sum(review_count), 0) AS review_count,
               count(DISTINCT product_category) AS category_count
        FROM selected_products
    """).fetchone()
    category_cursor = con.execute("SELECT * FROM category_summary")
    category_columns = [column[0] for column in category_cursor.description]
    category_rows = category_cursor.fetchall()
    summary = {
        "rules": {
            "analysis_period": "all_dated_history",
            "end_month": args.end_month,
            "active_since_month": args.active_since_month,
            "minimum_reviews": args.minimum_reviews,
            "minimum_active_months": args.minimum_active_months,
            "sentiment_counts_are_admission_filters": False,
            "whole_appliance_categories": sorted(WHOLE_APPLIANCE_CATEGORIES),
        },
        "result": {"product_count": totals[0], "review_count": totals[1], "category_count": totals[2]},
        "categories": [dict(zip(category_columns, row)) for row in category_rows],
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--silver-root", required=True)
    parser.add_argument("--sentiment-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--end-month", default="2023-09")
    parser.add_argument("--active-since-month", default="2022-10")
    parser.add_argument("--minimum-reviews", type=int, default=300)
    parser.add_argument("--minimum-active-months", type=int, default=12)
    run(parser.parse_args())
