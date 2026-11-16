#!/usr/bin/env python3
"""Explicit, checksum-verified local evaluation download; no runtime network I/O."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pretrained import WEIGHTS_URL, WEIGHTS_SHA256

WEIGHTS_BYTES = 6156034
# Keep in sync with models/manifest.json weights_mirrors (checked by tests).
# Every mirror must serve the byte-identical pinned file; WEIGHTS_SHA256
# decides, never the source. Kept here instead of pretrained.py, whose source
# feeds the detection-cache digest. Tried in order before the official URL.
_GITHUB = 'https://github.com/sundy-li/rallycut/releases/download/model-blurball-v1/blurball_best'
WEIGHTS_MIRRORS = (
    # Maintainer-approved byte-identical copy in a GitHub Release (not an app
    # release), via mainland-China download accelerators and directly.
    'https://edgeone.gh-proxy.com/' + _GITHUB,
    'https://ghfast.top/' + _GITHUB,
    _GITHUB,
    'https://hk.gh-proxy.com/' + _GITHUB,
    'https://gh-proxy.org/' + _GITHUB,
    'https://ghfile.geekertao.top/' + _GITHUB,
    # Official Nextcloud share-download endpoint (same host as WEIGHTS_URL).
    'https://cloud.cs.uni-tuebingen.de/index.php/s/6Z8TpM3sXRKHzGC/download?path=%2F&files=blurball_best',
)
MIRRORS_ENV = 'RALLYCUT_MODEL_MIRRORS'
ROUNDS = 4


def sources():
    """User mirrors first, then manifest mirrors, then the official URL."""
    ordered = []
    for raw in [*re.split(r'[\s,;]+', os.environ.get(MIRRORS_ENV, '')), *WEIGHTS_MIRRORS, WEIGHTS_URL]:
        if not raw or raw in ordered:
            continue
        parsed = urllib.parse.urlsplit(raw)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise ValueError(f'{MIRRORS_ENV} 含无效下载地址: {raw!r}')
        ordered.append(raw)
    return ordered


def fetch(url, target):
    """Download one source into target; returns its SHA-256 hex digest."""
    target.seek(0)
    target.truncate()
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(url, headers={'User-Agent': 'RallyCut/1.0', 'Accept-Encoding': 'identity'})
    with urllib.request.urlopen(request, timeout=30) as source:
        while chunk := source.read(1 << 20):
            size += len(chunk)
            if size > WEIGHTS_BYTES:
                raise ValueError('download exceeds pinned size')
            digest.update(chunk)
            target.write(chunk)
    if size != WEIGHTS_BYTES:
        raise ValueError(f'incomplete download: {size} / {WEIGHTS_BYTES} bytes')
    target.flush()
    return digest.hexdigest()


def download_any(urls, target, rounds=ROUNDS, sleep=time.sleep):
    """Try every source per round with backoff. None on success, else errors by host."""
    dead = set()
    errors = {}
    for round_ in range(rounds):
        if round_:
            sleep(min(8, 2 ** (round_ - 1)))
        for url in urls:
            if url in dead:
                continue
            host = urllib.parse.urlsplit(url).netloc
            try:
                if fetch(url, target) == WEIGHTS_SHA256:
                    return None
                errors[host] = 'SHA-256 mismatch'
                dead.add(url)
            except urllib.error.HTTPError as e:
                errors[host] = f'HTTP {e.code}'
                if e.code not in (408, 429) and e.code < 500:
                    dead.add(url)
            except ValueError as e:  # wrong size: this source serves another file
                errors[host] = str(e)
                dead.add(url)
            except OSError as e:
                errors[host] = str(e)
        if len(dead) == len(urls):
            break
        if round_ + 1 < rounds:
            print(f'retrying model download ({round_ + 1}/{rounds}): {errors}', file=sys.stderr)
    return errors


def main():
    parser = argparse.ArgumentParser(description='Download official BlurBall weights for local evaluation. Separate weight redistribution terms are unconfirmed.')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1]/'models/weights/blurball_best.pth')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        if hashlib.sha256(output.read_bytes()).hexdigest() != WEIGHTS_SHA256:
            raise ValueError(f'existing file checksum mismatch; refusing to replace: {output}')
        print(f'Already verified: {output}')
        return
    output.parent.mkdir(parents=True,exist_ok=True)
    urls = sources()
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as target:
            name = Path(target.name)
            errors = download_any(urls, target)
        if errors is not None:
            detail = '; '.join(f'{host}: {reason}' for host, reason in errors.items())
            raise SystemExit(f'model download failed from every source ({detail}). '
                             f'Set {MIRRORS_ENV} to another source of the same pinned file, '
                             'or place a verified copy and set RALLYCUT_MODEL_PATH.')
        # Hard link provides no-clobber publication on the same local volume.
        os.link(name,output)
        print(f'Installed {output} ({WEIGHTS_BYTES} bytes); SHA-256 {WEIGHTS_SHA256}')
        print('Local evaluation only: do not assume MIT code license grants separate weight redistribution rights.')
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
