import unittest
from pipelines.event_summary import summarize


class EventEvidence(unittest.TestCase):
    def test_counts_actual_executors_tasks_failures_and_peak_metric(self):
        events = [
            {'Event':'SparkListenerApplicationStart','App ID':'app-test'},
            {'Event':'SparkListenerExecutorAdded','Executor ID':'1','Executor Info':{'Host':'worker-a'}},
            {'Event':'SparkListenerTaskEnd','Task Info':{'Host':'worker-a'},
             'Task End Reason':{'Reason':'Success'},'Task Metrics':{'Executor Run Time':20,'Peak Execution Memory':1024}},
            {'Event':'SparkListenerTaskEnd','Task Info':{'Host':'worker-b'},
             'Task End Reason':{'Reason':'ExceptionFailure'},'Task Metrics':{}},
            {'Event':'SparkListenerStageCompleted','Stage Info':{'Stage ID':2}},
            {'Event':'SparkListenerJobEnd','Job Result':{'Result':'JobSucceeded'}},
            {'Event':'SparkListenerApplicationEnd'},
        ]
        result=summarize(iter(events))
        self.assertEqual(result['application_id'],'app-test')
        self.assertEqual(result['successful_tasks_by_host'],{'worker-a':1})
        self.assertEqual(result['failed_task_reasons'],{'ExceptionFailure':1})
        self.assertEqual(result['max_task_peak_execution_memory_bytes'],1024)
        self.assertEqual(result['executor_run_time_ms_sum'],20)
        self.assertEqual(result['completed_stage_attempts'],1)
        self.assertEqual(result['successful_jobs'],1)
        self.assertTrue(result['application_end_seen'])


if __name__=='__main__':
    unittest.main()
