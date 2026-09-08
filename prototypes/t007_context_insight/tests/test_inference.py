import unittest
import json
import tempfile
from pathlib import Path

from prototypes.t007_context_insight.inference import (
    DeviceError,
    ensure_external_output,
    ensure_model_on_xpu,
    failure_record,
    require_text_raw,
    validate_model_manifest,
)


class _Device:
    def __init__(self, device_type):
        self.type = device_type


class _Parameter:
    def __init__(self, device_type):
        self.device = _Device(device_type)


class _Model:
    def __init__(self, device_types):
        self._parameters = [_Parameter(item) for item in device_types]

    def parameters(self):
        return iter(self._parameters)


class InferenceSafetyTests(unittest.TestCase):
    def test_text_raw_is_required_without_review_text_fallback(self):
        with self.assertRaisesRegex(ValueError, "requires text_raw"):
            require_text_raw({"review_text": "wrong coordinate system"})

    def test_text_raw_is_used_even_when_review_text_is_present(self):
        self.assertEqual(
            require_text_raw({"text_raw": "raw", "review_text": "processed"}),
            "raw",
        )

    def test_output_inside_git_workspace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the Git workspace"):
            ensure_external_output(
                Path(r"D:\CS_Projects\big_data_web\tmp\result.jsonl")
            )

    def test_model_with_cpu_parameter_is_rejected(self):
        with self.assertRaisesRegex(DeviceError, "non-XPU"):
            ensure_model_on_xpu(_Model(["xpu", "cpu"]))

    def test_model_fully_on_xpu_is_accepted(self):
        ensure_model_on_xpu(_Model(["xpu", "xpu"]))

    def test_failed_record_keeps_product_provenance_and_attempts(self):
        error = RuntimeError("bad output")
        error.attempts = 2

        record = failure_record(
            {"review_id": "r1", "parent_asin": "p1", "asin": "a1"}, error
        )

        self.assertEqual(record["parent_asin"], "p1")
        self.assertEqual(record["asin"], "a1")
        self.assertEqual(record["attempts"], 2)

    def test_manifest_revision_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            model_dir = Path(directory)
            (model_dir / "model_manifest.json").write_text(
                json.dumps(
                    {
                        "model_id": "Qwen/Qwen3.5-4B",
                        "revision": "wrong-sha",
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "config.json").write_text(
                json.dumps(
                    {
                        "model_type": "qwen3_5",
                        "architectures": ["Qwen3_5ForConditionalGeneration"],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "revision mismatch"):
                validate_model_manifest(model_dir)


if __name__ == "__main__":
    unittest.main()
