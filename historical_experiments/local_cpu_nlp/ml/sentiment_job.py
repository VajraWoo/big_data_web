"""Run fixed VADER inference on every NLP-eligible English review."""

import argparse
import json
from pathlib import Path
import socket
import time

import yaml
from pyspark.sql import SparkSession, functions as F

from sentiment import label_compound


def score_partition(rows):
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()
    host = socket.gethostname()
    for row in rows:
        compound = float(analyzer.polarity_scores(row.text_normalized)["compound"])
        yield (
            row.review_id,
            row.parent_asin,
            row.rating,
            row.review_month,
            row.body_hash,
            compound,
            label_compound(compound),
            "vaderSentiment-3.3.2",
            host,
        )


def run(args):
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    root = Path(config["execution"]["output_root"]) / args.run_id / "sentiment"
    root.mkdir(parents=True, exist_ok=False)
    started = time.time()
    spark = SparkSession.builder.appName(args.run_id).config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    report = {"run_id": args.run_id, "method": "vaderSentiment-3.3.2"}
    try:
        reviews = spark.read.parquet(config["inputs"]["silver_root"] + "/reviews").select(
            "review_id", "parent_asin", "rating", "review_month", "text_normalized", "body_hash"
        )
        eligible = spark.read.parquet(config["inputs"]["text_features_root"]).filter("eligible_nlp").select("review_id")
        source = reviews.join(eligible, "review_id", "inner")
        expected = source.count()
        schema = "review_id string,parent_asin string,rating double,review_month string,body_hash string,compound double,sentiment string,method_version string,executor_host string"
        result = spark.createDataFrame(source.repartition(16).rdd.mapPartitions(score_partition), schema)
        result.write.mode("errorifexists").parquet(str(root / "reviews"))
        saved = spark.read.parquet(str(root / "reviews"))
        actual = saved.count()
        if actual != expected:
            raise ValueError(f"sentiment row mismatch: {actual} != {expected}")
        report.update(
            status="passed",
            input_rows=expected,
            output_rows=actual,
            sentiment_counts={r["sentiment"]: r["count"] for r in saved.groupBy("sentiment").count().collect()},
            executor_counts={r["executor_host"]: r["count"] for r in saved.groupBy("executor_host").count().collect()},
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["elapsed_seconds"] = round(time.time() - started, 2)
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        spark.stop()
    print("SENTIMENT_RESULT=" + json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/pipelines/config/analysis.yaml")
    parser.add_argument("--run-id", required=True)
    run(parser.parse_args())

