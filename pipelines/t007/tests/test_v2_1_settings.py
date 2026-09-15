import unittest

from pipelines.t007.prompt import PROMPT_VERSION, SYSTEM_PROMPT
from pipelines.t007.runner import DEFAULT_MAX_NEW_TOKENS


class V21SettingsTests(unittest.TestCase):
    def test_uses_observed_output_headroom(self):
        self.assertEqual(DEFAULT_MAX_NEW_TOKENS, 1024)

    def test_requires_concise_topics_and_evidence(self):
        self.assertEqual(PROMPT_VERSION, "t007-context-insight-v2.1")
        self.assertIn("short noun phrase", SYSTEM_PROMPT)
        self.assertIn("Do not copy a full sentence into topic_raw", SYSTEM_PROMPT)
        self.assertIn("shortest exact evidence", SYSTEM_PROMPT)

    def test_skips_actions_without_an_evaluation(self):
        self.assertIn("Do not extract instructions, actions, or background facts", SYSTEM_PROMPT)

    def test_clarifies_known_scope_failures(self):
        self.assertIn("replacement part, board, or kit", SYSTEM_PROMPT)
        self.assertIn("the appliance being repaired is other_product", SYSTEM_PROMPT)
        self.assertIn("X is noisier than Y", SYSTEM_PROMPT)
        self.assertIn("arrived crushed, dented, used, or broken", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
