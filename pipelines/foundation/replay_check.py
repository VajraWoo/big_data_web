"""Compare persisted deterministic rows across successful batches using Spark joins."""
import argparse
import json
from pathlib import Path
from pyspark.sql import SparkSession, functions as F, types as T
from cleaning import RELEASE
from silver_job import write_json


def comparable(df, identity):
    fields = []
    for field in sorted(df.schema.fields,key=lambda f:f.name):
        if field.name in ('processing_run_id','parser_executor_host'):
            continue
        value = F.col(field.name)
        if isinstance(field.dataType,T.MapType):
            value = F.map_from_entries(F.array_sort(F.map_entries(value)))
        fields.append(value.alias(field.name))
    return df.select(identity,F.sha2(F.to_json(F.struct(*fields),options={'ignoreNullFields':'false'}),256).alias('content'))


def compare(spark,left,right,folder,identity,subset=False):
    a,b = spark.read.parquet(str(left/folder)),spark.read.parquet(str(right/folder))
    for frame in (a,b):
        expected = F.sha2(F.concat_ws('\n',F.lit(RELEASE),F.col('source_file'),F.col('source_line_number').cast('string')),256)
        assert frame.filter(~F.col(identity).eqNullSafe(expected)).limit(1).count()==0, 'unstable identity'
    aa,bb = comparable(a,identity),comparable(b,identity)
    na,nb = aa.count(),bb.count()
    assert aa.select(identity).distinct().count()==na
    assert bb.select(identity).distinct().count()==nb
    assert aa.join(bb,identity,'left_anti').limit(1).count()==0,'missing replay IDs'
    if not subset:
        assert na==nb,(folder,na,nb)
    mismatches = aa.alias('a').join(bb.alias('b'),identity).filter(~F.col('a.content').eqNullSafe(F.col('b.content'))).count()
    assert mismatches==0,(folder,mismatches)
    return dict(folder=folder,left_rows=na,right_rows=nb,compared_rows=na,mismatches=mismatches,subset=subset)


def main(args):
    left,right = Path(args.left),Path(args.right)
    for root in (left,right):
        assert json.loads((root/'run.json').read_text())['status']=='passed_basic_silver'
    reports = [json.loads((root/'run.json').read_text()) for root in (left,right)]
    assert reports[0]['manifest_sha256']==reports[1]['manifest_sha256']
    assert reports[0]['rule_version']==reports[1]['rule_version']
    assert reports[0]['code_sha256']['cleaning.py']==reports[1]['code_sha256']['cleaning.py']
    spark=SparkSession.builder.appName('silver-replay-check').config('spark.sql.session.timeZone','UTC').getOrCreate()
    spark.sparkContext.setLogLevel('WARN')
    try:
        checks=[]
        for folder,identity,subset in [('_normalized/reviews','review_id',args.subset),
                                       ('_normalized/product_metadata','metadata_id',False),
                                       ('products','metadata_id',False)]:
            checks.append(compare(spark,left,right,folder,identity,subset))
        if not args.subset:
            checks.append(compare(spark,left,right,'reviews','review_id'))
        result=dict(status='PASS',application_id=spark.sparkContext.applicationId,left=str(left),right=str(right),checks=checks,
                    excluded_columns=['processing_run_id','parser_executor_host'],
                    note='Subset compares normalized source rows; final duplicate group counts depend on population.')
        write_json(args.output,result)
        print('REPLAY_RESULT='+json.dumps(result),flush=True)
    finally:
        spark.stop()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--left',required=True)
    parser.add_argument('--right',required=True)
    parser.add_argument('--subset',action='store_true')
    parser.add_argument('--output',required=True)
    main(parser.parse_args())
