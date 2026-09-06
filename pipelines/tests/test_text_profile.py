import math
import unittest

from pipelines.text_profile import assess_language, basic_text_features, fasttext_input, profile_rows


class TextProfileRules(unittest.TestCase):
    def test_counts_unicode_characters_english_words_sentences_and_lines(self):
        text = "It's well-made.\nWorks 24/7! 😊"

        result = basic_text_features(text)

        self.assertEqual(result['char_count'], len(text))
        self.assertEqual(result['word_count'], 4)
        self.assertEqual(result['sentence_count'], 2)
        self.assertEqual(result['line_count'], 2)
        self.assertEqual(result['alphabetic_count'], 16)

    def test_empty_text_has_zero_counts_and_is_not_nlp_eligible(self):
        self.assertEqual(
            basic_text_features(''),
            dict(char_count=0, word_count=0, sentence_count=0,
                 line_count=0, alphabetic_count=0),
        )
        result = assess_language('', None, None)
        self.assertEqual(result['language'], 'unknown')
        self.assertEqual(result['language_status'], 'empty')
        self.assertFalse(result['eligible_nlp'])
        self.assertEqual(result['nlp_exclusion_reasons'], ['text:empty'])

    def test_language_policy_separates_accepted_low_confidence_short_and_non_english(self):
        accepted = assess_language('This product works well.', '__label__en', 0.95)
        uncertain = assess_language('This product works well.', '__label__en', 0.79)
        short = assess_language('OK', '__label__en', 0.99)
        spanish = assess_language('Este producto funciona bien.', '__label__es', 0.97)

        self.assertEqual((accepted['language'], accepted['language_status'], accepted['eligible_nlp']),
                         ('en', 'accepted', True))
        self.assertEqual(uncertain['language_status'], 'low_confidence')
        self.assertFalse(uncertain['eligible_nlp'])
        self.assertEqual(short['language_status'], 'too_short')
        self.assertEqual(spanish['language_status'], 'non_english')

    def test_non_linguistic_and_invalid_prediction_are_explicitly_rejected(self):
        non_linguistic = assess_language('123 !!! 😊', '__label__en', 0.99)
        invalid = assess_language('A readable English sentence.', 'en', math.nan)

        self.assertEqual(non_linguistic['language_status'], 'non_linguistic')
        self.assertEqual(invalid['language_status'], 'invalid_prediction')
        self.assertFalse(non_linguistic['eligible_nlp'])
        self.assertFalse(invalid['eligible_nlp'])

    def test_fasttext_input_is_one_utf8_compatible_line(self):
        self.assertEqual(fasttext_input('  first\nsecond\tthird  '), 'first second third')

    def test_profile_rows_batches_predictable_text_and_preserves_context(self):
        class Predictor:
            def predict(self, texts, k=1):
                self.texts = texts
                return ([['__label__en'], ['__label__es']], [[0.96], [0.93]])

        predictor = Predictor()
        rows = [
            dict(review_id='1', parent_asin='P', rating=5.0, review_month='2023-01',
                 text_normalized='Works very well.'),
            dict(review_id='2', parent_asin='P', rating=2.0, review_month='2023-02',
                 text_normalized='Funciona bastante bien.'),
            dict(review_id='3', parent_asin='Q', rating=3.0, review_month=None,
                 text_normalized='😊 !!!'),
        ]

        result = profile_rows(rows, predictor, min_alphabetic=5, min_confidence=0.8)

        self.assertEqual(predictor.texts, ['Works very well.', 'Funciona bastante bien.'])
        self.assertEqual([row['language_status'] for row in result],
                         ['accepted', 'non_english', 'non_linguistic'])
        self.assertEqual(result[0]['review_id'], '1')
        self.assertEqual(result[0]['parent_asin'], 'P')
        self.assertEqual(result[0]['word_count'], 3)


if __name__ == '__main__':
    unittest.main()
