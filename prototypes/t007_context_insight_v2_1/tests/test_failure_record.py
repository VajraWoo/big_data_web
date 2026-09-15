import unittest
from t007_context_insight_v2_1.runner import failure_record

class FailureRecordTests(unittest.TestCase):
    def test_preserves_raw_output_for_diagnosis(self):
        record = failure_record({"review_id": "r"}, ValueError("bad"), 2, '{"insights":[]}')
        self.assertEqual(record["raw_output"], '{"insights":[]}')

if __name__ == "__main__":
    unittest.main()
