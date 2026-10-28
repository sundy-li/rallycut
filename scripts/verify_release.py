#!/usr/bin/env python3
"""Verify a complete RallyCut prerelease before publish or historical cleanup."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root, version):
    if not re.fullmatch(r'\d+\.\d+\.\d+-[A-Za-z0-9.-]+', version):
        raise ValueError('Invalid prerelease version')
    mac = {f'RallyCut-{version}-macos-universal.zip'}
    win = {f'RallyCut-{version}-windows-amd64.exe',
           f'RallyCut-{version}-windows-amd64-setup.exe',
           'RallyCut-runtime-windows-amd64.zip', 'runtime-bundle.json'}
    expected = mac | win | {'SHA256SUMS-macos.txt', 'SHA256SUMS-windows.txt'}
    actual = {p.name for p in root.iterdir()}
    if actual != expected:
        raise ValueError(f'Unexpected deliverables: missing={expected-actual}, extra={actual-expected}')
    for platform, names in [('macos', mac), ('windows', win)]:
        seen = set()
        for row in (root / f'SHA256SUMS-{platform}.txt').read_text(encoding='utf-8-sig').splitlines():
            digest, name = row.split(maxsplit=1)
            if name not in names or name in seen or not re.fullmatch('[a-f0-9]{64}', digest):
                raise ValueError(f'Invalid checksum entry: {name}')
            if sha256(root / name) != digest:
                raise ValueError(f'Checksum mismatch: {name}')
            seen.add(name)
            print(f'Verified {name}: {(root/name).stat().st_size} bytes')
        if seen != names:
            raise ValueError(f'Incomplete {platform} checksum coverage')
    spec = json.loads((root / 'runtime-bundle.json').read_text())['platforms']['windows/amd64']
    if spec['id'] != f'windows-x64-{version}' or spec['filename'] != 'RallyCut-runtime-windows-amd64.zip':
        raise ValueError('Runtime version or filename does not match release')
    runtime = root / spec['filename']
    if sha256(runtime) != spec['sha256'] or runtime.stat().st_size != spec['bytes']:
        raise ValueError('Runtime catalog does not match payload')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    verify(args.directory, args.version)
