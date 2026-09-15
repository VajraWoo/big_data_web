import unittest

from t007_context_insight_v2_1.prompt import PROMPT_VERSION, SYSTEM_PROMPT


class PromptV2Tests(unittest.TestCase):
    def test_defines_service_logistics_as_external_service_only(self):
        self.assertEqual(PROMPT_VERSION, "t007-context-insight-v2.1")
        self.assertIn("shipping, delivery, seller support, returns, refunds, or warranty service", SYSTEM_PROMPT)
        self.assertIn("noise, leaking, breakage, failure, installation difficulty, and compatibility", SYSTEM_PROMPT)

    def test_requires_all_distinct_positive_and_negative_opinions(self):
        self.assertIn("Scan the entire review in order", SYSTEM_PROMPT)
        self.assertIn("Do not stop after the first opinion", SYSTEM_PROMPT)
        self.assertIn("both positive and negative", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
