"""Real cluster acceptance, synthetic records only; NOT the Silver pipeline."""

import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import time
import urllib.request
import uuid

from pyspark.sql import SparkSession, functions as F


BRONZE = Path("/data/bronze/amazon_reviews_2023/appliances")
EXPECTED = {
    "Appliances.jsonl.gz": "150f209befceaa6f837abc997065b2d251034bbbda19bebc4ad56dac779730c2",
    "meta_Appliances.jsonl.gz": "5a94cffb9ec3be23e42b99643fcab5f48160b3c7a53835451c4457aadcdf9365",
}


def check_partition(rows):
    # Runs in executor Python processes, not on the submitting driver.
    count = sum(1 for _ in rows)
    for filename in EXPECTED:
        with gzip.open(BRONZE / filename, "rt", encoding="utf-8") as stream:
            assert isinstance(json.loads(stream.readline()), dict)
    time.sleep(0.2)
    yield socket.gethostname(), count


if __name__ == "__main__":
    with urllib.request.urlopen("http://spark-master:8080/json/", timeout=10) as response:
        master = json.load(response)
    workers = {w["host"] for w in master["workers"] if w["state"] == "ALIVE"}
    assert workers == {"spark-worker-1", "spark-worker-2"}, workers
    for filename, expected in EXPECTED.items():
        with (BRONZE / filename).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        assert actual == expected, f"Bronze checksum mismatch: {filename}"
    assert platform.python_version_tuple()[:2] == ("3", "12"), platform.python_version()

    spark = SparkSession.builder.appName("week1-environment-smoke").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    try:
        assert spark.sparkContext.master == "spark://spark-master:7077"
        assert spark.version == "4.1.2", spark.version
        java_version = spark.sparkContext._jvm.java.lang.System.getProperty("java.version")
        assert java_version.startswith("21."), java_version
        n = 100_000
        df = spark.range(n, numPartitions=16)
        partition_results = df.rdd.mapPartitions(check_partition).collect()
        executor_hosts = {host for host, _ in partition_results}
        assert executor_hosts == workers, executor_hosts
        assert sum(count for _, count in partition_results) == n
        total = df.agg(F.sum("id")).first()[0]
        assert total == n * (n - 1) // 2
        path = f"/opt/spark/work-dir/environment/{uuid.uuid4().hex}"
        df.write.mode("errorifexists").parquet(path)
        reread = spark.read.parquet(path).agg(F.count("*"), F.sum("id")).first()
        assert tuple(reread) == (n, total), reread
        report = {
            "status": "PASS", "application_id": spark.sparkContext.applicationId,
            "spark": spark.version, "java": java_version, "python": platform.python_version(),
            "worker_hosts": sorted(workers), "executor_hosts": sorted(executor_hosts),
            "rows": n, "sum": total, "partitions": len(partition_results),
            "bronze_sha256": EXPECTED, "parquet_path": path,
            "scope": "synthetic environment check, not Silver cleaning",
        }
        Path(path + ".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("ENVIRONMENT_RESULT=" + json.dumps(report, sort_keys=True), flush=True)
    finally:
        spark.stop()
