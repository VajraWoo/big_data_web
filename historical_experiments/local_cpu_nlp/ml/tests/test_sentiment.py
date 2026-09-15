import unittest

from ml.sentiment import label_compound


class VaderSentimentRules(unittest.TestCase):
    def test_uses_standard_vader_thresholds(self):
        self.assertEqual(label_compound(0.05), "positive")
        self.assertEqual(label_compound(0.0499), "neutral")
        self.assertEqual(label_compound(-0.0499), "neutral")
        self.assertEqual(label_compound(-0.05), "negative")

    def test_rejects_scores_outside_compound_range(self):
        with self.assertRaises(ValueError):
            label_compound(1.01)


if __name__ == "__main__":
    unittest.main()
