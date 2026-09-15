import unittest

from ml.demands import is_demand_candidate, normalize_label


class DemandRules(unittest.TestCase):
    def test_detects_explicit_request_markers_case_insensitively(self):
        self.assertTrue(is_demand_candidate("I wish the cord were longer."))
        self.assertTrue(is_demand_candidate("This NEEDS a quieter motor."))

    def test_does_not_match_marker_inside_another_word(self):
        self.assertFalse(is_demand_candidate("The renewed unit works."))

    def test_accepts_only_the_fixed_four_labels(self):
        self.assertEqual(normalize_label("功能建议"), "功能建议")
        with self.assertRaises(ValueError):
            normalize_label("新标签")


if __name__ == "__main__":
    unittest.main()
