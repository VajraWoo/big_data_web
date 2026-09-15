import math
import unittest

from pipelines.topics import document_terms, tfidf_score


class TopicRules(unittest.TestCase):
    def test_builds_unique_unigrams_and_bigrams(self):
        terms = document_terms("Filter leaks badly; filter leaks.")
        self.assertEqual(terms, ["filter", "leaks", "badly", "filter leaks", "leaks badly", "badly filter"])

    def test_scores_group_frequency_with_global_idf(self):
        expected = 8 * (math.log((101) / (11)) + 1.0)
        self.assertAlmostEqual(tfidf_score(8, 10, 100), expected)

    def test_rejects_invalid_counts(self):
        with self.assertRaises(ValueError):
            tfidf_score(1, 11, 10)


if __name__ == "__main__":
    unittest.main()
