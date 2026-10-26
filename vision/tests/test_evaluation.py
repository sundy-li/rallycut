"""Unit tests for the local human-truth rally evaluation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation import Interval, evaluate, load_intervals


class EvaluationTests(unittest.TestCase):
    def test_perfect_match(self):
        truth = [Interval("a", 1, 3), Interval("b", 5, 8)]
        result = evaluate(truth, truth)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (2, 0, 0))
        self.assertEqual(result["f1"], 1.0)
        self.assertEqual(result["boundary_accuracy"], 1.0)

    def test_false_positive_and_empty_sets(self):
        result = evaluate([Interval("a", 1, 2)], [Interval("a", 1, 2), Interval("x", 5, 6)])
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 1, 0))
        empty = evaluate([], [])
        self.assertEqual((empty["tp"], empty["f1"]), (0, 0.0))

    def test_merge_is_counted_and_only_one_truth_is_matched(self):
        result = evaluate(
            [Interval("a", 0, 3), Interval("b", 3.5, 5)],
            [Interval("merged", 0, 5)],
        )
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["fn"], 1)
        self.assertEqual(len(result["merges"]), 1)
        self.assertEqual(result["merges"][0]["truth"], ["a", "b"])

    def test_split_is_counted(self):
        result = evaluate(
            [Interval("a", 0, 5)],
            [Interval("left", 0, 3), Interval("right", 3, 5)],
        )
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["fp"], 1)
        self.assertEqual(len(result["splits"]), 1)

    def test_threshold_and_boundary_accuracy_use_all_truth(self):
        result = evaluate(
            [Interval("a", 0, 10), Interval("b", 20, 30)],
            [Interval("a", 0.5, 10.5), Interval("b", 24, 34)],
        )
        self.assertEqual(result["tp"], 1)
        self.assertEqual(result["boundary_accuracy"], 0.5)

    def test_invalid_rallies_are_not_counted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manual.json"
            path.write_text(json.dumps({
                "active_source_id": "s1",
                "sources": [{"id": "s1", "rallies": [
                    {"id": "valid", "start": 1, "end": 2, "selected": True},
                    {"id": "net-replay", "start": 4, "end": 5, "selected": True, "invalid": True},
                ]}],
            }))
            self.assertEqual(load_intervals(path), [Interval("valid", 1, 2)])

    def test_ttcut_and_headless_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            ttcut = Path(directory) / "ttcut.json"
            ttcut.write_text(json.dumps({"rallies": [{"index": 3, "start_time_seconds": 2, "end_time_seconds": 4}]}))
            self.assertEqual(load_intervals(ttcut), [Interval("3", 2, 4)])
            headless = Path(directory) / "headless.json"
            headless.write_text(json.dumps({"segments": [{"id": "visual-1", "start": 1, "end": 2}]}))
            self.assertEqual(load_intervals(headless), [Interval("visual-1", 1, 2)])

    def test_invalid_boundaries_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"rallies": [{"start": 3, "end": 2}]}))
            with self.assertRaises(ValueError):
                load_intervals(path)


if __name__ == "__main__":
    unittest.main()


class LabeledScoreTests(unittest.TestCase):
    def doc(self, rallies, covered=((0, 100),), **extra):
        return {"covered": [list(c) for c in covered], "rallies": rallies, **extra}

    def test_only_covered_ranges_count_and_optional_never_counts(self):
        from evaluation import score_labels
        doc = self.doc([{"id": "a", "start": 10, "end": 15}, {"id": "let", "start": 30, "end": 33, "optional": True}],
                       covered=((0, 50),))
        cands = [{"start": 10.2, "end": 15.1}, {"start": 30.1, "end": 33}, {"start": 70, "end": 75}]
        s = score_labels(doc, cands)
        self.assertEqual((s["tp"], s["fp"], s["fn"]), (1, 0, 0))
        s = score_labels(doc, [{"start": 30.1, "end": 33}])
        self.assertEqual((s["tp"], s["fp"], s["fn"]), (0, 0, 1))
        self.assertEqual(s["missed"][0]["id"], "a")

    def test_start_conventions(self):
        from evaluation import score_labels
        # Labeled from the preparation: a serve-anchored start 5 s later is fine.
        prep = self.doc([{"id": "p", "start": 10, "end": 18, "start_convention": "serve_preparation"}])
        s = score_labels(prep, [{"start": 15, "end": 18.2}])
        self.assertEqual((s["tp"], s["boundary_accuracy"]), (1, 1.0))
        # Toss-labeled truth: only a bounce-start candidate may begin earlier.
        toss = self.doc([{"id": "t", "start": 15, "end": 18}])
        self.assertEqual(score_labels(toss, [{"start": 10, "end": 18, "start_reason": "serve_prep"}])["tp"], 1)
        self.assertEqual(score_labels(toss, [{"start": 10, "end": 18}])["tp"], 0)
        # Ends stay strict.
        self.assertEqual(score_labels(prep, [{"start": 15, "end": 25}])["tp"], 0)
