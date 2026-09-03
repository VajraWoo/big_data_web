"""Real standalone Spark/Mongo round trip; bounded synthetic data only."""
import hashlib
import json
from pathlib import Path
import platform
import socket
import time
import uuid

from pyspark.sql import SparkSession, functions as F


def probe_partition(rows):
    count = sum(1 for _ in rows)
    with socket.create_connection(("mongodb", 27017), timeout=5):
        pass
    time.sleep(0.2)
    yield socket.gethostname(), count


if __name__ == "__main__":
    spark = (SparkSession.builder.appName("week1-mongodb-connector-smoke")
             .config("spark.sql.session.timeZone", "UTC").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    client = None
    try:
        jvm = spark.sparkContext._jvm
        # Fail before DB writes if the connector is not on the actual JVM classpath.
        jvm.java.lang.Class.forName("com.mongodb.spark.sql.connector.MongoTableProvider")
        assert spark.sparkContext.master == "spark://spark-master:7077"
        hashes = {}
        for line in Path("/opt/spark/connector-jars.sha256").read_text().splitlines():
            expected, filename = line.split()
            with (Path("/opt/spark/jars") / filename).open("rb") as stream:
                assert hashlib.file_digest(stream, "sha256").hexdigest() == expected
            hashes[filename] = expected
        n = 256
        probe = spark.range(n, numPartitions=8).rdd.mapPartitions(probe_partition).collect()
        hosts = sorted({host for host, count in probe if count > 0})
        assert hosts == ["spark-worker-1", "spark-worker-2"], probe
        assert sum(count for _, count in probe) == n
        run_id = uuid.uuid4().hex
        collection = "connector_" + run_id
        uri = "mongodb://mongodb:27017/?serverSelectionTimeoutMS=5000&connectTimeoutMS=5000"
        client = jvm.com.mongodb.client.MongoClients.create(uri)
        database = client.getDatabase("environment_checks")
        coll = database.getCollection(collection)
        assert coll.countDocuments() == 0
        frame = (spark.range(n, numPartitions=8)
                 .withColumn("_id", F.concat(F.lit(run_id + "-"), F.col("id")))
                 .withColumn("rating", (F.col("id") % 5 + 1).cast("double"))
                 .withColumn("verified", F.col("id") % 2 == 0)
                 .withColumn("text", F.when(F.col("id") % 3 == 0, F.lit(None).cast("string"))
                             .otherwise(F.lit("环境检查：ice maker — café")))
                 .withColumn("tags", F.when(F.col("id") % 2 == 0, F.array().cast("array<string>"))
                             .otherwise(F.array(F.lit("test"), F.lit("中文"))))
                 .withColumn("metadata", F.struct(F.lit("synthetic").alias("source"),
                                                  F.lit(run_id).alias("run_id")))
                 .withColumn("created_at", F.timestamp_millis(F.lit(1704067200123) + F.col("id"))))
        expected = [row.asDict(recursive=True) for row in frame.orderBy("id").collect()]
        options = {"connection.uri": uri, "database": "environment_checks", "collection": collection}
        def write():
            (frame.write.format("mongodb").mode("append").options(**options)
             .option("operationType", "replace").option("upsertDocument", "true")
             .option("idFieldList", "_id").option("ignoreNullValues", "false")
             .option("writeConcern.w", "1").option("writeConcern.journal", "true").save())

        write()
        assert coll.countDocuments() == n
        read = (spark.read.format("mongodb").schema(frame.schema).options(**options)
                .option("partitioner", "com.mongodb.spark.sql.connector.read.partitioner.SinglePartitionPartitioner")
                .option("mode", "FAILFAST").load())
        actual = [row.asDict(recursive=True) for row in read.orderBy("id").collect()]
        assert actual == expected, "MongoDB round-trip changed values"
        # MongoDB itself checks BSON types, independently of the Spark reader schema.
        types = {"id": "long", "rating": "double", "verified": "bool", "tags": "array",
                 "metadata": "object", "created_at": "date", "_id": "string"}
        for field, bson_type in types.items():
            query = jvm.org.bson.Document.parse(json.dumps({field: {"$type": bson_type}}))
            assert coll.countDocuments(query) == n, (field, bson_type)
        null_query = jvm.org.bson.Document.parse('{"text":{"$type":"null"}}')
        null_count = coll.countDocuments(null_query)
        assert null_count == 86
        write()
        assert coll.countDocuments() == n, "Replaying identical IDs created duplicates"
        repeated = [row.asDict(recursive=True) for row in read.orderBy("id").collect()]
        assert repeated == expected
        report = {
            "status": "PASS", "scope": "synthetic connector environment only",
            "application_id": spark.sparkContext.applicationId, "spark": spark.version,
            "python": platform.python_version(), "java": jvm.java.lang.System.getProperty("java.version"),
            "mongodb": database.runCommand(jvm.org.bson.Document.parse('{"buildInfo":1}')).getString("version"),
            "connector": "11.1.0", "java_driver": "5.1.4", "sha256": hashes,
            "executor_hosts": hosts, "database": "environment_checks", "collection": collection,
            "rows": n, "write_partitions": frame.rdd.getNumPartitions(), "null_text_rows": null_count,
            "round_trip_equal": True, "bson_types": types, "replay_rows": n,
        }
        target = Path("/opt/spark/work-dir/connector")
        target.mkdir(exist_ok=True)
        (target / f"{run_id}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("CONNECTOR_RESULT=" + json.dumps(report, sort_keys=True), flush=True)
    finally:
        if client is not None:
            client.close()
        spark.stop()
