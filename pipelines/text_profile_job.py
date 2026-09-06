"""Read existing Silver and write an independent, provisional language profile."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import time

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.window import Window
from text_profile import profile_rows


def partition(rows):
    import fasttext
    from tokenizers import Tokenizer
    model = fasttext.load_model('/models/fasttext/lid.176.bin')
    tokenizer = Tokenizer.from_file('/models/minilm/tokenizer.json')
    tokenizer.no_truncation()
    tokenizer.no_padding()
    def enriched(batch):
        results = profile_rows(batch, model)
        lengths = [len(x.ids) for x in tokenizer.encode_batch([r.text_normalized or '' for r in batch])]
        for result, length in zip(results,lengths,strict=True):
            result.update(token_count=length,executor_host=socket.gethostname())
            yield result
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == 256:
            yield from enriched(batch)
            batch = []
    if batch:
        yield from enriched(batch)


def run(args):
    root = Path('/data/silver') / args.run_id
    root.mkdir(exist_ok=False)
    started = time.time()
    lock = json.loads(Path('/pipelines/language-model-lock.json').read_text())['fasttext_lid_176']
    with open('/models/fasttext/lid.176.bin', 'rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == lock['sha256']
    spark = SparkSession.builder.appName(args.run_id).config('spark.sql.session.timeZone','UTC').config('spark.sql.shuffle.partitions','16').getOrCreate()
    spark.sparkContext.setLogLevel('WARN')
    report = dict(source=args.source, mode=args.mode, model=lock, application_id=spark.sparkContext.applicationId,
                  policy_status='provisional_not_manually_calibrated', min_confidence=0.8, min_alphabetic=5,
                  sentence_count_method='punctuation heuristic; abbreviations and decimals may overcount')
    try:
        source = spark.read.parquet(args.source + '/reviews')
        if args.mode == 'sample':
            source = source.orderBy(F.xxhash64('review_id')).limit(10000)
        n = source.count()
        cols = ['review_id','parent_asin','rating','review_month','text_normalized']
        schema = 'review_id string,parent_asin string,rating double,review_month string,char_count long,word_count long,sentence_count long,line_count long,alphabetic_count long,language string,language_confidence double,language_status string,eligible_nlp boolean,nlp_exclusion_reasons array<string>,executor_host string,token_count long'
        result = spark.createDataFrame(source.select(*cols).repartition(16).rdd.mapPartitions(partition), schema)
        result.write.mode('errorifexists').parquet(str(root/'text_features'))
        result = spark.read.parquet(str(root/'text_features'))
        assert result.count() == n
        assert result.select('review_id').distinct().count() == n
        assert source.select('review_id').join(result, 'review_id', 'left_anti').count() == 0
        report['rows'] = n
        for column in ['language','language_status','executor_host']:
            report[column] = [r.asDict() for r in result.groupBy(column).count().orderBy(F.desc('count')).limit(200).collect()]
        english = result.filter('eligible_nlp')
        report['provisional_english_rows'] = english.count()
        report['english_lengths'] = {}
        report['tokenizer'] = dict(name='all-MiniLM-L6-v2',revision='1110a243fdf4706b3f48f1d95db1a4f5529b4d41',sha256=hashlib.sha256(Path('/models/minilm/tokenizer.json').read_bytes()).hexdigest(),special_tokens=True,truncation=False,padding=False)
        report['token_overflow_counts'] = {str(t):english.filter(F.col('token_count')>t).count() for t in [128,256,512]}
        for column in ['char_count','word_count','sentence_count','line_count','token_count']:
            report['english_lengths'][column] = dict(mean=english.agg(F.avg(column)).first()[0],
                quantiles=dict(zip(['p50','p90','p95','p99'],english.approxQuantile(column,[.5,.9,.95,.99],.001))))
        for name, frame in [('monthly',result.groupBy('review_month').count()),
                            ('english_by_rating',english.groupBy('rating').agg(F.count('*').alias('count'),F.avg('word_count').alias('mean_words'))),
                            ('english_by_month',english.groupBy('review_month').agg(F.count('*').alias('count'),F.avg('word_count').alias('mean_words')))]:
            frame.write.mode('errorifexists').parquet(str(root/name))
            report[name] = [r.asDict() for r in frame.orderBy(frame.columns[0]).limit(500).collect()]
        months = result.filter('review_month is not null').select('parent_asin','review_month').distinct().withColumn('month_index',F.substring('review_month',1,4).cast('int')*12+F.substring('review_month',6,2).cast('int'))
        months = months.withColumn('gap',F.col('month_index')-F.lag('month_index').over(Window.partitionBy('parent_asin').orderBy('month_index'))-1)
        gaps = months.groupBy('parent_asin').agg(F.max('gap').alias('longest_internal_gap_months'))
        coverage = result.groupBy('parent_asin').agg(F.count('*').alias('reviews'),F.sum(F.col('eligible_nlp').cast('long')).alias('provisional_english'),F.min('review_month').alias('first_month'),F.max('review_month').alias('last_month'),F.countDistinct('review_month').alias('active_months'))
        coverage.join(gaps,'parent_asin','left').write.mode('errorifexists').parquet(str(root/'product_coverage'))
        report['threshold_candidates'] = {str(t):result.filter((F.col('language')=='en') & (F.col('language_confidence')>=t)).count() for t in [.7,.8,.9]}
        report['status']='passed_profile_provisional_policy'
    except Exception as error:
        report.update(status='failed',error=str(error))
        raise
    finally:
        report['elapsed_seconds']=round(time.time()-started,2)
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        spark.stop()
    print('PROFILE_RESULT='+json.dumps(report),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default='/data/silver/silver-full-20260903T154909-6c310067')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--mode',choices=['sample','full'],required=True)
    run(parser.parse_args())
