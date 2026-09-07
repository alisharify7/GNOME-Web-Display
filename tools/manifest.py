#!/usr/bin/env python3
"""Rebuild/check the release manifest without including local configuration/secrets.

Run after intentional source changes, before committing/tagging a release.
A checksum from the same source is change detection, not publisher authentication.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'MANIFEST.sha256'
EXCLUDED_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.idea', '.vscode', 'htmlcov'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.log', '.pid', '.key', '.pem', '.p12', '.pfx', '.zip', '.gz'}


def distributed_files():
    if (ROOT / '.git').is_dir():
        result = subprocess.run(
            ['git', '-C', str(ROOT), 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            check=True, capture_output=True,
        )
        paths = {ROOT / name.decode('utf-8') for name in result.stdout.split(b'\0') if name}
    else:
        paths = set(ROOT.rglob('*'))
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        if (path == MANIFEST or not path.is_file() or path.is_symlink()
                or any(part in EXCLUDED_DIRS for part in relative.parts)
                or path.suffix in EXCLUDED_SUFFIXES
                or path.name in {'config.toml', 'password.txt', '.coverage', '.DS_Store'}
                or path.name.startswith(('.env', 'password-'))):
            continue
        yield path


def render():
    return ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT).as_posix()}\n'
                   for path in distributed_files())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check exact manifest content without writing.')
    args = parser.parse_args()
    content = render()
    if args.check:
        if not MANIFEST.is_file() or MANIFEST.read_text() != content:
            print('Manifest is stale. After reviewing changes, run: python tools/manifest.py', file=sys.stderr)
            return 1
        print(f'Manifest is current ({len(content.splitlines())} files).')
    else:
        MANIFEST.write_text(content, encoding='utf-8')
        print(f'Wrote {MANIFEST.name}: {len(content.splitlines())} files.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
