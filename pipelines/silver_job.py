"""Spark Standalone Silver batch. No pandas, unbounded collect or implicit schema inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import socket
import sys
import time
import traceback

from pyspark.sql import SparkSession, functions as F, types as T
from cleaning import RELEASE, RULE_VERSION, clean_record, select_lines, stage_file

COMMON = '''data_release_id string, processing_run_id string, silver_rule_version string,
source_file string, source_line_number long, raw_json string, raw_bytes_base64 string,
parse_status string, parse_error_code string, exact_hash string, parent_asin string,
field_status map<string,string>, field_types map<string,string>, field_issues array<string>,
parser_executor_host string'''
REVIEW = '''review_id string, asin string, user_id_hash string, title_raw string, text_raw string,
text_normalized string, text_length long, text_status string, body_hash string, language string,
rating double, rating_valid boolean, low_rating boolean, timestamp_ms long, reviewed_at_iso string,
review_month string, helpful_vote long, verified_purchase boolean, eligible_rating_stats boolean,
eligible_text boolean, eligible_nlp boolean, rating_exclusion_reasons array<string>,
text_exclusion_reasons array<string>, nlp_exclusion_reasons array<string>,
near_duplicate_cluster_id string, rating_text_mismatch boolean, burst_flag boolean,
advanced_quality_status string'''
PRODUCT = '''metadata_id string, title string, store string, main_category string, price double,
categories array<string>, details_json string, features_json string, description_json string,
metadata_status string'''


def schema(role):
    return T._parse_datatype_string(COMMON + ', ' + (REVIEW if role == 'reviews' else PRODUCT))


def make_frame(spark, rows, role):
    return spark.createDataFrame(rows, schema(role))


def parse_partition(rows, role, run_id):
    host = socket.gethostname()
    for line in rows:
        record = clean_record(json.loads(line), role, run_id)
        record['parser_executor_host'] = host
        yield record


def product_keys(products):
    return (products.filter(F.col('parent_asin').isNotNull()).groupBy('parent_asin')
            .agg(F.count('*').alias('metadata_key_count'), F.min('metadata_id').alias('_candidate_id'))
            .withColumn('metadata_id_joined', F.when(F.col('metadata_key_count') == 1, F.col('_candidate_id')))
            .drop('_candidate_id'))


def enrich_reviews(reviews, keys):
    exact = reviews.groupBy('exact_hash').agg(F.count('*').alias('exact_group_size'))
    bodies = (reviews.filter(F.col('body_hash').isNotNull()).groupBy('body_hash')
              .agg(F.count('*').alias('body_group_size'),
                   F.countDistinct('user_id_hash').alias('body_distinct_users'),
                   F.countDistinct('parent_asin').alias('body_distinct_parents'),
                   F.countDistinct('asin').alias('body_distinct_asins')))
    result = reviews.join(exact, 'exact_hash', 'left').join(bodies, 'body_hash', 'left').join(keys, 'parent_asin', 'left')
    result = (result.withColumn('exact_duplicate', F.col('exact_group_size') > 1)
              .withColumn('body_duplicate', F.coalesce(F.col('body_group_size') > 1, F.lit(False)))
              .withColumn('body_cross_user', F.coalesce(F.col('body_distinct_users') > 1, F.lit(False)))
              .withColumn('body_cross_parent', F.coalesce(F.col('body_distinct_parents') > 1, F.lit(False)))
              .withColumn('body_cross_variant', F.coalesce(F.col('body_distinct_asins') > 1, F.lit(False)))
              .withColumn('reviewed_at', F.to_timestamp('reviewed_at_iso'))
              .withColumn('metadata_join_status',
                          F.when(F.col('parent_asin').isNull(), 'missing_parent')
                          .when(F.col('metadata_key_count').isNull(), 'unmatched')
                          .when(F.col('metadata_key_count') > 1, 'ambiguous').otherwise('matched')))
    return result


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def bounded_counts(df, column, denominator, limit=1000):
    rows = df.groupBy(column).count().orderBy(F.col(column).asc_nulls_first()).limit(limit+1).collect()
    if len(rows) > limit:
        raise ValueError(f'Unexpected cardinality in bounded metric {column}')
    return [dict(value=r[0], numerator=r[1], denominator=denominator) for r in rows]


def fingerprint(df, identity):
    # Commutative hash sum plus count and min/max; row-level replay comparison is separate.
    columns = sorted(c for c in df.columns if c not in ('processing_run_id', 'parser_executor_host'))
    hashed = df.select(identity, F.sha2(F.to_json(F.struct(*columns), options={'ignoreNullFields':'false'}),256).alias('content_digest'))
    stat = hashed.agg(F.count('*').alias('rows'), F.countDistinct(identity).alias('unique_ids'),
                      F.sum(F.xxhash64(identity, 'content_digest').cast('decimal(38,0)')).alias('content_hash_sum'),
                      F.min(identity).alias('min_id'), F.max(identity).alias('max_id')).first().asDict()
    stat['content_hash_sum'] = str(stat['content_hash_sum'])
    return stat


def validate_and_profile(spark, root, inputs):
    result = dict(denominator_policy='Each metric explicitly names its population; duplicates are marked, never removed.')
    frames = {}
    for role, folder, quarantine, identity in (
            ('reviews','reviews','quarantine_reviews','review_id'),
            ('product_metadata','products','quarantine_products','metadata_id')):
        df, q = spark.read.parquet(str(root/folder)), spark.read.parquet(str(root/quarantine))
        frames[role] = df
        stats, qstats = fingerprint(df, identity), fingerprint(q, identity)
        expected = inputs[role]['rows_selected']
        assert stats['rows'] + qstats['rows'] == expected, (role, stats, qstats, expected)
        assert stats['unique_ids'] == stats['rows'] and qstats['unique_ids'] == qstats['rows']
        assert df.select(identity).join(q.select(identity), identity).limit(1).count() == 0
        source_ids = df.select(identity,'source_line_number').union(q.select(identity,'source_line_number'))
        assert source_ids.select('source_line_number').distinct().count() == expected
        result[role] = dict(input_rows=expected, retained=stats, quarantine=qstats,
                            parse_errors=bounded_counts(q,'parse_error_code',expected),
                            field_issues=bounded_counts(df.select(F.explode('field_issues').alias('issue')),'issue',stats['rows']),
                            parser_hosts=bounded_counts(df, 'parser_executor_host', stats['rows']))
        type_rows = df.select(F.explode('field_types').alias('field','type')).groupBy('field','type').count().limit(1000).collect()
        result[role]['field_types'] = [dict(field=r.field, type=r.type, numerator=r['count'], denominator=stats['rows']) for r in type_rows]
        write_json(root/(folder+'_schema.json'),df.schema.jsonValue())
        # Restrict human readback to lineage and typed columns; raw text remains in local Parquet.
        sample_cols = [identity, 'source_line_number', 'parent_asin', 'parse_status']
        if role == 'reviews':
            sample_cols += ['rating','reviewed_at','text_status','metadata_join_status']
        result[role]['readback_sample'] = [r.asDict() for r in df.orderBy('source_line_number').select(*sample_cols).limit(5).collect()]
    reviews, products = frames['reviews'], frames['product_metadata']
    n = result['reviews']['retained']['rows']
    for col in ('rating','review_month','text_status','language','metadata_join_status','verified_purchase',
                'eligible_rating_stats','eligible_text','eligible_nlp','exact_duplicate','body_duplicate',
                'body_cross_user','body_cross_parent','body_cross_variant','advanced_quality_status'):
        result['reviews'][col] = bounded_counts(reviews,col,n)
    for col in ('rating_exclusion_reasons','text_exclusion_reasons','nlp_exclusion_reasons'):
        result['reviews'][col] = bounded_counts(reviews.select(F.explode(col).alias('reason')),'reason',n)
    result['reviews']['text_length_quantiles'] = dict(zip(['p50','p90','p95','p99'], reviews.approxQuantile('text_length',[.5,.9,.95,.99],.001)))
    result['reviews']['helpful_vote_quantiles'] = dict(zip(['p50','p90','p95','p99'], reviews.approxQuantile('helpful_vote',[.5,.9,.95,.99],.001)))
    result['reviews']['utc_range'] = reviews.agg(F.min('reviewed_at').alias('min'),F.max('reviewed_at').alias('max')).first().asDict()
    duplicate_summary = reviews.agg(
        (F.count('*')-F.countDistinct('exact_hash')).alias('exact_extra_occurrences'),
        (F.count('body_hash')-F.countDistinct('body_hash')).alias('body_extra_occurrences')).first().asDict()
    result['reviews']['duplicate_extra_occurrences'] = {k:dict(numerator=v,denominator=n) for k,v in duplicate_summary.items()}
    for name, expr in dict(helpful_zero=F.col('helpful_vote')==0, helpful_invalid=F.col('helpful_vote').isNull(),
                           asin_missing=F.col('asin').isNull(),parent_missing=F.col('parent_asin').isNull()).items():
        result['reviews'][name] = dict(numerator=reviews.filter(expr).count(),denominator=n)
    profiles = root/'profiles'
    for col in ('rating','review_month','text_length'):
        reviews.groupBy(col).count().write.mode('errorifexists').parquet(str(profiles/col))
    product_counts = reviews.groupBy('parent_asin').agg(F.count('*').alias('review_count'),
                F.sum(F.col('eligible_text').cast('long')).alias('basic_text_count'),
                F.countDistinct('review_month').alias('active_months'))
    product_counts.write.mode('errorifexists').parquet(str(profiles/'product_review_counts'))
    product_counts.groupBy('review_count').count().write.mode('errorifexists').parquet(str(profiles/'product_count_distribution'))
    result['candidate_thresholds'] = dict(status='not_calibrated', selected=None,
       basis='20/50/100 from existing spec; coverage only, no uncertainty, manual evaluation or backtest yet',
       candidates=[dict(min_basic_text_count=t, numerator=product_counts.filter((F.col('parent_asin').isNotNull()) & (F.col('basic_text_count')>=t)).count(),
                        denominator=product_counts.filter(F.col('parent_asin').isNotNull()).count()) for t in (20,50,100)])
    result['product_metadata']['metadata_status'] = bounded_counts(products,'metadata_status',result['product_metadata']['retained']['rows'])
    keys = spark.read.parquet(str(root/'product_keys'))
    result['product_metadata']['duplicate_parent_keys'] = dict(numerator=keys.filter('metadata_key_count > 1').count(),denominator=keys.count())
    result['status'] = 'passed_basic_silver'
    return result


def run(args):
    started = time.time()
    root = Path(args.output)/args.run_id
    root.mkdir(parents=True, exist_ok=False)
    report = dict(processing_run_id=args.run_id, mode=args.mode, started_at=datetime.now(timezone.utc).isoformat(),
                  rule_version=RULE_VERSION, data_release_id=RELEASE, status='registered', command=sys.argv,
                  seed=args.seed, shuffle_partitions=16, python=platform.python_version(),
                  image='big-data-web-spark:4.1.2-python3.12.12-v2', code_sha256={})
    for path in Path(__file__).parent.glob('*.py'):
        report['code_sha256'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    spark = None
    def checkpoint(status):
        report['status'] = status
        report['elapsed_seconds'] = round(time.time()-started,3)
        write_json(root/'run.json',report)
        print('SILVER_PROGRESS='+json.dumps(dict(status=status,run_id=args.run_id,elapsed_seconds=report['elapsed_seconds'])),flush=True)
    try:
        manifest_path = Path(args.bronze)/'manifest.json'
        report['manifest_sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        report['manifest'] = manifest
        report['inputs'] = {}
        checkpoint('staging')
        for info in manifest['files']:
            role = info['role']
            selected = select_lines(info['records'],10000,args.seed) if args.mode=='sample' and role=='reviews' else None
            if selected is not None:
                write_json(root/'sample_lines.json',sorted(selected))
                report['sample_line_sha256'] = hashlib.sha256((root/'sample_lines.json').read_bytes()).hexdigest()
                report['sampling_method'] = 'Python3.12 Random(seed).sample, without replacement, manifest line population'
            report['inputs'][role] = stage_file(Path(args.bronze)/info['path'],info,root/'_staging'/role,selected,
                                               shard_rows=1000 if args.mode=='sample' else 50000)
            checkpoint('staged_'+role)
        spark = (SparkSession.builder.appName('silver-'+args.mode+'-'+args.run_id)
                 .config('spark.sql.session.timeZone','UTC').config('spark.sql.shuffle.partitions','16')
                 .config('spark.sql.adaptive.enabled','true').getOrCreate())
        spark.sparkContext.setLogLevel('WARN')
        assert spark.sparkContext.master == 'spark://spark-master:7077'
        report.update(application_id=spark.sparkContext.applicationId, spark=spark.version,
                      java=spark.sparkContext._jvm.java.lang.System.getProperty('java.version'))
        checkpoint('processing')
        clean_frames = {}
        for role, output, quarantine in (('reviews','reviews','quarantine_reviews'),
                                          ('product_metadata','products','quarantine_products')):
            run_id = args.run_id
            raw_rdd = spark.sparkContext.textFile(str(root/'_staging'/role/'*.jsonl'),minPartitions=16)
            parsed = raw_rdd.mapPartitions(lambda rows, role=role: parse_partition(rows,role,run_id))
            df = make_frame(spark,parsed,role)
            normalized_path = str(root/'_normalized'/role)
            df.write.mode('errorifexists').parquet(normalized_path)
            df = spark.read.parquet(normalized_path)
            df.filter(F.col('parse_status')!='ok').write.mode('errorifexists').parquet(str(root/quarantine))
            clean_frames[role] = df.filter(F.col('parse_status')=='ok')
            checkpoint('parsed_'+role)
        products = clean_frames['product_metadata']
        products.write.mode('errorifexists').parquet(str(root/'products'))
        keys = product_keys(products)
        keys.write.mode('errorifexists').parquet(str(root/'product_keys'))
        reviews = enrich_reviews(clean_frames['reviews'], spark.read.parquet(str(root/'product_keys')))
        reviews.write.mode('errorifexists').parquet(str(root/'reviews'))
        spark.read.parquet(str(root/'reviews')).select('asin','parent_asin').distinct().write.mode('errorifexists').parquet(str(root/'variants'))
        checkpoint('validating')
        quality = validate_and_profile(spark,root,report['inputs'])
        hosts = {v['value'] for v in quality['reviews']['parser_hosts'] if v['numerator']>0}
        assert hosts == {'spark-worker-1','spark-worker-2'}, hosts
        report['actual_parser_hosts'] = sorted(hosts)
        write_json(root/'quality.json',quality)
        checkpoint('passed_basic_silver')
        print('SILVER_RESULT='+json.dumps(report),flush=True)
    except Exception:
        report['error'] = traceback.format_exc()
        checkpoint('failed')
        raise
    finally:
        if spark is not None:
            spark.stop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['sample','full'],required=True)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--seed',type=int,default=20260903)
    parser.add_argument('--bronze',default='/data/bronze/amazon_reviews_2023/appliances')
    parser.add_argument('--output',default='/data/silver')
    run(parser.parse_args())
