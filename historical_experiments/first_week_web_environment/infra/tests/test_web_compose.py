import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class WebComposeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run([
            shutil.which("docker"), "compose", "-f", str(ROOT / "infra/compose.yaml"),
            "-f", str(ROOT / "infra/compose.web.yaml"), "--profile", "web", "--profile", "tools",
            "config", "--format", "json",
        ], check=True, capture_output=True, text=True, timeout=30)
        cls.config = json.loads(result.stdout)

    def test_web_ports_are_localhost_only_and_frontend_has_no_database_access(self):
        services = self.config["services"]
        for name, port in [("backend", 8000), ("frontend", 5173)]:
            self.assertEqual(services[name]["ports"][0]["host_ip"], "127.0.0.1")
            self.assertEqual(services[name]["ports"][0]["target"], port)
        self.assertEqual(set(services["frontend"]["networks"]), {"web"})
        self.assertEqual(set(services["backend"]["networks"]), {"web", "database"})

    def test_combined_resource_budget_and_locked_base_images(self):
        memory = sum(int(s["mem_limit"]) for s in self.config["services"].values())
        self.assertLessEqual(memory, 18 * 1024**3)
        for folder in ["backend", "frontend"]:
            for line in (ROOT / folder / "Dockerfile").read_text(encoding="utf-8").splitlines():
                if line.startswith("FROM "):
                    self.assertRegex(line, r"@sha256:[a-f0-9]{64}( |$)")
        self.assertTrue((ROOT / "backend/uv.lock").is_file())
        self.assertTrue((ROOT / "frontend/package-lock.json").is_file())
