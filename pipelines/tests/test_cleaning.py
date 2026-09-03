import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pipelines.cleaning import clean_record, stable_id, select_lines, stage_file


def review(**changes):
    value = dict(rating=5.0, title='Good', text='Not bad! 😊', asin='A', parent_asin='P',
                 user_id='U', timestamp=1694476800000, helpful_vote=0, verified_purchase=True)
    value.update(changes)
    return value


def clean(value, line=1, role='reviews'):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return clean_record(dict(source_file='test.gz', source_line_number=line, raw_json=raw,
                             raw_bytes_base64=None), role, 'test-run')


class CleaningRules(unittest.TestCase):
    def test_extreme_scores_empty_text_remain_rating_eligible(self):
        for score in (1, 5):
            row = clean(review(rating=score, text='  '))
            self.assertTrue(row['eligible_rating_stats'])
            self.assertFalse(row['eligible_text'])
            self.assertFalse(row['eligible_nlp'])
            self.assertEqual(row['text_status'], 'empty')
            self.assertEqual(row['parse_status'], 'ok')

    def test_invalid_rating_type_range_and_missing(self):
        for score in (True, '5', 0, 6, None, [], {}):
            row = clean(review(rating=score))
            self.assertFalse(row['eligible_rating_stats'])
            self.assertIsNone(row['rating'])
            self.assertTrue(row['rating_exclusion_reasons'])
            self.assertEqual(row['parse_status'], 'ok')
        self.assertTrue(clean(review(rating=4.5))['rating_valid'])

    def test_raw_text_preserved_and_nlp_unknown(self):
        raw = '  Not <b>bad</b>! 😊 e\u0301\n  '
        row = clean(review(text=raw))
        self.assertEqual(row['text_raw'], raw)
        self.assertEqual(row['text_normalized'], 'Not <b>bad</b>! 😊 é')
        self.assertTrue(row['eligible_text'])
        self.assertIsNone(row['eligible_nlp'])
        self.assertEqual(row['language'], 'unknown')
        for field in ('rating_text_mismatch', 'burst_flag', 'near_duplicate_cluster_id'):
            self.assertIsNone(row[field])
        for body in ('你好', '😊', 'https://example.com', '<br>'):
            self.assertIsNone(clean(review(text=body))['eligible_nlp'])

    def test_bad_json_nonobject_duplicate_keys_nonfinite_are_quarantined(self):
        for raw in ('{', '[]', 'null', '{"x":1,"x":2}', '{"rating":NaN}'):
            row = clean(raw)
            self.assertEqual(row['parse_status'], 'quarantined')
            self.assertEqual(row['raw_json'], raw)
            self.assertTrue(row['parse_error_code'])

    def test_timestamp_utc_and_invalid_fields(self):
        row = clean(review(timestamp=0))
        self.assertEqual(row['reviewed_at_iso'], '1970-01-01T00:00:00+00:00')
        self.assertEqual(row['review_month'], '1970-01')
        for stamp in ('1694476800000', True, -1, 1696118400000, 10**50):
            self.assertIsNone(clean(review(timestamp=stamp))['reviewed_at_iso'])
        for votes in (-1, True, 1.5, '2', 2**63):
            self.assertIsNone(clean(review(helpful_vote=votes))['helpful_vote'])
        self.assertIsNone(clean(review(verified_purchase='true'))['verified_purchase'])
        self.assertFalse(clean(review(verified_purchase=False))['verified_purchase'])

    def test_lineage_identity_is_independent_of_content_and_batch(self):
        row = clean(review())
        self.assertEqual(row['review_id'], clean(review(text='Changed'))['review_id'])
        self.assertNotEqual(row['review_id'], clean(review(), line=2)['review_id'])
        self.assertEqual(row['review_id'], stable_id('test.gz', 1))
        self.assertEqual(row['asin'], 'A')
        self.assertEqual(row['parent_asin'], 'P')
        self.assertNotEqual(row['user_id_hash'], 'U')

    def test_exact_hash_and_body_hash_have_different_meanings(self):
        a, b, c = clean(review()), clean(review(), line=2), clean(review(user_id='V'))
        self.assertEqual(a['exact_hash'], b['exact_hash'])
        self.assertNotEqual(a['exact_hash'], c['exact_hash'])
        self.assertEqual(a['body_hash'], c['body_hash'])
        self.assertIsNone(clean(review(text=''))['body_hash'])

    def test_field_issues_distinguish_missing_null_and_type(self):
        value = review(text=42, title=None)
        del value['asin']
        row = clean(value)
        self.assertEqual(row['field_status']['asin'], 'missing')
        self.assertEqual(row['field_status']['title'], 'null')
        self.assertEqual(row['field_status']['text'], 'invalid_type')
        self.assertEqual(row['field_types']['text'], 'int')
        self.assertIn('text:invalid_type', row['field_issues'])

    def test_metadata_preserves_nested_source_and_does_not_fill_price(self):
        row = clean(dict(parent_asin='P', title='Product', price=None,
                         categories=['Appliances'], details={'Brand': 'X'}), role='product_metadata')
        self.assertEqual(row['parent_asin'], 'P')
        self.assertIsNone(row['price'])
        self.assertEqual(json.loads(row['details_json']), {'Brand': 'X'})
        self.assertEqual(row['categories'], ['Appliances'])
        self.assertIn('price:null', row['field_issues'])

    def test_random_sample_is_stable_distinct_and_spans_source(self):
        chosen = select_lines(2128605, 10000, 20260903)
        self.assertEqual(chosen, select_lines(2128605, 10000, 20260903))
        self.assertEqual(len(chosen), 10000)
        self.assertGreater(max(chosen), 2100000)
        self.assertLess(min(chosen), 10000)

    def test_staging_hash_count_selection_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'raw.gz'
            with gzip.open(source, 'wb') as out:
                out.write(b'{"rating":1}\n\xff\n{"rating":5}\n')
            before = source.read_bytes()
            info = dict(path=source.name, bytes=len(before), records=3,
                        sha256=hashlib.sha256(before).hexdigest())
            result = stage_file(source, info, root / 'staged', {2, 3}, shard_rows=1)
            self.assertEqual(result['rows_scanned'], 3)
            self.assertEqual(result['rows_selected'], 2)
            rows = [json.loads(p.read_text()) for p in sorted((root/'staged').glob('*.jsonl'))]
            self.assertEqual([r['source_line_number'] for r in rows], [2, 3])
            self.assertTrue(rows[0]['raw_bytes_base64'])
            self.assertEqual(clean_record(rows[0], 'reviews', 'run')['parse_error_code'], 'invalid_utf8')
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(ValueError):
                stage_file(source, dict(info, sha256='0'*64), root/'bad', None)
            with self.assertRaises(ValueError):
                stage_file(source, dict(info, records=4), root/'bad_count', None)


if __name__ == '__main__':
    unittest.main()
