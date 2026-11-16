from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from neural_analysis import LiveRefresh


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeStage:
    """rallies() cost grows with the horizon, like the real re-segmentation."""
    def __init__(self, clock):
        self.clock = clock
        self.calls = []

    def rallies(self, horizon):
        self.calls.append(horizon)
        # Measured on a 50-minute match: ~30 ms early, ~190 ms at 50 min.
        self.clock.now += .03 + horizon * 5.3e-5
        return [{'start': 0.0, 'end': horizon}]


class LiveRefreshTests(unittest.TestCase):
    def test_preview_cost_stays_a_bounded_share_of_wall_time(self):
        clock = FakeClock()
        stage = FakeStage(clock)
        live = LiveRefresh(ratio=30, clock=clock)
        # 50 minutes of video, a preview request every 2 s of video, and
        # ~0.25 s of decode / model work per 2 s (about 240 analysed fps).
        for horizon in range(0, 3000, 2):
            live.rallies(stage, float(horizon))
            clock.now += .25
        self.assertLess(live.seconds / clock.now, 1 / 30)
        # Requesting every time would cost sum(.03 + h * 5.3e-5) ~ 165 s.
        self.assertLess(live.seconds, 15)
        # Still refreshes regularly: roughly every 1-6 s of wall time.
        self.assertGreater(live.computed, 100)

    def test_skipped_requests_reuse_last_preview_and_force_recomputes(self):
        clock = FakeClock()
        stage = FakeStage(clock)
        live = LiveRefresh(ratio=30, clock=clock)
        first = live.rallies(stage, 1000.0)
        self.assertIs(live.rallies(stage, 1002.0), first)
        self.assertEqual(stage.calls, [1000.0])
        live.rallies(stage, 1004.0, force=True)
        self.assertEqual(stage.calls, [1000.0, 1004.0])


if __name__ == '__main__':
    unittest.main()
