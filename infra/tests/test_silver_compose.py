"""Silver mounts must agree across the existing Spark cluster."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SilverMounts(unittest.TestCase):
    def test_cluster_mounts_and_resources(self):
        command = [shutil.which('docker'),'compose','-f',str(ROOT/'infra/compose.yaml'),
                   '-f',str(ROOT/'infra/compose.silver.yaml'),'--profile','tools','config','--format','json']
        config = json.loads(subprocess.run(command,check=True,capture_output=True,text=True).stdout)
        services = config['services']
        mounts = []
        for name in ('spark-master','spark-worker-1','spark-worker-2','spark-driver'):
            volumes = {v['target']:v for v in services[name]['volumes']}
            self.assertTrue(volumes['/data/bronze']['read_only'])
            self.assertTrue(volumes['/pipelines']['read_only'])
            self.assertFalse(volumes['/data/silver'].get('read_only',False))
            mounts.append(tuple(volumes[p]['source'] for p in ('/data/bronze','/pipelines','/data/silver')))
        self.assertEqual(len(set(mounts)),1)
        self.assertEqual(int(services['spark-driver']['mem_limit']),3*1024**3)
        self.assertEqual(int(services['spark-worker-1']['mem_limit']),5*1024**3)
        self.assertEqual(int(services['spark-worker-2']['mem_limit']),5*1024**3)
