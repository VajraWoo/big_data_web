"""Contract for baked-in MongoDB JARs and executor connectivity."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ConnectorConfig(unittest.TestCase):
    def test_pinned_jars_are_baked_into_spark(self):
        dockerfile = (ROOT / "infra/spark/Dockerfile").read_text()
        additions = [line for line in dockerfile.splitlines() if line.startswith("ADD --checksum=")]
        self.assertEqual(len(additions), 5)
        for line in additions:
            self.assertRegex(line, r"--checksum=sha256:[a-f0-9]{64} https://repo.maven.apache.org/")
            self.assertIn("/opt/spark/jars/", line)
        self.assertIn("mongo-spark-connector_2.13-11.1.0.jar", dockerfile)
        self.assertIn("mongodb-driver-sync-5.1.4.jar", dockerfile)

    def test_mongodb_is_reachable_from_executor_network_without_public_port(self):
        result = subprocess.run([shutil.which("docker"), "compose", "-f", str(ROOT / "infra/compose.yaml"),
                                 "config", "--format", "json"], check=True, capture_output=True, text=True)
        services = json.loads(result.stdout)["services"]
        mongo = services["mongodb"]
        self.assertFalse(mongo.get("ports"))
        for name in ["spark-worker-1", "spark-worker-2"]:
            self.assertTrue(set(services[name]["networks"]) & set(mongo["networks"]))


if __name__ == "__main__":
    unittest.main()
