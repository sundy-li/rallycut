import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backends
import coreml_model
from pretrained import WEIGHTS_SHA256


class CoreMLArtifactTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.derived = coreml_model.derived_dir(self.dir)
        (self.derived / coreml_model.PACKAGE).mkdir(parents=True)

    def write_sidecar(self, **overrides):
        meta = {'converter': coreml_model.CONVERTER, 'package': coreml_model.PACKAGE, 'weights_sha256': WEIGHTS_SHA256}
        meta.update(overrides)
        (self.derived / coreml_model.SIDECAR).write_text(json.dumps(meta))

    def locate(self):
        with mock.patch.dict(os.environ, {'RALLYCUT_DATA_DIR': str(self.dir)}), \
             mock.patch.object(backends, '_candidates', lambda kind: iter([self.derived / coreml_model.PACKAGE])):
            os.environ.pop('RALLYCUT_COREML_MODEL', None)
            return backends.locate_artifact('coreml')

    def test_only_verified_packages_are_used(self):
        self.assertIsNone(self.locate(), 'package without sidecar')
        self.write_sidecar(converter='older-converter')
        self.assertIsNone(self.locate(), 'stale converter')
        self.write_sidecar(weights_sha256='0' * 64)
        self.assertIsNone(self.locate(), 'other weights')
        self.write_sidecar()
        self.assertEqual(self.locate(), self.derived / coreml_model.PACKAGE)

    def test_failure_marker_matches_converter_and_weights(self):
        self.assertFalse(coreml_model.failure_recorded(self.dir))
        failed = self.derived / coreml_model.FAILED
        failed.write_text(json.dumps({'converter': 'older', 'weights_sha256': WEIGHTS_SHA256}))
        self.assertFalse(coreml_model.failure_recorded(self.dir), 'a new converter retries')
        failed.write_text(json.dumps({'converter': coreml_model.CONVERTER, 'weights_sha256': WEIGHTS_SHA256}))
        self.assertTrue(coreml_model.failure_recorded(self.dir))


if __name__ == '__main__':
    unittest.main()
