from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb


EXPECTED_CANDIDATES = 315_400
EXPECTED_REVIEWS = 116_728
EXPECTED_PRODUCTS = 139

RATIO_DEFINITION_ID = "formal_unique_product_reviews_v1"
MONTH_RATIO_DEFINITION_ID = "formal_unique_product_month_reviews_v1"


def sql_path(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def get_columns(con: duckdb.DuckDBPyConnection, relation: str) -> set[str]:
    return {row[0] for row in con.execute(f"DESCRIBE {relation}").fetchall()}


def choose_column(columns: set[str], candidates: list[str]) -> str | None:
    for name in candidates:
        if name in columns:
            return name
    return None


def main(args: argparse.Namespace) -> None:
    mapping_path = Path(args.mappings)
    review_path = Path(args.reviews)
    output = Path(args.output)

    if not mapping_path.exists():
        raise FileNotFoundError(mapping_path)

    if not review_path.exists():
        raise FileNotFoundError(review_path)

    if output.exists():
        raise FileExistsError(
            f"Output already exists: {output}\n"
            "Do not overwrite an existing Gold run."
        )

    output.mkdir(parents=True)

    con = duckdb.connect()

    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")

    # ------------------------------------------------------------
    # 1. Inputs
    # ------------------------------------------------------------

    con.execute(
        f"""
        CREATE VIEW mappings AS
        SELECT *
        FROM read_json_auto(
            '{sql_path(mapping_path)}',
            format='newline_delimited'
        )
        """
    )

    con.execute(
        f"""
        CREATE VIEW reviews AS
        SELECT *
        FROM read_parquet('{sql_path(review_path)}')
        """
    )

    mapping_columns = get_columns(con, "mappings")
    review_columns = get_columns(con, "reviews")

    required_mapping_columns = {
        "candidate_id",
        "review_id",
        "parent_asin",
        "product_title",
        "product_category",
        "polarity",
        "evidence",
        "taxonomy_id",
        "canonical_theme_name",
        "mapping_status",
    }

    missing = required_mapping_columns - mapping_columns
    if missing:
        raise RuntimeError(
            f"T009 mappings missing required columns: {sorted(missing)}"
        )

    required_review_columns = {
        "review_id",
        "parent_asin",
        "rating",
        "review_month",
    }

    missing = required_review_columns - review_columns
    if missing:
        raise RuntimeError(
            f"review_inputs missing required columns: {sorted(missing)}"
        )

    text_column = choose_column(
        review_columns,
        ["text_raw", "text_normalized", "text"],
    )

    if text_column is None:
        raise RuntimeError(
            "review_inputs has no usable review text column "
            "(expected text_raw/text_normalized/text)"
        )

    date_column = choose_column(
        review_columns,
        ["reviewed_at_iso", "review_date", "reviewed_at"],
    )

    # ------------------------------------------------------------
    # 2. Validate frozen T009 input
    # ------------------------------------------------------------

    stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT candidate_id) AS candidates,
            COUNT(*) FILTER (
                WHERE mapping_status = 'mapped_by_cluster'
            ) AS mapped,
            COUNT(*) FILTER (
                WHERE mapping_status = 'unmapped_no_cluster'
            ) AS unmapped,
            COUNT(*) FILTER (
                WHERE mapping_status NOT IN (
                    'mapped_by_cluster',
                    'unmapped_no_cluster'
                )
            ) AS invalid_status
        FROM mappings
        """
    ).fetchone()

    mapping_rows, unique_candidates, mapped_count, unmapped_count, invalid_status = stats

    if mapping_rows != EXPECTED_CANDIDATES:
        raise RuntimeError(
            f"Unexpected T009 row count: {mapping_rows}"
        )

    if unique_candidates != EXPECTED_CANDIDATES:
        raise RuntimeError(
            f"candidate_id is not unique: {unique_candidates}"
        )

    if invalid_status != 0:
        raise RuntimeError(
            f"Unexpected mapping_status rows: {invalid_status}"
        )

    review_stats = con.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT review_id) AS unique_reviews,
            COUNT(DISTINCT parent_asin) AS products
        FROM reviews
        """
    ).fetchone()

    review_rows, unique_reviews, product_count = review_stats

    if unique_reviews != EXPECTED_REVIEWS:
        raise RuntimeError(
            f"Unexpected formal review count: {unique_reviews}"
        )

    if product_count != EXPECTED_PRODUCTS:
        raise RuntimeError(
            f"Unexpected formal product count: {product_count}"
        )

    # ------------------------------------------------------------
    # 3. Only mapped insights enter canonical aggregation
    # ------------------------------------------------------------

    con.execute(
        """
        CREATE TEMP TABLE mapped AS
        SELECT
            candidate_id,
            review_id,
            parent_asin,
            product_title,
            product_category,
            LOWER(polarity) AS polarity,
            evidence,
            taxonomy_id,
            canonical_theme_name
        FROM mappings
        WHERE mapping_status = 'mapped_by_cluster'
        """
    )

    bad_mapped = con.execute(
        """
        SELECT COUNT(*)
        FROM mapped
        WHERE taxonomy_id IS NULL
           OR canonical_theme_name IS NULL
        """
    ).fetchone()[0]

    if bad_mapped:
        raise RuntimeError(
            f"{bad_mapped} mapped rows have null taxonomy"
        )

    # ------------------------------------------------------------
    # 4. Collapse insight rows to review + taxonomy
    #
    # positive + negative => mixed
    # native mixed        => mixed
    # mixed is NOT also counted positive/negative
    # ------------------------------------------------------------

    con.execute(
        """
        CREATE TEMP TABLE review_theme AS
        SELECT
            review_id,
            parent_asin,

            ANY_VALUE(product_title) AS product_title,
            ANY_VALUE(product_category) AS product_category,

            taxonomy_id,
            ANY_VALUE(canonical_theme_name) AS canonical_theme_name,

            CASE
                WHEN BOOL_OR(polarity = 'mixed')
                    THEN 'mixed'

                WHEN BOOL_OR(polarity = 'positive')
                 AND BOOL_OR(polarity = 'negative')
                    THEN 'mixed'

                WHEN BOOL_OR(polarity = 'negative')
                    THEN 'negative'

                WHEN BOOL_OR(polarity = 'positive')
                    THEN 'positive'

                ELSE 'neutral'
            END AS review_polarity,

            COUNT(*) AS insight_count,

            STRING_AGG(
                DISTINCT evidence,
                ' || '
                ORDER BY evidence
            ) AS evidence_text

        FROM mapped

        GROUP BY
            review_id,
            parent_asin,
            taxonomy_id
        """
    )

    duplicate_review_theme = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                review_id,
                taxonomy_id,
                COUNT(*) AS n
            FROM review_theme
            GROUP BY review_id, taxonomy_id
            HAVING COUNT(*) <> 1
        )
        """
    ).fetchone()[0]

    if duplicate_review_theme:
        raise RuntimeError(
            f"review+taxonomy is not exact-once: {duplicate_review_theme}"
        )

    # ------------------------------------------------------------
    # 5. Product denominator
    # ------------------------------------------------------------

    # Metadata comes primarily from T009 because it already carries
    # product_title/category.
    con.execute(
        """
        CREATE TEMP TABLE product_meta AS
        SELECT
            parent_asin,
            ANY_VALUE(product_title) AS title,
            ANY_VALUE(product_category) AS category
        FROM mappings
        GROUP BY parent_asin
        """
    )

    con.execute(
        """
        CREATE TEMP TABLE products AS
        SELECT
            r.parent_asin,

            pm.title,
            pm.category,

            COUNT(DISTINCT r.review_id) AS review_count,

            COUNT(
                DISTINCT r.review_month
            ) FILTER (
                WHERE r.review_month IS NOT NULL
            ) AS active_month_count,

            MIN(r.review_month) AS first_review_month,
            MAX(r.review_month) AS last_review_month,

            'ready' AS analysis_status

        FROM reviews r

        LEFT JOIN product_meta pm
            USING (parent_asin)

        GROUP BY
            r.parent_asin,
            pm.title,
            pm.category
        """
    )

    # ------------------------------------------------------------
    # 6. Canonical product-theme metrics
    # ------------------------------------------------------------

    con.execute(
        """
        CREATE TEMP TABLE theme_metrics AS
        SELECT
            rt.parent_asin,
            rt.product_category,
            rt.taxonomy_id,

            ANY_VALUE(
                rt.canonical_theme_name
            ) AS canonical_theme_name,

            COUNT(DISTINCT rt.review_id) AS total_review_count,

            COUNT(DISTINCT rt.review_id)
                FILTER (
                    WHERE rt.review_polarity = 'positive'
                ) AS positive_review_count,

            COUNT(DISTINCT rt.review_id)
                FILTER (
                    WHERE rt.review_polarity = 'negative'
                ) AS negative_review_count,

            COUNT(DISTINCT rt.review_id)
                FILTER (
                    WHERE rt.review_polarity = 'neutral'
                ) AS neutral_review_count,

            COUNT(DISTINCT rt.review_id)
                FILTER (
                    WHERE rt.review_polarity = 'mixed'
                ) AS mixed_review_count,

            p.review_count AS eligible_review_count

        FROM review_theme rt

        JOIN products p
            USING (parent_asin)

        GROUP BY
            rt.parent_asin,
            rt.product_category,
            rt.taxonomy_id,
            p.review_count
        """
    )

    # ------------------------------------------------------------
    # 7. Frontend-facing themes
    #
    # One row per:
    # product + taxonomy + positive/negative
    #
    # Same taxonomy may therefore produce TWO theme_ids.
    # ------------------------------------------------------------

    con.execute(
        f"""
        CREATE TEMP TABLE themes AS

        SELECT
            parent_asin
                || '::'
                || taxonomy_id
                || '::positive'
                AS theme_id,

            parent_asin,
            product_category,
            taxonomy_id,

            canonical_theme_name AS name,

            'positive' AS sentiment,

            positive_review_count AS review_count,

            eligible_review_count,

            positive_review_count::DOUBLE
                / NULLIF(
                    eligible_review_count,
                    0
                ) AS ratio_value,

            'ready' AS ratio_status,

            '{RATIO_DEFINITION_ID}'
                AS ratio_definition_id,

            total_review_count,
            positive_review_count,
            negative_review_count,
            neutral_review_count,
            mixed_review_count

        FROM theme_metrics

        WHERE positive_review_count > 0

        UNION ALL

        SELECT
            parent_asin
                || '::'
                || taxonomy_id
                || '::negative'
                AS theme_id,

            parent_asin,
            product_category,
            taxonomy_id,

            canonical_theme_name AS name,

            'negative' AS sentiment,

            negative_review_count AS review_count,

            eligible_review_count,

            negative_review_count::DOUBLE
                / NULLIF(
                    eligible_review_count,
                    0
                ) AS ratio_value,

            'ready' AS ratio_status,

            '{RATIO_DEFINITION_ID}'
                AS ratio_definition_id,

            total_review_count,
            positive_review_count,
            negative_review_count,
            neutral_review_count,
            mixed_review_count

        FROM theme_metrics

        WHERE negative_review_count > 0
        """
    )

    # ------------------------------------------------------------
    # 8. Facets
    # ------------------------------------------------------------

    con.execute(
        """
        CREATE TEMP TABLE product_facets AS

        SELECT
            p.parent_asin,

            'positive_evaluation' AS facet,

            'ready' AS status,

            COUNT(t.theme_id) AS theme_count,

            CASE
                WHEN COUNT(t.theme_id) = 0
                THEN 'no_qualified_theme'
                ELSE NULL
            END AS empty_reason,

            NULL::VARCHAR AS error_summary

        FROM products p

        LEFT JOIN themes t
            ON p.parent_asin = t.parent_asin
           AND t.sentiment = 'positive'

        GROUP BY p.parent_asin


        UNION ALL


        SELECT
            p.parent_asin,

            'negative_evaluation' AS facet,

            'ready' AS status,

            COUNT(t.theme_id) AS theme_count,

            CASE
                WHEN COUNT(t.theme_id) = 0
                THEN 'no_qualified_theme'
                ELSE NULL
            END AS empty_reason,

            NULL::VARCHAR AS error_summary

        FROM products p

        LEFT JOIN themes t
            ON p.parent_asin = t.parent_asin
           AND t.sentiment = 'negative'

        GROUP BY p.parent_asin


        UNION ALL


        SELECT
            parent_asin,

            'improvement' AS facet,

            'pending' AS status,

            NULL::BIGINT AS theme_count,

            NULL::VARCHAR AS empty_reason,

            NULL::VARCHAR AS error_summary

        FROM products
        """
    )

    # ------------------------------------------------------------
    # 9. Monthly denominator
    # ------------------------------------------------------------

    con.execute(
        """
        CREATE TEMP TABLE product_month_denominator AS
        SELECT
            parent_asin,
            review_month,

            COUNT(
                DISTINCT review_id
            ) AS eligible_review_count

        FROM reviews

        WHERE review_month IS NOT NULL

        GROUP BY
            parent_asin,
            review_month
        """
    )

    # ------------------------------------------------------------
    # 10. Theme timeseries
    # ------------------------------------------------------------

    con.execute(
        f"""
        CREATE TEMP TABLE theme_timeseries AS

        SELECT
            rt.parent_asin
                || '::'
                || rt.taxonomy_id
                || '::'
                || rt.review_polarity
                AS theme_id,

            rt.parent_asin,
            rt.taxonomy_id,
            rt.review_polarity AS sentiment,

            r.review_month AS month,

            COUNT(
                DISTINCT rt.review_id
            ) AS review_count,

            d.eligible_review_count,

            COUNT(
                DISTINCT rt.review_id
            )::DOUBLE
                / NULLIF(
                    d.eligible_review_count,
                    0
                ) AS ratio_value,

            'ready' AS ratio_status,

            '{MONTH_RATIO_DEFINITION_ID}'
                AS ratio_definition_id

        FROM review_theme rt

        JOIN reviews r
          ON rt.review_id = r.review_id
         AND rt.parent_asin = r.parent_asin

        JOIN product_month_denominator d
          ON r.parent_asin = d.parent_asin
         AND r.review_month = d.review_month

        WHERE rt.review_polarity
            IN ('positive', 'negative')

        GROUP BY
            rt.parent_asin,
            rt.taxonomy_id,
            rt.review_polarity,
            r.review_month,
            d.eligible_review_count
        """
    )

    # ------------------------------------------------------------
    # 11. Theme review evidence
    # ------------------------------------------------------------

    review_date_expr = (
        f"CAST(r.{date_column} AS VARCHAR)"
        if date_column
        else "NULL::VARCHAR"
    )

    con.execute(
        f"""
        CREATE TEMP TABLE theme_reviews AS
        SELECT
            rt.parent_asin
                || '::'
                || rt.taxonomy_id
                || '::'
                || rt.review_polarity
                AS theme_id,

            rt.parent_asin,
            rt.taxonomy_id,

            rt.review_polarity AS sentiment,

            rt.review_id,

            CAST(
                r.{text_column}
                AS VARCHAR
            ) AS text,

            rt.evidence_text,

            r.rating,

            {review_date_expr}
                AS review_date,

            r.review_month,

            rt.insight_count

        FROM review_theme rt

        JOIN reviews r
          ON rt.review_id = r.review_id
         AND rt.parent_asin = r.parent_asin

        WHERE rt.review_polarity
            IN ('positive', 'negative')
        """
    )

    # ------------------------------------------------------------
    # 12. Validation
    # ------------------------------------------------------------

    invalid_ratio = con.execute(
        """
        SELECT COUNT(*)
        FROM themes
        WHERE ratio_value < 0
           OR ratio_value > 1
        """
    ).fetchone()[0]

    invalid_month_ratio = con.execute(
        """
        SELECT COUNT(*)
        FROM theme_timeseries
        WHERE ratio_value < 0
           OR ratio_value > 1
        """
    ).fetchone()[0]

    duplicate_theme_id = con.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT
                theme_id,
                COUNT(*) AS n
            FROM themes
            GROUP BY theme_id
            HAVING COUNT(*) <> 1
        )
        """
    ).fetchone()[0]

    unknown_review = con.execute(
        """
        SELECT COUNT(*)
        FROM review_theme rt

        LEFT JOIN reviews r
          ON rt.review_id = r.review_id
         AND rt.parent_asin = r.parent_asin

        WHERE r.review_id IS NULL
        """
    ).fetchone()[0]

    errors = []

    if invalid_ratio:
        errors.append(
            f"invalid product ratios: {invalid_ratio}"
        )

    if invalid_month_ratio:
        errors.append(
            f"invalid monthly ratios: {invalid_month_ratio}"
        )

    if duplicate_theme_id:
        errors.append(
            f"duplicate theme_id: {duplicate_theme_id}"
        )

    if unknown_review:
        errors.append(
            f"review join failures: {unknown_review}"
        )

    # ------------------------------------------------------------
    # 13. Write Parquet
    # ------------------------------------------------------------

    tables = [
        "products",
        "product_facets",
        "themes",
        "theme_timeseries",
        "theme_reviews",
    ]

    for table in tables:
        target = output / f"{table}.parquet"

        con.execute(
            f"""
            COPY (
                SELECT *
                FROM {table}
            )
            TO '{sql_path(target)}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
            """
        )

    # Convenience CSV summary
    con.execute(
        f"""
        COPY (
            SELECT
                category,
                COUNT(*) AS product_count,
                SUM(review_count) AS review_count
            FROM products
            GROUP BY category
            ORDER BY category
        )
        TO '{sql_path(output / "category-summary.csv")}'
        (
            HEADER,
            DELIMITER ','
        )
        """
    )

    output_counts = {}

    for table in tables:
        output_counts[table] = con.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    # ------------------------------------------------------------
    # 14. Batch metadata
    # ------------------------------------------------------------

    batch = {
        "batch_id": output.name,
        "data_source": "gold",
        "is_gold": True,
        "gold_status": "verified" if not errors else "failed",
        "analysis_status": "ready" if not errors else "failed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "facets": {
            "positive_evaluation": "ready",
            "negative_evaluation": "ready",
            "improvement": "pending",
        },
    }

    (output / "batch.json").write_text(
        json.dumps(
            batch,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    validation = {
        "status": "ready" if not errors else "failed",

        "engine": "duckdb",

        "input": {
            "candidate_rows": mapping_rows,
            "unique_candidate_ids": unique_candidates,
            "mapped_by_cluster": mapped_count,
            "unmapped_no_cluster": unmapped_count,
            "formal_unique_reviews": unique_reviews,
            "formal_products": product_count,
        },

        "rules": {
            "canonical_aggregation":
                "mapped_by_cluster only",

            "review_theme_dedup":
                "unique review_id + taxonomy_id",

            "mixed":
                "native mixed OR positive+negative "
                "within review_id+taxonomy_id => mixed once",

            "product_ratio":
                "sentiment-specific unique theme reviews "
                "/ all formal unique reviews for product",

            "monthly_ratio":
                "sentiment-specific unique theme reviews "
                "/ all formal unique reviews for product-month",

            "unmapped":
                "retained in T009, excluded from "
                "canonical theme aggregation",
        },

        "outputs": output_counts,

        "errors": errors,
    }

    (output / "validation.json").write_text(
        json.dumps(
            validation,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            validation,
            ensure_ascii=False,
            indent=2,
        )
    )

    if errors:
        raise RuntimeError(
            "T010 validation failed. "
            "See validation.json."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mappings",
        required=True,
    )

    parser.add_argument(
        "--reviews",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    main(parser.parse_args())