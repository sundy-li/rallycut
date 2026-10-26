import sys
import unittest
from unittest import mock
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rally_state import BallValidity
from shot_boundary import ShotMonitor, is_cut, thumbnail


def flat(value, size=(180, 320, 3)):
    return np.full(size, value, dtype='uint8')


def scene(seed):
    """Large colour tiles: survives 32x18 downscaling, unlike fine noise."""
    tiles = np.random.default_rng(seed).integers(0, 256, (4, 4, 3), dtype='uint8')
    return np.repeat(np.repeat(tiles, 45, axis=0), 80, axis=1)


def textured(seed, size=(1080, 1920)):
    """Full-HD frame with 6 px detail, smoothed like real footage."""
    import cv2
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (size[0] // 6, size[1] // 6, 3), dtype='uint8')
    frame = cv2.resize(small, (size[1], size[0]), interpolation=cv2.INTER_LINEAR)
    return cv2.GaussianBlur(frame, (5, 5), 0)


class ShotBoundaryTests(unittest.TestCase):
    def test_identical_and_gradual_changes_are_not_cuts(self):
        base = scene(1)
        self.assertFalse(is_cut(thumbnail(base), thumbnail(base)))
        brighter = np.clip(base.astype('int16') + 5, 0, 255).astype('uint8')
        self.assertFalse(is_cut(thumbnail(base), thumbnail(brighter)))

    def test_hard_cut_between_scenes_is_detected(self):
        self.assertTrue(is_cut(thumbnail(scene(2)), thumbnail(scene(9))))

    def test_person_walking_past_the_camera_is_not_a_cut(self):
        hall = scene(3)
        occluded = hall.copy()
        occluded[:, :128] = 240  # a white shirt covering the left 40% of the frame
        self.assertFalse(is_cut(thumbnail(hall), thumbnail(occluded)))
        # The same change over the whole picture is still a cut.
        self.assertTrue(is_cut(thumbnail(hall), thumbnail(flat(240))))

    def test_hand_held_shake_is_not_a_cut_but_a_hard_cut_still_is(self):
        # Fine texture: the strided probe aliases a few-pixel shift into a
        # cut-sized change; translation-compensated difference stays small.
        hall = textured(4)
        shaken = np.roll(hall, (3, 5), axis=(0, 1))
        self.assertTrue(is_cut(thumbnail(hall), thumbnail(shaken)))  # old rule alone
        monitor = ShotMonitor(geometry=False)
        monitor.push(0.0, hall)
        monitor.push(1.5, shaken)
        self.assertEqual(monitor.cuts, [])
        self.assertEqual(monitor.motion_vetoes, 1)
        other = np.repeat(np.repeat(scene(9), 6, axis=0), 6, axis=1)  # a different 1080p view
        monitor.push(3.0, other)
        self.assertEqual(monitor.cuts, [3.0])

    def test_motion_estimate_never_modifies_cached_probes(self):
        from shot_boundary import aligned_difference, motion_probe
        a, b = motion_probe(textured(4)), motion_probe(np.roll(textured(4), 4, axis=1))
        a0, b0 = a.copy(), b.copy()
        first = aligned_difference(a, b)
        self.assertTrue(np.array_equal(a, a0) and np.array_equal(b, b0))
        self.assertEqual(aligned_difference(a, b), first)

    def test_camera_drift_moves_geometry_without_declaring_a_cut(self):
        from test_table_locator import item
        hall = textured(4)
        monitor = ShotMonitor()
        with mock.patch('table_locator.candidates', return_value=[item((180, 200, 820, 270))]):
            for t in (0, 1, 2, 3):
                state = monitor.push(t, hall)
            self.assertTrue(state.bounds)
            panned = np.roll(hall, 120, axis=1)  # 6.25% of the width
            monitor.push(4, panned)
            self.assertEqual(monitor.state, state)  # one check is not enough
            moved = monitor.push(5, panned)
            self.assertEqual(moved.shot_id, state.shot_id)
            for a, b, delta in zip(state.bounds, moved.bounds, (60, 0, 60, 0)):
                self.assertAlmostEqual(b - a, delta, delta=2)
            self.assertEqual((monitor.cuts, monitor.drift_follows, monitor.drift_resets), ([], 1, 0))
            # Panning the table out of the frame clears it; probing restarts.
            gone = np.roll(hall, 500, axis=1)
            for t in (6, 7, 8):
                state_out = monitor.push(t, gone)
            self.assertEqual(state_out.bounds, ())
            self.assertEqual(state_out.shot_id, state.shot_id)
            self.assertEqual((monitor.cuts, monitor.drift_resets), ([], 1))
            for t in (9, 10, 11):
                again = monitor.push(t, gone)
        self.assertTrue(again.bounds)
        self.assertEqual(again.shot_id, state.shot_id)
        # A fixed camera with someone moving in front never drifts.
        still = ShotMonitor()
        with mock.patch('table_locator.candidates', return_value=[item((180, 200, 820, 270))]):
            for t in range(12):
                frame = hall.copy()
                frame[400:1000, 100 + 60 * t:500 + 60 * t] = 230  # walker, 20% of width
                still.push(t, frame)
        self.assertEqual((still.drift_resets, still.cuts), (0, []))
        self.assertTrue(still.state.bounds)

    def test_immutable_snapshots_never_leak_future_geometry_across_threads(self):
        from test_table_locator import item
        monitor=ShotMonitor()
        with mock.patch('table_locator.candidates',return_value=[item((180,200,820,270))]):
            first=monitor.push(0,scene(2));monitor.push(1,scene(2));known=monitor.push(2,scene(2))
        self.assertEqual(first.bounds,())
        self.assertTrue(known.bounds)
        with self.assertRaises(FrozenInstanceError):first.method='changed'
        cut=monitor.push(3,scene(9))
        self.assertEqual(cut.bounds,());self.assertTrue(known.bounds)
        self.assertEqual(monitor.segments(4)[0]['bounds'],[])
        self.assertEqual(monitor.segments(4)[-1]['bounds'],[])

    def test_optional_geometry_errors_do_not_block_detection(self):
        monitor=ShotMonitor()
        with mock.patch('table_locator.candidates',side_effect=ValueError('unsupported geometry')):
            state=monitor.push(0,scene(2))
        self.assertEqual(state.bounds,());self.assertTrue(monitor.warnings)
        off=ShotMonitor(geometry=False)
        with mock.patch('table_locator.candidates',side_effect=AssertionError('off should not inspect')):
            self.assertEqual(off.push(0,scene(2)).bounds,())

    def test_monitor_ignores_a_second_change_inside_the_same_shot(self):
        monitor = ShotMonitor()
        monitor.push(0.0, scene(2))
        monitor.push(1.2, scene(9))
        self.assertEqual(len(monitor.cuts), 1)
        self.assertAlmostEqual(monitor.cuts[0], 1.2)
        monitor.push(1.4, scene(2))  # flash inside the new shot: too soon
        self.assertEqual(len(monitor.cuts), 1)


class ValidityRebindTests(unittest.TestCase):
    def test_rebind_switches_geometry_and_clears_in_flight_history(self):
        validity = BallValidity([0.1, 0.4, 0.9, 0.5], None, 'side-color-rim')
        validity.observe(1.0, [(0.5, 0.45, 0.9)])
        validity.rebind([0.0, 0.3, 0.74, 0.49], None, 'side-color-rim')
        self.assertAlmostEqual(validity.left, 0.0)
        self.assertAlmostEqual(validity.right, 0.74)
        self.assertEqual(len(validity.history), 0)
        self.assertEqual(len(validity.events), 0)


if __name__ == '__main__':
    unittest.main()

    def test_thumbnail_is_small_and_grey(self):
        frame=np.zeros((1080,1920,3),dtype='uint8')
        grey,hist=thumbnail(frame)
        self.assertEqual(grey.shape,(18,32))
        self.assertEqual(grey.dtype,np.float32)
        self.assertEqual(hist.shape[0],32)
