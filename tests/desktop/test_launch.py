"""Opt-in macOS smoke: verify release tags/signature and run outside repo cwd.

This launches a real window briefly, then stops only the process it owns.
It is not an assertion about rendered WebView contents (covered by browser tests).
Run: python3 tests/desktop/test_launch.py --app build/release/RallyCut.app
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, default=Path('build/release/RallyCut.app'))
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('macOS only')
    app = args.app.resolve()
    binary = app/'Contents/MacOS/RallyCut'
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    info = subprocess.check_output(['go', 'version', '-m', str(binary)], text=True)
    tags = re.search(r'-tags=([^\s]+)', info)
    assert tags and 'production' in tags[1].split(',') and 'dev' not in tags[1].split(','), info
    with tempfile.TemporaryDirectory(prefix='rallycut-launch-') as cwd:
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen([str(binary)], cwd=cwd, stdout=log, stderr=log)
            try:
                try:
                    code = process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    code = None
                log.seek(0)
                output = log.read().decode('utf-8', errors='replace')
                assert code is None, f'app exited early ({code}): {output}'
                assert 'unable to infer the AssetDir' not in output, output
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    print('PASS: production signature/tags; independent launch from non-project cwd stayed alive for 6s')


if __name__ == '__main__':
    main()
