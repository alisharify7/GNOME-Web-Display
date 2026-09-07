"""Validated, non-executable configuration. No optional runtime imports here."""
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import os
import re
import stat
import tomllib

from .paths import ROOT, VERSION


class ConfigError(ValueError):
    """A user-actionable configuration error."""


@dataclass
class Settings:
    width: int = 1920
    height: int = 1080
    fps: int = 60
    bitrate: int = 6000
    audio_source: str = 'auto'
    audio_bitrate: int = 128000
    http_host: str = '0.0.0.0'
    http_port: int = 8090
    stream_name: str = 'monitor'
    public_origin: str = ''
    tls_cert: str = ''
    tls_key: str = ''
    advertised_ip: str = ''
    interface: str = ''
    mediamtx_image: str = 'bluenviron/mediamtx:1.21.0'
    user: str = 'display'
    password_file: str = ''
    session_hours: int = 12

    def validate(self):
        ranges = {'width': (256, 7680), 'height': (144, 4320), 'fps': (1, 120),
                  'bitrate': (128, 100000), 'audio_bitrate': (6000, 510000),
                  'http_port': (1024, 65535), 'session_hours': (1, 72)}
        for field, (low, high) in ranges.items():
            value = getattr(self, field)
            if type(value) is not int or not low <= value <= high:
                raise ConfigError(f'{field} must be an integer from {low} to {high}.')
        for field in fields(self):
            if field.name not in ranges and not isinstance(getattr(self, field.name), str):
                raise ConfigError(f'{field.name} must be a string.')
        if self.width % 2 or self.height % 2:
            raise ConfigError('width and height must be even for H.264 video.')
        if self.http_port in (8554, 8889):
            raise ConfigError('http_port conflicts with a private MediaMTX port (8554/8889).')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.stream_name):
            raise ConfigError('stream_name must use 1-64 letters, digits, hyphens or underscores.')
        for name in ('http_host', 'advertised_ip'):
            value = getattr(self, name)
            if value:
                try:
                    address = ipaddress.IPv4Address(value)
                except ValueError:
                    raise ConfigError(f'{name} must be an IPv4 address, not a hostname.') from None
                if name == 'advertised_ip' and (address.is_unspecified or address.is_multicast):
                    raise ConfigError('advertised_ip must be a reachable unicast address, not 0.0.0.0.')
        if not self.http_host:
            raise ConfigError('http_host cannot be empty.')
        if not self.user.strip() or len(self.user) > 128 or any(ord(c) < 32 for c in self.user):
            raise ConfigError('user must contain 1-128 printable characters.')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/:@-]*', self.mediamtx_image):
            raise ConfigError('mediamtx_image is not a valid image reference.')
        if self.public_origin:
            p = urlsplit(self.public_origin)
            try:
                _ = p.port
            except ValueError:
                raise ConfigError('public_origin contains an invalid port.') from None
            if (p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password
                    or p.path or p.query or p.fragment):
                raise ConfigError('public_origin must be an origin only, e.g. https://display.example.com (no trailing slash).')
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ConfigError('Set both tls_cert and tls_key, or leave both empty.')
        for name in ('tls_cert', 'tls_key'):
            if getattr(self, name) and not Path(getattr(self, name)).is_file():
                raise ConfigError(f'{name} file does not exist: {getattr(self, name)}')
        return self


SCHEMA = {
    'display': {'width': 'width', 'height': 'height', 'fps': 'fps', 'bitrate_kbps': 'bitrate'},
    'audio': {'source': 'audio_source', 'bitrate_bps': 'audio_bitrate'},
    'server': {'host': 'http_host', 'port': 'http_port', 'stream_name': 'stream_name',
               'public_origin': 'public_origin', 'tls_cert': 'tls_cert', 'tls_key': 'tls_key'},
    'network': {'advertised_ip': 'advertised_ip', 'interface': 'interface'},
    'mediamtx': {'image': 'mediamtx_image'},
    'auth': {'username': 'user', 'password_file': 'password_file', 'session_hours': 'session_hours'},
}
ENV = {name: 'VSCREEN_' + name.upper() for name in Settings.__dataclass_fields__}


def load_settings(path=None, environ=None):
    env = os.environ if environ is None else environ
    specified = path or env.get('VSCREEN_CONFIG')
    config_path = Path(specified).expanduser() if specified else ROOT / 'config.toml'
    cfg = Settings()
    if specified and not config_path.is_file():
        raise ConfigError(f'Configuration file not found: {config_path}')
    if config_path.exists():
        try:
            with config_path.open('rb') as f:
                data = tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f'Cannot read {config_path}: {exc}') from None
        for section, values in data.items():
            if section not in SCHEMA or not isinstance(values, dict):
                raise ConfigError(f'Unknown configuration section: {section}')
            for key, value in values.items():
                if key not in SCHEMA[section]:
                    raise ConfigError(f'Unknown setting: {section}.{key}')
                setattr(cfg, SCHEMA[section][key], value)
    for name, variable in ENV.items():
        if variable in env:
            value = env[variable]
            if isinstance(getattr(Settings(), name), int):
                try:
                    value = int(value)
                except ValueError:
                    raise ConfigError(f'{variable} must be an integer.') from None
            setattr(cfg, name, value)
    # File paths in TOML are relative to the configuration file, not the shell cwd.
    for name in ('tls_cert', 'tls_key', 'password_file'):
        value = getattr(cfg, name)
        if isinstance(value, str) and value:
            p = Path(value).expanduser()
            setattr(cfg, name, str(p if p.is_absolute() else config_path.resolve().parent / p))
    return cfg.validate()


def read_password(cfg, environ=None):
    env = os.environ if environ is None else environ
    if 'VSCREEN_PASSWORD' in env:
        password = env['VSCREEN_PASSWORD']
    elif cfg.password_file:
        p = Path(cfg.password_file)
        try:
            info = p.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ConfigError(f'Password file must be private: chmod 600 {p}')
            if hasattr(os, 'getuid') and info.st_uid != os.getuid():
                raise ConfigError('Password file must belong to the current user.')
            password = p.read_text(encoding='utf-8').rstrip('\r\n')
        except OSError as exc:
            raise ConfigError(f'Cannot read password file: {exc}') from None
    else:
        return ''
    if not 8 <= len(password) <= 1024:
        raise ConfigError('Password must contain 8-1024 characters.')
    return password
