import _bootstrap  # noqa: F401
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gnome_web_display import paths, settings, doctor

ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    def test_version_has_one_source_of_truth(self):
        self.assertEqual(paths.VERSION, (ROOT / 'VERSION').read_text().strip())
        self.assertEqual(settings.VERSION, paths.VERSION)

    def test_package_roots(self):
        self.assertEqual(paths.ROOT, ROOT)
        self.assertEqual(paths.WEB_ROOT, ROOT / 'web')
        self.assertEqual(paths.CONFIG_ROOT, ROOT / 'config')

    def test_all_moved_files_exist(self):
        for file in ('web/index.html', 'web/login.html', 'web/demo.html',
                     'config/mediamtx.yml', 'config/config.example.toml',
                     'scripts/start.sh', 'scripts/setup.sh', 'scripts/verify.sh'):
            with self.subTest(file=file):
                self.assertTrue((ROOT / file).is_file())

    def test_root_no_longer_contains_application_implementations(self):
        for file in ('app.py', 'host.py', 'launcher.py', 'settings.py', 'doctor.py',
                     'security.py', 'input_protocol.py', 'index.html', 'login.html',
                     'demo.html', 'mediamtx.yml', 'config.example.toml'):
            with self.subTest(file=file):
                self.assertFalse((ROOT / file).exists())

    def test_start_wrapper_works_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, VSCREEN_PYTHON=sys.executable)
            result = subprocess.run(['bash', str(ROOT / 'start.sh'), '--version'], cwd=directory,
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), paths.VERSION)

    def test_run_wrapper_preserves_version_flag(self):
        result = subprocess.run(['bash', str(ROOT / 'run.sh'), '--version'],
                                env=dict(os.environ, VSCREEN_PYTHON=sys.executable),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), paths.VERSION)

    def test_doctor_resolves_new_files(self):
        findings = doctor.collect(settings.Settings(), demo=True, ports=False)
        self.assertFalse([f for f in findings if f.code == 'file'])


if __name__ == '__main__':
    unittest.main()
