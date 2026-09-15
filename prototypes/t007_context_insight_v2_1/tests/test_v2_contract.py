import unittest

from t007_context_insight_v2_1.contract import build_partial_record


class PartialRecordTests(unittest.TestCase):
    def test_keeps_valid_insight_when_another_insight_has_bad_evidence(self):
        text = "Works well, but the hose leaks."
        response = {"insights": [
            {"topic_raw": "performance", "polarity": "positive", "evidence": "Works well", "target_scope": "current_product"},
            {"topic_raw": "leak", "polarity": "negative", "evidence": "the hose is leaking badly", "target_scope": "current_product"},
        ]}
        record = build_partial_record(
            review_id="r1", parent_asin="p", asin="a", review_text=text,
            response=response, model_id="m", revision="rev", prompt_version="v2",
        )
        self.assertEqual(record["processing_status"], "partial_success")
        self.assertEqual(len(record["insights"]), 1)
        self.assertEqual(record["insights"][0]["evidence"], "Works well")
        self.assertEqual(len(record["rejected_insights"]), 1)
        self.assertEqual(record["rejected_insights"][0]["index"], 1)

    def test_marks_record_failed_only_when_no_generated_insight_is_valid(self):
        record = build_partial_record(
            review_id="r2", parent_asin="p", asin="a", review_text="The hose leaks.",
            response={"insights": [{"topic_raw": "leak", "polarity": "negative", "evidence": "not copied from review", "target_scope": "current_product"}]},
            model_id="m", revision="rev", prompt_version="v2",
        )
        self.assertEqual(record["processing_status"], "failed")
        self.assertEqual(record["insights"], [])
        self.assertEqual(len(record["rejected_insights"]), 1)

    def test_empty_model_response_remains_success_no_insight(self):
        record = build_partial_record(
            review_id="r3", parent_asin="p", asin="a", review_text="Background only.",
            response={"insights": []}, model_id="m", revision="rev", prompt_version="v2",
        )
        self.assertEqual(record["processing_status"], "success_no_insight")
        self.assertEqual(record["rejected_insights"], [])


if __name__ == "__main__":
    unittest.main()
