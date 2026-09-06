"""Text profiling runtime must be reproducible on every Spark executor."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
DOCKER = shutil.which('docker') or shutil.which('docker.exe') or Path(
    'C:/Users/31407/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe'
)


class TextProfileRuntime(unittest.TestCase):
    def test_fasttext_runtime_and_locked_language_model(self):
        dockerfile = (ROOT / 'infra/spark/Dockerfile').read_text(encoding='utf-8')
        self.assertIn('fasttext==0.9.3', dockerfile)

        lock = json.loads((ROOT / 'pipelines/language-model-lock.json').read_text(encoding='utf-8'))
        model = lock['fasttext_lid_176']
        self.assertEqual(model['filename'], 'fasttext/lid.176.bin')
        self.assertEqual(model['url'], 'https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.bin')
        self.assertRegex(model['sha256'], r'^[0-9a-f]{64}$')

    def test_model_mount_is_read_only_on_driver_and_workers(self):
        command = [str(DOCKER), 'compose', '-f', str(ROOT/'infra/compose.yaml'),
                   '-f', str(ROOT/'infra/compose.silver.yaml'), '--profile', 'tools',
                   'config', '--format', 'json']
        config = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        for name in ('spark-worker-1', 'spark-worker-2', 'spark-driver'):
            volumes = {volume['target']: volume for volume in config['services'][name]['volumes']}
            self.assertTrue(volumes['/models']['read_only'])


if __name__ == '__main__':
    unittest.main()
