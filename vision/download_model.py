#!/usr/bin/env python3
"""Explicit, checksum-verified local evaluation download; no runtime network I/O."""
import argparse
import hashlib
from pathlib import Path
import tempfile
import urllib.request
from pretrained import WEIGHTS_URL, WEIGHTS_SHA256


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
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as target:
            name = Path(target.name)
            digest = hashlib.sha256()
            size = 0
            with urllib.request.urlopen(WEIGHTS_URL, timeout=60) as source:
                while chunk := source.read(1<<20):
                    size += len(chunk)
                    if size > 10<<20:
                        raise ValueError('download exceeds expected size bound')
                    digest.update(chunk)
                    target.write(chunk)
        if digest.hexdigest() != WEIGHTS_SHA256:
            raise ValueError('download SHA-256 mismatch; not installing')
        # Hard link provides no-clobber publication on the same local volume.
        import os
        os.link(name,output)
        print(f'Installed {output} ({size} bytes); SHA-256 {digest.hexdigest()}')
        print('Local evaluation only: do not assume MIT code license grants separate weight redistribution rights.')
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
