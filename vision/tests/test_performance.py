import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from performance import ProcessingRate


class ProcessingRateTests(unittest.TestCase):
    def test_actual_completed_frames_not_video_time_or_source_fps(self):
        clock=[10.0]
        rate=ProcessingRate(lambda:clock[0])
        self.assertEqual(rate.snapshot()['average_fps'],0)
        rate.add(120);clock[0]=11.0
        first=rate.snapshot()
        self.assertEqual((first['processed_frames'],first['recent_fps'],first['average_fps']),(120,120,120))
        rate.add(60);clock[0]=13.0
        second=rate.snapshot()
        self.assertEqual(second['recent_fps'],30)
        self.assertEqual(second['average_fps'],60)
        self.assertEqual(second['elapsed_seconds'],3)

    def test_zero_interval_is_finite(self):
        rate=ProcessingRate(lambda:1)
        rate.add(3)
        self.assertEqual(rate.snapshot()['recent_fps'],0)
        self.assertEqual(rate.snapshot()['average_fps'],0)


if __name__=='__main__':unittest.main()
