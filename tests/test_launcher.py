import _bootstrap  # noqa: F401
import unittest
from unittest.mock import patch

from gnome_web_display import launcher
from gnome_web_display.doctor import docker_version_issue
from gnome_web_display.settings import Settings


class LauncherTests(unittest.TestCase):
    def test_old_engine_rejected(self):
        for version in ('20.10.24', '26.1.5+dfsg1', '27.5.1'):
            with self.subTest(version=version):
                self.assertIn('too old', docker_version_issue(version))

    def test_modern_engine_accepted(self):
        for version in ('28.0.0', '28.3.3', '29.0.1', ' 28.1.0\n'):
            with self.subTest(version=version):
                self.assertIsNone(docker_version_issue(version))

    def test_unknown_engine_rejected(self):
        for value in ('', 'unknown', 'Docker version 27.0', 'permission denied'):
            with self.subTest(value=value):
                self.assertIsNotNone(docker_version_issue(value))

    def test_privileged_engine_is_checked(self):
        with patch('gnome_web_display.launcher.command', return_value=(0, '27.1.0')) as call:
            with self.assertRaisesRegex(launcher.LaunchError, '28'):
                launcher.require_safe_docker(['sudo', 'docker'])
            self.assertEqual(call.call_args.args[0][:3], ['sudo', 'docker', 'info'])

    def test_engine_query_failure_is_error(self):
        with patch('gnome_web_display.launcher.command', return_value=(1, 'permission denied')):
            with self.assertRaises(launcher.LaunchError):
                launcher.require_safe_docker(['docker'])

    def test_modern_engine_passes(self):
        with patch('gnome_web_display.launcher.command', return_value=(0, '28.3.0')):
            launcher.require_safe_docker(['docker'])

    def test_noninteractive_consent_defaults_no(self):
        with patch('gnome_web_display.launcher.sys.stdin.isatty', return_value=False), patch('builtins.input') as ask:
            self.assertFalse(launcher.consent('Install?'))
            ask.assert_not_called()

    def test_explicit_yes_allows_consent(self):
        with patch('gnome_web_display.launcher.sys.stdin.isatty', return_value=False):
            self.assertTrue(launcher.consent('Install?', yes=True))

    def test_explicit_address_skips_discovery(self):
        with patch('gnome_web_display.launcher.networks') as networks:
            self.assertEqual(launcher.choose_ip(Settings(advertised_ip='192.0.2.10')), '192.0.2.10')
            networks.assert_not_called()

    def test_ambiguous_noninteractive_network_fails(self):
        with patch('gnome_web_display.launcher.networks', return_value=[('eth0','192.0.2.1'),('tun0','192.0.2.2')]), patch('gnome_web_display.launcher.sys.stdin.isatty', return_value=False):
            with self.assertRaisesRegex(launcher.LaunchError, 'Several network'):
                launcher.choose_ip(Settings())

    def test_no_usable_network_fails(self):
        with patch('gnome_web_display.launcher.networks', return_value=[]):
            with self.assertRaisesRegex(launcher.LaunchError, 'No usable IPv4'):
                launcher.choose_ip(Settings())

    def test_interface_filter(self):
        with patch('gnome_web_display.launcher.networks', return_value=[('eth0','192.0.2.1'),('wlan0','192.0.2.2')]):
            self.assertEqual(launcher.choose_ip(Settings(interface='wlan0')), '192.0.2.2')

    def test_no_shell_command_execution(self):
        with patch('gnome_web_display.launcher.subprocess.run') as run:
            launcher.run_checked(['printf', '; echo unsafe'])
            self.assertEqual(run.call_args.args[0], ['printf', '; echo unsafe'])
            self.assertNotIn('shell', run.call_args.kwargs)
