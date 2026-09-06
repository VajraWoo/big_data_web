"""Profile all category-derived product groups and select outcome-blind NLP scopes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import yaml
from pyspark.sql import SparkSession, functions as F, types as T

from product_groups import canonical_product_group, select_candidates


GROUP_SCHEMA = T.StructType(
    [
        T.StructField("group_id", T.StringType()),
        T.StructField("name", T.StringType()),
        T.StructField("category_depth", T.IntegerType()),
        T.StructField("category_path", T.ArrayType(T.StringType())),
    ]
)


def run(args: argparse.Namespace) -> dict:
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    output_root = Path(args.output_root) / args.run_id / "product_groups"
    output_root.mkdir(parents=True, exist_ok=False)
    started = time.time()
    spark = (
        SparkSession.builder.appName(args.run_id)
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    report = {
        "run_id": args.run_id,
        "analysis_version": config["analysis_version"],
        "source_silver_run_id": config["inputs"]["silver_run_id"],
        "source_text_profile_run_id": config["inputs"]["text_profile_run_id"],
        "selection_rule": {
            "outcome_blind": True,
            "minimum_selected": config["scope"]["minimum_selected_product_groups"],
            "score_dimensions": config["scope"]["selection_dimensions"],
        },
    }
    try:
        products = spark.read.parquet(config["inputs"]["silver_root"] + "/products")
        text = spark.read.parquet(config["inputs"]["text_features_root"])
        to_group = F.udf(canonical_product_group, GROUP_SCHEMA)
        grouped_products = (
            products.withColumn("group", to_group("categories", "main_category"))
            .filter(F.col("group").isNotNull() & F.col("parent_asin").isNotNull())
            .select(
                "parent_asin",
                F.col("group.group_id").alias("group_id"),
                F.col("group.name").alias("name"),
                F.col("group.category_depth").alias("category_depth"),
                (F.col("title").isNotNull() | F.col("store").isNotNull()).cast("int").alias("identifiable"),
            )
        )
        parent_groups = (
            grouped_products.groupBy("parent_asin")
            .agg(
                F.min("group_id").alias("group_id"),
                F.min("name").alias("name"),
                F.max("category_depth").alias("category_depth"),
                F.max("identifiable").alias("identifiable"),
            )
        )
        product_metrics = (
            parent_groups.groupBy("group_id", "name")
            .agg(
                F.count("parent_asin").alias("product_count"),
                F.sum("identifiable").alias("identifiable_product_count"),
                F.max("category_depth").alias("category_depth"),
            )
            .withColumn(
                "metadata_identifiability",
                F.col("identifiable_product_count") / F.col("product_count"),
            )
        )
        review_metrics = (
            text.join(parent_groups.select("parent_asin", "group_id"), "parent_asin", "inner")
            .groupBy("group_id")
            .agg(
                F.count("review_id").alias("review_count"),
                F.sum(F.col("eligible_nlp").cast("long")).alias("eligible_text_count"),
                F.countDistinct("review_month").alias("active_months"),
                F.min("review_month").alias("first_month"),
                F.max("review_month").alias("last_month"),
            )
            .withColumn("eligible_text_rate", F.col("eligible_text_count") / F.col("review_count"))
        )
        metrics = product_metrics.join(review_metrics, "group_id", "left").fillna(
            {"review_count": 0, "eligible_text_count": 0, "active_months": 0, "eligible_text_rate": 0.0}
        )
        group_count = metrics.count()
        if group_count > 5000:
            raise ValueError(f"category candidate bound exceeded: {group_count} > 5000")
        rows = [row.asDict(recursive=True) for row in metrics.orderBy("group_id").limit(5000).collect()]
        decisions = select_candidates(
            rows,
            minimum_selected=config["scope"]["minimum_selected_product_groups"],
        )
        decision_frame = spark.createDataFrame(decisions)
        decision_frame.write.mode("errorifexists").parquet(str(output_root / "candidates"))
        report.update(
            {
                "status": "passed",
                "candidate_group_count": group_count,
                "selected": [row for row in decisions if row["selection_state"] == "selected"],
                "top_candidates": [row for row in decisions if row["selection_state"] != "rejected"][:10],
                "state_counts": {
                    state: sum(row["selection_state"] == state for row in decisions)
                    for state in ("selected", "candidate", "rejected")
                },
            }
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["elapsed_seconds"] = round(time.time() - started, 2)
        (output_root / "selection.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        spark.stop()
    print("PRODUCT_GROUP_RESULT=" + json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/pipelines/config/analysis.yaml")
    parser.add_argument("--output-root", default="/data/gold")
    parser.add_argument("--run-id", required=True)
    run(parser.parse_args())
