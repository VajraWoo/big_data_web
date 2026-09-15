"""Build per-product positive/negative TF-IDF unigram and bigram themes."""

import argparse
import json
import math
from pathlib import Path
import time

import yaml
from pyspark.ml.feature import NGram, RegexTokenizer, StopWordsRemover
from pyspark.sql import SparkSession, Window, functions as F


def run(args):
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    root = Path(config["execution"]["output_root"]) / args.run_id / "themes"
    root.mkdir(parents=True, exist_ok=False)
    started = time.time()
    spark = SparkSession.builder.appName(args.run_id).config("spark.sql.shuffle.partitions", "48").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    report = {"run_id": args.run_id, "method": "spark-tfidf-ngram-1-2"}
    try:
        reviews = spark.read.parquet(config["inputs"]["silver_root"] + "/reviews").select(
            "review_id", "parent_asin", "text_normalized"
        )
        sentiment = spark.read.parquet(args.sentiment_path).select("review_id", "parent_asin", "sentiment")
        documents = reviews.join(sentiment.select("review_id", "sentiment"), "review_id").filter(
            F.col("sentiment").isin("positive", "negative")
        )

        minimum_reviews = int(config["scope"]["minimum_eligible_reviews"])
        eligible_products = sentiment.groupBy("parent_asin").count().filter(F.col("count") >= minimum_reviews).select("parent_asin")
        documents = documents.join(eligible_products, "parent_asin")

        tokenizer = RegexTokenizer(inputCol="text_normalized", outputCol="raw_tokens", pattern="[^A-Za-z]+", minTokenLength=3)
        remover = StopWordsRemover(inputCol="raw_tokens", outputCol="tokens", caseSensitive=False)
        tokenized = remover.transform(tokenizer.transform(documents))
        tokenized = tokenized.withColumn("tokens", F.expr("filter(tokens, x -> length(x) >= 3)"))
        tokenized = NGram(n=2, inputCol="tokens", outputCol="bigrams").transform(tokenized)
        terms = tokenized.select(
            "review_id", "parent_asin", "sentiment",
            F.explode(F.array_distinct(F.array_union("tokens", "bigrams"))).alias("theme"),
        ).filter(F.length("theme") > 0).persist()

        total_documents = documents.select("review_id").distinct().count()
        global_df = terms.groupBy("theme").agg(F.countDistinct("review_id").alias("global_df"))
        group_sizes = documents.groupBy("parent_asin", "sentiment").agg(F.countDistinct("review_id").alias("group_reviews"))
        scores = terms.groupBy("parent_asin", "sentiment", "theme").agg(
            F.countDistinct("review_id").alias("review_count")
        ).filter(F.col("review_count") >= int(config["themes"]["minimum_document_frequency"]))
        scores = scores.join(global_df, "theme").join(group_sizes, ["parent_asin", "sentiment"])
        scores = scores.withColumn(
            "tfidf_score",
            F.col("review_count") * (F.log(F.lit(total_documents + 1) / (F.col("global_df") + 1)) + F.lit(1.0)),
        ).withColumn("review_share", F.col("review_count") / F.col("group_reviews"))
        ranking = Window.partitionBy("parent_asin", "sentiment").orderBy(
            F.desc("tfidf_score"), F.desc("review_count"), F.asc("theme")
        )
        top = scores.withColumn("rank", F.row_number().over(ranking)).filter(
            F.col("rank") <= int(config["themes"]["maximum_per_product_sentiment"])
        ).withColumn(
            "theme_id", F.sha2(F.concat_ws("|", "parent_asin", "sentiment", "theme"), 256)
        ).withColumn("method_version", F.lit("spark-tfidf-ngram-1-2"))
        top = top.select(
            "theme_id", "parent_asin", "sentiment", "theme", "review_count", "group_reviews",
            "review_share", "tfidf_score", "rank", "method_version",
        ).persist()
        top.write.mode("errorifexists").parquet(str(root / "summary"))

        mappings = terms.join(
            top.select("theme_id", "parent_asin", "sentiment", "theme"),
            ["parent_asin", "sentiment", "theme"],
        ).select("theme_id", "review_id", "parent_asin", "sentiment").dropDuplicates(["theme_id", "review_id"])
        mappings.write.mode("errorifexists").parquet(str(root / "review_map"))

        saved_top = spark.read.parquet(str(root / "summary"))
        saved_map = spark.read.parquet(str(root / "review_map"))
        report.update(
            status="passed",
            input_documents=total_documents,
            eligible_products=eligible_products.count(),
            theme_rows=saved_top.count(),
            review_map_rows=saved_map.count(),
        )
        terms.unpersist()
        top.unpersist()
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report["elapsed_seconds"] = round(time.time() - started, 2)
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        spark.stop()
    print("TOPIC_RESULT=" + json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/pipelines/config/analysis.yaml")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--sentiment-path", required=True)
    run(parser.parse_args())
