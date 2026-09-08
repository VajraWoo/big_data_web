"""Export the fixed whole-appliance review scope and prepare sentence-boundary chunks."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from pipelines.nlp_input import chunk_sentences, split_sentences


EXPECTED_PRODUCTS = 139
EXPECTED_REVIEWS = 116_728
SCOPE_VERSION = "scope-filter-20260906-v3"


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _write_json_line(handle, value: dict[str, object]) -> None:
    handle.write(json.dumps(value, ensure_ascii=False, default=_json_default) + "\n")


def _parquet_from_json(con: duckdb.DuckDBPyConnection, source: Path, target: Path) -> None:
    source_sql = source.as_posix().replace("'", "''")
    target_sql = target.as_posix().replace("'", "''")
    con.execute(
        f"COPY (SELECT * FROM read_json_auto('{source_sql}', format='newline_delimited')) "
        f"TO '{target_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )


def run(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    status_path = output / "status.json"
    status = {
        "stage": "nlp_input",
        "run_id": output.name,
        "scope_version": SCOPE_VERSION,
        "status": "processing",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "expected_products": EXPECTED_PRODUCTS,
        "expected_reviews": EXPECTED_REVIEWS,
        "max_chunk_words": args.max_chunk_words,
    }
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")

    con = duckdb.connect()
    con.execute("PRAGMA threads=8")
    con.execute("PRAGMA memory_limit='8GB'")
    products = (Path(args.scope_root) / "selected_products.parquet").as_posix().replace("'", "''")
    reviews = (Path(args.silver_root) / "reviews" / "*.parquet").as_posix().replace("'", "''")
    sentiment = (Path(args.sentiment_root) / "reviews" / "*.parquet").as_posix().replace("'", "''")

    query = f"""
        SELECT r.review_id, r.parent_asin, r.asin, r.text_raw, r.text_normalized,
               r.rating, r.review_month, r.reviewed_at_iso,
               s.compound, s.sentiment, s.method_version AS sentiment_method_version
        FROM read_parquet('{reviews}') r
        JOIN read_parquet('{sentiment}') s USING (review_id, parent_asin)
        JOIN read_parquet('{products}') p USING (parent_asin)
        WHERE coalesce(r.exact_duplicate, false) = false
          AND r.review_month IS NOT NULL
          AND r.review_month <= '2023-09'
        ORDER BY r.parent_asin, r.review_id
    """

    review_json = output / ".review_inputs.ndjson"
    sentence_json = output / ".sentences.ndjson"
    chunk_json = output / ".absa_chunks.ndjson"
    review_count = sentence_count = chunk_count = oversize_count = 0
    product_ids: set[str] = set()
    review_ids: set[str] = set()

    try:
        cursor = con.execute(query)
        columns = [item[0] for item in cursor.description]
        with (
            review_json.open("w", encoding="utf-8", newline="\n") as review_handle,
            sentence_json.open("w", encoding="utf-8", newline="\n") as sentence_handle,
            chunk_json.open("w", encoding="utf-8", newline="\n") as chunk_handle,
        ):
            while rows := cursor.fetchmany(2_000):
                for row in rows:
                    review = dict(zip(columns, row))
                    review_id = str(review["review_id"])
                    parent_asin = str(review["parent_asin"])
                    if review_id in review_ids:
                        raise RuntimeError(f"duplicate review_id in formal scope: {review_id}")
                    review_ids.add(review_id)
                    product_ids.add(parent_asin)
                    text = str(review["text_normalized"] or "").strip()
                    sentences = split_sentences(text)
                    if not sentences:
                        raise RuntimeError(f"formal review has no processable text: {review_id}")
                    chunks = chunk_sentences(sentences, args.max_chunk_words)

                    review_count += 1
                    sentence_count += len(sentences)
                    chunk_count += len(chunks)
                    oversize_count += sum(bool(chunk["oversize_sentence"]) for chunk in chunks)
                    _write_json_line(
                        review_handle,
                        {
                            **review,
                            "scope_version": SCOPE_VERSION,
                            "processing_status": "pending",
                            "sentence_count": len(sentences),
                            "chunk_count": len(chunks),
                        },
                    )
                    for sentence in sentences:
                        _write_json_line(
                            sentence_handle,
                            {
                                "sentence_id": f"{review_id}:s{sentence.index:04d}",
                                "review_id": review_id,
                                "parent_asin": parent_asin,
                                "sentence_index": sentence.index,
                                "sentence_text": sentence.text,
                                "char_start": sentence.start,
                                "char_end": sentence.end,
                                "processing_status": "pending",
                                "scope_version": SCOPE_VERSION,
                            },
                        )
                    for chunk in chunks:
                        index = int(chunk["chunk_index"])
                        _write_json_line(
                            chunk_handle,
                            {
                                "chunk_id": f"{review_id}:c{index:04d}",
                                "review_id": review_id,
                                "parent_asin": parent_asin,
                                **chunk,
                                "processing_status": "pending",
                                "scope_version": SCOPE_VERSION,
                            },
                        )

        if len(product_ids) != EXPECTED_PRODUCTS or review_count != EXPECTED_REVIEWS:
            raise RuntimeError(
                f"scope mismatch: products={len(product_ids)}, reviews={review_count}; "
                f"expected {EXPECTED_PRODUCTS}/{EXPECTED_REVIEWS}"
            )
        _parquet_from_json(con, review_json, output / "review_inputs.parquet")
        _parquet_from_json(con, sentence_json, output / "sentences.parquet")
        _parquet_from_json(con, chunk_json, output / "absa_chunks.parquet")

        elapsed = time.perf_counter() - started
        status.update(
            {
                "status": "ready",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(elapsed, 3),
                "product_count": len(product_ids),
                "review_count": review_count,
                "distinct_review_count": len(review_ids),
                "sentence_count": sentence_count,
                "chunk_count": chunk_count,
                "oversize_sentence_chunk_count": oversize_count,
                "outputs": ["review_inputs.parquet", "sentences.parquet", "absa_chunks.parquet"],
            }
        )
    except Exception as exc:
        status.update(
            {
                "status": "failed",
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        raise
    finally:
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        for temporary in (review_json, sentence_json, chunk_json):
            temporary.unlink(missing_ok=True)
        con.close()

    print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-root", required=True)
    parser.add_argument("--silver-root", required=True)
    parser.add_argument("--sentiment-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-chunk-words", type=int, default=180)
    run(parser.parse_args())
