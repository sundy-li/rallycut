import os
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backends
from pretrained import BlurBallDetector, normalize_input


def _package():
    if sys.platform != 'darwin':
        return None
    try:
        import coremltools  # noqa: F401
    except ImportError:
        return None
    return backends.locate_artifact('coreml')


PACKAGE = _package()


class NormalizeTests(unittest.TestCase):
    def test_shared_normalization_matches_detector_path(self):
        rng = np.random.default_rng(0)
        windows = [[(rng.integers(0, 256, (3, 288, 512), dtype=np.uint8), None) for _ in range(3)] for _ in range(2)]
        detector = BlurBallDetector.__new__(BlurBallDetector)
        detector._np_mean = np.array([.485, .456, .406] * 3, dtype='float32').reshape(1, 9, 1, 1)
        detector._np_std = np.array([.229, .224, .225] * 3, dtype='float32').reshape(1, 9, 1, 1)
        expected = detector.prepare_input(windows)
        batch = np.concatenate([np.concatenate([f for f, _ in w])[None] for w in windows]).astype(np.float32)
        got = normalize_input(batch)
        self.assertEqual(got.dtype, np.float32)
        self.assertTrue(np.array_equal(got, expected))


@unittest.skipUnless(PACKAGE, 'needs macOS, coremltools and a verified Core ML package')
class ProcessCoreMLTests(unittest.TestCase):
    def test_child_process_heatmaps_equal_in_process(self):
        from coreml_process import ProcessCoreMLBackend
        rng = np.random.default_rng(1)
        windows = [[(rng.integers(0, 256, (3, 288, 512), dtype=np.uint8), None) for _ in range(3)] for _ in range(4)]
        detector = BlurBallDetector.__new__(BlurBallDetector)
        detector._np_mean = np.array([.485, .456, .406] * 3, dtype='float32').reshape(1, 9, 1, 1)
        detector._np_std = np.array([.229, .224, .225] * 3, dtype='float32').reshape(1, 9, 1, 1)
        in_process = backends.CoreMLBackend(PACKAGE)
        child = ProcessCoreMLBackend(PACKAGE)
        try:
            # Same inputs on both sides: ANE results depend on the whole batch
            # (3 windows are padded to 4), so never compare across counts.
            for count in (4, 1, 3):
                reference = in_process.predict(detector.prepare_input(windows[:count]))
                got = child.predict_windows(windows[:count])
                self.assertTrue(np.array_equal(got, reference), count)
            with self.assertRaises(ValueError):
                child.predict_windows([[(np.zeros((3, 288, 512), np.float32), None)] * 3])
            process = child.process
        finally:
            child.close()
        self.assertIsNotNone(process.poll(), 'child must exit on close')

    def test_dead_child_raises_instead_of_hanging(self):
        from coreml_process import ProcessCoreMLBackend
        child = ProcessCoreMLBackend(PACKAGE)
        try:
            child.process.kill()
            child.process.wait()
            window = [(np.zeros((3, 288, 512), np.uint8), None)] * 3
            with self.assertRaises(RuntimeError):
                child.predict_windows([window])
        finally:
            child.close()


if __name__ == '__main__':
    unittest.main()
