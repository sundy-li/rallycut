import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visual import MODEL, Track, analyze, find_table, segment_rallies


def fixture(path, moving=True, with_table=True):
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), 30, (960, 540))
    if not out.isOpened():
        raise RuntimeError('fixture encoder unavailable')
    try:
        for i in range(300):
            frame = np.full((540, 960, 3), 65, np.uint8)
            if with_table:
                cv2.rectangle(frame, (120, 240), (840, 290), (150, 75, 75), -1)
            seconds = i / 30
            if moving and (1 <= seconds < 3 or 5 <= seconds < 8):
                x = 180 + (i * 12) % 600
                y = 200 + round(7 * np.sin(i*.3))
                cv2.circle(frame, (x, y), 4, (245, 245, 245), -1)
            out.write(frame)
    finally:
        out.release()


class VisualWorkerTests(unittest.TestCase):
    def test_real_frames_determine_results_and_timestamp_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            moving, empty = Path(directory)/'moving.mp4', Path(directory)/'empty.mp4'
            fixture(moving)
            fixture(empty, moving=False)
            result = analyze(moving, 10, lambda *_: None)
            again = analyze(moving, 10, lambda *_: None)
            self.assertEqual(result['rallies'], again['rallies'])
            self.assertEqual(result['tracks'], again['tracks'])
            self.assertGreaterEqual(len(result['rallies']), 2)
            self.assertGreater(len(result['tracks']), 0)
            # Same duration and table, different actual pixels: no fake segments.
            self.assertEqual(analyze(empty, 10, lambda *_: None)['rallies'], [])
            for track in result['tracks']:
                timestamps = [p['t'] for p in track['points']]
                self.assertEqual(timestamps, sorted(set(timestamps)))
                self.assertTrue(all(0 <= p['x'] <= 1 and 0 <= p['y'] <= 1 for p in track['points']))
            for rally in result['rallies']:
                self.assertGreaterEqual(rally['start'], 0)
                self.assertLessEqual(rally['end'], 10)

    def test_unsupported_table_and_missing_file_fail_without_mock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'no-table.mp4'
            fixture(path, with_table=False, moving=False)
            with self.assertRaisesRegex(ValueError, '球桌'):
                analyze(path, 10, lambda *_: None)
        with self.assertRaisesRegex(ValueError, '无法打开'):
            analyze('/does/not/exist.mp4', 10, lambda *_: None)

    def test_fsm_splits_gaps_not_fixed_windows(self):
        tracks = [Track(1, [(t, 400+t*2, 200, .8) for t in (1, 1.2, 1.4, 1.6, 1.8, 2, 2.2, 2.4)]),
                  Track(2, [(t, 400+t*2, 200, .8) for t in (6, 6.2, 6.4, 6.6, 6.8, 7, 7.2, 7.4)])]
        rallies = segment_rallies(tracks, 10)
        self.assertEqual(len(rallies), 2)
        self.assertLess(rallies[0]['end'], rallies[1]['start'])
        self.assertEqual(segment_rallies([], 10), [])

    def test_color_calibration_rejects_green_floor(self):
        floor = np.full((540, 960, 3), (40, 110, 40), np.uint8)
        self.assertIsNone(find_table(floor))
        cv2.rectangle(floor, (120, 240), (840, 290), (150, 75, 75), -1)
        box = find_table(floor)
        self.assertIsNotNone(box)
        self.assertGreater(box[1], 200)
        self.assertLess(box[3], 310)

    def test_protocol_error_is_json_not_traceback(self):
        worker = Path(__file__).resolve().parents[1] / 'worker.py'
        for request in ({}, {'protocol_version':1, 'type':'analyze', 'job_id':'x',
                            'config':{'detector':'mock-v1'}, 'duration':10}):
            result = subprocess.run([sys.executable, worker], input=json.dumps(request)+'\n',
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['type'], 'error')
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
