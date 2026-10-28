"""Release checksum coverage is enforced before publication and old-release cleanup."""
import json
from pathlib import Path
import runpy
import tempfile
import unittest

API = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/verify_release.py'))


class ReleaseVerifierTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.version = '0.1.0-alpha.3'
        self.mac = [f'RallyCut-{self.version}-macos-universal.zip']
        self.win = [f'RallyCut-{self.version}-windows-amd64.exe',
                    f'RallyCut-{self.version}-windows-amd64-setup.exe',
                    'RallyCut-runtime-windows-amd64.zip', 'runtime-bundle.json']
        for name in self.mac + self.win:
            (self.root / name).write_bytes(name.encode())
        runtime = self.root / self.win[2]
        spec = {'id': f'windows-x64-{self.version}', 'filename': runtime.name,
                'sha256': API['sha256'](runtime), 'bytes': runtime.stat().st_size}
        (self.root / 'runtime-bundle.json').write_text(json.dumps({'platforms': {'windows/amd64': spec}}))
        self.checksums()

    def checksums(self):
        for platform, names in [('macos', self.mac), ('windows', self.win)]:
            (self.root / f'SHA256SUMS-{platform}.txt').write_text(''.join(
                f"{API['sha256'](self.root/name)}  {name}\n" for name in names))

    def verify(self):
        API['verify'](self.root, self.version)

    def test_complete_release(self):
        self.verify()

    def test_missing_installer_rejected(self):
        (self.root / self.win[1]).unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_extra_payload_rejected(self):
        (self.root / 'private-data.txt').write_text('not a deliverable')
        with self.assertRaises(ValueError):
            self.verify()

    def test_tampering_rejected(self):
        (self.root / self.win[0]).write_text('changed')
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_or_duplicate_checksum_rejected(self):
        path = self.root / 'SHA256SUMS-windows.txt'
        rows = path.read_text().splitlines(keepends=True)
        for content in [''.join(rows[:-1]), ''.join(rows[:-1] + [rows[0]])]:
            with self.subTest(content=content):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_runtime_identity_rejected_even_with_consistent_checksums(self):
        path = self.root / 'runtime-bundle.json'
        spec = json.loads(path.read_text())
        spec['platforms']['windows/amd64']['id'] = 'windows-x64-old-version'
        path.write_text(json.dumps(spec))
        self.checksums()
        with self.assertRaises(ValueError):
            self.verify()
