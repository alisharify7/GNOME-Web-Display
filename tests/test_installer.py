"""Offline installer integration tests using REAL Git repositories and shell processes.

Only the fixture's setup/start programs are stubs. No network, APT, Docker or
real host changes are performed. Root CI containers drop privilege for installs.
"""
import os
from pathlib import Path
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'install.sh'
REMOTE_URL = 'https://github.com/alisharify7/GNOME-Web-Display.git'


@unittest.skipUnless(shutil.which('git') and os.name == 'posix', 'Git and POSIX required')
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='gwd-installer-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / 'home'
        self.seed = self.base / 'seed'
        self.remote = self.base / 'remote.git'
        self.home.mkdir()
        self.seed.mkdir()
        self.log = self.home / 'calls.log'
        self.install_dir = self.home / 'installed versions'
        self.env = dict(os.environ)
        for key in tuple(self.env):
            if key.startswith(('GIT_', 'VSCREEN_', 'GWD_TEST_')):
                self.env.pop(key)
        self.env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL=str(self.home / '.gitconfig'),
                        GWD_TEST_LOG=str(self.log), GWD_TEST_REPAIRED=str(self.home / 'repaired'))
        self.uid = 65534 if os.geteuid() == 0 else os.getuid()
        self.gid = 65534 if os.geteuid() == 0 else os.getgid()
        self.git('init', '-q', '-b', 'main', str(self.seed), initial=True)
        self.git('-C', str(self.seed), 'config', 'user.name', 'Installer Test', initial=True)
        self.git('-C', str(self.seed), 'config', 'user.email', 'test@example.invalid', initial=True)
        (self.seed / 'setup.sh').write_text('''#!/usr/bin/env bash
set -eu
if [[ "${1:-}" == --check ]]; then
  echo check >> "$GWD_TEST_LOG"
  exit "${GWD_TEST_PACKAGE_STATUS:-0}"
fi
printf 'setup:%s\\n' "$*" >> "$GWD_TEST_LOG"
if [[ "${GWD_TEST_TTY:-0}" == 1 ]]; then
  [[ -t 0 ]] || exit 55
  read -r -p 'Fixture setup confirmation: ' answer
  [[ "$answer" == go ]] || exit 56
fi
[[ "${GWD_TEST_SETUP_STATUS:-0}" == 0 ]] || exit "$GWD_TEST_SETUP_STATUS"
: > "$GWD_TEST_REPAIRED"
''')
        (self.seed / 'start.sh').write_text('''#!/usr/bin/env bash
set -eu
if [[ "${1:-}" == --doctor ]]; then
  echo doctor >> "$GWD_TEST_LOG"
  if [[ -f "$GWD_TEST_REPAIRED" ]]; then exit "${GWD_TEST_AFTER:-0}"; fi
  exit "${GWD_TEST_BEFORE:-0}"
fi
[[ "${GWD_TEST_TTY:-0}" != 1 || -t 0 ]] || exit 57
printf 'start:%s\\n' "$*" >> "$GWD_TEST_LOG"
exit "${GWD_TEST_START_STATUS:-0}"
''')
        (self.seed / 'VERSION').write_text('2.0.0\n')
        (self.seed / '.gitignore').write_text('config.toml\npassword.txt\n__pycache__/\n')
        self.git('-C', str(self.seed), 'add', '.', initial=True)
        self.git('-C', str(self.seed), 'commit', '-qm', 'Fixture', initial=True)
        for tag in ('v1.0.0', 'v2.0.0', 'v2.2.0', 'v2.10.0', 'v3.0.0-rc.1', 'not-a-version'):
            self.git('-C', str(self.seed), 'tag', tag, initial=True)
        self.git('-C', str(self.seed), 'tag', '-a', 'v1.4.0', '-m', 'Annotated tag', initial=True)
        self.git('clone', '-q', '--bare', str(self.seed), str(self.remote), initial=True)
        self.git('config', '--file', str(self.home / '.gitconfig'),
                 f'url.file://{self.remote}.insteadOf', REMOTE_URL, initial=True)
        self.owned(self.base)
        # Copy outside the user's private project path so unprivileged tests can read it.
        self.installer = self.home / 'install.sh'
        self.installer.write_bytes(INSTALLER.read_bytes())
        self.owned(self.installer)

    def owned(self, path):
        if os.geteuid() == 0:
            if path.is_dir():
                for item in path.rglob('*'):
                    if not item.is_symlink():
                        os.chown(item, self.uid, self.gid)
            os.chown(path, self.uid, self.gid)

    def process(self, args, initial=False, **kwargs):
        options = dict(env=self.env, cwd=self.base, text=True, capture_output=True, timeout=20)
        if not initial and os.geteuid() == 0:
            options.update(user=self.uid, group=self.gid, extra_groups=[])
        options.update(kwargs)
        return subprocess.run(args, **options)

    def git(self, *args, initial=False):
        result = self.process(['git', *args], initial=initial)
        if result.returncode:
            raise AssertionError(result.stderr)
        return result.stdout.strip()

    def run_install(self, *args, expected=0, env=None):
        if env:
            self.env.update(env)
        result = self.process(['bash', str(self.installer), '--install-dir', str(self.install_dir), *args],
                              stdin=subprocess.DEVNULL, start_new_session=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def publish_file(self, name, text, tag='v4.0.0'):
        path = self.seed / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        self.owned(self.seed)
        self.git('-C', str(self.seed), 'add', '.')
        self.git('-C', str(self.seed), 'commit', '-qm', 'New fixture')
        self.git('-C', str(self.seed), 'tag', tag)
        self.git('-C', str(self.seed), 'push', '-q', str(self.remote), f'refs/tags/{tag}')

    def test_list_numeric_sort_and_exclude_prerelease_from_latest(self):
        output = self.run_install('--list')
        self.assertIn('latest: v2.10.0', output)
        self.assertIn('v3.0.0-rc.1', output)
        self.assertNotIn('not-a-version', output)
        self.assertFalse(self.install_dir.exists())
        self.assertEqual(self.calls(), [])

    def test_latest_clone_only_runs_no_downloaded_code(self):
        output = self.run_install('--version', 'latest', '--download-only')
        self.assertIn('Verified tag + commit: v2.10.0', output)
        self.assertTrue((self.install_dir / 'versions/v2.10.0/start.sh').exists())
        self.assertEqual(self.calls(), [])

    def test_major_v1_resolves_annotated_tag(self):
        output = self.run_install('--version', 'v1', '--download-only')
        self.assertIn('Verified tag + commit: v1.4.0', output)

    def test_major_v2_uses_numeric_order(self):
        output = self.run_install('--version', 'v2', '--download-only')
        self.assertIn('Verified tag + commit: v2.10.0', output)

    def test_exact_old_version_is_not_upgraded(self):
        self.run_install('--version', 'v2.0.0', '--download-only')
        self.assertTrue((self.install_dir / 'versions/v2.0.0').is_dir())
        self.assertFalse((self.install_dir / 'versions/v2.10.0').exists())

    def test_unprefixed_request_finds_prefixed_tag(self):
        self.run_install('--version', '2.2.0', '--download-only')
        self.assertTrue((self.install_dir / 'versions/v2.2.0').exists())

    def test_unprefixed_tag_sorts_with_prefixed_tags(self):
        self.publish_file('extra.txt', 'extra\n', tag='2.11.0')
        output = self.run_install('--list')
        self.assertIn('latest: 2.11.0', output)

    def test_prerelease_can_be_selected_explicitly(self):
        self.run_install('--version', 'v3.0.0-rc.1', '--download-only')
        self.assertTrue((self.install_dir / 'versions/v3.0.0-rc.1').exists())

    def test_unpublished_major_fails_without_cloning(self):
        output = self.run_install('--version', 'v9', '--download-only', expected=1)
        self.assertIn('not published', output)
        self.assertFalse(self.install_dir.exists())

    def test_unsafe_version_is_not_executed(self):
        marker = self.home / 'injected'
        self.run_install('--version', f'$(touch {marker})', '--download-only', expected=1)
        self.assertFalse(marker.exists())

    def test_verify_runs_checks_but_not_setup_or_start(self):
        self.run_install('--version', 'v2', '--verify-only')
        self.assertEqual(self.calls(), ['check', 'doctor'])

    def test_verify_failure_remains_nonzero(self):
        self.run_install('--version', 'v2', '--verify-only', expected=1,
                         env={'GWD_TEST_PACKAGE_STATUS': '1', 'GWD_TEST_BEFORE': '2'})
        self.assertEqual(self.calls(), ['check', 'doctor'])

    def test_missing_dependencies_do_not_block_setup(self):
        self.run_install('--version', 'v2', '--action', 'all', '--yes',
                         env={'GWD_TEST_PACKAGE_STATUS': '1', 'GWD_TEST_BEFORE': '2'})
        self.assertEqual(self.calls(), ['check', 'doctor', 'setup:--yes', 'doctor', 'start:--no-install --yes'])

    def test_failed_setup_does_not_start(self):
        self.run_install('--version', 'v2', '--action', 'all', '--yes', expected=1,
                         env={'GWD_TEST_SETUP_STATUS': '3'})
        self.assertEqual(self.calls(), ['check', 'doctor', 'setup:--yes'])

    def test_failed_post_setup_doctor_does_not_start(self):
        self.run_install('--version', 'v2', '--action', 'all', '--yes', expected=1,
                         env={'GWD_TEST_AFTER': '1'})
        self.assertEqual(self.calls(), ['check', 'doctor', 'setup:--yes', 'doctor'])

    def test_no_start_action(self):
        self.run_install('--version', 'v2', '--no-start', '--yes')
        self.assertEqual(self.calls(), ['check', 'doctor', 'setup:--yes', 'doctor'])

    def test_start_action_never_calls_setup(self):
        self.run_install('--version', 'v2', '--action', 'start')
        self.assertEqual(self.calls(), ['doctor', 'start:--no-install'])

    def test_server_exit_code_is_preserved(self):
        self.run_install('--version', 'v2', '--action', 'start', expected=7,
                         env={'GWD_TEST_START_STATUS': '7'})

    def test_explicit_yes_defaults_to_latest_and_all(self):
        self.run_install('--yes')
        self.assertTrue((self.install_dir / 'versions/v2.10.0').is_dir())
        self.assertEqual(self.calls()[-1], 'start:--no-install --yes')

    def test_noninteractive_setup_requires_explicit_consent(self):
        output = self.run_install('--version', 'v2', '--action', 'setup', expected=1)
        self.assertIn('requires explicit --yes', output)
        self.assertFalse(self.install_dir.exists())

    def test_existing_clean_checkout_reused_and_config_preserved(self):
        self.run_install('--version', 'v2', '--download-only')
        target = self.install_dir / 'versions/v2.10.0'
        config = target / 'config.toml'
        config.write_text('[display]\nfps=24\n')
        self.owned(config)
        output = self.run_install('--version', 'v2', '--download-only')
        self.assertIn('Checking existing installation', output)
        self.assertEqual(config.read_text(), '[display]\nfps=24\n')

    def test_dirty_checkout_not_overwritten(self):
        self.run_install('--version', 'v2', '--download-only')
        path = self.install_dir / 'versions/v2.10.0/start.sh'
        path.write_text('echo local-edits\n')
        output = self.run_install('--version', 'v2', '--download-only', expected=1)
        self.assertIn('local changes', output)
        self.assertEqual(path.read_text(), 'echo local-edits\n')

    def test_untracked_code_not_executed(self):
        self.run_install('--version', 'v2', '--download-only')
        path = self.install_dir / 'versions/v2.10.0/untracked.py'
        path.write_text('print("untracked")\n')
        self.run_install('--version', 'v2', '--action', 'start', expected=1)
        self.assertEqual(self.calls(), [])

    def test_symlink_destination_rejected(self):
        self.install_dir.joinpath('versions').mkdir(parents=True)
        target = self.install_dir / 'versions/v2.10.0'
        target.symlink_to(self.seed, target_is_directory=True)
        self.owned(self.install_dir)
        self.run_install('--version', 'v2', '--download-only', expected=1)
        self.assertTrue(target.is_symlink())

    def test_existing_non_git_directory_is_preserved(self):
        target = self.install_dir / 'versions/v2.10.0'
        target.mkdir(parents=True)
        (target / 'keep.txt').write_text('keep')
        self.owned(self.install_dir)
        self.run_install('--version', 'v2', '--download-only', expected=1)
        self.assertEqual((target / 'keep.txt').read_text(), 'keep')

    def test_version_installations_are_separate(self):
        self.run_install('--version', 'v1', '--download-only')
        self.run_install('--version', 'v2', '--download-only')
        self.assertTrue((self.install_dir / 'versions/v1.4.0').is_dir())
        self.assertTrue((self.install_dir / 'versions/v2.10.0').is_dir())

    def test_new_layout_source_verifier_is_mandatory(self):
        self.publish_file('scripts/verify.sh', '#!/usr/bin/env bash\necho source-check >> "$GWD_TEST_LOG"\nexit 8\n')
        output = self.run_install('--version', 'v4', '--action', 'all', '--yes', expected=1)
        self.assertIn('Source verification failed', output)
        self.assertEqual(self.calls(), ['source-check'])

    def test_clone_only_does_not_execute_new_verifier(self):
        self.publish_file('scripts/verify.sh', '#!/usr/bin/env bash\necho SHOULD-NOT-RUN >> "$GWD_TEST_LOG"\nexit 8\n')
        self.run_install('--version', 'v4', '--download-only')
        self.assertEqual(self.calls(), [])

    def test_tag_retargeting_does_not_silently_replace_existing_version(self):
        self.run_install('--version', 'v2', '--download-only')
        self.publish_file('new.txt', 'new', tag='v4.0.0')
        new_commit = self.git('-C', str(self.seed), 'rev-parse', 'HEAD')
        self.git('--git-dir', str(self.remote), 'update-ref', 'refs/tags/v2.10.0', new_commit)
        self.run_install('--version', 'v2', '--download-only', expected=1)
        self.assertFalse((self.install_dir / 'versions/v2.10.0/new.txt').exists())

    def test_tag_branch_name_collision_selects_the_tag(self):
        self.publish_file('branch-only.txt', 'branch', tag='v4.0.0')
        branch_commit = self.git('-C', str(self.seed), 'rev-parse', 'HEAD')
        self.git('--git-dir', str(self.remote), 'update-ref', 'refs/heads/v2.0.0', branch_commit)
        self.run_install('--version', 'v2.0.0', '--download-only')
        self.assertFalse((self.install_dir / 'versions/v2.0.0/branch-only.txt').exists())

    def test_empty_tag_list_gives_actionable_error(self):
        for ref in self.git('--git-dir', str(self.remote), 'for-each-ref', '--format=%(refname)', 'refs/tags').splitlines():
            self.git('--git-dir', str(self.remote), 'update-ref', '-d', ref)
        output = self.run_install('--list', expected=1)
        self.assertIn('No version tags are published', output)

    def test_only_prereleases_have_no_implicit_latest(self):
        for ref in self.git('--git-dir', str(self.remote), 'for-each-ref', '--format=%(refname)', 'refs/tags').splitlines():
            if not ref.endswith('-rc.1'):
                self.git('--git-dir', str(self.remote), 'update-ref', '-d', ref)
        output = self.run_install('--version', 'latest', '--download-only', expected=1)
        self.assertIn('not published', output)

    def test_unknown_arguments_fail(self):
        self.run_install('--does-not-exist', expected=1)

    def test_help_does_not_need_network(self):
        self.run_install('--help')
        self.assertFalse(self.install_dir.exists())

    def test_root_install_is_rejected(self):
        if os.geteuid() != 0:
            self.skipTest('Only applicable in a root test container')
        result = self.process(['bash', str(self.installer), '--version', 'latest', '--download-only'],
                              initial=True, stdin=subprocess.DEVNULL, start_new_session=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Do not run this installer', result.stderr)

    def git_wrapper(self, body):
        folder = self.home / 'bin'
        folder.mkdir()
        path = folder / 'git'
        real_git = shutil.which('git')
        path.write_text('#!/usr/bin/env bash\nset -eu\n' + body + '\nexec ' + shlex.quote(real_git) + ' "$@"\n')
        path.chmod(0o755)
        self.owned(folder)
        self.env.update(PATH=str(folder) + os.pathsep + os.environ['PATH'])
        return real_git

    def test_tag_changed_between_discovery_and_clone_is_rejected(self):
        self.publish_file('new-code.txt', 'new', tag='v4.0.0')
        new_commit = self.git('-C', str(self.seed), 'rev-parse', 'HEAD')
        real_git = shlex.quote(shutil.which('git'))
        self.git_wrapper('case " $* " in *" clone "*) ' + real_git +
                         ' --git-dir ' + shlex.quote(str(self.remote)) +
                         ' update-ref refs/tags/v2.10.0 ' + new_commit + ' ;; esac')
        output = self.run_install('--version', 'v2', '--action', 'all', '--yes', expected=1)
        self.assertIn('Remote tag changed during installation', output)
        self.assertFalse((self.install_dir / 'versions/v2.10.0').exists())
        self.assertEqual(list(self.install_dir.glob('.gwd-install.*')), [])
        self.assertEqual(self.calls(), [])

    def test_failed_clone_cleans_only_staging(self):
        self.git_wrapper('case " $* " in *" clone "*) exit 31 ;; esac')
        output = self.run_install('--version', 'v2', '--download-only', expected=1)
        self.assertIn('Clone failed', output)
        self.assertFalse((self.install_dir / 'versions/v2.10.0').exists())
        self.assertEqual(list(self.install_dir.glob('.gwd-install.*')), [])

    def test_config_path_with_spaces_and_demo_are_forwarded(self):
        config = self.home / 'private configuration.toml'
        config.write_text('[display]\nfps=30\n')
        self.owned(config)
        self.run_install('--version', 'v2', '--action', 'start', '--config', str(config), '--demo')
        self.assertEqual(self.calls(), ['doctor', f'start:--no-install --config {config} --demo'])

    def test_broken_downloaded_shell_syntax_blocks_execution(self):
        self.publish_file('setup.sh', '#!/usr/bin/env bash\nif true; then\n')
        self.run_install('--version', 'v4', '--action', 'all', '--yes', expected=1)
        self.assertEqual(self.calls(), [])

    def test_pipe_menu_and_child_prompts_use_controlling_terminal(self):
        import pty
        master, slave = pty.openpty()
        self.env['GWD_TEST_TTY'] = '1'
        command = f'cat {shlex.quote(str(self.installer))} | bash -s -- --install-dir {shlex.quote(str(self.install_dir))}'
        helper = "import fcntl,os,sys,termios; fcntl.ioctl(0,termios.TIOCSCTTY,0); os.execvpe('bash',['bash','-c',sys.argv[1]],os.environ)"
        options = dict(stdin=slave, stdout=slave, stderr=slave, env=self.env,
                       cwd=self.base, start_new_session=True)
        if os.geteuid() == 0:
            options.update(user=self.uid, group=self.gid, extra_groups=[])
        process = subprocess.Popen([sys.executable, '-I', '-S', '-c', helper, command], **options)
        os.close(slave)
        transcript = b''
        steps = [(b'Select version [latest]:', b'v1\n'),
                 (b'Select action [1]:', b'1\n'),
                 (b'Continue with this trusted source?', b'y\n'),
                 (b'Fixture setup confirmation:', b'go\n')]
        deadline = time.monotonic() + 20
        status = None
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        chunk = b''
                    if chunk:
                        transcript += chunk
                if steps and steps[0][0] in transcript:
                    _, answer = steps.pop(0)
                    os.write(master, answer)
                if process.poll() is not None:
                    status = process.returncode
                    break
        finally:
            os.close(master)
            if status is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        self.assertEqual(status, 0, transcript.decode(errors='replace'))
        self.assertEqual(steps, [], transcript.decode(errors='replace'))
        self.assertEqual(self.calls(), ['check', 'doctor', 'setup:', 'doctor', 'start:--no-install'])


if __name__ == '__main__':
    unittest.main()
