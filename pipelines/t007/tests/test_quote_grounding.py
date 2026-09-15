import unittest
from pipelines.t007.contract import validate_response

class QuoteGroundingTests(unittest.TestCase):
    def test_unique_quote_variant_is_grounded_back_to_text_raw(self):
        text = 'The "empty water tank" indicator quit working.'
        response = {"insights": [{
            "topic_raw": "indicator",
            "polarity": "negative",
            "evidence": "The 'empty water tank' indicator quit working.",
            "target_scope": "current_product",
        }]}
        insight = validate_response(text, response)["insights"][0]
        self.assertEqual(insight["evidence"], text)
        self.assertEqual((insight["evidence_char_start"], insight["evidence_char_end"]), (0, len(text)))

if __name__ == "__main__":
    unittest.main()
