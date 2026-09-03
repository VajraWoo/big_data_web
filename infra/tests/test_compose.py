"""Configuration acceptance. Run with: python -m unittest discover -s infra/tests -v."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ComposeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compose = ROOT / "infra/compose.yaml"
        if not compose.is_file():
            raise AssertionError("ENV-01: infra/compose.yaml has not been implemented")
        docker = shutil.which("docker")
        if docker is None:
            raise RuntimeError("Docker CLI must be on PATH")
        result = subprocess.run(
            [docker, "compose", "-f", str(compose), "--profile", "tools", "config", "--format", "json"],
            text=True, capture_output=True, check=True, timeout=30,
        )
        cls.config = json.loads(result.stdout)
        cls.services = cls.config["services"]

    def test_master_two_workers_and_driver_exist(self):
        self.assertEqual(set(self.services), {
            "spark-master", "spark-worker-1", "spark-worker-2", "spark-driver", "mongodb",
        })

    def test_images_are_digest_pinned(self):
        for service in self.services.values():
            if "build" in service:
                dockerfile = (ROOT / "infra/spark/Dockerfile").read_text(encoding="utf-8")
                bases = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
                self.assertEqual(len(bases), 2)
                for base in bases:
                    self.assertRegex(base, r"@sha256:[a-f0-9]{64}( |$)")
                self.assertIn("3.12.12", dockerfile)
            else:
                self.assertRegex(service["image"], r"@sha256:[a-f0-9]{64}$")
            self.assertNotIn(":latest", service["image"])

    def test_no_public_ports_or_database_port(self):
        self.assertFalse(self.services["mongodb"].get("ports"))
        for service in self.services.values():
            for port in service.get("ports", []):
                self.assertEqual(port["host_ip"], "127.0.0.1")
                self.assertNotIn(port["target"], [27017, 7077])
        self.assertTrue(self.config["networks"]["database"]["internal"])
        self.assertEqual(set(self.services["mongodb"]["networks"]), {"database", "default"})
        for name in ["spark-master", "spark-worker-1", "spark-worker-2"]:
            self.assertEqual(set(self.services[name]["networks"]), {"default"})

    def test_bronze_is_read_only_on_all_spark_nodes(self):
        for name, service in self.services.items():
            if name.startswith("spark-"):
                bronze = [v for v in service["volumes"] if v["target"] == "/data/bronze"]
                self.assertEqual(len(bronze), 1)
                self.assertTrue(bronze[0]["read_only"])

    def test_resource_limits_and_healthchecks(self):
        memory = sum(int(service["mem_limit"]) for service in self.services.values())
        self.assertLessEqual(memory, 17 * 1024**3)
        for name, service in self.services.items():
            self.assertGreater(float(service["cpus"]), 0)
            if name != "spark-driver":
                self.assertIn("healthcheck", service)


if __name__ == "__main__":
    unittest.main()
