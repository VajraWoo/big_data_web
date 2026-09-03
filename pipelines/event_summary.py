"""Stream uncompressed Spark event logs into small execution evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path


def summarize(events):
    result=dict(application_id=None,executors={},successful_tasks_by_host={},failed_task_reasons={},
                completed_stage_attempts=0,failed_stage_attempts=0,successful_jobs=0,failed_jobs=0,
                executor_run_time_ms_sum=0,max_task_peak_execution_memory_bytes=0,application_end_seen=False,
                note='Peak execution memory is a Spark task metric, not container RSS or total physical memory.')
    hosts,failures=Counter(),Counter()
    for event in events:
        kind=event.get('Event')
        if kind=='SparkListenerApplicationStart':
            result['application_id']=event['App ID']
        elif kind=='SparkListenerApplicationEnd':
            result['application_end_seen']=True
        elif kind=='SparkListenerExecutorAdded':
            result['executors'][event['Executor ID']]=event['Executor Info']['Host']
        elif kind=='SparkListenerTaskEnd':
            reason=event.get('Task End Reason',{}).get('Reason','unknown')
            if reason=='Success':
                hosts[event['Task Info']['Host']]+=1
            else:
                failures[reason]+=1
            metrics=event.get('Task Metrics',{})
            result['executor_run_time_ms_sum']+=metrics.get('Executor Run Time',0)
            result['max_task_peak_execution_memory_bytes']=max(result['max_task_peak_execution_memory_bytes'],metrics.get('Peak Execution Memory',0))
        elif kind=='SparkListenerStageCompleted':
            result['completed_stage_attempts']+=1
            if event['Stage Info'].get('Failure Reason'):
                result['failed_stage_attempts']+=1
        elif kind=='SparkListenerJobEnd':
            key='successful_jobs' if event.get('Job Result',{}).get('Result')=='JobSucceeded' else 'failed_jobs'
            result[key]+=1
    result['successful_tasks_by_host']=dict(hosts)
    result['failed_task_reasons']=dict(failures)
    return result


def read_events(root):
    files=sorted(Path(root).glob('events_*'))
    if not files:
        raise ValueError('No Spark event files found')
    for path in files:
        if path.suffix=='.zstd':
            raise ValueError('Use spark.eventLog.compress=false for this evidence reader')
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                yield json.loads(line)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('event_directory')
    parser.add_argument('output')
    args=parser.parse_args()
    result=summarize(read_events(args.event_directory))
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
