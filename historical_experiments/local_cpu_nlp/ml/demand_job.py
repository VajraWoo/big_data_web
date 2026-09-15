"""Classify explicit request candidates with one fixed pretrained zero-shot model."""

import argparse
import json
from pathlib import Path
import socket
import time

import yaml
from pyspark.sql import SparkSession, functions as F


MODEL_ID = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"
MODEL_REVISION = "8e7e5af5983a0ddb1a5b45a38b129ab69e2258e8"
LABEL_MAP = {
    "feature request": "功能建议",
    "quality complaint": "质量抱怨",
    "praise": "表扬",
    "other": "其他",
}


def classify_partition(rows):
    from transformers import pipeline

    classifier = pipeline(
        "zero-shot-classification",
        model=MODEL_ID,
        revision=MODEL_REVISION,
        device=-1,
    )
    host = socket.gethostname()
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == 8:
            yield from classify_batch(classifier, batch, host)
            batch.clear()
    if batch:
        yield from classify_batch(classifier, batch, host)


def classify_batch(classifier, rows, host):
    outputs = classifier(
        [row.text_normalized[:4000] for row in rows],
        candidate_labels=list(LABEL_MAP),
        hypothesis_template="This customer review is a {}.",
        multi_label=False,
        batch_size=8,
        truncation=True,
    )
    if isinstance(outputs, dict):
        outputs = [outputs]
    for row, output in zip(rows, outputs):
        english_label = output["labels"][0]
        yield (
            row.review_id, row.parent_asin, row.review_month, row.body_hash, row.text_normalized,
            LABEL_MAP[english_label], float(output["scores"][0]), english_label,
            MODEL_ID, MODEL_REVISION, host,
        )


def run(args):
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    root = Path(config["execution"]["output_root"]) / args.run_id / "demands"
    root.mkdir(parents=True, exist_ok=False)
    started = time.time()
    spark = SparkSession.builder.appName(args.run_id).config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    report = {"run_id": args.run_id, "method": MODEL_ID, "revision": MODEL_REVISION}
    try:
        reviews = spark.read.parquet(config["inputs"]["silver_root"] + "/reviews").select(
            "review_id", "parent_asin", "review_month", "body_hash", "text_normalized"
        )
        eligible = spark.read.parquet(config["inputs"]["text_features_root"]).filter("eligible_nlp").select("review_id")
        source = reviews.join(eligible, "review_id")
        minimum_reviews = int(config["scope"]["minimum_eligible_reviews"])
        products = source.groupBy("parent_asin").count().filter(F.col("count") >= minimum_reviews).select("parent_asin")
        candidates = source.join(products, "parent_asin").filter(
            F.lower("text_normalized").rlike(r"\b(wish(es|ed|ing)?|need(s|ed|ing)?|should|could|would like|if only|hope(s|d|ing)?)\b")
        )
        candidate_count = candidates.count()
        schema = "review_id string,parent_asin string,review_month string,body_hash string,text_normalized string,label string,score double,label_en string,model_id string,model_revision string,executor_host string"
        classified = spark.createDataFrame(candidates.repartition(16).rdd.mapPartitions(classify_partition), schema)
        classified.write.mode("errorifexists").parquet(str(root / "classified"))
        saved = spark.read.parquet(str(root / "classified"))
        actual = saved.count()
        if actual != candidate_count:
            raise ValueError(f"demand row mismatch: {actual} != {candidate_count}")
        saved.filter(F.col("label") == config["demands"]["accepted_label"]).write.mode("errorifexists").parquet(
            str(root / "accepted")
        )
        report.update(
            status="passed",
            candidate_rows=candidate_count,
            output_rows=actual,
            accepted_rows=spark.read.parquet(str(root / "accepted")).count(),
            label_counts={row["label"]: row["count"] for row in saved.groupBy("label").count().collect()},
            executor_counts={row["executor_host"]: row["count"] for row in saved.groupBy("executor_host").count().collect()},
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["elapsed_seconds"] = round(time.time() - started, 2)
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        spark.stop()
    print("DEMAND_RESULT=" + json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/pipelines/config/analysis.yaml")
    parser.add_argument("--run-id", required=True)
    run(parser.parse_args())
