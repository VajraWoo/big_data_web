"""Bounded synthetic Spark assertions for joins and duplicate semantics."""
import json
from pyspark.sql import SparkSession
from cleaning import clean_record
from silver_job import make_frame, enrich_reviews, product_keys
from replay_check import comparable
from pyspark.sql import functions as F


def check_replay_detection(spark):
    base = spark.createDataFrame([('a', 'original', 'batch-a', {'b':'2','a':'1'})],
                                 'review_id string, text_raw string, processing_run_id string, flags map<string,string>')
    changed = base.withColumn('text_raw', F.lit('changed'))
    other_batch = base.withColumn('processing_run_id', F.lit('batch-b'))
    original_digest = comparable(base,'review_id').first().content
    assert original_digest == comparable(other_batch,'review_id').first().content
    assert original_digest != comparable(changed,'review_id').first().content


def main(spark):
    check_replay_detection(spark)
    raw = dict(rating=1, text='Not good!', title='', asin='A', parent_asin='P', user_id='U',
               timestamp=0, helpful_vote=0, verified_purchase=False)
    reviews = []
    for i, change in enumerate(({}, {}, {'user_id':'V', 'asin':'B'},
                                {'parent_asin':'NO'}, {'parent_asin':None}, {'parent_asin':'Q'}), 1):
        reviews.append(clean_record(dict(source_file='reviews.gz', source_line_number=i,
                                         raw_json=json.dumps(dict(raw, **change))), 'reviews', 'fixture'))
    products = [clean_record(dict(source_file='meta.gz', source_line_number=i,
                                 raw_json=json.dumps({'parent_asin':parent})),
                            'product_metadata', 'fixture') for i, parent in enumerate(['P','Q','Q'], 1)]
    result = enrich_reviews(make_frame(spark, reviews, 'reviews'),
                            product_keys(make_frame(spark, products, 'product_metadata')))
    rows = {r.source_line_number:r.asDict() for r in result.collect()}  # exactly six synthetic rows
    assert len(rows) == 6
    assert rows[1]['exact_group_size'] == 2
    assert rows[3]['exact_group_size'] == 1
    assert rows[1]['body_group_size'] == 6
    assert rows[1]['body_cross_user'] and rows[1]['body_cross_variant']
    assert rows[1]['metadata_join_status'] == 'matched'
    assert rows[4]['metadata_join_status'] == 'unmatched'
    assert rows[5]['metadata_join_status'] == 'missing_parent'
    assert rows[6]['metadata_join_status'] == 'ambiguous'
    assert rows[6]['metadata_id_joined'] is None
    print('SPARK_FIXTURE_PASS: six rows, duplicate groups and safe left joins', flush=True)


if __name__ == '__main__':
    session = SparkSession.builder.appName('silver-fixture').getOrCreate()
    session.sparkContext.setLogLevel('WARN')
    try:
        main(session)
    finally:
        session.stop()
