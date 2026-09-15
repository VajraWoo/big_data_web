import json
import tempfile
import unittest
from pathlib import Path

from pipelines.t007.runner import chunked, load_completed_review_ids, percentile


class RunnerTests(unittest.TestCase):
    def test_resume_reads_every_written_review_id(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.jsonl"
            output.write_text(
                json.dumps({"review_id": "done-success", "processing_status": "success"}) + "\n"
                + json.dumps({"review_id": "done-failed", "processing_status": "failed"}) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(load_completed_review_ids(output), {"done-success", "done-failed"})

    def test_chunked_preserves_order(self):
        self.assertEqual(list(chunked([1, 2, 3, 4, 5], 2)), [[1, 2], [3, 4], [5]])

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(percentile([1, 2, 3, 100], 0.95), 100)
        self.assertEqual(percentile([], 0.95), 0)


if __name__ == "__main__":
    unittest.main()
