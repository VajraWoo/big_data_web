"""Enrich frozen T006-v1 outputs with product metadata and verify identity."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb


EXPECTED_PRODUCTS = 139
EXPECTED_REVIEWS = 116_728
EXPECTED_SENTENCES = 459_186

SCOPE_VERSION = "scope-filter-20260906-v3"
INPUT_SCHEMA_VERSION = "nlp-input-v2"


def sql_path(path: Path) -> str:
    """Convert a Windows path to a DuckDB-safe SQL path."""
    return path.resolve().as_posix().replace("'", "''")


def find_products(project_root: Path) -> Path:
    """Find selected_products.parquet automatically."""
    matches = sorted(project_root.rglob("selected_products.parquet"))

    if not matches:
        raise FileNotFoundError(
            "No selected_products.parquet found under project root. "
            "Please pass --products explicitly."
        )

    if len(matches) > 1:
        raise RuntimeError(
            "Multiple selected_products.parquet files found:\n"
            + "\n".join(str(p) for p in matches)
            + "\nPlease pass the intended file with --products."
        )

    return matches[0]


def row_count(con: duckdb.DuckDBPyConnection, path: Path) -> int:
    return int(
        con.execute(
            f"""
            SELECT count(*)
            FROM read_parquet('{sql_path(path)}')
            """
        ).fetchone()[0]
    )


def distinct_count(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    column: str,
) -> int:
    return int(
        con.execute(
            f"""
            SELECT count(DISTINCT {column})
            FROM read_parquet('{sql_path(path)}')
            """
        ).fetchone()[0]
    )


def mismatch_count(
    con: duckdb.DuckDBPyConnection,
    left: Path,
    right: Path,
    columns: list[str],
) -> int:
    """
    Count symmetric row differences between v1 and v2
    for the specified core columns.
    """
    cols = ", ".join(columns)

    return int(
        con.execute(
            f"""
            SELECT count(*)
            FROM (
                (
                    SELECT {cols}
                    FROM read_parquet('{sql_path(left)}')

                    EXCEPT ALL

                    SELECT {cols}
                    FROM read_parquet('{sql_path(right)}')
                )

                UNION ALL

                (
                    SELECT {cols}
                    FROM read_parquet('{sql_path(right)}')

                    EXCEPT ALL

                    SELECT {cols}
                    FROM read_parquet('{sql_path(left)}')
                )
            )
            """
        ).fetchone()[0]
    )


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()

    # pipelines/foundation/nlp_input_v2_job.py -> project root
    project_root = Path(__file__).resolve().parents[2]

    baseline = (
        Path(args.baseline)
        if args.baseline
        else project_root / "data" / "gold" / "nlp-input-20260906-v1"
    )

    output = (
        Path(args.output)
        if args.output
        else project_root / "data" / "gold" / "nlp-input-20260907-v2"
    )

    products = (
        Path(args.products)
        if args.products
        else find_products(project_root)
    )

    baseline = baseline.resolve()
    output = output.resolve()
    products = products.resolve()

    review_v1 = baseline / "review_inputs.parquet"
    sentence_v1 = baseline / "sentences.parquet"
    chunk_v1 = baseline / "absa_chunks.parquet"

    required_files = [
        review_v1,
        sentence_v1,
        chunk_v1,
        products,
    ]

    for path in required_files:
        if not path.exists():
            raise FileNotFoundError(f"Missing required file: {path}")

    if output.exists():
        raise FileExistsError(
            f"Output already exists:\n{output}\n\n"
            "Delete it manually only if you intentionally want to rerun T006-v2."
        )

    output.mkdir(parents=True, exist_ok=False)

    status_path = output / "status.json"

    status: dict[str, object] = {
        "stage": "nlp_input_v2_enrichment",
        "status": "processing",
        "scope_version": SCOPE_VERSION,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "baseline": str(baseline),
        "products": str(products),
    }

    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    con = duckdb.connect()

    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")

    review_v2 = output / "review_inputs.parquet"
    sentence_v2 = output / "sentences.parquet"
    chunk_v2 = output / "absa_chunks.parquet"

    try:
        # ------------------------------------------------------------
        # 1. Validate selected_products.parquet
        # ------------------------------------------------------------

        product_stats = con.execute(
            f"""
            SELECT
                count(*) AS total_rows,
                count(DISTINCT parent_asin) AS distinct_products,

                count(*) FILTER (
                    WHERE title IS NULL
                       OR trim(cast(title AS VARCHAR)) = ''
                ) AS missing_title,

                count(*) FILTER (
                    WHERE product_category IS NULL
                       OR trim(cast(product_category AS VARCHAR)) = ''
                ) AS missing_category

            FROM read_parquet('{sql_path(products)}')
            """
        ).fetchone()

        product_rows = int(product_stats[0])
        product_distinct = int(product_stats[1])
        missing_title = int(product_stats[2])
        missing_category = int(product_stats[3])

        if (
            product_rows != EXPECTED_PRODUCTS
            or product_distinct != EXPECTED_PRODUCTS
        ):
            raise RuntimeError(
                "selected_products.parquet mismatch: "
                f"rows={product_rows}, "
                f"distinct_products={product_distinct}, "
                f"expected={EXPECTED_PRODUCTS}"
            )

        if missing_title != 0:
            raise RuntimeError(
                f"selected_products.parquet contains "
                f"{missing_title} missing product titles"
            )

        # ------------------------------------------------------------
        # 2. Validate frozen T006-v1 baseline
        # ------------------------------------------------------------

        base_reviews = row_count(con, review_v1)
        base_distinct_reviews = distinct_count(
            con,
            review_v1,
            "review_id",
        )
        base_products = distinct_count(
            con,
            review_v1,
            "parent_asin",
        )

        base_sentences = row_count(con, sentence_v1)
        base_distinct_sentences = distinct_count(
            con,
            sentence_v1,
            "sentence_id",
        )

        base_chunks = row_count(con, chunk_v1)
        base_distinct_chunks = distinct_count(
            con,
            chunk_v1,
            "chunk_id",
        )

        if (
            base_reviews != EXPECTED_REVIEWS
            or base_distinct_reviews != EXPECTED_REVIEWS
            or base_products != EXPECTED_PRODUCTS
            or base_sentences != EXPECTED_SENTENCES
            or base_distinct_sentences != EXPECTED_SENTENCES
            or base_chunks != base_distinct_chunks
        ):
            raise RuntimeError(
                "Baseline T006-v1 identity check failed:\n"
                f"reviews={base_reviews}/{base_distinct_reviews}\n"
                f"products={base_products}\n"
                f"sentences={base_sentences}/{base_distinct_sentences}\n"
                f"chunks={base_chunks}/{base_distinct_chunks}"
            )

        # ------------------------------------------------------------
        # 3. Create review_inputs.parquet v2
        # ------------------------------------------------------------

        con.execute(
            f"""
            COPY (
                SELECT
                    v1.*,
                    p.title AS product_title,
                    p.product_category

                FROM read_parquet('{sql_path(review_v1)}') v1

                JOIN read_parquet('{sql_path(products)}') p
                USING (parent_asin)

                ORDER BY
                    v1.parent_asin,
                    v1.review_id
            )

            TO '{sql_path(review_v2)}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
            """
        )

        # ------------------------------------------------------------
        # 4. Create sentences.parquet v2
        # asin is inherited from the frozen review-level data
        # ------------------------------------------------------------

        con.execute(
            f"""
            COPY (
                SELECT
                    s.*,
                    r.asin,
                    p.title AS product_title,
                    p.product_category

                FROM read_parquet('{sql_path(sentence_v1)}') s

                JOIN read_parquet('{sql_path(review_v1)}') r
                USING (review_id, parent_asin)

                JOIN read_parquet('{sql_path(products)}') p
                USING (parent_asin)

                ORDER BY
                    s.parent_asin,
                    s.review_id,
                    s.sentence_index
            )

            TO '{sql_path(sentence_v2)}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
            """
        )

        # ------------------------------------------------------------
        # 5. Create absa_chunks.parquet v2
        # ------------------------------------------------------------

        con.execute(
            f"""
            COPY (
                SELECT
                    c.*,
                    r.asin,
                    p.title AS product_title,
                    p.product_category

                FROM read_parquet('{sql_path(chunk_v1)}') c

                JOIN read_parquet('{sql_path(review_v1)}') r
                USING (review_id, parent_asin)

                JOIN read_parquet('{sql_path(products)}') p
                USING (parent_asin)

                ORDER BY
                    c.parent_asin,
                    c.review_id,
                    c.chunk_index
            )

            TO '{sql_path(chunk_v2)}'
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
            """
        )

        # ------------------------------------------------------------
        # 6. Count outputs
        # ------------------------------------------------------------

        review_count = row_count(con, review_v2)
        sentence_count = row_count(con, sentence_v2)
        chunk_count = row_count(con, chunk_v2)

        if review_count != base_reviews:
            raise RuntimeError(
                f"Review row count changed: "
                f"{review_count} != {base_reviews}"
            )

        if sentence_count != base_sentences:
            raise RuntimeError(
                f"Sentence row count changed: "
                f"{sentence_count} != {base_sentences}"
            )

        if chunk_count != base_chunks:
            raise RuntimeError(
                f"Chunk row count changed: "
                f"{chunk_count} != {base_chunks}"
            )

        # ------------------------------------------------------------
        # 7. Strict v1-v2 reconciliation
        # ------------------------------------------------------------

        review_core = [
            "review_id",
            "parent_asin",
            "asin",
            "text_raw",
            "text_normalized",
            "rating",
            "review_month",
            "reviewed_at_iso",
            "compound",
            "sentiment",
            "sentiment_method_version",
            "scope_version",
            "processing_status",
            "sentence_count",
            "chunk_count",
        ]

        sentence_core = [
            "sentence_id",
            "review_id",
            "parent_asin",
            "sentence_index",
            "sentence_text",
            "char_start",
            "char_end",
            "processing_status",
            "scope_version",
        ]

        chunk_core = [
            "chunk_id",
            "review_id",
            "parent_asin",
            "chunk_index",
            "sentence_start_index",
            "sentence_end_index",
            "char_start",
            "char_end",
            "text",
            "word_count",
            "oversize_sentence",
            "processing_status",
            "scope_version",
        ]

        review_mismatch = mismatch_count(
            con,
            review_v1,
            review_v2,
            review_core,
        )

        sentence_mismatch = mismatch_count(
            con,
            sentence_v1,
            sentence_v2,
            sentence_core,
        )

        chunk_mismatch = mismatch_count(
            con,
            chunk_v1,
            chunk_v2,
            chunk_core,
        )

        if (
            review_mismatch != 0
            or sentence_mismatch != 0
            or chunk_mismatch != 0
        ):
            raise RuntimeError(
                "v1-v2 identity mismatch:\n"
                f"review={review_mismatch}\n"
                f"sentence={sentence_mismatch}\n"
                f"chunk={chunk_mismatch}"
            )

        # ------------------------------------------------------------
        # 8. Metadata checks
        # ------------------------------------------------------------

        metadata_checks = {}

        datasets = [
            ("review_inputs", review_v2),
            ("sentences", sentence_v2),
            ("absa_chunks", chunk_v2),
        ]

        for name, path in datasets:
            result = con.execute(
                f"""
                SELECT
                    count(*) FILTER (
                        WHERE product_title IS NULL
                           OR trim(cast(product_title AS VARCHAR)) = ''
                    ),

                    count(*) FILTER (
                        WHERE product_category IS NULL
                           OR trim(cast(product_category AS VARCHAR)) = ''
                    ),

                    count(DISTINCT parent_asin)

                FROM read_parquet('{sql_path(path)}')
                """
            ).fetchone()

            dataset_missing_title = int(result[0])
            dataset_missing_category = int(result[1])
            dataset_products = int(result[2])

            metadata_checks[name] = {
                "missing_product_title": dataset_missing_title,
                "missing_product_category": dataset_missing_category,
                "distinct_products": dataset_products,
            }

            if dataset_missing_title != 0:
                raise RuntimeError(
                    f"{name} contains "
                    f"{dataset_missing_title} rows with missing product_title"
                )

            if dataset_products != EXPECTED_PRODUCTS:
                raise RuntimeError(
                    f"{name} contains "
                    f"{dataset_products} products, "
                    f"expected {EXPECTED_PRODUCTS}"
                )

        # ------------------------------------------------------------
        # 9. PASS
        # ------------------------------------------------------------

        elapsed = time.perf_counter() - started

        status.update(
            {
                "status": "ready",
                "verdict": "T006-v2 PASS",

                "finished_at":
                    datetime.now(timezone.utc).isoformat(),

                "elapsed_seconds":
                    round(elapsed, 3),

                "product_count":
                    EXPECTED_PRODUCTS,

                "review_count":
                    review_count,

                "sentence_count":
                    sentence_count,

                "chunk_count":
                    chunk_count,

                "v1_v2_mismatch": {
                    "review":
                        review_mismatch,

                    "sentence":
                        sentence_mismatch,

                    "chunk":
                        chunk_mismatch,
                },

                "selected_products_missing_category":
                    missing_category,

                "metadata_checks":
                    metadata_checks,

                "outputs": {
                    "review_inputs":
                        str(review_v2),

                    "sentences":
                        str(sentence_v2),

                    "absa_chunks":
                        str(chunk_v2),
                },

                "output_sizes_bytes": {
                    "review_inputs":
                        review_v2.stat().st_size,

                    "sentences":
                        sentence_v2.stat().st_size,

                    "absa_chunks":
                        chunk_v2.stat().st_size,
                },
            }
        )

    except Exception as exc:
        status.update(
            {
                "status": "failed",
                "verdict": "T006-v2 FAIL",

                "finished_at":
                    datetime.now(timezone.utc).isoformat(),

                "elapsed_seconds":
                    round(
                        time.perf_counter() - started,
                        3,
                    ),

                "error":
                    f"{type(exc).__name__}: {exc}",
            }
        )

        raise

    finally:
        status_path.write_text(
            json.dumps(
                status,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        con.close()

    print(
        json.dumps(
            status,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Create T006-v2 from frozen T006-v1 "
            "without re-cleaning or re-splitting reviews."
        )
    )

    parser.add_argument(
        "--baseline",
        help=(
            "Existing T006-v1 directory. "
            "Default: data/gold/nlp-input-20260906-v1"
        ),
    )

    parser.add_argument(
        "--products",
        help=(
            "Path to selected_products.parquet. "
            "If omitted, auto-search under project root."
        ),
    )

    parser.add_argument(
        "--output",
        help=(
            "New T006-v2 directory. "
            "Default: data/gold/nlp-input-20260907-v2"
        ),
    )

    run(parser.parse_args())
