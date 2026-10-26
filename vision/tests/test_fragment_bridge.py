"""Short detection dropouts are one rally; dead-ball evidence and cuts are not."""
from pathlib import Path
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rally_state


class StubValidity:
    def __init__(self):
        self.dead_intervals = []

    def finish(self, duration):
        return []


def rally(start, end, score=10):
    return {"start": start, "end": end, "confidence": .5, "score": score,
            "evidence": "visual", "selected": True, "edited": False}


class FragmentBridgeTests(unittest.TestCase):
    def test_short_dropout_becomes_one_rally(self):
        with patch.dict(os.environ, {"RALLYCUT_BRIDGE_GAP": "0.75"}), patch.object(rally_state, "segment_rallies", return_value=[rally(1, 2), rally(2.5, 3.5)]):
            output = rally_state.resegment([], [], 10, StubValidity(), finalize=True)
        self.assertEqual(len(output), 1)
        self.assertEqual((output[0]["start"], output[0]["end"]), (1, 3.5))
        self.assertTrue(output[0].get("bridged"))

    def test_default_does_not_bridge(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(rally_state, "segment_rallies", return_value=[rally(1, 2), rally(2.5, 3.5)]):
            out = rally_state.resegment([], [], 10, StubValidity(), finalize=True)
        self.assertEqual(len(out), 2)

    def test_camera_cut_blocks_the_bridge(self):
        calls = {"count": 0}

        def fake(*args, **kwargs):
            calls["count"] += 1
            return [rally(1, 2)] if calls["count"] == 1 else [rally(2.5, 3.5)]

        with patch.object(rally_state, "segment_rallies", side_effect=fake):
            output = rally_state.resegment([], [], 10, StubValidity(), finalize=True, cuts=(2.2,))
        self.assertEqual(len(output), 2)

    def test_long_gap_is_not_bridged(self):
        with patch.object(rally_state, "segment_rallies", return_value=[rally(1, 2), rally(3.0, 4.0)]):
            output = rally_state.resegment([], [], 10, StubValidity(), finalize=True)
        self.assertEqual(len(output), 2)


if __name__ == "__main__":
    unittest.main()
