import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NLPEnvironmentContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "infra/compose.nlp.yaml"
        if not path.is_file():
            raise AssertionError("NLP-ENV: Compose configuration has not been implemented")
        result = subprocess.run([shutil.which("docker"), "compose", "-f", str(path),
                                 "--profile", "ml", "config", "--format", "json"],
                                check=True, capture_output=True, text=True, timeout=30)
        cls.services = json.loads(result.stdout)["services"]

    def test_offline_validation_has_no_network_or_raw_data(self):
        check = self.services["nlp-check"]
        self.assertEqual(check["network_mode"], "none")
        self.assertFalse(check.get("ports"))
        self.assertEqual(check["environment"]["HF_HUB_OFFLINE"], "1")
        models = [v for v in check["volumes"] if v["target"] == "/models"]
        self.assertTrue(models[0]["read_only"])
        self.assertNotIn("bronze", json.dumps(check))

    def test_cpu_resources_and_fixed_model_revisions(self):
        for service in self.services.values():
            self.assertLessEqual(int(service["mem_limit"]), 12 * 1024**3)
            self.assertLessEqual(float(service["cpus"]), 8)
        manifest = json.loads((ROOT / "ml/model-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest), {"distilbert", "minilm"})
        for model in manifest.values():
            self.assertRegex(model["revision"], r"^[a-f0-9]{40}$")
            self.assertIn("model.safetensors", model["files"])
            self.assertFalse(any(f.endswith((".py", ".bin")) for f in model["files"]))
