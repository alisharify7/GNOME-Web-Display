import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from input_protocol import InputState
from security import LoginLimiter, Sessions, constant_equal
from settings import ConfigError, Settings, load_settings, read_password
import host


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(load_settings(environ={}).width, 1920)

    def test_environment_override(self):
        self.assertEqual(load_settings(environ={'VSCREEN_FPS':'30'}).fps, 30)

    def test_invalid_number(self):
        with self.assertRaises(ConfigError): load_settings(environ={'VSCREEN_FPS':'abc'})

    def test_invalid_ranges(self):
        for field, value in [('fps',0),('fps',121),('width',1),('http_port',80),('session_hours',0)]:
            with self.subTest(field=field, value=value), self.assertRaises(ConfigError):
                Settings(**{field:value}).validate()

    def test_even_dimensions(self):
        with self.assertRaises(ConfigError): Settings(width=1919).validate()

    def test_booleans_not_numbers(self):
        with self.assertRaises(ConfigError): Settings(fps=True).validate()

    def test_stream_validation(self):
        for name in ['../bad','bad/name','<script>','', 'x'*65]:
            with self.subTest(name=name), self.assertRaises(ConfigError):
                Settings(stream_name=name).validate()

    def test_reserved_port(self):
        with self.assertRaises(ConfigError): Settings(http_port=8889).validate()

    def test_origin_validation(self):
        for origin in ['https://x/a','https://x/','file:///tmp','https://x:bad','https://a@x']:
            with self.subTest(origin=origin), self.assertRaises(ConfigError):
                Settings(public_origin=origin).validate()

    def test_origin_accepted(self):
        self.assertEqual(Settings(public_origin='https://display.example.com').validate().public_origin, 'https://display.example.com')

    def test_missing_config(self):
        with self.assertRaises(ConfigError): load_settings('/does/not/exist.toml', {})

    def test_toml_overrides_and_relative_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'config.toml'
            path.write_text('[display]\nfps=24\n[auth]\npassword_file="secret"\n')
            cfg = load_settings(path, {'VSCREEN_FPS':'30'})
            self.assertEqual(cfg.fps, 30)
            self.assertEqual(cfg.password_file, str(Path(d)/'secret'))

    def test_unknown_and_malformed_toml(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'x.toml'
            for text in ['[display]\nfpss=40', '[unknown]\nx=1', '[display', '[display]\nfps="60"']:
                p.write_text(text)
                with self.subTest(text=text), self.assertRaises(ConfigError): load_settings(p,{})

    def test_private_password_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'secret'; p.write_text('password-test\n'); p.chmod(0o600)
            cfg=Settings(password_file=str(p))
            self.assertEqual(read_password(cfg,{}), 'password-test')
            p.chmod(0o644)
            with self.assertRaises(ConfigError): read_password(cfg,{})

    def test_password_precedence(self):
        self.assertEqual(read_password(Settings(password_file='/missing'), {'VSCREEN_PASSWORD':'environment-password'}), 'environment-password')

    def test_empty_password_rejected(self):
        with self.assertRaises(ConfigError): read_password(Settings(), {'VSCREEN_PASSWORD':''})

    def test_tls_pair(self):
        with self.assertRaises(ConfigError): Settings(tls_cert='/missing').validate()


class SecurityTests(unittest.TestCase):
    def test_unicode_passwords(self):
        self.assertTrue(constant_equal('\u0631\u0645\u0632-123456', '\u0631\u0645\u0632-123456'))
        self.assertFalse(constant_equal('hello', '\u0631\u0645\u0632'))

    def test_session_expiry(self):
        now=[0]; s=Sessions(ttl=10,clock=lambda:now[0]); token=s.create()
        self.assertTrue(s.valid(token)); now[0]=10; self.assertFalse(s.valid(token))

    def test_distinct_sessions_and_revocation(self):
        s=Sessions(); a=s.create(); b=s.create(); self.assertNotEqual(a,b)
        s.revoke(a); self.assertFalse(s.valid(a)); self.assertTrue(s.valid(b))

    def test_bounded_sessions(self):
        s=Sessions(maximum=2); first=s.create(); s.create(); s.create()
        self.assertFalse(s.valid(first)); self.assertEqual(len(s.tokens),2)

    def test_limiter(self):
        now=[0]; l=LoginLimiter(maximum=2,window=10,clock=lambda:now[0])
        self.assertTrue(l.allow('a')); self.assertTrue(l.allow('a')); self.assertFalse(l.allow('a'))
        now[0]=11; self.assertTrue(l.allow('a'))

    def test_limiter_bounded(self):
        l=LoginLimiter(peers=2)
        for peer in 'abc': l.allow(peer)
        self.assertEqual(len(l.buckets),2)


class FakeHost:
    STREAM_PATH='/fake'
    key_to_keysym=staticmethod(host.key_to_keysym)
    def __init__(self): self.events=[]
    def notify(self,*args): self.events.append(args)
    def send_keysym(self,*args): self.events.append(('key',*args))


class InputTests(unittest.TestCase):
    def setUp(self):
        self.host=FakeHost(); self.state=InputState(self.host,1920,1080)

    def test_clamped_coordinates(self):
        self.state.handle({'type':'move','x':-5,'y':5000})
        self.assertEqual(self.host.events[-1][2],('/fake',0.0,1079))

    def test_nan_and_infinity(self):
        for value in [float('nan'),float('inf'),'12',True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.state.handle({'type':'move','x':value,'y':1})

    def test_release_keys_and_buttons(self):
        self.state.handle({'type':'key','key':'Control','down':True})
        self.state.handle({'type':'button','button':0,'down':True})
        self.state.release()
        self.assertFalse(self.state.keys); self.assertFalse(self.state.buttons)
        self.assertIn(('key',0xffe3,False), self.host.events)

    def test_invalid_down(self):
        with self.assertRaises(ValueError): self.state.handle({'type':'key','key':'a','down':'false'})

    def test_text_limit(self):
        with self.assertRaises(ValueError): self.state.handle({'type':'text','text':'a'*257})

    def test_unicode_text(self):
        self.state.handle({'type':'text','text':'\u0633\n'})
        self.assertEqual(len(self.host.events),4)
        self.assertIn(('key',0xff0d,True),self.host.events)

    def test_non_object(self):
        with self.assertRaises(ValueError): self.state.handle([])

    def test_unknown_type(self):
        with self.assertRaises(ValueError): self.state.handle({'type':'shell'})


class HostTests(unittest.TestCase):
    def test_audio_list_tabs(self):
        def output(*args):
            if args==('list','short','sources'): return '2\tspeaker.monitor\tdriver\tformat\n3\tmic\tdriver\tformat'
            return 'speaker' if args==('get-default-sink',) else 'mic'
        with patch.object(host,'pactl_text',side_effect=output):
            sources=host.list_audio_sources()
        self.assertEqual(sources[0]['id'],'speaker.monitor')
        self.assertTrue(sources[0]['default'])

    def test_off_never_enumerates(self):
        with patch.object(host,'REQUESTED_AUDIO','off'), patch.object(host,'list_audio_sources') as f:
            self.assertIsNone(host.detect_audio_source()); f.assert_not_called()

    def test_explicit_missing_source(self):
        with patch.object(host,'REQUESTED_AUDIO','missing'), patch.object(host,'list_audio_sources',return_value=[]):
            with self.assertRaises(RuntimeError): host.detect_audio_source()

    def test_auto_no_audio_fallback(self):
        with patch.object(host,'REQUESTED_AUDIO','auto'), patch.object(host,'list_audio_sources',return_value=[]):
            self.assertIsNone(host.detect_audio_source())

    def test_pipeline_video_only(self):
        p=host.build_gstreamer_pipeline(None)
        self.assertIn('x264enc',p); self.assertNotIn('pulsesrc',p)

    def test_pipeline_audio(self):
        p=host.build_gstreamer_pipeline('speaker.monitor')
        self.assertIn('opusenc',p); self.assertIn('device=speaker.monitor',p)


if __name__=='__main__': unittest.main()
