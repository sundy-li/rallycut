"""Audio may label an existing visual rally, never create or move one."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_features import fuse_audio_visual
from visual import Track


def moving_track():
    return Track(1, [(2+i*.04, 400+i*70, 200, .8) for i in range(3)])


class AudioConfirmTests(unittest.TestCase):
    def test_confirm_mode_never_creates_rallies(self):
        impacts = [1, 1.4, 1.8, 2.2, 2.6, 3, 7, 7.4, 7.8, 8.2]
        self.assertEqual(fuse_audio_visual([], [moving_track()], impacts, 10, "confirm"), [])

    def test_confirm_mode_keeps_visual_boundaries(self):
        visual = [{"start": 2, "end": 4, "confidence": .7, "score": 50, "selected": True, "edited": False}]
        impacts = [1, 1.4, 1.8, 2.2, 2.6, 3, 7, 7.4, 7.8, 8.2]
        result = fuse_audio_visual(visual, [moving_track()], impacts, 10, "confirm")
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0]["start"], result[0]["end"]), (2, 4))
        self.assertEqual(result[0]["evidence"], "visual")
        self.assertEqual(result[0]["audio_hits"], 3)


if __name__ == "__main__":
    unittest.main()
