import unittest

from prototypes.t007_context_insight.contract import (
    ContractError,
    build_record,
    validate_response,
)


class InsightContractTests(unittest.TestCase):
    def test_grounded_evidence_gets_exact_offsets(self):
        review = "This unit works great, but the drain hose is too short."
        response = {
            "insights": [
                {
                    "topic_raw": "drain hose length",
                    "polarity": "negative",
                    "evidence": "the drain hose is too short",
                    "target_scope": "current_product",
                }
            ]
        }

        result = validate_response(review, response)

        insight = result["insights"][0]
        self.assertEqual(insight["evidence_char_start"], 27)
        self.assertEqual(insight["evidence_char_end"], 54)

    def test_repeated_evidence_requires_explicit_occurrence(self):
        review = "it leaks; it leaks"
        response = {
            "insights": [
                {
                    "topic_raw": "leaking",
                    "polarity": "negative",
                    "evidence": "it leaks",
                    "target_scope": "current_product",
                }
            ]
        }

        with self.assertRaisesRegex(ContractError, "ambiguous evidence"):
            validate_response(review, response)

    def test_repeated_evidence_uses_requested_occurrence(self):
        review = "it leaks; it leaks"
        response = {
            "insights": [
                {
                    "topic_raw": "leaking",
                    "polarity": "negative",
                    "evidence": "it leaks",
                    "evidence_occurrence": 1,
                    "target_scope": "current_product",
                }
            ]
        }

        result = validate_response(review, response)

        self.assertEqual(result["insights"][0]["evidence_char_start"], 10)

    def test_record_includes_model_and_prompt_provenance(self):
        record = build_record(
            review_id="r1",
            parent_asin="p1",
            asin="a1",
            review_text="Works great.",
            response={"insights": []},
            model_id="Qwen/Qwen3.5-4B",
            revision="fixed-sha",
            prompt_version="t007-v1",
        )

        self.assertEqual(record["processing_status"], "success_no_insight")
        self.assertEqual(record["model_id"], "Qwen/Qwen3.5-4B")
        self.assertEqual(record["revision"], "fixed-sha")
        self.assertEqual(record["prompt_version"], "t007-v1")

    def test_topic_deduplication_is_case_insensitive(self):
        response = {
            "insights": [
                {
                    "topic_raw": "Noise",
                    "polarity": "negative",
                    "evidence": "very loud",
                    "target_scope": "current_product",
                },
                {
                    "topic_raw": "noise",
                    "polarity": "negative",
                    "evidence": "very loud",
                    "target_scope": "current_product",
                },
            ]
        }

        result = validate_response("It is very loud.", response)

        self.assertEqual(len(result["insights"]), 1)
        self.assertEqual(result["insights"][0]["topic_raw"], "Noise")

    def test_ambiguous_evidence_metrics_are_reported(self):
        response = {
            "insights": [
                {
                    "topic_raw": "leaking",
                    "polarity": "negative",
                    "evidence": "it leaks",
                    "evidence_occurrence": 1,
                    "target_scope": "current_product",
                }
            ]
        }

        result = validate_response("it leaks; it leaks", response)

        self.assertEqual(result["ambiguous_evidence_count"], 1)
        self.assertEqual(result["ambiguous_evidence_rate"], 1.0)

    def test_hallucinated_evidence_is_rejected(self):
        response = {
            "insights": [
                {
                    "topic_raw": "noise",
                    "polarity": "negative",
                    "evidence": "extremely noisy",
                    "target_scope": "current_product",
                }
            ]
        }

        with self.assertRaisesRegex(ContractError, "not found"):
            validate_response("It works well.", response)

    def test_unknown_enum_is_rejected(self):
        response = {
            "insights": [
                {
                    "topic_raw": "noise",
                    "polarity": "bad",
                    "evidence": "loud",
                    "target_scope": "the_product",
                }
            ]
        }

        with self.assertRaises(ContractError):
            validate_response("It is loud.", response)


if __name__ == "__main__":
    unittest.main()
