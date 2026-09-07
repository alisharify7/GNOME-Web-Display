"""Source-checkout paths and a single source of truth for the release version."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / 'web'
CONFIG_ROOT = ROOT / 'config'
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
