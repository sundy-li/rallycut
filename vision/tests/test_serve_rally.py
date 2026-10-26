"""A serve is a point: short serve flights are kept for the user to judge."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from visual import Track, segment_rallies


def flight(start, seconds, fps=30):
    return Track(1, [(start+i/fps, 300+i*3, 200, .8) for i in range(int(seconds*fps))])


class ServeRallyTests(unittest.TestCase):
    def test_short_first_flight_is_kept_with_serve_thresholds(self):
        short = flight(.5, .5)
        self.assertEqual(segment_rallies([short], 10), [])
        kept = segment_rallies([short], 10, first_min_duration=.35, first_min_observations=4, first_min_bins=2)
        self.assertEqual(len(kept), 1)

    def test_short_later_flight_still_needs_full_evidence(self):
        first = flight(0, 1.2)
        second = Track(2, [(3+i/30, 300+i*3, 200, .8) for i in range(15)])
        kept = segment_rallies([first, second], 10, first_min_duration=.35,
                               first_min_observations=4, first_min_bins=2)
        self.assertEqual(len(kept), 1)

    def test_serve_boundary_lead_is_separate_from_export_padding(self):
        first = flight(5, 1.2)
        kept = segment_rallies([first], 10, start_lead=1.6)
        self.assertAlmostEqual(kept[0]['start'], 3.4, places=6)

    def test_inactive_pickup_tail_and_later_return_toss_are_trimmed(self):
        speed = .015 / (1/30)
        self.assertGreater(speed, .4 * .6)
        points = [(3+i/30, .2+i*.015, .35, .9) for i in range(36)]
        points += [(4.25+i/30, .5+(i%2)*.002, .35, .9) for i in range(36)]
        points += [(5.7+i/30, .2+i*.015, .35, .9) for i in range(24)]
        kept = segment_rallies([Track(1, points)], 8, min_duration=1,
                               table_bounds=(.1, .2, .7, .5), start_lead=.1)
        self.assertEqual(len(kept), 1)
        self.assertLess(kept[0]['end'], 5.0)
        self.assertGreater(kept[0]['end'], 4.0)


if __name__ == "__main__":
    unittest.main()
